"""
Authentication Tests
====================
Test user signup, login, PIN authentication, and screen lock.
"""

import pytest
from datetime import datetime


class TestSignup:
    """Test user signup functionality"""
    
    def test_signup_with_valid_data(self, auth_service):
        """Test successful signup with valid data"""
        success, error, result = auth_service.signup(
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
    
    def test_signup_with_duplicate_email(self, auth_service):
        """Test signup fails with duplicate email"""
        # First signup
        auth_service.signup(
            email='duplicate@example.com',
            password='Password123!',
            name='First User'
        )
        
        # Second signup with same email
        success, error, result = auth_service.signup(
            email='duplicate@example.com',
            password='Password456!',
            name='Second User'
        )
        
        assert success is False
        assert error is not None
        assert 'already registered' in error.lower()
    
    def test_signup_with_weak_password(self, auth_service):
        """Test that weak passwords are accepted (no policy yet)"""
        success, error, result = auth_service.signup(
            email='weak@example.com',
            password='123',
            name='Weak Pass User'
        )
        
        # Currently accepts any password - should add validation
        assert success is True


class TestLogin:
    """Test user login functionality"""
    
    def test_login_with_valid_credentials(self, auth_service, test_account):
        """Test successful login with correct credentials"""
        success, error, result = auth_service.login(
            email='test@example.com',
            password='TestPassword123!'
        )
        
        assert success is True
        assert error is None
        assert result is not None
        assert 'user' in result
        assert 'token' in result
    
    def test_login_with_invalid_password(self, auth_service, test_account):
        """Test login fails with wrong password"""
        success, error, result = auth_service.login(
            email='test@example.com',
            password='WrongPassword'
        )
        
        assert success is False
        assert error is not None
    
    def test_login_with_nonexistent_email(self, auth_service):
        """Test login fails with non-existent email"""
        success, error, result = auth_service.login(
            email='nonexistent@example.com',
            password='AnyPassword'
        )
        
        assert success is False
        assert error is not None


class TestPasswordHashing:
    """Test password hashing and verification"""
    
    def test_password_hashed_not_plain_text(self, auth_service):
        """Test that passwords are hashed, not stored as plain text"""
        password = 'SecretPassword123!'
        hashed = auth_service.hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 50  # bcrypt hashes are long
    
    def test_same_password_different_hashes(self, auth_service):
        """Test that same password produces different hashes (salt)"""
        password = 'SamePassword123!'
        hash1 = auth_service.hash_password(password)
        hash2 = auth_service.hash_password(password)
        
        assert hash1 != hash2  # Different salts
    
    def test_password_verification(self, auth_service):
        """Test password verification works correctly"""
        password = 'MyPassword123!'
        hashed = auth_service.hash_password(password)
        
        assert auth_service.verify_password(password, hashed) is True
        assert auth_service.verify_password('WrongPassword', hashed) is False


class TestTokenGeneration:
    """Test JWT token generation and verification"""
    
    def test_token_generation(self, auth_service, test_account, datastore):
        """Test that valid tokens are generated"""
        user = datastore.get_by_id('users', test_account['user_id'], test_account['account_id'])
        token = auth_service.generate_token(user)
        
        assert token is not None
        assert len(token) > 0
    
    def test_token_verification(self, auth_service, test_account):
        """Test that tokens can be verified"""
        payload = auth_service.verify_token(test_account['token'])
        
        assert payload is not None
        assert payload['user_id'] == test_account['user_id']
        assert payload['email'] == test_account['email']
        assert payload['account_id'] == test_account['account_id']
    
    def test_invalid_token_rejected(self, auth_service):
        """Test that invalid tokens are rejected"""
        payload = auth_service.verify_token('invalid.token.here')
        
        assert payload is None


class TestScreenLock:
    """Test screen lock functionality"""
    
    def test_lock_screen(self, auth_service, test_account, datastore):
        """Test locking user screen"""
        success = auth_service.lock_screen(
            test_account['user_id'],
            test_account['account_id']
        )
        
        assert success is True
        
        # Verify user is locked
        user = datastore.get_by_id('users', test_account['user_id'], test_account['account_id'])
        assert user['screen_locked'] is True
    
    def test_unlock_screen_with_correct_pin(self, auth_service, test_account, datastore):
        """Test unlocking with correct PIN"""
        # Set PIN for user
        datastore.update('users', test_account['user_id'], {'pin': '1234'}, test_account['account_id'])
        
        # Lock screen
        auth_service.lock_screen(test_account['user_id'], test_account['account_id'])
        
        # Unlock with correct PIN
        success, error = auth_service.unlock_screen(
            test_account['user_id'],
            '1234',
            test_account['account_id']
        )
        
        assert success is True
        assert error is None
    
    def test_unlock_screen_with_wrong_pin(self, auth_service, test_account, datastore):
        """Test unlocking fails with wrong PIN"""
        # Set PIN for user
        datastore.update('users', test_account['user_id'], {'pin': '1234'}, test_account['account_id'])
        
        # Lock screen
        auth_service.lock_screen(test_account['user_id'], test_account['account_id'])
        
        # Try to unlock with wrong PIN
        success, error = auth_service.unlock_screen(
            test_account['user_id'],
            '9999',
            test_account['account_id']
        )
        
        assert success is False
        assert error is not None


class TestRoleArchitecture:
    """Test role separation: MAIN_ADMIN vs BUSINESS_ADMIN vs CASHIER"""

    def test_signup_creates_business_admin_not_main_admin(self, auth_service):
        success, error, result = auth_service.signup(
            email='business@example.com',
            password='ValidPassword123!',
            name='Business Owner',
            plan='basic'
        )
        assert success is True
        assert result['user']['role'] == 'admin'
        assert result['user']['business_role'] == 'admin'

    def test_main_admin_bootstrap_creates_main_admin_role(self, auth_service, datastore):
        user = auth_service.ensure_main_admin(
            email='platform@example.com',
            password_hash=auth_service.hash_password('PlatformPass123!'),
            display_name='Platform Admin'
        )
        assert user['role'] == 'main_admin'
        assert user['business_role'] == 'main_admin'

    def test_cashier_default_role(self, auth_service, datastore, test_account):
        user = datastore.create('users', {
            'account_id': test_account['account_id'],
            'email': 'cashier@example.com',
            'password_hash': auth_service.hash_password('CashierPass123!'),
            'name': 'Cashier User',
            'role': 'cashier',
            'business_role': 'cashier',
            'is_active': True,
            'created_at': '2026-01-01T00:00:00'
        })
        assert user['role'] == 'cashier'

    def test_business_admin_cannot_access_main_admin_endpoints(self, auth_service, client, datastore):
        success, error, result = auth_service.signup(
            email='bizadmin@example.com',
            password='ValidPassword123!',
            name='Biz Admin',
            plan='basic'
        )
        assert success is True
        token = result['token']
        resp = client.get('/api/main-admin/users', headers={
            'Authorization': f'Bearer {token}'
        })
        assert resp.status_code == 403

    def test_cashier_cannot_access_admin_product_endpoints(self, auth_service, client, datastore, test_account):
        user = datastore.create('users', {
            'account_id': test_account['account_id'],
            'email': 'cashier2@example.com',
            'password_hash': auth_service.hash_password('CashierPass123!'),
            'name': 'Cashier Two',
            'role': 'cashier',
            'business_role': 'cashier',
            'is_active': True,
            'created_at': '2026-01-01T00:00:00'
        })
        token = auth_service.generate_token(user)
        resp = client.post('/api/products', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }, json={'name': 'Test', 'price': 10, 'quantity': 5})
        assert resp.status_code == 403

    def test_tenant_isolation_users_scoped_to_account(self, auth_service, client, datastore):
        success_a, _, result_a = auth_service.signup(
            email='tenant_a@example.com',
            password='ValidPassword123!',
            name='Tenant A Admin',
            plan='basic'
        )
        success_b, _, result_b = auth_service.signup(
            email='tenant_b@example.com',
            password='ValidPassword123!',
            name='Tenant B Admin',
            plan='basic'
        )
        assert success_a and success_b
        token_a = result_a['token']
        account_a = result_a['user']['account_id']
        account_b = result_b['user']['account_id']
        assert account_a != account_b

        resp_a = client.get('/api/users', headers={
            'Authorization': f'Bearer {token_a}'
        })
        assert resp_a.status_code == 200
        users_a = resp_a.get_json()
        emails_a = [u['email'] for u in users_a]
        assert 'tenant_a@example.com' in emails_a
        assert 'tenant_b@example.com' not in emails_a
