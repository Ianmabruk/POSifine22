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