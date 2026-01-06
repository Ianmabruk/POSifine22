import sqlite3
import json
import os
from datetime import datetime

DB_PATH = '/tmp/pos_database.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Create tables
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ownerEmail TEXT UNIQUE,
            plan TEXT,
            isLocked BOOLEAN DEFAULT 0,
            trialEndsAt TEXT,
            createdAt TEXT
        );
        
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE,
            password TEXT,
            name TEXT,
            role TEXT,
            plan TEXT,
            accountId INTEGER,
            active BOOLEAN DEFAULT 1,
            locked BOOLEAN DEFAULT 0,
            pin TEXT,
            createdBy INTEGER,
            createdAt TEXT,
            FOREIGN KEY (accountId) REFERENCES accounts (id)
        );
        
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accountId INTEGER,
            name TEXT,
            price REAL,
            cost REAL DEFAULT 0,
            quantity INTEGER DEFAULT 0,
            image TEXT,
            category TEXT DEFAULT 'general',
            unit TEXT DEFAULT 'pcs',
            recipe TEXT DEFAULT '[]',
            isComposite BOOLEAN DEFAULT 0,
            createdAt TEXT,
            createdBy INTEGER,
            updatedAt TEXT,
            FOREIGN KEY (accountId) REFERENCES accounts (id)
        );
        
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accountId INTEGER,
            items TEXT,
            total REAL,
            cashierId INTEGER,
            cashierName TEXT,
            createdAt TEXT,
            FOREIGN KEY (accountId) REFERENCES accounts (id)
        );
        
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accountId INTEGER,
            description TEXT,
            amount REAL,
            createdAt TEXT,
            FOREIGN KEY (accountId) REFERENCES accounts (id)
        );
        
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            userId INTEGER,
            email TEXT,
            name TEXT,
            plan TEXT,
            createdBy INTEGER,
            timestamp TEXT
        );
        
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            accountId INTEGER,
            title TEXT,
            description TEXT,
            dueDate TEXT,
            priority TEXT DEFAULT 'medium',
            completed BOOLEAN DEFAULT 0,
            createdBy INTEGER,
            createdAt TEXT,
            FOREIGN KEY (accountId) REFERENCES accounts (id)
        );
        
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screenLockPassword TEXT DEFAULT '2005',
            businessName TEXT DEFAULT 'My Business'
        );
    ''')
    
    # Insert default settings if not exists
    cursor.execute('SELECT COUNT(*) FROM settings')
    if cursor.fetchone()[0] == 0:
        cursor.execute('INSERT INTO settings (screenLockPassword, businessName) VALUES (?, ?)', 
                      ('2005', 'My Business'))
    
    conn.commit()
    conn.close()

def get_db():
    if not os.path.exists(DB_PATH):
        init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def dict_from_row(row):
    return dict(row) if row else None

def list_from_rows(rows):
    return [dict(row) for row in rows]

# Account operations
def create_account(owner_email, plan, trial_ends_at):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO accounts (ownerEmail, plan, trialEndsAt, createdAt)
        VALUES (?, ?, ?, ?)
    ''', (owner_email, plan, trial_ends_at, datetime.now().isoformat()))
    account_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return account_id

def get_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM accounts WHERE id = ?', (account_id,))
    result = dict_from_row(cursor.fetchone())
    conn.close()
    return result

# User operations
def create_user(email, password, name, role, plan, account_id, pin=None, created_by=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO users (email, password, name, role, plan, accountId, pin, createdBy, createdAt)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (email, password, name, role, plan, account_id, pin, created_by, datetime.now().isoformat()))
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return user_id

def get_user_by_email(email):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    result = dict_from_row(cursor.fetchone())
    conn.close()
    return result

def get_user_by_id(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    result = dict_from_row(cursor.fetchone())
    conn.close()
    return result

def get_users_by_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE accountId = ?', (account_id,))
    result = list_from_rows(cursor.fetchall())
    conn.close()
    return result

def get_all_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users')
    result = list_from_rows(cursor.fetchall())
    conn.close()
    return result

# Product operations
def create_product(account_id, name, price, cost, quantity, image, category, unit, recipe, is_composite, created_by):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO products (accountId, name, price, cost, quantity, image, category, unit, recipe, isComposite, createdAt, createdBy)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (account_id, name, price, cost, quantity, image, category, unit, json.dumps(recipe), is_composite, datetime.now().isoformat(), created_by))
    product_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return product_id

def get_products_by_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM products WHERE accountId = ?', (account_id,))
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
        set_clause.append(f"{key} = ?")
        values.append(value)
    
    if set_clause:
        values.append(datetime.now().isoformat())
        values.append(product_id)
        cursor.execute(f'''
            UPDATE products SET {", ".join(set_clause)}, updatedAt = ?
            WHERE id = ?
        ''', values)
        conn.commit()
    
    conn.close()

def delete_product(product_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

# Sales operations
def create_sale(account_id, items, total, cashier_id, cashier_name):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sales (accountId, items, total, cashierId, cashierName, createdAt)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (account_id, json.dumps(items), total, cashier_id, cashier_name, datetime.now().isoformat()))
    sale_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return sale_id

def get_sales_by_account(account_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM sales WHERE accountId = ?', (account_id,))
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
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
        set_clause.append(f"{key} = ?")
        values.append(value)
    
    if set_clause:
        cursor.execute(f'UPDATE settings SET {", ".join(set_clause)} WHERE id = 1', values)
        conn.commit()
    
    conn.close()