"""
Subscription and Trial Tests
=============================
Test trial duration, plan validation, and subscription endpoints.
"""

import pytest
import json
from datetime import datetime


class TestTrialDuration:
    """Test that all trials are 30 days"""

    def test_signup_creates_30_day_trial(self, auth_service, datastore):
        """Test that signup creates a 30-day trial"""
        success, error, result = auth_service.signup(
            email='trial30@example.com',
            password='ValidPassword123!',
            name='Trial User',
            plan='starter'
        )
        assert success is True
        account_id = result['user']['account_id']
        account = datastore.get_by_id('accounts', account_id)
        assert account['plan'] == 'starter'
        trial_end = account.get('trial_ends_at')
        assert trial_end is not None
        end_date = datetime.fromisoformat(trial_end)
        start_date = datetime.fromisoformat(account['created_at'])
        delta = (end_date - start_date).days
        assert delta == 30

    def test_trial_plans_api_returns_30_days(self, client):
        """Test GET /api/subscription/plans returns correct trial days"""
        response = client.get('/api/subscription/plans')
        assert response.status_code == 200
        data = response.get_json()
        plans = data.get('plans', [])
        for plan in plans:
            if plan['id'] == 'custom':
                assert plan['trial_days'] == 0
            else:
                assert plan['trial_days'] == 30

    def test_create_trial_validates_plan(self, client):
        """Test POST /api/trials/create validates plan"""
        response = client.post('/api/trials/create',
            data=json.dumps({'plan': 'invalid_plan'}),
            content_type='application/json'
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_create_trial_returns_30_days(self, client):
        """Test POST /api/trials/create returns 30-day trial"""
        response = client.post('/api/trials/create',
            data=json.dumps({'packageType': 'starter'}),
            content_type='application/json'
        )
        assert response.status_code == 201
        data = response.get_json()
        assert data['trial']['trial_days'] == 30


class TestSubscriptionRenewal:
    """Test subscription renewal with plan validation"""

    def test_subscription_renew_validates_plan(self, client, test_account):
        """Test that subscription renewal validates plan_id"""
        token = test_account['token']
        response = client.post('/api/subscription/renew',
            data=json.dumps({'plan_id': 'invalid_plan'}),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data


class TestRoleEscalationPrevention:
    """Test that users cannot escalate their roles"""

    def test_create_user_cannot_set_main_admin_role(self, auth_service, client, datastore, test_account):
        """Test that creating a user cannot assign main_admin role"""
        token = test_account['token']
        response = client.post('/api/users',
            data=json.dumps({'name': 'Evil User', 'email': 'evil@example.com', 'password': 'Pass123!', 'role': 'main_admin'}),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        user = response.get_json()
        assert user['role'] == 'cashier'

    def test_update_user_cannot_escalate_role(self, auth_service, client, datastore, test_account):
        """Test that updating a user cannot escalate role"""
        user = datastore.create('users', {
            'account_id': test_account['account_id'],
            'email': 'lowuser@example.com',
            'password_hash': auth_service.hash_password('Pass123!'),
            'name': 'Low User',
            'role': 'cashier',
            'is_active': True,
            'created_at': datetime.utcnow().isoformat()
        })
        token = test_account['token']
        response = client.put(f"/api/users/{user['id']}",
            data=json.dumps({'role': 'main_admin', 'name': 'Updated Name'}),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
        updated = response.get_json()
        assert updated['role'] == 'cashier'
        assert updated['name'] == 'Updated Name'


class TestMainAdminIsolation:
    """Test main admin cannot access business endpoints"""

    def test_main_admin_cannot_create_products(self, auth_service, client, datastore):
        """Test main_admin cannot create products via business endpoint"""
        main_admin = auth_service.ensure_main_admin(
            email='mainadmin2@example.com',
            password_hash=auth_service.hash_password('MainPass123!'),
            display_name='Main Admin 2'
        )
        token = auth_service.generate_token(main_admin)
        response = client.post('/api/products',
            data=json.dumps({'name': 'Main Admin Product', 'price': 10, 'quantity': 5}),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        assert response.status_code == 403

    def test_main_admin_cannot_renew_subscription(self, auth_service, client, datastore):
        """Test main_admin can access business subscription renew (super admin access)"""
        main_admin = auth_service.ensure_main_admin(
            email='mainadmin3@example.com',
            password_hash=auth_service.hash_password('MainPass123!'),
            display_name='Main Admin 3'
        )
        token = auth_service.generate_token(main_admin)
        response = client.post('/api/subscription/renew',
            data=json.dumps({'plan_id': 'business'}),
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
