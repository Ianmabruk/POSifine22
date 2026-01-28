#!/usr/bin/env python3
"""
POS System - Comprehensive Test Data Generator & Performance Profiler
Generates realistic business data and tests all critical workflows
"""

import requests
import json
import time
import sys
from datetime import datetime, timedelta
import random

BASE_URL = "http://localhost:5000/api"
HEADERS = {"Content-Type": "application/json"}

# Color codes for terminal output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
CYAN = '\033[96m'
RESET = '\033[0m'

class POSSystemTester:
    def __init__(self):
        self.admin_token = None
        self.cashier_token = None
        self.test_results = []
        self.performance_metrics = {}
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        if level == "SUCCESS":
            print(f"{GREEN}[{timestamp}] ✅ {message}{RESET}")
        elif level == "ERROR":
            print(f"{RED}[{timestamp}] ❌ {message}{RESET}")
        elif level == "WARNING":
            print(f"{YELLOW}[{timestamp}] ⚠️  {message}{RESET}")
        elif level == "DEBUG":
            print(f"{CYAN}[{timestamp}] 🔍 {message}{RESET}")
        else:
            print(f"{BLUE}[{timestamp}] ℹ️  {message}{RESET}")
    
    def make_request(self, method, endpoint, data=None, token=None, test_name=None):
        """Make API request and record performance"""
        url = f"{BASE_URL}{endpoint}"
        headers = HEADERS.copy()
        
        if token:
            headers["Authorization"] = f"Bearer {token}"
        
        try:
            start_time = time.time()
            
            if method == "GET":
                response = requests.get(url, headers=headers, timeout=10)
            elif method == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=10)
            else:
                raise ValueError(f"Unknown method: {method}")
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Record performance metric
            if test_name:
                if test_name not in self.performance_metrics:
                    self.performance_metrics[test_name] = []
                self.performance_metrics[test_name].append(elapsed_ms)
            
            return response, elapsed_ms
        except Exception as e:
            self.log(f"Request failed: {e}", "ERROR")
            return None, None
    
    def test_signup_flow(self):
        """Test 1: Signup admin user"""
        self.log("=" * 60, "INFO")
        self.log("TEST 1: Signup Admin User", "INFO")
        self.log("=" * 60, "INFO")
        
        payload = {
            "name": "Admin User",
            "email": f"admin_{int(time.time())}@posifine.test",
            "password": "Admin123456",
            "planId": "ultra"
        }
        
        response, elapsed_ms = self.make_request(
            "POST", "/auth/signup", payload, 
            test_name="Signup"
        )
        
        if response and response.status_code == 200:
            result = response.json()
            self.admin_token = result['token']
            admin_user = result['user']
            
            self.log(f"✅ Admin signup successful in {elapsed_ms:.2f}ms", "SUCCESS")
            self.log(f"   Email: {admin_user['email']}", "DEBUG")
            self.log(f"   Role: {admin_user['role']}", "DEBUG")
            self.log(f"   Plan: {admin_user['plan']}", "DEBUG")
            self.log(f"   Account ID: {admin_user['accountId']}", "DEBUG")
            
            return True, admin_user
        else:
            self.log(f"❌ Signup failed: {response.status_code if response else 'No response'}", "ERROR")
            return False, None
    
    def test_add_products(self):
        """Test 2: Add test products to inventory"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 2: Add Products to Inventory", "INFO")
        self.log("=" * 60, "INFO")
        
        products = [
            {"name": "Rice 50kg Bag", "price": 2500, "cost": 2000, "unit": "bag", "quantity": 100},
            {"name": "Premium Cooking Oil 5L", "price": 1800, "cost": 1400, "unit": "liter", "quantity": 50},
            {"name": "Nile Perch Fish 1kg", "price": 800, "cost": 500, "unit": "kg", "quantity": 200},
            {"name": "Bread 1kg", "price": 450, "cost": 300, "unit": "piece", "quantity": 150},
            {"name": "Ugali Flour 2kg", "price": 350, "cost": 250, "unit": "bag", "quantity": 80},
            {"name": "Tomato Sauce 500ml", "price": 120, "cost": 80, "unit": "bottle", "quantity": 300},
            {"name": "Eggs 1 Dozen", "price": 550, "cost": 400, "unit": "dozen", "quantity": 60},
            {"name": "Butter 250g", "price": 280, "cost": 200, "unit": "pack", "quantity": 100},
        ]
        
        created_products = []
        for product in products:
            response, elapsed_ms = self.make_request(
                "POST", "/products", product, 
                token=self.admin_token,
                test_name="Add Product"
            )
            
            if response and response.status_code in [200, 201]:
                result = response.json()
                created_products.append(result)
                self.log(f"✅ Added: {product['name']} ({elapsed_ms:.2f}ms)", "SUCCESS")
            else:
                self.log(f"⚠️  Failed to add {product['name']}", "WARNING")
        
        self.log(f"\n📊 Total products added: {len(created_products)}/{len(products)}", "DEBUG")
        return created_products
    
    def test_create_cashier_user(self):
        """Test 3: Create cashier user"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 3: Create Cashier User", "INFO")
        self.log("=" * 60, "INFO")
        
        cashier_data = {
            "name": "Cashier Test User",
            "email": f"cashier_{int(time.time())}@posifine.test",
            "password": "Cashier123456",
            "role": "cashier"
        }
        
        response, elapsed_ms = self.make_request(
            "POST", "/users", cashier_data, 
            token=self.admin_token,
            test_name="Create Cashier"
        )
        
        if response and response.status_code in [200, 201]:
            result = response.json()
            self.log(f"✅ Cashier created in {elapsed_ms:.2f}ms", "SUCCESS")
            self.log(f"   Email: {result.get('email', 'N/A')}", "DEBUG")
            self.log(f"   Role: {result.get('role', 'N/A')}", "DEBUG")
            return True, result
        else:
            self.log(f"❌ Failed to create cashier", "ERROR")
            return False, None
    
    def test_cashier_login(self, email, password):
        """Test 4: Cashier login"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 4: Cashier Login", "INFO")
        self.log("=" * 60, "INFO")
        
        login_data = {"email": email, "password": password}
        
        response, elapsed_ms = self.make_request(
            "POST", "/auth/login", login_data,
            test_name="Cashier Login"
        )
        
        if response and response.status_code == 200:
            result = response.json()
            self.cashier_token = result['token']
            self.log(f"✅ Cashier login successful in {elapsed_ms:.2f}ms", "SUCCESS")
            return True, result
        else:
            self.log(f"❌ Cashier login failed", "ERROR")
            return False, None
    
    def test_get_products_as_cashier(self):
        """Test 5: Cashier fetches products"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 5: Get Products (Cashier View)", "INFO")
        self.log("=" * 60, "INFO")
        
        response, elapsed_ms = self.make_request(
            "GET", "/products", None,
            token=self.cashier_token,
            test_name="Get Products"
        )
        
        if response and response.status_code == 200:
            products = response.json()
            self.log(f"✅ Retrieved {len(products)} products in {elapsed_ms:.2f}ms", "SUCCESS")
            return True, products
        else:
            self.log(f"❌ Failed to get products", "ERROR")
            return False, None
    
    def test_complete_sale(self, products):
        """Test 6: Complete a sale with stock deduction"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 6: Complete Sale (Stock Deduction Test)", "INFO")
        self.log("=" * 60, "INFO")
        
        if not products or len(products) < 2:
            self.log("❌ Not enough products for sale test", "ERROR")
            return False
        
        # Create sale items
        sale_items = [
            {
                "productId": products[0]['id'],
                "quantity": 2,
                "unit": products[0].get('unit', 'piece'),
                "price": products[0]['price']
            },
            {
                "productId": products[2]['id'],
                "quantity": 0.5,
                "unit": products[2].get('unit', 'piece'),
                "price": products[2]['price']
            }
        ]
        
        item_total = sum(item['quantity'] * item['price'] for item in sale_items)
        discount = 100  # KSH 100 discount
        tax = (item_total - discount) * 0.16  # 16% tax
        
        sale_data = {
            "items": sale_items,
            "total": item_total - discount + tax,
            "discount": discount,
            "tax": tax,
            "taxType": "exclusive",
            "paymentMethod": "cash"
        }
        
        self.log(f"Sale breakdown:", "DEBUG")
        self.log(f"  Item 1: {products[0]['name']} x {sale_items[0]['quantity']} = {sale_items[0]['quantity'] * sale_items[0]['price']} KSH", "DEBUG")
        self.log(f"  Item 2: {products[2]['name']} x {sale_items[1]['quantity']} = {sale_items[1]['quantity'] * sale_items[1]['price']} KSH", "DEBUG")
        self.log(f"  Subtotal: {item_total} KSH", "DEBUG")
        self.log(f"  Discount: -{discount} KSH", "DEBUG")
        self.log(f"  Tax (16%): +{tax:.2f} KSH", "DEBUG")
        self.log(f"  Total: {sale_data['total']:.2f} KSH", "DEBUG")
        
        response, elapsed_ms = self.make_request(
            "POST", "/sales", sale_data,
            token=self.cashier_token,
            test_name="Complete Sale"
        )
        
        if response and response.status_code in [200, 201]:
            result = response.json()
            self.log(f"\n✅ Sale completed in {elapsed_ms:.2f}ms", "SUCCESS")
            self.log(f"   Sale ID: #{result.get('saleId', 'N/A')}", "DEBUG")
            self.log(f"   Items: {len(sale_items)}", "DEBUG")
            self.log(f"   Total Amount: {result.get('total', 'N/A')} KSH", "DEBUG")
            
            # Check stock deductions
            if 'stockDeductions' in result and 'products' in result['stockDeductions']:
                deductions = result['stockDeductions']['products']
                self.log(f"\n   Stock Deductions:", "DEBUG")
                for deduction in deductions:
                    self.log(f"     • {deduction['name']}: -{deduction['deducted']}{deduction['unit']} ({deduction['before']} → {deduction['after']})", "DEBUG")
            
            return True, result
        else:
            self.log(f"❌ Sale failed: {response.status_code if response else 'No response'}", "ERROR")
            return False, None
    
    def test_verify_stock_updated(self, original_products):
        """Test 7: Verify stock was actually deducted"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 7: Verify Stock Deduction (POST-SALE CHECK)", "INFO")
        self.log("=" * 60, "INFO")
        
        response, elapsed_ms = self.make_request(
            "GET", "/products", None,
            token=self.cashier_token,
            test_name="Verify Stock"
        )
        
        if response and response.status_code == 200:
            current_products = response.json()
            
            self.log(f"✅ Retrieved products in {elapsed_ms:.2f}ms", "SUCCESS")
            self.log(f"\n   Stock Changes:", "DEBUG")
            
            for orig in original_products[:2]:
                current = next((p for p in current_products if p['id'] == orig['id']), None)
                if current:
                    change = orig['quantity'] - current['quantity']
                    if change > 0:
                        self.log(f"   ✓ {orig['name']}: {orig['quantity']} → {current['quantity']} ({change} deducted)", "DEBUG")
                    else:
                        self.log(f"   ✗ {orig['name']}: No change detected (POTENTIAL BUG)", "WARNING")
            
            return True
        else:
            self.log(f"❌ Failed to verify stock", "ERROR")
            return False
    
    def test_dashboard_stats(self):
        """Test 8: Check dashboard stats"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("TEST 8: Dashboard Stats", "INFO")
        self.log("=" * 60, "INFO")
        
        response, elapsed_ms = self.make_request(
            "GET", "/stats", None,
            token=self.admin_token,
            test_name="Get Stats"
        )
        
        if response and response.status_code == 200:
            stats = response.json()
            self.log(f"✅ Retrieved stats in {elapsed_ms:.2f}ms", "SUCCESS")
            self.log(f"\n   Dashboard Metrics:", "DEBUG")
            self.log(f"   Total Sales: {stats.get('totalSales', 0)} transactions", "DEBUG")
            self.log(f"   Total Revenue: {stats.get('totalRevenue', 0)} KSH", "DEBUG")
            self.log(f"   Gross Profit: {stats.get('grossProfit', 0)} KSH", "DEBUG")
            self.log(f"   Net Profit: {stats.get('netProfit', 0)} KSH", "DEBUG")
            self.log(f"   Expenses: {stats.get('totalExpenses', 0)} KSH", "DEBUG")
            return True, stats
        else:
            self.log(f"❌ Failed to get stats", "ERROR")
            return False, None
    
    def test_multiple_sales(self, products, count=5):
        """Test 9: Complete multiple sales to stress test"""
        self.log("\n" + "=" * 60, "INFO")
        self.log(f"TEST 9: Multiple Sales Stress Test ({count} sales)", "INFO")
        self.log("=" * 60, "INFO")
        
        successful_sales = 0
        total_revenue = 0
        
        for i in range(count):
            # Randomly select 1-3 products
            sale_items = []
            for _ in range(random.randint(1, 3)):
                product = random.choice(products)
                sale_items.append({
                    "productId": product['id'],
                    "quantity": random.uniform(0.5, 3),
                    "unit": product.get('unit', 'piece'),
                    "price": product['price']
                })
            
            item_total = sum(item['quantity'] * item['price'] for item in sale_items)
            discount = random.randint(0, int(item_total * 0.1))
            tax = (item_total - discount) * 0.16
            
            sale_data = {
                "items": sale_items,
                "total": item_total - discount + tax,
                "discount": discount,
                "tax": tax,
                "taxType": "exclusive",
                "paymentMethod": random.choice(["cash", "card", "check"])
            }
            
            response, elapsed_ms = self.make_request(
                "POST", "/sales", sale_data,
                token=self.cashier_token,
                test_name=f"Sale {i+1}"
            )
            
            if response and response.status_code in [200, 201]:
                result = response.json()
                successful_sales += 1
                total_revenue += result.get('total', 0)
                self.log(f"   Sale {i+1}: ✅ {result.get('total', 0):.2f} KSH ({elapsed_ms:.2f}ms)", "SUCCESS")
            else:
                self.log(f"   Sale {i+1}: ❌ Failed", "WARNING")
        
        self.log(f"\n📊 Sales Summary:", "DEBUG")
        self.log(f"   Successful: {successful_sales}/{count}", "DEBUG")
        self.log(f"   Total Revenue: {total_revenue:.2f} KSH", "DEBUG")
        self.log(f"   Average Sale: {total_revenue / successful_sales if successful_sales > 0 else 0:.2f} KSH", "DEBUG")
        
        return successful_sales == count
    
    def print_performance_report(self):
        """Print performance metrics"""
        self.log("\n" + "=" * 60, "INFO")
        self.log("PERFORMANCE REPORT", "INFO")
        self.log("=" * 60, "INFO")
        
        for test_name, times in self.performance_metrics.items():
            avg_time = sum(times) / len(times)
            min_time = min(times)
            max_time = max(times)
            
            status = "✅" if avg_time < 100 else "⚠️ " if avg_time < 500 else "❌"
            self.log(f"\n{status} {test_name}:", "DEBUG")
            self.log(f"   Avg: {avg_time:.2f}ms, Min: {min_time:.2f}ms, Max: {max_time:.2f}ms", "DEBUG")
    
    def run_all_tests(self):
        """Execute complete test suite"""
        self.log("\n" + "🧪 " * 20, "INFO")
        self.log("POS SYSTEM - COMPREHENSIVE TEST SUITE", "INFO")
        self.log("🧪 " * 20, "INFO")
        self.log(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")
        
        # Test 1: Signup
        success, admin = self.test_signup_flow()
        if not success:
            self.log("Cannot proceed without admin signup", "ERROR")
            return
        
        # Test 2: Add products
        products = self.test_add_products()
        if not products:
            self.log("Cannot proceed without products", "ERROR")
            return
        
        # Test 3: Create cashier
        success, cashier = self.test_create_cashier_user()
        if not success:
            self.log("Cannot proceed without cashier", "ERROR")
            return
        
        # Test 4: Cashier login
        success, _ = self.test_cashier_login(cashier['email'], "Cashier123456")
        if not success:
            self.log("Cannot proceed without cashier login", "ERROR")
            return
        
        # Test 5: Get products as cashier
        success, cashier_products = self.test_get_products_as_cashier()
        if not success:
            self.log("Cannot verify product visibility", "ERROR")
            return
        
        # Test 6: Complete single sale
        success, sale_result = self.test_complete_sale(cashier_products)
        if not success:
            self.log("Sale creation failed", "ERROR")
            return
        
        # Test 7: Verify stock deduction
        self.test_verify_stock_updated(products)
        
        # Test 8: Check dashboard stats
        self.test_dashboard_stats()
        
        # Test 9: Multiple sales
        self.test_multiple_sales(cashier_products, count=5)
        
        # Print performance report
        self.print_performance_report()
        
        self.log("\n" + "=" * 60, "INFO")
        self.log("✅ TEST SUITE COMPLETE", "INFO")
        self.log("=" * 60, "INFO")
        self.log(f"End Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", "INFO")

if __name__ == "__main__":
    print("\n")
    tester = POSSystemTester()
    tester.run_all_tests()
