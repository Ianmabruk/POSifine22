#!/usr/bin/env python3
"""
Migration helper: import JSON data from backend/data/*.json into Postgres.

Usage:
    DATABASE_URL=... python migrate_json_to_pg.py

Features:
    - Upserts `companies`, `users`, `products` and synchronizes `composite_components`.
    - Also migrates `batches.json`, `sales.json`, and `expenses.json` when present.
    - Before making changes, creates a backup of existing table contents under
        `backend/data/migration_backups/<timestamp>/` for safe rollback.
    - Supports `--rollback <timestamp>` to restore tables from a backup.

Notes:
    - Requires the same DB schema as `database.init_database()` or will create lightweight helper
        tables for `batches`, `sales`, and `expenses` if they do not exist.
    - Script performs upserts (INSERT ... ON CONFLICT DO UPDATE) for basic idempotency.
    - Composite component rows are synchronized by deleting existing component rows for a composite and reinserting from the JSON recipe.
"""
import os
import json
import argparse
from pathlib import Path
from datetime import datetime

import database


DATA_DIR = Path(__file__).parent / 'data'
BACKUPS_DIR = DATA_DIR / 'migration_backups'


def load_json(filename):
    path = DATA_DIR / filename
    if not path.exists():
        return []
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return []


def to_ts(s):
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def migrate():
    parser = argparse.ArgumentParser(description='Migrate JSON data into Postgres with backup/rollback support')
    parser.add_argument('--rollback', help='Timestamp folder name under migration_backups to restore', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Validate JSON and show planned operations without writing to DB')
    args = parser.parse_args()

    # Dry-run: validate JSON inputs and show a summary without touching DB
    if args.dry_run:
        print('Dry-run: validating JSON files in', str(DATA_DIR))
        companies = load_json('companies.json')
        users = load_json('users.json')
        products = load_json('products.json')
        batches = load_json('batches.json')
        sales = load_json('sales.json')
        expenses = load_json('expenses.json')

        def sample_name(arr):
            return (list(arr[0].keys())[:6] if arr else [])

        print('Summary:')
        print(' - companies:', len(companies), 'sample keys:', sample_name(companies))
        print(' - users:', len(users), 'sample keys:', sample_name(users))
        print(' - products:', len(products), 'sample keys:', sample_name(products))
        print(' - batches:', len(batches), 'sample keys:', sample_name(batches))
        print(' - sales:', len(sales), 'sample keys:', sample_name(sales))
        print(' - expenses:', len(expenses), 'sample keys:', sample_name(expenses))

        # Basic validation examples
        errors = []
        for i, p in enumerate(products[:20]):
            if 'id' not in p:
                errors.append(f'product[{i}] missing id')
            if 'price' in p:
                try:
                    float(p.get('price') or 0)
                except Exception:
                    errors.append(f'product[{i}] invalid price')

        if errors:
            print('Validation errors (first 20 products checked):')
            for e in errors[:20]:
                print('  -', e)
            print('Dry-run failed with validation errors')
            return 4

        print('Dry-run OK — no obvious errors found. No DB changes performed.')
        return 0

    if not os.environ.get('DATABASE_URL'):
        print('DATABASE_URL is not set. Aborting.')
        return 1

    conn = database.get_db_connection()
    if not conn:
        print('Failed to connect to DB')
        return 2

    # Tables to include in backup/restore and migration
    tables = ['companies', 'users', 'products', 'composite_components', 'batches', 'sales', 'expenses']

    cur = conn.cursor()

    def ensure_aux_tables():
        # Create lightweight helper tables if missing to accept imported data
        cur.execute("""
        CREATE TABLE IF NOT EXISTS batches (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            product_id TEXT,
            quantity NUMERIC,
            cost NUMERIC,
            batch_number TEXT,
            created_at TIMESTAMP,
            expiry_date TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            cashier_id TEXT,
            cashier_name TEXT,
            items JSONB,
            total NUMERIC,
            created_at TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id TEXT PRIMARY KEY,
            company_id TEXT,
            description TEXT,
            amount NUMERIC,
            category TEXT,
            created_at TIMESTAMP
        )
        """)

    def backup_tables(ts_folder):
        ts_path = BACKUPS_DIR / ts_folder
        ts_path.mkdir(parents=True, exist_ok=True)
        for t in tables:
            try:
                cur.execute(f"SELECT row_to_json(t) FROM (SELECT * FROM {t}) t")
                rows = [r[0] for r in cur.fetchall()]
            except Exception:
                rows = []
            with open(ts_path / f"{t}.json", 'w', encoding='utf-8') as f:
                json.dump(rows, f, default=str)
        return ts_path

    def restore_from_backup(ts_folder):
        ts_path = BACKUPS_DIR / ts_folder
        if not ts_path.exists():
            print('Backup folder not found:', ts_path)
            return 4
        for t in tables:
            p = ts_path / f"{t}.json"
            if not p.exists():
                continue
            with open(p, 'r', encoding='utf-8') as f:
                rows = json.load(f)
            # restore: delete existing then insert each row
            cur.execute(f"DELETE FROM {t}")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cols = list(row.keys())
                vals = [row[c] for c in cols]
                placeholders = ','.join(['%s'] * len(cols))
                colnames = ','.join(cols)
                sql = f"INSERT INTO {t} ({colnames}) VALUES ({placeholders})"
                cur.execute(sql, vals)
        conn.commit()
        return 0

    try:
        if args.rollback:
            print('Restoring backup from', args.rollback)
            code = restore_from_backup(args.rollback)
            print('Rollback complete')
            return code

        # Normal migration flow
        # 1) Ensure helper tables exist
        ensure_aux_tables()

        # 2) Create a timestamped backup
        ts = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
        backup_path = backup_tables(ts)
        print('Created backup at', str(backup_path))

        # load source JSON
        companies = load_json('companies.json')
        users = load_json('users.json')
        products = load_json('products.json')
        batches = load_json('batches.json')
        sales = load_json('sales.json')
        expenses = load_json('expenses.json')

        # Upsert companies
        for c in companies:
            cid = c.get('id')
            name = c.get('name') or c.get('companyName') or 'Imported Company'
            plan = c.get('plan') or c.get('pricing') or 'basic'
            created_at = c.get('createdAt') or c.get('created_at') or None
            cur.execute(
                """
                INSERT INTO companies (id, name, plan, created_at)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, plan = EXCLUDED.plan
                RETURNING id
                """,
                (cid, name, plan, created_at)
            )

        # Upsert users
        for u in users:
            uid = u.get('id')
            email = u.get('email')
            password = u.get('password') or 'migrated'
            name = u.get('name') or u.get('fullName') or email
            role = u.get('role') or 'cashier'
            plan = u.get('plan') or 'trial'
            company_id = u.get('company_id') or u.get('companyId') or (companies[0].get('id') if companies else None)
            active = u.get('active', True)
            locked = u.get('locked', False)
            pin = u.get('pin')
            permissions = json.dumps(u.get('permissions') or {})
            created_at = u.get('createdAt') or u.get('created_at') or None
            cur.execute(
                """
                INSERT INTO users (id, email, password, name, role, plan, active, locked, pin, permissions, company_id, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email, name = EXCLUDED.name, role = EXCLUDED.role, plan = EXCLUDED.plan
                RETURNING id
                """,
                (uid, email, password, name, role, plan, active, locked, pin, permissions, company_id, created_at)
            )

        # Upsert products and composite components
        for p in products:
            pid = p.get('id')
            company_id = p.get('company_id') or p.get('companyId') or (companies[0].get('id') if companies else None)
            name = p.get('name') or p.get('productName') or 'Imported Product'
            price = float(p.get('price') or 0)
            cost = float(p.get('cost') or 0)
            recipe = p.get('recipe') or []
            is_composite = bool(p.get('isComposite') or p.get('is_composite') or recipe)
            quantity = 0 if is_composite else int(p.get('quantity') or 0)
            unit = p.get('unit') or 'pcs'
            category = p.get('category') or 'general'
            visible = p.get('visible_to_cashier', p.get('visibleToCashier', True))
            created_at = p.get('createdAt') or p.get('created_at') or None

            cur.execute(
                """
                INSERT INTO products (id, company_id, name, price, cost, quantity, unit, category, is_composite, visible_to_cashier, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, price = EXCLUDED.price, cost = EXCLUDED.cost, quantity = EXCLUDED.quantity
                RETURNING id
                """,
                (pid, company_id, name, price, cost, quantity, unit, category, is_composite, visible, created_at)
            )

            if is_composite:
                cur.execute("DELETE FROM composite_components WHERE composite_product_id = %s", (pid,))
                for ingredient in recipe:
                    comp_pid = ingredient.get('productId') or ingredient.get('id')
                    qty = float(ingredient.get('quantity') or ingredient.get('qty') or 0)
                    if comp_pid is None or qty <= 0:
                        continue
                    cur.execute(
                        "INSERT INTO composite_components (composite_product_id, component_product_id, quantity) VALUES (%s,%s,%s)",
                        (pid, comp_pid, qty)
                    )

        # Upsert batches
        for b in batches:
            bid = b.get('id') or b.get('batchId')
            if not bid:
                continue
            company_id = b.get('company_id') or b.get('companyId') or (companies[0].get('id') if companies else None)
            product_id = b.get('product_id') or b.get('productId') or b.get('sku')
            quantity = float(b.get('quantity') or b.get('qty') or 0)
            cost = float(b.get('cost') or 0)
            batch_number = b.get('batch_number') or b.get('batch')
            created_at = b.get('createdAt') or b.get('created_at') or None
            expiry = b.get('expiry') or b.get('expiry_date') or None
            cur.execute(
                """
                INSERT INTO batches (id, company_id, product_id, quantity, cost, batch_number, created_at, expiry_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET quantity = EXCLUDED.quantity, cost = EXCLUDED.cost
                """,
                (bid, company_id, product_id, quantity, cost, batch_number, created_at, expiry)
            )

        # Upsert sales
        for s in sales:
            sid = s.get('id')
            if not sid:
                continue
            company_id = s.get('company_id') or s.get('companyId') or (companies[0].get('id') if companies else None)
            cashier_id = s.get('cashier_id') or s.get('cashierId')
            cashier_name = s.get('cashier_name') or s.get('cashierName') or s.get('cashier')
            items = s.get('items') or s.get('cart') or []
            total = float(s.get('total') or s.get('amount') or 0)
            created_at = s.get('createdAt') or s.get('created_at') or None
            cur.execute(
                """
                INSERT INTO sales (id, company_id, cashier_id, cashier_name, items, total, created_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET total = EXCLUDED.total
                """,
                (sid, company_id, cashier_id, cashier_name, json.dumps(items), total, created_at)
            )

        # Upsert expenses
        for e in expenses:
            eid = e.get('id')
            if not eid:
                continue
            company_id = e.get('company_id') or e.get('companyId') or (companies[0].get('id') if companies else None)
            description = e.get('description') or e.get('note') or ''
            amount = float(e.get('amount') or 0)
            category = e.get('category') or 'general'
            created_at = e.get('createdAt') or e.get('created_at') or None
            cur.execute(
                """
                INSERT INTO expenses (id, company_id, description, amount, category, created_at)
                VALUES (%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET amount = EXCLUDED.amount, description = EXCLUDED.description
                """,
                (eid, company_id, description, amount, category, created_at)
            )

        conn.commit()
        print('Migration completed successfully; backup at', str(backup_path))
        return 0

    except Exception as e:
        print('Migration failed:', e)
        try:
            conn.rollback()
        except Exception:
            pass
        return 3
    finally:
        try:
            cur.close()
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    exit(migrate())
