"""
Authentication Tests
====================
Test user signup, login, PIN authentication, and screen lock.
"""

import pytest
from datetime import datetime


class TestSignup:
    """Test user signup functionality"""
    
    def test_signup_with_valid_data(self, auth_controller):
        """Test successful signup with valid data"""
        success, error, result = auth_controller.signup(
            email='newuser@example.com',
            password='ValidPassword123!',
            name='New User',
            plan='free'
        )
        
        assert success is True
        assert error is None
        assert result is not None
        assert 'user' in result
        assert 'token' in result
        assert result['user']['email'] == 'newuser@example.com'
        assert result['user']['name'] == 'New User'
    
    def test_signup_with_duplicate_email(self, auth_controller):
        """Test signup fails with duplicate email"""
        # First signup
        auth_controller.signup(
            email='duplicate@example.com',
            password='Password123!',
            name='First User'
        )
        
        # Second signup with same email
        success, error, result = auth_controller.signup(
            email='duplicate@example.com',
            password='Password456!',
            name='Second User'
        )
        
        assert success is False
        assert error is not None
        assert 'already registered' in error.lower()
    
    def test_signup_with_weak_password(self, auth_controller):
        """Test that weak passwords are accepted (no policy yet)"""
        success, error, result = auth_controller.signup(
            email='weak@example.com',
            password='123',
            name='Weak Pass User'
        )
        
        # Currently accepts any password - should add validation
        assert success is True


class TestLogin:
    """Test user login functionality"""
    
    def test_login_with_valid_credentials(self, auth_controller, test_account):
        """Test successful login with correct credentials"""
        success, error, result = auth_controller.login(
            email='test@example.com',
            password='TestPassword123!'
        )
        
        assert success is True
        assert error is None
        assert result is not None
        assert 'user' in result
        assert 'token' in result
    
    def test_login_with_invalid_password(self, auth_controller, test_account):
        """Test login fails with wrong password"""
        success, error, result = auth_controller.login(
            email='test@example.com',
            password='WrongPassword'
        )
        
        assert success is False
        assert error is not None
    
    def test_login_with_nonexistent_email(self, auth_controller):
        """Test login fails with non-existent email"""
        success, error, result = auth_controller.login(
            email='nonexistent@example.com',
            password='AnyPassword'
        )
        
        assert success is False
        assert error is not None


class TestPasswordHashing:
    """Test password hashing and verification"""
    
    def test_password_hashed_not_plain_text(self, auth_controller):
        """Test that passwords are hashed, not stored as plain text"""
        password = 'SecretPassword123!'
        hashed = auth_controller.hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long
    
    def test_same_password_different_hashes(self, auth_controller):
        """Test that same password produces different hashes (salt)"""
        password = 'SamePassword123!'
        hash1 = auth_controller.hash_password(password)
        hash2 = auth_controller.hash_password(password)
        
        assert hash1 != hash2  # Different salts
    
    def test_password_verification(self, auth_controller):
        """Test password verification works correctly"""
        password = 'MyPassword123!'
        hashed = auth_controller.hash_password(password)
        
        assert auth_controller.verify_password(password, hashed) is True
        assert auth_controller.verify_password('WrongPassword', hashed) is False


class TestTokenGeneration:
    """Test JWT token generation and verification"""
    
    def test_token_generation(self, auth_controller, test_account, datastore):
        """Test that valid tokens are generated"""
        user = datastore.get_by_id('users', test_account['user_id'], test_account['account_id'])
        token = auth_controller.generate_token(user)
        
        assert token is not None
        assert len(token) > 0
    
    def test_token_verification(self, auth_controller, test_account):
        """Test that tokens can be verified"""
        payload = auth_controller.verify_token(test_account['token'])
        
        assert payload is not None
        assert payload['user_id'] == test_account['user_id']
        assert payload['email'] == test_account['email']
        assert payload['account_id'] == test_account['account_id']
    
    def test_invalid_token_rejected(self, auth_controller):
        """Test that invalid tokens are rejected"""
        payload = auth_controller.verify_token('invalid.token.here')
        
        assert payload is None


class TestScreenLock:
    """Test screen lock functionality"""
    
    def test_lock_screen(self, auth_controller, test_account, datastore):
        """Test locking user screen"""
        success = auth_controller.lock_screen(
            test_account['user_id'],
            test_account['account_id']
        )
        
        assert success is True
        
        # Verify user is locked
        user = datastore.get_by_id('users', test_account['user_id'], test_account['account_id'])
        assert user['screen_locked'] is True
    
    def test_unlock_screen_with_correct_pin(self, auth_controller, test_account, datastore):
        """Test unlocking with correct PIN"""
        # Set PIN for user
        datastore.update('users', test_account['user_id'], {'pin': '1234'}, test_account['account_id'])
        
        # Lock screen
        auth_controller.lock_screen(test_account['user_id'], test_account['account_id'])
        
        # Unlock with correct PIN
        success, error = auth_controller.unlock_screen(
            test_account['user_id'],
            '1234',
            test_account['account_id']
        )
        
        assert success is True
        assert error is None
    
    def test_unlock_screen_with_wrong_pin(self, auth_controller, test_account, datastore):
        """Test unlocking fails with wrong PIN"""
        # Set PIN for user
        datastore.update('users', test_account['user_id'], {'pin': '1234'}, test_account['account_id'])
        
        # Lock screen
        auth_controller.lock_screen(test_account['user_id'], test_account['account_id'])
        
        # Try to unlock with wrong PIN
        success, error = auth_controller.unlock_screen(
            test_account['user_id'],
            '9999',
            test_account['account_id']
        )
        
        assert success is False
        assert error is not None
