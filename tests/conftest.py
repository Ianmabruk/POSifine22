"""
Pytest Configuration and Fixtures
==================================
Shared test fixtures for all test modules.
"""

import pytest
import os
import sys
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app import app as flask_app
from database import DataStore
from auth_controller import AuthController
from admin_controller import AdminController
from cashier_controller import CashierController
from stock_engine import StockEngine


@pytest.fixture
def app():
    """Create Flask app for testing"""
    flask_app.config['TESTING'] = True
    flask_app.config['SECRET_KEY'] = 'test-secret-key'
    yield flask_app


@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()


@pytest.fixture
def datastore():
    """Create test datastore with in-memory storage"""
    ds = DataStore(data_dir='/tmp/pos_test_data', use_postgres=False)
    yield ds
    # Cleanup test data
    import shutil
    if os.path.exists('/tmp/pos_test_data'):
        shutil.rmtree('/tmp/pos_test_data')


@pytest.fixture
def auth_controller(datastore):
    """Create auth controller for testing"""
    return AuthController(datastore, 'test-secret-key')


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
def test_account(datastore, auth_controller):
    """Create test account"""
    success, error, user_data = auth_controller.signup(
        email='test@example.com',
        password='TestPassword123!',
        name='Test User',
        plan='basic'
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
