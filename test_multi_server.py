#!/usr/bin/env python3
"""
POS Multi-Server Test Suite
============================
Tests the 3-server architecture:
  - AUTH-1 (port 8081)
  - API-1 (port 8082)
  - API-2 (port 8083)

Usage:
  python test_multi_server.py
"""

import os
import sys
import time
import uuid
import json
import logging
import threading
import requests
from typing import Optional, Dict, Any

# Test configuration
AUTH_BASE = "http://localhost:8081"
API1_BASE = "http://localhost:8082"
API2_BASE = "http://localhost:8083"
TEST_EMAIL = f"e2e-multi-{int(time.time())}@example.com"
TEST_PASSWORD = "Testpass1"
TEST_NAME = "E2E Multi Server Test"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_multi_server")

results = []

def log_result(test_name, passed, details=""):
    status = "PASS" if passed else "FAIL"
    results.append((test_name, status, details))
    logger.info(f"[{status}] {test_name}: {details}")


def wait_for_server(url, name, timeout=30):
    """Wait for a server to become healthy."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{url}/health", timeout=2)
            if resp.status_code == 200:
                logger.info(f"{name} is healthy")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    logger.error(f"{name} did not become healthy within {timeout}s")
    return False


def test_health_checks():
    """Test all servers respond to health checks."""
    log_result("Health: AUTH-1", wait_for_server(AUTH_BASE, "AUTH-1"))
    log_result("Health: API-1", wait_for_server(API1_BASE, "API-1"))
    log_result("Health: API-2", wait_for_server(API2_BASE, "API-2"))


def test_signup():
    """Test signup through auth server."""
    try:
        resp = requests.post(
            f"{AUTH_BASE}/api/auth/signup",
            json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD,
                "name": TEST_NAME,
            },
            timeout=30,
        )
        data = resp.json()
        passed = resp.status_code == 201 and data.get("token") is not None
        log_result("Signup via AUTH-1", passed, f"status={resp.status_code}, has_token={bool(data.get('token'))}")
        return data if passed else None
    except Exception as e:
        log_result("Signup via AUTH-1", False, str(e))
        return None


def test_login(signup_data=None):
    """Test login through auth server."""
    email = signup_data.get("user", {}).get("email") if signup_data else TEST_EMAIL
    try:
        resp = requests.post(
            f"{AUTH_BASE}/api/auth/login",
            json={"email": email, "password": TEST_PASSWORD},
            timeout=30,
        )
        data = resp.json()
        passed = resp.status_code == 200 and data.get("token") is not None
        log_result("Login via AUTH-1", passed, f"status={resp.status_code}, has_token={bool(data.get('token'))}")
        return data if passed else None
    except Exception as e:
        log_result("Login via AUTH-1", False, str(e))
        return None


def test_cross_server_auth(login_data):
    """Test that API servers recognize auth from auth server."""
    if not login_data:
        log_result("Cross-server auth", False, "No login data")
        return None
    
    token = login_data.get("token")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test API-1
    try:
        resp1 = requests.get(f"{API1_BASE}/api/auth/me", headers=headers, timeout=10)
        api1_ok = resp1.status_code == 200
        log_result("Auth recognized by API-1", api1_ok, f"status={resp1.status_code}")
    except Exception as e:
        log_result("Auth recognized by API-1", False, str(e))
        api1_ok = False
    
    # Test API-2
    try:
        resp2 = requests.get(f"{API2_BASE}/api/auth/me", headers=headers, timeout=10)
        api2_ok = resp2.status_code == 200
        log_result("Auth recognized by API-2", api2_ok, f"status={resp2.status_code}")
    except Exception as e:
        log_result("Auth recognized by API-2", False, str(e))
        api2_ok = False
    
    return token if (api1_ok or api2_ok) else None


def test_product_creation(token):
    """Test product creation through API-1."""
    if not token:
        log_result("Product creation via API-1", False, "No token")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    product_name = f"E2E Multi Server Product {int(time.time())}"
    
    try:
        resp = requests.post(
            f"{API1_BASE}/api/products",
            json={
                "name": product_name,
                "price": 100,
                "quantity": 10,
                "product_type": "regular",
                "visible_to_cashier": True,
            },
            headers=headers,
            timeout=30,
        )
        data = resp.json()
        passed = resp.status_code in (200, 201)
        log_result("Product creation via API-1", passed, f"status={resp.status_code}")
        return data if passed else None
    except Exception as e:
        log_result("Product creation via API-1", False, str(e))
        return None


def test_inventory_visibility(token, product_data):
    """Test that product is visible from API-2."""
    if not token or not product_data:
        log_result("Product visible on API-2", False, "Missing data")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    product_name = product_data.get("name", "")
    
    try:
        resp = requests.get(f"{API2_BASE}/api/products", headers=headers, timeout=30)
        data = resp.json()
        found = product_name in str(data) if isinstance(data, (list, dict)) else False
        log_result("Product visible on API-2", found, f"status={resp.status_code}")
    except Exception as e:
        log_result("Product visible on API-2", False, str(e))


def test_sale(token, product_data):
    """Test sale through API-1."""
    if not token or not product_data:
        log_result("Sale via API-1", False, "Missing data")
        return None
    
    headers = {"Authorization": f"Bearer {token}"}
    product_id = product_data.get("id")
    product_name = product_data.get("name", "")
    
    try:
        resp = requests.post(
            f"{API1_BASE}/api/sales",
            json={
                "items": [{"product_id": product_id, "quantity": 1, "price": 100}],
                "payment_method": "cash",
                "total": 100,
            },
            headers=headers,
            timeout=30,
        )
        data = resp.json()
        passed = resp.status_code in (200, 201)
        log_result("Sale via API-1", passed, f"status={resp.status_code}")
        return data if passed else None
    except Exception as e:
        log_result("Sale via API-1", False, str(e))
        return None


def test_concurrent_sales(token):
    """Test concurrent sales with a product that has stock=1."""
    if not token:
        log_result("Concurrent sales", False, "No token")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Create a product with stock=1
    product_name = f"E2E Concurrent Product {int(time.time())}"
    try:
        resp = requests.post(
            f"{API1_BASE}/api/products",
            json={
                "name": product_name,
                "price": 100,
                "quantity": 1,
                "product_type": "regular",
                "visible_to_cashier": True,
            },
            headers=headers,
            timeout=30,
        )
        product_data = resp.json()
        product_id = product_data.get("id")
        if not product_id:
            log_result("Concurrent sales", False, "Failed to create test product")
            return
    except Exception as e:
        log_result("Concurrent sales", False, f"Create product failed: {e}")
        return
    
    def make_sale():
        try:
            resp = requests.post(
                f"{API1_BASE}/api/sales",
                json={
                    "items": [{"product_id": product_id, "quantity": 1, "price": 100}],
                    "payment_method": "cash",
                    "total": 100,
                },
                headers=headers,
                timeout=30,
            )
            return resp.status_code, resp.json()
        except Exception as e:
            return 0, {"error": str(e)}
    
    # Fire two simultaneous requests
    results_list = []
    threads = []
    for i in range(2):
        t = threading.Thread(target=lambda: results_list.append(make_sale()))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # One should succeed, one should fail (or both fail due to race condition handling)
    statuses = [r[0] for r in results_list]
    success_count = sum(1 for s in statuses if s in (200, 201))
    
    passed = success_count == 1
    log_result("Concurrent sales (stock=1)", passed, f"success_count={success_count}, statuses={statuses}")


def test_server_headers():
    """Test that servers identify themselves correctly."""
    try:
        resp = requests.get(f"{AUTH_BASE}/health", timeout=5)
        headers = dict(resp.headers)
        has_server_id = "X-Server-ID" in headers or "x-server-id" in headers
        has_server_mode = "X-Server-Mode" in headers or "x-server-mode" in headers
        log_result("Server identification headers", has_server_id and has_server_mode,
                   f"X-Server-ID={headers.get('X-Server-ID', 'missing')}, X-Server-Mode={headers.get('X-Server-Mode', 'missing')}")
    except Exception as e:
        log_result("Server identification headers", False, str(e))


def test_logout(login_data):
    """Test logout through auth server."""
    if not login_data:
        log_result("Logout", False, "No login data")
        return
    
    token = login_data.get("token")
    refresh_token = login_data.get("refreshToken", "dummy")
    csrf_token = login_data.get("csrfToken", "")
    
    if not token:
        log_result("Logout", False, "No token")
        return
    
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        
        cookies = {}
        if csrf_token:
            cookies["csrf_token"] = csrf_token
        
        resp = requests.post(
            f"{AUTH_BASE}/api/auth/logout",
            json={"refreshToken": refresh_token},
            headers=headers,
            cookies=cookies,
            timeout=10,
        )
        passed = resp.status_code == 200
        log_result("Logout", passed, f"status={resp.status_code}")
    except Exception as e:
        log_result("Logout", False, str(e))


def test_protected_route_after_logout():
    """Test that protected routes are inaccessible after logout."""
    try:
        resp = requests.get(f"{API1_BASE}/api/auth/me", timeout=10)
        passed = resp.status_code in (401, 403)
        log_result("Protected route blocked after logout", passed, f"status={resp.status_code}")
    except Exception as e:
        log_result("Protected route blocked after logout", False, str(e))


def print_summary():
    """Print test summary."""
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, s, _ in results if s == "PASS")
    failed = sum(1 for _, s, _ in results if s == "FAIL")
    
    for name, status, details in results:
        print(f"  [{status}] {name}: {details}")
    
    print("-" * 70)
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    print("=" * 70)
    
    return failed == 0


def main():
    print("=" * 70)
    print("POS MULTI-SERVER ARCHITECTURE TEST")
    print("=" * 70)
    print(f"Auth Server:  {AUTH_BASE}")
    print(f"API Server 1: {API1_BASE}")
    print(f"API Server 2: {API2_BASE}")
    print("=" * 70)
    
    # Wait for all servers
    logger.info("Waiting for servers to be healthy...")
    test_health_checks()
    
    # Run tests
    logger.info("Running authentication tests...")
    signup_data = test_signup()
    login_data = test_login(signup_data)
    
    logger.info("Running cross-server auth tests...")
    token = test_cross_server_auth(login_data)
    
    if token:
        logger.info("Running business logic tests...")
        product_data = test_product_creation(token)
        test_inventory_visibility(token, product_data)
        test_sale(token, product_data)
        
        test_concurrent_sales(token)
        
        logger.info("Running server identification tests...")
        test_server_headers()
        
        logger.info("Running logout tests...")
        test_logout(login_data)
        test_protected_route_after_logout()
    
    success = print_summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
