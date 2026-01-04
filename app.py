from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
CORS(app)
app.config['SECRET_KEY'] = 'simple-secret-key'

# Global storage
users = []
products = []
sales = []
expenses = []

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
    
    if not email or not password or not name:
        return jsonify({'error': 'Missing fields'}), 400
    
    if any(u['email'] == email for u in users):
        return jsonify({'error': 'User exists'}), 400
    
    user = {
        'id': len(users) + 1,
        'email': email,
        'password': password,
        'name': name,
        'role': 'admin' if len(users) == 0 else 'cashier',
        'plan': data.get('plan', 'trial'),
        'active': True,
        'locked': False
    }
    users.append(user)
    
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
        return jsonify(products)
    
    data = request.get_json()
    product = {
        'id': len(products) + 1,
        'name': data.get('name', ''),
        'price': float(data.get('price', 0)),
        'quantity': int(data.get('quantity', 0))
    }
    products.append(product)
    return jsonify(product)

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

if __name__ == '__main__':
    app.run(debug=True)