"""
BUSINESS MANAGEMENT ENDPOINTS
==============================
API endpoints for managing business types, roles, and Pro/Custom plan features.
"""

from flask import Blueprint, request, jsonify
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Import business types configuration
try:
    from business_types import (
        get_available_business_types,
        get_business_type_config,
        get_roles_for_business_type,
        validate_business_role,
        get_features_for_business_type,
        get_dashboard_route
    )
except ImportError:
    logger.error("Failed to import business_types module")
    # Provide fallback functions
    def get_available_business_types():
        return []
    def get_business_type_config(bt):
        return {}
    def get_roles_for_business_type(bt):
        return []
    def validate_business_role(bt, role):
        return True
    def get_features_for_business_type(bt):
        return []
    def get_dashboard_route(bt):
        return "/admin"


def create_business_routes(datastore, auth_controller):
    """Create business management routes"""
    
    business_bp = Blueprint('business', __name__)
    
    # ============================================================
    # PUBLIC ENDPOINTS - Business Type Information
    # ============================================================
    
    @business_bp.route('/business-types', methods=['GET', 'OPTIONS'])
    def get_business_types():
        """Get list of all available business types for Pro/Custom plans"""
        try:
            business_types = get_available_business_types()
            return jsonify({
                'success': True,
                'businessTypes': business_types
            }), 200
        except Exception as e:
            logger.error(f"Error fetching business types: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/business-types/<business_type>', methods=['GET', 'OPTIONS'])
    def get_business_type_details(business_type):
        """Get detailed configuration for a specific business type"""
        try:
            config = get_business_type_config(business_type)
            if not config:
                return jsonify({'error': 'Business type not found'}), 404
            
            return jsonify({
                'success': True,
                'businessType': config
            }), 200
        except Exception as e:
            logger.error(f"Error fetching business type details: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/business-types/<business_type>/roles', methods=['GET', 'OPTIONS'])
    def get_business_roles(business_type):
        """Get available roles for a specific business type"""
        try:
            roles = get_roles_for_business_type(business_type)
            return jsonify({
                'success': True,
                'roles': roles
            }), 200
        except Exception as e:
            logger.error(f"Error fetching business roles: {e}")
            return jsonify({'error': str(e)}), 500
    
    # ============================================================
    # PROTECTED ENDPOINTS - Require Authentication
    # ============================================================
    
    @business_bp.route('/select', methods=['POST', 'OPTIONS'])
    @auth_controller.require_auth
    def select_business_type():
        """
        Allow Pro/Custom plan admin to select or change their business type.
        This sets up the business profile for the account.
        """
        try:
            user = request.user
            account_id = user.get('account_id')
            
            # Verify user is admin
            if user.get('role') != 'admin':
                return jsonify({'error': 'Only admins can select business type'}), 403
            
            # Verify user is on Pro or Custom plan
            account = datastore.get_by_id('accounts', account_id)
            if not account or account.get('plan') not in ['pro', 'custom']:
                return jsonify({'error': 'Business type selection is only available for Pro and Custom plans'}), 403
            
            data = request.get_json()
            business_type = data.get('business_type')
            
            if not business_type:
                return jsonify({'error': 'business_type is required'}), 400
            
            # Validate business type exists
            config = get_business_type_config(business_type)
            if not config:
                return jsonify({'error': f'Invalid business type: {business_type}'}), 400
            
            # Update user's business type
            datastore.update('users', user['id'], {
                'business_type': business_type,
                'business_role': 'admin'  # Admin who selects gets admin role
            })
            
            # Create or update business profile
            existing_profiles = datastore.find('business_profiles', {'account_id': account_id})
            
            profile_data = {
                'account_id': account_id,
                'business_type': business_type,
                'plan': account.get('plan', 'pro'),
                'owner_id': user['id'],
                'settings': data.get('settings', {}),
                'features': get_features_for_business_type(business_type)
            }
            
            if existing_profiles:
                # Update existing profile
                profile = existing_profiles[0]
                datastore.update('business_profiles', profile['id'], profile_data)
                logger.info(f"✅ Updated business profile for {account_id}: {business_type}")
            else:
                # Create new profile
                datastore.create('business_profiles', profile_data)
                logger.info(f"✅ Created business profile for {account_id}: {business_type}")
            
            # Return updated user info with business type
            updated_user = datastore.get_by_id('users', user['id'])
            return jsonify({
                'success': True,
                'message': f'Business type set to {config["name"]}',
                'businessType': business_type,
                'dashboardRoute': get_dashboard_route(business_type),
                'user': {
                    'id': updated_user['id'],
                    'email': updated_user['email'],
                    'name': updated_user['name'],
                    'role': updated_user['role'],
                    'business_type': updated_user.get('business_type'),
                    'business_role': updated_user.get('business_role')
                }
            }), 200
            
        except Exception as e:
            logger.error(f"Error selecting business type: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/profile', methods=['GET', 'OPTIONS'])
    @auth_controller.require_auth
    def get_business_profile():
        """Get business profile for the current user's account"""
        try:
            user = request.user
            account_id = user.get('account_id')
            
            # Find business profile
            profiles = datastore.find('business_profiles', {'account_id': account_id})
            
            if not profiles:
                return jsonify({
                    'success': True,
                    'profile': None,
                    'message': 'No business profile configured'
                }), 200
            
            profile = profiles[0]
            business_type = profile.get('business_type')
            
            # Enrich with configuration
            config = get_business_type_config(business_type)
            profile['config'] = config
            
            return jsonify({
                'success': True,
                'profile': profile
            }), 200
            
        except Exception as e:
            logger.error(f"Error fetching business profile: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/users', methods=['POST', 'OPTIONS'])
    @auth_controller.require_auth
    def create_business_user():
        """
        Create a user under the admin's business with a specific business role.
        Only admins on Pro/Custom plans can create business users.
        """
        try:
            admin_user = request.user
            account_id = admin_user.get('account_id')
            
            # Verify user is admin
            if admin_user.get('role') != 'admin':
                return jsonify({'error': 'Only admins can create business users'}), 403
            
            # Get account and verify Pro/Custom plan
            account = datastore.get_by_id('accounts', account_id)
            if not account or account.get('plan') not in ['pro', 'custom']:
                return jsonify({'error': 'Business users are only available for Pro and Custom plans'}), 403
            
            # Get admin's business type
            admin_business_type = admin_user.get('business_type')
            if not admin_business_type:
                return jsonify({'error': 'Please select a business type first'}), 400
            
            data = request.get_json()
            email = data.get('email')
            name = data.get('name')
            password = data.get('password', 'changeme123')  # Default password
            business_role = data.get('business_role', 'cashier')  # Default to cashier
            
            if not email or not name:
                return jsonify({'error': 'email and name are required'}), 400
            
            # Validate business role for this business type
            if not validate_business_role(admin_business_type, business_role):
                available_roles = get_roles_for_business_type(admin_business_type)
                return jsonify({
                    'error': f'Invalid business role for {admin_business_type}',
                    'availableRoles': available_roles
                }), 400
            
            # Check if user already exists
            existing_user = datastore.get_user_by_email(email)
            if existing_user:
                return jsonify({'error': 'Email already registered'}), 400
            
            # Create new business user
            import bcrypt
            from datetime import datetime
            
            # Hash password using bcrypt
            password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            user_data = {
                'account_id': account_id,
                'email': email,
                'password_hash': password_hash,
                'name': name,
                'role': 'cashier',  # System role is cashier (not admin)
                'business_type': admin_business_type,  # Inherit from admin
                'business_role': business_role,  # Specific business role (doctor, waiter, etc.)
                'is_active': True,
                'is_locked': False,
                'screen_locked': False,
                'pin': data.get('pin', None),  # Optional PIN for quick login
                'created_at': datetime.now().isoformat(),
                'last_login': None,
                'hourly_rate': data.get('hourly_rate', 0.0)
            }
            
            new_user = datastore.create('users', user_data)
            
            # Remove sensitive data
            user_response = {k: v for k, v in new_user.items() if k != 'password_hash'}
            
            logger.info(f"✅ Created business user: {email} with role {business_role} for {admin_business_type}")
            
            return jsonify({
                'success': True,
                'message': f'User created successfully',
                'user': user_response,
                'defaultPassword': password
            }), 201
            
        except Exception as e:
            logger.error(f"Error creating business user: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/users', methods=['GET', 'OPTIONS'])
    @auth_controller.require_auth
    def get_business_users():
        """Get all users in the admin's business"""
        try:
            admin_user = request.user
            account_id = admin_user.get('account_id')
            
            # Get all users for this account
            all_users = datastore.find('users', {'account_id': account_id})
            
            # Remove sensitive data
            users_response = []
            for user in all_users:
                user_data = {k: v for k, v in user.items() if k != 'password_hash'}
                users_response.append(user_data)
            
            return jsonify({
                'success': True,
                'users': users_response
            }), 200
            
        except Exception as e:
            logger.error(f"Error fetching business users: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/users/<user_id>', methods=['PUT', 'OPTIONS'])
    @auth_controller.require_auth
    def update_business_user(user_id):
        """Update a business user's information or role"""
        try:
            admin_user = request.user
            account_id = admin_user.get('account_id')
            
            # Verify user is admin
            if admin_user.get('role') != 'admin':
                return jsonify({'error': 'Only admins can update business users'}), 403
            
            # Get the user to update
            user_to_update = datastore.get_by_id('users', user_id)
            if not user_to_update:
                return jsonify({'error': 'User not found'}), 404
            
            # Verify user belongs to same account
            if user_to_update.get('account_id') != account_id:
                return jsonify({'error': 'Cannot update users from other accounts'}), 403
            
            # Get update data
            data = request.get_json()
            
            # Build update object (only allow certain fields)
            update_data = {}
            allowed_fields = ['name', 'business_role', 'is_active', 'hourly_rate']
            
            for field in allowed_fields:
                if field in data:
                    update_data[field] = data[field]
            
            # If updating business_role, validate it
            if 'business_role' in update_data:
                business_type = admin_user.get('business_type')
                if not validate_business_role(business_type, update_data['business_role']):
                    return jsonify({'error': 'Invalid business role'}), 400
            
            # Update user
            datastore.update('users', user_id, update_data)
            
            # Get updated user
            updated_user = datastore.get_by_id('users', user_id)
            user_response = {k: v for k, v in updated_user.items() if k != 'password_hash'}
            
            return jsonify({
                'success': True,
                'message': 'User updated successfully',
                'user': user_response
            }), 200
            
        except Exception as e:
            logger.error(f"Error updating business user: {e}")
            return jsonify({'error': str(e)}), 500
    
    @business_bp.route('/users/<user_id>', methods=['DELETE', 'OPTIONS'])
    @auth_controller.require_auth
    def delete_business_user(user_id):
        """Delete a business user"""
        try:
            admin_user = request.user
            account_id = admin_user.get('account_id')
            
            # Verify user is admin
            if admin_user.get('role') != 'admin':
                return jsonify({'error': 'Only admins can delete business users'}), 403
            
            # Get the user to delete
            user_to_delete = datastore.get_by_id('users', user_id)
            if not user_to_delete:
                return jsonify({'error': 'User not found'}), 404
            
            # Verify user belongs to same account
            if user_to_delete.get('account_id') != account_id:
                return jsonify({'error': 'Cannot delete users from other accounts'}), 403
            
            # Prevent deleting self
            if user_id == admin_user['id']:
                return jsonify({'error': 'Cannot delete yourself'}), 403
            
            # Prevent deleting other admins
            if user_to_delete.get('role') == 'admin':
                return jsonify({'error': 'Cannot delete other admins'}), 403
            
            # Delete user
            datastore.delete('users', user_id)
            
            logger.info(f"✅ Deleted business user: {user_to_delete.get('email')}")
            
            return jsonify({
                'success': True,
                'message': 'User deleted successfully'
            }), 200
            
        except Exception as e:
            logger.error(f"Error deleting business user: {e}")
            return jsonify({'error': str(e)}), 500
    
    return business_bp
