"""
Payment / M-Pesa Tests
======================
Tests for IntaSend M-Pesa STK Push integration.
"""

import pytest
import os
import sys
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import DataStore
from auth import AuthManager, AuthService
from intasend_service import IntaSendService
from payment_service import PaymentService


@pytest.fixture(autouse=True)
def _clean_test_data():
    test_dir = '/tmp/pos_test_payments'
    if os.path.exists(test_dir):
        import shutil
        shutil.rmtree(test_dir)
    os.makedirs(test_dir, exist_ok=True)
    yield
    if os.path.exists(test_dir):
        import shutil
        shutil.rmtree(test_dir)


@pytest.fixture
def datastore():
    return DataStore(data_dir='/tmp/pos_test_payments', use_postgres=False)


@pytest.fixture
def auth_manager(datastore):
    return AuthManager('test-secret-key', datastore=datastore)


@pytest.fixture
def auth_service(auth_manager, datastore):
    return AuthService(auth_manager, datastore=datastore)


@pytest.fixture
def test_account(auth_service, datastore):
    success, error, result = auth_service.signup(
        email='paymenttest@example.com',
        password='ValidPassword123!',
        name='Payment Test Admin',
        plan='basic'
    )
    assert success is True
    return {
        'account_id': result['user']['account_id'],
        'user_id': result['user']['id'],
        'email': result['user']['email'],
        'token': result['token']
    }


@pytest.fixture
def mock_intasend():
    mock = MagicMock(spec=IntaSendService)
    def normalize(phone):
        cleaned = (phone or '').replace(' ', '').replace('-', '')
        if not cleaned:
            return ''
        if cleaned.startswith('+'):
            cleaned = cleaned[1:]
        if cleaned.startswith('254'):
            return cleaned
        if cleaned.startswith('0') and len(cleaned) == 10:
            return '254' + cleaned[1:]
        if len(cleaned) == 9:
            return '254' + cleaned
        return ''
    mock.normalize_phone.side_effect = normalize
    mock.initiate_stk_push.return_value = {
        'success': True,
        'status_code': 200,
        'data': {'reference': 'TEST-REF-123', 'invoice_number': 'INV-123'},
        'provider_reference': 'TEST-REF-123',
        'error': None,
    }
    return mock


@pytest.fixture
def payment_service(datastore, mock_intasend):
    return PaymentService(intasend=mock_intasend, datastore=datastore)


class TestIntaSendService:
    def test_normalize_phone_leading_zero(self):
        svc = IntaSendService()
        assert svc.normalize_phone('0712345678') == '254712345678'

    def test_normalize_phone_with_254(self):
        svc = IntaSendService()
        assert svc.normalize_phone('254712345678') == '254712345678'

    def test_normalize_phone_with_plus(self):
        svc = IntaSendService()
        assert svc.normalize_phone('+254712345678') == '254712345678'

    def test_normalize_phone_011(self):
        svc = IntaSendService()
        assert svc.normalize_phone('0112345678') == '254112345678'

    def test_normalize_phone_empty(self):
        svc = IntaSendService()
        assert svc.normalize_phone('') == ''


class TestPaymentService:
    def test_initiate_mpesa_creates_payment(self, payment_service, test_account):
        success, error, payment = payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='0712345678'
        )
        assert success is True
        assert error is None
        assert payment['status'] == 'pending'
        assert payment['amount'] == 1500.0
        assert payment['customer_phone'] == '254712345678'

    def test_initiate_mpesa_duplicate_protection(self, payment_service, test_account):
        payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='0712345678'
        )
        success, error, payment = payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='0712345678'
        )
        assert success is False
        assert 'already in progress' in (error or '').lower()

    def test_initiate_mpesa_invalid_phone(self, payment_service, test_account):
        success, error, payment = payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='123'
        )
        assert success is False
        assert 'Invalid M-Pesa phone number' in error

    def test_webhook_updates_payment_status(self, payment_service, test_account):
        success, error, payment = payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='0712345678'
        )
        assert success is True
        provider_ref = payment['provider_reference']

        success, error, result = payment_service.handle_webhook('intasend', provider_ref, {
            'state': 'completed',
            'reference': provider_ref,
            'amount': '1500'
        })
        assert success is True
        assert result['status'] == 'success'
        assert result.get('idempotent') is not True

        status = payment_service.get_payment_status(payment['payment_id'], test_account['account_id'])
        assert status['status'] == 'success'

    def test_webhook_idempotent_on_completed(self, payment_service, test_account):
        success, error, payment = payment_service.initiate_mpesa_payment(
            account_id=test_account['account_id'],
            sale_id=1,
            cashier_id=test_account['user_id'],
            amount=1500.0,
            phone_number='0712345678'
        )
        provider_ref = payment['provider_reference']

        payment_service.handle_webhook('intasend', provider_ref, {'state': 'completed', 'reference': provider_ref})
        success, error, result = payment_service.handle_webhook('intasend', provider_ref, {'state': 'completed', 'reference': provider_ref})
        assert success is True
        assert result.get('idempotent') is True
