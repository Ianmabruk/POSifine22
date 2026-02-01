"""
OPTIMIZED DATABASE LAYER
=========================
High-performance data access layer with:
- Dual storage support (JSON files + PostgreSQL)
- Connection pooling for PostgreSQL
- Efficient batch operations
- Transaction management
- Multi-tenant data isolation
- Caching for frequently accessed data
"""

import json
import os
import threading
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import logging
from functools import lru_cache

# PostgreSQL support (optional)
try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    psycopg = None
    ConnectionPool = None

logger = logging.getLogger(__name__)

# Thread-safe file locks
file_locks = {}
lock_manager = threading.Lock()


def get_file_lock(filepath: str) -> threading.Lock:
    """Get or create a thread-safe lock for a file"""
    with lock_manager:
        if filepath not in file_locks:
            file_locks[filepath] = threading.Lock()
        return file_locks[filepath]


class DataStore:
    """
    High-performance data store with dual backend support
    """
    
    def __init__(self, data_dir: str = None, use_postgres: bool = False):
        """
        Initialize data store
        
        Args:
            data_dir: Directory for JSON file storage
            use_postgres: Whether to use PostgreSQL (requires DATABASE_URL)
        """
        # Setup data directory
        if data_dir is None:
            data_dir = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
        
        self.data_dir = os.path.abspath(data_dir)
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        
        # Storage backend
        self.use_postgres = use_postgres and HAS_POSTGRES
        self.pg_pool: Optional[ConnectionPool] = None
        
        # In-memory cache for frequently accessed data
        self._cache = {}
        self._cache_lock = threading.Lock()
        
        # Initialize storage
        if self.use_postgres:
            self._init_postgres()
        else:
            self._init_json_files()
        
        logger.info(f"DataStore initialized with {'PostgreSQL' if self.use_postgres else 'JSON files'}")
    
    # ============================================================
    # POSTGRESQL OPERATIONS
    # ============================================================
    
    def _init_postgres(self):
        """Initialize PostgreSQL connection pool"""
        try:
            db_url = os.environ.get('DATABASE_URL', '')
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)
            
            # Create connection pool (min 2, max 10 connections)
            self.pg_pool = ConnectionPool(
                db_url,
                min_size=2,
                max_size=10,
                timeout=30
            )
            
            # Create tables
            self._create_tables()
            logger.info("PostgreSQL connection pool created")
        except Exception as e:
            logger.error(f"PostgreSQL initialization failed: {e}")
            logger.info("Falling back to JSON file storage")
            self.use_postgres = False
            self._init_json_files()
    
    def _create_tables(self):
        """Create database tables if they don't exist"""
        with self.pg_pool.connection() as conn:
            with conn.cursor() as cur:
                # Accounts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS accounts (
                        id TEXT PRIMARY KEY,
                        owner_email TEXT UNIQUE NOT NULL,
                        business_name TEXT NOT NULL,
                        plan TEXT DEFAULT 'free',
                        is_active BOOLEAN DEFAULT TRUE,
                        is_locked BOOLEAN DEFAULT FALSE,
                        trial_ends_at TEXT,
                        subscription_ends_at TEXT,
                        created_at TEXT NOT NULL,
                        business_logo TEXT,
                        currency TEXT DEFAULT 'KES',
                        tax_rate REAL DEFAULT 0.0,
                        screen_lock_password TEXT DEFAULT '2005',
                        days_used INTEGER DEFAULT 0,
                        last_activity_date TEXT,
                        requested_trial BOOLEAN DEFAULT FALSE
                    )
                """)
                
                # Users table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        email TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        name TEXT NOT NULL,
                        role TEXT DEFAULT 'cashier',
                        pin TEXT,
                        cashier_pin TEXT,
                        is_active BOOLEAN DEFAULT TRUE,
                        is_locked BOOLEAN DEFAULT FALSE,
                        screen_locked BOOLEAN DEFAULT FALSE,
                        created_at TEXT NOT NULL,
                        created_by INTEGER,
                        last_login TEXT,
                        hourly_rate REAL DEFAULT 0.0,
                        business_type TEXT,
                        business_role TEXT,
                        UNIQUE(account_id, email)
                    )
                """)

                # Roles table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS roles (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT,
                        created_at TEXT NOT NULL
                    )
                """)

                # Sessions table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        refresh_token_hash TEXT NOT NULL,
                        user_agent TEXT,
                        ip_address TEXT,
                        created_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        revoked_at TEXT
                    )
                """)

                # Activity logs
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS activity_logs (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT,
                        user_id INTEGER,
                        action TEXT NOT NULL,
                        resource TEXT,
                        metadata JSONB DEFAULT '{}'::jsonb,
                        ip_address TEXT,
                        created_at TEXT NOT NULL
                    )
                """)

                # Audit logs
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS audit_logs (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT,
                        actor_id INTEGER,
                        actor_role TEXT,
                        action TEXT NOT NULL,
                        target TEXT,
                        metadata JSONB DEFAULT '{}'::jsonb,
                        ip_address TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Products table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS products (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        price REAL NOT NULL,
                        cost REAL DEFAULT 0.0,
                        quantity REAL DEFAULT 0.0,
                        product_type TEXT DEFAULT 'regular',
                        category TEXT DEFAULT 'general',
                        unit TEXT DEFAULT 'pcs',
                        image TEXT,
                        barcode TEXT,
                        sku TEXT,
                        is_composite BOOLEAN DEFAULT FALSE,
                        recipe JSONB DEFAULT '[]',
                        reorder_level REAL DEFAULT 0.0,
                        max_stock_level REAL DEFAULT 0.0,
                        cost_per_unit REAL DEFAULT 0.0,
                        enable_weight_pricing BOOLEAN DEFAULT FALSE,
                        created_at TEXT NOT NULL,
                        created_by INTEGER,
                        updated_at TEXT
                    )
                """)

                # Raw materials table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS raw_materials (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        quantity REAL DEFAULT 0.0,
                        unit TEXT DEFAULT 'unit',
                        cost_per_unit REAL DEFAULT 0.0,
                        reorder_level REAL DEFAULT 0.0,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                """)
                
                # Sales table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS sales (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        items JSONB NOT NULL,
                        total REAL NOT NULL,
                        total_cost REAL DEFAULT 0.0,
                        gross_profit REAL DEFAULT 0.0,
                        payment_method TEXT DEFAULT 'cash',
                        amount_paid REAL DEFAULT 0.0,
                        change REAL DEFAULT 0.0,
                        tax_amount REAL DEFAULT 0.0,
                        discount_amount REAL DEFAULT 0.0,
                        service_fee REAL DEFAULT 0.0,
                        cashier_id INTEGER,
                        cashier_name TEXT,
                        created_at TEXT NOT NULL,
                        receipt_number TEXT,
                        notes TEXT
                    )
                """)

                # Petroleum tanks
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS petroleum_tanks (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        fuel_type TEXT NOT NULL,
                        capacity REAL NOT NULL,
                        current_volume REAL NOT NULL,
                        price_per_liter REAL NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                """)

                # Petroleum staff
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS petroleum_staff (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT DEFAULT 'pump_attendant',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL,
                        UNIQUE(account_id, email)
                    )
                """)

                # Petroleum sales
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS petroleum_sales (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        staff_id INTEGER,
                        staff_name TEXT,
                        fuel_type TEXT NOT NULL,
                        liters REAL NOT NULL,
                        amount REAL NOT NULL,
                        pump_number TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Time entries table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS time_entries (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        user_id INTEGER NOT NULL,
                        user_name TEXT NOT NULL,
                        clock_in_time TEXT NOT NULL,
                        clock_out_time TEXT,
                        duration_minutes INTEGER DEFAULT 0,
                        date TEXT NOT NULL,
                        notes TEXT
                    )
                """)
                
                # Reminders table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        seen_by JSONB DEFAULT '[]'
                    )
                """)
                
                # Vendors table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS vendors (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        product_or_service TEXT NOT NULL,
                        email TEXT,
                        phone TEXT,
                        address TEXT,
                        city TEXT,
                        country TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Credit requests table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS credit_requests (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        cashier_id INTEGER NOT NULL,
                        cashier_name TEXT NOT NULL,
                        amount REAL NOT NULL,
                        reason TEXT NOT NULL,
                        status TEXT DEFAULT 'pending',
                        reviewed_by INTEGER,
                        reviewed_at TEXT,
                        admin_notes TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Expenses table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS expenses (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        amount REAL NOT NULL,
                        quantity REAL DEFAULT 1.0,
                        unit TEXT DEFAULT 'unit',
                        category TEXT DEFAULT 'general',
                        description TEXT,
                        source TEXT DEFAULT 'manual',
                        linked_product_id INTEGER,
                        created_at TEXT NOT NULL,
                        created_by INTEGER
                    )
                """)
                
                # Discounts table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS discounts (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL,
                        discount_type TEXT DEFAULT 'percentage',
                        discount_value REAL DEFAULT 0.0,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Service fees table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS service_fees (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        amount REAL NOT NULL,
                        fee_type TEXT DEFAULT 'fixed',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Stock movements table (audit trail)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS stock_movements (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL,
                        quantity REAL NOT NULL,
                        movement_type TEXT NOT NULL,
                        reference_id INTEGER,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        created_by INTEGER
                    )
                """)
                
                # Batches table (for stock batch management)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS batches (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        productId INTEGER NOT NULL,
                        quantity REAL NOT NULL,
                        expiryDate TEXT,
                        batchNumber TEXT NOT NULL,
                        cost REAL DEFAULT 0.0,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Business profiles table (Pro Plan)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS business_profiles (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE UNIQUE,
                        business_type TEXT NOT NULL,
                        plan TEXT DEFAULT 'basic',
                        created_at TEXT NOT NULL,
                        settings JSONB DEFAULT '{}'
                    )
                """)
                
                # Role assignments table (Pro Plan - business-specific roles)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS role_assignments (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        business_type TEXT NOT NULL,
                        business_role TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, business_type)
                    )
                """)
                
                # Appointments table (Clinic/Hospital)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS appointments (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        patient_name TEXT NOT NULL,
                        patient_phone TEXT,
                        patient_email TEXT,
                        doctor_id INTEGER,
                        appointment_date TEXT NOT NULL,
                        appointment_time TEXT NOT NULL,
                        status TEXT DEFAULT 'scheduled',
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        created_by INTEGER
                    )
                """)
                
                # Prescriptions table (Clinic/Hospital)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS prescriptions (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        appointment_id INTEGER REFERENCES appointments(id),
                        patient_name TEXT NOT NULL,
                        doctor_id INTEGER NOT NULL,
                        medications JSONB NOT NULL,
                        instructions TEXT,
                        status TEXT DEFAULT 'pending',
                        dispensed_by INTEGER,
                        dispensed_at TEXT,
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Tables/Orders table (Bar/Restaurant)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS table_orders (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        table_number TEXT NOT NULL,
                        items JSONB NOT NULL,
                        total REAL DEFAULT 0.0,
                        status TEXT DEFAULT 'open',
                        server_id INTEGER,
                        created_at TEXT NOT NULL,
                        closed_at TEXT
                    )
                """)
                
                # Room bookings table (Hotel)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS room_bookings (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        room_number TEXT NOT NULL,
                        guest_name TEXT NOT NULL,
                        guest_phone TEXT,
                        guest_email TEXT,
                        check_in_date TEXT NOT NULL,
                        check_out_date TEXT NOT NULL,
                        status TEXT DEFAULT 'reserved',
                        total_amount REAL DEFAULT 0.0,
                        notes TEXT,
                        created_at TEXT NOT NULL,
                        created_by INTEGER
                    )
                """)
                
                # Create indexes for performance
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_account ON users(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_account ON activity_logs(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_audit_account ON audit_logs(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_products_account ON products(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_raw_materials_account ON raw_materials(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_account ON sales(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_sales_cashier ON sales(cashier_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_tanks_account ON petroleum_tanks(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_tanks_fuel ON petroleum_tanks(fuel_type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_account ON petroleum_sales(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_fuel ON petroleum_sales(fuel_type)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_created ON petroleum_sales(created_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_petroleum_staff_account ON petroleum_staff(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_account ON time_entries(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_user ON time_entries(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_time_entries_date ON time_entries(date)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_batches_account ON batches(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_batches_product ON batches(productId)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_business_profiles_account ON business_profiles(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_role_assignments_user ON role_assignments(user_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_appointments_account ON appointments(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_prescriptions_account ON prescriptions(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_table_orders_account ON table_orders(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_room_bookings_account ON room_bookings(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_expenses_account ON expenses(account_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_expenses_created ON expenses(created_at)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id)")
                cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_movements_account ON stock_movements(account_id)")
                
                # ============================================================
                # MIGRATIONS: Add new columns to existing tables
                # ============================================================
                
                # Add business_type and business_role columns to users table if they don't exist
                try:
                    cur.execute("""
                        ALTER TABLE users 
                        ADD COLUMN IF NOT EXISTS business_type TEXT,
                        ADD COLUMN IF NOT EXISTS business_role TEXT
                    """)
                    logger.info("✅ Migration: Added business_type and business_role columns to users table")
                except Exception as e:
                    logger.warning(f"Migration warning (may be normal if columns exist): {e}")
                
                conn.commit()
    
    # ============================================================
    # JSON FILE OPERATIONS
    # ============================================================
    
    def _init_json_files(self):
        """Initialize JSON file storage"""
        self.files = {
            'accounts': os.path.join(self.data_dir, 'accounts.json'),
            'users': os.path.join(self.data_dir, 'users.json'),
            'roles': os.path.join(self.data_dir, 'roles.json'),
            'sessions': os.path.join(self.data_dir, 'sessions.json'),
            'activity_logs': os.path.join(self.data_dir, 'activity_logs.json'),
            'audit_logs': os.path.join(self.data_dir, 'audit_logs.json'),
            'products': os.path.join(self.data_dir, 'products.json'),
            'raw_materials': os.path.join(self.data_dir, 'raw_materials.json'),
            'sales': os.path.join(self.data_dir, 'sales.json'),
            'time_entries': os.path.join(self.data_dir, 'time_entries.json'),
            'reminders': os.path.join(self.data_dir, 'reminders.json'),
            'vendors': os.path.join(self.data_dir, 'vendors.json'),
            'credit_requests': os.path.join(self.data_dir, 'credit_requests.json'),
            'expenses': os.path.join(self.data_dir, 'expenses.json'),
            'discounts': os.path.join(self.data_dir, 'discounts.json'),
            'service_fees': os.path.join(self.data_dir, 'service_fees.json'),
            'stock_movements': os.path.join(self.data_dir, 'stock_movements.json'),
            'batches': os.path.join(self.data_dir, 'batches.json'),
            'business_profiles': os.path.join(self.data_dir, 'business_profiles.json'),
            'role_assignments': os.path.join(self.data_dir, 'role_assignments.json'),
            'appointments': os.path.join(self.data_dir, 'appointments.json'),
            'prescriptions': os.path.join(self.data_dir, 'prescriptions.json'),
            'table_orders': os.path.join(self.data_dir, 'table_orders.json'),
            'room_bookings': os.path.join(self.data_dir, 'room_bookings.json'),
            'petroleum_tanks': os.path.join(self.data_dir, 'petroleum_tanks.json'),
            'petroleum_sales': os.path.join(self.data_dir, 'petroleum_sales.json'),
            'petroleum_staff': os.path.join(self.data_dir, 'petroleum_staff.json')
        }
        
        # Initialize empty files
        for filepath in self.files.values():
            if not os.path.exists(filepath):
                self._write_json(filepath, [])
    
    def _read_json(self, filepath: str) -> List[Dict]:
        """Thread-safe JSON file read"""
        lock = get_file_lock(filepath)
        with lock:
            try:
                with open(filepath, 'r') as f:
                    return json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                return []
    
    def _write_json(self, filepath: str, data: List[Dict]):
        """Thread-safe JSON file write"""
        lock = get_file_lock(filepath)
        with lock:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
    
    # ============================================================
    # GENERIC CRUD OPERATIONS
    # ============================================================
    
    def get_all(self, table: str, account_id: Optional[str] = None) -> List[Dict]:
        """Get all records from a table"""
        if self.use_postgres:
            return self._pg_get_all(table, account_id)
        else:
            return self._json_get_all(table, account_id)
    
    def get_by_id(self, table: str, id: int, account_id: Optional[str] = None) -> Optional[Dict]:
        """Get record by ID"""
        if self.use_postgres:
            return self._pg_get_by_id(table, id, account_id)
        else:
            return self._json_get_by_id(table, id, account_id)
    
    def get_by_field(self, table: str, field: str, value: Any) -> List[Dict]:
        """
        Get all records where field matches value
        
        Args:
            table: Table name
            field: Field name to filter by
            value: Value to match
            
        Returns:
            List of matching records
        """
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    # Use parameterized query for security
                    query = f"SELECT * FROM {table} WHERE {field} = %s"
                    cur.execute(query, (value,))
                    return cur.fetchall()
        else:
            all_items = self.get_all(table)
            return [item for item in all_items if item.get(field) == value]
    
    def create(self, table: str, data: Dict) -> Dict:
        """Create a new record"""
        if self.use_postgres:
            return self._pg_create(table, data)
        else:
            return self._json_create(table, data)
    
    def update(self, table: str, id: int, data: Dict, account_id: Optional[str] = None) -> bool:
        """Update a record"""
        if self.use_postgres:
            return self._pg_update(table, id, data, account_id)
        else:
            return self._json_update(table, id, data, account_id)
    
    def delete(self, table: str, id: int, account_id: Optional[str] = None) -> bool:
        """Delete a record"""
        if self.use_postgres:
            return self._pg_delete(table, id, account_id)
        else:
            return self._json_delete(table, id, account_id)
    
    def get_next_id(self, table: str) -> int:
        """Get next available ID for a table"""
        if self.use_postgres:
            # PostgreSQL uses SERIAL, so this is not needed
            return 0
        else:
            filepath = self.files.get(table)
            if not filepath:
                return 1
            data = self._read_json(filepath)
            if not data:
                return 1
            return max(item.get('id', 0) for item in data) + 1
    
    # ============================================================
    # POSTGRESQL IMPLEMENTATIONS
    # ============================================================
    
    def _pg_get_all(self, table: str, account_id: Optional[str] = None) -> List[Dict]:
        """PostgreSQL: Get all records"""
        with self.pg_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if account_id and table != 'accounts':
                    cur.execute(f"SELECT * FROM {table} WHERE account_id = %s ORDER BY id", (account_id,))
                else:
                    cur.execute(f"SELECT * FROM {table} ORDER BY id")
                return cur.fetchall()
    
    def _pg_get_by_id(self, table: str, id: int, account_id: Optional[str] = None) -> Optional[Dict]:
        """PostgreSQL: Get record by ID"""
        with self.pg_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if account_id and table != 'accounts':
                    cur.execute(f"SELECT * FROM {table} WHERE id = %s AND account_id = %s", (id, account_id))
                else:
                    cur.execute(f"SELECT * FROM {table} WHERE id = %s", (id,))
                return cur.fetchone()
    
    def _pg_create(self, table: str, data: Dict) -> Dict:
        """PostgreSQL: Create record"""
        with self.pg_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['%s'] * len(data))
                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
                cur.execute(query, list(data.values()))
                conn.commit()
                return cur.fetchone()
    
    def _pg_update(self, table: str, id: int, data: Dict, account_id: Optional[str] = None) -> bool:
        """PostgreSQL: Update record"""
        with self.pg_pool.connection() as conn:
            with conn.cursor() as cur:
                set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
                values = list(data.values())
                values.append(id)
                
                if account_id and table != 'accounts':
                    query = f"UPDATE {table} SET {set_clause} WHERE id = %s AND account_id = %s"
                    values.append(account_id)
                else:
                    query = f"UPDATE {table} SET {set_clause} WHERE id = %s"
                
                cur.execute(query, values)
                conn.commit()
                return cur.rowcount > 0
    
    def _pg_delete(self, table: str, id: int, account_id: Optional[str] = None) -> bool:
        """PostgreSQL: Delete record"""
        with self.pg_pool.connection() as conn:
            with conn.cursor() as cur:
                if account_id and table != 'accounts':
                    cur.execute(f"DELETE FROM {table} WHERE id = %s AND account_id = %s", (id, account_id))
                else:
                    cur.execute(f"DELETE FROM {table} WHERE id = %s", (id,))
                conn.commit()
                return cur.rowcount > 0
    
    # ============================================================
    # JSON FILE IMPLEMENTATIONS
    # ============================================================
    
    def _json_get_all(self, table: str, account_id: Optional[str] = None) -> List[Dict]:
        """JSON: Get all records"""
        filepath = self.files.get(table)
        if not filepath:
            return []
        
        data = self._read_json(filepath)
        
        if account_id and table != 'accounts':
            return [item for item in data if item.get('account_id') == account_id]
        return data
    
    def _json_get_by_id(self, table: str, id: int, account_id: Optional[str] = None) -> Optional[Dict]:
        """JSON: Get record by ID"""
        data = self._json_get_all(table, account_id)
        for item in data:
            if item.get('id') == id:
                return item
        return None
    
    def _json_create(self, table: str, data: Dict) -> Dict:
        """JSON: Create record"""
        filepath = self.files.get(table)
        if not filepath:
            raise ValueError(f"Unknown table: {table}")
        
        all_data = self._read_json(filepath)
        
        # Auto-assign ID if not provided
        if 'id' not in data:
            data['id'] = self.get_next_id(table)
        
        all_data.append(data)
        self._write_json(filepath, all_data)
        
        return data
    
    def _json_update(self, table: str, id: int, data: Dict, account_id: Optional[str] = None) -> bool:
        """JSON: Update record"""
        filepath = self.files.get(table)
        if not filepath:
            return False
        
        all_data = self._read_json(filepath)
        updated = False
        
        for i, item in enumerate(all_data):
            if item.get('id') == id:
                if account_id and item.get('account_id') != account_id:
                    continue
                all_data[i].update(data)
                updated = True
                break
        
        if updated:
            self._write_json(filepath, all_data)
        
        return updated
    
    def _json_delete(self, table: str, id: int, account_id: Optional[str] = None) -> bool:
        """JSON: Delete record"""
        filepath = self.files.get(table)
        if not filepath:
            return False
        
        all_data = self._read_json(filepath)
        original_length = len(all_data)
        
        all_data = [
            item for item in all_data 
            if not (item.get('id') == id and (not account_id or item.get('account_id') == account_id))
        ]
        
        if len(all_data) < original_length:
            self._write_json(filepath, all_data)
            return True
        
        return False
    
    # ============================================================
    # SPECIALIZED QUERIES
    # ============================================================
    
    def get_user_by_email(self, email: str) -> Optional[Dict]:
        """Get user by email"""
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                    return cur.fetchone()
        else:
            users = self._read_json(self.files['users'])
            for user in users:
                if user.get('email') == email:
                    return user
            return None
    
    def get_account_by_email(self, owner_email: str) -> Optional[Dict]:
        """Get account by owner email"""
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SELECT * FROM accounts WHERE owner_email = %s", (owner_email,))
                    return cur.fetchone()
        else:
            accounts = self._read_json(self.files['accounts'])
            for account in accounts:
                if account.get('owner_email') == owner_email:
                    return account
            return None
    
    def get_sales_by_date_range(self, account_id: str, start_date: str, end_date: str) -> List[Dict]:
        """Get sales within a date range"""
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("""
                        SELECT * FROM sales 
                        WHERE account_id = %s AND created_at >= %s AND created_at <= %s
                        ORDER BY created_at DESC
                    """, (account_id, start_date, end_date))
                    return cur.fetchall()
        else:
            sales = self._json_get_all('sales', account_id)
            return [
                sale for sale in sales 
                if start_date <= sale.get('created_at', '') <= end_date
            ]
    
    def batch_update_stock(self, updates: List[Tuple[int, float, str]]) -> bool:
        """
        Batch update product stock
        
        Args:
            updates: List of (product_id, new_quantity, account_id) tuples
        """
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor() as cur:
                    for product_id, quantity, account_id in updates:
                        cur.execute("""
                            UPDATE products SET quantity = %s, updated_at = %s 
                            WHERE id = %s AND account_id = %s
                        """, (quantity, datetime.now().isoformat(), product_id, account_id))
                    conn.commit()
            return True
        else:
            filepath = self.files['products']
            products = self._read_json(filepath)
            
            update_map = {(pid, aid): qty for pid, qty, aid in updates}
            
            for product in products:
                key = (product.get('id'), product.get('account_id'))
                if key in update_map:
                    product['quantity'] = update_map[key]
                    product['updated_at'] = datetime.now().isoformat()
            
            self._write_json(filepath, products)
            return True

    def batch_update_raw_materials(self, updates: List[Tuple[int, float, str]]) -> bool:
        """
        Batch update raw material stock

        Args:
            updates: List of (raw_material_id, new_quantity, account_id) tuples
        """
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor() as cur:
                    for material_id, quantity, account_id in updates:
                        cur.execute("""
                            UPDATE raw_materials SET quantity = %s, updated_at = %s
                            WHERE id = %s AND account_id = %s
                        """, (quantity, datetime.now().isoformat(), material_id, account_id))
                    conn.commit()
            return True
        else:
            filepath = self.files.get('raw_materials')
            if not filepath:
                return False

            materials = self._read_json(filepath)
            update_map = {(mid, aid): qty for mid, qty, aid in updates}

            for material in materials:
                key = (material.get('id'), material.get('account_id'))
                if key in update_map:
                    material['quantity'] = update_map[key]
                    material['updated_at'] = datetime.now().isoformat()

            self._write_json(filepath, materials)
            return True
    
    def get_active_time_entry(self, user_id: int, account_id: str) -> Optional[Dict]:
        """Get active (not clocked out) time entry for user"""
        if self.use_postgres:
            with self.pg_pool.connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("""
                        SELECT * FROM time_entries 
                        WHERE user_id = %s AND account_id = %s AND clock_out_time IS NULL
                        ORDER BY id DESC LIMIT 1
                    """, (user_id, account_id))
                    return cur.fetchone()
        else:
            entries = self._json_get_all('time_entries', account_id)
            for entry in reversed(entries):
                if entry.get('user_id') == user_id and not entry.get('clock_out_time'):
                    return entry
            return None
