"""
End-to-End Auth Flow Tests
============================
Covers the full signup -> login -> refresh -> logout lifecycle,
PIN login, screen lock/unlock, role separation, tenant isolation,
cookie handling, password hashing, and token payload verification.
"""

import json
import time
import pytest


def _signup_and_get_refresh(client, auth_service, email, password, name):
    """Helper: signup via service (bypasses rate limiter), return (token, user, refresh_token)."""
    success, _, result = auth_service.signup(email=email, password=password, name=name)
    assert success
    user = result['user']
    refresh_token = auth_service.manager.create_refresh_session(
        user=user,
        user_agent='test-agent',
        ip_address='127.0.0.1'
    )
    return result['token'], user, refresh_token


class TestSignupFlowE2E:
    """Full signup endpoint lifecycle"""

    def test_signup_returns_token_and_user_payload(self, client):
        response = client.post('/api/auth/signup',
            data=json.dumps({
                'email': 'e2esignup@example.com',
                'password': 'ValidPass123!',
                'name': 'E2E Signup User'
            }),
            content_type='application/json')
        assert response.status_code == 201
        data = response.get_json()
        assert 'token' in data
        assert 'user' in data
        assert 'refreshToken' in data
        assert 'csrfToken' in data
        user = data['user']
        assert user['email'] == 'e2esignup@example.com'
        assert user['name'] == 'E2E Signup User'
        assert 'password_hash' not in user
        assert 'pin' not in user
        assert 'cashier_pin' not in user

    def test_signup_sets_auth_cookies(self, client):
        response = client.post('/api/auth/signup',
            data=json.dumps({
                'email': 'cookieuser@example.com',
                'password': 'ValidPass123!',
                'name': 'Cookie User'
            }),
            content_type='application/json')
        assert response.status_code == 201
        data = response.get_json()
        assert 'refreshToken' in data
        assert 'csrfToken' in data
        cookies = response.headers.getlist('Set-Cookie')
        cookie_str = ' '.join(cookies)
        assert 'refresh_token' in cookie_str
        assert 'csrf_token' in cookie_str

    def test_signup_duplicate_email_rejected(self, client, test_account):
        response = client.post('/api/auth/signup',
            data=json.dumps({
                'email': 'test@example.com',
                'password': 'ValidPass123!',
                'name': 'Duplicate'
            }),
            content_type='application/json')
        assert response.status_code == 400
        data = response.get_json()
        assert 'already registered' in data['error'].lower()

    def test_signup_creates_account_and_user(self, client, datastore, auth_service):
        _signup_and_get_refresh(client, auth_service, 'accountcheck@example.com', 'ValidPass123!', 'Account Check')
        # Also hit the endpoint to verify account is persisted
        resp = client.post('/api/auth/login',
            data=json.dumps({'email': 'accountcheck@example.com', 'password': 'ValidPass123!'}),
            content_type='application/json')
        assert resp.status_code == 200
        user = resp.get_json()['user']
        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user is not None
        db_account = datastore.get_by_id('accounts', user['account_id'])
        assert db_account is not None
        assert db_account['owner_email'] == 'accountcheck@example.com'


class TestLoginFlowE2E:
    """Full login endpoint lifecycle"""

    def test_login_returns_fresh_token(self, client, auth_service):
        auth_service.signup(
            email='loginflow@example.com',
            password='ValidPass123!',
            name='Login Flow User'
        )
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'loginflow@example.com',
                'password': 'ValidPass123!'
            }),
            content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert 'token' in data
        assert 'user' in data
        assert 'refreshToken' in data
        assert 'csrfToken' in data

    def test_login_invalid_password_401(self, client, test_account):
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': test_account['email'],
                'password': 'WrongPassword!999'
            }),
            content_type='application/json')
        assert response.status_code == 401

    def test_login_nonexistent_user_401(self, client):
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'ghost@example.com',
                'password': 'AnyPassword123!'
            }),
            content_type='application/json')
        assert response.status_code == 401
        data = response.get_json()
        assert 'error' in data


class TestTokenRefreshE2E:
    """Token refresh via refresh session"""

    def test_refresh_returns_new_token(self, auth_service):
        _, _, refresh_token = _signup_and_get_refresh(
            None, auth_service, 'refreshuser@example.com', 'ValidPass123!', 'Refresh User')
        assert refresh_token is not None

        rotated = auth_service.manager.rotate_refresh_session(
            refresh_token=refresh_token,
            user_agent='test-agent',
            ip_address='127.0.0.1'
        )
        assert rotated is not None
        assert 'token' in rotated
        assert 'user' in rotated
        assert 'refreshToken' in rotated

    def test_refresh_with_invalid_token_returns_none(self, auth_service):
        result = auth_service.manager.rotate_refresh_session(
            refresh_token='invalid_refresh_token',
            user_agent='test-agent',
            ip_address='127.0.0.1'
        )
        assert result is None

    def test_revoked_token_cannot_be_refreshed(self, auth_service):
        _, _, refresh_token = _signup_and_get_refresh(
            None, auth_service, 'revokeuser@example.com', 'ValidPass123!', 'Revoke User')
        assert refresh_token is not None

        auth_service.manager.revoke_refresh_session(refresh_token)

        rotated = auth_service.manager.rotate_refresh_session(
            refresh_token=refresh_token,
            user_agent='test-agent',
            ip_address='127.0.0.1'
        )
        assert rotated is None

    def test_refresh_endpoint_with_valid_session(self, client, auth_service):
        _, _, refresh_token = _signup_and_get_refresh(
            client, auth_service, 'refreshapi@example.com', 'ValidPass123!', 'Refresh API User')

        client.set_cookie('csrf_token', 'test-csrf')
        response = client.post('/api/auth/refresh',
            data=json.dumps({'refreshToken': refresh_token}),
            content_type='application/json',
            headers={'X-CSRF-Token': 'test-csrf'})
        assert response.status_code == 200
        data = response.get_json()
        assert 'token' in data
        assert 'user' in data
        assert 'csrfToken' in data
        cookies = response.headers.getlist('Set-Cookie')
        cookie_str = ' '.join(cookies)
        assert 'refresh_token' in cookie_str

    def test_refresh_endpoint_with_invalid_token_401(self, client):
        client.set_cookie('csrf_token', 'test-csrf')
        response = client.post('/api/auth/refresh',
            data=json.dumps({'refreshToken': 'bogus_token'}),
            content_type='application/json',
            headers={'X-CSRF-Token': 'test-csrf'})
        assert response.status_code == 401


class TestLogoutE2E:
    """Logout and session revocation"""

    def test_logout_revolks_refresh_session(self, client, auth_service):
        _, _, refresh_token = _signup_and_get_refresh(
            client, auth_service, 'logoutuser@example.com', 'ValidPass123!', 'Logout User')

        client.set_cookie('csrf_token', 'test-csrf')
        response = client.post('/api/auth/logout',
            data=json.dumps({'refreshToken': refresh_token}),
            content_type='application/json',
            headers={'X-CSRF-Token': 'test-csrf'})
        assert response.status_code == 200
        assert response.get_json()['success'] is True

        can_rotate = auth_service.manager.rotate_refresh_session(
            refresh_token=refresh_token,
            user_agent='test-agent',
            ip_address='127.0.0.1'
        )
        assert can_rotate is None

        cookies = response.headers.getlist('Set-Cookie')
        cookie_str = ' '.join(cookies)
        assert 'refresh_token=' in cookie_str

    def test_logout_clears_cookies(self, client, auth_service):
        _, _, refresh_token = _signup_and_get_refresh(
            client, auth_service, 'logoutcookie@example.com', 'ValidPass123!', 'Logout Cookie User')

        client.set_cookie('csrf_token', 'test-csrf')
        response = client.post('/api/auth/logout',
            data=json.dumps({'refreshToken': refresh_token}),
            content_type='application/json',
            headers={'X-CSRF-Token': 'test-csrf'})
        cookies = response.headers.getlist('Set-Cookie')
        cookie_str = ' '.join(cookies)
        assert 'refresh_token=' in cookie_str


class TestScreenLockE2E:
    """Screen lock / unlock via API"""

    def test_lock_screen_sets_locked_flag(self, client, auth_service, datastore):
        success, _, result = auth_service.signup(
            email='lockuser@example.com',
            password='ValidPass123!',
            name='Lock User'
        )
        assert success
        token = result['token']
        user = result['user']

        response = client.post('/api/auth/lock-screen',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True
        assert 'token' in data

        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user['screen_locked'] is True

    def test_unlock_screen_without_credentials(self, client, auth_service, datastore):
        success, _, result = auth_service.signup(
            email='unlockuser@example.com',
            password='ValidPass123!',
            name='Unlock User'
        )
        assert success
        token = result['token']
        user = result['user']

        response = client.post('/api/auth/lock-screen',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user['screen_locked'] is True

        response = client.post('/api/auth/unlock-screen',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            data=json.dumps({}))
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user['screen_locked'] is False

    def test_unlock_screen_without_credentials(self, client, auth_service, datastore):
        success, _, result = auth_service.signup(
            email='unlockuser@example.com',
            password='ValidPass123!',
            name='Unlock User'
        )
        assert success
        token = result['token']
        user = result['user']

        response = client.post('/api/auth/lock-screen',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user['screen_locked'] is True

        response = client.post('/api/auth/unlock-screen',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            data=json.dumps({}))
        assert response.status_code == 200
        data = response.get_json()
        assert data['success'] is True

        db_user = datastore.get_by_id('users', user['id'], user['account_id'])
        assert db_user['screen_locked'] is False


class TestPasswordChangeE2E:
    """Password change workflow"""

    def test_change_password_with_correct_current(self, client, auth_service):
        success, _, result = auth_service.signup(
            email='pwdchg@example.com',
            password='OldPass123!',
            name='PWD Change User'
        )
        assert success
        token = result['token']

        response = client.post('/api/auth/change-password',
            data=json.dumps({
                'currentPassword': 'OldPass123!',
                'newPassword': 'NewPass456!'
            }),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            content_type='application/json')
        assert response.status_code == 200
        data = response.get_json()
        assert 'message' in data

        login_resp = client.post('/api/auth/login',
            data=json.dumps({'email': 'pwdchg@example.com', 'password': 'NewPass456!'}),
            content_type='application/json')
        assert login_resp.status_code == 200

    def test_change_password_wrong_current_401(self, client, auth_service):
        success, _, result = auth_service.signup(
            email='pwdchgbad@example.com',
            password='OldPass123!',
            name='PWD Change Bad User'
        )
        assert success
        token = result['token']

        response = client.post('/api/auth/change-password',
            data=json.dumps({
                'currentPassword': 'WrongCurrent!',
                'newPassword': 'NewPass456!'
            }),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            content_type='application/json')
        assert response.status_code == 401


class TestRoleSeparationE2E:
    """Ensure role-based access control works end-to-end"""

    def test_cashier_cannot_access_settings(self, client, auth_service, datastore):
        success, _, result = auth_service.signup(
            email='cashierrole@example.com',
            password='ValidPass123!',
            name='Cashier Role User'
        )
        assert success
        user = result['user']
        datastore.update('users', user['id'], {'role': 'cashier'}, user['account_id'])
        new_token = auth_service.generate_token(datastore.get_by_id('users', user['id'], user['account_id']))

        # GET settings is allowed for all authenticated users
        get_resp = client.get('/api/settings', headers={'Authorization': f'Bearer {new_token}'})
        assert get_resp.status_code == 200
        # PUT settings requires business admin
        put_resp = client.put('/api/settings',
            data=json.dumps({'currency': 'USD'}),
            headers={'Authorization': f'Bearer {new_token}', 'Content-Type': 'application/json'},
            content_type='application/json')
        assert put_resp.status_code == 403

    def test_main_admin_can_access_main_admin_endpoints(self, client, auth_service, datastore):
        owner_user = auth_service.ensure_main_admin(
            email='mainadmin_e2e@example.com',
            password_hash=auth_service.hash_password('MainPass123!'),
            display_name='Main Admin E2E'
        )
        token = auth_service.generate_token(owner_user)
        response = client.get('/api/main-admin/users', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200

    def test_business_admin_blocked_from_main_admin_endpoints(self, client, auth_service):
        success, _, result = auth_service.signup(
            email='bize2e@example.com',
            password='ValidPass123!',
            name='Biz E2E Admin'
        )
        assert success
        token = result['token']
        response = client.get('/api/main-admin/users', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 403


class TestTenantIsolationE2E:
    """Multi-user tenant isolation"""

    def test_user_from_tenant_a_cannot_see_tenant_b_products(self, client, auth_service, datastore, admin_controller):
        auth_service.signup(email='tenanta2@example.com', password='ValidPass123!', name='Tenant A2')
        auth_service.signup(email='tenantb2@example.com', password='ValidPass123!', name='Tenant B2')

        tenant_a = datastore.get_user_by_email('tenanta2@example.com')
        tenant_b = datastore.get_user_by_email('tenantb2@example.com')
        token_a = auth_service.generate_token(tenant_a)
        token_b = auth_service.generate_token(tenant_b)

        admin_controller.create_product(
            account_id=tenant_a['account_id'],
            created_by=tenant_a['id'],
            name='Tenant A Product',
            price=100.0, cost=50.0, quantity=10.0, category='test'
        )
        admin_controller.create_product(
            account_id=tenant_b['account_id'],
            created_by=tenant_b['id'],
            name='Tenant B Product',
            price=200.0, cost=100.0, quantity=5.0, category='test'
        )

        resp_a = client.get('/api/products', headers={'Authorization': f'Bearer {token_a}'})
        assert resp_a.status_code == 200
        products_a = resp_a.get_json()
        names_a = [p['name'] for p in products_a]
        assert 'Tenant A Product' in names_a
        assert 'Tenant B Product' not in names_a

        resp_b = client.get('/api/products', headers={'Authorization': f'Bearer {token_b}'})
        products_b = resp_b.get_json()
        names_b = [p['name'] for p in products_b]
        assert 'Tenant B Product' in names_b
        assert 'Tenant A Product' not in names_b


class TestPasswordHashSecurity:
    """Verify passwords are never stored as plaintext"""

    def test_password_hash_is_bcrypt_format(self, auth_service):
        hashed = auth_service.hash_password('TestPassword123!')
        assert hashed.startswith('$2a$') or hashed.startswith('$2b$') or hashed.startswith('$2y$')

    def test_verify_password_rejects_non_bcrypt(self, auth_service):
        assert auth_service.verify_password('password', 'plaintext') is False

    def test_verify_password_rejects_empty(self, auth_service):
        assert auth_service.verify_password('password', '') is False
        assert auth_service.verify_password('', '') is False


class TestTokenPayloadE2E:
    """Verify JWT token contains correct claims"""

    def test_token_contains_user_id_email_role_account(self, auth_service):
        success, _, result = auth_service.signup(
            email='tokenpayload@example.com',
            password='ValidPass123!',
            name='Token Payload User'
        )
        assert success
        token = result['token']
        payload = auth_service.verify_token(token)
        assert payload is not None
        assert payload['email'] == 'tokenpayload@example.com'
        assert 'user_id' in payload
        assert 'account_id' in payload
        assert 'role' in payload
        assert 'exp' in payload
        assert 'jti' in payload

    def test_token_expiration_is_set(self, auth_service):
        success, _, result = auth_service.signup(
            email='tokenexp@example.com',
            password='ValidPass123!',
            name='Token Exp User'
        )
        assert success
        payload = auth_service.verify_token(result['token'])
        now = time.time()
        assert payload['exp'] > now
        max_exp = 25 * 3600 + now
        assert payload['exp'] < max_exp


class TestAuthMeEndpoint:
    """Test the /api/auth/me endpoint"""

    def test_me_returns_user_info(self, client, test_account):
        token = test_account['token']
        response = client.get('/api/auth/me', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200
        data = response.get_json()
        assert data['email'] == test_account['email']
        assert 'password_hash' not in data
        assert 'pin' not in data

    def test_me_without_token_401(self, client):
        response = client.get('/api/auth/me')
        assert response.status_code == 401

    def test_me_with_invalid_token_401(self, client):
        response = client.get('/api/auth/me', headers={'Authorization': 'Bearer invalid.token.here'})
        assert response.status_code == 401
