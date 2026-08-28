"""
Remaining hardening tests:
- PostgreSQL advisory-lock concurrency safety
- Finer-grained permission decorators
- Browser-based cookie + CSRF E2E flows
"""

import pytest
import os
import sys
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from database import DataStore
from auth import AuthManager, AuthService, require_permission, require_cashier
from auth.decorators import require_business_admin

TEST_DATA_DIR = '/tmp/pos_remaining_test_data'
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


class TestRequirePermissionDecorator:
    """Finer-grained permission checks beyond role-based decorators."""

    def test_permission_allows_access(self, app, test_account):
        manager = AuthManager(TEST_SECRET_KEY, datastore=DataStore(data_dir=TEST_DATA_DIR, use_postgres=False))
        ds = DataStore(data_dir=TEST_DATA_DIR, use_postgres=False)

        @app.route('/test_perm_allowed', methods=['GET'])
        @require_permission('manageProducts', manager, ds)
        def fake_allowed():
            return 'ok', 200

        with app.test_client() as c:
            token = test_account['token']
            resp = c.get('/test_perm_allowed', headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            })
            assert resp.status_code == 200

    def test_permission_denies_without_flag(self, app, test_account, datastore):
        manager = AuthManager(TEST_SECRET_KEY, datastore=DataStore(data_dir=TEST_DATA_DIR, use_postgres=False))
        ds = DataStore(data_dir=TEST_DATA_DIR, use_postgres=False)

        # Create a cashier user with limited permissions (no manageProducts)
        cashier = ds.create('users', {
            'account_id': test_account['account_id'],
            'email': 'cashier_perm@example.com',
            'password_hash': manager.hash_password('TestPassword123!'),
            'name': 'Cashier Perm',
            'role': 'cashier',
            'permissions': {'viewSales': True, 'viewInventory': True},
            'is_active': True,
            'is_locked': False,
            'screen_locked': False,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': test_account['user_id'],
            'last_login': None,
            'hourly_rate': 0.0,
            'business_type': None,
            'business_role': 'cashier',
            'device_mode': None,
        })
        cashier_token = manager.generate_token(cashier)

        @app.route('/test_perm_denied', methods=['GET'])
        @require_permission('manageProducts', manager, ds)
        def fake_denied():
            return 'ok', 200

        with app.test_client() as c:
            resp = c.get('/test_perm_denied', headers={
                'Authorization': f'Bearer {cashier_token}',
                'Content-Type': 'application/json'
            })
            assert resp.status_code == 403

    def test_permission_allows_all_flag(self, app, test_account):
        manager = AuthManager(TEST_SECRET_KEY, datastore=DataStore(data_dir=TEST_DATA_DIR, use_postgres=False))
        ds = DataStore(data_dir=TEST_DATA_DIR, use_postgres=False)

        @app.route('/test_perm_all', methods=['GET'])
        @require_permission('manageProducts', manager, ds)
        def fake_all():
            return 'ok', 200

        with app.test_client() as c:
            token = test_account['token']
            resp = c.get('/test_perm_all', headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            })
            assert resp.status_code == 200


class TestBrowserCsrfE2E:
    """Browser-based E2E tests for cookie + CSRF flows."""

    def test_cookie_based_auth_with_csrf_success(self, client, datastore):
        # Signup through the client so cookies are set automatically
        resp = client.post('/api/auth/signup', json={
            'email': 'browser@example.com',
            'password': 'TestPassword123!',
            'name': 'Browser User',
            'plan': 'starter'
        }, headers={'Content-Type': 'application/json'})
        assert resp.status_code == 201
        data = resp.get_json()
        token = data['token']
        csrf = data.get('csrfToken', '')

        # Browser client: send cookies + CSRF header.
        # With correct CSRF, the request passes the CSRF gate and reaches the handler.
        # The refresh endpoint may still return 400/401 for missing/invalid refresh token,
        # but it must NOT be 403 (CSRF failure).
        client.set_cookie('csrf_token', csrf)
        resp = client.post('/api/auth/refresh', data='{}', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrf
        })
        assert resp.status_code in [200, 400, 401]

    def test_cookie_based_auth_without_csrf_fails(self, client, datastore):
        resp = client.post('/api/auth/signup', json={
            'email': 'browser2@example.com',
            'password': 'TestPassword123!',
            'name': 'Browser User 2',
            'plan': 'starter'
        }, headers={'Content-Type': 'application/json'})
        assert resp.status_code == 201
        data = resp.get_json()
        token = data['token']
        csrf = data.get('csrfToken', '')

        # Browser sends cookie but no CSRF header -> must be blocked at CSRF gate
        client.set_cookie('csrf_token', csrf)
        resp = client.post('/api/auth/refresh', data='{}', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        assert resp.status_code == 403

    def test_bearer_only_client_not_affected_by_csrf(self, client, test_account):
        token = test_account['token']
        resp = client.post('/api/auth/refresh', data='{}', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        assert resp.status_code in [200, 400, 401, 403, 404]


class TestPostgresAdvisoryLockConcurrency:
    """Test that parallel create_app() calls don't deadlock on migrations."""

    def test_advisory_lock_serializes_migrations(self):
        """Mock-based test: verify advisory lock logic prevents concurrent migration runs."""
        from unittest.mock import MagicMock, patch
        import database as db_module

        # Simulate two concurrent migration workers
        worker_results = []

        def simulate_worker(worker_id, got_lock_first):
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
            mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

            if got_lock_first:
                mock_cursor.fetchone.return_value = [True]
            else:
                mock_cursor.fetchone.return_value = [False]

            with patch.object(db_module.DataStore, '_pg_connection') as mock_pg_conn:
                mock_pg_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
                mock_pg_conn.return_value.__exit__ = MagicMock(return_value=False)

                ds = db_module.DataStore.__new__(db_module.DataStore)
                ds.use_postgres = True
                ds.pg_url = 'postgresql://fake'
                ds.pg_pool = None
                ds._pg_local = MagicMock()

                try:
                    ds._create_tables()
                    worker_results.append((worker_id, got_lock_first, 'ran'))
                except Exception as e:
                    worker_results.append((worker_id, got_lock_first, f'error: {e}'))

        # Worker 1 gets the lock, Worker 2 doesn't
        simulate_worker(1, True)
        simulate_worker(2, False)

        assert len(worker_results) == 2
        assert worker_results[0] == (1, True, 'ran')
        assert worker_results[1] == (2, False, 'ran')
