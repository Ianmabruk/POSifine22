from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)

# Complete CORS fix
CORS(app, origins=['*'], methods=['*'], allow_headers=['*'])

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

app.config['SECRET_KEY'] = 'ultra-pos-secret-2024'

# File-based storage
DATA_DIR = '/tmp'
USERS_FILE = f'{DATA_DIR}/users.json'
PRODUCTS_FILE = f'{DATA_DIR}/products.json'
SALES_FILE = f'{DATA_DIR}/sales.json'

def load_data(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return []

def save_data(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f)

def get_next_id(data):
    return max([item.get('id', 0) for item in data] + [0]) + 1

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    return jsonify({'message': 'POS API is running'})

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    users = load_data(USERS_FILE)
    
    # Check if user exists
    if any(u['email'] == data['email'] for u in users):
        return jsonify({'error': 'User exists'}), 400
    
    # Create user
    user = {
        'id': get_next_id(users),
        'email': data['email'],
        'password': data['password'],
        'name': data['name'],
        'role': 'admin' if data.get('plan') == 'ultra' else 'cashier',
        'plan': data.get('plan', 'basic'),
        'accountId': get_next_id(users),
        'active': True,
        'createdAt': datetime.now().isoformat()
    }
    
    users.append(user)
    save_data(USERS_FILE, users)
    
    token = jwt.encode({'id': user['id'], 'email': user['email'], 'role': user['role'], 'accountId': user['accountId']}, 
                      app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    users = load_data(USERS_FILE)
    
    user = next((u for u in users if u['email'] == data['email'] and u['password'] == data['password']), None)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = jwt.encode({'id': user['id'], 'email': user['email'], 'role': user['role'], 'accountId': user['accountId']}, 
                      app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def handle_products():
    products = load_data(PRODUCTS_FILE)
    
    if request.method == 'GET':
        return jsonify(products)
    
    data = request.get_json()
    product = {
        'id': get_next_id(products),
        'name': data['name'],
        'price': float(data['price']),
        'quantity': int(data.get('quantity', 0)),
        'category': data.get('category', 'general'),
        'accountId': request.user['accountId'],
        'createdAt': datetime.now().isoformat()
    }
    
    products.append(product)
    save_data(PRODUCTS_FILE, products)
    
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_product(product_id):
    products = load_data(PRODUCTS_FILE)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        product.update(data)
        save_data(PRODUCTS_FILE, products)
        return jsonify(product)
    
    if request.method == 'DELETE':
        products = [p for p in products if p['id'] != product_id]
        save_data(PRODUCTS_FILE, products)
        return jsonify({'message': 'Product deleted'})

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    users = load_data(USERS_FILE)
    
    if request.method == 'GET':
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
    
    data = request.get_json()
    user = {
        'id': get_next_id(users),
        'email': data['email'],
        'password': data.get('password', 'changeme123'),
        'name': data['name'],
        'role': 'cashier',
        'plan': 'ultra',
        'accountId': request.user['accountId'],
        'pin': data.get('pin', '1234'),
        'active': True,
        'createdAt': datetime.now().isoformat()
    }
    
    users.append(user)
    save_data(USERS_FILE, users)
    
    return jsonify({k: v for k, v in user.items() if k != 'password'})

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    sales = load_data(SALES_FILE)
    
    if request.method == 'GET':
        return jsonify(sales)
    
    data = request.get_json()
    sale = {
        'id': get_next_id(sales),
        'items': data['items'],
        'total': float(data['total']),
        'accountId': request.user['accountId'],
        'cashierId': request.user['id'],
        'createdAt': datetime.now().isoformat()
    }
    
    sales.append(sale)
    save_data(SALES_FILE, sales)
    
    return jsonify(sale)

@app.route('/api/stats')
@token_required
def stats():
    sales = load_data(SALES_FILE)
    products = load_data(PRODUCTS_FILE)
    
    total_sales = sum(s.get('total', 0) for s in sales)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': 0,
        'profit': total_sales,
        'productCount': len(products)
    })

if __name__ == '__main__':
    app.run(debug=True)