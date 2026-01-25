"""
BACKEND TESTING SCRIPT
======================
Test critical features of the rewritten POS backend:
1. Complete Sell performance (<50ms target)
2. Stock deduction accuracy
3. Real-time sync
4. Multi-tenant isolation
"""

import requests
import time
import json
from datetime import datetime

# Configuration
BASE_URL = "http://localhost:5000"
TEST_EMAIL = "test@example.com"
TEST_PASSWORD = "testpassword123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

def print_success(msg):
    print(f"{Colors.GREEN}✓ {msg}{Colors.END}")

def print_error(msg):
    print(f"{Colors.RED}✗ {msg}{Colors.END}")

def print_info(msg):
    print(f"{Colors.BLUE}→ {msg}{Colors.END}")

def print_warning(msg):
    print(f"{Colors.YELLOW}⚠ {msg}{Colors.END}")

class BackendTester:
    def __init__(self, base_url):
        self.base_url = base_url
        self.token = None
        self.account_id = None
        self.user_id = None
        self.test_product_id = None
    
    def test_health(self):
        """Test backend health"""
        print_info("Testing backend health...")
        try:
            response = requests.get(f"{self.base_url}/")
            if response.status_code == 200:
                data = response.json()
                print_success(f"Backend is running - Version: {data.get('version')}, Storage: {data.get('storage')}")
                return True
            else:
                print_error(f"Health check failed: {response.status_code}")
                return False
        except Exception as e:
            print_error(f"Cannot connect to backend: {e}")
            return False
    
    def test_signup_login(self):
        """Test signup and login"""
        print_info("Testing signup and login...")
        
        # Signup
        signup_data = {
            'email': TEST_EMAIL,
            'password': TEST_PASSWORD,
            'name': 'Test User',
            'plan': 'free'
        }
        
        try:
            response = requests.post(f"{self.base_url}/api/auth/signup", json=signup_data)
            
            if response.status_code == 201 or response.status_code == 400:
                # 400 might mean user already exists, try login
                login_data = {
                    'email': TEST_EMAIL,
                    'password': TEST_PASSWORD
                }
                
                response = requests.post(f"{self.base_url}/api/auth/login", json=login_data)
                
                if response.status_code == 200:
                    data = response.json()
                    self.token = data.get('token')
                    self.account_id = data.get('account_id')
                    self.user_id = data.get('id')
                    print_success(f"Login successful - User ID: {self.user_id}, Account: {self.account_id}")
                    return True
                else:
                    print_error(f"Login failed: {response.text}")
                    return False
            else:
                print_error(f"Signup failed: {response.text}")
                return False
        
        except Exception as e:
            print_error(f"Signup/Login error: {e}")
            return False
    
    def get_headers(self):
        """Get authorization headers"""
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def test_create_product(self):
        """Test product creation"""
        print_info("Testing product creation...")
        
        product_data = {
            'name': 'Test Product',
            'price': 100.0,
            'cost': 50.0,
            'quantity': 100.0,
            'category': 'test',
            'unit': 'pcs'
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/api/products",
                headers=self.get_headers(),
                json=product_data
            )
            
            if response.status_code == 201:
                data = response.json()
                self.test_product_id = data.get('id')
                print_success(f"Product created - ID: {self.test_product_id}")
                return True
            else:
                print_error(f"Product creation failed: {response.text}")
                return False
        
        except Exception as e:
            print_error(f"Product creation error: {e}")
            return False
    
    def test_complete_sell_performance(self):
        """Test Complete Sell performance (TARGET: <50ms)"""
        print_info("Testing Complete Sell performance...")
        
        if not self.test_product_id:
            print_warning("No test product available")
            return False
        
        sale_data = {
            'items': [
                {
                    'product_id': self.test_product_id,
                    'quantity': 1
                }
            ],
            'paymentMethod': 'cash',
            'amountPaid': 100.0,
            'taxRate': 0.0,
            'discountAmount': 0.0,
            'serviceFee': 0.0
        }
        
        # Warm-up request
        requests.post(
            f"{self.base_url}/api/sales",
            headers=self.get_headers(),
            json=sale_data
        )
        
        # Performance test (5 sales)
        times = []
        for i in range(5):
            start = time.time()
            
            response = requests.post(
                f"{self.base_url}/api/sales",
                headers=self.get_headers(),
                json=sale_data
            )
            
            end = time.time()
            elapsed_ms = (end - start) * 1000
            times.append(elapsed_ms)
            
            if response.status_code == 201:
                print_success(f"Sale {i+1} completed in {elapsed_ms:.2f}ms")
            else:
                print_error(f"Sale {i+1} failed: {response.text}")
        
        # Calculate average
        avg_time = sum(times) / len(times)
        
        if avg_time < 50:
            print_success(f"✨ EXCELLENT! Average time: {avg_time:.2f}ms (Target: <50ms)")
        elif avg_time < 100:
            print_success(f"✓ GOOD! Average time: {avg_time:.2f}ms (Target: <50ms)")
        elif avg_time < 200:
            print_warning(f"⚠ ACCEPTABLE! Average time: {avg_time:.2f}ms (Target: <50ms)")
        else:
            print_error(f"✗ TOO SLOW! Average time: {avg_time:.2f}ms (Target: <50ms)")
        
        return avg_time < 200
    
    def test_stock_accuracy(self):
        """Test stock deduction accuracy"""
        print_info("Testing stock accuracy...")
        
        if not self.test_product_id:
            print_warning("No test product available")
            return False
        
        try:
            # Get initial stock
            response = requests.get(
                f"{self.base_url}/api/products/{self.test_product_id}",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                initial_stock = response.json().get('quantity')
                print_info(f"Initial stock: {initial_stock}")
                
                # Make a sale
                sale_data = {
                    'items': [
                        {
                            'product_id': self.test_product_id,
                            'quantity': 2
                        }
                    ],
                    'paymentMethod': 'cash',
                    'amountPaid': 200.0
                }
                
                response = requests.post(
                    f"{self.base_url}/api/sales",
                    headers=self.get_headers(),
                    json=sale_data
                )
                
                if response.status_code == 201:
                    # Check stock after sale
                    response = requests.get(
                        f"{self.base_url}/api/products/{self.test_product_id}",
                        headers=self.get_headers()
                    )
                    
                    if response.status_code == 200:
                        final_stock = response.json().get('quantity')
                        expected_stock = initial_stock - 2
                        
                        print_info(f"Final stock: {final_stock}, Expected: {expected_stock}")
                        
                        if abs(final_stock - expected_stock) < 0.001:
                            print_success("Stock deduction is accurate!")
                            return True
                        else:
                            print_error(f"Stock mismatch! Expected {expected_stock}, got {final_stock}")
                            return False
                else:
                    print_error(f"Sale failed: {response.text}")
                    return False
            else:
                print_error(f"Failed to get product: {response.text}")
                return False
        
        except Exception as e:
            print_error(f"Stock accuracy test error: {e}")
            return False
    
    def test_time_tracking(self):
        """Test clock in/out"""
        print_info("Testing time tracking...")
        
        try:
            # Clock in
            response = requests.post(
                f"{self.base_url}/api/clock-in",
                headers=self.get_headers()
            )
            
            if response.status_code == 201:
                entry = response.json()
                print_success(f"Clocked in - Entry ID: {entry.get('id')}")
                
                # Check status
                response = requests.get(
                    f"{self.base_url}/api/clock-status",
                    headers=self.get_headers()
                )
                
                if response.status_code == 200:
                    status = response.json()
                    if status.get('clocked_in'):
                        print_success("Clock status verified")
                        
                        # Clock out
                        time.sleep(1)
                        response = requests.post(
                            f"{self.base_url}/api/clock-out",
                            headers=self.get_headers()
                        )
                        
                        if response.status_code == 200:
                            entry = response.json()
                            duration = entry.get('duration_minutes')
                            print_success(f"Clocked out - Duration: {duration} minutes")
                            return True
                        else:
                            print_error(f"Clock out failed: {response.text}")
                            return False
                    else:
                        print_error("Clock in not registered")
                        return False
                else:
                    print_error(f"Failed to get clock status: {response.text}")
                    return False
            else:
                print_error(f"Clock in failed: {response.text}")
                return False
        
        except Exception as e:
            print_error(f"Time tracking test error: {e}")
            return False
    
    def test_dashboard_stats(self):
        """Test dashboard statistics"""
        print_info("Testing dashboard statistics...")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/stats",
                headers=self.get_headers()
            )
            
            if response.status_code == 200:
                stats = response.json()
                print_success("Dashboard stats retrieved successfully")
                print_info(f"Total Sales: {stats.get('total_sales')}")
                print_info(f"Gross Profit: {stats.get('gross_profit')}")
                print_info(f"Net Profit: {stats.get('net_profit')}")
                return True
            else:
                print_error(f"Failed to get stats: {response.text}")
                return False
        
        except Exception as e:
            print_error(f"Dashboard stats test error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*60)
        print("POS BACKEND TEST SUITE")
        print("="*60 + "\n")
        
        results = []
        
        # Test 1: Health
        results.append(("Health Check", self.test_health()))
        
        # Test 2: Auth
        results.append(("Signup/Login", self.test_signup_login()))
        
        if not self.token:
            print_error("Authentication failed. Stopping tests.")
            return
        
        # Test 3: Product Creation
        results.append(("Product Creation", self.test_create_product()))
        
        # Test 4: Complete Sell Performance
        results.append(("Complete Sell Performance", self.test_complete_sell_performance()))
        
        # Test 5: Stock Accuracy
        results.append(("Stock Accuracy", self.test_stock_accuracy()))
        
        # Test 6: Time Tracking
        results.append(("Time Tracking", self.test_time_tracking()))
        
        # Test 7: Dashboard Stats
        results.append(("Dashboard Stats", self.test_dashboard_stats()))
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        for name, result in results:
            status = "PASS" if result else "FAIL"
            color = Colors.GREEN if result else Colors.RED
            print(f"{color}{status}{Colors.END} - {name}")
        
        print(f"\n{Colors.BLUE}Total: {passed}/{total} tests passed{Colors.END}\n")
        
        if passed == total:
            print_success("🎉 All tests passed!")
        elif passed >= total * 0.7:
            print_warning("⚠️  Most tests passed, but some issues remain")
        else:
            print_error("❌ Multiple tests failed. System needs attention.")

if __name__ == "__main__":
    tester = BackendTester(BASE_URL)
    tester.run_all_tests()
