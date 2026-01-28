"""
AUTHENTICATION CONTROLLER
=========================
JWT-based authentication with:
- Signup and login
- PIN-based login for cashiers
- Role-based access control
- Multi-tenant isolation
- Screen lock/unlock
- Password hashing with bcrypt
"""

import jwt
import bcrypt
import hashlib
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from typing import Optional, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class AuthController:
    """Handle authentication and authorization"""
    
    def __init__(self, datastore, secret_key: str):
        """
        Initialize auth controller
        
        Args:
            datastore: DataStore instance
            secret_key: JWT secret key
        """
        self.ds = datastore
        self.secret_key = secret_key
    
    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            return bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False
    
    def generate_token(self, user: Dict, expires_hours: int = 24) -> str:
        """Generate JWT token for user"""
        # Handle both account_id and accountId field names
        account_id = user.get('account_id', user.get('accountId'))
        payload = {
            'user_id': user['id'],
            'email': user['email'],
            'role': user['role'],
            'account_id': account_id,
            'exp': datetime.utcnow() + timedelta(hours=expires_hours)
        }
        return jwt.encode(payload, self.secret_key, algorithm='HS256')
    
    def verify_token(self, token: str) -> Optional[Dict]:
        """Verify JWT token and return payload"""
        try:
            return jwt.decode(token, self.secret_key, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None
    
    def signup(self, email: str, password: str, name: str, plan: str = 'free', is_main_admin: bool = False, business_type: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create new account and user (owner or admin based on plan)
        
        Args:
            email: User email
            password: Password
            name: User name
            plan: Subscription plan (free, basic, ultra, enterprise)
            is_main_admin: If True, create as owner/main admin; otherwise create as regular admin
            business_type: Business type for Pro plan users (clinic, hotel, bar, etc.)
        
        Returns:
            (success, error_message, user_data_with_token)
        """
        try:
            # Check if email already exists
            existing_user = self.ds.get_user_by_email(email)
            if existing_user:
                return False, "Email already registered", None
            
            # All signups create 'admin' role users
            # Main admin dashboard (/main-admin) is accessed via direct URL only
            # Admins manage their business and create cashier users
            user_role = 'admin'  # All new signups are business admins
            
            # Create account
            account_id = hashlib.md5(email.encode()).hexdigest()[:16]
            account_data = {
                'id': account_id,
                'owner_email': email,
                'business_name': f"{name}'s Business",
                'plan': plan,
                'is_active': True,
                'is_locked': False,
                'trial_ends_at': (datetime.now() + timedelta(days=14)).isoformat() if plan == 'free' else None,
                'created_at': datetime.now().isoformat(),
                'currency': 'KES',
                'tax_rate': 0.0,
                'screen_lock_password': '2005',
                'days_used': 0,
                'requested_trial': False
            }
            
            # Check if account already exists
            existing_account = self.ds.get_account_by_email(email)
            if not existing_account:
                self.ds.create('accounts', account_data)
            else:
                account_id = existing_account['id']
            
            # Create user with appropriate role
            user_data = {
                'account_id': account_id,
                'email': email,
                'password_hash': self.hash_password(password),
                'name': name,
                'role': user_role,  # 'owner' for main admins, 'admin' for regular admins
                'is_active': True,
                'is_locked': False,
                'screen_locked': False,
                'created_at': datetime.now().isoformat(),
                'last_login': datetime.now().isoformat(),
                'hourly_rate': 0.0,
                'business_type': business_type,  # Store business type directly in user
                'business_role': 'admin'  # Default role for signups
            }
            user = self.ds.create('users', user_data)
            
            # Generate token
            token = self.generate_token(user)
            
            # Add plan to user response for frontend routing
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            user_response['plan'] = plan
            user_response['subscription'] = plan  # Add both for compatibility
            # Map is_active to active for frontend compatibility
            user_response['active'] = user.get('is_active', True)
            
            # Add businessType to response if it exists
            if business_type:
                user_response['businessType'] = business_type
                user_response['business_type'] = business_type  # Keep both formats
                logger.info(f"✅ Signup with business_type: {business_type}")
            
            # Log signup
            logger.info(f"✅ New signup: {email}")
            logger.info(f"   - Role: {user_role}")
            logger.info(f"   - Subscription: {plan}")
            logger.info(f"   - Business Type: {business_type or 'None'}")
            
            return True, None, {
                'user': user_response,
                'token': token
            }
            
        except Exception as e:
            logger.error(f"Signup error: {e}")
            return False, f"Signup failed: {str(e)}", None
    
    def login(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Login with email and password
        
        Args:
            email: User email
            password: Password
        
        Returns:
            (success, error_message, user_data_with_token)
        """
        try:
            # Get user
            user = self.ds.get_user_by_email(email)
            if not user:
                return False, "Invalid email or password", None
            
            # Verify password - handle both old (plaintext) and new (hashed) formats
            password_field = user.get('password_hash') or user.get('password')
            if not password_field:
                return False, "Invalid email or password", None
            
            # If password starts with $2b$, it's bcrypt hashed
            if password_field.startswith('$2b$'):
                password_valid = self.verify_password(password, password_field)
            else:
                # Plain text password (legacy format)
                password_valid = (password == password_field)
                
                # Upgrade to hashed password on successful login
                if password_valid:
                    hashed = self.hash_password(password)
                    self.ds.update('users', user['id'], {
                        'password_hash': hashed,
                        'password': None  # Remove plain text
                    })
                    logger.info(f"Upgraded password to hashed format for user {user['id']}")
            
            if not password_valid:
                return False, "Invalid email or password", None
            
            # Check if user is active
            if not user.get('is_active', user.get('active', True)):
                return False, "Account is inactive", None
            
            if user.get('is_locked'):
                return False, "Account is locked", None
            
            # Check account status
            account = self.ds.get_by_id('accounts', user.get('account_id', user.get('accountId')))
            if account:
                if not account.get('is_active', account.get('active', True)):
                    return False, "Account is inactive", None
                if account.get('is_locked'):
                    return False, "Account is locked", None
            
            # Update last login
            self.ds.update('users', user['id'], {
                'last_login': datetime.now().isoformat()
            })
            
            # Generate token
            token = self.generate_token(user)
            
            # CRITICAL: Get subscription plan from account (not from user)
            subscription = 'free'  # Default
            if account:
                subscription = account.get('plan', 'free')
                logger.info(f"✅ User subscription from account: {subscription}")
            
            # Return user data in the expected format
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            # Map is_active to active for frontend compatibility
            user_response['active'] = user.get('is_active', True)
            
            # CRITICAL: Always include subscription field (from account.plan)
            user_response['subscription'] = subscription
            user_response['plan'] = subscription  # Keep both for compatibility
            
            # Include businessType and businessRole if user has them (from user record)
            if user.get('business_type'):
                user_response['businessType'] = user.get('business_type')
                user_response['business_type'] = user.get('business_type')  # Keep both formats
                user_response['businessRole'] = user.get('business_role', 'cashier')
                user_response['business_role'] = user.get('business_role', 'cashier')  # Keep both formats
                logger.info(f"✅ User has business_type: {user.get('business_type')}, role: {user.get('business_role')}")
            
            # For Pro/Custom plan users without direct business_type, check business_profile
            if subscription in ['pro', 'custom'] and not user_response.get('businessType'):
                try:
                    profiles = self.ds.find('business_profiles', {'account_id': user['account_id']})
                    if profiles:
                        profile = profiles[0]
                        business_type = profile.get('business_type')
                        user_response['businessType'] = business_type
                        user_response['business_type'] = business_type
                        logger.info(f"✅ Added businessType from profile: {business_type}")
                except Exception as e:
                    logger.error(f"Failed to load business profile: {e}")
            
            # Log complete user info for debugging
            logger.info(f"✅ Login successful: {email}")
            logger.info(f"   - Role: {user_response.get('role')}")
            logger.info(f"   - Subscription: {user_response.get('subscription')}")
            logger.info(f"   - Business Type: {user_response.get('businessType', 'None')}")
            logger.info(f"   - Business Role: {user_response.get('businessRole', 'None')}")
            
            return True, None, {
                'user': user_response,
                'token': token
            }
            
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False, f"Login failed: {str(e)}", None
    
    def pin_login(self, pin: str, account_id: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Login with PIN (for cashiers)
        
        Args:
            pin: User PIN
            account_id: Optional account ID to narrow search
        
        Returns:
            (success, error_message, user_data_with_token)
        """
        try:
            # Get all users (or filter by account if provided)
            if account_id:
                users = self.ds.get_all('users', account_id)
            else:
                users = self.ds.get_all('users')
            
            # Find user with matching PIN
            user = None
            for u in users:
                if u.get('pin') == pin or u.get('cashier_pin') == pin:
                    user = u
                    break
            
            if not user:
                return False, "Invalid PIN", None
            
            # Check if user is active
            if not user.get('is_active'):
                return False, "Account is inactive", None
            
            if user.get('is_locked'):
                return False, "Account is locked", None
            
            # Update last login
            self.ds.update('users', user['id'], {
                'last_login': datetime.now().isoformat()
            })
            
            # Generate token
            token = self.generate_token(user)
            
            # Return user data in the expected format
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            # Map is_active to active for frontend compatibility
            user_response['active'] = user.get('is_active', True)
            
            return True, None, {
                'user': user_response,
                'token': token
            }
            
        except Exception as e:
            logger.error(f"PIN login error: {e}")
            return False, f"Login failed: {str(e)}", None
    
    def set_pin(self, user_id: int, pin: str, account_id: str) -> Tuple[bool, Optional[str]]:
        """
        Set/update user PIN
        
        Args:
            user_id: User ID
            pin: New PIN
            account_id: Account ID
        
        Returns:
            (success, error_message)
        """
        try:
            success = self.ds.update('users', user_id, {
                'pin': pin,
                'cashier_pin': pin
            }, account_id)
            
            if success:
                return True, None
            else:
                return False, "Failed to update PIN"
                
        except Exception as e:
            logger.error(f"Set PIN error: {e}")
            return False, f"Failed to set PIN: {str(e)}"
    
    def lock_screen(self, user_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        """
        Lock user screen
        
        Args:
            user_id: User ID
            account_id: Account ID
        
        Returns:
            (success, error_message)
        """
        try:
            success = self.ds.update('users', user_id, {
                'screen_locked': True
            }, account_id)
            
            if success:
                return True, None
            else:
                return False, "Failed to lock screen"
                
        except Exception as e:
            logger.error(f"Lock screen error: {e}")
            return False, f"Failed to lock screen: {str(e)}"
    
    def unlock_screen(self, user_id: int, pin: str, account_id: str) -> Tuple[bool, Optional[str]]:
        """
        Unlock user screen with PIN
        
        Args:
            user_id: User ID
            pin: 4-digit PIN
            account_id: Account ID
        
        Returns:
            (success, error_message)
        """
        try:
            # Get user
            user = self.ds.get_by_id('users', user_id, account_id)
            if not user:
                return False, "User not found"
            
            # Verify PIN
            user_pin = user.get('pin')
            if not user_pin:
                # If user has no PIN set, try default account PIN
                account = self.ds.get_by_id('accounts', account_id)
                if account:
                    default_pin = account.get('screen_lock_password', '2005')
                    if pin != default_pin:
                        return False, "Invalid PIN"
                else:
                    return False, "No PIN configured for this user"
            elif user_pin != pin:
                return False, "Invalid PIN"
            
            # Unlock screen
            success = self.ds.update('users', user_id, {
                'screen_locked': False
            }, account_id)
            
            if success:
                return True, None
            else:
                return False, "Failed to unlock screen"
                
        except Exception as e:
            logger.error(f"Unlock screen error: {e}")
            return False, f"Failed to unlock screen: {str(e)}"
    
    def require_auth(self, f):
        """
        Decorator to require authentication
        
        Usage:
            @auth.require_auth
            def protected_route():
                user = request.user  # Injected by decorator
                ...
        """
        @wraps(f)
        def decorated(*args, **kwargs):
            token = None
            
            # Get token from Authorization header
            if 'Authorization' in request.headers:
                auth_header = request.headers['Authorization']
                if auth_header.startswith('Bearer '):
                    token = auth_header[7:]
            
            if not token:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Verify token
            payload = self.verify_token(token)
            if not payload:
                return jsonify({'error': 'Invalid or expired token'}), 401
            
            # Get user - try with account_id first, fallback to just user_id for legacy data
            account_id = payload.get('account_id')
            user_id = payload.get('user_id')
            
            if not user_id:
                logger.error(f"Invalid token payload: user_id={user_id}")
                return jsonify({'error': 'Invalid token payload'}), 401
            
            # Try to get user with account isolation first
            user = None
            if account_id:
                user = self.ds.get_by_id('users', user_id, account_id)
            
            # Fallback to getting user without account isolation (for legacy data)
            if not user:
                user = self.ds.get_by_id('users', user_id)
            
            if not user:
                logger.error(f"User not found: user_id={user_id}, account_id={account_id}")
                return jsonify({'error': 'User not found'}), 401
            
            # Check if user is active - handle both field name formats
            is_active = user.get('is_active', user.get('active', True))
            is_locked = user.get('is_locked', False)
            if not is_active or is_locked:
                return jsonify({'error': 'Account is inactive or locked'}), 403
            
            # Map is_active to active for frontend compatibility
            user['active'] = user.get('is_active', True)
            
            # Inject user and account_id into request
            request.user = user
            request.account_id = account_id
            
            return f(*args, **kwargs)
        
        return decorated
    
    def require_role(self, *allowed_roles):
        """
        Decorator to require specific role
        
        Usage:
            @auth.require_role('owner', 'admin')
            def admin_only_route():
                ...
        """
        def decorator(f):
            @wraps(f)
            def decorated(*args, **kwargs):
                if not hasattr(request, 'user'):
                    return jsonify({'error': 'Authentication required'}), 401
                
                user_role = request.user.get('role')
                if user_role not in allowed_roles:
                    return jsonify({'error': 'Insufficient permissions'}), 403
                
                return f(*args, **kwargs)
            
            return decorated
        return decorator
    
    def get_current_user(self) -> Optional[Dict]:
        """Get current authenticated user from request context"""
        return getattr(request, 'user', None)
    
    def get_current_account_id(self) -> Optional[str]:
        """Get current account ID from request context"""
        return getattr(request, 'account_id', None)
