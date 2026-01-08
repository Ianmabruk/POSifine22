from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
import time
from datetime import datetime, timedelta
from functools import wraps
from flask_sock import Sock

app = Flask(__name__)

# Complete CORS fix
CORS(app, origins=['*'], methods=['*'], allow_headers=['*'])

# WebSocket (flask-sock)
sock = Sock(app)

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'ultra-pos-secret-2024')

# File-based storage - NO DATABASE REQUIRED
# Use /app/data on Render, or data/ locally
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
# Fallback to /app/data if directory doesn't exist locally
if not os.path.exists(DATA_DIR) and os.path.exists('/app'):
    DATA_DIR = '/app/data'

USERS_FILE = f'{DATA_DIR}/users.json'
PRODUCTS_FILE = f'{DATA_DIR}/products.json'
SALES_FILE = f'{DATA_DIR}/sales.json'
EXPENSES_FILE = f'{DATA_DIR}/expenses.json'
BATCHES_FILE = f'{DATA_DIR}/batches.json'
DISCOUNTS_FILE = f'{DATA_DIR}/discounts.json'
CREDIT_REQUESTS_FILE = f'{DATA_DIR}/credit_requests.json'
SETTINGS_FILE = f'{DATA_DIR}/settings.json'
REMINDERS_FILE = f'{DATA_DIR}/reminders.json'

# Ensure data directory exists and initialize empty JSON files
os.makedirs(DATA_DIR, exist_ok=True)

def init_json_file(filepath):
    """Initialize JSON file with empty array if it doesn't exist"""
    try:
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump([], f)
        # Verify file has valid JSON
        with open(filepath, 'r') as f:
            content = f.read().strip()
            if not content:
                with open(filepath, 'w') as fw:
                    json.dump([], fw)
    except Exception as e:
        print(f"Error initializing {filepath}: {e}")

# Initialize all data files on startup
for filepath in [USERS_FILE, PRODUCTS_FILE, SALES_FILE, EXPENSES_FILE, 
                 BATCHES_FILE, DISCOUNTS_FILE, CREDIT_REQUESTS_FILE, 
                 SETTINGS_FILE, REMINDERS_FILE]:
    init_json_file(filepath)

print(f"✅ Using file storage at: {DATA_DIR}")
print(f"✅ Data directory exists: {os.path.exists(DATA_DIR)}")
print(f"✅ Data files initialized")

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
        # Allow OPTIONS preflight requests without token
        if request.method == 'OPTIONS':
            return '', 200
        
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


@app.route('/api/auth/me', methods=['GET'])
@token_required
def me():
    """Return current user (without password)"""
    users = load_data(USERS_FILE)
    uid = request.user.get('id')
    user = next((u for u in users if u.get('id') == uid), None)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    return jsonify({k: v for k, v in user.items() if k != 'password'})


# Simple WebSocket endpoint for products updates
@sock.route('/api/ws/products')
def products_ws(ws):
    # Accept token as query param: ?token=...
    token = request.args.get('token', '')
    if not token:
        try:
            ws.send(json.dumps({'error': 'No token provided'}))
        except Exception:
            pass
        return

    try:
        jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    except Exception:
        try:
            ws.send(json.dumps({'error': 'Invalid token'}))
        except Exception:
            pass
        return

    # Send current products on connect, then send periodic heartbeats
    products = load_data(PRODUCTS_FILE)
    try:
        ws.send(json.dumps({'type': 'initial', 'products': products}))
        while True:
            time.sleep(10)
            try:
                ws.send(json.dumps({'type': 'heartbeat'}))
            except Exception:
                break
    except Exception:
        pass

@app.route('/')
def home():
    return jsonify({
        'message': 'POS API is running', 
        'storage': 'file-based',
        'status': 'healthy',
        'database': 'none'
    })

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body', 'message': 'Request body must be JSON'}), 400
        
        # Validate required fields
        required_fields = ['email', 'password', 'name']
        for field in required_fields:
            if field not in data or not data[field]:
                return jsonify({'error': f'Missing required field: {field}'}), 400
        
        users = load_data(USERS_FILE)
        
        # Check if user exists
        if any(u.get('email') == data['email'] for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        # Create user
        user = {
            'id': get_next_id(users),
            'email': data['email'],
            'password': data['password'],
            'name': data['name'],
            'role': 'admin' if data.get('plan') in ['1600', 'ultra'] else 'cashier',
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
    except Exception as e:
        import traceback
        error_msg = f"{str(e)} | {traceback.format_exc()}"
        print(f"Signup error: {error_msg}")
        return jsonify({'error': 'Signup failed', 'message': str(e), 'details': error_msg}), 500

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body', 'message': 'Request body must be JSON'}), 400
        
        # Validate required fields
        if 'email' not in data or not data['email']:
            return jsonify({'error': 'Missing required field: email'}), 400
        if 'password' not in data or not data['password']:
            return jsonify({'error': 'Missing required field: password'}), 400
        
        users = load_data(USERS_FILE)
        
        user = next((u for u in users if u.get('email') == data['email'] and u.get('password') == data['password']), None)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        token = jwt.encode({'id': user['id'], 'email': user['email'], 'role': user['role'], 'accountId': user['accountId']}, 
                          app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
    except Exception as e:
        import traceback
        error_msg = f"{str(e)} | {traceback.format_exc()}"
        print(f"Login error: {error_msg}")
        return jsonify({'error': 'Login failed', 'message': str(e), 'details': error_msg}), 500

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

@app.route('/api/stats', methods=['GET', 'OPTIONS'])
@token_required
def stats():
    if request.method == 'OPTIONS':
        return '', 200
    
    sales = load_data(SALES_FILE)
    products = load_data(PRODUCTS_FILE)
    
    total_sales = sum(s.get('total', 0) for s in sales)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': 0,
        'profit': total_sales,
        'productCount': len(products)
    })

@app.route('/api/reminders/today', methods=['GET', 'OPTIONS'])
@token_required
def reminders_today():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify([])

@app.route('/api/settings', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def settings():
    if request.method == 'OPTIONS':
        return '', 200
    
    if request.method == 'GET':
        return jsonify({
            'screenLockPassword': '2005',
            'businessName': 'My Business',
            'timezone': 'UTC'
        })
    
    data = request.get_json()
    return jsonify(data)

@app.route('/api/expenses', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def expenses():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify([])

@app.route('/api/batches', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def batches():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify([])

@app.route('/api/credit-requests', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def credit_requests():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify([])

@app.route('/api/discounts', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])
@token_required
def discounts_endpoint():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify([])

# 404 Error Handler
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint not found',
        'path': request.path,
        'method': request.method,
        'message': 'Please check the endpoint URL'
    }), 404

# 500 Error Handler
@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal server error',
        'message': str(error)
    }), 500

if __name__ == '__main__':
    app.run(debug=False, use_reloader=False, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))