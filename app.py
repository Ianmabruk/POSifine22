from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
CORS(app, origins=['*'], methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['*'])
app.config['SECRET_KEY'] = 'simple-secret-key'

# ACCOUNT-BASED DATA MODEL (NOT COMPANY-BASED)
# Each account has its own data pool that all users in that account share

# Account = Primary data owner (Ultra admin or Basic user)
# Users = People who can access an account's data
accounts = []
users = []
products = []  # Each product has accountId
sales = []     # Each sale has accountId  
expenses = []  # Each expense has accountId
activities = []
reminders = []
settings = [{'screenLockPassword': '2005', 'businessName': 'My Business'}]

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

@app.route('/api/debug')
def debug():
    return jsonify({
        'accounts': len(accounts),
        'users': len(users),
        'products': len(products),
        'all_products': products,
        'all_users': users
    })

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
    
    # CREATE ACCOUNT-BASED SYSTEM
    # Each signup creates a new account (data owner)
    account = {
        'id': len(accounts) + 1,
        'ownerEmail': email,
        'plan': plan,
        'isLocked': False,
        'trialEndsAt': (datetime.now() + timedelta(days=30)).isoformat(),
        'createdAt': datetime.now().isoformat()
    }
    accounts.append(account)
    
    # Determine role based on plan
    if plan == 'ultra':
        role = 'admin'  # Ultra users get admin dashboard
    elif plan == 'basic':
        role = 'cashier'  # Basic users get cashier dashboard only
    else:
        role = 'cashier'  # Default to cashier
    
    user = {
        'id': len(users) + 1,
        'email': email,
        'password': password,
        'name': name,
        'role': role,
        'plan': plan,
        'accountId': account['id'],  # Link to account
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
    
    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role'], 'accountId': user['accountId']}, 
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
    
    # Check if account is locked
    account = next((a for a in accounts if a['id'] == user['accountId']), None)
    if account and account.get('isLocked'):
        return jsonify({'error': 'Account locked'}), 403
    
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
    
    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role'], 'accountId': user['accountId']}, 
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
        # Return ALL products for the user's account - SINGLE SOURCE OF TRUTH
        account_id = request.user.get('accountId')
        account_products = [p for p in products if p.get('accountId') == account_id]
        return jsonify(account_products)
    
    data = request.get_json()
    account_id = request.user.get('accountId')
    
    product = {
        'id': len(products) + 1,
        'accountId': account_id,  # CRITICAL: All products belong to account
        'name': data.get('name', ''),
        'price': float(data.get('price', 0)),
        'cost': float(data.get('cost', 0)),
        'quantity': int(data.get('quantity', 0)),
        'image': data.get('image', ''),
        'category': data.get('category', 'general'),
        'unit': data.get('unit', 'pcs'),
        'recipe': data.get('recipe', []),
        'isComposite': bool(data.get('recipe', [])),
        'createdAt': datetime.now().isoformat(),
        'createdBy': request.user.get('id')
    }
    
    # Validate recipe ingredients exist in same account
    if product['recipe']:
        for ingredient in product['recipe']:
            ingredient_product = next((p for p in products 
                                    if p['id'] == ingredient.get('productId') 
                                    and p.get('accountId') == account_id), None)
            if not ingredient_product:
                return jsonify({'error': f'Ingredient product not found: {ingredient.get("productId")}'}), 400
    
    products.append(product)
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_product(product_id):
    account_id = request.user.get('accountId')
    product = next((p for p in products if p['id'] == product_id and p.get('accountId') == account_id), None)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        product['name'] = data.get('name', product['name'])
        product['price'] = float(data.get('price', product['price']))
        product['quantity'] = int(data.get('quantity', product['quantity']))
        product['image'] = data.get('image', product.get('image', ''))
        product['category'] = data.get('category', product.get('category', 'general'))
        product['updatedAt'] = datetime.now().isoformat()
        return jsonify(product)
    
    if request.method == 'DELETE':
        products.remove(product)
        return jsonify({'message': 'Product deleted successfully'}), 200

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        account_sales = [s for s in sales if s.get('accountId') == account_id]
        return jsonify(account_sales)
    
    data = request.get_json()
    
    # Process each item and handle composite products
    for item in data.get('items', []):
        product = next((p for p in products 
                       if p['id'] == item['productId'] 
                       and p.get('accountId') == account_id), None)
        if product:
            # If it's a composite product, deduct ingredients from stock
            if product.get('isComposite') and product.get('recipe'):
                for ingredient in product['recipe']:
                    ingredient_product = next((p for p in products 
                                            if p['id'] == ingredient['productId'] 
                                            and p.get('accountId') == account_id), None)
                    if ingredient_product:
                        required_qty = ingredient['quantity'] * item['quantity']
                        ingredient_product['quantity'] = max(0, ingredient_product['quantity'] - required_qty)
            else:
                # Regular product - deduct from stock
                product['quantity'] = max(0, product['quantity'] - item['quantity'])
    
    sale = {
        'id': len(sales) + 1,
        'accountId': account_id,  # CRITICAL: Sale belongs to account
        'items': data.get('items', []),
        'total': float(data.get('total', 0)),
        'cashierId': request.user['id'],
        'cashierName': next((u['name'] for u in users if u['id'] == request.user['id']), 'Unknown'),
        'createdAt': datetime.now().isoformat()
    }
    sales.append(sale)
    return jsonify(sale)

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def handle_expenses():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        account_expenses = [e for e in expenses if e.get('accountId') == account_id]
        return jsonify(account_expenses)
    
    data = request.get_json()
    expense = {
        'id': len(expenses) + 1,
        'accountId': account_id,  # CRITICAL: Expense belongs to account
        'description': data.get('description', ''),
        'amount': float(data.get('amount', 0)),
        'createdAt': datetime.now().isoformat()
    }
    expenses.append(expense)
    return jsonify(expense)

@app.route('/api/stats')
@token_required
def stats():
    account_id = request.user.get('accountId')
    account_sales = [s for s in sales if s.get('accountId') == account_id]
    account_expenses = [e for e in expenses if e.get('accountId') == account_id]
    account_products = [p for p in products if p.get('accountId') == account_id]
    
    total_sales = sum(s.get('total', 0) for s in account_sales)
    total_expenses = sum(e.get('amount', 0) for e in account_expenses)
    
    return jsonify({
        'totalSales': total_sales,
        'totalExpenses': total_expenses,
        'profit': total_sales - total_expenses,
        'productCount': len(account_products)
    })

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def handle_users():
    if request.method == 'GET':
        account_id = request.user.get('accountId')
        account_users = [u for u in users if u.get('accountId') == account_id]
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in account_users])
    
    # Debug logging
    print(f"Token user: {request.user}")
    
    # Only Ultra admins can create users
    current_user = next((u for u in users if u['id'] == request.user['id']), None)
    print(f"Found current user: {current_user}")
    
    if not current_user:
        return jsonify({'error': 'Current user not found'}), 404
    
    if current_user.get('role') != 'admin':
        return jsonify({'error': f'Admin role required, got: {current_user.get("role")}'}), 403
        
    if current_user.get('plan') != 'ultra':
        return jsonify({'error': f'Ultra plan required, got: {current_user.get("plan")}'}), 403
    
    data = request.get_json()
    new_user = {
        'id': len(users) + 1,
        'email': data.get('email', '').lower(),
        'password': data.get('password', 'changeme123'),
        'name': data.get('name', ''),
        'role': 'cashier',  # Created users are always cashiers
        'plan': 'ultra',    # Inherit Ultra plan from creator
        'accountId': current_user['accountId'],  # CRITICAL: Same account as creator
        'active': True,
        'locked': False,
        'pin': data.get('pin', ''),
        'createdBy': current_user['id'],
        'createdAt': datetime.now().isoformat()
    }
    users.append(new_user)
    
    # Log activity
    activities.append({
        'id': len(activities) + 1,
        'type': 'user_created',
        'userId': new_user['id'],
        'email': new_user['email'],
        'name': new_user['name'],
        'plan': new_user['plan'],
        'createdBy': current_user['id'],
        'timestamp': datetime.now().isoformat()
    })
    
    return jsonify({k: v for k, v in new_user.items() if k != 'password'})

@app.route('/api/reminders', methods=['GET', 'POST'])
@token_required
def handle_reminders():
    account_id = request.user.get('accountId')
    
    if request.method == 'GET':
        account_reminders = [r for r in reminders if r.get('accountId') == account_id]
        return jsonify(account_reminders)
    
    data = request.get_json()
    reminder = {
        'id': len(reminders) + 1,
        'accountId': account_id,  # CRITICAL: Reminder belongs to account
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'dueDate': data.get('dueDate', ''),
        'priority': data.get('priority', 'medium'),
        'completed': False,
        'createdBy': request.user.get('id'),
        'createdAt': datetime.now().isoformat()
    }
    reminders.append(reminder)
    return jsonify(reminder)

@app.route('/api/reminders/<int:reminder_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_reminder(reminder_id):
    account_id = request.user.get('accountId')
    reminder = next((r for r in reminders if r['id'] == reminder_id and r.get('accountId') == account_id), None)
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        reminder.update({
            'title': data.get('title', reminder['title']),
            'description': data.get('description', reminder['description']),
            'dueDate': data.get('dueDate', reminder['dueDate']),
            'priority': data.get('priority', reminder['priority']),
            'completed': data.get('completed', reminder['completed'])
        })
        return jsonify(reminder)
    
    if request.method == 'DELETE':
        reminders.remove(reminder)
        return jsonify({'message': 'Reminder deleted'}), 200

# MAIN ADMIN ENDPOINTS (System Owner)
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
    sorted_activities = sorted(activities, key=lambda x: x.get('timestamp', ''), reverse=True)
    return jsonify(sorted_activities)

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

@app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST'])
@token_required
def main_admin_lock_user(user_id):
    if request.user.get('type') != 'main_admin':
        return jsonify({'error': 'Access denied'}), 403
    
    data = request.get_json()
    locked = data.get('locked', False)
    
    # Lock the account, not just the user
    user = next((u for u in users if u['id'] == user_id), None)
    if user:
        account = next((a for a in accounts if a['id'] == user['accountId']), None)
        if account:
            account['isLocked'] = locked
            # Also update all users in the account
            for u in users:
                if u.get('accountId') == user['accountId']:
                    u['locked'] = locked
                    u['active'] = not locked
    
    return jsonify({'message': 'User lock status updated'})

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

# Stub endpoints for missing API calls
@app.route('/api/batches', methods=['GET', 'POST'])
def handle_batches():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Batch created'})

@app.route('/api/production', methods=['GET', 'POST'])
def handle_production():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Production created'})

@app.route('/api/categories/generate-code', methods=['POST'])
def generate_category_code():
    return jsonify({'code': 'CAT001'})

@app.route('/api/price-history', methods=['GET', 'POST'])
def handle_price_history():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Price history created'})

@app.route('/api/service-fees', methods=['GET', 'POST'])
def handle_service_fees():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Service fee created'})

@app.route('/api/service-fees/<int:fee_id>', methods=['PUT', 'DELETE'])
def handle_service_fee(fee_id):
    if request.method == 'PUT':
        return jsonify({'id': fee_id, 'message': 'Service fee updated'})
    return jsonify({'message': 'Service fee deleted'})

@app.route('/api/discounts', methods=['GET', 'POST'])
def handle_discounts():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Discount created'})

@app.route('/api/discounts/<int:discount_id>', methods=['PUT', 'DELETE'])
def handle_discount(discount_id):
    if request.method == 'PUT':
        return jsonify({'id': discount_id, 'message': 'Discount updated'})
    return jsonify({'message': 'Discount deleted'})

@app.route('/api/credit-requests', methods=['GET', 'POST'])
def handle_credit_requests():
    if request.method == 'GET':
        return jsonify([])
    return jsonify({'id': 1, 'message': 'Credit request created'})

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
    image_data = data.get('image', '')
    return jsonify({'url': image_data, 'success': True})

if __name__ == '__main__':
    app.run(debug=True)