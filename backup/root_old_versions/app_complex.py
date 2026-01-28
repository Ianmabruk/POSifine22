from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app, origins="*")
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')

# Simple in-memory storage
DATA_STORE = {
    'users': [],
    'products': [],
    'sales': [],
    'expenses': [],
    'activities': []
}

def get_data(table):
    return DATA_STORE.get(table, [])

def save_data(table, data):
    DATA_STORE[table] = data
    return True

def add_data(table, item):
    items = get_data(table)
    item['id'] = len(items) + 1
    items.append(item)
    save_data(table, items)
    return item

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header[7:]
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
            
            if data.get('type') in ['main_admin', 'owner']:
                return f(*args, **kwargs)
            
            users = get_data('users')
            user = next((u for u in users if u['id'] == data.get('id')), None)
            
            if not user or user.get('locked', False):
                return jsonify({'error': 'User not found or locked'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        
        return f(*args, **kwargs)
    return decorated

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        name = data.get('name', '').strip()
        
        if not email or not password or not name:
            return jsonify({'error': 'Email, password, and name are required'}), 400
        
        users = get_data('users')
        if any(u['email'] == email for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        plan = data.get('plan', 'trial')
        user = {
            'email': email,
            'password': password,
            'name': name,
            'role': 'admin' if len(users) == 0 or plan in ['ultra', 'basic'] else 'cashier',
            'plan': plan,
            'active': True,
            'locked': False,
            'permissions': {},
            'createdAt': datetime.now().isoformat()
        }
        
        user = add_data('users', user)
        
        add_data('activities', {
            'type': 'signup',
            'userId': user['id'],
            'email': email,
            'name': name,
            'plan': plan,
            'timestamp': datetime.now().isoformat()
        })
        
        token = jwt.encode({
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Signup failed: {str(e)}'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        users = get_data('users')
        user = next((u for u in users if u['email'] == email and u['password'] == password), None)
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        if user.get('locked', False):
            return jsonify({'error': 'Account is locked'}), 403
        
        add_data('activities', {
            'type': 'login',
            'userId': user['id'],
            'email': user['email'],
            'name': user['name'],
            'plan': user.get('plan', 'trial'),
            'timestamp': datetime.now().isoformat()
        })
        
        token = jwt.encode({
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user():
    try:
        users = get_data('users')
        user = next((u for u in users if u['id'] == request.user.get('id')), None)
        
        if user:
            return jsonify({k: v for k, v in user.items() if k != 'password'})
        else:
            return jsonify({'error': 'User not found'}), 404
            
    except Exception as e:
        return jsonify({'error': f'Failed to get user: {str(e)}'}), 500

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def products():
    try:
        if request.method == 'GET':
            return jsonify(get_data('products'))
        
        data = request.get_json()
        if not data or not data.get('name'):
            return jsonify({'error': 'Product name is required'}), 400
        
        product = {
            'name': data['name'],
            'price': float(data.get('price', 0)),
            'quantity': int(data.get('quantity', 0)),
            'createdAt': datetime.now().isoformat()
        }
        
        product = add_data('products', product)
        return jsonify(product), 201
        
    except Exception as e:
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def sales():
    try:
        if request.method == 'GET':
            return jsonify(get_data('sales'))
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        sale = {
            'items': data.get('items', []),
            'total': float(data.get('total', 0)),
            'cashierId': request.user.get('id'),
            'createdAt': datetime.now().isoformat()
        }
        
        sale = add_data('sales', sale)
        return jsonify(sale), 201
        
    except Exception as e:
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def expenses():
    try:
        if request.method == 'GET':
            return jsonify(get_data('expenses'))
        
        data = request.get_json()
        if not data or not data.get('description'):
            return jsonify({'error': 'Description is required'}), 400
        
        expense = {
            'description': data['description'],
            'amount': float(data.get('amount', 0)),
            'createdAt': datetime.now().isoformat()
        }
        
        expense = add_data('expenses', expense)
        return jsonify(expense), 201
        
    except Exception as e:
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/stats', methods=['GET'])
@token_required
def get_stats():
    try:
        sales = get_data('sales')
        expenses = get_data('expenses')
        
        total_sales = sum(sale.get('total', 0) for sale in sales)
        total_expenses = sum(expense.get('amount', 0) for expense in expenses)
        profit = total_sales - total_expenses
        
        return jsonify({
            'totalSales': total_sales,
            'totalExpenses': total_expenses,
            'profit': profit,
            'productCount': len(get_data('products'))
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get statistics: {str(e)}'}), 500

@app.route('/api/main-admin/auth/login', methods=['POST'])
def main_admin_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if email == 'ianmabruk3@gmail.com' and password == 'mabruk2004':
            token = jwt.encode({
                'id': 'main_admin',
                'email': email,
                'type': 'main_admin',
                'role': 'main_admin'
            }, app.config['SECRET_KEY'], algorithm='HS256')
            
            return jsonify({
                'token': token,
                'user': {
                    'id': 'main_admin',
                    'email': email,
                    'name': 'Ian Mabruk',
                    'type': 'main_admin',
                    'role': 'main_admin'
                }
            })
        
        return jsonify({'error': 'Access denied. Owner access only.'}), 401
        
    except Exception as e:
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)