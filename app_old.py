from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt
import os
from datetime import datetime
from functools import wraps
import json
from pathlib import Path
import tempfile
import shutil
try:
    import database
except Exception:
    database = None

# Try to enable WebSocket support via flask_sock when available
try:
    from flask_sock import Sock
    has_sock = True
except Exception:
    Sock = None
    has_sock = False

import threading
from queue import Queue, Empty

app = Flask(__name__)
# Use BACKEND_ALLOWED_ORIGINS (comma-separated) to restrict CORS in production
allowed = os.environ.get('BACKEND_ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000,https://posifine11.vercel.app,https://posifine11.netlify.app')
allowed_list = [o.strip() for o in allowed.split(',') if o.strip()]
CORS(app, origins=allowed_list, methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], allow_headers=['Content-Type', 'Authorization'])
app.config['SECRET_KEY'] = os.environ.get('APP_SECRET', 'simple-secret-key')

# Data persistence helpers (simple JSON files in backend/data)
DATA_DIR = Path(__file__).parent / 'data'

# Ensure data directory exists
DATA_DIR.mkdir(exist_ok=True)

def load_json(filename):
    path = DATA_DIR / filename
    try:
        if not path.exists():
            return []
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []

def save_json(filename, data):
    path = DATA_DIR / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Atomic write to avoid partial/corrupt files on failure
        fd, tmp = tempfile.mkstemp(dir=str(path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            shutil.move(tmp, str(path))
        except Exception as e:
            print(f"Error saving {filename}: {e}")
            try:
                os.remove(tmp)
            except Exception:
                pass
    except Exception as e:
        print(f"Error creating temp file for {filename}: {e}")
        # Fallback to direct write
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e2:
            print(f"Fallback save failed for {filename}: {e2}")


# Ensure responses have correct CORS headers. Use BACKEND_ALLOWED_ORIGINS env var (comma-separated)
@app.after_request
def add_cors_headers(response):
    allowed = os.environ.get('BACKEND_ALLOWED_ORIGINS', 'http://localhost:5173,http://localhost:3000,https://posifine11.vercel.app,https://posifine11.netlify.app')
    origin = request.headers.get('Origin')
    if allowed.strip() == '*':
        response.headers['Access-Control-Allow-Origin'] = '*'
    else:
        allowed_list = [o.strip() for o in allowed.split(',') if o.strip()]
        if origin and origin in allowed_list:
            response.headers['Access-Control-Allow-Origin'] = origin
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response

# Global storage - load from data files so state persists across restarts
try:
    users = load_json('users.json')
    products = load_json('products.json')
    sales = load_json('sales.json')
    expenses = load_json('expenses.json')
    activities = load_json('activities.json')
    reminders = load_json('reminders.json')
    settings = load_json('settings.json') or [{'screenLockPassword': '2005', 'businessName': 'My Business'}]
    companies = load_json('companies.json')
    
    # Ensure companies has at least one entry
    if not companies:
        companies = [{
            'id': 1,
            'name': 'Demo Company',
            'plan': 'ultra',
            'createdAt': datetime.now().isoformat()
        }]
        save_json('companies.json', companies)
        
except Exception as e:
    print(f"Error initializing data: {e}")
    # Fallback to empty data
    users = []
    products = []
    sales = []
    expenses = []
    activities = []
    reminders = []
    settings = [{'screenLockPassword': '2005', 'businessName': 'My Business'}]
    companies = [{
        'id': 1,
        'name': 'Demo Company',
        'plan': 'ultra',
        'createdAt': datetime.now().isoformat()
    }]

# SSE subscribers: list of tuples (Queue, company_id)
_subscribers = []
_subs_lock = threading.Lock()

# WebSocket clients per company: { company_id: set(ws, ...) }
_ws_clients = {}
_ws_lock = threading.Lock()

def broadcast_products_update(event_type, payload, company_id=None):
    """Broadcast a JSON payload to all SSE subscribers for a company."""
    msg = {'type': event_type, 'payload': payload}
    with _subs_lock:
        for q, cid in list(_subscribers):
            try:
                if company_id is None or cid == company_id:
                    q.put(msg)
            except Exception:
                pass
    # Also push to any active WebSocket clients
    try:
        text = json.dumps(msg)
        with _ws_lock:
            if company_id is not None:
                clients = list(_ws_clients.get(company_id, []))
            else:
                clients = [ws for s in _ws_clients.values() for ws in s]

        for ws in clients:
            try:
                ws.send(text)
            except Exception:
                pass
    except Exception:
        pass


@app.route('/api/stream/products')
def stream_products():
    """Server-Sent Events endpoint for product updates scoped to user's company.
    Supports token via `Authorization: Bearer <token>` header or `?token=<token>` query param (for EventSource).
    """
    # Authentication: allow token in header or query param (EventSource cannot set headers)
    token = request.headers.get('Authorization', '').replace('Bearer ', '') or request.args.get('token')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    try:
        data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = next((u for u in users if u.get('id') == data.get('id')), None)
        if user:
            request.user = user
        else:
            request.user = data
    except Exception:
        return jsonify({'error': 'Invalid token'}), 401

    company_id = request.user.get('company_id')
    q = Queue()
    # send initial snapshot
    try:
        company_products = [p for p in products if p.get('company_id') == company_id]
        q.put({'type': 'initial', 'payload': company_products})
    except Exception:
        q.put({'type': 'initial', 'payload': []})

    with _subs_lock:
        _subscribers.append((q, company_id))

    def gen():
        try:
            while True:
                try:
                    msg = q.get(timeout=30)
                except Empty:
                    yield ': keep-alive\n\n'
                    continue
                yield f"data: {json.dumps(msg)}\n\n"
        finally:
            with _subs_lock:
                try:
                    _subscribers.remove((q, company_id))
                except ValueError:
                    pass

    return app.response_class(gen(), mimetype='text/event-stream')


# WebSocket endpoint (preferred) - requires flask-sock and a server that supports websockets
if has_sock:
    sock = Sock(app)

    @sock.route('/api/ws/products')
    def ws_products(ws):
        # Accept token via query param or initial auth message
        token = request.args.get('token')
        user = None
        if token:
            try:
                data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
                user = next((u for u in users if u.get('id') == data.get('id')), None) or data
            except Exception:
                user = None

        # If no token in query, expect the client to send an auth message first
        if not user:
            try:
                auth_msg = ws.receive(timeout=5)
                if auth_msg:
                    try:
                        j = json.loads(auth_msg)
                        t = j.get('token') or j.get('auth')
                        if t:
                            data = jwt.decode(t, app.config['SECRET_KEY'], algorithms=['HS256'])
                            user = next((u for u in users if u.get('id') == data.get('id')), None) or data
                    except Exception:
                        pass
            except Exception:
                pass

        if not user:
            try:
                ws.send(json.dumps({'error': 'Unauthorized'}))
            except Exception:
                pass
            return

        company_id = user.get('company_id')

        # Register client
        with _ws_lock:
            _ws_clients.setdefault(company_id, set()).add(ws)

        # Send initial snapshot
        try:
            company_products = [p for p in products if p.get('company_id') == company_id]
            ws.send(json.dumps({'type': 'initial', 'payload': company_products}))
        except Exception:
            try:
                ws.send(json.dumps({'type': 'initial', 'payload': []}))
            except Exception:
                pass

        # Keep connection alive and handle inbound messages if needed
        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break
                # Allow clients to request a refresh explicitly
                try:
                    data = json.loads(msg)
                    if data.get('type') == 'refresh':
                        company_products = [p for p in products if p.get('company_id') == company_id]
                        ws.send(json.dumps({'type': 'products_snapshot', 'payload': company_products}))
                except Exception:
                    # ignore malformed messages
                    pass
        finally:
            # Cleanup
            with _ws_lock:
                try:
                    _ws_clients.get(company_id, set()).discard(ws)
                except Exception:
                    pass


# Background listener to support Postgres LISTEN/NOTIFY for cross-process broadcasts
def _start_db_notification_listener():
    if not os.environ.get('DATABASE_URL'):
        return
    if not database:
        return
    try:
        import select
        conn = database.get_db_connection()
        if not conn:
            return
        cur = conn.cursor()
        cur.execute("LISTEN products_update;")
        print('[DB LISTENER] Listening on products_update channel')

        while True:
            try:
                if select.select([conn], [], [], 30) == ([], [], []):
                    continue
                conn.poll()
                while conn.notifies:
                    notify = conn.notifies.pop(0)
                    try:
                        payload = json.loads(notify.payload)
                        cid = payload.get('company_id')
                        # Fetch fresh company products and broadcast
                        try:
                            company_products = database.db_select('products', 'company_id = %s', (cid,))
                            broadcast_products_update('products_snapshot', company_products, cid)
                        except Exception:
                            pass
                    except Exception:
                        pass
            except Exception:
                # Sleep briefly and attempt to reconnect
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    conn = database.get_db_connection()
                    if not conn:
                        return
                    cur = conn.cursor()
                    cur.execute("LISTEN products_update;")
                except Exception:
                    return
    except Exception:
        return


# Start background DB listener thread if DB is enabled
if os.environ.get('DATABASE_URL') and database:
    t = threading.Thread(target=_start_db_notification_listener, daemon=True)
    t.start()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({'error': 'Token missing'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            # Attach full user record if available, include company_id
            user = next((u for u in users if u.get('id') == data.get('id')), None)
            if user:
                request.user = user
            else:
                request.user = data
            # Allow main_admin token type bypass
            if data.get('type') == 'main_admin':
                return f(*args, **kwargs)
            
        except Exception:
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
    
    if any(u['email'] == email for u in users):
        return jsonify({'error': 'User exists'}), 400
    
    # Create a new company for the first user or accept companyId when provided
    if len(users) == 0:
        role = 'admin'
        # create company
        company = {
            'id': len(companies) + 1,
            'name': data.get('companyName', f"{name}'s Company"),
            'plan': plan,
            'createdAt': datetime.now().isoformat()
        }
        companies.append(company)
        company_id = company['id']
    else:
        # If signing up under an existing company provide companyId
        company_id = data.get('companyId') or data.get('company_id')
        if company_id is None:
            # default to first company for simplicity (invitations flow is out-of-scope)
            company_id = companies[0]['id'] if companies else 1
        # If user selected Ultra package, make them an admin for that company.
        # This ensures Ultra signups get admin privileges and land on the Admin dashboard.
        role = 'admin' if plan == 'ultra' else ('cashier' if plan == 'basic' else 'cashier')

    user = {
        'id': len(users) + 1,
        'email': email,
        'password': password,
        'name': name,
        'role': role,
        'plan': plan,
        'company_id': company_id,
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

    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role'], 'company_id': user['company_id']}, 
                      app.config['SECRET_KEY'], algorithm='HS256')

    # persist users and companies
    save_json('users.json', users)
    save_json('companies.json', companies)

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
    
    token = jwt.encode({'id': user['id'], 'email': email, 'role': user['role'], 'company_id': user.get('company_id')}, 
                      app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'token': token,
        'user': {k: v for k, v in user.items() if k != 'password'}
    })

@app.route('/api/auth/me')
@token_required
def me():
    user = next((u for u in users if u['id'] == request.user.get('id')), None)
    if user:
        return jsonify({k: v for k, v in user.items() if k != 'password'})
    return jsonify({'error': 'User not found'}), 404

@app.route('/api/products', methods=['GET', 'POST'])
@token_required
def handle_products():
    if request.method == 'GET':
        # Return products for the user's company only (single source of truth)
        company_id = request.user.get('company_id')
        if not company_id:
            return jsonify({'error': 'Missing company context'}), 400
        company_products = [p for p in products if p.get('company_id') == company_id]

        # Compute producible units for composite products and expose as maxUnits
        def compute_max_units(prod):
            # Prefer inline recipe (file-backed). recipe is list of {productId, quantity}
            recipe = prod.get('recipe') or []
            if recipe:
                max_units = float('inf')
                for ingredient in recipe:
                    pid = ingredient.get('productId')
                    if pid is None:
                        continue
                    raw = next((r for r in company_products if r.get('id') == pid), None)
                    if not raw:
                        return 0
                    available = raw.get('quantity', 0) or 0
                    needed = ingredient.get('quantity', 0) or 0
                    if needed <= 0:
                        return 0
                    possible = available // needed
                    if possible < max_units:
                        max_units = possible
                return int(max_units) if max_units != float('inf') else 0

            # Fallback: if DB is enabled, attempt to compute from composite_components
            if os.environ.get('DATABASE_URL'):
                try:
                    conn = database.get_db_connection()
                    if not conn:
                        return 0
                    cur = conn.cursor()
                    cur.execute("SELECT component_product_id, quantity FROM composite_components WHERE composite_product_id = %s", (prod.get('id'),))
                    rows = cur.fetchall()
                    cur.close()
                    conn.close()
                    if not rows:
                        return 0
                    max_units = float('inf')
                    for row in rows:
                        comp_pid = row.get('component_product_id')
                        per_unit = float(row.get('quantity') or 0)
                        raw = next((r for r in company_products if r.get('id') == comp_pid), None)
                        if not raw:
                            return 0
                        available = raw.get('quantity', 0) or 0
                        if per_unit <= 0:
                            return 0
                        possible = available // per_unit
                        if possible < max_units:
                            max_units = possible
                    return int(max_units) if max_units != float('inf') else 0
                except Exception:
                    return 0

            return 0

        for p in company_products:
            if p.get('isComposite') or p.get('is_composite'):
                p['maxUnits'] = compute_max_units(p)
            else:
                p['maxUnits'] = p.get('quantity', 0)

        return jsonify(company_products)
    
    data = request.get_json()
    # Only admins can create or update products
    if request.user.get('role') != 'admin':
        return jsonify({'error': 'Unauthorized: only admins can create products'}), 403

    company_id = request.user.get('company_id')
    product = {
        'id': len(products) + 1,
        'company_id': company_id,
        'name': data.get('name', ''),
        'price': float(data.get('price', 0)),
        'cost': float(data.get('cost', 0)),
        # For composite products quantity is not tracked on the composite itself
        'quantity': 0 if data.get('recipe') else int(data.get('quantity', 0)),
        'image': data.get('image', ''),
        'category': data.get('category', 'general'),
        'unit': data.get('unit', 'pcs'),
        'recipe': data.get('recipe', []),  # For composite products
        'isComposite': bool(data.get('recipe')),
        'visible_to_cashier': bool(data.get('visible_to_cashier', True)),
        'createdAt': datetime.now().isoformat(),
        'createdBy': request.user.get('id')
    }

    # Plan enforcement: Basic plan cannot create composite products
    company = next((c for c in companies if c.get('id') == company_id), None)
    if product['isComposite'] and company and company.get('plan') == 'basic':
        return jsonify({'error': 'Basic plan cannot create composite products'}), 403

    # Validate recipe ingredients exist and belong to same company
    if product['recipe']:
        for ingredient in product['recipe']:
            pid = ingredient.get('productId')
            if pid is None:
                continue
            ingredient_product = next((p for p in products if p['id'] == pid and p.get('company_id') == company_id), None)
            if not ingredient_product:
                return jsonify({'error': f'Ingredient product not found or does not belong to company: {pid}'}), 400

    # Log product creation for diagnostics
    print(f"[PRODUCT CREATE] company={company_id} by user={request.user.get('id')} payload={product}")

    products.append(product)
    save_json('products.json', products)
    # Broadcast creation to SSE subscribers for this company
    try:
        broadcast_products_update('product_created', product, company_id)
    except Exception:
        pass
    return jsonify(product)

@app.route('/api/products/<int:product_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_product(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    if request.method == 'PUT':
        data = request.get_json()
        # Only admins from same company can update
        if request.user.get('role') != 'admin' or request.user.get('company_id') != product.get('company_id'):
            return jsonify({'error': 'Unauthorized'}), 403

        # Update allowed fields (do not allow quantity change for composite)
        product['name'] = data.get('name', product['name'])
        product['price'] = float(data.get('price', product['price']))
        if not product.get('isComposite'):
            product['quantity'] = int(data.get('quantity', product.get('quantity', 0)))
        product['image'] = data.get('image', product.get('image', ''))
        product['category'] = data.get('category', product.get('category', 'general'))
        product['updatedAt'] = datetime.now().isoformat()
        # Log product update for diagnostics
        print(f"[PRODUCT UPDATE] company={product.get('company_id')} by user={request.user.get('id')} product_id={product_id} updates={data}")
        save_json('products.json', products)
        try:
            broadcast_products_update('product_updated', product, product.get('company_id'))
        except Exception:
            pass
        return jsonify(product)
    
    if request.method == 'DELETE':
        # Only admins from same company can delete
        if request.user.get('role') != 'admin' or request.user.get('company_id') != product.get('company_id'):
            return jsonify({'error': 'Unauthorized'}), 403

        # Log product deletion for diagnostics
        print(f"[PRODUCT DELETE] company={product.get('company_id')} by user={request.user.get('id')} product_id={product_id}")
        products.remove(product)
        save_json('products.json', products)
        try:
            broadcast_products_update('product_deleted', {'id': product_id}, product.get('company_id'))
        except Exception:
            pass
        return jsonify({'message': 'Product deleted successfully'}), 200


@app.route('/api/products/<int:product_id>/max-producible', methods=['GET'])
@token_required
def product_max_producible(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    if not product or not product.get('recipe'):
        return jsonify({'maxUnits': 0, 'limitingIngredient': None})

    max_units = float('inf')
    limiting = None
    for ingredient in product['recipe']:
        # Skip ingredients that are custom/name-only (no productId)
        pid = ingredient.get('productId')
        if pid is None:
            continue
        raw = next((p for p in products if p['id'] == pid and p.get('company_id') == product.get('company_id')), None)
        if not raw:
            # If a referenced raw product is missing, treat as zero producible
            return jsonify({'maxUnits': 0, 'limitingIngredient': None})
        available = raw.get('quantity', 0)
        needed = ingredient.get('quantity', 0)
        possible = available / needed if needed > 0 else 0
        if possible < max_units:
            max_units = possible
            limiting = raw.get('name')

    return jsonify({'maxUnits': int(max_units) if max_units != float('inf') else 0, 'limitingIngredient': limiting})


@app.route('/api/diagnostic', methods=['GET', 'POST', 'OPTIONS'])
def diagnostic():
    # Lightweight diagnostic endpoint to check CORS and request payloads
    if request.method == 'OPTIONS':
        return ('', 204)

    data = None
    try:
        data = request.get_json(silent=True)
    except Exception:
        data = None

    origin = request.headers.get('Origin')
    resp = jsonify({
        'ok': True,
        'origin': origin,
        'received': data,
        'headers': {k: v for k, v in request.headers.items()}
    })
    # Echo CORS header for quick verification
    # echo allowed origin for verification
    allowed = os.environ.get('BACKEND_ALLOWED_ORIGINS', ','.join(allowed_list))
    if allowed.strip() == '*':
        resp.headers['Access-Control-Allow-Origin'] = '*'
    else:
        if origin and origin in [o.strip() for o in allowed.split(',') if o.strip()]:
            resp.headers['Access-Control-Allow-Origin'] = origin
            resp.headers['Vary'] = 'Origin'
    return resp

@app.route('/api/sales', methods=['GET', 'POST'])
@token_required
def handle_sales():
    if request.method == 'GET':
        # Return sales for user's company only
        company_id = request.user.get('company_id')
        user_sales = [s for s in sales if s.get('company_id') == company_id]
        return jsonify(user_sales)

    data = request.get_json()

    # Only cashiers or admins of the same company can create sales
    if request.user.get('role') not in ('cashier', 'admin'):
        return jsonify({'error': 'Unauthorized'}), 403

    company_id = request.user.get('company_id')
    items = data.get('items', [])
    total = float(data.get('total', 0))

    # If a real database is configured, prefer transactional DB-backed sale
    if os.environ.get('DATABASE_URL'):
        cashier_name = next((u['name'] for u in users if u.get('id') == request.user.get('id')), 'Unknown')
        ok, result = database.composite_sale(company_id, request.user.get('id'), cashier_name, items, total)
        if ok:
            # fetch latest company products from DB and broadcast
            try:
                if database:
                    company_products = database.db_select('products', 'company_id = %s', (company_id,))
                    broadcast_products_update('products_snapshot', company_products, company_id)
            except Exception:
                pass
            return jsonify(result)
        else:
            return jsonify(result), 400


    # Validate availability first (operate on copies to ensure transactional behavior)
    insufficient = []
    products_copy = [dict(p) for p in products]

    def find_prod(pid):
        return next((p for p in products_copy if p['id'] == pid and p.get('company_id') == company_id), None)

    for item in items:
        product = find_prod(item['productId'])
        if not product:
            insufficient.append({'productId': item.get('productId'), 'reason': 'Product not found'})
            continue

        qty_needed = item.get('quantity', 0)

        if product.get('isComposite') and product.get('recipe'):
            for ingredient in product['recipe']:
                pid = ingredient.get('productId')
                if pid is None:
                    continue
                ingredient_product = find_prod(pid)
                if not ingredient_product:
                    insufficient.append({'productId': item.get('productId'), 'reason': f"Missing ingredient {pid}"})
                    continue
                required_qty = ingredient.get('quantity', 0) * qty_needed
                if ingredient_product.get('quantity', 0) < required_qty:
                    insufficient.append({
                        'productId': item.get('productId'),
                        'reason': f"Insufficient ingredient {ingredient_product.get('name')}",
                        'needed': required_qty,
                        'available': ingredient_product.get('quantity', 0)
                    })
        else:
            if product.get('quantity', 0) < qty_needed:
                insufficient.append({'productId': item.get('productId'), 'reason': 'Insufficient product quantity', 'needed': qty_needed, 'available': product.get('quantity', 0)})

    if insufficient:
        return jsonify({'error': 'Insufficient stock', 'details': insufficient}), 400

    # Apply deductions to the copy
    total = float(data.get('total', 0))
    total_cogs = 0
    for item in items:
        product = find_prod(item['productId'])
        qty = item.get('quantity', 0)
        if not product:
            continue

        if product.get('isComposite') and product.get('recipe'):
            for ingredient in product['recipe']:
                pid = ingredient.get('productId')
                if pid is None:
                    continue
                ingredient_product = find_prod(pid)
                if not ingredient_product:
                    continue
                required_qty = ingredient.get('quantity', 0) * qty
                ingredient_product['quantity'] = max(0, ingredient_product.get('quantity', 0) - required_qty)
                total_cogs += ingredient_product.get('cost', 0) * required_qty
        else:
            product['quantity'] = max(0, product.get('quantity', 0) - qty)
            total_cogs += product.get('cost', 0) * qty

    # Commit: replace products and append sale atomically
    # Merge products_copy back into products for saving
    for updated in products_copy:
        for i, p in enumerate(products):
            if p['id'] == updated['id'] and p.get('company_id') == company_id:
                products[i] = updated

    sale = {
        'id': len(sales) + 1,
        'company_id': company_id,
        'items': items,
        'total': total,
        'cashierId': request.user.get('id'),
        'cashierName': next((u['name'] for u in users if u.get('id') == request.user.get('id')), 'Unknown'),
        'createdAt': datetime.now().isoformat(),
        'cogs': total_cogs
    }
    sales.append(sale)

    # Persist changes atomically
    save_json('products.json', products)
    save_json('sales.json', sales)
    save_json('expenses.json', expenses)

    # Broadcast updated product snapshot to subscribers for this company
    try:
        company_products = [p for p in products if p.get('company_id') == company_id]
        broadcast_products_update('products_snapshot', company_products, company_id)
    except Exception:
        pass

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
    # Sort activities by timestamp (newest first)
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
    
    # Debug: Print token info
    print(f"Token user: {request.user}")
    print(f"All users: {[{'id': u['id'], 'email': u['email'], 'role': u['role'], 'plan': u['plan']} for u in users]}")
    
    # Get user info from token - handle both string and int IDs
    token_user_id = request.user.get('id')
    token_email = request.user.get('email')
    
    # Find current user - try both ID and email
    current_user = None
    
    # Try by ID (handle both int and string)
    for u in users:
        if str(u['id']) == str(token_user_id) or u['id'] == token_user_id:
            current_user = u
            break
    
    # Fallback: try by email
    if not current_user and token_email:
        current_user = next((u for u in users if u['email'] == token_email), None)
    
    if not current_user:
        return jsonify({
            'error': f'Current user not found. Token ID: {token_user_id}, Email: {token_email}',
            'debug': {
                'tokenUser': request.user,
                'allUsers': [{'id': u['id'], 'email': u['email']} for u in users]
            }
        }), 404
    
    # Check permissions
    if current_user.get('role') != 'admin' or current_user.get('plan') != 'ultra':
        return jsonify({
            'error': f'Ultra admin required. Current: role={current_user.get("role")}, plan={current_user.get("plan")}'
        }), 403
    
    data = request.get_json()
    new_user = {
        'id': len(users) + 1,
        'email': data.get('email', '').lower(),
        'password': data.get('password', 'changeme123'),
        'name': data.get('name', ''),
        'role': data.get('role', 'cashier'),  # Allow role specification
        'plan': current_user.get('plan', 'ultra'),  # Inherit plan from creator
        'active': True,
        'locked': False,
        'pin': data.get('pin', ''),
        'createdBy': current_user['id'],
        # Ensure the created user is assigned to the creator's company
        'company_id': current_user.get('company_id'),
        'createdAt': datetime.now().isoformat()
    }
    users.append(new_user)
    # Persist users to disk so the new user is available for login
    save_json('users.json', users)
    
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
    
    # Optionally return a token for the newly created user so they can sign in immediately
    try:
        token = jwt.encode({'id': new_user['id'], 'email': new_user['email'], 'role': new_user['role'], 'company_id': new_user.get('company_id')}, 
                          app.config['SECRET_KEY'], algorithm='HS256')
    except Exception:
        token = None

    return jsonify({
        'user': {k: v for k, v in new_user.items() if k != 'password'},
        'token': token
    })

@app.route('/api/reminders', methods=['GET', 'POST'])
@token_required
def handle_reminders():
    if request.method == 'GET':
        return jsonify(reminders)
    
    data = request.get_json()
    reminder = {
        'id': len(reminders) + 1,
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'dueDate': data.get('dueDate', ''),
        'priority': data.get('priority', 'medium'),
        'completed': False,
        'createdBy': request.user.get('id'),
        'createdAt': datetime.now().isoformat()
    }
    reminders.append(reminder)
    save_json('reminders.json', reminders)
    return jsonify(reminder)

@app.route('/api/reminders/<int:reminder_id>', methods=['PUT', 'DELETE'])
@token_required
def handle_reminder(reminder_id):
    reminder = next((r for r in reminders if r['id'] == reminder_id), None)
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
        save_json('reminders.json', reminders)
        return jsonify(reminder)
    
    if request.method == 'DELETE':
        reminders.remove(reminder)
        save_json('reminders.json', reminders)
        return jsonify({'message': 'Reminder deleted'}), 200

@app.route('/api/batches', methods=['GET', 'POST'])
def handle_batches():
    # Allow GET without token for basic functionality
    if request.method == 'GET':
        return jsonify([])
    # POST requires token
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Batch created'})

@app.route('/api/production', methods=['GET', 'POST'])
def handle_production():
    if request.method == 'GET':
        return jsonify([])
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Production created'})

@app.route('/api/categories/generate-code', methods=['POST'])
def generate_category_code():
    return jsonify({'code': 'CAT001'})

@app.route('/api/price-history', methods=['GET', 'POST'])
def handle_price_history():
    if request.method == 'GET':
        return jsonify([])
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Price history created'})

@app.route('/api/service-fees', methods=['GET', 'POST'])
def handle_service_fees():
    if request.method == 'GET':
        return jsonify([])
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Service fee created'})

@app.route('/api/service-fees/<int:fee_id>', methods=['PUT', 'DELETE'])
def handle_service_fee(fee_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    if request.method == 'PUT':
        return jsonify({'id': fee_id, 'message': 'Service fee updated'})
    return jsonify({'message': 'Service fee deleted'})

@app.route('/api/discounts', methods=['GET', 'POST'])
def handle_discounts():
    if request.method == 'GET':
        return jsonify([])
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Discount created'})

@app.route('/api/discounts/<int:discount_id>', methods=['PUT', 'DELETE'])
def handle_discount(discount_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    if request.method == 'PUT':
        return jsonify({'id': discount_id, 'message': 'Discount updated'})
    return jsonify({'message': 'Discount deleted'})

@app.route('/api/credit-requests', methods=['GET', 'POST'])
def handle_credit_requests():
    if request.method == 'GET':
        return jsonify([])
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'id': 1, 'message': 'Credit request created'})

@app.route('/api/credit-requests/<int:request_id>/approve', methods=['POST'])
def approve_credit_request(request_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'message': 'Credit request approved'})

@app.route('/api/credit-requests/<int:request_id>/reject', methods=['POST'])
def reject_credit_request(request_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        return jsonify({'error': 'Token missing'}), 401
    return jsonify({'message': 'Credit request rejected'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    host = os.environ.get('HOST', '0.0.0.0')
    # Run without the reloader for predictable single-process behavior during tests
    app.run(debug=False, use_reloader=False, host=host, port=port)