from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
import time
from datetime import datetime, timedelta
from functools import wraps
from flask_sock import Sock
import bcrypt
import hashlib
from collections import defaultdict

# Import optimized stock engine
from stock_engine import StockDeductionEngine, optimize_sale_completion

app = Flask(__name__)

# ============================================================
# COMPREHENSIVE CORS CONFIGURATION - PRODUCTION READY
# ============================================================

# 1. Configure Flask-CORS with explicit settings
CORS(
    app,
    resources={
        r"/api/*": {
            "origins": ["*"],
            "methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization", "X-Requested-With"],
            "expose_headers": ["Content-Type", "Authorization"],
            "max_age": 86400,
            "supports_credentials": False
        }
    },
    send_wildcard=True,
    vary_header=True,
    automatic_options=True
)

# 2. Explicit preflight handler - catches all OPTIONS requests
@app.before_request
def handle_preflight_request():
    """
    Explicitly handle CORS preflight (OPTIONS) requests
    This ensures the preflight gets proper headers BEFORE reaching any route
    """
    if request.method == 'OPTIONS':
        response = jsonify({'status': 'ok'})
        response.status_code = 204
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept'
        response.headers['Access-Control-Max-Age'] = '86400'
        response.headers['Access-Control-Allow-Credentials'] = 'false'
        return response

# 3. Ensure all responses include CORS headers
@app.after_request
def set_cors_headers(response):
    """
    Add CORS headers to ALL responses (success, error, 404, 500, etc.)
    This is the final safety net to ensure no response slips through without headers
    """
    # Always add these headers
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, PATCH, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, Accept'
    response.headers['Access-Control-Max-Age'] = '86400'
    response.headers['Access-Control-Expose-Headers'] = 'Content-Type, Authorization'
    
    # Ensure proper Content-Type for API responses
    if not response.headers.get('Content-Type'):
        response.headers['Content-Type'] = 'application/json'
    
    return response

# WebSocket (flask-sock)
sock = Sock(app)

# Track connected WebSocket clients for broadcasting
connected_clients = []

def broadcast_update(message_type, data, account_id=None):
    """Broadcast updates to all connected WebSocket clients (optionally filtered by account)"""
    message = {'type': message_type, 'data': data, 'timestamp': datetime.now().isoformat()}
    disconnected = []
    for client in connected_clients:
        try:
            # If account_id specified, send to that account's dashboards only
            if account_id is None or getattr(client, 'account_id', None) == account_id:
                client.send(json.dumps(message))
        except Exception:
            disconnected.append(client)
    # Remove disconnected clients
    for client in disconnected:
        if client in connected_clients:
            connected_clients.remove(client)

app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'ultra-pos-secret-2024')

# File-based storage - NO DATABASE REQUIRED
# Use /app/data on Render, or data/ locally
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))

# Fallback logic: if in /app environment, use /app/data
if '/app' in os.getcwd() or os.path.exists('/app'):
    # On Render or similar platform
    DATA_DIR = os.environ.get('DATA_DIR', '/app/data')

# Ensure DATA_DIR is an absolute path
DATA_DIR = os.path.abspath(DATA_DIR)

# Create data directory with proper error handling
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    # Test if directory is writable
    test_file = os.path.join(DATA_DIR, '.write_test')
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print(f"✅ Data directory ready: {DATA_DIR}")
except PermissionError:
    # If /app/data not writable, fallback to ./data
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
    os.makedirs(DATA_DIR, exist_ok=True)
    print(f"⚠️  Using fallback data directory: {DATA_DIR}")
except Exception as e:
    print(f"⚠️  Warning setting up data directory: {e}")
    DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), 'data'))
    os.makedirs(DATA_DIR, exist_ok=True)

# Define all data file paths
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
TIME_ENTRIES_FILE = f'{DATA_DIR}/time_entries.json'
VENDORS_FILE = f'{DATA_DIR}/vendors.json'
RAW_MATERIALS_FILE = f'{DATA_DIR}/raw_materials.json'
SUBSCRIPTIONS_FILE = f'{DATA_DIR}/subscriptions.json'
SUBSCRIPTION_PLANS_FILE = f'{DATA_DIR}/subscription_plans.json'
CLOCK_ENTRIES_FILE = f'{DATA_DIR}/clock_entries.json'

# Ensure data directory exists and initialize empty JSON files
os.makedirs(DATA_DIR, exist_ok=True)

def init_json_file(filepath):
    """Initialize JSON file with empty array if it doesn't exist"""
    try:
        # Ensure parent directory exists
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        if not os.path.exists(filepath):
            with open(filepath, 'w') as f:
                json.dump([], f)
        # Verify file has valid JSON
        with open(filepath, 'r') as f:
            content = f.read().strip()
            if not content:
                with open(filepath, 'w') as fw:
                    json.dump([], fw)
    except PermissionError as e:
        print(f"⚠️  Permission error initializing {filepath}: {e}")
    except Exception as e:
        print(f"⚠️  Error initializing {filepath}: {e}")

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

def create_auto_expenses_for_sale(deductions, products, expenses, account_id):
    """
    Auto-create expense records when composite products consume ingredients.
    
    For each ingredient deducted from a composite product sale:
    - Calculate cost used = quantity deducted * costPerUnit
    - Create/update expense record
    
    Args:
        deductions: From StockDeductionEngine.validate_and_prepare_deductions()
        products: All products (includes expense-only items)
        expenses: Current expenses list
        account_id: For data isolation
    
    Returns:
        Updated expenses list
    """
    try:
        product_map = {p['id']: p for p in products}
        
        # Process each ingredient/expense deduction
        for deduction in deductions.get('expenses', []):
            product_id = deduction['id']
            qty_deducted = deduction.get('qty_deducted', 0)
            
            product = product_map.get(product_id)
            if not product:
                continue
            
            # Calculate cost
            cost_per_unit = float(product.get('cost_per_unit', product.get('costPerUnit', 0)))
            total_cost = qty_deducted * cost_per_unit
            
            if total_cost > 0:
                # Create auto-expense record
                auto_expense = {
                    'id': get_next_id(expenses),
                    'name': f"Auto-deducted: {product['name']}",
                    'amount': total_cost,
                    'quantity': qty_deducted,
                    'unit': product.get('unit', 'unit'),
                    'category': 'ingredient',
                    'accountId': account_id,
                    'source': 'auto-deduction',
                    'linkedProductId': product_id,
                    'createdAt': datetime.now().isoformat(),
                    'description': f"Auto-deducted from sale - {qty_deducted}{product.get('unit', 'unit')} @ {cost_per_unit} KES/{product.get('unit', 'unit')}"
                }
                expenses.append(auto_expense)
        
        return expenses
    except Exception as e:
        print(f"⚠️  Error creating auto-expenses: {str(e)}")
        return expenses

# Initialize all data files on startup
try:
    for filepath in [USERS_FILE, PRODUCTS_FILE, SALES_FILE, EXPENSES_FILE, 
                     BATCHES_FILE, DISCOUNTS_FILE, CREDIT_REQUESTS_FILE, 
                     SETTINGS_FILE, REMINDERS_FILE, RECIPES_FILE, TIME_ENTRIES_FILE, RAW_MATERIALS_FILE, CLOCK_ENTRIES_FILE, VENDORS_FILE]:
        init_json_file(filepath)
    
    print(f"✅ Using file storage at: {DATA_DIR}")
    print(f"✅ Data directory exists: {os.path.exists(DATA_DIR)}")
    print(f"✅ Data files initialized")
except Exception as e:
    print(f"⚠️  Warning during file initialization: {e}")
    print(f"✅ Using file storage at: {DATA_DIR}")

# Initialize main admin user if not exists
def init_main_admin():
    try:
        users = load_data(USERS_FILE)
        admin_email = 'ianmabruk3@gmail.com'
        
        # Check if admin already exists
        if any(u.get('email') == admin_email for u in users):
            return
        
        # Create main admin user with complete tracking fields
        main_admin_user = {
            'id': get_next_id(users),
            'email': admin_email,
            'password': 'mabruk2004',
            'name': 'Ian Mabruk',
            'role': 'owner',
            'plan': 'ultra',
            'planType': 'paid',
            'accountId': 'main',
            'active': True,
            'locked': False,
            'isMainAdmin': True,
            'createdAt': datetime.now().isoformat(),
            'serviceStartDate': datetime.now().isoformat(),
            'lastActivityDate': datetime.now().isoformat(),
            'daysUsed': 0,
            'requestedTrial': False
        }
        
        users.append(main_admin_user)
        save_data(USERS_FILE, users)
        print(f"✅ Main admin user created: {admin_email}")
    except Exception as e:
        print(f"⚠️  Warning initializing main admin: {e}")

try:
    init_main_admin()
except Exception as e:
    print(f"⚠️  Failed to initialize main admin on startup: {e}")

# PIN Rate Limiting Tracker (in-memory, resets on server restart)
pin_attempts = defaultdict(lambda: {'count': 0, 'locked_until': None})

def check_pin_rate_limit(user_id):
    """Check if user is rate limited for PIN attempts"""
    tracker = pin_attempts[user_id]
    if tracker['locked_until']:
        if datetime.now() < tracker['locked_until']:
            return False, f"Account locked. Try again after {tracker['locked_until'].strftime('%H:%M')}"
        else:
            # Lockout expired
            tracker['count'] = 0
            tracker['locked_until'] = None
    return True, None

def increment_pin_attempts(user_id):
    """Increment PIN attempt counter. Lock if threshold exceeded."""
    tracker = pin_attempts[user_id]
    tracker['count'] += 1
    
    if tracker['count'] >= 3:
        tracker['locked_until'] = datetime.now() + timedelta(minutes=15)
        return f"Account locked after 3 failed attempts. Try again in 15 minutes."
    return None

def reset_pin_attempts(user_id):
    """Reset PIN attempts after successful unlock"""
    pin_attempts[user_id] = {'count': 0, 'locked_until': None}

def hash_pin(pin):
    """Hash PIN using bcrypt"""
    try:
        salt = bcrypt.gensalt(rounds=12)
        return bcrypt.hashpw(pin.encode('utf-8'), salt).decode('utf-8')
    except Exception as e:
        print(f"❌ PIN hashing error: {e}")
        return None

def verify_pin(pin, hashed_pin):
    """Verify PIN against hash using bcrypt"""
    try:
        if not hashed_pin:
            return False
        return bcrypt.checkpw(pin.encode('utf-8'), hashed_pin.encode('utf-8'))
    except Exception as e:
        print(f"❌ PIN verification error: {e}")
        return False

# ============================================================
# SUBSCRIPTION MANAGEMENT FUNCTIONS
# ============================================================

def get_subscription_status(user):
    """Calculate subscription status for a user"""
    try:
        service_start = datetime.fromisoformat(user.get('serviceStartDate', datetime.now().isoformat()))
        
        # Get subscription duration in days (default 30 for monthly)
        duration_days = user.get('subscriptionDurationDays', 30)
        
        subscription_end = service_start + timedelta(days=duration_days)
        now = datetime.now()
        
        days_used = (now - service_start).days + 1
        days_remaining = max(0, (subscription_end - now).days)
        
        # Determine status
        if days_remaining <= 0:
            status = 'expired'
        elif days_remaining == 1:
            status = 'expiring_soon'
        elif days_remaining <= 7:
            status = 'expiring'
        else:
            status = 'active'
        
        return {
            'status': status,
            'days_used': max(0, days_used),
            'days_remaining': days_remaining,
            'subscription_start': service_start.isoformat(),
            'subscription_end': subscription_end.isoformat(),
            'is_active': status != 'expired' and user.get('active', True),
            'reminder_needed': days_remaining == 1 and not user.get('subscription_reminder_sent', False)
        }
    except Exception as e:
        print(f"Error calculating subscription status: {e}")
        return {
            'status': 'unknown',
            'days_used': 0,
            'days_remaining': 30,
            'is_active': False
        }

def init_subscription_plans():
    """Initialize subscription plans if not exists"""
    try:
        plans = load_data(SUBSCRIPTION_PLANS_FILE)
        if not plans:
            plans = [
                {
                    'id': 'basic',
                    'name': 'Professional Package',
                    'price': 1500,
                    'currency': 'KSH',
                    'duration_days': 30,
                    'features': [
                        'Admin Dashboard + Cashier POS',
                        'Basic Inventory Management',
                        'Sales Tracking',
                        'Daily/Weekly Sales Summaries',
                        'Basic Profit/Loss View',
                        'Limited Email Notifications',
                        'Record Products Sold',
                        'Up to 2 Users',
                        'Vendor Management',
                        'Basic Expense Tracking',
                        'Limited Analytics'
                    ]
                },
                {
                    'id': 'ultra',
                    'name': 'Ultra Package (Enterprise)',
                    'price': 3000,
                    'currency': 'KSH',
                    'duration_days': 30,
                    'features': [
                        'Admin Dashboard + Cashier POS',
                        'Full Inventory Management',
                        'Recipe/BOM Builder',
                        'Composite Products Support',
                        'Automatic Stock Deduction',
                        'COGS Calculation',
                        'User Management',
                        'Permission Controls',
                        'Expense Tracking',
                        'Advanced Analytics',
                        'Unlimited Users',
                        'Vendor Management',
                        'Advanced Reporting',
                        'Priority Support'
                    ]
                }
            ]
            save_data(SUBSCRIPTION_PLANS_FILE, plans)
    except Exception as e:
        print(f"Error initializing subscription plans: {e}")

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        # Allow OPTIONS preflight requests without token
        if request.method == 'OPTIONS':
            return '', 200
        
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            print(f"❌ Token missing for {request.path}")
            return jsonify({'error': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
            
            # NEW: Check screen lock state - block API calls if locked (except unlock endpoint)
            if data.get('screen_locked') and request.path != '/api/auth/unlock-screen':
                return jsonify({'error': 'Screen is locked', 'screen_locked': True}), 423
            
        except Exception as e:
            print(f"❌ Invalid token: {str(e)}")
            return jsonify({'error': f'Invalid token: {str(e)}'}), 401
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
        decoded = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        # Extract accountId from token for message filtering
        account_id = decoded.get('accountId')
        if not account_id:
            ws.send(json.dumps({'error': 'Invalid token - no accountId'}))
            return
    except Exception as e:
        try:
            ws.send(json.dumps({'error': 'Invalid token'}))
        except Exception:
            pass
        return

    # Store account_id on the WebSocket object for filtering
    ws.account_id = account_id
    
    # Register this client for broadcasts
    connected_clients.append(ws)
    
    # Send current products on connect filtered by accountId
    products = load_data(PRODUCTS_FILE)
    filtered_products = [p for p in products if p.get('accountId') == account_id]
    try:
        ws.send(json.dumps({'type': 'initial', 'products': filtered_products}))
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
    """Handle user signup"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 204
    
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
        
        # Normalize email to lowercase
        email = data['email'].strip().lower()
        
        # Fast check if user exists
        for u in users:
            if u.get('email', '').lower() == email:
                return jsonify({'error': 'User already exists'}), 400
        
        # Create user with optimized fields
        plan_id = data.get('planId', data.get('plan', 'basic'))  # Support both planId and plan for backwards compatibility
        
        # Load plan configuration to get maxCashiers
        plan_config = None
        max_cashiers = None
        try:
            subscription_plans = load_data(SUBSCRIPTION_PLANS_FILE)
            for plan in subscription_plans:
                if plan.get('id') == plan_id:
                    plan_config = plan
                    max_cashiers = plan.get('maxCashiers')  # None for unlimited, or specific number
                    break
        except Exception as e:
            print(f"⚠️ Could not load subscription plans: {e}")
        
        trial_days = 14
        account_id = get_next_id(users)
        creation_time = datetime.now()
        trial_expiry = creation_time + timedelta(days=trial_days)
        
        user = {
            'id': get_next_id(users),
            'email': email,
            'password': data['password'],
            'name': data['name'],
            'role': 'admin' if plan_id in ['1600', 'ultra', 'paid', 'basic', 'ultra'] else 'cashier',
            'plan': plan_id,
            'planType': data.get('planType', plan_id),
            'accountId': account_id,
            'maxCashiers': max_cashiers,
            'active': True,
            'locked': False,
            'createdAt': creation_time.isoformat(),
            'serviceStartDate': creation_time.isoformat(),
            'lastActivityDate': creation_time.isoformat(),
            'lastLoginDate': creation_time.isoformat(),
            'daysUsed': 0,
            'requestedTrial': data.get('requestedTrial', False),
            'trialDaysLeft': trial_days if plan_id in ['trial', 'free_demo'] else None,
            'trialExpiry': trial_expiry.isoformat() if plan_id in ['trial', 'free_demo'] else None,
            'signupSource': data.get('signupSource', 'direct'),
            'signupDetails': {
                'company': data.get('company'),
                'phone': data.get('phone'),
                'country': data.get('country'),
                'industry': data.get('industry')
            }
        }
        
        users.append(user)
        save_data(USERS_FILE, users)
        
        # Generate token
        token = jwt.encode(
            {'id': user['id'], 'email': user['email'], 'role': user['role'], 'accountId': user['accountId'], 'locked': False}, 
            app.config['SECRET_KEY'], 
            algorithm='HS256'
        )
        
        # Return minimal user data to reduce payload size
        user_response = {
            'id': user['id'],
            'email': user['email'],
            'name': user['name'],
            'role': user['role'],
            'plan': user.get('plan'),
            'accountId': user.get('accountId'),
            'userLimit': user.get('userLimit'),
            'locked': False,
            'active': True
        }
        
        return jsonify({
            'token': token,
            'user': user_response
        }), 200
    except Exception as e:
        import traceback
        error_msg = f"{str(e)} | {traceback.format_exc()}"
        print(f"❌ Signup error: {error_msg}")
        return jsonify({'error': 'Signup failed', 'message': str(e)}), 500

@app.route('/api/auth/login', methods=['POST', 'OPTIONS'])
def login():
    """Handle user login"""
    if request.method == 'OPTIONS':
        return jsonify({'status': 'ok'}), 204
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request body', 'message': 'Request body must be JSON'}), 400
        
        # Validate required fields
        if 'email' not in data or not data['email']:
            return jsonify({'error': 'Missing required field: email'}), 400
        if 'password' not in data or not data['password']:
            return jsonify({'error': 'Missing required field: password'}), 400
        
        # Optimize: Use a cache to avoid reading file repeatedly
        users = load_data(USERS_FILE)
        
        # Normalize email to lowercase for case-insensitive comparison
        email = data['email'].strip().lower()
        password = data['password']
        
        # Fast lookup with early exit
        user = None
        for u in users:
            if u.get('email', '').lower() == email and u.get('password') == password:
                user = u
                break
        
        if not user:
            return jsonify({'error': 'Invalid credentials'}), 401
        
        # Check if user is locked
        if user.get('locked', False):
            return jsonify({'error': 'Account is locked. Contact administrator.', 'userLocked': True}), 403
        
        # Update last login date without full save (optimize)
        user['lastLoginDate'] = datetime.now().isoformat()
        user['lastActivityDate'] = datetime.now().isoformat()
        
        # Save updated user
        save_data(USERS_FILE, users)
        
        # Generate token with screen lock information
        token = jwt.encode(
            {
                'id': user['id'],
                'email': user['email'],
                'role': user['role'],
                'accountId': user['accountId'],
                'locked': user.get('locked', False),
                'screen_locked': False,           # New: lock state
                'locked_at': None,                # New: when locked
                'lock_requires_pin': user.get('screen_lock_enabled', True)  # New: needs PIN
            }, 
            app.config['SECRET_KEY'], 
            algorithm='HS256'
        )
        
        # Return minimal user data to reduce payload size
        user_response = {
            'id': user['id'],
            'email': user['email'],
            'name': user['name'],
            'role': user['role'],
            'plan': user.get('plan'),
            'accountId': user.get('accountId'),
            'userLimit': user.get('userLimit'),
            'locked': user.get('locked', False),
            'active': user.get('active', True)
        }
        
        return jsonify({
            'token': token,
            'user': user_response
        }), 200
    except Exception as e:
        import traceback
        error_msg = f"{str(e)} | {traceback.format_exc()}"
        print(f"❌ Login error: {error_msg}")
        return jsonify({'error': 'Login failed', 'message': str(e)}), 500

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
    """Main admin (owner) login - RESTRICTED TO OWNER ROLE ONLY"""
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
        
        # STRICT: Only ianmabruk3@gmail.com can access main admin
        OWNER_EMAIL = 'ianmabruk3@gmail.com'
        if email != OWNER_EMAIL:
            return jsonify({'error': f'Access denied. Only {OWNER_EMAIL} can access main admin'}), 403
        
        # Main admin password must be 'mabruk2004'
        if password != 'mabruk2004':
            return jsonify({'error': 'Invalid password'}), 401
        
        # Check if user is the main admin/owner
        users = load_data(USERS_FILE)
        user = next((u for u in users if u.get('email', '').lower() == email), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        # STRICT: Only OWNER role can access main admin dashboard
        if user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Only owner can access main admin dashboard'}), 403
        
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

# ==================== NEW SECURITY ENDPOINTS ====================

@app.route('/api/auth/set-pin', methods=['POST', 'OPTIONS'])
@token_required
def set_pin():
    """Set or update user PIN - admin only for other users"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        new_pin = data.get('new_pin', '').strip()
        user_id = data.get('user_id')  # If admin setting PIN for another user
        
        if not new_pin or len(new_pin) < 4:
            return jsonify({'error': 'PIN must be at least 4 digits'}), 400
        
        # Non-numeric validation
        if not new_pin.isdigit():
            return jsonify({'error': 'PIN must contain only digits'}), 400
        
        users = load_data(USERS_FILE)
        
        # Determine whose PIN we're setting
        if user_id:
            # Admin setting PIN for another user
            if request.user['role'] != 'admin':
                return jsonify({'error': 'Only admins can set PIN for other users'}), 403
            target_user = next((u for u in users if u['id'] == user_id and u['accountId'] == request.user['accountId']), None)
        else:
            # User setting own PIN
            target_user = next((u for u in users if u['id'] == request.user['id']), None)
        
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Hash PIN using bcrypt
        hashed_pin = hash_pin(new_pin)
        if not hashed_pin:
            return jsonify({'error': 'Failed to hash PIN'}), 500
        
        target_user['hashed_pin'] = hashed_pin
        target_user['pin_attempts'] = 0
        target_user['pin_locked_until'] = None
        target_user['screen_lock_enabled'] = True
        
        save_data(USERS_FILE, users)
        reset_pin_attempts(target_user['id'])
        
        print(f"✅ PIN updated for user {target_user['id']}")
        return jsonify({'success': True, 'message': 'PIN set successfully'})
    
    except Exception as e:
        print(f"❌ Set PIN error: {str(e)}")
        return jsonify({'error': 'Failed to set PIN', 'message': str(e)}), 500

@app.route('/api/auth/lock-screen', methods=['POST', 'OPTIONS'])
@token_required
def lock_screen():
    """Lock screen - ADMIN ONLY"""
    if request.method == 'OPTIONS':
        return '', 200
    
    # AUTHORIZATION: Only admin can lock screen
    if request.user['role'] != 'admin':
        return jsonify({'error': 'Only admins can lock the screen'}), 403
    
    try:
        # Generate new token with screen_locked: true
        new_token = jwt.encode(
            {
                'id': request.user['id'],
                'email': request.user['email'],
                'role': request.user['role'],
                'accountId': request.user['accountId'],
                'locked': request.user.get('locked', False),
                'screen_locked': True,            # LOCKED
                'locked_at': datetime.now().isoformat(),
                'lock_requires_pin': True
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )
        
        # Broadcast to all clients
        broadcast_update('screen_locked', {
            'admin_id': request.user['id'],
            'locked_at': datetime.now().isoformat(),
            'message': 'Screen locked by admin'
        })
        
        print(f"🔒 Screen locked by admin {request.user['id']}")
        return jsonify({
            'success': True,
            'token': new_token,
            'screen_locked': True,
            'locked_at': datetime.now().isoformat()
        })
    
    except Exception as e:
        print(f"❌ Lock screen error: {str(e)}")
        return jsonify({'error': 'Failed to lock screen', 'message': str(e)}), 500

@app.route('/api/auth/unlock-screen', methods=['POST', 'OPTIONS'])
@token_required
def unlock_screen():
    """Unlock screen by verifying PIN - SECURE BACKEND VALIDATION"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        submitted_pin = data.get('pin', '').strip()
        
        if not submitted_pin:
            return jsonify({'error': 'PIN required'}), 400
        
        user_id = request.user['id']
        
        # Check rate limit
        can_attempt, rate_limit_msg = check_pin_rate_limit(user_id)
        if not can_attempt:
            return jsonify({'error': 'Rate limited', 'message': rate_limit_msg}), 429
        
        # Load user
        users = load_data(USERS_FILE)
        user = next((u for u in users if u['id'] == user_id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Verify PIN hash
        hashed_pin = user.get('hashed_pin')
        if not hashed_pin or not verify_pin(submitted_pin, hashed_pin):
            # Wrong PIN - increment attempts
            lockout_msg = increment_pin_attempts(user_id)
            print(f"❌ Failed unlock attempt for user {user_id}")
            
            if lockout_msg:
                return jsonify({'error': 'Invalid PIN', 'message': lockout_msg, 'locked': True}), 429
            else:
                remaining = 3 - pin_attempts[user_id]['count']
                return jsonify({'error': 'Invalid PIN', 'message': f'{remaining} attempts remaining'}), 401
        
        # Correct PIN - generate new token with screen_locked: false
        reset_pin_attempts(user_id)
        
        new_token = jwt.encode(
            {
                'id': request.user['id'],
                'email': request.user['email'],
                'role': request.user['role'],
                'accountId': request.user['accountId'],
                'locked': request.user.get('locked', False),
                'screen_locked': False,           # UNLOCKED
                'locked_at': None,
                'lock_requires_pin': True
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )
        
        print(f"🔓 Screen unlocked by user {user_id}")
        return jsonify({
            'success': True,
            'token': new_token,
            'screen_locked': False,
            'message': 'Screen unlocked successfully'
        })
    
    except Exception as e:
        print(f"❌ Unlock screen error: {str(e)}")
        return jsonify({'error': 'Failed to unlock screen', 'message': str(e)}), 500

@app.route('/api/admin/lock-user-screen/<user_id>', methods=['POST', 'OPTIONS'])
@token_required
def lock_user_screen_admin(user_id):
    """Admin endpoint to lock a specific user's screen remotely"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        # AUTHORIZATION: Only owner (main admin) can lock other users' screens
        if request.user.get('role') != 'owner':
            return jsonify({'error': 'Only owner/admin can lock other users\' screens'}), 403
        
        # Load target user
        users = load_data(USERS_FILE)
        target_user = next((u for u in users if u['id'] == user_id), None)
        
        if not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Generate locked token for the target user (they'll get it on next request/refresh)
        locked_token = jwt.encode(
            {
                'id': target_user['id'],
                'email': target_user['email'],
                'role': target_user['role'],
                'accountId': target_user.get('accountId'),
                'locked': target_user.get('locked', False),
                'screen_locked': True,  # LOCKED BY ADMIN
                'locked_at': datetime.now().isoformat(),
                'lock_requires_pin': True,
                'locked_by_admin': True
            },
            app.config['SECRET_KEY'],
            algorithm='HS256'
        )
        
        # Store lock notification for user
        target_user['screen_locked'] = True
        target_user['locked_at'] = datetime.now().isoformat()
        target_user['locked_by_admin'] = True
        save_data(USERS_FILE, users)
        
        # Broadcast to all clients that user's screen is locked
        broadcast_update('admin_locked_user_screen', {
            'admin_id': request.user['id'],
            'target_user_id': user_id,
            'target_user_name': target_user.get('name'),
            'locked_at': datetime.now().isoformat(),
            'message': f'Screen locked for {target_user.get("name")} by admin'
        })
        
        print(f"🔒 Admin {request.user['id']} locked screen for user {user_id}")
        return jsonify({
            'success': True,
            'message': f'Screen locked for {target_user.get("name")}',
            'token': locked_token,
            'target_user_id': user_id
        })
    
    except Exception as e:
        print(f"❌ Admin lock user screen error: {str(e)}")
        return jsonify({'error': 'Failed to lock screen', 'message': str(e)}), 500

# ============================================================
# SUBSCRIPTION MANAGEMENT ENDPOINTS
# ============================================================

@app.route('/api/subscriptions/plans', methods=['GET', 'OPTIONS'])
def get_subscription_plans():
    """Get all available subscription plans"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        init_subscription_plans()
        plans = load_data(SUBSCRIPTION_PLANS_FILE)
        return jsonify(plans)
    except Exception as e:
        print(f"Error fetching plans: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscriptions/overview', methods=['GET'])
@token_required
def get_subscription_overview():
    """Get complete subscription overview for Main Admin"""
    try:
        # Verify owner access
        if request.user.get('role') != 'owner':
            return jsonify({'error': 'Owner access required'}), 403
        
        init_subscription_plans()
        plans = load_data(SUBSCRIPTION_PLANS_FILE)
        users = load_data(USERS_FILE)
        
        # Build plan overview with subscribers
        plan_overview = []
        for plan in plans:
            active_subs = []
            expired_subs = []
            total_revenue = 0
            
            for user in users:
                if user.get('plan') == plan['id']:
                    sub_status = get_subscription_status(user)
                    
                    if sub_status['is_active']:
                        active_subs.append({
                            'userId': user.get('id'),
                            'userName': user.get('name'),
                            'email': user.get('email'),
                            'daysUsed': sub_status['days_used'],
                            'daysRemaining': sub_status['days_remaining'],
                            'startDate': sub_status['subscription_start'],
                            'endDate': sub_status['subscription_end'],
                            'status': sub_status['status']
                        })
                        total_revenue += plan['price']
                    else:
                        expired_subs.append({
                            'userId': user.get('id'),
                            'userName': user.get('name'),
                            'email': user.get('email'),
                            'expiredDate': sub_status['subscription_end']
                        })
            
            plan_overview.append({
                'planId': plan['id'],
                'planName': plan['name'],
                'price': plan['price'],
                'currency': plan.get('currency', 'KSH'),
                'durationDays': plan.get('duration_days', 30),
                'features': plan.get('features', []),
                'activeSubscribers': len(active_subs),
                'expiredSubscribers': len(expired_subs),
                'totalRevenue': total_revenue,
                'activeSubscriptions': active_subs,
                'expiredSubscriptions': expired_subs
            })
        
        return jsonify({
            'plans': plan_overview,
            'totalSubscribers': len(users),
            'totalActiveSubscriptions': sum(len(p['activeSubscriptions']) for p in plan_overview),
            'totalRevenue': sum(p['totalRevenue'] for p in plan_overview)
        })
    
    except Exception as e:
        print(f"Error fetching subscription overview: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/user/subscription-status', methods=['GET'])
@token_required
def get_user_subscription_status():
    """Get current user's subscription status"""
    try:
        users = load_data(USERS_FILE)
        user_id = request.user.get('id')
        user = next((u for u in users if u.get('id') == user_id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        sub_status = get_subscription_status(user)
        
        return jsonify({
            'userId': user_id,
            'userName': user.get('name'),
            'plan': user.get('plan'),
            'planName': user.get('planName', ''),
            **sub_status
        })
    
    except Exception as e:
        print(f"Error fetching user subscription status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscriptions/renew', methods=['POST'])
@token_required
def renew_subscription():
    """Renew user's subscription"""
    try:
        data = request.get_json()
        user_id = request.user.get('id')
        
        users = load_data(USERS_FILE)
        user = next((u for u in users if u.get('id') == user_id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        # Reset subscription
        now = datetime.now()
        duration_days = data.get('duration_days', 30)
        
        user['serviceStartDate'] = now.isoformat()
        user['subscriptionDurationDays'] = duration_days
        user['subscription_reminder_sent'] = False
        user['active'] = True
        
        save_data(USERS_FILE, users)
        
        # Broadcast renewal event
        broadcast_update('subscription_renewed', {
            'userId': user_id,
            'userName': user.get('name'),
            'renewedAt': now.isoformat(),
            'endDate': (now + timedelta(days=duration_days)).isoformat()
        })
        
        print(f"✅ Subscription renewed for user {user_id}")
        return jsonify({
            'success': True,
            'message': 'Subscription renewed successfully',
            'newEndDate': (now + timedelta(days=duration_days)).isoformat()
        })
    
    except Exception as e:
        print(f"Error renewing subscription: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/subscriptions/check-expiry', methods=['GET'])
def check_subscription_expiry():
    """Check for subscriptions reaching day 29 (1 day remaining) and create reminders"""
    try:
        users = load_data(USERS_FILE)
        reminders_created = []
        
        for user in users:
            # Skip if already sent reminder
            if user.get('subscription_reminder_sent', False):
                continue
            
            # Skip if subscription already expired
            sub_status = get_subscription_status(user)
            if sub_status['days_remaining'] != 1:
                continue
            
            # Mark reminder as sent
            user['subscription_reminder_sent'] = True
            reminders_created.append({
                'userId': user.get('id'),
                'userName': user.get('name'),
                'email': user.get('email'),
                'daysRemaining': sub_status['days_remaining'],
                'expiryDate': sub_status['subscription_end'],
                'createdAt': datetime.now().isoformat()
            })
        
        # Save updated users
        save_data(USERS_FILE, users)
        
        # Broadcast reminders
        for reminder in reminders_created:
            broadcast_update('subscription_reminder_day29', reminder)
            print(f"🔔 Reminder created for user {reminder['userId']}: {reminder['daysRemaining']} day(s) remaining")
        
        return jsonify({
            'success': True,
            'reminders_created': len(reminders_created),
            'reminders': reminders_created
        })
    
    except Exception as e:
        print(f"Error checking subscription expiry: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/users', methods=['GET', 'OPTIONS'])
@token_required
def main_admin_get_users():
    """Get ALL users in the system with analytics - accessible to owner only"""
    if request.method == 'OPTIONS':
        return '', 200
    try:
        # Verify owner access from token
        users = load_data(USERS_FILE)
        current_user_id = request.user.get('id')
        current_user = next((u for u in users if u.get('id') == current_user_id), None)
        
        if not current_user or current_user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Owner access required'}), 403
        
        # Return ALL users with enhanced analytics
        all_users = []
        for user in load_data(USERS_FILE):
            # Calculate days used
            if user.get('serviceStartDate'):
                start_date = datetime.fromisoformat(user['serviceStartDate'])
                days_used = (datetime.now() - start_date).days + 1
            else:
                days_used = 0
            
            # Create enhanced user object
            enhanced_user = {k: v for k, v in user.items() if k not in ['password', 'pin']}
            enhanced_user['daysUsed'] = days_used
            enhanced_user['planType'] = user.get('planType', 'free_demo')
            enhanced_user['requestedTrial'] = user.get('requestedTrial', False)
            enhanced_user['serviceStartDate'] = user.get('serviceStartDate', user.get('createdAt'))
            all_users.append(enhanced_user)
        
        return jsonify(all_users)
    except Exception as e:
        print(f"Get users error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/sales-all', methods=['GET'])
@token_required
def main_admin_get_all_sales():
    """Get ALL sales from ALL users/accounts"""
    try:
        # Verify owner access
        current_user_id = request.headers.get('X-User-Id')
        users = load_data(USERS_FILE)
        current_user = next((u for u in users if current_user_id and u.get('id') == int(current_user_id)), None)
        
        if not current_user or current_user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Owner access required'}), 403
        
        # Load all sales
        sales = load_data(SALES_FILE)
        
        # Aggregate statistics
        total_sales = sum(s.get('total', 0) for s in sales)
        total_items = sum(len(s.get('items', [])) for s in sales)
        
        return jsonify({
            'sales': sales,
            'total': total_sales,
            'count': len(sales),
            'itemsCount': total_items
        })
    except Exception as e:
        print(f"Get all sales error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/stats', methods=['GET', 'OPTIONS'])
@token_required
def main_admin_get_stats():
    """Get system-wide statistics from ALL users"""
    if request.method == 'OPTIONS':
        return '', 200
    try:
        # Verify owner access from token
        users = load_data(USERS_FILE)
        current_user_id = request.user.get('id')
        current_user = next((u for u in users if u.get('id') == current_user_id), None)
        
        if not current_user or current_user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Owner access required'}), 403
        
        # Load all data
        sales = load_data(SALES_FILE)
        expenses = load_data(EXPENSES_FILE)
        products = load_data(PRODUCTS_FILE)
        all_users = load_data(USERS_FILE)
        
        # Calculate totals
        total_sales = sum(s.get('total', 0) for s in sales)
        total_expenses = sum(e.get('amount', 0) for e in expenses)
        profit = total_sales - total_expenses
        
        return jsonify({
            'totalSales': total_sales,
            'totalExpenses': total_expenses,
            'profit': profit,
            'salesCount': len(sales),
            'expensesCount': len(expenses),
            'productsCount': len(products),
            'usersCount': len(all_users),
            'activeUsers': len([u for u in all_users if u.get('active', True)]),
            'lockedUsers': len([u for u in all_users if u.get('locked', False)])
        })
    except Exception as e:
        print(f"Get stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/activities', methods=['GET'])
@token_required
def main_admin_get_activities():
    """Get ALL activities/events from ALL users"""
    try:
        # Verify owner access
        current_user_id = request.headers.get('X-User-Id')
        users = load_data(USERS_FILE)
        current_user = next((u for u in users if current_user_id and u.get('id') == int(current_user_id)), None)
        
        if not current_user or current_user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Owner access required'}), 403
        
        # Get all sales as activities (each sale is an activity)
        sales = load_data(SALES_FILE)
        activities = []
        
        for sale in sales:
            activities.append({
                'type': 'sale',
                'description': f"Sale of {len(sale.get('items', []))} items",
                'amount': sale.get('total', 0),
                'timestamp': sale.get('createdAt', ''),
                'user': sale.get('soldBy', 'Unknown'),
                'accountId': sale.get('accountId', 'main'),
                'sale': sale
            })
        
        # Add expense activities
        expenses = load_data(EXPENSES_FILE)
        for expense in expenses:
            activities.append({
                'type': 'expense',
                'description': expense.get('description', 'Expense'),
                'amount': expense.get('amount', 0),
                'timestamp': expense.get('createdAt', ''),
                'user': expense.get('addedBy', 'Unknown'),
                'accountId': expense.get('accountId', 'main'),
                'expense': expense
            })
        
        # Sort by timestamp (most recent first)
        activities.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify(activities[:100])  # Return last 100 activities
    except Exception as e:
        print(f"Get activities error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/time-entries-all', methods=['GET'])
@token_required
def main_admin_get_all_time_entries():
    """Get ALL clock in/out time entries from ALL users"""
    try:
        # Verify owner access
        current_user_id = request.headers.get('X-User-Id')
        users = load_data(USERS_FILE)
        current_user = next((u for u in users if current_user_id and u.get('id') == int(current_user_id)), None)
        
        if not current_user or current_user.get('role') != 'owner':
            return jsonify({'error': 'Access denied. Owner access required'}), 403
        
        # Load all time entries
        time_entries = load_data(TIME_ENTRIES_FILE) if os.path.exists(TIME_ENTRIES_FILE) else []
        
        # Group by user
        entries_by_user = {}
        for entry in time_entries:
            user_id = entry.get('userId')
            if user_id not in entries_by_user:
                entries_by_user[user_id] = []
            entries_by_user[user_id].append(entry)
        
        return jsonify({
            'timeEntries': time_entries,
            'entriesByUser': entries_by_user,
            'totalEntries': len(time_entries)
        })
    except Exception as e:
        print(f"Get time entries error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/products', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_products():
    if request.method == 'OPTIONS':
        return '', 200
        
    products = load_data(PRODUCTS_FILE)
    
    if request.method == 'GET':
        # Filter products by accountId for data isolation
        account_id = request.user.get('accountId')
        filtered_products = [p for p in products if p.get('accountId') == account_id]
        return jsonify(filtered_products)
    
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
        'cost': float(data.get('cost', 0)),  # Cost price for inventory tracking
        'quantity': float(data.get('quantity', 0)),  # Changed to float for weight support
        'unit': data.get('unit', 'pcs'),  # 'pcs', 'kg', 'liters', 'grams', etc.
        'unitPrice': float(data.get('unitPrice', data['price'])),  # Price per unit/kg
        'category': data.get('category', 'general'),
        'image': data.get('image', None),  # Base64 image or URL
        'expenseOnly': data.get('expenseOnly', False),  # Hide from cashier
        'visibleToCashier': data.get('visibleToCashier', True),  # Show to cashier
        'isComposite': data.get('isComposite', False) or bool(data.get('recipe')),  # Auto-set if recipe exists
        'ingredients': data.get('ingredients', []),  # List of {productId, quantity}
        'recipe': data.get('recipe', []),  # Used by Recipes.jsx - list of ingredients with names/productIds
        'accountId': request.user['accountId'],
        'createdAt': datetime.now().isoformat()
    }
    
    products.append(product)
    save_data(PRODUCTS_FILE, products)
    
    # OPTIMIZED BROADCAST: Lightweight product creation notification to all dashboards in account
    account_id = request.user['accountId']
    broadcast_update('product_created', {
        'id': product['id'],
        'name': product['name'],
        'quantity': product['quantity'],
        'unit': product['unit'],
        'price': product['price']
    }, account_id=account_id)
    
    print(f"✅ Product created: {product['name']} (ID: {product['id']}, {product['quantity']}{product['unit']})")
    
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
        
        # Broadcast product update to all connected clients
        broadcast_update('product_updated', {
            'product': product,
            'allProducts': products
        })
        
        return jsonify(product)
    
    if request.method == 'DELETE':
        products = [p for p in products if p['id'] != product_id]
        save_data(PRODUCTS_FILE, products)
        
        # Broadcast product deletion to all connected clients
        broadcast_update('product_deleted', {
            'deletedId': product_id,
            'allProducts': products
        })
        
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
    
    # Handle different stock update types (support floats for weight-based products)
    if 'quantity' in data:
        product['quantity'] = float(data['quantity'])
    elif 'increment' in data:
        product['quantity'] = float(product.get('quantity', 0)) + float(data['increment'])
    elif 'decrement' in data:
        product['quantity'] = max(0, float(product.get('quantity', 0)) - float(data['decrement']))
    
    save_data(PRODUCTS_FILE, products)
    
    # OPTIMIZED BROADCAST: Minimal stock update payload to all dashboards in account
    account_id = request.user['accountId']
    broadcast_update('stock_updated', {
        'productId': product_id,
        'newQuantity': product['quantity'],
        'unit': product['unit'],
        'timestamp': datetime.now().isoformat()
    }, account_id=account_id)
    
    print(f"✅ Stock updated: {product['name']} → {product['quantity']}{product['unit']}")
    
    return jsonify(product)

@app.route('/api/products/<int:product_id>/weight-pricing', methods=['GET', 'PUT', 'POST', 'DELETE', 'OPTIONS'])
@token_required
def handle_weight_pricing(product_id):
    """Manage weight-based pricing for products (0.1kg increments)"""
    if request.method == 'OPTIONS':
        return '', 200
    
    products = load_data(PRODUCTS_FILE)
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    # Initialize weightPricing if it doesn't exist
    if 'weightPricing' not in product:
        product['weightPricing'] = {}
    
    if request.method == 'GET':
        # Get all weight-based prices for this product
        return jsonify({
            'productId': product_id,
            'name': product.get('name'),
            'basePrice': product.get('price'),
            'weightPricing': product.get('weightPricing', {})
        })
    
    if request.method == 'POST' or request.method == 'PUT':
        # Add or update weight-based pricing
        data = request.get_json()
        weight = data.get('weight')  # e.g., "0.1", "0.5", "1.0"
        price = data.get('price')
        
        if not weight or price is None:
            return jsonify({'error': 'Weight and price required'}), 400
        
        # Validate weight is valid increment (0.1kg increments)
        try:
            weight_val = float(weight)
            if (weight_val * 10) % 1 != 0:
                return jsonify({'error': 'Weight must be in 0.1kg increments (0.1, 0.2, 0.3, etc)'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid weight value'}), 400
        
        product['weightPricing'][str(weight)] = float(price)
        save_data(PRODUCTS_FILE, products)
        
        # Broadcast update
        broadcast_update('weight_pricing_updated', {
            'productId': product_id,
            'product': product,
            'allProducts': products
        })
        
        return jsonify({
            'message': 'Weight pricing updated',
            'weight': str(weight),
            'price': float(price),
            'allPrices': product['weightPricing']
        })
    
    if request.method == 'DELETE':
        # Delete weight-based pricing
        data = request.get_json()
        weight = data.get('weight')
        
        if not weight:
            return jsonify({'error': 'Weight required'}), 400
        
        if str(weight) in product['weightPricing']:
            del product['weightPricing'][str(weight)]
            save_data(PRODUCTS_FILE, products)
            
            # Broadcast update
            broadcast_update('weight_pricing_deleted', {
                'productId': product_id,
                'product': product,
                'allProducts': products
            })
        
        return jsonify({
            'message': 'Weight pricing deleted',
            'remainingPrices': product['weightPricing']
        })

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    users = load_data(USERS_FILE)
    
    if request.method == 'GET':
        # Filter users by accountId for data isolation
        account_id = request.user.get('accountId')
        filtered_users = [u for u in users if u.get('accountId') == account_id]
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in filtered_users])
    
    data = request.get_json()
    # Normalize email to lowercase and ensure password is provided
    email = data['email'].strip().lower() if data.get('email') else ''
    password = data.get('password', '').strip()
    
    if not email or not password:
        return jsonify({'error': 'Email and password are required'}), 400
    
    # Check if user already exists (case-insensitive)
    if any(u.get('email', '').lower() == email for u in users):
        return jsonify({'error': 'User with this email already exists'}), 400
    
    # Check cashier limit for basic plan
    account_id = request.user['accountId']
    admin_user = next((u for u in users if u.get('accountId') == account_id and u.get('role') == 'admin'), None)
    
    if admin_user:
        max_cashiers = admin_user.get('maxCashiers')
        # If maxCashiers is set (not None), count existing cashiers and check limit
        if max_cashiers is not None:
            # Count existing cashiers (non-admin users) for this account
            existing_cashiers = [u for u in users if u.get('accountId') == account_id and u.get('role') == 'cashier']
            if len(existing_cashiers) >= max_cashiers:
                return jsonify({
                    'error': f'Cashier limit reached. Your plan allows maximum {max_cashiers} cashier(s). Current cashiers: {len(existing_cashiers)}'
                }), 403
    
    user = {
        'id': get_next_id(users),
        'email': email,
        'password': password,
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

@app.route('/api/users/<int:user_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_user(user_id):
    """Delete a single user"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        users = load_data(USERS_FILE)
        user_to_delete = next((u for u in users if u['id'] == user_id), None)
        
        if not user_to_delete:
            return jsonify({'error': 'User not found'}), 404
        
        # Prevent deleting owner/admin (only non-owner can delete)
        if user_to_delete.get('role') == 'owner':
            return jsonify({'error': 'Cannot delete owner account'}), 403
        
        # Remove the user
        users = [u for u in users if u['id'] != user_id]
        save_data(USERS_FILE, users)
        
        # Broadcast update
        broadcast_update('user_deleted', {'userId': user_id})
        
        return jsonify({'success': True, 'message': 'User deleted successfully'})
    except Exception as e:
        print(f"Delete user error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/users/bulk-delete', methods=['POST', 'OPTIONS'])
@token_required
def bulk_delete_users():
    """Delete multiple users (except owner)"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        user_ids = data.get('userIds', [])
        
        if not user_ids:
            return jsonify({'error': 'No users to delete'}), 400
        
        users = load_data(USERS_FILE)
        original_count = len(users)
        
        # Filter out the users to delete (but keep owner)
        users = [u for u in users if u['id'] not in user_ids or u.get('role') == 'owner']
        deleted_count = original_count - len(users)
        
        save_data(USERS_FILE, users)
        
        # Broadcast update
        broadcast_update('users_bulk_deleted', {'deletedCount': deleted_count, 'userIds': user_ids})
        
        return jsonify({'success': True, 'message': f'{deleted_count} users deleted', 'deletedCount': deleted_count})
    except Exception as e:
        print(f"Bulk delete users error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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

@app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST', 'OPTIONS'])
@token_required
def toggle_user_lock(user_id):
    """Lock or unlock a user account"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        locked = data.get('locked', False)
        
        users = load_data(USERS_FILE)
        user = next((u for u in users if u.get('id') == user_id), None)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        user['active'] = not locked
        save_data(USERS_FILE, users)
        
        # Broadcast update
        broadcast_update('user_lock_toggled', {
            'userId': user_id,
            'locked': locked,
            'user': {k: v for k, v in user.items() if k not in ['password', 'pin']}
        })
        
        return jsonify({
            'success': True,
            'user_id': user_id,
            'locked': locked,
            'message': f'User {"locked" if locked else "unlocked"} successfully'
        })
    except Exception as e:
        print(f"Toggle user lock error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/main-admin/users/<int:user_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def main_admin_delete_user(user_id):
    """Main admin delete user endpoint"""
    try:
        users = load_data(USERS_FILE)
        
        # Find user to delete
        user_to_delete = next((u for u in users if u.get('id') == user_id), None)
        if not user_to_delete:
            return jsonify({'error': 'User not found'}), 404
        
        # Prevent deleting the main admin user
        if user_to_delete.get('isMainAdmin'):
            return jsonify({'error': 'Cannot delete main admin user'}), 403
        
        # Remove user from list
        users = [u for u in users if u.get('id') != user_id]
        save_data(USERS_FILE, users)
        
        # Broadcast deletion event
        broadcast_update('user_deleted_by_admin', {
            'userId': user_id,
            'userName': user_to_delete.get('name', 'Unknown'),
            'email': user_to_delete.get('email')
        })
        
        return jsonify({
            'success': True,
            'message': f'User {user_to_delete.get("name")} deleted successfully',
            'deletedUser': {k: v for k, v in user_to_delete.items() if k not in ['password', 'pin']}
        })
    except Exception as e:
        print(f"Main admin delete user error: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================
# OPTIMIZED STOCK MANAGEMENT FUNCTIONS
# ============================================================
# Using StockDeductionEngine from stock_engine.py for <200ms performance

def validate_and_deduct_stock(products, expenses, items, sale_items_deductions):
    """
    Backward compatible wrapper for old code.
    Uses optimized StockDeductionEngine internally.
    
    Returns: (bool, error_message, deductions)
    """
    engine = StockDeductionEngine(products, expenses)
    is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(items)
    
    if is_valid:
        # Apply deductions to the products list
        engine.apply_deductions(deductions)
    
    return is_valid, error_msg, deductions

def apply_stock_deductions(products, expenses, deductions):
    """Backward compatible wrapper - deductions already applied in engine."""
    # Since the optimized engine modifies products in-place during validate_and_deduct_stock,
    # this is now a no-op. Kept for backward compatibility.
    return True

def check_low_stock_warnings(products, account_id=None, threshold=1.0):
    """
    Check for products with stock below threshold.
    Returns list of warnings for admin/cashier alerts.
    """
    warnings = []
    for product in products:
        if account_id and product.get('accountId') != account_id:
            continue
        
        quantity = float(product.get('quantity', 0))
        # Only warn for non-zero stock below threshold
        if 0 < quantity < threshold:
            severity = 'CRITICAL' if quantity < 0.1 else 'WARNING'
            warnings.append({
                'productId': product['id'],
                'productName': product['name'],
                'currentStock': quantity,
                'unit': product.get('unit', 'pcs'),
                'threshold': threshold,
                'severity': severity,
                'timestamp': datetime.now().isoformat(),
                'category': product.get('category', 'general')
            })
    
    return warnings

@app.route('/api/products/low-stock-warnings', methods=['GET', 'OPTIONS'])
@token_required
def get_low_stock_warnings():
    """Get all low stock warnings for current account"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        products = load_data(PRODUCTS_FILE)
        account_id = request.user.get('accountId')
        threshold = request.args.get('threshold', 1.0, type=float)
        
        warnings = check_low_stock_warnings(products, account_id, threshold)
        
        return jsonify({
            'warnings': warnings,
            'total_warnings': len(warnings),
            'critical_count': sum(1 for w in warnings if w['severity'] == 'CRITICAL'),
            'warning_count': sum(1 for w in warnings if w['severity'] == 'WARNING')
        })
    
    except Exception as e:
        print(f"Error fetching low stock warnings: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/products/stock-status', methods=['GET', 'OPTIONS'])
@token_required
def get_stock_status():
    """Get detailed stock status for all products including composite deductions"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        products = load_data(PRODUCTS_FILE)
        account_id = request.user.get('accountId')
        
        # Filter by account and build detailed stock view
        stock_data = []
        
        for product in products:
            if product.get('accountId') != account_id:
                continue
            
            product_info = {
                'id': product['id'],
                'name': product['name'],
                'quantity': float(product.get('quantity', 0)),
                'unit': product.get('unit', 'pcs'),
                'price': float(product.get('price', 0)),
                'cost': float(product.get('cost', 0)),
                'category': product.get('category', 'general'),
                'isComposite': product.get('isComposite', False),
                'expenseOnly': product.get('expenseOnly', False),
                'visibleToCashier': product.get('visibleToCashier', True)
            }
            
            # Add ingredient information for composite products
            if product.get('isComposite'):
                ingredients = product.get('recipe', product.get('ingredients', []))
                product_info['ingredients'] = []
                
                for ingredient in ingredients:
                    ingredient_id = ingredient.get('productId')
                    ingredient_product = None
                    
                    if ingredient_id:
                        ingredient_product = next((p for p in products if p['id'] == ingredient_id), None)
                    elif ingredient.get('name'):
                        ingredient_product = next((p for p in products if p['name'].lower() == ingredient['name'].lower()), None)
                    
                    if ingredient_product:
                        ingredient_qty = float(ingredient.get('quantity', 0))
                        product_info['ingredients'].append({
                            'id': ingredient_product['id'],
                            'name': ingredient_product['name'],
                            'quantity_per_unit': ingredient_qty,
                            'unit': ingredient_product.get('unit', 'pcs'),
                            'current_stock': float(ingredient_product.get('quantity', 0)),
                            'type': 'expense' if ingredient_product.get('expenseOnly') else 'raw_material'
                        })
            
            stock_data.append(product_info)
        
        return jsonify(stock_data)
    
    except Exception as e:
        print(f"Error fetching stock status: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sales', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_sales():
    """Handle sales - GET returns sales list, POST creates sale with OPTIMIZED atomic stock deduction"""
    if request.method == 'OPTIONS':
        return '', 200
    
    sales = load_data(SALES_FILE)
    
    if request.method == 'GET':
        # Filter sales by accountId for data isolation
        account_id = request.user.get('accountId')
        filtered_sales = [s for s in sales if s.get('accountId') == account_id]
        return jsonify(filtered_sales)
    
    # POST - Create new sale with OPTIMIZED atomic stock deduction
    try:
        start_time = time.time()
        data = request.get_json()
        
        if not data:
            print("❌ No JSON data in request")
            return jsonify({'error': 'No data provided', 'message': 'Request body is empty'}), 400
        
        products = load_data(PRODUCTS_FILE)
        expenses = load_data(EXPENSES_FILE)
        
        # Validate request
        if not data.get('items') or len(data['items']) == 0:
            return jsonify({'error': 'At least one item is required for a sale'}), 400
        
        # OPTIMIZED VALIDATION: Use stock engine for fast validation + deductions
        engine = StockDeductionEngine(products, expenses)
        is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(data.get('items', []))
        
        if not is_valid:
            return jsonify({
                'error': error_msg,
                'message': 'Sale validation failed'
            }), 400
        
        # Apply deductions to products (in-memory)
        if not engine.apply_deductions(deductions):
            return jsonify({
                'error': 'Failed to apply deductions',
                'message': 'Please try again'
            }), 500
        
        # SINGLE FILE WRITE: Save updated products
        save_data(PRODUCTS_FILE, products)
        
        # Auto-create expense entries for ingredient deductions (if any)
        expenses = create_auto_expenses_for_sale(deductions, products, expenses, request.user['accountId'])
        save_data(EXPENSES_FILE, expenses)
        
        # Create sale record
        sale = {
            'id': get_next_id(sales),
            'items': data['items'],
            'total': float(data['total']),
            'discount': float(data.get('discount', 0)),
            'tax': float(data.get('tax', 0)),
            'taxType': data.get('taxType', 'exclusive'),
            'paymentMethod': data.get('paymentMethod', 'cash'),
            'accountId': request.user['accountId'],
            'cashierId': request.user['id'],
            'cashierName': request.user.get('name', 'Unknown'),
            'stockDeductions': deductions,
            'createdAt': datetime.now().isoformat()
        }
        
        sales.append(sale)
        save_data(SALES_FILE, sales)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Warn if processing took too long
        if elapsed_ms > 5000:
            print(f"⚠️ WARNING: Sale processing took {elapsed_ms:.0f}ms (slow database?)")
        
        # Check for low stock warnings
        warnings = check_low_stock_warnings(products, request.user['accountId'])
        
        # EFFICIENT BROADCAST: Single notification with updated products list
        account_id = request.user['accountId']
        
        # Get updated products to send to connected clients
        updated_products = [p for p in products if p.get('accountId') == account_id]
        
        broadcast_update('sale_completed', {
            'saleId': sale['id'],
            'deductions': deductions,
            'timestamp': datetime.now().isoformat(),
            'processingTime': f"{elapsed_ms:.0f}ms",
            'lowStockWarnings': warnings if warnings else None,
            'updatedProducts': updated_products  # Send updated product list for UI refresh
        }, account_id=account_id)
        
        print(f"✅ Sale #{sale['id']} completed in {elapsed_ms:.0f}ms - stock auto-deducted")
        
        return jsonify({
            'success': True,
            'sale': sale,
            'deductions': deductions,
            'processingTime': f"{elapsed_ms:.0f}ms",
            'lowStockWarnings': warnings,
            'updatedProducts': updated_products,  # Include updated products in response
            'message': f"Sale completed in {elapsed_ms:.0f}ms ✓"
        })
    
    except Exception as e:
        print(f"❌ Sale creation error: {str(e)}")
        return jsonify({'error': 'Failed to create sale', 'message': str(e)}), 500

@app.route('/api/admin-complete-sale', methods=['POST', 'OPTIONS'])
@token_required
def admin_complete_sale():
    """Admin dashboard - Complete sale with IMMEDIATE sharp stock deduction"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        start_time = time.time()
        data = request.get_json()
        products = load_data(PRODUCTS_FILE)
        expenses = load_data(EXPENSES_FILE)
        sales = load_data(SALES_FILE)
        
        # Validate request
        if not data.get('items') or len(data['items']) == 0:
            return jsonify({'error': 'At least one item is required for a sale'}), 400
        
        # OPTIMIZED VALIDATION: Use stock engine
        engine = StockDeductionEngine(products, expenses)
        is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(data.get('items', []))
        
        if not is_valid:
            return jsonify({
                'error': error_msg,
                'message': 'Sale validation failed'
            }), 400
        
        # Apply deductions to products (in-memory)
        if not engine.apply_deductions(deductions):
            return jsonify({
                'error': 'Failed to apply deductions',
                'message': 'Please try again'
            }), 500
        
        # SINGLE FILE WRITE: Save updated products immediately
        save_data(PRODUCTS_FILE, products)
        
        # Auto-create expense entries for ingredient deductions (if any)
        expenses = create_auto_expenses_for_sale(deductions, products, expenses, request.user['accountId'])
        save_data(EXPENSES_FILE, expenses)
        
        # Create sale record
        sale = {
            'id': get_next_id(sales),
            'items': data['items'],
            'total': float(data['total']),
            'discount': float(data.get('discount', 0)),
            'tax': float(data.get('tax', 0)),
            'taxType': data.get('taxType', 'exclusive'),
            'paymentMethod': data.get('paymentMethod', 'cash'),
            'accountId': request.user['accountId'],
            'cashierId': request.user['id'],
            'cashierName': request.user.get('name', 'Unknown'),
            'completedBy': 'admin',
            'stockDeductions': deductions,
            'createdAt': datetime.now().isoformat()
        }
        
        sales.append(sale)
        save_data(SALES_FILE, sales)
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Warn if processing took too long
        if elapsed_ms > 5000:
            print(f"⚠️ WARNING: Sale processing took {elapsed_ms:.0f}ms (slow database?)")
        
        # Check for low stock warnings
        warnings = check_low_stock_warnings(products, request.user['accountId'])
        
        # EFFICIENT BROADCAST: Dual notification for all dashboards
        account_id = request.user['accountId']
        
        # Notify cashier dashboard of immediate deduction
        broadcast_update('sale_completed', {
            'saleId': sale['id'],
            'deductions': deductions,
            'source': 'admin',
            'timestamp': datetime.now().isoformat(),
            'lowStockWarnings': warnings if warnings else None,
            'updatedProducts': [p for p in products if p.get('accountId') == account_id]
        }, account_id=account_id)
        
        # Notify admin dashboard of completed sale
        broadcast_update('admin_sale_completed', {
            'saleId': sale['id'],
            'totalItems': len(deductions['products']),
            'totalAmount': sale['total'],
            'processingTime': f"{elapsed_ms:.0f}ms",
            'lowStockWarnings': warnings if warnings else None,
            'updatedProducts': [p for p in products if p.get('accountId') == account_id]
        }, account_id=account_id)
        
        print(f"✅ Admin Sale #{sale['id']} completed in {elapsed_ms:.0f}ms")
        
        return jsonify({
            'success': True,
            'sale': sale,
            'deductions': deductions,
            'processingTime': f"{elapsed_ms:.0f}ms",
            'lowStockWarnings': warnings,
            'updatedProducts': [p for p in products if p.get('accountId') == request.user['accountId']],  # Include updated products
            'message': f"Sale #{sale['id']} completed in {elapsed_ms:.0f}ms ✓"
        })
    
    except Exception as e:
        print(f"❌ Admin sale error: {str(e)}")
        return jsonify({'error': 'Failed to complete sale', 'message': str(e)}), 500


@app.route('/api/sales/<int:sale_id>', methods=['DELETE', 'OPTIONS'])
@token_required
def delete_sale(sale_id):
    """Delete a single sale"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        sales = load_data(SALES_FILE)
        sale_to_delete = next((s for s in sales if s['id'] == sale_id), None)
        
        if not sale_to_delete:
            return jsonify({'error': 'Sale not found'}), 404
        
        # Remove the sale
        sales = [s for s in sales if s['id'] != sale_id]
        save_data(SALES_FILE, sales)
        
        # Broadcast update
        broadcast_update('sale_deleted', {'saleId': sale_id})
        
        return jsonify({'success': True, 'message': 'Sale deleted successfully'})
    except Exception as e:
        print(f"Delete sale error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/sales/bulk-delete', methods=['POST', 'OPTIONS'])
@token_required
def bulk_delete_sales():
    """Delete multiple sales"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        sale_ids = data.get('saleIds', [])
        
        if not sale_ids:
            return jsonify({'error': 'No sales to delete'}), 400
        
        sales = load_data(SALES_FILE)
        original_count = len(sales)
        
        # Filter out the sales to delete
        sales = [s for s in sales if s['id'] not in sale_ids]
        deleted_count = original_count - len(sales)
        
        save_data(SALES_FILE, sales)
        
        # Broadcast update
        broadcast_update('sales_bulk_deleted', {'deletedCount': deleted_count, 'saleIds': sale_ids})
        
        return jsonify({'success': True, 'message': f'{deleted_count} sales deleted', 'deletedCount': deleted_count})
    except Exception as e:
        print(f"Bulk delete sales error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET', 'OPTIONS'])
@token_required
def stats():
    if request.method == 'OPTIONS':
        return '', 200
    
    sales = load_data(SALES_FILE)
    products = load_data(PRODUCTS_FILE)
    expenses_data = load_data(EXPENSES_FILE)
    
    # Filter by accountId for data isolation
    account_id = request.user.get('accountId')
    filtered_sales = [s for s in sales if s.get('accountId') == account_id]
    filtered_products = [p for p in products if p.get('accountId') == account_id]
    filtered_expenses = [e for e in expenses_data if e.get('accountId') == account_id]
    
    total_sales = sum(s.get('total', 0) for s in filtered_sales)
    total_expenses = sum(e.get('amount', 0) for e in filtered_expenses)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': total_expenses,
        'profit': total_sales - total_expenses,
        'productCount': len(filtered_products)
    })

@app.route('/api/reminders/today', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def reminders_today():
    """Get reminders or send a reminder message to all dashboards in account"""
    if request.method == 'OPTIONS':
        return '', 200
    
    reminders = load_data(REMINDERS_FILE)
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        # Get today's reminders for this account
        today = datetime.now().date().isoformat()
        filtered_reminders = [r for r in reminders 
                            if r.get('accountId') == account_id 
                            and r.get('date', '').startswith(today)]
        return jsonify(filtered_reminders)
    
    # POST - Send reminder message to all dashboards in account
    try:
        data = request.get_json()
        reminder = {
            'id': get_next_id(reminders),
            'accountId': account_id,
            'message': data.get('message', ''),
            'priority': data.get('priority', 'normal'),  # 'low', 'normal', 'high', 'urgent'
            'target': data.get('target', 'all'),  # 'all', 'cashiers', 'admins'
            'sentBy': request.user.get('name', 'Unknown'),
            'date': datetime.now().date().isoformat(),
            'timestamp': datetime.now().isoformat(),
            'createdAt': datetime.now().isoformat()
        }
        
        reminders.append(reminder)
        save_data(REMINDERS_FILE, reminders)
        
        # BROADCAST: Send reminder to all dashboards in this account IMMEDIATELY
        broadcast_update('REMINDER_ALERT', {
            'id': reminder['id'],
            'message': reminder['message'],
            'priority': reminder['priority'],
            'sentBy': reminder['sentBy'],
            'timestamp': reminder['timestamp']
        }, account_id=account_id)
        
        print(f"✅ Reminder sent to all dashboards in account {account_id}: {reminder['message']}")
        
        return jsonify({
            'success': True,
            'reminder': reminder,
            'message': 'Reminder delivered to all dashboards'
        })
    
    except Exception as e:
        print(f"❌ Reminder error: {str(e)}")
        return jsonify({'error': str(e)}), 500

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
    
    expenses_data = load_data(EXPENSES_FILE)
    
    if request.method == 'GET':
        # Filter expenses by accountId for data isolation
        account_id = request.user.get('accountId')
        filtered_expenses = [e for e in expenses_data if e.get('accountId') == account_id]
        return jsonify(filtered_expenses)
    
    # POST - Create new expense
    data = request.get_json()
    expense = {
        'id': get_next_id(expenses_data),
        'description': data.get('description', ''),
        'amount': float(data.get('amount', 0)),
        'accountId': request.user['accountId'],
        'createdAt': datetime.now().isoformat()
    }
    
    expenses_data.append(expense)
    save_data(EXPENSES_FILE, expenses_data)
    
    return jsonify(expense)

@app.route('/api/batches', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def batches():
    if request.method == 'OPTIONS':
        return '', 200
    
    if request.method == 'GET':
        # Load and return all batches
        batches_data = load_data(BATCHES_FILE)
        return jsonify(batches_data)
    
    # POST - Create new batch
    data = request.get_json()
    batches_data = load_data(BATCHES_FILE)
    
    batch = {
        'id': max([b.get('id', 0) for b in batches_data], default=0) + 1,
        'productId': int(data.get('productId')),
        'quantity': int(data.get('quantity', 0)),
        'expiryDate': data.get('expiryDate', ''),
        'batchNumber': data.get('batchNumber', f'BATCH-{datetime.now().strftime("%Y%m%d%H%M%S")}'),
        'cost': float(data.get('cost', 0)),
        'createdAt': datetime.now().isoformat()
    }
    
    batches_data.append(batch)
    save_data(BATCHES_FILE, batches_data)
    
    # Also update product quantity in products.json
    products = load_data(PRODUCTS_FILE)
    product = next((p for p in products if p['id'] == batch['productId']), None)
    if product:
        product['quantity'] = product.get('quantity', 0) + batch['quantity']
        save_data(PRODUCTS_FILE, products)
        
        # Broadcast stock update to all connected clients
        broadcast_update('stock_updated', {
            'id': batch['productId'],
            'product': product,
            'allProducts': products
        })
    
    return jsonify(batch), 201

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
    
    discounts = load_data(DISCOUNTS_FILE)
    
    if request.method == 'GET':
        return jsonify(discounts)
    
    data = request.get_json()
    
    if request.method == 'POST':
        discount = {
            'id': max([d.get('id', 0) for d in discounts], default=0) + 1,
            'name': data.get('name', ''),
            'type': data.get('type', 'percentage'),
            'value': float(data.get('value', 0)),
            'description': data.get('description', ''),
            'active': data.get('active', True),
            'createdAt': datetime.now().isoformat()
        }
        discounts.append(discount)
        save_data(DISCOUNTS_FILE, discounts)
        broadcast_update('discount_updated', {'discounts': discounts})
        return jsonify(discount), 201
    
    elif request.method == 'PUT':
        discount_id = int(data.get('id'))
        discount = next((d for d in discounts if d['id'] == discount_id), None)
        if discount:
            discount.update({
                'name': data.get('name', discount.get('name')),
                'type': data.get('type', discount.get('type')),
                'value': float(data.get('value', discount.get('value', 0))),
                'description': data.get('description', discount.get('description')),
                'active': data.get('active', discount.get('active'))
            })
            save_data(DISCOUNTS_FILE, discounts)
            broadcast_update('discount_updated', {'discounts': discounts})
            return jsonify(discount)
        return jsonify({'error': 'Discount not found'}), 404
    
    elif request.method == 'DELETE':
        discount_id = int(data.get('id'))
        discounts = [d for d in discounts if d['id'] != discount_id]
        save_data(DISCOUNTS_FILE, discounts)
        broadcast_update('discount_updated', {'discounts': discounts})
        return jsonify({'status': 'deleted'})

@app.route('/api/vendors', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_vendors():
    """Handle vendor management - GET returns vendors list, POST creates vendor"""
    if request.method == 'OPTIONS':
        return '', 200
    
    vendors = load_data(VENDORS_FILE)
    
    if request.method == 'GET':
        # Filter vendors by accountId for data isolation
        account_id = request.user.get('accountId')
        filtered_vendors = [v for v in vendors if v.get('accountId') == account_id]
        return jsonify(filtered_vendors)
    
    # POST - Create new vendor
    try:
        data = request.get_json()
        
        if not data.get('name'):
            return jsonify({'error': 'Vendor name is required'}), 400
        
        vendor = {
            'id': get_next_id(vendors),
            'name': data.get('name'),
            'email': data.get('email', ''),
            'phone': data.get('phone', ''),
            'address': data.get('address', ''),
            'city': data.get('city', ''),
            'country': data.get('country', ''),
            'products': data.get('products', ''),
            'accountId': request.user['accountId'],
            'createdAt': datetime.now().isoformat()
        }
        
        vendors.append(vendor)
        save_data(VENDORS_FILE, vendors)
        
        return jsonify(vendor), 201
    
    except Exception as e:
        print(f"❌ Vendor creation error: {str(e)}")
        return jsonify({'error': 'Failed to create vendor', 'message': str(e)}), 500

@app.route('/api/vendors/<int:vendor_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_vendor(vendor_id):
    """Handle individual vendor operations"""
    if request.method == 'OPTIONS':
        return '', 200
    
    vendors = load_data(VENDORS_FILE)
    vendor = next((v for v in vendors if v['id'] == vendor_id), None)
    
    if not vendor:
        return jsonify({'error': 'Vendor not found'}), 404
    
    # Check account isolation
    if vendor.get('accountId') != request.user.get('accountId'):
        return jsonify({'error': 'Access denied'}), 403
    
    if request.method == 'GET':
        return jsonify(vendor)
    
    if request.method == 'PUT':
        try:
            data = request.get_json()
            
            # Update allowed fields
            vendor['name'] = data.get('name', vendor['name'])
            vendor['email'] = data.get('email', vendor['email'])
            vendor['phone'] = data.get('phone', vendor['phone'])
            vendor['address'] = data.get('address', vendor['address'])
            vendor['city'] = data.get('city', vendor['city'])
            vendor['country'] = data.get('country', vendor['country'])
            vendor['products'] = data.get('products', vendor['products'])
            vendor['updatedAt'] = datetime.now().isoformat()
            
            save_data(VENDORS_FILE, vendors)
            return jsonify(vendor)
        
        except Exception as e:
            print(f"❌ Vendor update error: {str(e)}")
            return jsonify({'error': 'Failed to update vendor'}), 500
    
    if request.method == 'DELETE':
        try:
            vendors = [v for v in vendors if v['id'] != vendor_id]
            save_data(VENDORS_FILE, vendors)
            return jsonify({'status': 'deleted'})
        
        except Exception as e:
            print(f"❌ Vendor deletion error: {str(e)}")
            return jsonify({'error': 'Failed to delete vendor'}), 500

@app.route('/api/raw-materials', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_raw_materials():
    """Manage raw materials for composite products with decimal precision"""
    if request.method == 'OPTIONS':
        return '', 200
    
    materials = load_data(RAW_MATERIALS_FILE)
    
    if request.method == 'GET':
        return jsonify(materials)
    
    # POST - Create new raw material
    data = request.get_json()
    material = {
        'id': get_next_id(materials),
        'name': data.get('name'),
        'quantity': float(data.get('quantity', 0)),  # Decimal precision
        'unit': data.get('unit', 'kg'),  # kg, g, L, ml, pcs
        'cost_per_unit': float(data.get('cost_per_unit', 0)),  # For COGS calculation
        'reorder_level': float(data.get('reorder_level', 0)),
        'category': data.get('category', 'ingredient'),
        'createdAt': datetime.now().isoformat(),
        'updatedAt': datetime.now().isoformat()
    }
    materials.append(material)
    save_data(RAW_MATERIALS_FILE, materials)
    
    broadcast_update('raw_material_created', {'materials': materials})
    return jsonify(material), 201

@app.route('/api/raw-materials/<int:material_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_raw_material(material_id):
    """Update or delete a raw material"""
    if request.method == 'OPTIONS':
        return '', 200
    
    materials = load_data(RAW_MATERIALS_FILE)
    material = next((m for m in materials if m['id'] == material_id), None)
    
    if not material:
        return jsonify({'error': 'Raw material not found'}), 404
    
    if request.method == 'GET':
        return jsonify(material)
    
    if request.method == 'DELETE':
        materials = [m for m in materials if m['id'] != material_id]
        save_data(RAW_MATERIALS_FILE, materials)
        broadcast_update('raw_material_deleted', {'materials': materials})
        return jsonify({'message': 'Raw material deleted'}), 200
    
    if request.method == 'PUT':
        data = request.get_json()
        material.update({
            'name': data.get('name', material.get('name')),
            'quantity': float(data.get('quantity', material.get('quantity', 0))),
            'unit': data.get('unit', material.get('unit')),
            'cost_per_unit': float(data.get('cost_per_unit', material.get('cost_per_unit', 0))),
            'reorder_level': float(data.get('reorder_level', material.get('reorder_level', 0))),
            'category': data.get('category', material.get('category')),
            'updatedAt': datetime.now().isoformat()
        })
        save_data(RAW_MATERIALS_FILE, materials)
        broadcast_update('raw_material_updated', {'materials': materials})
        return jsonify(material)

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

# Time Tracking Endpoints for Clock In/Out
@app.route('/api/time-entries', methods=['GET', 'POST', 'OPTIONS'])
@token_required
def handle_time_entries():
    """Get all time entries or create a new one"""
    if request.method == 'OPTIONS':
        return '', 200
    
    time_entries = load_data(TIME_ENTRIES_FILE)
    
    if request.method == 'GET':
        return jsonify(time_entries)
    
    # POST - Clock in/out
    data = request.get_json()
    action = data.get('action', 'clock_in')  # 'clock_in' or 'clock_out'
    
    cashier_id = request.user.get('id')
    cashier_name = request.user.get('name', 'Unknown')
    
    if action == 'clock_in':
        # Create new time entry
        entry = {
            'id': get_next_id(time_entries),
            'cashierId': cashier_id,
            'cashierName': cashier_name,
            'cashierEmail': request.user.get('email'),
            'clockInTime': datetime.now().isoformat(),
            'clockOutTime': None,
            'duration': None,  # In minutes
            'status': 'clocked_in',
            'date': datetime.now().strftime('%Y-%m-%d'),
            'createdAt': datetime.now().isoformat()
        }
        
        time_entries.append(entry)
        save_data(TIME_ENTRIES_FILE, time_entries)
        
        # Broadcast clock in to all connected clients
        broadcast_update('cashier_clocked_in', {
            'entry': entry,
            'allTimeEntries': time_entries
        })
        
        return jsonify(entry), 201
    
    elif action == 'clock_out':
        # Find the latest open time entry for this cashier
        open_entry = next(
            (e for e in reversed(time_entries) if e.get('cashierId') == cashier_id and e.get('status') == 'clocked_in'),
            None
        )
        
        if not open_entry:
            return jsonify({'error': 'No active clock in found'}), 404
        
        # Calculate duration
        clock_in = datetime.fromisoformat(open_entry['clockInTime'])
        clock_out = datetime.now()
        duration = int((clock_out - clock_in).total_seconds() / 60)  # Duration in minutes
        
        open_entry['clockOutTime'] = clock_out.isoformat()
        open_entry['duration'] = duration
        open_entry['status'] = 'clocked_out'
        
        save_data(TIME_ENTRIES_FILE, time_entries)
        
        # Broadcast clock out to all connected clients
        broadcast_update('cashier_clocked_out', {
            'entry': open_entry,
            'allTimeEntries': time_entries
        })
        
        return jsonify(open_entry)
    
    else:
        return jsonify({'error': 'Invalid action. Use clock_in or clock_out'}), 400

@app.route('/api/time-entries/<int:entry_id>', methods=['GET', 'PUT', 'DELETE', 'OPTIONS'])
@token_required
def handle_time_entry(entry_id):
    """Get, update, or delete a specific time entry"""
    if request.method == 'OPTIONS':
        return '', 200
    
    time_entries = load_data(TIME_ENTRIES_FILE)
    entry = next((e for e in time_entries if e['id'] == entry_id), None)
    
    if not entry:
        return jsonify({'error': 'Time entry not found'}), 404
    
    if request.method == 'GET':
        return jsonify(entry)
    
    if request.method == 'PUT':
        data = request.get_json()
        entry.update(data)
        save_data(TIME_ENTRIES_FILE, time_entries)
        
        # Broadcast time entry update
        broadcast_update('time_entry_updated', {
            'entry': entry,
            'allTimeEntries': time_entries
        })
        
        return jsonify(entry)
    
    if request.method == 'DELETE':
        time_entries = [e for e in time_entries if e['id'] != entry_id]
        save_data(TIME_ENTRIES_FILE, time_entries)
        
        # Broadcast time entry deletion
        broadcast_update('time_entry_deleted', {
            'deletedId': entry_id,
            'allTimeEntries': time_entries
        })
        
        return jsonify({'message': 'Time entry deleted'})

@app.route('/api/time-entries/cashier/<int:cashier_id>', methods=['GET', 'OPTIONS'])
@token_required
def get_cashier_time_entries(cashier_id):
    """Get all time entries for a specific cashier"""
    if request.method == 'OPTIONS':
        return '', 200
    
    time_entries = load_data(TIME_ENTRIES_FILE)
    cashier_entries = [e for e in time_entries if e.get('cashierId') == cashier_id]
    
    return jsonify(cashier_entries)

@app.route('/api/time-entries/today', methods=['GET', 'OPTIONS'])
@token_required
def get_today_time_entries():
    """Get all time entries for today"""
    if request.method == 'OPTIONS':
        return '', 200
    
    time_entries = load_data(TIME_ENTRIES_FILE)
    today = datetime.now().strftime('%Y-%m-%d')
    today_entries = [e for e in time_entries if e.get('date') == today]
    
    return jsonify(today_entries)

@app.route('/api/clear-data', methods=['POST', 'OPTIONS'])
@token_required
def clear_data():
    """Clear all system data: products, sales, expenses, users, history, batches, time entries, etc."""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.get_json()
        clear_type = data.get('type', 'all')
        
        files_cleared = []
        
        # Clear products
        if clear_type in ['products', 'all']:
            save_data(PRODUCTS_FILE, [])
            files_cleared.append('products')
        
        # Clear sales (main transaction history)
        if clear_type in ['sales', 'all']:
            save_data(SALES_FILE, [])
            files_cleared.append('sales')
        
        # Clear expenses
        if clear_type in ['expenses', 'all']:
            save_data(EXPENSES_FILE, [])
            files_cleared.append('expenses')
        
        # Clear users
        if clear_type in ['users', 'all']:
            save_data(USERS_FILE, [])
            files_cleared.append('users')
        
        # Clear batches (inventory history)
        if clear_type in ['history', 'all']:
            save_data(BATCHES_FILE, [])
            files_cleared.append('batches')
        
        # Clear time entries (employee time tracking history)
        if clear_type in ['history', 'all']:
            save_data(TIME_ENTRIES_FILE, [])
            files_cleared.append('time_entries')
        
        # Clear discounts
        if clear_type in ['all']:
            save_data(DISCOUNTS_FILE, [])
            files_cleared.append('discounts')
        
        # Clear credit requests
        if clear_type in ['all']:
            save_data(CREDIT_REQUESTS_FILE, [])
            files_cleared.append('credit_requests')
        
        # Clear reminders
        if clear_type in ['all']:
            save_data(REMINDERS_FILE, [])
            files_cleared.append('reminders')
        
        # Clear recipes/BOM data
        if clear_type in ['products', 'all']:
            save_data(RECIPES_FILE, [])
            files_cleared.append('recipes')
        
        # Clear raw materials
        if clear_type in ['products', 'all']:
            save_data(RAW_MATERIALS_FILE, [])
            files_cleared.append('raw_materials')
        
        # Clear notes/activities
        if clear_type in ['all']:
            save_data(NOTES_FILE, [])
            files_cleared.append('notes')
        
        print(f"🗑️ Cleared data: {files_cleared}")
        
        # Broadcast update to all clients
        broadcast_update('data_cleared', {
            'type': clear_type,
            'filesCleared': files_cleared,
            'timestamp': datetime.now().isoformat()
        })
        
        # Also broadcast empty products update so clients refetch
        if clear_type in ['products', 'all']:
            broadcast_update('products_cleared', {
                'allProducts': [],
                'timestamp': datetime.now().isoformat()
            })
        
        return jsonify({
            'success': True,
            'message': f'All data cleared successfully! {len(files_cleared)} data sources cleared.',
            'filesCleared': files_cleared
        })
    except Exception as e:
        print(f"Clear data error: {str(e)}")
        return jsonify({'error': 'Failed to clear data', 'message': str(e)}), 500

# ============================================================
# CLOCK-IN / CLOCK-OUT TRACKING
# ============================================================

@app.route('/api/clock-in', methods=['POST', 'OPTIONS'])
@token_required
def clock_in():
    """User clocks in - create a new clock entry"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        clock_entries = load_data(CLOCK_ENTRIES_FILE)
        
        # Check if user already has an active clock-in
        active_entry = next((e for e in clock_entries 
                           if e.get('userId') == request.user['id'] 
                           and (e.get('status') == 'IN' or e.get('status') == 'clocked_in')
                           and not e.get('clockOut')), None)
        
        if active_entry:
            return jsonify({'error': 'Already clocked in', 'message': f'Clock-in time: {active_entry["clockIn"]}'}), 400
        
        # Create new clock entry
        entry = {
            'id': get_next_id(clock_entries),
            'userId': request.user['id'],
            'userName': request.user.get('name', 'Unknown'),
            'accountId': request.user.get('accountId'),
            'clockIn': datetime.now().isoformat(),
            'clockOut': None,
            'status': 'IN',
            'duration': 0
        }
        
        clock_entries.append(entry)
        save_data(CLOCK_ENTRIES_FILE, clock_entries)
        
        print(f"✅ User {request.user['name']} clocked IN at {entry['clockIn']}")
        
        return jsonify({
            'success': True,
            'entry': entry,
            'message': f"Clocked in at {entry['clockIn']}"
        }), 200
    
    except Exception as e:
        print(f"Clock-in error: {str(e)}")
        return jsonify({'error': 'Clock-in failed', 'message': str(e)}), 500


@app.route('/api/clock-out', methods=['POST', 'OPTIONS'])
@token_required
def clock_out():
    """User clocks out - complete the clock entry"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        clock_entries = load_data(CLOCK_ENTRIES_FILE)
        
        # Find active clock entry for this user
        active_entry = next((e for e in clock_entries 
                           if e.get('userId') == request.user['id'] 
                           and (e.get('status') == 'IN' or e.get('status') == 'clocked_in')
                           and not e.get('clockOut')), None)
        
        if not active_entry:
            return jsonify({'error': 'Not clocked in', 'message': 'No active clock-in record found'}), 400
        
        # Calculate duration
        clock_in_time = datetime.fromisoformat(active_entry['clockIn'])
        clock_out_time = datetime.now()
        duration_seconds = (clock_out_time - clock_in_time).total_seconds()
        
        # Update entry
        active_entry['clockOut'] = clock_out_time.isoformat()
        active_entry['status'] = 'OUT'
        active_entry['duration'] = duration_seconds
        
        save_data(CLOCK_ENTRIES_FILE, clock_entries)
        
        # Calculate hours and minutes
        hours = int(duration_seconds // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        
        print(f"✅ User {request.user['name']} clocked OUT after {hours}h {minutes}m")
        
        return jsonify({
            'success': True,
            'entry': active_entry,
            'duration': duration_seconds,
            'displayDuration': f"{hours}h {minutes}m",
            'message': f"Clocked out. Total time: {hours}h {minutes}m"
        }), 200
    
    except Exception as e:
        print(f"Clock-out error: {str(e)}")
        return jsonify({'error': 'Clock-out failed', 'message': str(e)}), 500


@app.route('/api/clock-status', methods=['GET', 'OPTIONS'])
@token_required
def get_clock_status():
    """Get current clock status for user"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        clock_entries = load_data(CLOCK_ENTRIES_FILE)
        
        # Find active clock entry
        active_entry = next((e for e in clock_entries 
                           if e.get('userId') == request.user['id'] 
                           and e.get('status') == 'IN'
                           and not e.get('clockOut')), None)
        
        if active_entry:
            # Calculate elapsed time
            clock_in_time = datetime.fromisoformat(active_entry['clockIn'])
            elapsed_seconds = (datetime.now() - clock_in_time).total_seconds()
            hours = int(elapsed_seconds // 3600)
            minutes = int((elapsed_seconds % 3600) // 60)
            
            return jsonify({
                'isClockedIn': True,
                'clockInTime': active_entry['clockIn'],
                'elapsedSeconds': elapsed_seconds,
                'elapsedDisplay': f"{hours}h {minutes}m"
            }), 200
        else:
            return jsonify({
                'isClockedIn': False,
                'message': 'Not currently clocked in'
            }), 200
    
    except Exception as e:
        print(f"Clock status error: {str(e)}")
        return jsonify({'error': 'Failed to get clock status', 'message': str(e)}), 500


@app.route('/api/clock-entries', methods=['GET', 'OPTIONS'])
@token_required
def get_clock_entries():
    """Get all clock entries for current user"""
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        clock_entries = load_data(CLOCK_ENTRIES_FILE)
        
        # Filter by user and account
        user_entries = [e for e in clock_entries 
                       if e.get('userId') == request.user['id'] 
                       and e.get('accountId') == request.user.get('accountId')]
        
        # Sort by date descending
        user_entries.sort(key=lambda x: x.get('clockIn', ''), reverse=True)
        
        return jsonify(user_entries), 200
    
    except Exception as e:
        print(f"Get clock entries error: {str(e)}")
        return jsonify({'error': 'Failed to get clock entries', 'message': str(e)}), 500

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