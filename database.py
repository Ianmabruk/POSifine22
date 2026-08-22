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
import time
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from pathlib import Path
import logging
from functools import lru_cache
from contextlib import contextmanager
from urllib.parse import urlparse, urlunparse, parse_qs

# PostgreSQL support (optional)
try:
    import psycopg
    from psycopg.rows import dict_row
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    psycopg = None
    dict_row = None

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
    
    ALLOWED_TABLES = {
        'accounts', 'users', 'products', 'sales', 'expenses', 'time_entries',
        'reminders', 'vendors', 'credit_requests', 'discounts', 'service_fees',
        'sessions', 'activity_logs', 'audit_logs', 'batches', 'stock_movements',
        'business_profiles', 'customers', 'raw_materials', 'recipes',
        'recipe_ingredients', 'inventory_transactions',
        'petroleum_tanks', 'petroleum_sales', 'petroleum_staff',
        'room_bookings', 'appointments', 'prescriptions', 'table_orders',
        'students', 'exam_results', 'assignments', 'school_notices',
        'admin_support_messages', 'messages', 'stock_deductions',
        'role_assignments', 'settings', 'email_templates', 'payments',
        'custom_plan_requests', 'email_logs', 'notification_devices', 'notifications'
    }
    
    ALLOWED_FILTER_FIELDS = {
        'id', 'account_id', 'user_id', 'product_id', 'sale_id', 'expense_id',
        'email', 'role', 'plan', 'status', 'created_at', 'updated_at',
        'refresh_token_hash', 'cashier_id', 'category', 'business_id',
        'name', 'phone', 'is_active', 'is_locked', 'trial_ends_at',
        'subscription_ends_at', 'payment_status', 'provider_reference', 'package_type',
        'inventory_item_id', 'transaction_type', 'reference_type', 'reference_id',
        'reason', 'created_by', 'recipe_id', 'product_type', 'active',
        'device_name', 'platform', 'browser', 'enabled', 'permission_status',
        'type', 'read', 'read_at'
    }
    
    ALLOWED_SORT_FIELDS = {
        'id', 'account_id', 'user_id', 'product_id', 'sale_id', 'expense_id',
        'email', 'role', 'plan', 'status', 'created_at', 'updated_at',
        'name', 'phone', 'is_active', 'is_locked', 'trial_ends_at',
        'subscription_ends_at', 'payment_status', 'provider_reference', 'package_type',
        'category', 'business_id', 'cashier_id', 'created_by', 'recipe_id',
        'product_type', 'active', 'price', 'cost', 'quantity', 'total', 'amount',
        'inventory_item_id', 'transaction_type', 'reference_type', 'reference_id',
        'reason', 'hourly_rate', 'last_login', 'reorder_level', 'max_stock_level',
        'cost_per_unit', 'visible_to_cashier', 'enable_weight_pricing', 'barcode', 'sku'
    }
    
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
        self.pg_pool = None
        self.pg_url = None
        self._pg_local = threading.local()
        
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
        """Initialize PostgreSQL (direct connections, no app-level pool)."""
        try:
            db_url = os.environ.get('DATABASE_URL', '')
            if db_url.startswith('postgres://'):
                db_url = db_url.replace('postgres://', 'postgresql://', 1)

            parsed = urlparse(db_url)
            query_params = parse_qs(parsed.query)
            query_params.pop('channel_binding', None)
            if 'connect_timeout' not in query_params:
                query_params['connect_timeout'] = ['10']
            clean_query = '&'.join(f'{k}={v[0]}' for k, v in query_params.items())
            db_url = urlunparse(parsed._replace(query=clean_query))

            self.pg_url = db_url
            self.pg_pool = None

            self._create_tables()
            logger.info("PostgreSQL initialized (direct connections)")

        except Exception as e:
            logger.error(f"PostgreSQL initialization failed: {e}")
            if os.environ.get('DATABASE_URL'):
                raise RuntimeError(f"PostgreSQL is required in production but failed to initialize: {e}")
            logger.info("Falling back to JSON file storage (development mode)")
            self.use_postgres = False
            self.pg_pool = None
            self._init_json_files()
    
    def _create_tables(self):
        """Create database tables if they don't exist.

        Uses AUTOCOMMIT mode so every DDL statement is its own transaction.
        This prevents a deadlock or error on one statement from aborting the
        entire migration batch (the previous bug where a deadlock on
        ``ALTER TABLE products`` cascaded into "current transaction is
        aborted" for every subsequent migration).
        """
        with self._pg_connection() as conn:
            conn.autocommit = True
            
            # Helper: run a DDL statement, log on failure, never raise.
            # Uses a fresh cursor per statement to avoid "cursor is closed" errors.
            def _safe(sql, desc):
                try:
                    with conn.cursor() as cur:
                        cur.execute(sql)
                    logger.info(f"✅ Migration: {desc}")
                except Exception as e:
                    logger.warning(f"Migration warning for {desc}: {e}")

            # Serialize concurrent migration runs across workers with an
            # advisory lock so two processes don't deadlock on ALTER TABLE.
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_try_advisory_lock(20240814)")
                    got_lock = cur.fetchone()[0]
                if not got_lock:
                    logger.info("Migrations skipped — another worker holds the advisory lock")
                    return
            except Exception as e:
                logger.warning(f"Migration warning for advisory lock: {e}")
                return

                # Accounts table
                _safe("""
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
                        requested_trial BOOLEAN DEFAULT FALSE,
                        business_type TEXT
                    )
                               """, "Created table: accounts")
                
                # Users table
                _safe("""
                    CREATE TABLE IF NOT EXISTS users (
                         id SERIAL PRIMARY KEY,
                         account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                         email TEXT UNIQUE NOT NULL,
                         password_hash TEXT NOT NULL,
                         name TEXT NOT NULL,
                         role TEXT DEFAULT 'cashier',
                         is_active BOOLEAN DEFAULT TRUE,
                         is_locked BOOLEAN DEFAULT FALSE,
                         screen_locked BOOLEAN DEFAULT FALSE,
                         created_at TEXT NOT NULL,
                         created_by INTEGER,
                         last_login TEXT,
                         hourly_rate REAL DEFAULT 0.0,
                         business_type TEXT,
                         business_role TEXT,
                         profile_picture TEXT,
                         device_mode TEXT,
                         permissions JSONB DEFAULT '{}'::jsonb,
                         UNIQUE(account_id, email)
                     )
                                """, "Created table: users")

                # Roles table
                _safe("""
                    CREATE TABLE IF NOT EXISTS roles (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: roles")

                # Sessions table
                _safe("""
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
                               """, "Created table: sessions")

                # Activity logs
                _safe("""
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
                               """, "Created table: activity_logs")

                # Audit logs
                _safe("""
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
                               """, "Created table: audit_logs")

                # Admin support messages
                _safe("""
                    CREATE TABLE IF NOT EXISTS admin_support_messages (
                        id TEXT PRIMARY KEY,
                        account_id TEXT,
                        admin_user_id INTEGER,
                        admin_email TEXT,
                        admin_name TEXT,
                        subject TEXT,
                        message TEXT,
                        category TEXT,
                        priority TEXT,
                        status TEXT,
                        response TEXT,
                        responded_at TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                               """, "Created table: admin_support_messages")

                # Email templates (main admin)
                _safe("""
                    CREATE TABLE IF NOT EXISTS email_templates (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        subject TEXT,
                        text TEXT,
                        html TEXT,
                        created_by TEXT,
                        created_at TEXT,
                        updated_at TEXT
                    )
                               """, "Created table: email_templates")
                
                # Products table
                _safe("""
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
                        visible_to_cashier BOOLEAN DEFAULT TRUE,
                        enable_weight_pricing BOOLEAN DEFAULT FALSE,
                        created_at TEXT NOT NULL,
                        created_by INTEGER,
                        updated_at TEXT
                    )
                               """, "Created table: products")

                # Raw materials table
                _safe("""
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
                               """, "Created table: raw_materials")
                
                # Sales table
                _safe("""
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
                         notes TEXT,
                         payment_status TEXT DEFAULT 'paid'
                     )
                                 """, "Created table: sales")

                 # Payments table
                _safe("""
                    CREATE TABLE IF NOT EXISTS payments (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        sale_id INTEGER REFERENCES sales(id) ON DELETE SET NULL,
                        cashier_id INTEGER NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT DEFAULT 'KES',
                        customer_phone TEXT,
                        provider TEXT DEFAULT 'manual',
                        provider_reference TEXT,
                        account_ref TEXT,
                        status TEXT DEFAULT 'pending',
                        failure_reason TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                               """, "Created table: payments")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_account ON payments(account_id)", "Created index: idx_payments_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments(sale_id)", "Created index: idx_payments_sale")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_provider_ref ON payments(provider_reference)", "Created index: idx_payments_provider_ref")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)", "Created index: idx_payments_status")

                 # Stock deductions table (audit trail for inventory reductions)
                _safe("""
                    CREATE TABLE IF NOT EXISTS stock_deductions (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                        product_name TEXT NOT NULL,
                        quantity_before REAL NOT NULL,
                        quantity_deducted REAL NOT NULL,
                        quantity_after REAL NOT NULL,
                        unit TEXT DEFAULT 'pcs',
                        payment_method TEXT DEFAULT 'cash',
                        cashier_id INTEGER,
                        cashier_name TEXT,
                        deduction_reason TEXT,
                        sale_id INTEGER REFERENCES sales(id) ON DELETE SET NULL,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: stock_deductions")

                # Petroleum tanks
                _safe("""
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
                               """, "Created table: petroleum_tanks")

                # Petroleum staff
                _safe("""
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
                               """, "Created table: petroleum_staff")

                # Petroleum sales
                _safe("""
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
                               """, "Created table: petroleum_sales")
                
                # Time entries table
                _safe("""
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
                               """, "Created table: time_entries")
                
                # Reminders table
                _safe("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        title TEXT NOT NULL,
                        message TEXT NOT NULL,
                        priority TEXT DEFAULT 'normal',
                        status TEXT DEFAULT 'pending',
                        created_by INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        expires_at TEXT,
                        target_users JSONB DEFAULT '[]',
                        admin_note TEXT,
                        cashier_note TEXT,
                        admin_signature TEXT,
                        cashier_signature TEXT,
                        admin_signed_at TEXT,
                        cashier_signed_at TEXT,
                        seen_by JSONB DEFAULT '[]'
                    )
                               """, "Created table: reminders")
                
                # Vendors table
                _safe("""
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
                               """, "Created table: vendors")
                
                # Credit requests table
                _safe("""
                    CREATE TABLE IF NOT EXISTS credit_requests (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        cashier_id INTEGER NOT NULL,
                        cashier_name TEXT NOT NULL,
                        customer_name TEXT,
                        amount REAL NOT NULL,
                        reason TEXT NOT NULL,
                        notes TEXT,
                        status TEXT DEFAULT 'pending',
                        reviewed_by INTEGER,
                        reviewed_at TEXT,
                        admin_notes TEXT,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: credit_requests")
                
                # Expenses table
                _safe("""
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
                               """, "Created table: expenses")
                
                # Discounts table
                _safe("""
                    CREATE TABLE IF NOT EXISTS discounts (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL,
                        discount_type TEXT DEFAULT 'percentage',
                        discount_value REAL DEFAULT 0.0,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: discounts")
                
                # Service fees table
                _safe("""
                    CREATE TABLE IF NOT EXISTS service_fees (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        amount REAL NOT NULL,
                        fee_type TEXT DEFAULT 'fixed',
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: service_fees")
                
                # Stock movements table (audit trail)
                _safe("""
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
                               """, "Created table: stock_movements")
                
                # Batches table (for stock batch management)
                _safe("""
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
                               """, "Created table: batches")
                
                # Safe migration: rename legacy product_id to productId in batches if needed
                try:
                    _safe("""
                        DO $$
                        BEGIN
                            IF EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = 'batches' AND column_name = 'product_id'
                            ) AND NOT EXISTS (
                                SELECT 1 FROM information_schema.columns 
                                WHERE table_name = 'batches' AND column_name = 'productId'
                            ) THEN
                                ALTER TABLE batches RENAME COLUMN product_id TO productId;
                            END IF;
                        END $$;
                                       """, "Ensured batches table uses productId column")
                    logger.info("✅ Migration: Ensured batches table uses productId column")
                except Exception as e:
                    logger.warning(f"Migration warning for batches.productId: {e}")
                
                # Business profiles table (Pro Plan)
                _safe("""
                    CREATE TABLE IF NOT EXISTS business_profiles (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE UNIQUE,
                        business_type TEXT NOT NULL,
                        plan TEXT DEFAULT 'starter',
                        created_at TEXT NOT NULL,
                        settings JSONB DEFAULT '{}'
                    )
                               """, "Created table: business_profiles")
                
                # Role assignments table (Pro Plan - business-specific roles)
                _safe("""
                    CREATE TABLE IF NOT EXISTS role_assignments (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        business_type TEXT NOT NULL,
                        business_role TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        UNIQUE(user_id, business_type)
                    )
                               """, "Created table: role_assignments")
                
                # Appointments table (Clinic/Hospital)
                _safe("""
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
                               """, "Created table: appointments")
                
                # Prescriptions table (Clinic/Hospital)
                _safe("""
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
                               """, "Created table: prescriptions")
                
                # Tables/Orders table (Bar/Restaurant)
                _safe("""
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
                               """, "Created table: table_orders")
                
                # Room bookings table (Hotel)
                _safe("""
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
                               """, "Created table: room_bookings")
                
                # Recipes table
                _safe("""
                    CREATE TABLE IF NOT EXISTS recipes (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        active BOOLEAN DEFAULT TRUE,
                        created_at TEXT NOT NULL,
                        updated_at TEXT
                    )
                               """, "Created table: recipes")
                
                # Recipe ingredients table
                _safe("""
                    CREATE TABLE IF NOT EXISTS recipe_ingredients (
                        id SERIAL PRIMARY KEY,
                        recipe_id INTEGER NOT NULL REFERENCES recipes(id) ON DELETE CASCADE,
                        inventory_item_id INTEGER NOT NULL,
                        quantity REAL NOT NULL,
                        unit TEXT DEFAULT 'pcs',
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: recipe_ingredients")
                
                # Inventory transactions table
                _safe("""
                     CREATE TABLE IF NOT EXISTS inventory_transactions (
                         id SERIAL PRIMARY KEY,
                         account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                         inventory_item_id INTEGER NOT NULL,
                         transaction_type TEXT NOT NULL,
                         quantity REAL NOT NULL,
                         unit TEXT DEFAULT 'pcs',
                         before_quantity REAL NOT NULL,
                         after_quantity REAL NOT NULL,
                         reference_type TEXT,
                         reference_id INTEGER,
                         reason TEXT,
                         created_by INTEGER,
                         created_at TEXT NOT NULL
                     )
                               """, "Created table: inventory_transactions")

                # Custom plan requests table
                _safe("""
                    CREATE TABLE IF NOT EXISTS custom_plan_requests (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        business_name TEXT NOT NULL,
                        contact_name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        phone TEXT,
                        industry TEXT,
                        expected_users INTEGER,
                        expected_branches INTEGER,
                        features_needed TEXT,
                        additional_notes TEXT,
                        status TEXT DEFAULT 'pending',
                        admin_notes TEXT,
                        reviewed_by INTEGER,
                        reviewed_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                               """, "Created table: custom_plan_requests")

                # Email logs table
                _safe("""
                    CREATE TABLE IF NOT EXISTS email_logs (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        recipient TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        template_type TEXT,
                        status TEXT DEFAULT 'pending',
                        failure_reason TEXT,
                        sent_at TEXT,
                        created_by INTEGER,
                        created_at TEXT NOT NULL
                    )
                                """, "Created table: email_logs")

                 # Push notification devices table
                _safe("""
                    CREATE TABLE IF NOT EXISTS notification_devices (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        account_id TEXT NOT NULL,
                        device_name TEXT DEFAULT 'Unknown Device',
                        platform TEXT DEFAULT 'unknown',
                        browser TEXT DEFAULT 'unknown',
                        push_subscription JSONB NOT NULL,
                        permission_status TEXT DEFAULT 'granted',
                        enabled BOOLEAN DEFAULT TRUE,
                        last_seen_at TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                               """, "Created table: notification_devices")

                # Notifications history table
                _safe("""
                    CREATE TABLE IF NOT EXISTS notifications (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL,
                        account_id TEXT NOT NULL,
                        type TEXT DEFAULT 'info',
                        title TEXT NOT NULL,
                        body TEXT NOT NULL,
                        data JSONB DEFAULT '{}',
                        read BOOLEAN DEFAULT FALSE,
                        read_at TEXT,
                        created_at TEXT NOT NULL
                    )
                               """, "Created table: notifications")

                 # Create indexes for performance
                _safe("CREATE INDEX IF NOT EXISTS idx_users_account ON users(account_id)", "Created index: idx_users_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)", "Created index: idx_users_email")
                _safe("CREATE INDEX IF NOT EXISTS idx_sessions_account ON sessions(account_id)", "Created index: idx_sessions_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)", "Created index: idx_sessions_user")
                _safe("CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token_hash ON sessions(refresh_token_hash)", "Created index: idx_sessions_refresh_token_hash")
                _safe("CREATE INDEX IF NOT EXISTS idx_activity_account ON activity_logs(account_id)", "Created index: idx_activity_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_audit_account ON audit_logs(account_id)", "Created index: idx_audit_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_products_account ON products(account_id)", "Created index: idx_products_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_products_category ON products(category)", "Created index: idx_products_category")
                _safe("CREATE INDEX IF NOT EXISTS idx_raw_materials_account ON raw_materials(account_id)", "Created index: idx_raw_materials_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_sales_account ON sales(account_id)", "Created index: idx_sales_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_sales_created ON sales(created_at)", "Created index: idx_sales_created")
                _safe("CREATE INDEX IF NOT EXISTS idx_sales_cashier ON sales(cashier_id)", "Created index: idx_sales_cashier")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_tanks_account ON petroleum_tanks(account_id)", "Created index: idx_petroleum_tanks_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_tanks_fuel ON petroleum_tanks(fuel_type)", "Created index: idx_petroleum_tanks_fuel")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_account ON petroleum_sales(account_id)", "Created index: idx_petroleum_sales_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_fuel ON petroleum_sales(fuel_type)", "Created index: idx_petroleum_sales_fuel")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_sales_created ON petroleum_sales(created_at)", "Created index: idx_petroleum_sales_created")
                _safe("CREATE INDEX IF NOT EXISTS idx_petroleum_staff_account ON petroleum_staff(account_id)", "Created index: idx_petroleum_staff_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_time_entries_account ON time_entries(account_id)", "Created index: idx_time_entries_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_time_entries_user ON time_entries(user_id)", "Created index: idx_time_entries_user")
                _safe("CREATE INDEX IF NOT EXISTS idx_time_entries_date ON time_entries(date)", "Created index: idx_time_entries_date")
                _safe("CREATE INDEX IF NOT EXISTS idx_batches_account ON batches(account_id)", "Created index: idx_batches_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_batches_product ON batches(productId)", "Created index: idx_batches_product")
                _safe("CREATE INDEX IF NOT EXISTS idx_business_profiles_account ON business_profiles(account_id)", "Created index: idx_business_profiles_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_role_assignments_user ON role_assignments(user_id)", "Created index: idx_role_assignments_user")
                _safe("CREATE INDEX IF NOT EXISTS idx_appointments_account ON appointments(account_id)", "Created index: idx_appointments_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id)", "Created index: idx_appointments_doctor")
                _safe("CREATE INDEX IF NOT EXISTS idx_prescriptions_account ON prescriptions(account_id)", "Created index: idx_prescriptions_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_table_orders_account ON table_orders(account_id)", "Created index: idx_table_orders_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_room_bookings_account ON room_bookings(account_id)", "Created index: idx_room_bookings_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_expenses_account ON expenses(account_id)", "Created index: idx_expenses_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_expenses_created ON expenses(created_at)", "Created index: idx_expenses_created")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_movements_product ON stock_movements(product_id)", "Created index: idx_stock_movements_product")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_movements_account ON stock_movements(account_id)", "Created index: idx_stock_movements_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_deductions_account ON stock_deductions(account_id)", "Created index: idx_stock_deductions_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_deductions_product ON stock_deductions(product_id)", "Created index: idx_stock_deductions_product")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_deductions_created ON stock_deductions(created_at)", "Created index: idx_stock_deductions_created")
                _safe("CREATE INDEX IF NOT EXISTS idx_stock_deductions_cashier ON stock_deductions(cashier_id)", "Created index: idx_stock_deductions_cashier")
                _safe("CREATE INDEX IF NOT EXISTS idx_recipes_account ON recipes(account_id)", "Created index: idx_recipes_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_recipes_product ON recipes(product_id)", "Created index: idx_recipes_product")
                _safe("CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_recipe ON recipe_ingredients(recipe_id)", "Created index: idx_recipe_ingredients_recipe")
                _safe("CREATE INDEX IF NOT EXISTS idx_recipe_ingredients_item ON recipe_ingredients(inventory_item_id)", "Created index: idx_recipe_ingredients_item")
                _safe("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_account ON inventory_transactions(account_id)", "Created index: idx_inventory_transactions_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_item ON inventory_transactions(inventory_item_id)", "Created index: idx_inventory_transactions_item")
                _safe("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_type ON inventory_transactions(transaction_type)", "Created index: idx_inventory_transactions_type")
                _safe("CREATE INDEX IF NOT EXISTS idx_inventory_transactions_created ON inventory_transactions(created_at)", "Created index: idx_inventory_transactions_created")
                _safe("CREATE INDEX IF NOT EXISTS idx_custom_plan_requests_account ON custom_plan_requests(account_id)", "Created index: idx_custom_plan_requests_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_custom_plan_requests_status ON custom_plan_requests(status)", "Created index: idx_custom_plan_requests_status")
                _safe("CREATE INDEX IF NOT EXISTS idx_email_logs_account ON email_logs(account_id)", "Created index: idx_email_logs_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_email_logs_status ON email_logs(status)", "Created index: idx_email_logs_status")
                
                # ============================================================
                # MIGRATIONS: Add new columns to existing tables
                # ============================================================
                
                # Add business_type and business_role columns to users table if they don't exist
                _safe("""
                    ALTER TABLE users 
                    ADD COLUMN IF NOT EXISTS business_type TEXT,
                    ADD COLUMN IF NOT EXISTS business_role TEXT,
                    ADD COLUMN IF NOT EXISTS profile_picture TEXT,
                    ADD COLUMN IF NOT EXISTS permissions JSONB DEFAULT '{}'::jsonb,
                    ADD COLUMN IF NOT EXISTS updated_at TEXT
                """, "Added business_type and business_role columns to users table")

                 # Ensure products table has newer fields used by API/controllers.
                _safe("""
                    ALTER TABLE products
                    ADD COLUMN IF NOT EXISTS image TEXT,
                    ADD COLUMN IF NOT EXISTS barcode TEXT,
                    ADD COLUMN IF NOT EXISTS sku TEXT,
                    ADD COLUMN IF NOT EXISTS reorder_level REAL DEFAULT 0.0,
                    ADD COLUMN IF NOT EXISTS max_stock_level REAL DEFAULT 0.0,
                    ADD COLUMN IF NOT EXISTS cost_per_unit REAL DEFAULT 0.0,
                    ADD COLUMN IF NOT EXISTS enable_weight_pricing BOOLEAN DEFAULT FALSE,
                    ADD COLUMN IF NOT EXISTS visible_to_cashier BOOLEAN DEFAULT TRUE,
                    ADD COLUMN IF NOT EXISTS updated_at TEXT,
                    ADD COLUMN IF NOT EXISTS package_size REAL DEFAULT 1.0
                """, "Ensured extended products columns exist")

                # Fix products sequence if it is out of sync.
                try:
                    with self._pg_connection() as conn:
                        with conn.cursor() as cur:
                            cur.execute("SELECT setval(pg_get_serial_sequence('products', 'id'), COALESCE((SELECT MAX(id) FROM products) + 1, 1), false)")
                            conn.commit()
                            logger.info("✅ Products sequence fixed")
                except Exception as exc:
                    logger.warning(f"Failed to fix products sequence: {exc}")

                # Ensure expenses table has linking/source fields used by auto-COGS code.
                _safe("""
                    ALTER TABLE expenses
                    ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual',
                    ADD COLUMN IF NOT EXISTS linked_product_id INTEGER,
                    ADD COLUMN IF NOT EXISTS linked_raw_material_id INTEGER,
                    ADD COLUMN IF NOT EXISTS linked_sale_id INTEGER,
                    ADD COLUMN IF NOT EXISTS description TEXT,
                    ADD COLUMN IF NOT EXISTS created_by INTEGER
                """, "Ensured extended expenses columns exist")
                
                # Migration: Add missing columns to credit_requests
                _safe("""
                ALTER TABLE credit_requests
                    ADD COLUMN IF NOT EXISTS customer_name TEXT,
                    ADD COLUMN IF NOT EXISTS notes TEXT
                """, "Added customer_name and notes columns to credit_requests")

                # Migration: Add missing business_type column to accounts
                _safe("""
                    ALTER TABLE accounts
                        ADD COLUMN IF NOT EXISTS business_type TEXT
                """, "Ensured accounts table has business_type column")
                
                # Migration: Add payment_required flag to accounts
                _safe("""
                    ALTER TABLE accounts
                        ADD COLUMN IF NOT EXISTS payment_required BOOLEAN DEFAULT FALSE
                """, "Ensured accounts table has payment_required column")
                
                # Migration: Add payment_status to sales
                _safe("""
                    ALTER TABLE sales
                        ADD COLUMN IF NOT EXISTS payment_status TEXT DEFAULT 'paid'
                """, "Ensured sales table has payment_status column")

                # Migration: Create payments table if it does not exist
                _safe("""
                    CREATE TABLE IF NOT EXISTS payments (
                        id SERIAL PRIMARY KEY,
                        account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                        sale_id INTEGER REFERENCES sales(id) ON DELETE SET NULL,
                        cashier_id INTEGER NOT NULL,
                        amount REAL NOT NULL,
                        currency TEXT DEFAULT 'KES',
                        customer_phone TEXT,
                        provider TEXT DEFAULT 'manual',
                        provider_reference TEXT,
                        account_ref TEXT,
                        status TEXT DEFAULT 'pending',
                        failure_reason TEXT,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                """, "Created table: payments")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_account ON payments(account_id)", "Created index: idx_payments_account")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_sale ON payments(sale_id)", "Created index: idx_payments_sale")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_provider_ref ON payments(provider_reference)", "Created index: idx_payments_provider_ref")
                _safe("CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)", "Created index: idx_payments_status")

                logger.info("✅ All migrations completed successfully")

                # Release advisory lock after migrations complete
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT pg_advisory_unlock(20240814)")
                except Exception as unlock_err:
                    logger.warning(f"Failed to release advisory lock: {unlock_err}")
    
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
            'petroleum_staff': os.path.join(self.data_dir, 'petroleum_staff.json'),
            'settings': os.path.join(self.data_dir, 'settings.json'),
            'admin_support_messages': os.path.join(self.data_dir, 'admin_support_messages.json'),
            'email_templates': os.path.join(self.data_dir, 'email_templates.json'),
            'students': os.path.join(self.data_dir, 'students.json'),
            'fee_payments': os.path.join(self.data_dir, 'fee_payments.json'),
            'exam_results': os.path.join(self.data_dir, 'exam_results.json'),
            'assignments': os.path.join(self.data_dir, 'assignments.json'),
            'school_notices': os.path.join(self.data_dir, 'school_notices.json'),
            'payments': os.path.join(self.data_dir, 'payments.json'),
            'recipes': os.path.join(self.data_dir, 'recipes.json'),
            'recipe_ingredients': os.path.join(self.data_dir, 'recipe_ingredients.json'),
            'inventory_transactions': os.path.join(self.data_dir, 'inventory_transactions.json'),
            'customers': os.path.join(self.data_dir, 'customers.json'),
            'custom_plan_requests': os.path.join(self.data_dir, 'custom_plan_requests.json'),
             'email_logs': os.path.join(self.data_dir, 'email_logs.json'),
             'notification_devices': os.path.join(self.data_dir, 'notification_devices.json'),
             'notifications': os.path.join(self.data_dir, 'notifications.json'),
             'messages': os.path.join(self.data_dir, 'messages.json'),
             'stock_deductions': os.path.join(self.data_dir, 'stock_deductions.json')
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
            temp_filepath = f"{filepath}.tmp"
            with open(temp_filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, separators=(',', ':'), ensure_ascii=True)
            os.replace(temp_filepath, filepath)
    
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
        if table not in self.ALLOWED_TABLES:
            logger.warning(f"Blocked query on disallowed table: {table}")
            return []
        if field not in self.ALLOWED_FILTER_FIELDS:
            logger.warning(f"Blocked query on disallowed field: {field}")
            return []
        if self.use_postgres:
            with self._pg_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    query = f"SELECT * FROM {table} WHERE {field} = %s"
                    cur.execute(query, (value,))
                    return cur.fetchall()
        else:
                filepath = self.files.get(table)
                if not filepath:
                    return []
                all_items = self._read_json(filepath)
                return [item for item in all_items if item.get(field) == value]
    
    def get_paginated(self, table: str, account_id: Optional[str] = None, page: int = 1, limit: int = 20, search: Optional[str] = None, sort: Optional[str] = None, search_fields: Optional[list] = None) -> Dict[str, Any]:
        """Get paginated records from a table with optional search and sort.
        
        Args:
            table: Table name
            account_id: Optional account_id filter
            page: Page number (1-indexed)
            limit: Items per page
            search: Optional search string
            sort: Optional sort field, prefix with - for descending
            search_fields: Optional list of fields to search in (defaults to name, email)
            
        Returns:
            Dict with items, total, page, limit, total_pages
        """
        if table not in self.ALLOWED_TABLES:
            logger.warning(f"Blocked query on disallowed table: {table}")
            return {"items": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}
        
        if self.use_postgres:
            return self._pg_get_paginated(table, account_id, page, limit, search, sort, search_fields)
        else:
            return self._json_get_paginated(table, account_id, page, limit, search, sort, search_fields)
    
    def _pg_get_paginated(self, table: str, account_id: Optional[str], page: int, limit: int, search: Optional[str], sort: Optional[str], search_fields: Optional[list]) -> Dict[str, Any]:
        """PostgreSQL paginated query"""
        with self._pg_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Build WHERE clause
                where_clauses = []
                params = []
                
                if account_id and table != 'accounts':
                    where_clauses.append("account_id = %s")
                    params.append(account_id)
                
                if search and search_fields:
                    search_conditions = []
                    for field in search_fields:
                        search_conditions.append(f"{field} ILIKE %s")
                        params.append(f"%{search}%")
                    where_clauses.append(f"({' OR '.join(search_conditions)})")
                
                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
                
                # Count total
                count_query = f"SELECT COUNT(*) as total FROM {table} {where_sql}"
                cur.execute(count_query, params)
                total = cur.fetchone()['total']
                
                # Build ORDER BY
                order_sql = ""
                if sort:
                    reverse = sort.startswith("-")
                    sort_field = sort[1:] if reverse else sort
                    if sort_field not in self.ALLOWED_SORT_FIELDS:
                        sort_field = "id"
                    order_sql = f"ORDER BY {sort_field} {'DESC' if reverse else 'ASC'}"
                else:
                    order_sql = "ORDER BY id DESC"
                
                # Paginated query
                offset = (page - 1) * limit
                query = f"SELECT * FROM {table} {where_sql} {order_sql} LIMIT %s OFFSET %s"
                params.extend([limit, offset])
                cur.execute(query, params)
                items = cur.fetchall()
                
                total_pages = max(1, (total + limit - 1) // limit)
                return {
                    "items": items,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "total_pages": total_pages,
                }
    
    def _json_get_paginated(self, table: str, account_id: Optional[str], page: int, limit: int, search: Optional[str], sort: Optional[str], search_fields: Optional[list]) -> Dict[str, Any]:
        """JSON file paginated query (fallback)"""
        filepath = self.files.get(table)
        if not filepath:
            return {"items": [], "total": 0, "page": page, "limit": limit, "total_pages": 0}
        
        all_items = self._read_json(filepath)
        
        # Filter by account_id
        if account_id and table != 'accounts':
            all_items = [item for item in all_items if item.get('account_id') == account_id]
        
        # Search
        if search and search_fields:
            search_lower = search.lower()
            filtered = []
            for item in all_items:
                for field in search_fields:
                    if str(item.get(field, '')).lower().find(search_lower) != -1:
                        filtered.append(item)
                        break
            all_items = filtered
        
        total = len(all_items)
        
        # Sort
        if sort:
            reverse = sort.startswith("-")
            sort_field = sort[1:] if reverse else sort
            all_items.sort(key=lambda x: str(x.get(sort_field) or ''), reverse=reverse)
        
        # Paginate
        offset = (page - 1) * limit
        items = all_items[offset:offset + limit]
        total_pages = max(1, (total + limit - 1) // limit)
        
        return {
            "items": items,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": total_pages,
        }
    
    def find(self, table: str, filters: Dict[str, Any], account_id: Optional[str] = None) -> List[Dict]:
        """Find records matching ALL filter conditions.
        
        Args:
            table: Table name
            filters: Dict of field->value pairs; ALL must match
            account_id: Optional account_id override for security (if not in filters)
        
        Returns:
            List of matching records
        """
        if table not in self.ALLOWED_TABLES:
            logger.warning(f"Blocked query on disallowed table: {table}")
            return []
        for field in filters.keys():
            if field not in self.ALLOWED_FILTER_FIELDS:
                logger.warning(f"Blocked query on disallowed field: {field}")
                return []
        # Ensure account_id is always part of filtering for tenant isolation
        effective_account_id = account_id or filters.get('account_id') or filters.get('accountId')

        if self.use_postgres:
            with self._pg_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    conditions = []
                    values = []
                    for field, value in filters.items():
                        conditions.append(f"{field} = %s")
                        values.append(value)
                    if not conditions:
                        return []
                    query = f"SELECT * FROM {table} WHERE " + " AND ".join(conditions)
                    cur.execute(query, values)
                    return cur.fetchall()
        else:
            filepath = self.files.get(table)
            if not filepath:
                return []
            all_items = self._read_json(filepath)
            results = []
            for item in all_items:
                if all(item.get(k) == v for k, v in filters.items()):
                    results.append(item)
            return results

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
    
    @contextmanager
    def _pg_connection(self):
        """Get a PostgreSQL connection with per-thread reuse."""
        conn = getattr(self._pg_local, 'conn', None)
        if conn is None or getattr(conn, 'closed', True):
            conn = psycopg.connect(self.pg_url)
            self._pg_local.conn = conn
        else:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = psycopg.connect(self.pg_url)
                self._pg_local.conn = conn
        try:
            yield conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            self._pg_local.conn = None
            raise
    
    def _pg_get_all(self, table: str, account_id: Optional[str] = None) -> List[Dict]:
        """PostgreSQL: Get all records"""
        with self._pg_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if account_id and table != 'accounts':
                    cur.execute(f"SELECT * FROM {table} WHERE account_id = %s ORDER BY id", (account_id,))
                else:
                    cur.execute(f"SELECT * FROM {table} ORDER BY id")
                return cur.fetchall()
    
    def _pg_get_by_id(self, table: str, id: int, account_id: Optional[str] = None) -> Optional[Dict]:
        """PostgreSQL: Get record by ID"""
        with self._pg_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if account_id and table != 'accounts':
                    cur.execute(f"SELECT * FROM {table} WHERE id = %s AND account_id = %s", (id, account_id))
                else:
                    cur.execute(f"SELECT * FROM {table} WHERE id = %s", (id,))
                return cur.fetchone()
    
    def _pg_create(self, table: str, data: Dict) -> Dict:
        """PostgreSQL: Create record"""
        with self._pg_connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                columns = ', '.join(data.keys())
                placeholders = ', '.join(['%s'] * len(data))
                values = []
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        logger.debug("Serializing dict/list for %s.%s: %s", table, k, type(v).__name__)
                        values.append(json.dumps(v))
                    else:
                        values.append(v)
                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) RETURNING *"
                cur.execute(query, values)
                conn.commit()
                return cur.fetchone()
    
    def _pg_update(self, table: str, id: int, data: Dict, account_id: Optional[str] = None) -> bool:
        """PostgreSQL: Update record"""
        with self._pg_connection() as conn:
            with conn.cursor() as cur:
                set_clause = ', '.join([f"{k} = %s" for k in data.keys()])
                values = []
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        logger.debug("Serializing dict/list for UPDATE %s.%s: %s", table, k, type(v).__name__)
                        values.append(json.dumps(v))
                    else:
                        values.append(v)
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
        with self._pg_connection() as conn:
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
            data['id'] = (max((item.get('id', 0) for item in all_data), default=0) + 1)
        
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
            with self._pg_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute("SELECT * FROM users WHERE email = %s", (email,))
                    return cur.fetchone()
        else:
            normalized_email = (email or '').strip().lower()
            users = self._read_json(self.files['users'])
            for user in users:
                if (user.get('email') or '').strip().lower() == normalized_email:
                    return user
            return None
    
    def get_account_by_email(self, owner_email: str) -> Optional[Dict]:
        """Get account by owner email"""
        if self.use_postgres:
            with self._pg_connection() as conn:
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
            with self._pg_connection() as conn:
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
            with self._pg_connection() as conn:
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
            with self._pg_connection() as conn:
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
            with self._pg_connection() as conn:
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
    
    def execute_sql(self, sql: str) -> Optional[List[Dict]]:
        """Execute raw SQL against the PostgreSQL database.
        
        Falls back to no-op if not using PostgreSQL.
        Used by DatabaseOptimizer for index creation and raw queries.
        """
        if not self.use_postgres or not self.pg_pool:
            return None
        try:
            with self._pg_connection() as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(sql)
                    conn.commit()
                    if cur.description:
                        return cur.fetchall()
                    return None
        except Exception as e:
            logger.error(f"execute_sql failed: {e}")
            return None
