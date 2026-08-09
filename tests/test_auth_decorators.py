"""
Auth Decorator Tests
=====================
Test require_auth, require_admin, require_main_admin, require_business_admin.
"""

import pytest
import json
import time
from datetime import datetime, timedelta


class TestRequireAuth:
    """Test require_auth decorator"""

    def test_missing_token_returns_401(self, client):
        response = client.get('/api/products')
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client):
        response = client.get('/api/products',
            headers={'Authorization': 'Bearer invalid-token'})
        assert response.status_code == 401

    def test_expired_token_returns_401(self, client, auth_service):
        expired_payload = {
            'user_id': 1,
            'email': 'test@example.com',
            'account_id': 'acc_test',
            'role': 'admin',
            'exp': int(time.time()) - 100
        }
        import jwt as pyjwt
        expired_token = pyjwt.encode(expired_payload, 'test-secret-key', algorithm='HS256')
        response = client.get('/api/products',
            headers={'Authorization': f'Bearer {expired_token}'})
        assert response.status_code == 401

    def test_wrong_secret_token_returns_401(self, client, auth_service):
        wrong_payload = {
            'user_id': 1,
            'email': 'test@example.com',
            'account_id': 'acc_test',
            'role': 'admin',
            'exp': int(time.time()) + 3600
        }
        import jwt as pyjwt
        wrong_token = pyjwt.encode(wrong_payload, 'wrong-secret-key', algorithm='HS256')
        response = client.get('/api/products',
            headers={'Authorization': f'Bearer {wrong_token}'})
        assert response.status_code == 401


class TestRequireAdmin:
    """Test require_admin decorator"""

    def test_admin_can_access_admin_endpoints(self, client, auth_headers):
        response = client.get('/api/users', headers=auth_headers)
        assert response.status_code == 200

    def test_cashier_cannot_access_admin_endpoints(self, client, auth_service, datastore):
        cashier_account = auth_service.signup(
            email='cashier_decorator@example.com',
            password='CashierPass123!',
            name='Cashier Decorator'
        )
        assert cashier_account[0] is True
        cashier_id = cashier_account[2]['user']['id']
        cashier_user = cashier_account[2]['user']

        datastore.update('users', cashier_id, {'role': 'cashier'}, cashier_user['account_id'])

        updated_user = datastore.get_by_id('users', cashier_id, cashier_user['account_id'])
        new_token = auth_service.manager.generate_token(updated_user)

        response = client.post('/api/users',
            data=json.dumps({
                'name': 'New User',
                'email': 'newuser@example.com',
                'password': 'NewPass123!',
                'role': 'cashier'
            }),
            headers={'Authorization': f'Bearer {new_token}', 'Content-Type': 'application/json'})
        assert response.status_code == 403


class TestRequireMainAdmin:
    """Test require_main_admin decorator"""

    def test_main_admin_can_access_main_admin_endpoints(self, client, auth_service, datastore):
        main_admin = auth_service.ensure_main_admin(
            email='mainadmin_decorator@example.com',
            password_hash=auth_service.hash_password('MainPass123!'),
            display_name='Main Admin Decorator'
        )
        token = auth_service.generate_token(main_admin)
        response = client.get('/api/main-admin/users',
            headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200

    def test_business_admin_cannot_access_main_admin_endpoints(self, client, test_account):
        response = client.get('/api/main-admin/users',
            headers={'Authorization': f'Bearer {test_account["token"]}'})
        assert response.status_code == 403


class TestRequireBusinessAdmin:
    """Test require_business_admin decorator"""

    def test_business_admin_can_access_business_endpoints(self, client, auth_headers):
        response = client.post('/api/products',
            data=json.dumps({
                'name': 'Decorator Product',
                'price': 100.0,
                'cost': 50.0,
                'quantity': 100.0
            }),
            headers=auth_headers)
        assert response.status_code == 201

    def test_main_admin_can_access_business_endpoints(self, client, auth_service, datastore):
        main_admin = auth_service.ensure_main_admin(
            email='mainadmin_biz_decorator@example.com',
            password_hash=auth_service.hash_password('MainPass123!'),
            display_name='Main Admin Biz Decorator'
        )
        token = auth_service.generate_token(main_admin)
        response = client.post('/api/products',
            data=json.dumps({
                'name': 'Main Admin Product',
                'price': 100.0,
                'cost': 50.0,
                'quantity': 100.0
            }),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
        assert response.status_code == 201
