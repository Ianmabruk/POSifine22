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

# Track connected WebSocket clients for broadcasting
connected_clients = []

def broadcast_update(message_type, data):
    """Broadcast updates to all connected WebSocket clients"""
    message = {'type': message_type, 'data': data, 'timestamp': datetime.now().isoformat()}
    disconnected = []
    for client in connected_clients:
        try:
            client.send(json.dumps(message))
        except Exception:
            disconnected.append(client)
    # Remove disconnected clients
    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)

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
RECIPES_FILE = f'{DATA_DIR}/recipes.json'
NOTES_FILE = f'{DATA_DIR}/cashier_notes.json'

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

    # Register this client for broadcasts
    connected_clients.append(ws)
    
    # Send current products on connect
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
    finally:
        # Remove client when disconnected
        if ws in connected_clients:
            connected_clients.remove(ws)

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

@app.route('/api/auth/pin-login', methods=['POST', 'OPTIONS'])
def pin_login():
    """Login using PIN instead of password"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body', 'message': 'Request body must be JSON'}), 400
        
        # Validate required fields
        if 'email' not in data or not data['email']:
            return jsonify({'error': 'Missing required field: email'}), 400
        if 'pin' not in data or not data['pin']:
            return jsonify({'error': 'Missing required field: pin'}), 400
        
        users = load_data(USERS_FILE)
        
        # For now, PIN login works same as password login (PIN is not implemented yet)
        # In production, you would check user.pin instead of user.password
        user = next((u for u in users if u.get('email') == data['email']), None)
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        # Simple PIN validation - in production, use bcrypt or similar
        if str(data['pin']) != str(user.get('pin', data['pin'])):
            return jsonify({'error': 'Invalid PIN'}), 401
        
        token = jwt.encode({'id': user['id'], 'email': user['email'], 'role': user['role'], 'accountId': user['accountId']}, 
                          app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password' and k != 'pin'}
        })
    except Exception as e:
        import traceback
        error_msg = f"{str(e)} | {traceback.format_exc()}"
        print(f"PIN Login error: {error_msg}")
        return jsonify({'error': 'PIN login failed', 'message': str(e)}), 500

@app.route('/api/main-admin/auth/login', methods=['POST', 'OPTIONS'])
def main_admin_login():
    """Main admin (owner) login"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body'}), 400
        
        email = data.get('email', '').lower()
        password = data.get('password', '')
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        # Check if user is the main admin/owner
        # Main admin should have role 'owner' or 'admin' with special flag
        users = load_data(USERS_FILE)
        user = next((u for u in users if u.get('email', '').lower() == email and u.get('password') == password), None)
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if user has admin/owner privileges
        if user.get('role') not in ['owner', 'admin']:
            return jsonify({'error': 'Access denied. Admin privileges required'}), 403
        
        token = jwt.encode({
            'id': user['id'],
            'email': user['email'],
            'role': user['role'],
            'accountId': user.get('accountId', 'main'),
            'isMainAdmin': True
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': token,
            'user': {k: v for k, v in user.items() if k != 'password' and k != 'pin'}
        })
    except Exception as e:
        import traceback
        print(f"Main admin login error: {str(e)} | {traceback.format_exc()}")
        return jsonify({'error': 'Login failed', 'message': str(e)}), 500

@app.route('/api/products', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_products():
    if request.method == 'OPTIONS':
        return '', 200
        
    products = load_data(PRODUCTS_FILE)
    
    if request.method == 'GET':
        return jsonify(products)
    
    data = request.get_json()
    
    # Validate required fields
    if 'name' not in data or not data['name']:
        return jsonify({'error': 'Product name is required'}), 400
    if 'price' not in data or data['price'] is None:
        return jsonify({'error': 'Product price is required'}), 400
    
    product = {
        'id': get_next_id(products),
        'name': data['name'],
        'price': float(data['price']),
        'quantity': int(data.get('quantity', 0)),
        'category': data.get('category', 'general'),
        'image': data.get('image', None),  # Base64 image or URL
        'isComposite': data.get('isComposite', False),
        'ingredients': data.get('ingredients', []),  # List of {productId, quantity}
        'accountId': request.user['accountId'],
        'createdAt': datetime.now().isoformat()
    }
    
    products.append(product)
    save_data(PRODUCTS_FILE, products)
    
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_product(product_id):
    if request.method == 'OPTIONS':
        return '', 200
        
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

@app.route('/api/products/<int:product_id>/stock', methods=['PUT', 'OPTIONS'])
@token_required
def update_stock(product_id):
    """Update product stock/inventory"""
    if request.method == 'OPTIONS':
        return '', 200
    
    products = load_data(PRODUCTS_FILE)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    data = request.get_json()
    
    # Handle different stock update types
    if 'quantity' in data:
        product['quantity'] = int(data['quantity'])
    elif 'increment' in data:
        product['quantity'] = product.get('quantity', 0) + int(data['increment'])
    elif 'decrement' in data:
        product['quantity'] = max(0, product.get('quantity', 0) - int(data['decrement']))
    
    save_data(PRODUCTS_FILE, products)
    
    # Broadcast stock update to all connected clients
    broadcast_update('stock_updated', {
        'id': product_id,
        'product': product,
        'allProducts': products
    })
    
    return jsonify(product)

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

@app.route('/api/main-admin/users-with-subscriptions', methods=['GET'])
@token_required
def get_users_with_subscriptions():
    """Get all users enriched with subscription tracking data"""
    users = load_data(USERS_FILE)
    now = datetime.now()
    
    enriched_users = []
    for u in users:
        # Skip if no createdAt (shouldn't happen with new code)
        if 'createdAt' not in u:
            u['createdAt'] = datetime.now().isoformat()
        
        # Parse createdAt to datetime
        try:
            created_at = datetime.fromisoformat(u['createdAt'])
        except:
            created_at = datetime.now()
        
        # Calculate days active
        days_active = (now - created_at).days
        
        # Determine if user is on free trial
        is_free_trial = u.get('plan') in [None, 'free', '']
        
        # Check if reached 30-day limit
        has_reached_trial_limit = days_active >= 30 and is_free_trial
        
        # Calculate days until expiry
        days_until_expiry = max(0, 30 - days_active) if is_free_trial else 0
        
        # Determine subscription status
        if is_free_trial:
            if has_reached_trial_limit:
                subscription_status = 'trial_expired'
            else:
                subscription_status = 'free_trial'
        else:
            subscription_status = 'paid'
        
        # Calculate trial expiry date
        trial_expiry_date = None
        if is_free_trial:
            trial_expiry_date = (created_at + timedelta(days=30)).isoformat()
        
        # Enrich user object
        enriched_user = {
            k: v for k, v in u.items() if k != 'password'
        }
        enriched_user.update({
            'daysActive': days_active,
            'isFreeTrial': is_free_trial,
            'hasReachedTrialLimit': has_reached_trial_limit,
            'daysUntilExpiry': days_until_expiry,
            'subscriptionStatus': subscription_status,
            'trialExpireDate': trial_expiry_date,
            'planPrice': 0 if is_free_trial else 99  # Default prices - adjust as needed
        })
        
        enriched_users.append(enriched_user)
    
    return jsonify(enriched_users)

@app.route('/api/main-admin/send-email', methods=['POST'])
@token_required
def send_admin_email():
    """Send email to user for upgrade or trial reminder"""
    data = request.get_json()
    user_id = data.get('userId')
    email_type = data.get('type')  # 'upgrade' or 'reminder'
    
    users = load_data(USERS_FILE)
    user = next((u for u in users if u.get('id') == user_id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    # In production, integrate with email service (SendGrid, Mailgun, etc.)
    # For now, just return success
    if email_type == 'upgrade':
        # Send upgrade email
        subject = 'Your free trial has expired - Upgrade now!'
        message = f"Hi {user.get('name', 'User')}, your 30-day free trial has ended. Please upgrade to continue using our service."
    elif email_type == 'reminder':
        # Send reminder email
        days_left = data.get('daysLeft', 5)
        subject = f'Your free trial expires in {days_left} days'
        message = f"Hi {user.get('name', 'User')}, your free trial expires in {days_left} days. Upgrade now to avoid losing access."
    else:
        return jsonify({'error': 'Invalid email type'}), 400
    
    # TODO: Implement actual email sending
    # For now, just log and return success
    print(f"[EMAIL] To: {user.get('email')}, Subject: {subject}")
    
    return jsonify({
        'success': True,
        'message': f'Email sent to {user.get("email")}',
        'user_id': user_id,
        'type': email_type
    })

@app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST'])
@token_required
def toggle_user_lock(user_id):
    """Lock or unlock a user account"""
    data = request.get_json()
    locked = data.get('locked', False)
    
    users = load_data(USERS_FILE)
    user = next((u for u in users if u.get('id') == user_id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user['active'] = not locked
    save_data(USERS_FILE, users)
    
    return jsonify({
        'success': True,
        'user_id': user_id,
        'locked': locked,
        'message': f'User {"locked" if locked else "unlocked"} successfully'
    })

@app.route('/api/sales', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_sales():
    if request.method == 'OPTIONS':
        return '', 200
    
    sales = load_data(SALES_FILE)
    
    if request.method == 'GET':
        return jsonify(sales)
    
    data = request.get_json()
    products = load_data(PRODUCTS_FILE)
    
    # Process sale items - deduct inventory and handle composite products
    for item in data.get('items', []):
        product = next((p for p in products if p['id'] == item['productId']), None)
        if product:
            # Deduct sold quantity
            product['quantity'] = product.get('quantity', 0) - item['quantity']
            
            # If composite product, deduct ingredients
            if product.get('isComposite'):
                for ingredient in product.get('ingredients', []):
                    ingredient_product = next((p for p in products if p['id'] == ingredient['productId']), None)
                    if ingredient_product:
                        ingredient_product['quantity'] = ingredient_product.get('quantity', 0) - (ingredient['quantity'] * item['quantity'])
    
    save_data(PRODUCTS_FILE, products)
    
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

@app.route('/api/recipes', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_recipes():
    """Manage composite product recipes/BOMs"""
    if request.method == 'OPTIONS':
        return '', 200
    
    recipes = load_data(RECIPES_FILE)
    
    if request.method == 'GET':
        return jsonify(recipes)
    
    # POST - Create new recipe
    data = request.get_json()
    recipe = {
        'id': max([r.get('id', 0) for r in recipes], default=0) + 1,
        'productId': data.get('productId'),
        'name': data.get('name'),
        'ingredients': data.get('ingredients', []),  # [{productId, quantity, name}, ...]
        'createdAt': datetime.now().isoformat(),
        'updatedAt': datetime.now().isoformat()
    }
    recipes.append(recipe)
    save_data(RECIPES_FILE, recipes)
    
    return jsonify(recipe), 201

@app.route('/api/recipes/<int:recipe_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_recipe(recipe_id):
    """Update or delete a recipe"""
    if request.method == 'OPTIONS':
        return '', 200
    
    recipes = load_data(RECIPES_FILE)
    recipe = next((r for r in recipes if r['id'] == recipe_id), None)
    
    if not recipe:
        return jsonify({'error': 'Recipe not found'}), 404
    
    if request.method == 'GET':
        return jsonify(recipe)
    
    if request.method == 'DELETE':
        recipes = [r for r in recipes if r['id'] != recipe_id]
        save_data(RECIPES_FILE, recipes)
        return jsonify({'message': 'Recipe deleted'}), 200
    
    if request.method == 'PUT':
        data = request.get_json()
        recipe.update({
            'name': data.get('name', recipe.get('name')),
            'ingredients': data.get('ingredients', recipe.get('ingredients')),
            'updatedAt': datetime.now().isoformat()
        })
        save_data(RECIPES_FILE, recipes)
        return jsonify(recipe)

@app.route('/api/cashier-notes', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_cashier_notes():
    """Cashier notes/reminders for other staff"""
    if request.method == 'OPTIONS':
        return '', 200
    
    notes = load_data(NOTES_FILE)
    
    if request.method == 'GET':
        return jsonify(notes)
    
    # POST - Create new note
    data = request.get_json()
    note = {
        'id': max([n.get('id', 0) for n in notes], default=0) + 1,
        'fromCashierId': request.user.get('id'),
        'fromCashierName': request.user.get('name'),
        'message': data.get('message'),
        'priority': data.get('priority', 'normal'),  # low, normal, high
        'read': False,
        'createdAt': datetime.now().isoformat()
    }
    notes.append(note)
    save_data(NOTES_FILE, notes)
    
    # Broadcast note to all connected dashboards
    broadcast_update('new_note', note)
    
    return jsonify(note), 201

@app.route('/api/cashier-notes/<int:note_id>', methods=['PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_cashier_note(note_id):
    """Mark note as read or delete"""
    if request.method == 'OPTIONS':
        return '', 200
    
    notes = load_data(NOTES_FILE)
    note = next((n for n in notes if n['id'] == note_id), None)
    
    if not note:
        return jsonify({'error': 'Note not found'}), 404
    
    if request.method == 'DELETE':
        notes = [n for n in notes if n['id'] != note_id]
        save_data(NOTES_FILE, notes)
        return jsonify({'message': 'Note deleted'}), 200
    
    if request.method == 'PUT':
        data = request.get_json()
        note['read'] = data.get('read', note.get('read'))
        save_data(NOTES_FILE, notes)
        return jsonify(note)

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