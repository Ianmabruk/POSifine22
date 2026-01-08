#!/usr/bin/env python3
"""
Script runner for manual backend checks (not a pytest test file).
"""
import requests

BASE_URL = "http://localhost:5002/api"

def health_check():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        print('health', r.status_code, r.text)
    except Exception as e:
        print('health failed', e)

if __name__ == '__main__':
    health_check()
