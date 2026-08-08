"""
Internal Messaging System for Business Communication
Allows role-to-role messaging within business types
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import Blueprint, request, jsonify
from functools import wraps
import jwt
import os

# Create Blueprint
message_bp = Blueprint('messages', __name__, url_prefix='/api/messages')

try:
    from business_types import get_roles_for_business_type
except Exception:
    def get_roles_for_business_type(_business_type):
        return []

def require_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'No token provided'}), 401
        
        try:
            secret = os.environ.get('JWT_SECRET')
            if not secret:
                return jsonify({'error': 'Server misconfigured: JWT_SECRET missing'}), 500
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            request.user = payload
            return f(*args, **kwargs)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
    
    return decorated


def init_messages_table(ds):
    """Initialize messages table in database"""
    # Create messages table if it doesn't exist
    messages_table = ds.tables.get('messages', {})
    if not messages_table:
        ds.tables['messages'] = {}
        ds.save_all()


@message_bp.route('/send', methods=['POST'])
@require_auth
def send_message():
    """
    Send a message from one role to another within same business
    
    POST /api/messages/send
    {
        "toRole": "doctor",
        "content": "Patient in room 5 needs attention",
        "priority": "normal"
    }
    """
    from database import DataStore
    ds = DataStore()
    init_messages_table(ds)
    
    try:
        data = request.json
        user = request.user
        
        # Validate required fields
        if not data.get('toRole') or not data.get('content'):
            return jsonify({'error': 'toRole and content are required'}), 400
        
        # Get user details
        user_id = user.get('id')
        user_data = ds.get_by_id('users', user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        
        from_role = user_data.get('business_role') or user_data.get('role')
        business_type = user_data.get('business_type')
        account_id = user_data.get('account_id')
        
        if not business_type:
            return jsonify({'error': 'User must be in a business to send messages'}), 400
        
        # Create message
        message_id = f"msg_{datetime.now().timestamp()}"
        message = {
            'id': message_id,
            'fromUserId': user_id,
            'fromUserName': user_data.get('name'),
            'fromRole': from_role,
            'toRole': data['toRole'],
            'businessType': business_type,
            'accountId': account_id,
            'content': data['content'],
            'priority': data.get('priority', 'normal'),
            'status': 'sent',
            'timestamp': datetime.now().isoformat(),
            'readAt': None
        }
        
        # Save message
        ds.create('messages', message)
        
        return jsonify({
            'success': True,
            'message': 'Message sent successfully',
            'messageId': message_id
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@message_bp.route('/inbox', methods=['GET'])
@require_auth
def get_inbox():
    """
    Get all messages for current user's role
    
    GET /api/messages/inbox?status=unread&limit=50
    """
    from database import DataStore
    ds = DataStore()
    init_messages_table(ds)
    
    try:
        user = request.user
        user_id = user.get('id')
        
        # Get user details
        user_data = ds.get_by_id('users', user_id)
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        
        user_role = user_data.get('business_role') or user_data.get('role')
        business_type = user_data.get('business_type')
        account_id = user_data.get('account_id')
        
        if not business_type:
            return jsonify({'messages': []}), 200
        
        # Query parameters
        status = request.args.get('status')  # unread, read, all
        limit = int(request.args.get('limit', 50))
        
        # Find messages for this role
        all_messages = ds.find('messages', {
            'toRole': user_role,
            'businessType': business_type,
            'accountId': account_id
        })
        
        # Filter by status if specified
        if status == 'unread':
            all_messages = [m for m in all_messages if m['status'] == 'sent']
        elif status == 'read':
            all_messages = [m for m in all_messages if m['status'] == 'read']
        
        # Sort by timestamp (newest first)
        all_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Limit results
        messages = all_messages[:limit]
        
        return jsonify({
            'messages': messages,
            'total': len(all_messages),
            'unreadCount': len([m for m in all_messages if m['status'] == 'sent'])
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@message_bp.route('/<message_id>/read', methods=['PUT'])
@require_auth
def mark_as_read(message_id):
    """
    Mark a message as read
    
    PUT /api/messages/{message_id}/read
    """
    from database import DataStore
    ds = DataStore()
    
    try:
        message = ds.get_by_id('messages', message_id)
        if not message:
            return jsonify({'error': 'Message not found'}), 404
        
        user = request.user
        user_account_id = user.get('account_id')
        message_account_id = message.get('accountId')
        if user_account_id and message_account_id and user_account_id != message_account_id:
            return jsonify({'error': 'Access denied'}), 403
        
        ds.update('messages', message_id, {
            'status': 'read',
            'readAt': datetime.now().isoformat()
        })
        
        return jsonify({
            'success': True,
            'message': 'Message marked as read'
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@message_bp.route('/available-roles', methods=['GET'], endpoint='available_roles')
@require_auth
def get_available_roles():
    """Get available business roles for current user's business type"""
    from database import DataStore
    ds = DataStore()
    init_messages_table(ds)

    try:
        user = request.user
        user_id = user.get('id')
        user_data = ds.get_by_id('users', user_id)
        if not user_data:
            return jsonify({'roles': []}), 200

        business_type = user_data.get('business_type')
        roles = get_roles_for_business_type(business_type) if business_type else []

        return jsonify({'roles': roles}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@message_bp.route('/sent', methods=['GET'])
@require_auth
def get_sent_messages():
    """
    Get all messages sent by current user
    
    GET /api/messages/sent?limit=50
    """
    from database import DataStore
    ds = DataStore()
    
    try:
        user = request.user
        user_id = user.get('id')
        
        limit = int(request.args.get('limit', 50))
        
        # Find messages sent by this user
        all_messages = ds.find('messages', {
            'fromUserId': user_id
        })
        
        # Sort by timestamp (newest first)
        all_messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Limit results
        messages = all_messages[:limit]
        
        return jsonify({
            'messages': messages,
            'total': len(all_messages)
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


