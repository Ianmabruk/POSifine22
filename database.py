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
        
        # Companies table (multi-tenant)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                plan VARCHAR(50) DEFAULT 'basic',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                password VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(50) DEFAULT 'cashier',
                plan VARCHAR(50) DEFAULT 'trial',
                price INTEGER DEFAULT 0,
                active BOOLEAN DEFAULT true,
                locked BOOLEAN DEFAULT false,
                pin VARCHAR(4),
                permissions JSONB DEFAULT '{}',
                company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                trial_expiry TIMESTAMP
            )
        """)

        # Products table (single source of truth per company)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10,2) DEFAULT 0,
                cost DECIMAL(10,2) DEFAULT 0,
                quantity INTEGER DEFAULT 0,
                unit VARCHAR(50) DEFAULT 'pcs',
                category VARCHAR(100) DEFAULT 'raw',
                is_composite BOOLEAN DEFAULT false,
                expense_only BOOLEAN DEFAULT false,
                visible_to_cashier BOOLEAN DEFAULT true,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT composite_no_stock CHECK (NOT (is_composite AND quantity > 0))
            )
        """)

        # Composite components table: normalized recipe lines
        cur.execute("""
            CREATE TABLE IF NOT EXISTS composite_components (
                id SERIAL PRIMARY KEY,
                composite_product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                component_product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
                quantity NUMERIC(10,4) NOT NULL DEFAULT 1
            )
        """)
        
        # Notify trigger function to publish product changes for LISTEN/NOTIFY
        cur.execute("""
            CREATE OR REPLACE FUNCTION notify_products_update() RETURNS trigger AS $$
            DECLARE
                payload JSON;
            BEGIN
                IF (TG_OP = 'DELETE') THEN
                    payload = json_build_object('company_id', OLD.company_id, 'action', TG_OP, 'product_id', OLD.id);
                ELSE
                    payload = json_build_object('company_id', NEW.company_id, 'action', TG_OP, 'product_id', NEW.id);
                END IF;
                PERFORM pg_notify('products_update', payload::text);
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Attach triggers for INSERT/UPDATE/DELETE on products to notify listeners
        cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'products_notify_insert') THEN
                    CREATE TRIGGER products_notify_insert AFTER INSERT ON products FOR EACH ROW EXECUTE FUNCTION notify_products_update();
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'products_notify_update') THEN
                    CREATE TRIGGER products_notify_update AFTER UPDATE ON products FOR EACH ROW EXECUTE FUNCTION notify_products_update();
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'products_notify_delete') THEN
                    CREATE TRIGGER products_notify_delete AFTER DELETE ON products FOR EACH ROW EXECUTE FUNCTION notify_products_update();
                END IF;
            END$$;
        """)
        
        # Sales table (company-scoped)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
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


def composite_sale(company_id, cashier_id, cashier_name, items, total):
    """
    Perform a sale transactionally in the database.
    - Deducts component stock for composite products
    - Deducts product stock for simple products
    - Validates availability before committing
    Returns (True, sale_row) on success or (False, {'error':.., 'details': [...]}) on failure
    """
    conn = get_db_connection()
    if not conn:
        return False, {'error': 'db_connection_failed'}

    try:
        cur = conn.cursor()
        insufficient = []
        total_cogs = 0

        # We'll collect updates to apply after validation
        updates = []  # tuples of (product_id, new_quantity)

        for item in items:
            pid = item.get('productId')
            qty_needed = item.get('quantity', 0)

            # Check if product exists and belongs to company
            cur.execute("SELECT id, is_composite, company_id FROM products WHERE id = %s", (pid,))
            prod = cur.fetchone()
            if not prod or prod.get('company_id') != company_id:
                insufficient.append({'productId': pid, 'reason': 'Product not found or not in company'})
                continue

            if prod.get('is_composite'):
                # Fetch components FOR UPDATE
                cur.execute("""
                    SELECT cc.component_product_id AS component_id, cc.quantity AS per_unit, p.quantity AS available, p.cost AS cost, p.id AS pid
                    FROM composite_components cc
                    JOIN products p ON p.id = cc.component_product_id
                    WHERE cc.composite_product_id = %s
                    FOR UPDATE
                """, (pid,))
                comps = cur.fetchall()
                if not comps:
                    insufficient.append({'productId': pid, 'reason': 'Composite product missing components'})
                    continue

                for comp in comps:
                    required = float(comp.get('per_unit', 0)) * qty_needed
                    available = float(comp.get('available', 0) or 0)
                    if available < required:
                        insufficient.append({'productId': pid, 'reason': f"Insufficient component {comp.get('component_id')}", 'needed': required, 'available': available})
                    else:
                        new_q = available - required
                        updates.append((comp.get('pid'), new_q))
                        total_cogs += float(comp.get('cost') or 0) * required
            else:
                # Simple product; lock row FOR UPDATE
                cur.execute("SELECT id, quantity, cost FROM products WHERE id = %s FOR UPDATE", (pid,))
                p = cur.fetchone()
                if not p:
                    insufficient.append({'productId': pid, 'reason': 'Product not found'})
                    continue
                available = float(p.get('quantity') or 0)
                if available < qty_needed:
                    insufficient.append({'productId': pid, 'reason': 'Insufficient product quantity', 'needed': qty_needed, 'available': available})
                else:
                    new_q = available - qty_needed
                    updates.append((p.get('id'), new_q))
                    total_cogs += float(p.get('cost') or 0) * qty_needed

        if insufficient:
            conn.rollback()
            cur.close()
            conn.close()
            return False, {'error': 'insufficient_stock', 'details': insufficient}

        # Apply updates
        for pid, new_q in updates:
            cur.execute("UPDATE products SET quantity = %s WHERE id = %s", (new_q, pid))

        # Insert sale
        cur.execute("INSERT INTO sales (company_id, items, total, cogs, cashier_id, cashier_name) VALUES (%s, %s, %s, %s, %s, %s) RETURNING *",
                    (company_id, json.dumps(items), total, total_cogs, cashier_id, cashier_name))
        sale = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return True, dict(sale) if sale else (True, None)

    except Exception as e:
        print(f"composite_sale error: {e}")
        try:
            conn.rollback()
            cur.close()
            conn.close()
        except Exception:
            pass
        return False, {'error': 'internal_error', 'message': str(e)}