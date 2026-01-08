#!/usr/bin/env python3
import requests
import json
import time
import urllib.parse
import websocket

BASE = 'http://127.0.0.1:5000/api'


def signup():
    data = {
        'email': 'smoke+test@example.com',
        'password': 'smoke123',
        'name': 'Smoke Tester'
    }
    try:
        r = requests.post(f"{BASE}/auth/signup", json=data, timeout=5)
    except Exception as e:
        print('Signup request failed:', e)
        return None
    if r.status_code in (200, 201):
        print('Signup OK')
        return r.json().get('token')
    if r.status_code == 400:
        print('User exists, will try login')
        return None
    print('Signup unexpected:', r.status_code, r.text)
    return None


def login():
    data = {'email': 'smoke+test@example.com', 'password': 'smoke123'}
    try:
        r = requests.post(f"{BASE}/auth/login", json=data, timeout=5)
    except Exception as e:
        print('Login request failed:', e)
        return None
    if r.status_code == 200:
        print('Login OK')
        return r.json().get('token')
    print('Login failed:', r.status_code, r.text)
    return None


if __name__ == '__main__':
    token = signup()
    if not token:
        token = login()

    if not token:
        print('No token obtained; aborting smoke tests')
        raise SystemExit(1)

    headers = {'Authorization': f'Bearer {token}'}

    # /auth/me
    try:
        r = requests.get(f"{BASE}/auth/me", headers=headers, timeout=5)
        print('/auth/me', r.status_code, r.text[:500])
    except Exception as e:
        print('Error calling /auth/me:', e)

    # /products GET
    try:
        r = requests.get(f"{BASE}/products", headers=headers, timeout=5)
        print('/products GET', r.status_code)
        try:
            print('Products:', r.json())
        except Exception:
            print('Products response not JSON')
    except Exception as e:
        print('Error calling /products:', e)

    # /products POST
    prod = {'name': 'SmokeProduct', 'price': 9.99, 'quantity': 3, 'unit': 'pcs', 'category': 'test'}
    try:
        r = requests.post(f"{BASE}/products", json=prod, headers=headers, timeout=5)
        print('/products POST', r.status_code, r.text[:500])
    except Exception as e:
        print('Error creating product:', e)

    # WebSocket connect
    ws_token = urllib.parse.quote(token, safe='')
    ws_url = f"ws://127.0.0.1:5000/api/ws/products?token={ws_token}"
    print('Connecting to WS at', ws_url)
    try:
        ws = websocket.create_connection(ws_url, timeout=10)
        print('WS connected')
        try:
            msg = ws.recv()
            print('WS recv:', msg)
        except Exception as e:
            print('WS recv error:', e)
        ws.close()
    except Exception as e:
        print('WS connection error:', e)
