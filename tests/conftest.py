"""
Pytest Configuration and Fixtures
===================================
Shared test fixtures for all test modules.
"""

import pytest
import os
import sys
import shutil
from datetime import datetime

# Set test environment variables BEFORE any imports
TEST_DATA_DIR = '/tmp/pos_test_data'
TEST_SECRET_KEY = 'test-secret-key'

os.environ['DATA_DIR'] = TEST_DATA_DIR
os.environ['SECRET_KEY'] = TEST_SECRET_KEY
os.environ['JWT_SECRET'] = TEST_SECRET_KEY
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
os.environ['CACHE_URL'] = ''

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Import app module (app will be created with test env vars)
import app as app_module
from database import DataStore
from auth import AuthManager, AuthService
from admin_controller import AdminController
from cashier_controller import CashierController
from stock_engine import StockEngine


def _clear_test_data():
    """Remove stale test data directory"""
    if os.path.exists(TEST_DATA_DIR):
        shutil.rmtree(TEST_DATA_DIR)


@pytest.fixture(autouse=True)
def _clean_test_data():
    """Auto-clean test data before and after each test"""
    _clear_test_data()
    os.makedirs(TEST_DATA_DIR, exist_ok=True)
    yield
    _clear_test_data()


@pytest.fixture
def app():
    """Create Flask app for testing"""
    flask_app = app_module.app
    flask_app.config['TESTING'] = True
    yield flask_app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def datastore():
    """Create test datastore with isolated storage"""
    ds = DataStore(data_dir=TEST_DATA_DIR, use_postgres=False)
    yield ds


@pytest.fixture
def auth_service(datastore):
    """Create auth service for testing"""
    manager = AuthManager(TEST_SECRET_KEY, datastore=datastore)
    service = AuthService(manager, datastore=datastore)
    return service


@pytest.fixture
def stock_engine(datastore):
    """Create stock engine for testing"""
    return StockEngine(datastore)


@pytest.fixture
def admin_controller(datastore, stock_engine):
    """Create admin controller for testing"""
    return AdminController(datastore, stock_engine)


@pytest.fixture
def cashier_controller(datastore, stock_engine):
    """Create cashier controller for testing"""
    return CashierController(datastore, stock_engine)


@pytest.fixture
def test_account(datastore, auth_service):
    """Create test account"""
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
def test_product(datastore, admin_controller, test_account):
    """Create test product"""
    success, error, product = admin_controller.create_product(
        account_id=test_account['account_id'],
        created_by=test_account['user_id'],
        name='Test Product',
        price=100.0,
        cost=50.0,
        quantity=100.0,
        category='test'
    )
    if success:
        return product
    raise RuntimeError(f"Failed to create test product: {error}")


@pytest.fixture
def auth_headers(test_account):
    """Get authorization headers for authenticated requests"""
    return {
        'Authorization': f"Bearer {test_account['token']}",
        'Content-Type': 'application/json'
    }
