"""
Database Schema Extensions for Production POS System
Adds support for:
- Atomic transactions with shifts
- Stock tracking with logs
- Role-based access control
- Business type support
- Real-time monitoring
"""

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

def run_migrations():
    """Run all necessary database migrations"""
    try:
        with psycopg.connect(get_db_url()) as conn:
            with conn.cursor() as cursor:
                
                # 1. Add businessType to existing tables
                print("📍 Adding businessType columns...")
                cursor.execute('''
                    ALTER TABLE accounts ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic';
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic';
                    ALTER TABLE products ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic';
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS businesstype TEXT DEFAULT 'generic';
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS discount REAL DEFAULT 0;
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS tax REAL DEFAULT 0;
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS subtotal REAL DEFAULT 0;
                ''')
                
                # 2. Create shifts table
                print("📍 Creating shifts table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS shifts (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                        userid INTEGER REFERENCES users(id) ON DELETE CASCADE,
                        username TEXT,
                        clockintime TIMESTAMP WITH TIME ZONE NOT NULL,
                        clockouttime TIMESTAMP WITH TIME ZONE,
                        totalsales REAL DEFAULT 0,
                        totalexpenses REAL DEFAULT 0,
                        status TEXT DEFAULT 'open',
                        notes TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_open_shift UNIQUE (userid, accountid) WHERE status = 'open'
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_shifts_userid ON shifts(userid);
                    CREATE INDEX IF NOT EXISTS idx_shifts_accountid ON shifts(accountid);
                    CREATE INDEX IF NOT EXISTS idx_shifts_status ON shifts(status);
                ''')
                
                # 3. Create stock_logs table
                print("📍 Creating stock_logs table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS stock_logs (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
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
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_stock_logs_productid ON stock_logs(productid);
                    CREATE INDEX IF NOT EXISTS idx_stock_logs_accountid ON stock_logs(accountid);
                    CREATE INDEX IF NOT EXISTS idx_stock_logs_createdat ON stock_logs(createdat);
                    CREATE INDEX IF NOT EXISTS idx_stock_logs_type ON stock_logs(logtype);
                ''')
                
                # 4. Create roles table
                print("📍 Creating roles table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS roles (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        permissions TEXT NOT NULL DEFAULT '[]',
                        description TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_role_per_account UNIQUE (accountid, name)
                    );
                    
                    -- Insert default roles
                    INSERT INTO roles (accountid, name, permissions, description) VALUES 
                        (NULL, 'admin', '["all"]', 'Full system access')
                    ON CONFLICT DO NOTHING;
                ''')
                
                # 5. Create business_modules table
                print("📍 Creating business_modules table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS business_modules (
                        id SERIAL PRIMARY KEY,
                        businesstype TEXT UNIQUE NOT NULL,
                        features TEXT NOT NULL DEFAULT '[]',
                        adminmodules TEXT NOT NULL DEFAULT '[]',
                        cashiermodules TEXT NOT NULL DEFAULT '[]',
                        metadata TEXT NOT NULL DEFAULT '{}',
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                ''')
                
                # 6. Create monitor_cache table (for real-time stats)
                print("📍 Creating monitor_cache table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS monitor_cache (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                        key TEXT NOT NULL,
                        value TEXT,
                        expirat TIMESTAMP WITH TIME ZONE,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        updatedat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        CONSTRAINT unique_cache_key UNIQUE (accountid, key)
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_monitor_cache_accountid ON monitor_cache(accountid);
                ''')
                
                # 7. Add transaction support columns to sales
                print("📍 Enhancing sales table...")
                cursor.execute('''
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS transactionstatus TEXT DEFAULT 'completed' CHECK (transactionstatus IN ('pending', 'completed', 'refunded', 'failed'));
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS shiftid INTEGER REFERENCES shifts(id) ON DELETE SET NULL;
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS paymentmethod TEXT DEFAULT 'cash';
                    ALTER TABLE sales ADD COLUMN IF NOT EXISTS notes TEXT;
                    
                    CREATE INDEX IF NOT EXISTS idx_sales_shiftid ON sales(shiftid);
                    CREATE INDEX IF NOT EXISTS idx_sales_transactionstatus ON sales(transactionstatus);
                    CREATE INDEX IF NOT EXISTS idx_sales_createdat ON sales(createdat);
                ''')
                
                # 8. Create audit_log table for compliance
                print("📍 Creating audit_log table...")
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS audit_log (
                        id SERIAL PRIMARY KEY,
                        accountid INTEGER REFERENCES accounts(id) ON DELETE CASCADE,
                        userid INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        action TEXT NOT NULL,
                        entitytype TEXT NOT NULL,
                        entityid INTEGER,
                        oldvalues TEXT,
                        newvalues TEXT,
                        ipaddress TEXT,
                        useragent TEXT,
                        createdat TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    
                    CREATE INDEX IF NOT EXISTS idx_audit_log_accountid ON audit_log(accountid);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_userid ON audit_log(userid);
                    CREATE INDEX IF NOT EXISTS idx_audit_log_createdat ON audit_log(createdat);
                ''')
                
                conn.commit()
                logger.info("✅ All migrations completed successfully")
                print("\n✅ Database migrations completed successfully!")
                return True
                
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        print(f"\n❌ Migration failed: {e}")
        return False

if __name__ == '__main__':
    run_migrations()
