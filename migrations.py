"""
Database Schema Extensions for Production POS System
Adds support for:
- Atomic transactions with shifts
- Stock tracking with logs
- Role-based access control
- Business type support
- Real-time monitoring

With psycopg3, autocommit mode makes each DDL its own transaction.
For multi-statement batches, split into individual execute calls so
each statement is isolated.
"""

import os
from dotenv import load_dotenv
load_dotenv()

import psycopg
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def get_db_url():
    import os
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
    return 'postgresql://localhost/pos_db'

def _safe_execute(cursor, sql, desc):
    """Execute a single DDL statement, log on failure, never raise."""
    try:
        cursor.execute(sql)
        logger.info(f"✅ Migration: {desc}")
    except Exception as e:
        logger.warning(f"Migration warning for {desc}: {e}")

def run_migrations():
    """Run all necessary database migrations.

    Uses AUTOCOMMIT mode so each DDL statement is its own transaction.
    This prevents a deadlock on one statement from aborting the entire
    migration batch.
    """
    try:
        with psycopg.connect(get_db_url()) as conn:
            conn.autocommit = True
            with conn.cursor() as cursor:
                
                # 1. Add businessType to existing tables
                print("📍 Adding businessType columns...")
                _safe_execute(cursor, "ALTER TABLE accounts ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic'", "Added businesstype to accounts")
                _safe_execute(cursor, "ALTER TABLE users ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic'", "Added businesstype to users")
                _safe_execute(cursor, "ALTER TABLE products ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic'", "Added businesstype to products")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic'", "Added businesstype to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount REAL DEFAULT 0", "Added discount to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS tax REAL DEFAULT 0", "Added tax to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS subtotal REAL DEFAULT 0", "Added subtotal to sales")
                
                # 2. Create shifts table
                print("📍 Creating shifts table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS shifts (
                        id SERIAL PRIMARY KEY,
                        accountid TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        userid INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        username TEXT,
                        clockintime TIMESTAMP WITH TIME ZONE NOT NULL,
                        clockouttime TIMESTAMP WITH TIME ZONE,
                        totalsales REAL DEFAULT 0,
                        totalexpenses REAL DEFAULT 0,
                        status TEXT DEFAULT 'open',
                        notes TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_shifts_userid ON shifts(userid)", "Created index: idx_shifts_userid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_shifts_accountid ON shifts(accountid)", "Created index: idx_shifts_accountid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status)", "Created index: idx_shifts_status")
                _safe_execute(cursor, "CREATE UNIQUE INDEX IF NOT EXISTS idx_shifts_unique_open ON shifts(userid, accountid) WHERE status = 'open'", "Created unique index: idx_shifts_unique_open")
                
                # 3. Create stock_logs table
                print("📍 Creating stock_logs table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS stock_logs (
                        id SERIAL PRIMARY KEY,
                        accountid TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        productid INTEGER REFERENCES products(id) ON DELETE CASCADE,
                        quantitychanged REAL NOT NULL,
                        logtype TEXT NOT NULL CHECK (logtype IN ('add', 'deduct', 'adjust', 'sale')),
                        reason TEXT,
                        saleid INTEGER REFERENCES sales(id) ON DELETE SET NULL,
                        userid INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        previousquantity REAL,
                        newquantity REAL,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT positive_quantity CHECK (newquantity >= 0)
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_stock_logs_productid ON stock_logs(productid)", "Created index: idx_stock_logs_productid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_stock_logs_accountid ON stock_logs(accountid)", "Created index: idx_stock_logs_accountid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_stock_logs_createdat ON stock_logs(createdat)", "Created index: idx_stock_logs_createdat")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_stock_logs_type ON stock_logs(logtype)", "Created index: idx_stock_logs_type")
                
                # 4. Create roles table
                print("📍 Creating roles table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS roles (
                        id SERIAL PRIMARY KEY,
                        accountid TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        permissions TEXT NOT NULL DEFAULT '[]',
                        description TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_role_per_account UNIQUE (accountid, name)
                    )
                """)
                # Insert default roles
                _safe_execute(cursor, "INSERT INTO roles (accountid, name, permissions, description) VALUES (NULL, 'admin', '[\"all\"]', 'Full system access') ON CONFLICT DO NOTHING", "Inserted default admin role")
                
                # 5. Create business_modules table
                print("📍 Creating business_modules table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS business_modules (
                        id SERIAL PRIMARY KEY,
                        businesstype TEXT UNIQUE NOT NULL,
                        features TEXT NOT NULL DEFAULT '[]',
                        adminmodules TEXT NOT NULL DEFAULT '[]',
                        cashiermodules TEXT NOT NULL DEFAULT '[]',
                        metadata TEXT NOT NULL DEFAULT '{}',
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 6. Create monitor_cache table (for real-time stats)
                print("📍 Creating monitor_cache table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS monitor_cache (
                        id SERIAL PRIMARY KEY,
                        accountid TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        key TEXT NOT NULL,
                        value TEXT,
                        expirat TIMESTAMP WITH TIME ZONE,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updatedat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_cache_key UNIQUE (accountid, key)
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_monitor_cache_accountid ON monitor_cache(accountid)", "Created index: idx_monitor_cache_accountid")
                
                # 7. Extend reminders table
                print("📍 Updating reminders table...")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS priority TEXT DEFAULT 'normal'", "Added priority to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending'", "Added status to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS expires_at TEXT", "Added expires_at to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS target_users JSONB DEFAULT '[]'", "Added target_users to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS admin_note TEXT", "Added admin_note to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS cashier_note TEXT", "Added cashier_note to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS admin_signature TEXT", "Added admin_signature to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS cashier_signature TEXT", "Added cashier_signature to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS admin_signed_at TEXT", "Added admin_signed_at to reminders")
                _safe_execute(cursor, "ALTER TABLE reminders ADD COLUMN IF NOT EXISTS cashier_signed_at TEXT", "Added cashier_signed_at to reminders")
                
                # 7. Add transaction support columns to sales
                print("📍 Enhancing sales table...")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS transactionstatus TEXT DEFAULT 'completed' CHECK (transactionstatus IN ('pending', 'completed', 'refunded', 'failed'))", "Added transactionstatus to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS shiftid INTEGER REFERENCES shifts(id) ON DELETE SET NULL", "Added shiftid to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS paymentmethod TEXT DEFAULT 'cash'", "Added paymentmethod to sales")
                _safe_execute(cursor, "ALTER TABLE sales ADD COLUMN IF NOT EXISTS notes TEXT", "Added notes to sales")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_sales_shiftid ON sales(shiftid)", "Created index: idx_sales_shiftid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_sales_transactionstatus ON sales(transactionstatus)", "Created index: idx_sales_transactionstatus")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_sales_createdat ON sales(created_at)", "Created index: idx_sales_createdat")
                
                # 8. Create audit_log table for compliance
                print("📍 Creating audit_log table...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id SERIAL PRIMARY KEY,
                        accountid TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        userid INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        action TEXT NOT NULL,
                        entitytype TEXT NOT NULL,
                        entityid INTEGER,
                        oldvalues TEXT,
                        newvalues TEXT,
                        ipaddress TEXT,
                        useragent TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_audit_log_accountid ON audit_log(accountid)", "Created index: idx_audit_log_accountid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_audit_log_userid ON audit_log(userid)", "Created index: idx_audit_log_userid")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_audit_log_createdat ON audit_log(createdat)", "Created index: idx_audit_log_createdat")
                
                # 8. Add auth optimization indexes
                print("📍 Adding auth optimization indexes...")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)", "Created index: idx_users_email")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token_hash ON sessions(refresh_token_hash)", "Created index: idx_sessions_refresh_token_hash")
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_sessions_account_id ON sessions(account_id)", "Created index: idx_sessions_account_id")

                # School / Pro-plan tables
                print("📍 Creating school tables (students, fee_payments, exam_results, assignments, school_notices)...")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS students (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        admission_number TEXT,
                        class_name TEXT,
                        parent_name TEXT,
                        parent_phone TEXT,
                        notes TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_by INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_students_account ON students(account_id)", "Created index: idx_students_account")
                _safe_execute(cursor, "ALTER TABLE students ADD COLUMN IF NOT EXISTS student_image TEXT", "Added student_image to students")
                _safe_execute(cursor, "ALTER TABLE students ADD COLUMN IF NOT EXISTS id_image TEXT", "Added id_image to students")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS fee_payments (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
                        term TEXT,
                        year INTEGER,
                        amount_due REAL DEFAULT 0,
                        amount_paid REAL DEFAULT 0,
                        balance REAL GENERATED ALWAYS AS (amount_due - amount_paid) STORED,
                        payment_date TIMESTAMP WITH TIME ZONE,
                        payment_method TEXT DEFAULT 'cash',
                        notes TEXT,
                        created_by INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_fee_payments_student ON fee_payments(student_id)", "Created index: idx_fee_payments_student")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS exam_results (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
                        subject TEXT NOT NULL,
                        score REAL,
                        max_score REAL DEFAULT 100,
                        grade TEXT,
                        term TEXT,
                        year INTEGER,
                        exam_type TEXT DEFAULT 'end_term',
                        notes TEXT,
                        created_by INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_exam_results_student ON exam_results(student_id)", "Created index: idx_exam_results_student")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS assignments (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        class_name TEXT,
                        subject TEXT,
                        title TEXT NOT NULL,
                        description TEXT,
                        due_date TIMESTAMP WITH TIME ZONE,
                        created_by INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_assignments_account ON assignments(account_id)", "Created index: idx_assignments_account")

                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS school_notices (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT REFERENCES accounts(id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        body TEXT,
                        audience TEXT DEFAULT 'all',
                        created_by INTEGER,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    )
                 """)
                _safe_execute(cursor, "CREATE INDEX IF NOT EXISTS idx_school_notices_account ON school_notices(account_id)", "Created index: idx_school_notices_account")

                # Add missing columns to credit_requests
                print("📍 Adding missing columns to credit_requests...")
                _safe_execute(cursor, "ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS customer_name TEXT", "Added customer_name to credit_requests")
                _safe_execute(cursor, "ALTER TABLE credit_requests ADD COLUMN IF NOT EXISTS notes TEXT", "Added notes to credit_requests")

                # Add deviceMode to users
                print("📍 Adding deviceMode to users...")
                _safe_execute(cursor, "ALTER TABLE users ADD COLUMN IF NOT EXISTS device_mode TEXT", "Added device_mode to users")

                logger.info("✅ All migrations completed successfully")
                print("\n✅ Database migrations completed successfully!")
                return True
                
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        print(f"\n❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    run_migrations()
