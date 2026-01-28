from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
from datetime import datetime, timedelta
from functools import wraps
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Complete CORS fix
CORS(app, origins=['*'], methods=['*'], allow_headers=['*'])

@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = '*'
    response.headers['Access-Control-Allow-Methods'] = '*'
    return response

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'ultra-pos-secret-2024')

# Environment detection
USE_DATABASE = os.environ.get('DATABASE_URL') is not None

if USE_DATABASE:
    try:
        import database as db
        db.init_db()
        logger.info("✅ Database initialized successfully")
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        logger.info("🔄 Falling back to file-based storage")
        USE_DATABASE = False

# File-based storage setup
if not USE_DATABASE:
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    USERS_FILE = f'{DATA_DIR}/users.json'
    PRODUCTS_FILE = f'{DATA_DIR}/products.json'
    SALES_FILE = f'{DATA_DIR}/sales.json'
    
    # Ensure data directory exists
    os.makedirs(DATA_DIR, exist_ok=True)
    logger.info("📁 Using file-based storage")

def load_data(filename):
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except:
        return []

def save_data(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

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
    storage_type = "Database" if USE_DATABASE else "File-based"
    return jsonify({
        'message': 'POS API is running',
        'storage': storage_type,
        'status': 'healthy'
    })

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok', 'storage': 'database' if USE_DATABASE else 'file'})

@app.route('/api/auth/signup', methods=['POST', 'OPTIONS'])
def signup():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    name = data.get('name', '')
    plan = data.get('plan', 'trial')
    
    if not email or not password or not name:
        return jsonify({'error': 'Missing required fields'}), 400
    
    if USE_DATABASE:
        # Database implementation
        if db.get_user_by_email(email):
            return jsonify({'error': 'User already exists'}), 400
        
        trial_ends_at = (datetime.now() + timedelta(days=30)).isoformat()
        account_id = db.create_account(email, plan, trial_ends_at)
        role = 'admin' if plan == 'ultra' else 'cashier'
        user_id = db.create_user(email, password, name, role, plan, account_id)
        db.create_activity('signup', user_id, email, name, plan)
        
        user = db.get_user_by_id(user_id)
        user_data = {k: v for k, v in user.items() if k != 'password'}
    else:
        # File-based implementation
        users = load_data(USERS_FILE)
        
        if any(u['email'] == email for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        user = {
            'id': get_next_id(users),
            'email': email,
            'password': password,
            'name': name,
            'role': 'admin' if plan == 'ultra' else 'cashier',
            'plan': plan,
            'accountId': get_next_id(users),
            'active': True,
            'createdAt': datetime.now().isoformat()
        }
        
        users.append(user)
        save_data(USERS_FILE, users)
        user_data = {k: v for k, v in user.items() if k != 'password'}
    
    token = jwt.encode({
        'id': user_data['id'], 
        'email': email, 
        'role': user_data['role'], 
        'accountId': user_data['accountId']
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': user_data
    })

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    
    if USE_DATABASE:
        user = db.get_user_by_email(email)
        if not user or user['password'] != password:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        account = db.get_account(user['accountId'])
        if account and account.get('isLocked'):
            return jsonify({'error': 'Account locked'}), 403
        
        db.create_activity('login', user['id'], user['email'], user['name'], user.get('plan', 'trial'))
        user_data = {k: v for k, v in user.items() if k != 'password'}
    else:
        users = load_data(USERS_FILE)
        user = next((u for u in users if u['email'] == email and u['password'] == password), None)
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        user_data = {k: v for k, v in user.items() if k != 'password'}
    
    token = jwt.encode({
        'id': user_data['id'], 
        'email': email, 
        'role': user_data['role'], 
        'accountId': user_data['accountId']
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': user_data
    })

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def handle_products():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        if USE_DATABASE:
            products = db.get_products_by_account(account_id)
        else:
            products = load_data(PRODUCTS_FILE)
            products = [p for p in products if p.get('accountId') == account_id]
        return jsonify(products)
    
    data = request.get_json()
    
    if USE_DATABASE:
        product_id = db.create_product(
            account_id=account_id,
            name=data.get('name', ''),
            price=float(data.get('price', 0)),
            cost=float(data.get('cost', 0)),
            quantity=int(data.get('quantity', 0)),
            image=data.get('image', ''),
            category=data.get('category', 'general'),
            unit=data.get('unit', 'pcs'),
            recipe=data.get('recipe', []),
            is_composite=bool(data.get('recipe', [])),
            created_by=request.user.get('id')
        )
        products = db.get_products_by_account(account_id)
        product = next((p for p in products if p['id'] == product_id), None)
    else:
        products = load_data(PRODUCTS_FILE)
        product = {
            'id': get_next_id(products),
            'name': data['name'],
            'price': float(data['price']),
            'quantity': int(data.get('quantity', 0)),
            'category': data.get('category', 'general'),
            'accountId': account_id,
            'createdAt': datetime.now().isoformat()
        }
        products.append(product)
        save_data(PRODUCTS_FILE, products)
    
    return jsonify(product)

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        if USE_DATABASE:
            sales = db.get_sales_by_account(account_id)
        else:
            sales = load_data(SALES_FILE)
            sales = [s for s in sales if s.get('accountId') == account_id]
        return jsonify(sales)
    
    data = request.get_json()
    
    if USE_DATABASE:
        user = db.get_user_by_id(request.user['id'])
        sale_id = db.create_sale(
            account_id=account_id,
            items=data.get('items', []),
            total=float(data.get('total', 0)),
            cashier_id=request.user['id'],
            cashier_name=user['name'] if user else 'Unknown'
        )
        sales = db.get_sales_by_account(account_id)
        sale = next((s for s in sales if s['id'] == sale_id), None)
    else:
        sales = load_data(SALES_FILE)
        sale = {
            'id': get_next_id(sales),
            'items': data['items'],
            'total': float(data['total']),
            'accountId': account_id,
            'cashierId': request.user['id'],
            'createdAt': datetime.now().isoformat()
        }
        sales.append(sale)
        save_data(SALES_FILE, sales)
    
    return jsonify(sale)

@app.route('/api/stats')
@token_required
def stats():
    account_id = request.user.get('accountId')
    
    if USE_DATABASE:
        sales = db.get_sales_by_account(account_id)
        products = db.get_products_by_account(account_id)
    else:
        sales = load_data(SALES_FILE)
        products = load_data(PRODUCTS_FILE)
        sales = [s for s in sales if s.get('accountId') == account_id]
        products = [p for p in products if p.get('accountId') == account_id]
    
    total_sales = sum(s.get('total', 0) for s in sales)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': 0,
        'profit': total_sales,
        'productCount': len(products)
    })

# Additional endpoints for compatibility
@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    if request.method == 'GET':
        if USE_DATABASE:
            account_id = request.user.get('accountId')
            users = db.get_users_by_account(account_id)
        else:
            users = load_data(USERS_FILE)
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
    
    return jsonify({'message': 'User creation not implemented in this version'})

@app.route('/api/expenses', methods=['GET'])
@token_required
def handle_expenses():
    return jsonify([])

@app.route('/api/reminders', methods=['GET'])
@token_required
def handle_reminders():
    return jsonify([])

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)