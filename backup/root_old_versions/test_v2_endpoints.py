#!/usr/bin/env python3
"""
Backend V2 Endpoints Test Script
Tests the new /api/v2 endpoints for completeness
"""

import requests
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "test123"

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

def test_login():
    """Test login and get token"""
    print_section("TEST 1: Login")
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get('token')
        print(f"✅ Login successful")
        print(f"   Token: {token[:20]}...")
        return token
    else:
        print(f"❌ Login failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

def test_monitor_stats(token):
    """Test /api/v2/monitor/stats endpoint"""
    print_section("TEST 2: Monitor Stats")
    
    headers = {"Authorization": f"Bearer {token}"}
    start_time = time.time()
    
    response = requests.get(
        f"{BASE_URL}/api/v2/monitor/stats",
        headers=headers
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Monitor stats retrieved ({elapsed_ms:.1f}ms)")
        print(f"   Total Sales: {data.get('totalSales')}")
        print(f"   Total Expenses: {data.get('totalExpenses')}")
        print(f"   Net Profit: {data.get('netProfit')}")
        print(f"   Transactions: {data.get('transactionCount')}")
        return True
    else:
        print(f"❌ Monitor stats failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def test_clock_in(token):
    """Test /api/v2/shifts/clock-in endpoint"""
    print_section("TEST 3: Clock In")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.post(
        f"{BASE_URL}/api/v2/shifts/clock-in",
        headers=headers
    )
    
    if response.status_code == 200:
        data = response.json()
        shift_id = data.get('shiftId')
        print(f"✅ Clock in successful")
        print(f"   Shift ID: {shift_id}")
        print(f"   Clock In Time: {data.get('clockInTime')}")
        return shift_id
    else:
        print(f"❌ Clock in failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return None

def test_complete_sale(token, shift_id):
    """Test /api/v2/sales/complete endpoint"""
    print_section("TEST 4: Complete Sale")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    sale_data = {
        "items": [
            {
                "productId": 1,
                "name": "Test Product",
                "quantity": 1,
                "price": 1000
            }
        ],
        "total": 1000,
        "discount": 0,
        "tax": 0,
        "paymentMethod": "cash",
        "shiftId": shift_id
    }
    
    start_time = time.time()
    
    response = requests.post(
        f"{BASE_URL}/api/v2/sales/complete",
        headers=headers,
        json=sale_data
    )
    
    elapsed_ms = (time.time() - start_time) * 1000
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Sale completed ({elapsed_ms:.1f}ms)")
        print(f"   Sale ID: {data.get('saleId')}")
        print(f"   Total: {data.get('total')}")
        print(f"   Processing Time: {data.get('processingTime')}")
        print(f"   Status: {data.get('status')}")
        
        if elapsed_ms < 300:
            print(f"   🎉 PERFORMANCE: Under 300ms target!")
        else:
            print(f"   ⚠️  WARNING: Exceeded 300ms target")
        
        return True
    else:
        print(f"❌ Sale failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def test_clock_out(token, shift_id):
    """Test /api/v2/shifts/clock-out endpoint"""
    print_section("TEST 5: Clock Out")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/v2/shifts/clock-out",
        headers=headers,
        json={"shiftId": shift_id}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Clock out successful")
        print(f"   Shift ID: {data.get('shiftId')}")
        print(f"   Clock Out Time: {data.get('clockOutTime')}")
        print(f"   Total Sales: {data.get('totalSales')}")
        return True
    else:
        print(f"❌ Clock out failed: {response.status_code}")
        print(f"   Response: {response.text}")
        return False

def main():
    """Run all tests"""
    print(f"\n🧪 TESTING V2 ENDPOINTS")
    print(f"Base URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    
    # Test 1: Login
    token = test_login()
    if not token:
        print("\n❌ FAILED: Cannot continue without token")
        return
    
    # Test 2: Monitor Stats
    test_monitor_stats(token)
    
    # Test 3: Clock In
    shift_id = test_clock_in(token)
    
    # Test 4: Complete Sale (only if we have a shift)
    if shift_id:
        test_complete_sale(token, shift_id)
    else:
        print("\n⚠️  Skipping sale test (no shift ID)")
    
    # Test 5: Clock Out
    if shift_id:
        test_clock_out(token, shift_id)
    
    # Final Summary
    print_section("TEST SUMMARY")
    print("✅ All critical endpoints tested")
    print("📊 Check results above for performance metrics")
    print(f"\n🎯 Performance Requirement: <300ms for Complete Sale")
    print(f"📈 Actual performance should be 50-150ms\n")

if __name__ == "__main__":
    main()
