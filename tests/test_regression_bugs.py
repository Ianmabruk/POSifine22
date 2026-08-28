"""
Regression tests for discovered bugs in POSIFINE platform.
These tests are expected to FAIL before the fixes are applied.
"""

import pytest
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import create_app
from database import DataStore
from auth import AuthManager, AuthService
from stock_engine import StockEngine


TEST_DATA_DIR = '/tmp/pos_regression_test_data'
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


@pytest.fixture
def auth_headers(test_account):
    return {
        'Authorization': f"Bearer {test_account['token']}",
        'Content-Type': 'application/json'
    }


class TestSubscriptionEnforcement:
    """BUG: Paid subscription expiry is NOT enforced in require_auth decorator.
    
    The decorator only checks trial expiry for plan=='trial', but never checks
    subscription_ends_at for paid plans. Users with expired paid subscriptions
    can still access all business endpoints.
    """

    def test_expired_subscription_blocks_access(self, client, datastore, auth_service):
        account_email = 'subscribed@example.com'
        success, error, user_data = auth_service.signup(
            email=account_email,
            password='TestPassword123!',
            name='Subscribed User',
            plan='business'
        )
        assert success, f"Signup failed: {error}"
        account_id = user_data['user']['account_id']
        token = user_data['token']

        # Expire the subscription
        past_date = (datetime.utcnow() - timedelta(days=1)).isoformat()
        datastore.update('accounts', account_id, {
            'subscription_ends_at': past_date
        })

        # Try to access a protected endpoint
        resp = client.get('/api/products', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        # Should be blocked with 403, but currently returns 200
        assert resp.status_code == 403, f"Expected 403 for expired subscription, got {resp.status_code}"


class TestMainAdminLockStatus:
    """BUG: _require_main_admin does not check if account/user is locked.
    
    A locked main admin can still access all main-admin endpoints and perform
    destructive actions.
    """

    def test_locked_main_admin_blocked(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='mainadmin@example.com',
            password='TestPassword123!',
            name='Main Admin',
            plan='starter'
        )
        assert success
        account_id = user_data['user']['account_id']
        user_id = user_data['user']['id']

        # Promote to main_admin
        datastore.update('users', user_id, {
            'role': 'main_admin'
        }, account_id)

        # Login as main admin while unlocked
        resp = client.post('/api/main-admin/auth/login', json={
            'email': 'mainadmin@example.com',
            'password': 'TestPassword123!'
        })
        assert resp.status_code == 200
        token = resp.get_json()['token']

        # Now lock the main admin
        datastore.update('users', user_id, {
            'is_locked': True
        }, account_id)

        # Try to access main-admin endpoint with existing token
        resp = client.get('/api/main-admin/users', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        # Should be blocked with 403, but currently returns 200
        assert resp.status_code == 403, f"Expected 403 for locked main admin, got {resp.status_code}"


class TestRecipeDeleteTenantIsolation:
    """BUG: delete_recipe checks stock_deductions without account_id.
    
    This causes cross-tenant false positives: Account B cannot delete a recipe
    if Account A has stock deductions for the same product_id.
    """

    def test_delete_recipe_not_blocked_by_other_account_deductions(self, client, datastore, auth_service):
        # Create account A
        success_a, _, user_a = auth_service.signup(
            email='account_a@example.com',
            password='TestPassword123!',
            name='Account A',
            plan='starter'
        )
        assert success_a
        account_a_id = user_a['user']['account_id']
        token_a = user_a['token']

        # Create product in account A
        product_a = datastore.create('products', {
            'account_id': account_a_id,
            'name': 'Product A',
            'price': 100.0,
            'cost': 50.0,
            'quantity': 10.0,
            'category': 'test'
        })

        # Create stock deduction for product A in account A
        datastore.create('stock_deductions', {
            'account_id': account_a_id,
            'product_id': product_a['id'],
            'product_name': 'Product A',
            'quantity_before': 10.0,
            'quantity_deducted': 1.0,
            'quantity_after': 9.0,
            'unit': 'pcs',
            'payment_method': 'cash',
            'cashier_id': 1,
            'cashier_name': 'test',
            'deduction_reason': 'test',
            'created_at': datetime.utcnow().isoformat()
        })

        # Create recipe for product A in account A
        recipe_a = datastore.create('recipes', {
            'account_id': account_a_id,
            'product_id': product_a['id'],
            'name': 'Recipe A',
            'active': True,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        })

        # Create account B
        success_b, _, user_b = auth_service.signup(
            email='account_b@example.com',
            password='TestPassword123!',
            name='Account B',
            plan='starter'
        )
        assert success_b
        account_b_id = user_b['user']['account_id']
        token_b = user_b['token']

        # Create same product ID in account B (unlikely but possible with different DB backends)
        # For JSON backend, IDs are auto-incremented per table, so we'll use a different approach
        # The bug is that get_by_field without account_id returns ALL stock_deductions
        # So we just verify that account B can delete its own recipe even though account A
        # has deductions for a DIFFERENT product with the SAME ID (simulated)
        product_b = datastore.create('products', {
            'account_id': account_b_id,
            'name': 'Product B',
            'price': 100.0,
            'cost': 50.0,
            'quantity': 10.0,
            'category': 'test'
        })

        # Create recipe for product B in account B (no deductions for this product in account B)
        recipe_b = datastore.create('recipes', {
            'account_id': account_b_id,
            'product_id': product_b['id'],
            'name': 'Recipe B',
            'active': True,
            'created_at': datetime.utcnow().isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        })

        # Account B should be able to delete recipe B
        resp = client.delete(
            f'/api/recipes/{recipe_b["id"]}',
            headers={
                'Authorization': f'Bearer {token_b}',
                'Content-Type': 'application/json'
            }
        )
        # Currently fails because get_by_field finds account A's deductions for product_id
        # (In JSON backend, product IDs are per-table, so this test may pass in JSON mode
        # but fail in PostgreSQL mode where IDs are SERIAL and could collide)
        # We still write the test to document the expected behavior.
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.get_json()}"


class TestSaleChangeCalculation:
    """BUG: Sale change calculation hides underpayment.
    
    When amount_paid < total, change is set to 0.0 instead of the negative
    difference. This hides the fact that the customer underpaid.
    """

    def test_change_reflects_underpayment(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='cashier@example.com',
            password='TestPassword123!',
            name='Cashier',
            plan='starter'
        )
        assert success
        account_id = user_data['user']['account_id']
        token = user_data['token']

        product = datastore.create('products', {
            'account_id': account_id,
            'name': 'Test Product',
            'price': 100.0,
            'cost': 50.0,
            'quantity': 10.0,
            'category': 'test'
        })

        resp = client.post('/api/sales', json={
            'items': [{'product_id': product['id'], 'quantity': 1}],
            'total': 100.0,
            'payment_method': 'cash',
            'amount_paid': 80.0  # Underpaid by 20
        }, headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })

        assert resp.status_code == 201
        sale = resp.get_json()['sale']
        # change should be -20.0 (customer still owes), not 0.0
        assert sale['change'] == -20.0, f"Expected change=-20.0, got {sale['change']}"


class TestUpdateUserRole:
    """BUG: update_user silently drops role changes to non-cashier roles.
    
    When trying to update a user's role to 'admin', the role field is silently
    removed from the update instead of being rejected or applied.
    """

    def test_update_user_role_to_admin(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='admin@example.com',
            password='TestPassword123!',
            name='Admin',
            plan='starter'
        )
        assert success
        account_id = user_data['user']['account_id']
        admin_token = user_data['token']

        # Create a cashier in the SAME account
        cashier_payload = {
            'account_id': account_id,
            'email': 'cashier@example.com',
            'password_hash': auth_service.hash_password('TestPassword123!'),
            'name': 'Cashier',
            'role': 'cashier',
            'is_active': True,
            'is_locked': False,
            'screen_locked': False,
            'created_at': datetime.utcnow().isoformat(),
            'created_by': user_data['user']['id'],
            'last_login': None,
            'hourly_rate': 0.0,
            'business_type': None,
            'business_role': 'cashier'
        }
        cashier = datastore.create('users', cashier_payload)
        cashier_id = cashier['id']

        # Try to update cashier role to admin (with another field to avoid empty update)
        resp = client.put(
            f'/api/users/{cashier_id}',
            json={'role': 'admin', 'name': 'Cashier Updated'},
            headers={
                'Authorization': f'Bearer {admin_token}',
                'Content-Type': 'application/json'
            }
        )

        assert resp.status_code == 200
        updated = resp.get_json()
        # Role should be updated to 'admin', not silently dropped
        assert updated.get('role') == 'admin', f"Expected role='admin', got role={updated.get('role')}"


class TestCreateUserRole:
    """BUG: create_user only allows creating 'cashier' roles.
    
    There is no way to create additional admins through the standard API.
    """

    def test_create_user_with_admin_role(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='admin@example.com',
            password='TestPassword123!',
            name='Admin',
            plan='business'
        )
        assert success
        admin_token = user_data['token']
        account_id = user_data['user']['account_id']

        # Try to create a user with admin role in the SAME account
        resp = client.post('/api/users', json={
            'name': 'New Admin',
            'email': f'newadmin_{account_id}@example.com',
            'password': 'TestPassword123!',
            'role': 'admin'
        }, headers={
            'Authorization': f'Bearer {admin_token}',
            'Content-Type': 'application/json'
        })

        assert resp.status_code == 201
        created = resp.get_json()
        # Role should be 'admin', not forced to 'cashier'
        assert created.get('role') == 'admin', f"Expected role='admin', got role={created.get('role')}"


class TestMainAdminInactiveAccount:
    """BUG: _require_main_admin doesn't check if account is inactive.
    
    A main admin from an inactive account can still access main-admin endpoints.
    """

    def test_inactive_account_main_admin_blocked(self, client, datastore, auth_service):
        success, _, user_data = auth_service.signup(
            email='mainadmin@example.com',
            password='TestPassword123!',
            name='Main Admin',
            plan='starter'
        )
        assert success
        account_id = user_data['user']['account_id']
        user_id = user_data['user']['id']

        # Set account to inactive
        datastore.update('accounts', account_id, {'is_active': False})

        # Promote to main_admin
        datastore.update('users', user_id, {'role': 'main_admin'}, account_id)

        # Login
        resp = client.post('/api/main-admin/auth/login', json={
            'email': 'mainadmin@example.com',
            'password': 'TestPassword123!'
        })
        assert resp.status_code == 200
        token = resp.get_json()['token']

        # Try to access main-admin endpoint
        resp = client.get('/api/main-admin/users', headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        })
        # Should be blocked with 403, but currently returns 200
        assert resp.status_code == 403, f"Expected 403 for inactive account, got {resp.status_code}"
