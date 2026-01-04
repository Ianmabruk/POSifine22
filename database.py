import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json
from datetime import datetime

# Database connection
def get_db_connection():
    """Get database connection"""
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/posifine')
    
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def init_database():
    """Initialize database tables"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                password VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'cashier',
                plan VARCHAR(50) DEFAULT 'trial',
                price INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT true,
                locked BOOLEAN DEFAULT false,
                pin VARCHAR(4),
                permissions JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_expiry TIMESTAMP
            )
        """)
        
        # Products table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) DEFAULT 0,
                cost DECIMAL(10,2) DEFAULT 0,
                quantity INTEGER DEFAULT 0,
                unit VARCHAR(50) DEFAULT 'pcs',
                category VARCHAR(100) DEFAULT 'raw',
                recipe JSONB DEFAULT '[]',
                expense_only BOOLEAN DEFAULT false,
                visible_to_cashier BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Sales table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                items JSONB NOT NULL,
                total DECIMAL(10,2) NOT NULL,
                cogs DECIMAL(10,2) DEFAULT 0,
                profit DECIMAL(10,2) DEFAULT 0,
                payment_method VARCHAR(50) DEFAULT 'cash',
                cashier_id INTEGER REFERENCES users(id),
                cashier_name VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Expenses table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                description VARCHAR(255) NOT NULL,
                amount DECIMAL(10,2) NOT NULL,
                category VARCHAR(100) DEFAULT 'general',
                automatic BOOLEAN DEFAULT false,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Activities table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id SERIAL PRIMARY KEY,
                type VARCHAR(50) NOT NULL,
                user_id INTEGER,
                email VARCHAR(255),
                name VARCHAR(255),
                plan VARCHAR(50),
                user_agent TEXT,
                ip_address VARCHAR(45),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                id SERIAL PRIMARY KEY,
                business_name VARCHAR(255) DEFAULT 'My Business',
                currency VARCHAR(10) DEFAULT 'KES',
                tax_rate DECIMAL(5,2) DEFAULT 16,
                receipt_footer TEXT DEFAULT 'Thank you for your business!',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert default settings if none exist
        cur.execute("SELECT COUNT(*) FROM settings")
        if cur.fetchone()['count'] == 0:
            cur.execute("""
                INSERT INTO settings (business_name, currency, tax_rate, receipt_footer)
                VALUES ('My Business', 'KES', 16, 'Thank you for your business!')
            """)
        
        conn.commit()
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Database initialization error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False

# Database operations
def db_select(table, where_clause="", params=None):
    """Select data from database"""
    conn = get_db_connection()
    if not conn:
        return []
    
    try:
        cur = conn.cursor()
        query = f"SELECT * FROM {table}"
        if where_clause:
            query += f" WHERE {where_clause}"
        
        cur.execute(query, params or ())
        result = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(row) for row in result]
    except Exception as e:
        print(f"Database select error: {e}")
        if conn:
            conn.close()
        return []

def db_insert(table, data):
    """Insert data into database"""
    conn = get_db_connection()
    if not conn:
        return None
    
    try:
        cur = conn.cursor()
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ', '.join(['%s'] * len(values))
        
        query = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders}) RETURNING *"
        cur.execute(query, values)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(result) if result else None
    except Exception as e:
        print(f"Database insert error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return None

def db_update(table, data, where_clause, params=None):
    """Update data in database"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
        query = f"UPDATE {table} SET {set_clause} WHERE {where_clause} RETURNING *"
        
        update_params = list(data.values()) + (params or [])
        cur.execute(query, update_params)
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return dict(result) if result else None
    except Exception as e:
        print(f"Database update error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return None

def db_delete(table, where_clause, params=None):
    """Delete data from database"""
    conn = get_db_connection()
    if not conn:
        return False
    
    try:
        cur = conn.cursor()
        query = f"DELETE FROM {table} WHERE {where_clause}"
        cur.execute(query, params or ())
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Database delete error: {e}")
        if conn:
            conn.rollback()
            conn.close()
        return False