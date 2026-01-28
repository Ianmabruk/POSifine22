"""
API Endpoint Tests
==================
Test REST API endpoints end-to-end.
"""

import pytest
import json


class TestAuthEndpoints:
    """Test authentication endpoints"""
    
    def test_signup_endpoint(self, client):
        """Test POST /api/auth/signup"""
        response = client.post('/api/auth/signup',
            data=json.dumps({
                'email': 'apitest@example.com',
                'password': 'TestPass123!',
                'name': 'API Test User',
                'plan': 'free'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'token' in data
        assert 'user' in data
        assert data['user']['email'] == 'apitest@example.com'
    
    def test_login_endpoint(self, client, test_account):
        """Test POST /api/auth/login"""
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'test@example.com',
                'password': 'TestPassword123!'
            }),
            content_type='application/json'
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'token' in data
        assert 'user' in data
    
    def test_login_with_invalid_credentials(self, client):
        """Test login fails with wrong credentials"""
        response = client.post('/api/auth/login',
            data=json.dumps({
                'email': 'wrong@example.com',
                'password': 'WrongPassword'
            }),
            content_type='application/json'
        )
        
        assert response.status_code in [401, 400]


class TestProductEndpoints:
    """Test product management endpoints"""
    
    def test_get_products(self, client, auth_headers, test_product):
        """Test GET /api/products"""
        response = client.get('/api/products', headers=auth_headers)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
        assert len(data) > 0
    
    def test_create_product(self, client, auth_headers):
        """Test POST /api/products"""
        response = client.post('/api/products',
            data=json.dumps({
                'name': 'API Test Product',
                'price': 99.99,
                'cost': 49.99,
                'quantity': 100,
                'category': 'test'
            }),
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert data['name'] == 'API Test Product'
        assert data['price'] == 99.99
    
    def test_update_product(self, client, auth_headers, test_product):
        """Test PUT /api/products/<id>"""
        response = client.put(f"/api/products/{test_product['id']}",
            data=json.dumps({
                'price': 125.0
            }),
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['price'] == 125.0


class TestSalesEndpoints:
    """Test sales endpoints"""
    
    def test_complete_sale_endpoint(self, client, auth_headers, test_product):
        """Test POST /api/sales (complete sale)"""
        response = client.post('/api/sales',
            data=json.dumps({
                'items': [{
                    'product_id': test_product['id'],
                    'name': test_product['name'],
                    'quantity': 2,
                    'price': test_product['price']
                }],
                'payment_method': 'cash',
                'amount_paid': 200.0
            }),
            headers=auth_headers
        )
        
        assert response.status_code == 201
        data = json.loads(response.data)
        assert 'sale' in data
        assert data['sale']['total'] == 200.0
    
    def test_get_sales(self, client, auth_headers):
        """Test GET /api/sales"""
        response = client.get('/api/sales', headers=auth_headers)
        
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)


class TestHealthEndpoint:
    """Test health check endpoint"""
    
    def test_health_check(self, client):
        """Test GET /health"""
        response = client.get('/health')
        
        assert response.status_code in [200, 503]  # 503 if services unhealthy
        data = json.loads(response.data)
        assert 'status' in data
        assert 'services' in data
        assert 'timestamp' in data
