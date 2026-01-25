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
        payload = {
            'user_id': user['id'],
            'email': user['email'],
            'role': user['role'],
            'account_id': user['account_id'],
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
    
    def signup(self, email: str, password: str, name: str, plan: str = 'free') -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Create new account and owner user
        
        Args:
            email: User email (also account owner email)
            password: Password
            name: User name
            plan: Subscription plan
        
        Returns:
            (success, error_message, user_data_with_token)
        """
        try:
            # Check if email already exists
            existing_user = self.ds.get_user_by_email(email)
            if existing_user:
                return False, "Email already registered", None
            
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
            
            # Create owner user
            user_data = {
                'account_id': account_id,
                'email': email,
                'password_hash': self.hash_password(password),
                'name': name,
                'role': 'owner',
                'is_active': True,
                'is_locked': False,
                'screen_locked': False,
                'created_at': datetime.now().isoformat(),
                'last_login': datetime.now().isoformat(),
                'hourly_rate': 0.0
            }
            user = self.ds.create('users', user_data)
            
            # Generate token
            token = self.generate_token(user)
            
            # Return user data (without password_hash) in the expected format
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            
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
            
            # Verify password
            if not self.verify_password(password, user['password_hash']):
                return False, "Invalid email or password", None
            
            # Check if user is active
            if not user.get('is_active'):
                return False, "Account is inactive", None
            
            if user.get('is_locked'):
                return False, "Account is locked", None
            
            # Check account status
            account = self.ds.get_by_id('accounts', user['account_id'])
            if account:
                if not account.get('is_active'):
                    return False, "Account is inactive", None
                if account.get('is_locked'):
                    return False, "Account is locked", None
            
            # Update last login
            self.ds.update('users', user['id'], {
                'last_login': datetime.now().isoformat()
            })
            
            # Generate token
            token = self.generate_token(user)
            
            # Return user data in the expected format
            user_response = {k: v for k, v in user.items() if k != 'password_hash'}
            
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
    
    def unlock_screen(self, user_id: int, password: str, account_id: str) -> Tuple[bool, Optional[str]]:
        """
        Unlock user screen with password
        
        Args:
            user_id: User ID
            password: Screen lock password (from account settings)
            account_id: Account ID
        
        Returns:
            (success, error_message)
        """
        try:
            # Get account settings
            account = self.ds.get_by_id('accounts', account_id)
            if not account:
                return False, "Account not found"
            
            # Verify password
            screen_lock_password = account.get('screen_lock_password', '2005')
            if password != screen_lock_password:
                return False, "Invalid password"
            
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
            
            # Get user
            user = self.ds.get_by_id('users', payload['user_id'])
            if not user:
                return jsonify({'error': 'User not found'}), 401
            
            # Check if user is active
            if not user.get('is_active') or user.get('is_locked'):
                return jsonify({'error': 'Account is inactive or locked'}), 403
            
            # Inject user into request
            request.user = user
            request.account_id = payload['account_id']
            
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
