#!/usr/bin/env python3
"""Test the Complete Sale button fix"""

import requests
import json
import time

BASE_URL = 'http://localhost:5000/api'

def test_complete_sale():
    print("🧪 Testing Complete Sale Button Fix")
    print("=" * 60)
    
    # 1. Signup admin
    print("\n1️⃣  Signing up admin...")
    admin_response = requests.post(f'{BASE_URL}/auth/signup', json={
        'email': f'admin_test_{int(time.time())}@test.com',
        'password': 'Test@1234',
        'name': 'Admin Test',
        'role': 'admin'
    })
    admin_data = admin_response.json()
    admin_token = admin_data.get('token')
    print(f"✅ Admin signed up: {admin_data.get('user', {}).get('name')}")
    
    # 2. Add products to inventory
    print("\n2️⃣  Adding products...")
    headers = {'Authorization': f'Bearer {admin_token}'}
    
    products_to_add = [
        {'name': 'Rice', 'price': 500, 'cost': 300, 'quantity': 100, 'unit': 'bag'},
        {'name': 'Fish', 'price': 800, 'cost': 400, 'quantity': 200, 'unit': 'kg'}
    ]
    
    product_ids = []
    for product in products_to_add:
        resp = requests.post(f'{BASE_URL}/products', json=product, headers=headers)
        if resp.status_code in [200, 201]:
            pid = resp.json().get('id')
            product_ids.append(pid)
            print(f"✅ Added product: {product['name']} (ID: {pid})")
        else:
            print(f"❌ Failed to add {product['name']}: {resp.status_code}")
    
    # 3. Create cashier user
    print("\n3️⃣  Creating cashier...")
    cashier_resp = requests.post(f'{BASE_URL}/users', json={
        'email': f'cashier_test_{int(time.time())}@test.com',
        'password': 'Test@1234',
        'name': 'Cashier Test',
        'role': 'cashier'
    }, headers=headers)
    cashier_data = cashier_resp.json()
    cashier_token = cashier_data.get('token') or admin_token
    print(f"✅ Cashier created: {cashier_data.get('user', {}).get('name')}")
    
    # 4. Create a sale (this is the "Complete Sale" button action)
    print("\n4️⃣  Testing Complete Sale button (creating sale)...")
    
    if not product_ids:
        print("❌ No products available to sell!")
        return False
    
    sale_data = {
        'items': [
            {'productId': product_ids[0], 'quantity': 2, 'unit': 'bag', 'price': 500},
            {'productId': product_ids[1], 'quantity': 0.5, 'unit': 'kg', 'price': 800}
        ],
        'total': 2000.0,
        'discount': 0,
        'tax': 320,
        'taxType': 'exclusive',
        'paymentMethod': 'cash'
    }
    
    sale_resp = requests.post(f'{BASE_URL}/sales', json=sale_data, headers={'Authorization': f'Bearer {admin_token}'})
    
    print(f"📊 Sale Response Status: {sale_resp.status_code}")
    sale_result = sale_resp.json()
    print(f"📊 Sale Response: {json.dumps(sale_result, indent=2)}")
    
    if sale_resp.status_code in [200, 201]:
        if sale_result.get('success') or sale_result.get('saleId'):
            print(f"✅ COMPLETE SALE SUCCESS!")
            print(f"   Sale ID: {sale_result.get('saleId')}")
            print(f"   Total: {sale_result.get('total')} KSH")
            print(f"   Stock Deductions: {sale_result.get('stockDeductions', {}).get('products', [])}")
            return True
        else:
            print(f"❌ Sale created but missing success indicator")
            return False
    else:
        print(f"❌ Sale creation failed: {sale_result.get('error', 'Unknown error')}")
        return False

if __name__ == '__main__':
    try:
        success = test_complete_sale()
        print("\n" + "=" * 60)
        if success:
            print("✅ COMPLETE SALE BUTTON FIX VERIFIED")
        else:
            print("❌ Issue detected with complete sale")
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
