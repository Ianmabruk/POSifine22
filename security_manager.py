"""
Security Enhancements Module
Rate limiting, CSRF protection, input validation
"""

import time
import re
import secrets
from functools import wraps
from flask import request, jsonify

class SecurityManager:
    def __init__(self):
        self.rate_limits = {}
        self.csrf_tokens = {}
    
    def rate_limit(self, max_requests=60, window=60):
        """Rate limiting decorator"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                client_ip = request.remote_addr
                current_time = time.time()
                
                if client_ip not in self.rate_limits:
                    self.rate_limits[client_ip] = []
                
                # Clean old requests
                self.rate_limits[client_ip] = [
                    req_time for req_time in self.rate_limits[client_ip]
                    if current_time - req_time < window
                ]
                
                if len(self.rate_limits[client_ip]) >= max_requests:
                    return jsonify({'error': 'Rate limit exceeded'}), 429
                
                self.rate_limits[client_ip].append(current_time)
                return func(*args, **kwargs)
            return wrapper
        return decorator
    
    def generate_csrf_token(self, user_id):
        """Generate CSRF token"""
        token = secrets.token_urlsafe(32)
        self.csrf_tokens[user_id] = token
        return token
    
    def validate_csrf_token(self, user_id, token):
        """Validate CSRF token"""
        return self.csrf_tokens.get(user_id) == token
    
    def validate_input(self, data, rules):
        """Input validation"""
        errors = []
        
        for field, rule in rules.items():
            value = data.get(field)
            
            if rule.get('required') and not value:
                errors.append(f"{field} is required")
                continue
            
            if value and rule.get('type') == 'email':
                if not re.match(r'^[^@]+@[^@]+\.[^@]+$', value):
                    errors.append(f"{field} must be valid email")
            
            if value and rule.get('min_length'):
                if len(str(value)) < rule['min_length']:
                    errors.append(f"{field} must be at least {rule['min_length']} characters")
            
            if value and rule.get('max_length'):
                if len(str(value)) > rule['max_length']:
                    errors.append(f"{field} must be less than {rule['max_length']} characters")
        
        return errors

# Usage decorators
def require_csrf(security_manager):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_id = getattr(request, 'user', {}).get('id')
            token = request.headers.get('X-CSRF-Token')
            
            if not security_manager.validate_csrf_token(user_id, token):
                return jsonify({'error': 'Invalid CSRF token'}), 403
            
            return func(*args, **kwargs)
        return wrapper
    return decorator

def validate_json(rules):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            data = request.get_json() or {}
            security = SecurityManager()
            errors = security.validate_input(data, rules)
            
            if errors:
                return jsonify({'error': 'Validation failed', 'details': errors}), 400
            
            return func(*args, **kwargs)
        return wrapper
    return decorator