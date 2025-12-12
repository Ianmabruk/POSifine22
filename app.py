from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import json
import os
from datetime import datetime, timedelta
from functools import wraps


app = Flask(__name__)
# Enhanced CORS configuration for Netlify deployment
CORS(app, 
     resources={r"/api/*": {"origins": "*"}},
     methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
     allow_headers=['Content-Type', 'Authorization', 'X-Requested-With', 'Accept'],
     credentials=True)
app.config['SECRET_KEY'] = os.environ.get('JWT_SECRET', 'your-secret-key-change-in-production')


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize empty data files if they don't exist
data_files = {
    'users.json': [],
    'products.json': [],
    'sales.json': [],
    'expenses.json': [],
    'reminders.json': [],
    'service_fees.json': [],
    'discounts.json': [],
    'credit_requests.json': [],
    'settings.json': [],
    'batches.json': [],
    'production.json': [],
    'price_history.json': [],
    'time_entries.json': [],
    'categories.json': [],
    'payments.json': [],
    'emails.json': []
}

for filename, default_data in data_files.items():
    file_path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(file_path):
        with open(file_path, 'w') as f:
            json.dump(default_data, f, indent=2)
        print(f"Created {filename} with default data")

def load_json(filename):
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return []

def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            token = token.split(' ')[1] if ' ' in token else token
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            request.user = data
        except:
            return jsonify({'error': 'Token is invalid'}), 401
        return f(*args, **kwargs)
    return decorated



@app.route('/api/auth/signup', methods=['POST'])
def signup():
    data = request.json
    users = load_json('users.json')
    
    if any(u['email'] == data['email'] for u in users):
        return jsonify({'error': 'User already exists'}), 400
    
    # First user is admin with Ultra package
    is_first_user = len(users) == 0
    
    user = {
        'id': len(users) + 1,
        'email': data['email'],
        'password': data['password'],
        'name': data.get('name', ''),
        'role': 'admin' if is_first_user else 'cashier',
        'plan': 'ultra' if is_first_user else None,
        'price': 1600 if is_first_user else None,
        'active': is_first_user,  # First user is active immediately
        'locked': False,
        'permissions': {
            'viewSales': True,
            'viewInventory': True,
            'viewExpenses': False,
            'manageProducts': False
        } if not is_first_user else {},
        'createdAt': datetime.now().isoformat()
    }
    users.append(user)
    save_json('users.json', users)
    
    token = jwt.encode({'id': user['id'], 'email': user['email'], 'role': user['role']}, 
                       app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({'token': token, 'user': {k: v for k, v in user.items() if k != 'password'}})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    users = load_json('users.json')
    
    user = next((u for u in users if u['email'] == data['email'] and u['password'] == data['password']), None)
    if not user:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    # Check if user is locked
    if user.get('locked', False):
        return jsonify({'error': 'Account is locked. Contact administrator.'}), 403
    
    # Include role in token for proper authorization
    token = jwt.encode({
        'id': user['id'], 
        'email': user['email'], 
        'role': user['role']
    }, app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({'token': token, 'user': {k: v for k, v in user.items() if k != 'password'}})

@app.route('/api/users', methods=['GET', 'POST'])
@token_required
def users_list():
    if request.method == 'GET':
        # Check if user is admin
        if request.user.get('role') != 'admin':
            return jsonify({'error': 'Admin access required'}), 403
        
        users = load_json('users.json')
        return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])
    
    # POST - Admin creating cashier
    # Check if user is admin
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.json
    users = load_json('users.json')
    
    if any(u['email'] == data['email'] for u in users):
        return jsonify({'error': 'User already exists'}), 400
    
    user = {
        'id': len(users) + 1,
        'email': data['email'],
        'password': data.get('password', 'changeme123'),
        'name': data['name'],
        'role': 'cashier',
        'plan': 'basic',
        'price': 900,
        'active': True,
        'locked': False,
        'permissions': data.get('permissions', {
            'viewSales': True,
            'viewInventory': True,
            'viewExpenses': False,
            'manageProducts': False
        }),
        'createdAt': datetime.now().isoformat()
    }
    users.append(user)
    save_json('users.json', users)
    
    return jsonify({k: v for k, v in user.items() if k != 'password'}), 201

@app.route('/api/users/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def user_detail(id):
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    if request.method == 'PUT':
        data = request.json
        # Allow user to update themselves or admin to update anyone
        if request.user.get('id') != id and request.user.get('role') != 'admin':
            return jsonify({'error': 'Unauthorized'}), 403
        
        user.update({k: v for k, v in data.items() if k != 'password' and k != 'id'})
        save_json('users.json', users)
        
        # Generate new token with updated role
        new_token = jwt.encode({
            'id': user['id'], 
            'email': user['email'], 
            'role': user['role']
        }, app.config['SECRET_KEY'], algorithm='HS256')
        
        return jsonify({
            'token': new_token,
            'user': {k: v for k, v in user.items() if k != 'password'}
        })
    
    # DELETE
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    users = [u for u in users if u['id'] != id]
    save_json('users.json', users)
    return '', 204

@app.route('/api/users/<int:id>/lock', methods=['POST'])
@token_required
def lock_user(id):
    """Lock or unlock a user account"""
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.json
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user['locked'] = data.get('locked', False)
    if user['locked']:
        user['active'] = False
    
    save_json('users.json', users)
    return jsonify({'success': True, 'locked': user['locked']})

@app.route('/api/users/<int:id>/activate', methods=['POST'])
@token_required
def activate_user(id):
    """Activate or deactivate a user account"""
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.json
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user['active'] = data.get('active', False)
    save_json('users.json', users)
    return jsonify({'success': True, 'active': user['active']})

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def products():
    if request.method == 'GET':
        products = load_json('products.json')
        
        # Cashiers don't see expense-only items
        if request.user.get('role') == 'cashier':
            products = [p for p in products if not p.get('expenseOnly', False)]
        
        return jsonify(products)
    
    data = request.json
    products = load_json('products.json')
    
    product = {
        'id': len(products) + 1,
        'name': data['name'],
        'price': data.get('price', 0),
        'cost': data.get('cost', 0),
        'quantity': data.get('quantity', 0),
        'unit': data.get('unit', 'pcs'),
        'category': data.get('category', 'raw'),
        'recipe': data.get('recipe', []),
        'expenseOnly': data.get('expenseOnly', False),
        'visibleToCashier': data.get('visibleToCashier', True),
        'createdAt': datetime.now().isoformat()
    }
    products.append(product)
    save_json('products.json', products)
    return jsonify(product), 201

@app.route('/api/products/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def product_detail(id):
    products = load_json('products.json')
    product = next((p for p in products if p['id'] == id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.json
        product.update({k: v for k, v in data.items() if k != 'id'})
        save_json('products.json', products)
        return jsonify(product)
    
    products = [p for p in products if p['id'] != id]
    save_json('products.json', products)
    return '', 204

@app.route('/api/products/<int:id>/max-producible', methods=['GET'])
@token_required
def max_producible(id):
    products = load_json('products.json')
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
    
    return jsonify({'maxUnits': int(max_units) if max_units != float('inf') else 0, 'limitingIngredient': limiting})

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def sales():
    if request.method == 'GET':
        sales = load_json('sales.json')
        return jsonify(sales)
    
    data = request.json
    products = load_json('products.json')
    expenses = load_json('expenses.json')
    
    total_cogs = 0
    
    # Process each item sold
    for item in data['items']:
        product = next((p for p in products if p['id'] == item['productId']), None)
        if not product:
            continue
        
        quantity_sold = item['quantity']
        
        # If composite product with recipe
        if product.get('recipe'):
            for ingredient in product['recipe']:
                raw_product = next((p for p in products if p['id'] == ingredient['productId']), None)
                if raw_product:
                    qty_needed = ingredient['quantity'] * quantity_sold
                    raw_product['quantity'] = raw_product.get('quantity', 0) - qty_needed
                    
                    # Calculate COGS
                    unit_cost = raw_product.get('cost', 0) / max(raw_product.get('quantity', 1) + qty_needed, 1)
                    cost = unit_cost * qty_needed
                    total_cogs += cost
                    
                    # Record expense if expenseOnly
                    if raw_product.get('expenseOnly'):
                        expense = {
                            'id': len(expenses) + 1,
                            'description': f'Used {qty_needed} {raw_product.get("unit", "units")} of {raw_product["name"]}',
                            'amount': cost,
                            'category': 'ingredient',
                            'automatic': True,
                            'saleId': len(load_json('sales.json')) + 1,
                            'createdAt': datetime.now().isoformat()
                        }
                        expenses.append(expense)
        else:
            # Simple product
            product['quantity'] = product.get('quantity', 0) - quantity_sold
            total_cogs += product.get('cost', 0) * quantity_sold
    
    save_json('products.json', products)
    save_json('expenses.json', expenses)
    
    sales_list = load_json('sales.json')
    sale = {
        'id': len(sales_list) + 1,
        'items': data['items'],
        'total': data['total'],
        'cogs': total_cogs,
        'profit': data['total'] - total_cogs,
        'paymentMethod': data.get('paymentMethod', 'cash'),
        'cashierId': request.user.get('id'),
        'cashierName': next((u['name'] for u in load_json('users.json') if u['id'] == request.user.get('id')), 'Unknown'),
        'createdAt': datetime.now().isoformat()
    }
    sales_list.append(sale)
    save_json('sales.json', sales_list)
    
    return jsonify(sale), 201

@app.route('/api/expenses', methods=['GET', 'POST'])
@token_required
def expenses():
    if request.method == 'GET':
        expenses = load_json('expenses.json')
        return jsonify(expenses)
    
    data = request.json
    expenses = load_json('expenses.json')
    
    expense = {
        'id': len(expenses) + 1,
        'description': data['description'],
        'amount': data['amount'],
        'category': data.get('category', 'general'),
        'automatic': False,
        'createdAt': datetime.now().isoformat()
    }
    expenses.append(expense)
    save_json('expenses.json', expenses)
    
    return jsonify(expense), 201

@app.route('/api/auth/me', methods=['GET'])
@token_required
def get_current_user():
    """Get current user info from token"""
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == request.user.get('id')), None)
    if user:
        return jsonify({k: v for k, v in user.items() if k != 'password'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/stats', methods=['GET'])
@token_required
def stats():
    sales = load_json('sales.json')
    expenses = load_json('expenses.json')
    products = load_json('products.json')
    
    total_sales = sum(s.get('total', 0) for s in sales)
    total_cogs = sum(s.get('cogs', 0) for s in sales)
    total_expenses = sum(e.get('amount', 0) for e in expenses)
    gross_profit = total_sales - total_cogs
    net_profit = total_sales - total_cogs - total_expenses
    
    # Daily/Weekly stats
    today = datetime.now().date()
    daily_sales = sum(s.get('total', 0) for s in sales if datetime.fromisoformat(s['createdAt']).date() == today)
    
    week_start = today - timedelta(days=today.weekday())
    weekly_sales = sum(s.get('total', 0) for s in sales if datetime.fromisoformat(s['createdAt']).date() >= week_start)
    
    # Cashier activity stats
    cashier_stats = {}
    for sale in sales:
        cashier_id = sale.get('cashierId')
        if cashier_id:
            if cashier_id not in cashier_stats:
                cashier_stats[cashier_id] = {'sales': 0, 'total': 0}
            cashier_stats[cashier_id]['sales'] += 1
            cashier_stats[cashier_id]['total'] += sale.get('total', 0)
    
    return jsonify({
        'totalSales': total_sales,
        'totalCOGS': total_cogs,
        'totalExpenses': total_expenses,
        'grossProfit': gross_profit,
        'netProfit': net_profit,
        'salesCount': len(sales),
        'dailySales': daily_sales,
        'weeklySales': weekly_sales,
        'productCount': len(products),
        'cashierStats': cashier_stats
    })


@app.route('/api/reminders', methods=['GET', 'POST'])
@token_required
def reminders():
    if request.method == 'GET':
        reminders = load_json('reminders.json')
        return jsonify(reminders)
    
    # POST - Only admins can create reminders
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.json
    reminders = load_json('reminders.json')
    reminder = {
        'id': len(reminders) + 1,
        'customerName': data['customerName'],
        'productId': data['productId'],
        'frequency': data['frequency'],
        'days': data.get('days', []),
        'nextDate': data['nextDate'],
        'status': 'pending',
        'createdBy': request.user.get('id'),
        'createdAt': datetime.now().isoformat()
    }
    reminders.append(reminder)
    save_json('reminders.json', reminders)
    return jsonify(reminder), 201

@app.route('/api/reminders/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def reminder_detail(id):
    reminders = load_json('reminders.json')
    reminder = next((r for r in reminders if r['id'] == id), None)
    if not reminder:
        return jsonify({'error': 'Reminder not found'}), 404
    
    if request.method == 'PUT':
        data = request.json
        reminder.update({k: v for k, v in data.items() if k != 'id'})
        save_json('reminders.json', reminders)
        return jsonify(reminder)
    
    reminders = [r for r in reminders if r['id'] != id]
    save_json('reminders.json', reminders)
    return '', 204

@app.route('/api/reminders/today', methods=['GET'])
@token_required
def reminders_today():
    reminders = load_json('reminders.json')
    today = datetime.now().date().isoformat()
    today_reminders = [r for r in reminders if r.get('nextDate', '')[:10] <= today and r.get('status') == 'pending']
    return jsonify(today_reminders)

@app.route('/api/price-history', methods=['GET', 'POST'])
@token_required
def price_history():
    if request.method == 'GET':
        history = load_json('price_history.json')
        return jsonify(history)
    
    data = request.json
    if data['newPrice'] < data['oldPrice']:
        return jsonify({'error': 'You cannot lower prices, only increase.'}), 400
    
    history = load_json('price_history.json')
    record = {
        'id': len(history) + 1,
        'productId': data['productId'],
        'oldPrice': data['oldPrice'],
        'newPrice': data['newPrice'],
        'userId': request.user.get('id'),
        'timestamp': datetime.now().isoformat()
    }
    history.append(record)
    save_json('price_history.json', history)
    return jsonify(record), 201

@app.route('/api/service-fees', methods=['GET', 'POST'])
@token_required
def service_fees():
    if request.method == 'GET':
        fees = load_json('service_fees.json')
        return jsonify(fees)
    
    data = request.json
    fees = load_json('service_fees.json')
    fee = {
        'id': len(fees) + 1,
        'name': data['name'],
        'amount': data['amount'],
        'description': data.get('description', ''),
        'active': data.get('active', True),
        'createdAt': datetime.now().isoformat()
    }
    fees.append(fee)
    save_json('service_fees.json', fees)
    return jsonify(fee), 201

@app.route('/api/service-fees/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def service_fee_detail(id):
    fees = load_json('service_fees.json')
    fee = next((f for f in fees if f['id'] == id), None)
    if not fee:
        return jsonify({'error': 'Fee not found'}), 404
    
    if request.method == 'PUT':
        data = request.json
        fee.update({k: v for k, v in data.items() if k != 'id'})
        save_json('service_fees.json', fees)
        return jsonify(fee)
    
    fees = [f for f in fees if f['id'] != id]
    save_json('service_fees.json', fees)
    return '', 204

@app.route('/api/discounts', methods=['GET', 'POST'])
@token_required
def discounts():
    if request.method == 'GET':
        discounts = load_json('discounts.json')
        return jsonify(discounts)
    
    data = request.json
    discounts = load_json('discounts.json')
    discount = {
        'id': len(discounts) + 1,
        'name': data['name'],
        'percentage': data['percentage'],
        'validFrom': data['validFrom'],
        'validTo': data['validTo'],
        'active': data.get('active', True),
        'createdAt': datetime.now().isoformat()
    }
    discounts.append(discount)
    save_json('discounts.json', discounts)
    return jsonify(discount), 201

@app.route('/api/discounts/<int:id>', methods=['PUT', 'DELETE'])
@token_required
def discount_detail(id):
    discounts = load_json('discounts.json')
    discount = next((d for d in discounts if d['id'] == id), None)
    if not discount:
        return jsonify({'error': 'Discount not found'}), 404
    
    if request.method == 'PUT':
        data = request.json
        discount.update({k: v for k, v in data.items() if k != 'id'})
        save_json('discounts.json', discounts)
        return jsonify(discount)
    
    discounts = [d for d in discounts if d['id'] != id]
    save_json('discounts.json', discounts)
    return '', 204

@app.route('/api/credit-requests', methods=['GET', 'POST'])
@token_required
def credit_requests():
    if request.method == 'GET':
        requests = load_json('credit_requests.json')
        return jsonify(requests)
    
    data = request.json
    requests = load_json('credit_requests.json')
    credit_request = {
        'id': len(requests) + 1,
        'productId': data['productId'],
        'quantity': data['quantity'],
        'customerName': data['customerName'],
        'amount': data['amount'],
        'cashierId': request.user.get('id'),
        'status': 'pending',
        'createdAt': datetime.now().isoformat()
    }
    requests.append(credit_request)
    save_json('credit_requests.json', requests)
    return jsonify(credit_request), 201

@app.route('/api/credit-requests/<int:id>/approve', methods=['POST'])
@token_required
def approve_credit(id):
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    requests = load_json('credit_requests.json')
    credit_request = next((r for r in requests if r['id'] == id), None)
    if not credit_request:
        return jsonify({'error': 'Request not found'}), 404
    
    credit_request['status'] = 'approved'
    credit_request['approvedAt'] = datetime.now().isoformat()
    save_json('credit_requests.json', requests)
    return jsonify(credit_request)

@app.route('/api/credit-requests/<int:id>/reject', methods=['POST'])
@token_required
def reject_credit(id):
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    requests = load_json('credit_requests.json')
    credit_request = next((r for r in requests if r['id'] == id), None)
    if not credit_request:
        return jsonify({'error': 'Request not found'}), 404
    
    credit_request['status'] = 'rejected'
    save_json('credit_requests.json', requests)
    return jsonify(credit_request)

@app.route('/api/settings', methods=['GET', 'POST'])
@token_required
def settings():
    if request.method == 'GET':
        settings = load_json('settings.json')
        return jsonify(settings[0] if settings else {})
    
    data = request.json
    settings = load_json('settings.json')
    if settings:
        settings[0].update(data)
    else:
        settings = [data]
    save_json('settings.json', settings)
    return jsonify(settings[0])

@app.route('/api/batches', methods=['GET', 'POST'])
@token_required
def batches():
    if request.method == 'GET':
        batches = load_json('batches.json')
        product_id = request.args.get('productId')
        if product_id:
            batches = [b for b in batches if b['productId'] == int(product_id)]
        return jsonify(batches)
    
    data = request.json
    batches = load_json('batches.json')
    batch = {
        'id': len(batches) + 1,
        'productId': data['productId'],
        'batchCode': data.get('batchCode', f"B{len(batches) + 1:04d}"),
        'buyingPrice': data['buyingPrice'],
        'sellingPrice': data['sellingPrice'],
        'quantity': data['quantity'],
        'remaining': data['quantity'],
        'type': data.get('type', 'new'),
        'createdAt': datetime.now().isoformat()
    }
    batches.append(batch)
    save_json('batches.json', batches)
    return jsonify(batch), 201

@app.route('/api/production', methods=['GET', 'POST'])
@token_required
def production():
    if request.method == 'GET':
        production = load_json('production.json')
        return jsonify(production)
    
    data = request.json
    production_list = load_json('production.json')
    batches = load_json('batches.json')
    
    record = {
        'id': len(production_list) + 1,
        'sourceProductId': data['sourceProductId'],
        'targetProductId': data['targetProductId'],
        'quantityUsed': data['quantityUsed'],
        'quantityProduced': data['quantityProduced'],
        'waste': data.get('waste', 0),
        'userId': request.user.get('id'),
        'createdAt': datetime.now().isoformat()
    }
    
    # Deduct from old batches first (FIFO)
    remaining_to_deduct = data['quantityUsed']
    source_batches = sorted([b for b in batches if b['productId'] == data['sourceProductId'] and b['remaining'] > 0], key=lambda x: x['createdAt'])
    
    for batch in source_batches:
        if remaining_to_deduct <= 0:
            break
        deduct = min(batch['remaining'], remaining_to_deduct)
        batch['remaining'] -= deduct
        remaining_to_deduct -= deduct
    
    save_json('batches.json', batches)
    production_list.append(record)
    save_json('production.json', production_list)
    return jsonify(record), 201

@app.route('/api/categories/generate-code', methods=['POST'])
@token_required
def generate_code():
    data = request.json
    products = load_json('products.json')
    prefix = data.get('prefix', 'P')
    category_products = [p for p in products if p.get('category') == data.get('category')]
    next_num = len(category_products) + 1
    code = f"{prefix}{next_num:03d}"
    return jsonify({'code': code})

@app.route('/api/upload-image', methods=['POST'])
@token_required
def upload_image():
    """Handle base64 image uploads for products and profiles"""
    data = request.json
    image_data = data.get('image')  # Base64 encoded image
    image_type = data.get('type', 'product')  # 'product', 'profile', 'logo'
    
    # Store image data (in production, you'd save to file system or cloud storage)
    # For now, we'll just return the base64 data back
    return jsonify({'imageUrl': image_data, 'type': image_type})

# Main Admin Routes
@app.route('/api/main-admin/users', methods=['GET'])
@token_required
def main_admin_get_users():
    """Get all users with payment info for main admin"""
    users = load_json('users.json')
    # Add locked field if not present
    for user in users:
        if 'locked' not in user:
            user['locked'] = False
    save_json('users.json', users)
    return jsonify([{k: v for k, v in u.items() if k != 'password'} for u in users])

@app.route('/api/main-admin/payments', methods=['GET'])
@token_required
def main_admin_get_payments():
    """Get all payments for main admin"""
    payments = load_json('payments.json')
    return jsonify(payments)

@app.route('/api/main-admin/users/<int:user_id>/lock', methods=['POST'])
@token_required
def main_admin_lock_user(user_id):
    """Lock or unlock a user account"""
    data = request.json
    users = load_json('users.json')
    user = next((u for u in users if u['id'] == user_id), None)
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    user['locked'] = data.get('locked', False)
    if user['locked']:
        user['active'] = False
    
    save_json('users.json', users)
    return jsonify({'success': True, 'locked': user['locked']})

@app.route('/api/main-admin/send-email', methods=['POST'])
@token_required
def main_admin_send_email():
    """Send email to selected users"""
    data = request.json
    user_ids = data.get('userIds', [])
    subject = data.get('subject', '')
    message = data.get('message', '')
    
    users = load_json('users.json')
    emails = load_json('emails.json')
    
    # Log emails (in production, integrate with email service like SendGrid, Mailgun, etc.)
    for user_id in user_ids:
        user = next((u for u in users if u['id'] == user_id), None)
        if user:
            email_record = {
                'id': len(emails) + 1,
                'userId': user_id,
                'userEmail': user['email'],
                'userName': user['name'],
                'subject': subject,
                'message': message,
                'status': 'sent',
                'sentAt': datetime.now().isoformat()
            }
            emails.append(email_record)
    
    save_json('emails.json', emails)
    return jsonify({'success': True, 'emailsSent': len(user_ids)})

@app.route('/api/main-admin/create-payment', methods=['POST'])
@token_required
def main_admin_create_payment():
    """Create a payment record for a user"""
    data = request.json
    payments = load_json('payments.json')
    
    payment = {
        'id': len(payments) + 1,
        'userId': data['userId'],
        'amount': data['amount'],
        'plan': data.get('plan', 'basic'),
        'status': data.get('status', 'pending'),
        'dueDate': data.get('dueDate'),
        'createdAt': datetime.now().isoformat()
    }
    
    payments.append(payment)
    save_json('payments.json', payments)
    return jsonify(payment), 201

@app.route('/api/main-admin/payments/<int:payment_id>', methods=['PUT'])
@token_required
def main_admin_update_payment(payment_id):
    """Update payment status"""
    data = request.json
    payments = load_json('payments.json')
    payment = next((p for p in payments if p['id'] == payment_id), None)
    
    if not payment:
        return jsonify({'error': 'Payment not found'}), 404
    
    payment['status'] = data.get('status', payment['status'])
    if payment['status'] == 'paid':
        payment['paidAt'] = datetime.now().isoformat()
    
    save_json('payments.json', payments)
    return jsonify(payment)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
