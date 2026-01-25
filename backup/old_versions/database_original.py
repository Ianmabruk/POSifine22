import psycopg
from psycopg.rows import dict_row
import json
import os
import logging
from datetime import datetime
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

def get_db_url():
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    return 'postgresql://localhost/pos_db'

def init_db():
    try:
        with psycopg.connect(get_db_url()) as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS accounts (
                        id SERIAL PRIMARY KEY,
                        owneremail TEXT UNIQUE,
                        plan TEXT,
                        islocked BOOLEAN DEFAULT FALSE,
                        trialendsat TEXT,
                        createdat TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        email TEXT UNIQUE,
                        password TEXT,
                        name TEXT,
                        role TEXT,
                        plan TEXT,
                        accountid INTEGER REFERENCES accounts(id),
                        active BOOLEAN DEFAULT TRUE,
                        locked BOOLEAN DEFAULT FALSE,
                        pin TEXT,
                        cashierpin TEXT,
                        createdby INTEGER,
                        createdat TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS products (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id),
                        name TEXT,
                        price REAL,
                        cost REAL DEFAULT 0,
                        quantity INTEGER DEFAULT 0,
                        image TEXT,
                        category TEXT DEFAULT 'general',
                        unit TEXT DEFAULT 'pcs',
                        recipe TEXT DEFAULT '[]',
                        iscomposite BOOLEAN DEFAULT FALSE,
                        createdat TEXT,
                        createdby INTEGER,
                        updatedat TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS sales (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id),
                        items TEXT,
                        total REAL,
                        cashierid INTEGER,
                        cashiername TEXT,
                        createdat TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS expenses (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id),
                        description TEXT,
                        amount REAL,
                        createdat TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS activities (
                        id SERIAL PRIMARY KEY,
                        type TEXT,
                        userid INTEGER,
                        email TEXT,
                        name TEXT,
                        plan TEXT,
                        createdby INTEGER,
                        timestamp TEXT
                    );
                    
                    CREATE TABLE IF NOT EXISTS settings (
                        id SERIAL PRIMARY KEY,
                        screenlockpassword TEXT DEFAULT '2005',
                        businessname TEXT DEFAULT 'My Business'
                    );
                ''')
                
                cursor.execute('SELECT COUNT(*) FROM settings')
                if cursor.fetchone()[0] == 0:
                    cursor.execute('INSERT INTO settings (screenlockpassword, businessname) VALUES (%s, %s)', 
                                  ('2005', 'My Business'))
            conn.commit()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

def get_db():
    try:
        conn = psycopg.connect(get_db_url(), row_factory=dict_row)
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

def create_account(owner_email, plan, trial_ends_at):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO accounts (owneremail, plan, trialendsat, createdat)
                    VALUES (%s, %s, %s, %s) RETURNING id
                ''', (owner_email, plan, trial_ends_at, datetime.now().isoformat()))
                return cursor.fetchone()['id']
    except Exception as e:
        logger.error(f"Failed to create account: {e}")
        raise

def get_account(account_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM accounts WHERE id = %s', (account_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get account: {e}")
        return None

def create_user(email, password, name, role, plan, account_id, pin=None, created_by=None):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO users (email, password, name, role, plan, accountid, pin, cashierpin, createdby, createdat)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                ''', (email, password, name, role, plan, account_id, pin, pin, created_by, datetime.now().isoformat()))
                return cursor.fetchone()['id']
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise

def get_user_by_email(email):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get user by email: {e}")
        return None

def get_user_by_id(user_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get user by id: {e}")
        return None

def get_users_by_account(account_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users WHERE accountid = %s', (account_id,))
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get users by account: {e}")
        return []

def get_all_users():
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('SELECT * FROM users')
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get all users: {e}")
        return []

# Product operations
def create_product(account_id, name, price, cost, quantity, image, category, unit, recipe, is_composite, created_by):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (accountId, name, price, cost, quantity, image, category, unit, recipe, isComposite, createdAt, createdBy)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
    ''', (account_id, name, price, cost, quantity, image, category, unit, json.dumps(recipe), is_composite, datetime.now().isoformat(), created_by))
    product_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return product_id

def get_products_by_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE accountId = %s', (account_id,))
    rows = cursor.fetchall()
    products = []
    for row in rows:
        product = dict(row)
        product['recipe'] = json.loads(product['recipe']) if product['recipe'] else []
        products.append(product)
    conn.close()
    return products

def update_product(product_id, **kwargs):
    conn = get_db()
    cursor = conn.cursor()
    
    set_clause = []
    values = []
    for key, value in kwargs.items():
        set_clause.append(f"{key} = %s")
        values.append(value)
    
    if set_clause:
        values.append(datetime.now().isoformat())
        values.append(product_id)
        cursor.execute(f'''
            UPDATE products SET {", ".join(set_clause)}, updatedAt = %s
            WHERE id = %s
        ''', values)
        conn.commit()
    
    conn.close()

def delete_product(product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = %s', (product_id,))
    conn.commit()
    conn.close()

# Sales operations
def create_sale(account_id, items, total, cashier_id, cashier_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sales (accountId, items, total, cashierId, cashierName, createdAt)
        VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
    ''', (account_id, json.dumps(items), total, cashier_id, cashier_name, datetime.now().isoformat()))
    sale_id = cursor.fetchone()[0]
    conn.commit()
    conn.close()
    return sale_id

def get_sales_by_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sales WHERE accountId = %s', (account_id,))
    rows = cursor.fetchall()
    sales = []
    for row in rows:
        sale = dict(row)
        sale['items'] = json.loads(sale['items']) if sale['items'] else []
        sales.append(sale)
    conn.close()
    return sales

# Activity operations
def create_activity(activity_type, user_id, email, name, plan, created_by=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO activities (type, userId, email, name, plan, createdBy, timestamp)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    ''', (activity_type, user_id, email, name, plan, created_by, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def get_all_activities():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM activities ORDER BY timestamp DESC')
    result = list_from_rows(cursor.fetchall())
    conn.close()
    return result

# Settings operations
def get_settings():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM settings LIMIT 1')
    result = dict_from_row(cursor.fetchone())
    conn.close()
    return result or {'screenLockPassword': '2005', 'businessName': 'My Business'}

def update_settings(**kwargs):
    conn = get_db()
    cursor = conn.cursor()
    
    set_clause = []
    values = []
    for key, value in kwargs.items():
        set_clause.append(f"{key} = %s")
        values.append(value)
    
    if set_clause:
        cursor.execute(f'UPDATE settings SET {", ".join(set_clause)} WHERE id = 1', values)
        conn.commit()
    
    conn.close()


# ============================================================================
# NEW PRODUCTION FUNCTIONS FOR SHIFTS, STOCK LOGS, AND REAL-TIME SYNC
# ============================================================================

# SHIFT OPERATIONS (Clock In/Out)
def clock_in(account_id, user_id, username):
    """Clock in a user and create a new shift"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                # Check if user already has an open shift
                cursor.execute('''
                    SELECT id FROM shifts 
                    WHERE userid = %s AND accountid = %s AND status = 'open'
                    LIMIT 1
                ''', (user_id, account_id))
                
                existing_shift = cursor.fetchone()
                if existing_shift:
                    return {'error': 'User already has an open shift', 'shift_id': existing_shift['id']}
                
                # Create new shift
                cursor.execute('''
                    INSERT INTO shifts (accountid, userid, username, clockintime, status)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP, 'open')
                    RETURNING id, clockintime
                ''', (account_id, user_id, username))
                
                result = cursor.fetchone()
                conn.commit()
                return {'shift_id': result['id'], 'clock_in_time': result['clockintime'].isoformat()}
    except Exception as e:
        logger.error(f"Failed to clock in: {e}")
        return {'error': str(e)}

def clock_out(shift_id):
    """Clock out a user and close the shift"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    UPDATE shifts 
                    SET status = 'closed', clockouttime = CURRENT_TIMESTAMP
                    WHERE id = %s AND status = 'open'
                    RETURNING id, clockouttime, totalsales, totalexpenses
                ''', (shift_id,))
                
                result = cursor.fetchone()
                conn.commit()
                
                if result:
                    return {
                        'shift_id': result['id'],
                        'clock_out_time': result['clockouttime'].isoformat(),
                        'total_sales': result['totalsales'],
                        'total_expenses': result['totalexpenses']
                    }
                else:
                    return {'error': 'Shift not found or already closed'}
    except Exception as e:
        logger.error(f"Failed to clock out: {e}")
        return {'error': str(e)}

def get_user_open_shift(account_id, user_id):
    """Get the currently open shift for a user"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT id, clockintime, totalsales, totalexpenses 
                    FROM shifts
                    WHERE userid = %s AND accountid = %s AND status = 'open'
                    LIMIT 1
                ''', (user_id, account_id))
                
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get user open shift: {e}")
        return None


# STOCK LOG OPERATIONS (Atomic Transaction Tracking)
def create_stock_log(account_id, product_id, quantity_changed, log_type, reason, sale_id=None, user_id=None, previous_qty=None, new_qty=None):
    """Create a stock log entry for tracking"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO stock_logs 
                    (accountid, productid, quantitychanged, logtype, reason, saleid, userid, previousquantity, newquantity)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                ''', (account_id, product_id, quantity_changed, log_type, reason, sale_id, user_id, previous_qty, new_qty))
                
                result = cursor.fetchone()
                conn.commit()
                return result['id'] if result else None
    except Exception as e:
        logger.error(f"Failed to create stock log: {e}")
        return None

def get_stock_logs(account_id, product_id=None, limit=100):
    """Get stock logs for auditing"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                if product_id:
                    cursor.execute('''
                        SELECT * FROM stock_logs
                        WHERE accountid = %s AND productid = %s
                        ORDER BY createdat DESC
                        LIMIT %s
                    ''', (account_id, product_id, limit))
                else:
                    cursor.execute('''
                        SELECT * FROM stock_logs
                        WHERE accountid = %s
                        ORDER BY createdat DESC
                        LIMIT %s
                    ''', (account_id, limit))
                
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get stock logs: {e}")
        return []

def get_daily_stock_summary(account_id, product_id):
    """Get daily stock changes for a product"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT 
                        logtype,
                        SUM(quantitychanged) as total_changed,
                        COUNT(*) as transaction_count
                    FROM stock_logs
                    WHERE accountid = %s AND productid = %s 
                    AND DATE(createdat) = CURRENT_DATE
                    GROUP BY logtype
                ''', (account_id, product_id))
                
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get daily stock summary: {e}")
        return []


# REAL-TIME MONITOR CACHE (for performance)
def set_monitor_cache(account_id, key, value, ttl_seconds=300):
    """Set cache for real-time monitor stats"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO monitor_cache (accountid, key, value, expirat, updatedat)
                    VALUES (%s, %s, %s, CURRENT_TIMESTAMP + INTERVAL '%s seconds', CURRENT_TIMESTAMP)
                    ON CONFLICT (accountid, key) DO UPDATE SET
                        value = EXCLUDED.value,
                        expirat = CURRENT_TIMESTAMP + INTERVAL '%s seconds',
                        updatedat = CURRENT_TIMESTAMP
                ''', (account_id, key, value, ttl_seconds, ttl_seconds))
                
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Failed to set monitor cache: {e}")
        return False

def get_monitor_cache(account_id, key):
    """Get cached value if not expired"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT value FROM monitor_cache
                    WHERE accountid = %s AND key = %s AND expirat > CURRENT_TIMESTAMP
                ''', (account_id, key))
                
                result = cursor.fetchone()
                return result['value'] if result else None
    except Exception as e:
        logger.error(f"Failed to get monitor cache: {e}")
        return None


# AUDIT LOG OPERATIONS (Compliance & Security)
def create_audit_log(account_id, user_id, action, entity_type, entity_id, old_values=None, new_values=None, ip_address=None, user_agent=None):
    """Create audit log for compliance"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    INSERT INTO audit_log 
                    (accountid, userid, action, entitytype, entityid, oldvalues, newvalues, ipaddress, useragent)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (account_id, user_id, action, entity_type, entity_id, 
                      json.dumps(old_values) if old_values else None,
                      json.dumps(new_values) if new_values else None,
                      ip_address, user_agent))
                
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        return False

def get_audit_logs(account_id, limit=100):
    """Get audit logs for an account"""
    try:
        with get_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute('''
                    SELECT * FROM audit_log
                    WHERE accountid = %s
                    ORDER BY createdat DESC
                    LIMIT %s
                ''', (account_id, limit))
                
                return cursor.fetchall()
    except Exception as e:
        logger.error(f"Failed to get audit logs: {e}")
        return []