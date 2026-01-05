import json
import urllib.request
import urllib.parse

BASE = 'http://127.0.0.1:5002'

def request(path, method='GET', data=None, token=None):
    url = BASE + path
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    data_bytes = None
    if data is not None:
        data_bytes = json.dumps(data).encode('utf-8')
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode('utf-8')
            try:
                return resp.getcode(), json.loads(body)
            except Exception:
                return resp.getcode(), body
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8')
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, body
    except Exception as e:
        return None, str(e)

def main():
    print('Checking health...')
    code, body = request('/api/health')
    print(code, body)

    # Signup admin user (Ultra plan)
    admin = {'email': 'admin@example.com', 'password': 'pass', 'name': 'Admin', 'plan': 'ultra', 'companyName': 'ACME'}
    code, body = request('/api/auth/signup', method='POST', data=admin)
    print('signup:', code, body)
    token = None
    if code == 200 and isinstance(body, dict) and 'token' in body:
        token = body['token']
    else:
        print('Signup failed, attempting login...')
        code, body = request('/api/auth/login', method='POST', data={'email': admin['email'], 'password': admin['password']})
        print('login:', code, body)
        if code == 200 and 'token' in body:
            token = body['token']

    if not token:
        print('No token available, aborting tests')
        return

    # Create a simple product
    prod = {'name': 'Water Bottle', 'price': 120, 'cost': 60, 'quantity': 10, 'unit': 'pcs', 'category': 'drinks'}
    code, body = request('/api/products', method='POST', data=prod, token=token)
    print('create product:', code, body)
    simple_id = body.get('id') if isinstance(body, dict) else None

    # Create a component product
    comp = {'name': 'Syrup', 'price': 50, 'cost': 20, 'quantity': 20, 'unit': 'ml', 'category': 'ingredients'}
    code, body = request('/api/products', method='POST', data=comp, token=token)
    print('create component:', code, body)
    comp_id = body.get('id') if isinstance(body, dict) else None

    # Create composite product (if allowed)
    composite = {'name': 'Drink Mix', 'price': 300, 'cost': 0, 'image': '', 'category': 'drinks', 'unit': 'cup', 'recipe': [{'productId': comp_id, 'quantity': 50}], 'visible_to_cashier': True}
    code, body = request('/api/products', method='POST', data=composite, token=token)
    print('create composite:', code, body)
    composite_id = body.get('id') if isinstance(body, dict) else None

    # List products
    code, body = request('/api/products', method='GET', token=token)
    print('list products:', code, body)

    # Create sale for simple product
    if simple_id:
        sale = {'items': [{'productId': simple_id, 'quantity': 2}], 'total': 240}
        code, body = request('/api/sales', method='POST', data=sale, token=token)
        print('sale simple:', code, body)

    # Create sale for composite product
    if composite_id:
        sale = {'items': [{'productId': composite_id, 'quantity': 1}], 'total': 300}
        code, body = request('/api/sales', method='POST', data=sale, token=token)
        print('sale composite:', code, body)

if __name__ == '__main__':
    main()
