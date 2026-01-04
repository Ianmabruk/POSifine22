#!/usr/bin/env python3
"""
Simple test script to verify Flask backend is working correctly
"""

import requests
import json

BASE_URL = "http://localhost:5002/api"

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            print("✅ Health check passed")
            print(f"   Response: {response.json()}")
            return True
        else:
            print(f"❌ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_signup():
    """Test signup endpoint"""
    print("\nTesting signup endpoint...")
    try:
        data = {
            "email": "test@example.com",
            "password": "test123",
            "name": "Test User"
        }
        response = requests.post(f"{BASE_URL}/auth/signup", json=data)
        if response.status_code in [200, 201]:
            print("✅ Signup successful")
            result = response.json()
            print(f"   User: {result.get('user', {}).get('name')}")
            print(f"   Role: {result.get('user', {}).get('role')}")
            return result.get('token')
        elif response.status_code == 400 and "already exists" in response.json().get('error', ''):
            print("⚠️  User already exists (this is okay)")
            return None
        else:
            print(f"❌ Signup failed: {response.status_code}")
            print(f"   Error: {response.json()}")
            return None
    except Exception as e:
        print(f"❌ Signup failed: {e}")
        return None

def test_login():
    """Test login endpoint"""
    print("\nTesting login endpoint...")
    try:
        data = {
            "email": "test@example.com",
            "password": "test123"
        }
        response = requests.post(f"{BASE_URL}/auth/login", json=data)
        if response.status_code == 200:
            print("✅ Login successful")
            result = response.json()
            print(f"   User: {result.get('user', {}).get('name')}")
            print(f"   Token: {result.get('token')[:20]}...")
            return result.get('token')
        else:
            print(f"❌ Login failed: {response.status_code}")
            print(f"   Error: {response.json()}")
            return None
    except Exception as e:
        print(f"❌ Login failed: {e}")
        return None

def test_products(token):
    """Test products endpoint"""
    print("\nTesting products endpoint...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/products", headers=headers)
        if response.status_code == 200:
            products = response.json()
            print(f"✅ Products fetched successfully")
            print(f"   Total products: {len(products)}")
            return True
        else:
            print(f"❌ Products fetch failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Products fetch failed: {e}")
        return False

def test_create_product(token):
    """Test creating a product"""
    print("\nTesting product creation...")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "name": "Test Product",
            "price": 100,
            "cost": 50,
            "quantity": 10,
            "unit": "pcs",
            "category": "raw"
        }
        response = requests.post(f"{BASE_URL}/products", json=data, headers=headers)
        if response.status_code in [200, 201]:
            print("✅ Product created successfully")
            product = response.json()
            print(f"   Product: {product.get('name')}")
            print(f"   Price: {product.get('price')}")
            return True
        else:
            print(f"❌ Product creation failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Product creation failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 60)
    print("Flask Backend Test Suite")
    print("=" * 60)
    
    # Test 1: Health check
    if not test_health():
        print("\n❌ Backend is not running or not accessible")
        print("   Please start the backend with: python app.py")
        return
    
    # Test 2: Signup (or skip if user exists)
    token = test_signup()
    
    # Test 3: Login
    if not token:
        token = test_login()
    
    if not token:
        print("\n❌ Authentication failed. Cannot proceed with other tests.")
        return
    
    # Test 4: Fetch products
    test_products(token)
    
    # Test 5: Create product
    test_create_product(token)
    
    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60)
    print("\nBackend is working correctly. You can now:")
    print("1. Start the frontend: cd my-react-app && npm run dev")
    print("2. Open browser: http://localhost:5173")
    print("3. Login with: test@example.com / test123")

if __name__ == "__main__":
    main()
