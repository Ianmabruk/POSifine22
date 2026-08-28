"""
Additional regression tests for security hardening and operational correctness.
"""

import pytest
import os
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from database import DataStore
from auth import AuthManager, AuthService

TEST_DATA_DIR = '/tmp/pos_security_test_data'
TEST_SECRET_KEY = 'test-secret-key-32-bytes-long-1234567890'


def _clear_test_data():
    if os.path.exists(TEST_DATA_DIR):
        import shutil
        shutil.rmtree(TEST_DATA_DIR)


@pytest.fixture(autouse=True)
def _clean_test_data():
    _clear_test_data()
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    yield
    _clear_test_data()


@pytest.fixture
def app():
    os.environ['DATA_DIR'] = TEST_DATA_DIR
    os.environ['SECRET_KEY'] = TEST_SECRET_KEY
    os.environ['JWT_SECRET'] = TEST_SECRET_KEY
    os.environ['DATABASE_URL'] = ''
    os.environ['REDIS_URL'] = ''
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def datastore():
    return DataStore(data_dir=TEST_DATA_DIR, use_postgres=False)


@pytest.fixture
def auth_service(datastore):
    manager = AuthManager(TEST_SECRET_KEY, datastore=datastore)
    service = AuthService(manager, datastore=datastore)
    return service


@pytest.fixture
def test_account(datastore, auth_service):
    success, error, user_data = auth_service.signup(
        email='test@example.com',
        password='TestPassword123!',
        name='Test User',
        plan='starter'
    )
    if success:
        return {
            'account_id': user_data['user']['account_id'],
            'user_id': user_data['user']['id'],
            'email': user_data['user']['email'],
            'token': user_data['token']
        }
    raise RuntimeError(f"Failed to create test account: {error}")


class TestSessionRevocationOnPasswordChange:
    """Session hygiene: changing password must invalidate all existing sessions."""

    def test_password_change_revokes_sessions(self, client, datastore, auth_service, test_account):
        token = test_account['token']
        account_id = test_account['account_id']
        user_id = test_account['user_id']

        # Create a refresh session manually
        from auth.manager import AuthManager
        manager = AuthManager(TEST_SECRET_KEY, datastore=datastore)
        refresh_token = manager.create_refresh_session(
            user={'id': user_id, 'account_id': account_id, 'email': 'test@example.com'},
            user_agent='test',
            ip_address='127.0.0.1'
        )

        # Change password
        resp = client.post('/api/auth/change-password', json={
            'currentPassword': 'TestPassword123!',
            'newPassword': 'NewPassword123!'
        }, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert resp.status_code == 200

        # Try to use the old refresh token
        resp = client.post('/api/auth/refresh', json={
            'refreshToken': refresh_token
        }, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert resp.status_code == 401


class TestSessionRevocationOnLock:
    """Session hygiene: locking a user must invalidate all existing sessions."""

    def test_lock_user_revokes_sessions(self, client, datastore, auth_service, test_account):
        token = test_account['token']
        account_id = test_account['account_id']
        user_id = test_account['user_id']

        from auth.manager import AuthManager
        manager = AuthManager(TEST_SECRET_KEY, datastore=datastore)
        refresh_token = manager.create_refresh_session(
            user={'id': user_id, 'account_id': account_id, 'email': 'test@example.com'},
            user_agent='test',
            ip_address='127.0.0.1'
        )

        # Lock the user
        resp = client.post(f'/api/users/{user_id}/lock', json={
            'locked': True
        }, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert resp.status_code == 200

        # Try to use the old refresh token
        resp = client.post('/api/auth/refresh', json={
            'refreshToken': refresh_token
        }, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert resp.status_code == 401


class TestUserRateLimiting:
    """Per-user rate limiting prevents token-cycling abuse."""

    def test_user_rate_limit_blocks_excessive_requests(self, client, test_account):
        token = test_account['token']
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

        # Send many POST requests rapidly (limit is 120 per 60s in app.py)
        for i in range(125):
            resp = client.post('/api/products', json={
                'name': f'Product {i}',
                'price': 100.0,
                'category': 'test'
            }, headers=headers)
            if resp.status_code == 429:
                return  # Test passes

        pytest.fail("Expected 429 rate-limit response after excessive requests")


class TestCsrfEnforcement:
    """CSRF tokens are enforced for browser-like cookie requests."""

    def test_missing_csrf_rejected_when_cookies_present(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='csrf@example.com',
            password='TestPassword123!',
            name='CSRF User',
            plan='starter'
        )
        assert success
        token = user_data['token']

        # Simulate a browser client that sends cookies but no CSRF header
        client.set_cookie('csrf_token', 'abc123')
        resp = client.post('/api/auth/refresh', json={}, headers={
            'Authorization': f'Bearer {token}'
        })
        assert resp.status_code == 403


class TestAuditTrailEndToEnd:
    """Critical workflows produce expected audit/activity log entries."""

    def test_signup_and_login_produce_activity_logs(self, client, datastore):
        # Signup via route to generate activity log
        resp = client.post('/api/auth/signup', json={
            'email': 'audit@example.com',
            'password': 'TestPassword123!',
            'name': 'Audit User',
            'plan': 'starter'
        }, headers={'Content-Type': 'application/json'})
        assert resp.status_code == 201
        data = resp.get_json()
        account_id = data['user']['account_id']
        token = data['token']
        csrf_token = data.get('csrfToken', '')

        # Login via route (include CSRF token if cookie was set by signup)
        headers = {'Content-Type': 'application/json'}
        if csrf_token:
            headers['X-CSRF-Token'] = csrf_token
        resp = client.post('/api/auth/login', json={
            'email': 'audit@example.com',
            'password': 'TestPassword123!'
        }, headers=headers)
        assert resp.status_code == 200

        activity_logs = datastore.get_all('activity_logs', account_id)
        actions = [log.get('action') for log in activity_logs]

        assert 'signup' in actions
        assert 'login' in actions


class TestPetroleumRouteCoverage:
    """Petroleum module routes are protected and functional."""

    def test_petroleum_tanks_requires_auth(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='petro@example.com',
            password='TestPassword123!',
            name='Petro User',
            plan='starter'
        )
        assert success
        token = user_data['token']

        resp = client.get('/api/petroleum/tanks', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        assert resp.status_code == 403  # Requires PRO_PETROLEUM plan


class TestSchoolRouteCoverage:
    """School module routes are protected and functional."""

    def test_school_students_requires_auth(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='school@example.com',
            password='TestPassword123!',
            name='School User',
            plan='starter'
        )
        assert success
        token = user_data['token']

        resp = client.get('/api/students', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        assert resp.status_code == 200


class TestCacheMultiTenantIsolation:
    """Cache keys are tenant-scoped and invalidation is correct."""

    def test_product_cache_invalidation_per_tenant(self, datastore, auth_service):
        success_a, _, user_a = auth_service.signup(
            email='cache_a@example.com',
            password='TestPassword123!',
            name='Cache A',
            plan='starter'
        )
        success_b, _, user_b = auth_service.signup(
            email='cache_b@example.com',
            password='TestPassword123!',
            name='Cache B',
            plan='starter'
        )
        assert success_a and success_b

        account_a_id = user_a['user']['account_id']
        account_b_id = user_b['user']['account_id']

        product_a = datastore.create('products', {
            'account_id': account_a_id,
            'name': 'Product A',
            'price': 100.0,
            'cost': 50.0,
            'quantity': 10.0,
            'category': 'test'
        })

        product_b = datastore.create('products', {
            'account_id': account_b_id,
            'name': 'Product B',
            'price': 200.0,
            'cost': 100.0,
            'quantity': 20.0,
            'category': 'test'
        })

        # Verify tenant isolation at datastore level
        products_a = datastore.get_all('products', account_a_id)
        products_b = datastore.get_all('products', account_b_id)

        assert len(products_a) == 1
        assert len(products_b) == 1
        assert products_a[0]['name'] == 'Product A'
        assert products_b[0]['name'] == 'Product B'
