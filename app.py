from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
import database as db

app = Flask(__name__)

# Enhanced CORS configuration
CORS(app, 
     origins=['*'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
     allow_headers=['*'],
     supports_credentials=True)

# Add CORS headers to all responses
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', '*')
    response.headers.add('Access-Control-Allow-Methods', '*')
    return response

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')

# Initialize database
db.init_db()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
            
            # For main admin, skip user lookup
            if data.get('type') == 'main_admin':
                return f(*args, **kwargs)
            
        except:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/')
def home():
    return jsonify({'message': 'POS API is running'})

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

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
        return jsonify({'error': 'Missing fields'}), 400
    
    if db.get_user_by_email(email):
        return jsonify({'error': 'User exists'}), 400
    
    # Create account
    trial_ends_at = (datetime.now() + timedelta(days=30)).isoformat()
    account_id = db.create_account(email, plan, trial_ends_at)
    
    # Determine role based on plan
    role = 'admin' if plan in ['ultra', 'outer'] else 'cashier'
    
    # Create user
    user_id = db.create_user(email, password, name, role, plan, account_id)
    
    # Log activity
    db.create_activity('signup', user_id, email, name, plan)
    
    token = jwt.encode({
        'id': user_id, 
        'email': email, 
        'role': role, 
        'plan': plan,
        'package': plan,  # Add package field for compatibility
        'accountId': account_id
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    user = db.get_user_by_id(user_id)
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    
    user = db.get_user_by_email(email)
    if not user or user['password'] != password:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Check if account is locked
    account = db.get_account(user['accountId'])
    if account and account.get('isLocked'):
        return jsonify({'error': 'Account locked'}), 403
    
    # Log activity
    db.create_activity('login', user['id'], user['email'], user['name'], user.get('plan', 'trial'))
    
    token = jwt.encode({
        'id': user['id'], 
        'email': email, 
        'role': user['role'], 
        'plan': user.get('plan', 'trial'),
        'package': user.get('plan', 'trial'),  # Add package field for compatibility
        'accountId': user['accountId']
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/pin-login', methods=['POST', 'OPTIONS'])
def pin_login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    email = data.get('email', '').lower()
    pin = data.get('pin', '')
    
    if not pin or len(pin) != 4:
        return jsonify({'error': 'Invalid PIN format'}), 400
    
    user = db.get_user_by_email(email)
    if not user:
        return jsonify({'error': 'User not found'}), 401
    
    if not user.get('pin') or user['pin'] != pin:
        return jsonify({'error': 'Invalid PIN'}), 401
    
    # Check if account is locked
    account = db.get_account(user['accountId'])
    if account and account.get('isLocked'):
        return jsonify({'error': 'Account locked'}), 403
    
    # Log activity
    db.create_activity('pin_login', user['id'], user['email'], user['name'], user.get('plan', 'trial'))
    
    token = jwt.encode({
        'id': user['id'], 
        'email': email, 
        'role': user['role'], 
        'plan': user.get('plan', 'trial'),
        'package': user.get('plan', 'trial'),  # Add package field for compatibility
        'accountId': user['accountId']
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/me')
@token_required
def me():
    user = db.get_user_by_id(request.user['id'])
    if user:
        return jsonify({k: v for k, v in user.items() if k != 'password'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def handle_products():
    if request.method == 'GET':
        account_id = request.user.get('accountId')
        products = db.get_products_by_account(account_id)
        return jsonify(products)
    
    data = request.get_json()
    account_id = request.user.get('accountId')
    
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
    
    # Return created product
    products = db.get_products_by_account(account_id)
    product = next((p for p in products if p['id'] == product_id), None)
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_product(product_id):
    account_id = request.user.get('accountId')
    products = db.get_products_by_account(account_id)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        db.update_product(
            product_id,
            name=data.get('name', product['name']),
            price=float(data.get('price', product['price'])),
            quantity=int(data.get('quantity', product['quantity'])),
            image=data.get('image', product.get('image', '')),
            category=data.get('category', product.get('category', 'general'))
        )
        
        # Return updated product
        products = db.get_products_by_account(account_id)
        updated_product = next((p for p in products if p['id'] == product_id), None)
        return jsonify(updated_product)
    
    if request.method == 'DELETE':
        db.delete_product(product_id)
        return jsonify({'message': 'Product deleted successfully'}), 200

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        sales = db.get_sales_by_account(account_id)
        return jsonify(sales)
    
    data = request.get_json()
    
    # Process stock deduction
    products = db.get_products_by_account(account_id)
    for item in data.get('items', []):
        product = next((p for p in products if p['id'] == item['productId']), None)
        if product:
            new_quantity = max(0, product['quantity'] - item['quantity'])
            db.update_product(product['id'], quantity=new_quantity)
    
    # Create sale
    user = db.get_user_by_id(request.user['id'])
    sale_id = db.create_sale(
        account_id=account_id,
        items=data.get('items', []),
        total=float(data.get('total', 0)),
        cashier_id=request.user['id'],
        cashier_name=user['name'] if user else 'Unknown'
    )
    
    # Return created sale
    sales = db.get_sales_by_account(account_id)
    sale = next((s for s in sales if s['id'] == sale_id), None)
    return jsonify(sale)

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def handle_expenses():
    # Stub implementation
    return jsonify([])

@app.route('/api/stats')
@token_required
def stats():
    account_id = request.user.get('accountId')
    sales = db.get_sales_by_account(account_id)
    products = db.get_products_by_account(account_id)
    
    total_sales = sum(s.get('total', 0) for s in sales)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': 0,
        'profit': total_sales,
        'productCount': len(products)
    })

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    if request.method == 'GET':
        account_id = request.user.get('accountId')
        users = db.get_users_by_account(account_id)
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
    
    # POST - Create new user (cashier)
    current_user = db.get_user_by_id(request.user['id'])
    if not current_user:
        return jsonify({'error': 'Current user not found'}), 404
    
    # Only admins can create users
    if current_user['role'] != 'admin':
        return jsonify({'error': 'Only admins can create users'}), 403
    
    data = request.get_json()
    
    # Validate required fields
    if not data.get('email') or not data.get('name'):
        return jsonify({'error': 'Email and name are required'}), 400
    
    # Check if user already exists
    if db.get_user_by_email(data.get('email').lower()):
        return jsonify({'error': 'User with this email already exists'}), 400
    
    try:
        user_id = db.create_user(
            email=data.get('email', '').lower(),
            password=data.get('password', 'changeme123'),
            name=data.get('name', ''),
            role='cashier',  # Always create as cashier
            plan=current_user['plan'],  # Inherit plan from admin
            account_id=current_user['accountId'],
            pin=data.get('pin', ''),
            created_by=current_user['id']
        )
        
        # Log activity
        db.create_activity('user_created', user_id, data.get('email', ''), data.get('name', ''), current_user['plan'], current_user['id'])
        
        user = db.get_user_by_id(user_id)
        return jsonify({k: v for k, v in user.items() if k != 'password'})
        
    except Exception as e:
        print(f"Error creating user: {e}")
        return jsonify({'error': 'Failed to create user'}), 500

@app.route('/api/reminders', methods=['GET', 'POST'])
@token_required
def handle_reminders():
    return jsonify([])

@app.route('/api/reminders/<int:reminder_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_reminder(reminder_id):
    return jsonify({'message': 'Reminder updated'})

# MAIN ADMIN ENDPOINTS
@app.route('/api/main-admin/auth/login', methods=['POST'])
def main_admin_login():
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    
    if email == 'ianmabruk3@gmail.com' and password == 'admin123':
        token = jwt.encode({'id': 'admin', 'email': email, 'type': 'main_admin'}, 
                          app.config['SECRET_KEY'], algorithm='HS256')
        return jsonify({
            'token': token,
            'user': {'id': 'admin', 'email': email, 'name': 'Ian Mabruk', 'type': 'main_admin'}
        })
    
    return jsonify({'error': 'Access denied'}), 401

@app.route('/api/main-admin/users')
@token_required
def main_admin_users():
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    users = db.get_all_users()
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])

@app.route('/api/main-admin/activities')
@token_required
def main_admin_activities():
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    activities = db.get_all_activities()
    return jsonify(activities)

@app.route('/api/main-admin/stats')
@token_required
def main_admin_stats():
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    users = db.get_all_users()
    return jsonify({
        'totalUsers': len(users),
        'activeUsers': len([u for u in users if u.get('active', True)]),
        'totalSales': 0,
        'totalTransactions': 0
    })

@app.route('/api/settings', methods=['GET', 'POST'])
@token_required
def handle_settings():
    if request.method == 'GET':
        return jsonify(db.get_settings())
    
    data = request.get_json()
    db.update_settings(**data)
    return jsonify(db.get_settings())

# Stub endpoints
@app.route('/api/batches', methods=['GET', 'POST'])
def handle_batches():
    return jsonify([])

@app.route('/api/production', methods=['GET', 'POST'])
def handle_production():
    return jsonify([])

@app.route('/api/categories/generate-code', methods=['POST'])
def generate_category_code():
    return jsonify({'code': 'CAT001'})

@app.route('/api/price-history', methods=['GET', 'POST'])
def handle_price_history():
    return jsonify([])

@app.route('/api/service-fees', methods=['GET', 'POST'])
def handle_service_fees():
    return jsonify([])

@app.route('/api/service-fees/<int:fee_id>', methods=['PUT', 'DELETE'])
def handle_service_fee(fee_id):
    return jsonify({'message': 'Service fee updated'})

@app.route('/api/discounts', methods=['GET', 'POST'])
def handle_discounts():
    return jsonify([])

@app.route('/api/discounts/<int:discount_id>', methods=['PUT', 'DELETE'])
def handle_discount(discount_id):
    return jsonify({'message': 'Discount updated'})

@app.route('/api/credit-requests', methods=['GET', 'POST'])
def handle_credit_requests():
    return jsonify([])

@app.route('/api/credit-requests/<int:request_id>/approve', methods=['POST'])
def approve_credit_request(request_id):
    return jsonify({'message': 'Credit request approved'})

@app.route('/api/credit-requests/<int:request_id>/reject', methods=['POST'])
def reject_credit_request(request_id):
    return jsonify({'message': 'Credit request rejected'})

@app.route('/api/upload-image', methods=['POST'])
@token_required
def upload_image():
    data = request.get_json()
    return jsonify({'url': data.get('image', ''), 'success': True})

if __name__ == '__main__':
    app.run(debug=True)