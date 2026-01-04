from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'simple-secret-key'

# Global storage - shared across all users
users = []
products = []
sales = []
expenses = []
activities = []
settings = [{'screenLockPassword': 'admin123', 'businessName': 'My Business'}]

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

@app.route('/api/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    name = data.get('name', '')
    plan = data.get('plan', 'trial')
    
    if not email or not password or not name:
        return jsonify({'error': 'Missing fields'}), 400
    
    if any(u['email'] == email for u in users):
        return jsonify({'error': 'User exists'}), 400
    
    # Basic package restriction - only allow signup, redirect to cashier
    if plan == 'basic':
        role = 'cashier'
    else:
        role = 'admin' if len(users) == 0 or plan in ['ultra'] else 'cashier'
    
    user = {
        'id': len(users) + 1,
        'email': email,
        'password': password,
        'name': name,
        'role': role,
        'plan': plan,
        'active': True,
        'locked': False
    }
    users.append(user)
    
    # Log activity
    activities.append({
        'id': len(activities) + 1,
        'type': 'signup',
        'userId': user['id'],
        'email': email,
        'name': name,
        'plan': user['plan'],
        'timestamp': datetime.now().isoformat()
    })
    
    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role']}, 
                      app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email', '').lower()
    password = data.get('password', '')
    
    user = next((u for u in users if u['email'] == email and u['password'] == password), None)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Log activity
    activities.append({
        'id': len(activities) + 1,
        'type': 'login',
        'userId': user['id'],
        'email': user['email'],
        'name': user['name'],
        'plan': user.get('plan', 'trial'),
        'timestamp': datetime.now().isoformat()
    })
    
    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role']}, 
                      app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/me')
@token_required
def me():
    user = next((u for u in users if u['id'] == request.user['id']), None)
    if user:
        return jsonify({k: v for k, v in user.items() if k != 'password'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def handle_products():
    if request.method == 'GET':
        # Return ALL products for everyone - shared data
        return jsonify(products)
    
    data = request.get_json()
    product = {
        'id': len(products) + 1,
        'name': data.get('name', ''),
        'price': float(data.get('price', 0)),
        'quantity': int(data.get('quantity', 0)),
        'image': data.get('image', ''),
        'category': data.get('category', 'general'),
        'createdAt': datetime.now().isoformat(),
        'createdBy': request.user.get('id')  # Track who created it
    }
    products.append(product)
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_product(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        product.update({
            'name': data.get('name', product['name']),
            'price': float(data.get('price', product['price'])),
            'quantity': int(data.get('quantity', product['quantity'])),
            'image': data.get('image', product.get('image', '')),
            'category': data.get('category', product.get('category', 'general'))
        })
        return jsonify(product)
    
    if request.method == 'DELETE':
        products.remove(product)
        return '', 204

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    if request.method == 'GET':
        return jsonify(sales)
    
    data = request.get_json()
    sale = {
        'id': len(sales) + 1,
        'items': data.get('items', []),
        'total': float(data.get('total', 0)),
        'cashierId': request.user['id']
    }
    sales.append(sale)
    return jsonify(sale)

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def handle_expenses():
    if request.method == 'GET':
        return jsonify(expenses)
    
    data = request.get_json()
    expense = {
        'id': len(expenses) + 1,
        'description': data.get('description', ''),
        'amount': float(data.get('amount', 0))
    }
    expenses.append(expense)
    return jsonify(expense)

@app.route('/api/stats')
@token_required
def stats():
    total_sales = sum(s.get('total', 0) for s in sales)
    total_expenses = sum(e.get('amount', 0) for e in expenses)
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': total_expenses,
        'profit': total_sales - total_expenses,
        'productCount': len(products)
    })

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
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])

@app.route('/api/main-admin/activities')
@token_required
def main_admin_activities():
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    return jsonify(activities)

@app.route('/api/main-admin/stats')
@token_required
def main_admin_stats():
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    total_users = len(users)
    active_users = len([u for u in users if u.get('active', True)])
    total_sales = sum(s.get('total', 0) for s in sales)
    
    return jsonify({
        'totalUsers': total_users,
        'activeUsers': active_users,
        'totalSales': total_sales,
        'totalTransactions': len(sales)
    })

@app.route('/api/settings', methods=['GET', 'POST'])
@token_required
def handle_settings():
    if request.method == 'GET':
        return jsonify(settings[0] if settings else {})
    
    data = request.get_json()
    if settings:
        settings[0].update(data)
    else:
        settings.append(data)
    
    return jsonify(settings[0])

@app.route('/api/upload-image', methods=['POST'])
@token_required
def upload_image():
    data = request.get_json()
    image_data = data.get('image', '')
    
    # For demo purposes, just return the base64 data
    # In production, you'd upload to cloud storage
    return jsonify({
        'url': image_data,
        'success': True
    })

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    if request.method == 'GET':
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
    
    # Only ultra package admins can create users
    current_user = next((u for u in users if u['id'] == request.user.get('id')), None)
    if not current_user or current_user.get('role') != 'admin' or current_user.get('plan') != 'ultra':
        return jsonify({'error': 'Ultra package admin access required'}), 403
    
    data = request.get_json()
    user = {
        'id': len(users) + 1,
        'email': data.get('email', '').lower(),
        'password': data.get('password', 'changeme123'),
        'name': data.get('name', ''),
        'role': 'cashier',
        'plan': 'ultra',  # Inherit ultra plan from admin
        'active': True,
        'locked': False,
        'pin': data.get('pin', ''),
        'createdBy': request.user.get('id')  # Track who created this user
    }
    users.append(user)
    
    # Log activity
    activities.append({
        'id': len(activities) + 1,
        'type': 'user_created',
        'userId': user['id'],
        'email': user['email'],
        'name': user['name'],
        'plan': user['plan'],
        'createdBy': request.user.get('id'),
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({k: v for k, v in user.items() if k != 'password'})

if __name__ == '__main__':
    app.run(debug=True)