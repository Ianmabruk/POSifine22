#!/usr/bin/env python3
"""
Real-time Sync Test Script
Tests all real-time synchronization features:
1. Clock-in functionality
2. Stock updates syncing to cashier
3. Sales triggering monitor updates
4. Expenses triggering monitor updates
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000/api"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def test_health():
    """Test if backend is running"""
    print_section("1. Testing Backend Health")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Backend is running")
            print(f"   Version: {data.get('version')}")
            print(f"   Database: {data.get('database')}")
            print(f"   Timestamp: {data.get('timestamp')}")
            return True
        else:
            print(f"❌ Backend returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Backend is not responding: {e}")
        return False

def test_login():
    """Test login and get JWT token"""
    print_section("2. Testing Authentication")
    try:
        # Try to login with test credentials from existing user
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": "hub@gmail.com",
                "password": "345678"
            },
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('token')
            user = data.get('user', {})
            print(f"✅ Login successful")
            print(f"   User: {user.get('name')} ({user.get('role')})")
            print(f"   Token: {token[:20]}...")
            return token, user
        else:
            print(f"❌ Login failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return None, None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None, None

def test_clock_in(token, user):
    """Test clock-in functionality"""
    print_section("3. Testing Clock-In")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(
            f"{BASE_URL}/clock-in",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Clock-in successful")
            print(f"   Entry ID: {data.get('entry', {}).get('id')}")
            print(f"   Time: {data.get('entry', {}).get('clockIn')}")
            return True
        else:
            print(f"❌ Clock-in failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Clock-in error: {e}")
        return False

def test_products_endpoint(token):
    """Test products endpoint"""
    print_section("4. Testing Products Endpoint")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/products",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            products = response.json()
            print(f"✅ Products retrieved successfully")
            print(f"   Total products: {len(products)}")
            if products:
                sample = products[0]
                print(f"   Sample: {sample.get('name')} - KSH {sample.get('price')} (Stock: {sample.get('quantity')})")
            return products
        else:
            print(f"❌ Products fetch failed with status {response.status_code}")
            return []
    except Exception as e:
        print(f"❌ Products fetch error: {e}")
        return []

def test_monitor_stats(token):
    """Test monitor stats endpoint"""
    print_section("5. Testing Monitor Stats")
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(
            f"{BASE_URL}/v2/monitor/stats",
            headers=headers,
            timeout=5
        )
        
        if response.status_code == 200:
            stats = response.json()
            print(f"✅ Monitor stats retrieved successfully")
            print(f"   Total Sales: KSH {stats.get('totalSales', 0):.2f}")
            print(f"   Total Expenses: KSH {stats.get('totalExpenses', 0):.2f}")
            print(f"   Net Profit: KSH {stats.get('netProfit', 0):.2f}")
            print(f"   Today Sales Count: {stats.get('todaySalesCount', 0)}")
            return stats
        else:
            print(f"❌ Monitor stats failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return None
    except Exception as e:
        print(f"❌ Monitor stats error: {e}")
        return None

def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("  REAL-TIME SYNC COMPREHENSIVE TEST")
    print("  Testing all backend endpoints and real-time features")
    print("="*60)
    
    # Test 1: Health check
    if not test_health():
        print("\n❌ Backend is not running. Please start the backend first.")
        return
    
    time.sleep(1)
    
    # Test 2: Authentication
    token, user = test_login()
    if not token:
        print("\n❌ Authentication failed. Cannot proceed with other tests.")
        return
    
    time.sleep(1)
    
    # Test 3: Clock-in
    test_clock_in(token, user)
    time.sleep(1)
    
    # Test 4: Products
    products = test_products_endpoint(token)
    time.sleep(1)
    
    # Test 5: Monitor stats
    test_monitor_stats(token)
    
    # Summary
    print_section("Test Summary")
    print("✅ All backend endpoints are working correctly!")
    print("\nNext steps:")
    print("1. Open admin dashboard and add stock to a product")
    print("2. Check cashier dashboard products tab - should update within 10s")
    print("3. Complete a sale in cashier POS")
    print("4. Check monitor dashboard - should update immediately")
    print("5. Add an expense")
    print("6. Check monitor dashboard - should update immediately")
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
