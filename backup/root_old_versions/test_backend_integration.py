#!/usr/bin/env python3
"""
Test script for backend integration endpoints
Run this after starting the Flask app to verify all endpoints work
"""

import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:5000"
# IMPORTANT: Set this to a valid mainAdminToken from your system
TEST_TOKEN = "your_main_admin_token_here"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def test_endpoint(method, endpoint, description, body=None):
    """Test a single endpoint"""
    print(f"\n{Colors.BLUE}Testing: {description}{Colors.END}")
    print(f"  {method} {endpoint}")
    
    headers = {
        'Authorization': f'Bearer {TEST_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    try:
        if method == 'GET':
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
        elif method == 'POST':
            response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, json=body)
        
        if response.status_code in [200, 201]:
            print(f"  {Colors.GREEN}✓ SUCCESS (Status: {response.status_code}){Colors.END}")
            try:
                data = response.json()
                if isinstance(data, list):
                    print(f"  Response: Array with {len(data)} items")
                    if data and 'daysActive' in data[0]:
                        print(f"    First user subscription data:")
                        print(f"      - daysActive: {data[0].get('daysActive')}")
                        print(f"      - subscriptionStatus: {data[0].get('subscriptionStatus')}")
                        print(f"      - daysUntilExpiry: {data[0].get('daysUntilExpiry')}")
                else:
                    print(f"  Response: {json.dumps(data, indent=2)}")
            except:
                print(f"  Response: {response.text[:200]}")
            return True
        else:
            print(f"  {Colors.RED}✗ FAILED (Status: {response.status_code}){Colors.END}")
            print(f"  Response: {response.text}")
            return False
    except Exception as e:
        print(f"  {Colors.RED}✗ ERROR: {e}{Colors.END}")
        return False

def run_tests():
    """Run all tests"""
    print(f"\n{Colors.BLUE}{'='*60}")
    print("Backend Integration Tests")
    print(f"{'='*60}{Colors.END}")
    
    results = {}
    
    # Test 1: Get users with subscriptions
    results['subscriptions'] = test_endpoint(
        'GET',
        '/api/main-admin/users-with-subscriptions',
        'Get users with subscription data'
    )
    
    # Test 2: Send upgrade email
    results['email_upgrade'] = test_endpoint(
        'POST',
        '/api/main-admin/send-email',
        'Send upgrade reminder email',
        {
            'userId': 1,
            'type': 'upgrade'
        }
    )
    
    # Test 3: Send reminder email
    results['email_reminder'] = test_endpoint(
        'POST',
        '/api/main-admin/send-email',
        'Send trial reminder email',
        {
            'userId': 1,
            'type': 'reminder',
            'daysLeft': 5
        }
    )
    
    # Test 4: Lock user
    results['lock_user'] = test_endpoint(
        'POST',
        '/api/main-admin/users/1/lock',
        'Lock user account',
        {'locked': True}
    )
    
    # Test 5: Unlock user
    results['unlock_user'] = test_endpoint(
        'POST',
        '/api/main-admin/users/1/lock',
        'Unlock user account',
        {'locked': False}
    )
    
    # Summary
    print(f"\n{Colors.BLUE}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{Colors.END}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = f"{Colors.GREEN}PASS{Colors.END}" if result else f"{Colors.RED}FAIL{Colors.END}"
        print(f"  {test_name:30} {status}")
    
    print(f"\n  Total: {passed}/{total} tests passed")
    
    if passed == total:
        print(f"\n{Colors.GREEN}All tests passed! ✓{Colors.END}")
    else:
        print(f"\n{Colors.YELLOW}Some tests failed. Check responses above.{Colors.END}")
    
    # Instructions
    print(f"\n{Colors.YELLOW}Setup Instructions:{Colors.END}")
    print(f"  1. Update TEST_TOKEN variable with valid mainAdminToken from localStorage")
    print(f"  2. Make sure Flask backend is running: python app.py")
    print(f"  3. Run this test: python test_backend_integration.py")
    print(f"  4. Check responses for correct data structure")

if __name__ == '__main__':
    run_tests()
