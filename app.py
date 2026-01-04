from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
from datetime import datetime, timedelta
from functools import wraps
import threading
import time
from main_admin_endpoints import create_main_admin_routes

app = Flask(__name__)

# Enhanced CORS configuration for both localhost and Railway deployment
CORS(app, 
     resources={r"/api/*": {"origins": "*"}},
     methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With', 'Accept'],
     credentials=True)

app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')
app.config['JSON_SORT_KEYS'] = False

# Data directory setup
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# File lock for safe concurrent access
file_locks = {}
data_files = [
    'users.json', 'products.json', 'sales.json', 'expenses.json', 
    'settings.json', 'credit_requests.json', 'reminders.json',
    'service_fees.json', 'discounts.json', 'batches.json',
    'production.json', 'price_history.json', 'time_entries.json',
    'categories.json', 'payments.json', 'emails.json'
]

# Initialize file locks and data files
for filename in data_files:
    file_locks[filename] = threading.Lock()
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump([], f, indent=2)

# Add activities.json to track user activities
if 'activities.json' not in data_files:
    data_files.append('activities.json')
    file_locks['activities.json'] = threading.Lock()
    activities_path = os.path.join(DATA_DIR, 'activities.json')
    if not os.path.exists(activities_path):
        with open(activities_path, 'w') as f:
            json.dump([], f, indent=2)

def safe_load_json(filename):
    """Safely load JSON data with proper error handling"""
    path = os.path.join(DATA_DIR, filename)
    try:
        with file_locks[filename]:
            if os.path.exists(path):
                with open(path, 'r') as f:
                    return json.load(f)
            return []
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading {filename}: {e}")
        return []

def safe_save_json(filename, data):
    """Safely save JSON data with proper error handling"""
    path = os.path.join(DATA_DIR, filename)
    try:
        with file_locks[filename]:
            # Write to temporary file first, then rename (atomic operation)
            temp_path = path + '.tmp'
            with open(temp_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            os.rename(temp_path, path)
            return True
    except (IOError, OSError) as e:
        print(f"Error saving {filename}: {e}")
        return False

def token_required(f):
    """Enhanced token validation decorator with comprehensive error handling"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Try to get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header:
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]  # Remove 'Bearer ' prefix
            elif auth_header.startswith('Token '):
                token = auth_header[6:]  # Remove 'Token ' prefix
            else:
                token = auth_header
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        try:
            # Decode token with comprehensive error handling
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
            
            # Special handling for main_admin tokens
            if data.get('type') in ['main_admin', 'owner']:
                return f(*args, **kwargs)
            
            # Ensure user exists and is active
            users = safe_load_json('users.json')
            user = next((u for u in users if u['id'] == data.get('id')), None)
            
            if not user:
                return jsonify({'error': 'User not found'}), 401
            
            if not user.get('active', False):
                return jsonify({'error': 'Account is not active'}), 403
                
            if user.get('locked', False):
                return jsonify({'error': 'Account is locked'}), 403
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Invalid token'}), 401
        except Exception as e:
            return jsonify({'error': f'Token validation error: {str(e)}'}), 401
        
        return f(*args, **kwargs)
    return decorated

# ============================================================================
# AUTHENTICATION ENDPOINTS
# ============================================================================

@app.route('/api/auth/signup', methods=['POST'])
def signup():
    """User registration endpoint"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        # Validate required fields
        required_fields = ['email', 'password', 'name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.capitalize()} is required'}), 400
        
        email = data['email'].strip().lower()
        password = data['password']
        name = data['name'].strip()
        
        # Validate email format
        if '@' not in email or '.' not in email.split('@')[1]:
            return jsonify({'error': 'Invalid email format'}), 400
        
        # Validate password length
        if len(password) < 4:
            return jsonify({'error': 'Password must be at least 4 characters'}), 400
        
        users = safe_load_json('users.json')
        
        # Check if user already exists
        if any(u['email'] == email for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        # First user becomes admin, others become cashiers
        is_first_user = len(users) == 0
        plan = data.get('plan', 'trial')  # Default to trial instead of basic
        
        user = {
            'id': len(users) + 1,
            'email': email,
            'password': password,
            'name': name,
            'role': 'admin' if (is_first_user or plan in ['ultra', 'basic']) else 'cashier',
            'plan': plan,
            'price': 2400 if plan == 'ultra' else (1000 if plan == 'basic' else 0),
            'active': True,
            'locked': False,
            'pin': None,
            'permissions': {
                'viewSales': True,
                'viewInventory': True,
                'viewExpenses': plan == 'ultra',
                'manageProducts': plan == 'ultra'
            } if plan == 'basic' else {},
            'createdAt': datetime.now().isoformat(),
            'trialExpiry': (datetime.now() + timedelta(days=30)).isoformat() if plan == 'trial' else None
        }
        
        users.append(user)
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to save user data'}), 500
        
        # Log signup activity for main admin
        activities = safe_load_json('activities.json')
        activity = {
            'id': len(activities) + 1,
            'type': 'signup',
            'userId': user['id'],
            'email': email,
            'name': name,
            'plan': plan,
            'userAgent': request.headers.get('User-Agent', 'Unknown'),
            'ipAddress': request.remote_addr,
            'timestamp': datetime.now().isoformat()
        }
        activities.append(activity)
        safe_save_json('activities.json', activities)
        
        # Generate token
        token_data = {
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }
        token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        }), 201
        
    except Exception as e:
        print(f"Signup error: {e}")
        return jsonify({'error': f'Signup failed: {str(e)}'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    """User login endpoint with comprehensive error handling"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        users = safe_load_json('users.json')
        user = next((u for u in users if u['email'] == email and u['password'] == password), None)
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check account status
        if user.get('locked', False):
            return jsonify({'error': 'Account is locked. Contact administrator.'}), 403
        
        if not user.get('active', False):
            return jsonify({'error': 'Account is not active'}), 403
        
        # Log login activity for main admin
        activities = safe_load_json('activities.json')
        activity = {
            'id': len(activities) + 1,
            'type': 'login',
            'userId': user['id'],
            'email': user['email'],
            'name': user['name'],
            'plan': user.get('plan', 'trial'),
            'userAgent': request.headers.get('User-Agent', 'Unknown'),
            'ipAddress': request.remote_addr,
            'timestamp': datetime.now().isoformat()
        }
        activities.append(activity)
        safe_save_json('activities.json', activities)
        
        # Generate token with user information
        token_data = {
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }
        token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/auth/pin-login', methods=['POST'])
def pin_login():
    """PIN-based login endpoint for cashiers"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        pin = data.get('pin', '')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if not pin:
            return jsonify({'error': 'PIN is required'}), 400
        
        users = safe_load_json('users.json')
        user = next((u for u in users if u['email'] == email), None)
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if PIN is set
        if not user.get('pin'):
            return jsonify({'error': 'PIN not set for this user'}), 400
        
        # Verify PIN
        if user.get('pin') != pin:
            return jsonify({'error': 'Invalid PIN'}), 401
        
        # Check account status
        if user.get('locked', False):
            return jsonify({'error': 'Account is locked. Contact administrator.'}), 403
        
        if not user.get('active', False):
            return jsonify({'error': 'Account is not active'}), 403
        
        # Generate token with user information
        token_data = {
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }
        token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        print(f"PIN login error: {e}")
        return jsonify({'error': f'PIN login failed: {str(e)}'}), 500

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current user information"""
    try:
        users = safe_load_json('users.json')
        user = next((u for u in users if u['id'] == request.user.get('id')), None)
        
        if user:
            return jsonify({k: v for k, v in user.items() if k != 'password'})
        else:
            return jsonify({'error': 'User not found'}), 404
            
    except Exception as e:
        print(f"Get current user error: {e}")
        return jsonify({'error': f'Failed to get user: {str(e)}'}), 500

# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def users_list():
    """Get all users or create new user (admin only)"""
    try:
        if request.method == 'GET':
            # Check if user is admin
            if request.user.get('role') != 'admin':
                return jsonify({'error': 'Admin access required'}), 403
            
            users = safe_load_json('users.json')
            return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
        
        # POST - Admin creating cashier
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        # Validate required fields
        required_fields = ['email', 'name']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.capitalize()} is required'}), 400
        
        email = data['email'].strip().lower()
        name = data['name'].strip()
        
        users = safe_load_json('users.json')
        
        # Check if user already exists
        if any(u['email'] == email for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        # Create new cashier user
        user = {
            'id': len(users) + 1,
            'email': email,
            'password': data.get('password', 'changeme123'),  # Default password
            'name': name,
            'role': 'cashier',
            'plan': 'basic',
            'price': 900,
            'active': True,  # Always active
            'locked': False,
            'pin': None,
            'permissions': {
                'viewSales': True,
                'viewInventory': True,
                'viewExpenses': False,
                'manageProducts': False
            },
            'createdAt': datetime.now().isoformat()
        }
        
        users.append(user)
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to save user data'}), 500
        
        return jsonify({k: v for k, v in user.items() if k != 'password'}), 201
        
    except Exception as e:
        print(f"Users endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/users/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def user_detail(id):
    """Update or delete user"""
    try:
        users = safe_load_json('users.json')
        user = next((u for u in users if u['id'] == id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        if request.method == 'PUT':
            # Check permissions
            if request.user.get('id') != id and request.user.get('role') != 'admin':
                return jsonify({'error': 'Unauthorized'}), 403
            
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request data is required'}), 400
            
            # Update user fields (excluding protected fields)
            protected_fields = {'id', 'password'}
            for key, value in data.items():
                if key not in protected_fields:
                    user[key] = value
            
            if not safe_save_json('users.json', users):
                return jsonify({'error': 'Failed to save user data'}), 500
            
            # If role changed, generate new token
            if 'role' in data:
                new_token = jwt.encode({
                    'id': user['id'],
                    'email': user['email'],
                    'role': user['role']
                }, app.config['SECRET_KEY'], algorithm='HS256')
                
                return jsonify({
                    'token': new_token,
                    'user': {k: v for k, v in user.items() if k != 'password'}
                })
            
            return jsonify({k: v for k, v in user.items() if k != 'password'})
        
        # DELETE
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        users = [u for u in users if u['id'] != id]
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to delete user'}), 500
        
        return '', 204
        
    except Exception as e:
        print(f"User detail error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/users/<int:id>/set-pin', methods=['POST'])
@token_required
def set_user_pin(id):
    """Set PIN for a user (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        if not data or 'pin' not in data:
            return jsonify({'error': 'PIN is required'}), 400
        
        pin = data['pin']
        
        # Validate PIN (should be 4 digits)
        if not pin or len(str(pin)) != 4 or not str(pin).isdigit():
            return jsonify({'error': 'PIN must be exactly 4 digits'}), 400
        
        users = safe_load_json('users.json')
        user = next((u for u in users if u['id'] == id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Set the PIN
        user['pin'] = str(pin)
        
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to save PIN'}), 500
        
        return jsonify({
            'message': 'PIN set successfully',
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        print(f"Set PIN error: {e}")
        return jsonify({'error': f'Failed to set PIN: {str(e)}'}), 500

@app.route('/api/users/<int:id>/lock', methods=['POST'])
@token_required
def lock_user(id):
    """Lock/unlock a user (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        if not data or 'locked' not in data:
            return jsonify({'error': 'Locked status is required'}), 400
        
        locked = bool(data['locked'])
        
        users = safe_load_json('users.json')
        user = next((u for u in users if u['id'] == id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Update lock status
        user['locked'] = locked
        user['active'] = not locked  # If locked, make inactive
        
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to update user status'}), 500
        
        return jsonify({
            'message': f'User {"locked" if locked else "unlocked"} successfully',
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        print(f"Lock user error: {e}")
        return jsonify({'error': f'Failed to update user status: {str(e)}'}), 500

# ============================================================================
# PRODUCT ENDPOINTS
# ============================================================================

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def products():
    """Get all products or create new product"""
    try:
        if request.method == 'GET':
            products = safe_load_json('products.json')
            
            # Filter products based on user role
            if request.user.get('role') == 'cashier':
                # Cashiers only see products visible to them
                products = [p for p in products if not p.get('expenseOnly', False)]
            
            # Sort by creation date (newest first)
            products.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
            return jsonify(products)
        
        # POST - Create new product
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        # Validate required fields
        if not data.get('name'):
            return jsonify({'error': 'Product name is required'}), 400
        
        products = safe_load_json('products.json')
        
        product = {
            'id': len(products) + 1,
            'name': data['name'].strip(),
            'price': float(data.get('price', 0)),
            'cost': float(data.get('cost', 0)),
            'quantity': int(data.get('quantity', 0)),
            'unit': data.get('unit', 'pcs'),
            'category': data.get('category', 'raw'),
            'recipe': data.get('recipe', []),
            'expenseOnly': data.get('expenseOnly', False),
            'visibleToCashier': data.get('visibleToCashier', True),
            'createdAt': datetime.now().isoformat()
        }
        
        products.append(product)
        if not safe_save_json('products.json', products):
            return jsonify({'error': 'Failed to save product data'}), 500
        
        return jsonify(product), 201
        
    except Exception as e:
        print(f"Products endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/products/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def product_detail(id):
    """Update or delete product"""
    try:
        products = safe_load_json('products.json')
        product = next((p for p in products if p['id'] == id), None)
        
        if not product:
            return jsonify({'error': 'Product not found'}), 404
        
        if request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request data is required'}), 400
            
            # Update product fields (excluding protected fields)
            protected_fields = {'id'}
            for key, value in data.items():
                if key not in protected_fields:
                    if key in ['price', 'cost']:
                        product[key] = float(value)
                    elif key in ['quantity']:
                        product[key] = int(value)
                    else:
                        product[key] = value
            
            if not safe_save_json('products.json', products):
                return jsonify({'error': 'Failed to save product data'}), 500
            
            return jsonify(product)
        
        # DELETE
        products = [p for p in products if p['id'] != id]
        if not safe_save_json('products.json', products):
            return jsonify({'error': 'Failed to delete product'}), 500
        
        return '', 204
        
    except Exception as e:
        print(f"Product detail error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/products/<int:id>/max-producible', methods=['GET'])
@token_required
def max_producible(id):
    """Calculate maximum producible units for a product"""
    try:
        products = safe_load_json('products.json')
        product = next((p for p in products if p['id'] == id), None)
        
        if not product or not product.get('recipe'):
            return jsonify({'maxUnits': 0, 'limitingIngredient': None})
        
        max_units = float('inf')
        limiting = None
        
        for ingredient in product['recipe']:
            raw = next((p for p in products if p['id'] == ingredient['productId']), None)
            if raw:
                available = raw.get('quantity', 0)
                needed = ingredient['quantity']
                possible = available / needed if needed > 0 else 0
                if possible < max_units:
                    max_units = possible
                    limiting = raw['name']
        
        return jsonify({
            'maxUnits': int(max_units) if max_units != float('inf') else 0,
            'limitingIngredient': limiting
        })
        
    except Exception as e:
        print(f"Max producible error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# SALES ENDPOINTS
# ============================================================================

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def sales():
    """Get all sales or create new sale"""
    try:
        if request.method == 'GET':
            sales = safe_load_json('sales.json')
            return jsonify(sales)
        
        # POST - Create new sale
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        batches = safe_load_json('batches.json')
        expenses = safe_load_json('expenses.json')
        
        total_cogs = 0
        
        # Process each item sold using FIFO from batches
        for item in data.get('items', []):
            product_id = item['productId']
            quantity_sold = item['quantity']
            
            # Get batches for this product (FIFO - oldest first)
            product_batches = [b for b in batches if b.get('productId') == product_id and b.get('quantity', 0) > 0]
            product_batches.sort(key=lambda x: x.get('createdAt', ''))
            
            remaining_qty = quantity_sold
            
            # Deduct from batches using FIFO
            for batch in product_batches:
                if remaining_qty <= 0:
                    break
                
                available = batch.get('quantity', 0)
                take_from_batch = min(remaining_qty, available)
                
                # Calculate COGS from this batch
                batch_cost = batch.get('cost', 0)
                total_cogs += batch_cost * take_from_batch
                
                # Update batch quantity
                batch['quantity'] = available - take_from_batch
                remaining_qty -= take_from_batch
        
        # Save updated batches
        if not safe_save_json('batches.json', batches):
            return jsonify({'error': 'Failed to update inventory'}), 500
        
        # Create sale record
        sales_list = safe_load_json('sales.json')
        sale = {
            'id': len(sales_list) + 1,
            'items': data['items'],
            'total': data['total'],
            'cogs': total_cogs,
            'profit': data['total'] - total_cogs,
            'paymentMethod': data.get('paymentMethod', 'cash'),
            'cashierId': request.user.get('id'),
            'cashierName': next((u['name'] for u in safe_load_json('users.json') if u['id'] == request.user.get('id')), 'Unknown'),
            'createdAt': datetime.now().isoformat()
        }
        
        sales_list.append(sale)
        if not safe_save_json('sales.json', sales_list):
            return jsonify({'error': 'Failed to save sale data'}), 500
        
        return jsonify(sale), 201
        
    except Exception as e:
        print(f"Sales endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# EXPENSES ENDPOINTS
# ============================================================================

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def expenses():
    """Get all expenses or create new expense"""
    try:
        if request.method == 'GET':
            expenses = safe_load_json('expenses.json')
            return jsonify(expenses)
        
        # POST - Create new expense
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        if not data.get('description'):
            return jsonify({'error': 'Expense description is required'}), 400
        
        if not data.get('amount'):
            return jsonify({'error': 'Expense amount is required'}), 400
        
        expenses = safe_load_json('expenses.json')
        
        expense = {
            'id': len(expenses) + 1,
            'description': data['description'].strip(),
            'amount': float(data['amount']),
            'category': data.get('category', 'general'),
            'automatic': False,
            'createdAt': datetime.now().isoformat()
        }
        
        expenses.append(expense)
        if not safe_save_json('expenses.json', expenses):
            return jsonify({'error': 'Failed to save expense data'}), 500
        
        return jsonify(expense), 201
        
    except Exception as e:
        print(f"Expenses endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# SETTINGS ENDPOINTS
# ============================================================================

@app.route('/api/settings', methods=['GET', 'POST'])
@token_required
def settings():
    """Get or update settings"""
    try:
        if request.method == 'GET':
            settings = safe_load_json('settings.json')
            return jsonify(settings[0] if settings else {})
        
        # POST - Update settings
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        settings = safe_load_json('settings.json')
        if settings:
            settings[0].update(data)
        else:
            settings = [data]
        
        if not safe_save_json('settings.json', settings):
            return jsonify({'error': 'Failed to save settings'}), 500
        
        return jsonify(settings[0])
        
    except Exception as e:
        print(f"Settings endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# BATCHES ENDPOINTS
# ============================================================================

@app.route('/api/batches', methods=['GET', 'POST'])
@token_required
def batches_endpoint():
    """Get all batches or create new batch"""
    try:
        if request.method == 'GET':
            product_id = request.args.get('productId')
            batches = safe_load_json('batches.json')
            
            if product_id:
                batches = [b for b in batches if b.get('productId') == int(product_id)]
            
            return jsonify(batches)
        
        # POST - Create new batch
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        required_fields = ['productId', 'quantity']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        batches = safe_load_json('batches.json')
        
        batch = {
            'id': len(batches) + 1,
            'productId': int(data['productId']),
            'quantity': int(data['quantity']),
            'originalQuantity': int(data['quantity']),
            'expiryDate': data.get('expiryDate'),
            'batchNumber': data.get('batchNumber', f'BATCH-{len(batches) + 1}-{int(time.time())}'),
            'cost': float(data.get('cost', 0)),
            'createdAt': datetime.now().isoformat()
        }
        
        batches.append(batch)
        if not safe_save_json('batches.json', batches):
            return jsonify({'error': 'Failed to save batch data'}), 500
        
        return jsonify(batch), 201
        
    except Exception as e:
        print(f"Batches endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/batches/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def batch_detail(id):
    """Update or delete batch"""
    try:
        batches = safe_load_json('batches.json')
        batch = next((b for b in batches if b['id'] == id), None)
        
        if not batch:
            return jsonify({'error': 'Batch not found'}), 404
        
        if request.method == 'PUT':
            data = request.get_json()
            if not data:
                return jsonify({'error': 'Request data is required'}), 400
            
            # Update batch fields (excluding protected fields)
            protected_fields = {'id', 'createdAt'}
            for key, value in data.items():
                if key not in protected_fields:
                    if key in ['quantity', 'originalQuantity', 'productId']:
                        batch[key] = int(value)
                    elif key in ['cost']:
                        batch[key] = float(value)
                    else:
                        batch[key] = value
            
            if not safe_save_json('batches.json', batches):
                return jsonify({'error': 'Failed to save batch data'}), 500
            
            return jsonify(batch)
        
        # DELETE
        batches = [b for b in batches if b['id'] != id]
        if not safe_save_json('batches.json', batches):
            return jsonify({'error': 'Failed to delete batch'}), 500
        
        return '', 204
        
    except Exception as e:
        print(f"Batch detail error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@app.route('/api/stats', methods=['GET'])
@token_required
def get_stats():
    """Get dashboard statistics"""
    try:
        sales = safe_load_json('sales.json')
        expenses = safe_load_json('expenses.json')
        products = safe_load_json('products.json')
        
        # Calculate totals
        total_sales = sum(sale.get('total', 0) for sale in sales)
        total_expenses = sum(expense.get('amount', 0) for expense in expenses)
        total_cogs = sum(sale.get('cogs', 0) for sale in sales)
        gross_profit = total_sales - total_cogs
        net_profit = gross_profit - total_expenses
        
        # Calculate daily sales (today)
        today = datetime.now().date()
        daily_sales = sum(
            sale.get('total', 0) for sale in sales 
            if sale.get('createdAt') and datetime.fromisoformat(sale['createdAt']).date() == today
        )
        
        # Calculate weekly sales (last 7 days)
        week_ago = today - timedelta(days=7)
        weekly_sales = sum(
            sale.get('total', 0) for sale in sales 
            if sale.get('createdAt') and datetime.fromisoformat(sale['createdAt']).date() >= week_ago
        )
        
        # Count products
        product_count = len(products)
        
        return jsonify({
            'totalSales': total_sales,
            'totalExpenses': total_expenses,
            'totalCOGS': total_cogs,
            'grossProfit': gross_profit,
            'netProfit': net_profit,
            'profit': net_profit,  # Legacy field
            'dailySales': daily_sales,
            'weeklySales': weekly_sales,
            'productCount': product_count
        })
        
    except Exception as e:
        print(f"Stats endpoint error: {e}")
        return jsonify({'error': f'Failed to get statistics: {str(e)}'}), 500

# ============================================================================
# ADDITIONAL ENDPOINTS (Supporting existing functionality)
# ============================================================================

@app.route('/api/credit-requests', methods=['GET', 'POST'])
@token_required
def credit_requests():
    """Get all credit requests or create new credit request"""
    try:
        if request.method == 'GET':
            requests = safe_load_json('credit_requests.json')
            return jsonify(requests)
        
        # POST - Create new credit request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        required_fields = ['productId', 'quantity', 'customerName', 'amount']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.capitalize()} is required'}), 400
        
        requests = safe_load_json('credit_requests.json')
        credit_request = {
            'id': len(requests) + 1,
            'productId': data['productId'],
            'quantity': data['quantity'],
            'customerName': data['customerName'].strip(),
            'amount': data['amount'],
            'cashierId': request.user.get('id'),
            'status': 'pending',
            'createdAt': datetime.now().isoformat()
        }
        
        requests.append(credit_request)
        if not safe_save_json('credit_requests.json', requests):
            return jsonify({'error': 'Failed to save credit request'}), 500
        
        return jsonify(credit_request), 201
        
    except Exception as e:
        print(f"Credit requests error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/credit-requests/<int:id>/approve', methods=['POST'])
@token_required
def approve_credit(id):
    """Approve credit request (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        requests = safe_load_json('credit_requests.json')
        credit_request = next((r for r in requests if r['id'] == id), None)
        
        if not credit_request:
            return jsonify({'error': 'Request not found'}), 404
        
        credit_request['status'] = 'approved'
        credit_request['approvedAt'] = datetime.now().isoformat()
        
        if not safe_save_json('credit_requests.json', requests):
            return jsonify({'error': 'Failed to update request'}), 500
        
        return jsonify(credit_request)
        
    except Exception as e:
        print(f"Approve credit error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/credit-requests/<int:id>/reject', methods=['POST'])
@token_required
def reject_credit(id):
    """Reject credit request (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        requests = safe_load_json('credit_requests.json')
        credit_request = next((r for r in requests if r['id'] == id), None)
        
        if not credit_request:
            return jsonify({'error': 'Request not found'}), 404
        
        credit_request['status'] = 'rejected'
        if not safe_save_json('credit_requests.json', requests):
            return jsonify({'error': 'Failed to update request'}), 500
        
        return jsonify(credit_request)
        
    except Exception as e:
        print(f"Reject credit error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/users/give-access', methods=['POST'])
@token_required
def give_access():
    """Give access to a user by email (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        data = request.get_json()
        if not data or not data.get('email'):
            return jsonify({'error': 'Email is required'}), 400
        
        email = data['email'].strip().lower()
        users = safe_load_json('users.json')
        user = next((u for u in users if u['email'] == email), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Activate user
        user['active'] = True
        user['locked'] = False
        
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to update user'}), 500
        
        return jsonify({'message': 'Access granted successfully'})
        
    except Exception as e:
        print(f"Give access error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/signup-with-payment', methods=['POST'])
def signup_with_payment():
    """Create user account with payment in single transaction"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        # Validate required fields
        required_fields = ['email', 'name', 'plan', 'amount']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.capitalize()} is required'}), 400
        
        email = data['email'].strip().lower()
        name = data['name'].strip()
        plan = data['plan']
        amount = float(data['amount'])
        
        # Check if user already exists
        users = safe_load_json('users.json')
        if any(u['email'] == email for u in users):
            return jsonify({'error': 'User already exists'}), 400
        
        # Create user
        user = {
            'id': len(users) + 1,
            'email': email,
            'password': data.get('password', 'changeme123'),
            'name': name,
            'role': 'admin',  # First user is always admin for their account
            'plan': plan,
            'active': True,
            'locked': False,
            'pin': None,
            'permissions': {},
            'createdAt': datetime.now().isoformat()
        }
        
        users.append(user)
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to save user'}), 500
        
        # Create payment record
        payments = safe_load_json('payments.json')
        payment = {
            'id': len(payments) + 1,
            'userId': user['id'],
            'email': email,
            'fullName': name,
            'plan': plan,
            'amount': amount,
            'method': data.get('paymentMethod', 'card'),
            'accountNumber': data.get('accountNumber', ''),
            'status': 'approved',
            'createdAt': datetime.now().isoformat(),
            'approvedAt': datetime.now().isoformat()
        }
        
        payments.append(payment)
        if not safe_save_json('payments.json', payments):
            return jsonify({'error': 'Failed to save payment'}), 500
        
        # Generate token
        token = jwt.encode({
            'id': user['id'],
            'email': user['email'],
            'role': user['role']
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password'},
            'payment': payment
        }), 201
        
    except Exception as e:
        print(f"Signup with payment error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/payments', methods=['GET'])
@token_required
def get_payments():
    """Get all payments (admin only)"""
    try:
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        payments = safe_load_json('payments.json')
        return jsonify(payments)
        
    except Exception as e:
        print(f"Get payments error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/demo-requests', methods=['GET', 'POST'])
def demo_requests():
    """Get all demo requests or create new demo request"""
    try:
        if request.method == 'GET':
            # Require admin token for GET
            auth_header = request.headers.get('Authorization')
            if auth_header:
                try:
                    token = auth_header.replace('Bearer ', '')
                    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
                    if data.get('role') != 'admin':
                        return jsonify({'error': 'Admin access required'}), 403
                except:
                    return jsonify({'error': 'Invalid token'}), 401
            else:
                return jsonify({'error': 'Token required'}), 401
            
            requests = safe_load_json('emails.json')  # Using emails.json for demo requests
            return jsonify([r for r in requests if r.get('type') == 'demo'])
        
        # POST - Create new demo request (no auth required)
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        required_fields = ['name', 'email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field.capitalize()} is required'}), 400
        
        requests = safe_load_json('emails.json')
        demo_request = {
            'id': len(requests) + 1,
            'type': 'demo',
            'name': data['name'].strip(),
            'email': data['email'].strip(),
            'company': data.get('company', '').strip(),
            'status': 'pending',
            'createdAt': datetime.now().isoformat()
        }
        
        requests.append(demo_request)
        if not safe_save_json('emails.json', requests):
            return jsonify({'error': 'Failed to save demo request'}), 500
        
        return jsonify(demo_request), 201
        
    except Exception as e:
        print(f"Demo requests error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# MAIN ADMIN ENDPOINTS (SUPER ADMIN)
# ============================================================================

@app.route('/api/main-admin/auth/login', methods=['POST'])
def main_admin_login():
    """Main admin login endpoint - Only ianmabruk3@gmail.com allowed"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400
        
        # Only allow ianmabruk3@gmail.com with password admin123
        if email == 'ianmabruk3@gmail.com' and password == 'admin123':
            token_data = {
                'id': 'main_admin',
                'email': email,
                'type': 'main_admin',
                'role': 'main_admin'
            }
            token = jwt.encode(token_data, app.config['SECRET_KEY'], algorithm='HS256')
            
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
        print(f"Main admin login error: {e}")
        return jsonify({'error': f'Login failed: {str(e)}'}), 500

@app.route('/api/main-admin/companies', methods=['GET'])
@token_required
def get_all_companies():
    """Get all companies with stats (owner only)"""
    try:
        if request.user.get('type') != 'owner':
            return jsonify({'error': 'Owner access required'}), 403
        
        users = safe_load_json('users.json')
        sales = safe_load_json('sales.json')
        
        # Group users by email domain to simulate companies
        companies_data = {}
        
        for user in users:
            # Use email as company identifier for now
            company_key = user['email']
            
            if company_key not in companies_data:
                companies_data[company_key] = {
                    'id': user['id'],
                    'name': f"{user['name']}'s Business",
                    'email': user['email'],
                    'plan': user.get('plan', 'basic'),
                    'active': user.get('active', True),
                    'locked': user.get('locked', False),
                    'role': user.get('role', 'cashier'),
                    'users': [],
                    'totalSales': 0,
                    'transactionCount': 0,
                    'createdAt': user.get('createdAt'),
                    'trialExpiry': None,
                    'lastActivity': user.get('createdAt')
                }
            
            companies_data[company_key]['users'].append({
                'id': user['id'],
                'name': user['name'],
                'email': user['email'],
                'role': user['role'],
                'active': user.get('active', True),
                'locked': user.get('locked', False)
            })
        
        # Calculate sales per company
        for sale in sales:
            cashier_id = sale.get('cashierId')
            if cashier_id:
                cashier = next((u for u in users if u['id'] == cashier_id), None)
                if cashier:
                    company_key = cashier['email']
                    if company_key in companies_data:
                        companies_data[company_key]['totalSales'] += sale.get('total', 0)
                        companies_data[company_key]['transactionCount'] += 1
                        companies_data[company_key]['lastActivity'] = sale.get('createdAt')
        
        return jsonify(list(companies_data.values()))
        
    except Exception as e:
        print(f"Get companies error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/main-admin/stats', methods=['GET'])
@token_required
def get_main_admin_stats():
    """Get global statistics for main admin"""
    try:
        if request.user.get('type') not in ['main_admin', 'owner']:
            return jsonify({'error': 'Main admin access required'}), 403
        
        users = safe_load_json('users.json')
        sales = safe_load_json('sales.json')
        payments = safe_load_json('payments.json')
        
        # Calculate user stats
        total_users = len(users)
        active_users = len([u for u in users if u.get('active', True)])
        locked_users = len([u for u in users if u.get('locked', False)])
        trial_users = len([u for u in users if not u.get('plan') or u.get('plan') == 'trial'])
        
        # Plan distribution
        plan_counts = {'basic': 0, 'ultra': 0, 'trial': 0}
        for user in users:
            plan = user.get('plan', 'trial')
            if plan in plan_counts:
                plan_counts[plan] += 1
            elif not plan:
                plan_counts['trial'] += 1
        
        # Sales stats
        total_sales = sum(sale.get('total', 0) for sale in sales)
        total_transactions = len(sales)
        
        # Payment stats
        total_revenue = sum(p.get('amount', 0) for p in payments if p.get('status') == 'approved')
        pending_payments = len([p for p in payments if p.get('status') == 'pending'])
        
        # Calculate MRR (Monthly Recurring Revenue)
        mrr = (plan_counts['basic'] * 1000) + (plan_counts['ultra'] * 2400)
        
        return jsonify({
            'totalUsers': total_users,
            'activeUsers': active_users,
            'lockedUsers': locked_users,
            'trialUsers': trial_users,
            'planDistribution': plan_counts,
            'totalSales': total_sales,
            'totalTransactions': total_transactions,
            'totalRevenue': total_revenue,
            'pendingPayments': pending_payments,
            'mrr': mrr
        })
        
    except Exception as e:
        print(f"Get main admin stats error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500



@app.route('/api/main-admin/activities', methods=['GET'])
@token_required
def get_activities():
    """Get all user activities for main admin"""
    try:
        if request.user.get('type') not in ['main_admin', 'owner']:
            return jsonify({'error': 'Main admin access required'}), 403
        
        activities = safe_load_json('activities.json')
        # Sort by timestamp (newest first)
        activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify(activities)
        
    except Exception as e:
        print(f"Get activities error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500
@app.route('/api/main-admin/users', methods=['GET'])
@token_required
def main_admin_get_users():
    """Get all users for main admin"""
    try:
        if request.user.get('type') not in ['main_admin', 'owner']:
            return jsonify({'error': 'Main admin access required'}), 403
        
        users = safe_load_json('users.json')
        # Add trial status calculation
        for user in users:
            if user.get('plan') == 'trial' or not user.get('plan'):
                user['isFreeTrial'] = True
                if user.get('trialExpiry'):
                    try:
                        expiry = datetime.fromisoformat(user['trialExpiry'])
                        user['trialDaysLeft'] = max(0, (expiry - datetime.now()).days)
                    except:
                        user['trialDaysLeft'] = 0
                else:
                    user['trialDaysLeft'] = 30  # Default trial period
            else:
                user['isFreeTrial'] = False
                user['trialDaysLeft'] = 0
        
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
        
    except Exception as e:
        print(f"Main admin get users error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/main-admin/payments', methods=['GET'])
@token_required
def main_admin_get_payments():
    """Get all payments for main admin"""
    try:
        if request.user.get('type') != 'main_admin':
            return jsonify({'error': 'Main admin access required'}), 403
        
        payments = safe_load_json('payments.json')
        return jsonify(payments)
        
    except Exception as e:
        print(f"Main admin get payments error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST'])
@token_required
def main_admin_lock_user(user_id):
    """Lock/unlock user by main admin"""
    try:
        if request.user.get('type') not in ['main_admin', 'owner']:
            return jsonify({'error': 'Main admin access required'}), 403
        
        data = request.get_json()
        if not data or 'locked' not in data:
            return jsonify({'error': 'Locked status is required'}), 400
        
        locked = bool(data['locked'])
        
        users = safe_load_json('users.json')
        user = next((u for u in users if u['id'] == user_id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user['locked'] = locked
        user['active'] = not locked
        
        if not safe_save_json('users.json', users):
            return jsonify({'error': 'Failed to update user status'}), 500
        
        return jsonify({
            'message': f'User {"locked" if locked else "unlocked"} successfully',
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
        
    except Exception as e:
        print(f"Owner lock user error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/main-admin/system/reset', methods=['POST'])
@token_required
def system_reset():
    """Reset system data (owner only)"""
    try:
        if request.user.get('type') != 'owner':
            return jsonify({'error': 'Owner access required'}), 403
        
        data = request.get_json()
        reset_type = data.get('type', 'all')
        
        if reset_type == 'sales':
            if not safe_save_json('sales.json', []):
                return jsonify({'error': 'Failed to reset sales'}), 500
        elif reset_type == 'products':
            if not safe_save_json('products.json', []):
                return jsonify({'error': 'Failed to reset products'}), 500
        elif reset_type == 'all':
            # Reset all data except users and settings
            files_to_reset = ['sales.json', 'products.json', 'expenses.json', 'batches.json', 'production.json']
            for filename in files_to_reset:
                if not safe_save_json(filename, []):
                    return jsonify({'error': f'Failed to reset {filename}'}), 500
        
        return jsonify({'message': f'System {reset_type} data reset successfully'})
        
    except Exception as e:
        print(f"System reset error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/main-admin/demo-requests', methods=['GET', 'POST'])
@token_required
def manage_demo_requests():
    """Manage demo requests (owner only)"""
    try:
        if request.method == 'GET':
            if request.user.get('type') != 'owner':
                return jsonify({'error': 'Owner access required'}), 403
            
            requests = safe_load_json('demo_requests.json')
            return jsonify(requests)
        
        # POST - Approve demo request
        if request.user.get('type') != 'owner':
            return jsonify({'error': 'Owner access required'}), 403
        
        data = request.get_json()
        request_id = data.get('requestId')
        action = data.get('action')  # 'approve' or 'reject'
        
        requests = safe_load_json('demo_requests.json')
        demo_request = next((r for r in requests if r['id'] == request_id), None)
        
        if not demo_request:
            return jsonify({'error': 'Demo request not found'}), 404
        
        demo_request['status'] = action
        demo_request['processedAt'] = datetime.now().isoformat()
        
        if not safe_save_json('demo_requests.json', requests):
            return jsonify({'error': 'Failed to update demo request'}), 500
        
        return jsonify(demo_request)
        
    except Exception as e:
        print(f"Demo requests error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# CUSTOMER CREDIT SYSTEM (ULTRA FEATURE)
# ============================================================================

@app.route('/api/customers', methods=['GET', 'POST'])
@token_required
def customers():
    """Get all customers or create new customer"""
    try:
        if request.method == 'GET':
            customers = safe_load_json('customers.json')
            return jsonify(customers)
        
        # POST - Create new customer (Ultra plan only)
        user_plan = request.user.get('plan', 'basic')
        if user_plan != 'ultra':
            return jsonify({'error': 'Customer management requires Ultra plan'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        required_fields = ['name', 'email']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'error': f'{field} is required'}), 400
        
        customers = safe_load_json('customers.json')
        
        customer = {
            'id': len(customers) + 1,
            'name': data['name'].strip(),
            'email': data['email'].strip().lower(),
            'phone': data.get('phone', ''),
            'creditBalance': float(data.get('creditBalance', 0)),
            'companyId': request.user.get('companyId', 'default'),
            'active': True,
            'createdAt': datetime.now().isoformat()
        }
        
        customers.append(customer)
        if not safe_save_json('customers.json', customers):
            return jsonify({'error': 'Failed to save customer data'}), 500
        
        return jsonify(customer), 201
        
    except Exception as e:
        print(f"Customers endpoint error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/customers/<int:customer_id>/credit', methods=['POST'])
@token_required
def add_customer_credit(customer_id):
    """Add credit to customer account (Ultra plan only)"""
    try:
        user_plan = request.user.get('plan', 'basic')
        if user_plan != 'ultra':
            return jsonify({'error': 'Customer credit requires Ultra plan'}), 403
        
        data = request.get_json()
        if not data or 'amount' not in data:
            return jsonify({'error': 'Amount is required'}), 400
        
        amount = float(data['amount'])
        if amount <= 0:
            return jsonify({'error': 'Amount must be positive'}), 400
        
        customers = safe_load_json('customers.json')
        customer = next((c for c in customers if c['id'] == customer_id), None)
        
        if not customer:
            return jsonify({'error': 'Customer not found'}), 404
        
        # Update credit balance
        customer['creditBalance'] = customer.get('creditBalance', 0) + amount
        
        # Log credit transaction
        credit_logs = safe_load_json('credit_logs.json')
        credit_log = {
            'id': len(credit_logs) + 1,
            'customerId': customer_id,
            'type': 'credit_added',
            'amount': amount,
            'balance': customer['creditBalance'],
            'description': data.get('description', 'Credit added'),
            'addedBy': request.user.get('id'),
            'createdAt': datetime.now().isoformat()
        }
        credit_logs.append(credit_log)
        
        if not safe_save_json('customers.json', customers):
            return jsonify({'error': 'Failed to update customer'}), 500
        
        if not safe_save_json('credit_logs.json', credit_logs):
            return jsonify({'error': 'Failed to log transaction'}), 500
        
        return jsonify({
            'customer': customer,
            'transaction': credit_log
        })
        
    except Exception as e:
        print(f"Add customer credit error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

# ============================================================================
# STOCK TAKING SYSTEM
# ============================================================================

@app.route('/api/stock-taking', methods=['GET', 'POST'])
@token_required
def stock_taking():
    """Stock taking operations"""
    try:
        if request.method == 'GET':
            stock_takes = safe_load_json('stock_takes.json')
            return jsonify(stock_takes)
        
        # POST - Create new stock take
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request data is required'}), 400
        
        stock_takes = safe_load_json('stock_takes.json')
        products = safe_load_json('products.json')
        batches = safe_load_json('batches.json')
        
        stock_take = {
            'id': len(stock_takes) + 1,
            'userId': request.user.get('id'),
            'companyId': request.user.get('companyId', 'default'),
            'items': data.get('items', []),
            'status': 'pending',
            'variances': [],
            'createdAt': datetime.now().isoformat()
        }
        
        # Calculate variances
        for item in stock_take['items']:
            product_id = item['productId']
            physical_count = item['physicalCount']
            
            # Get system count from batches
            system_count = sum(b.get('quantity', 0) for b in batches if b.get('productId') == product_id)
            
            variance = physical_count - system_count
            if variance != 0:
                stock_take['variances'].append({
                    'productId': product_id,
                    'systemCount': system_count,
                    'physicalCount': physical_count,
                    'variance': variance
                })
        
        stock_takes.append(stock_take)
        if not safe_save_json('stock_takes.json', stock_takes):
            return jsonify({'error': 'Failed to save stock take'}), 500
        
        return jsonify(stock_take), 201
        
    except Exception as e:
        print(f"Stock taking error: {e}")
        return jsonify({'error': f'Operation failed: {str(e)}'}), 500

@app.route('/api/clear-data', methods=['POST'])
@token_required
def clear_data():
    """Clear sales and expenses data"""
    try:
        data = request.get_json()
        clear_type = data.get('type', 'all')
        
        if clear_type == 'sales' or clear_type == 'all':
            if not safe_save_json('sales.json', []):
                return jsonify({'error': 'Failed to clear sales'}), 500
        
        if clear_type == 'expenses' or clear_type == 'all':
            if not safe_save_json('expenses.json', []):
                return jsonify({'error': 'Failed to clear expenses'}), 500
        
        return jsonify({'message': 'Data cleared successfully'})
        
    except Exception as e:
        print(f"Clear data error: {e}")
        return jsonify({'error': f'Failed to clear data: {str(e)}'}), 500

# ============================================================================
# HEALTH CHECK AND UTILITY ENDPOINTS
# ============================================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

@app.route('/api/', methods=['GET'])
def api_root():
    """API root endpoint"""
    return jsonify({
        'message': 'POS Backend API v2.0',
        'endpoints': {
            'auth': ['/api/auth/signup', '/api/auth/login', '/api/auth/me'],
            'users': ['/api/users', '/api/users/<id>'],
            'products': ['/api/products', '/api/products/<id>'],
            'sales': ['/api/sales'],
            'expenses': ['/api/expenses'],
            'settings': ['/api/settings'],
            'credit_requests': ['/api/credit-requests']
        }
    })

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({'error': 'Method not allowed'}), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

# ============================================================================
# MAIN APPLICATION ENTRY POINT
# ============================================================================

# Create main admin routes
# create_main_admin_routes(app, safe_load_json, safe_save_json, token_required)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    debug_mode = os.environ.get('FLASK_ENV') == 'development'
    
    print(f"Starting POS Backend API v2.0 on port {port}")
    print(f"Debug mode: {debug_mode}")
    print(f"Data directory: {DATA_DIR}")
    print("Available endpoints:")
    print("  - Authentication: /api/auth/*")
    print("  - Users: /api/users")
    print("  - Products: /api/products")
    print("  - Sales: /api/sales")
    print("  - Expenses: /api/expenses")
    print("  - Settings: /api/settings")
    print("  - Credit Requests: /api/credit-requests")
    
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
