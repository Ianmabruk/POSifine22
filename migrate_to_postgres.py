#!/usr/bin/env python3
"""
Migrate JSON data to PostgreSQL
================================
Safely migrate existing JSON data files to PostgreSQL database
"""

import os
import json
import sys
from datetime import datetime
from database import DataStore
from dotenv import load_dotenv

# Load environment
load_dotenv()

def migrate_data():
    """Migrate all JSON data to PostgreSQL"""
    
    print("🚀 Starting migration from JSON to PostgreSQL...")
    print("=" * 60)
    
    # Initialize datastores
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    print("\n📁 Initializing JSON source...")
    json_store = DataStore(data_dir=data_dir, use_postgres=False)
    
    print("🐘 Initializing PostgreSQL target...")
    pg_store = DataStore(data_dir=data_dir, use_postgres=True)
    
    # Tables to migrate (in order due to foreign key constraints)
    tables = [
        'accounts',
        'users',
        'products',
        'batches',
        'sales',
        'expenses',
        'time_entries',
        'discounts',
        'credit_requests',
        'reminders',
        'vendors',
        'service_fees',
        'stock_movements',
        'business_profiles',
        'role_assignments',
        'appointments',
        'prescriptions',
        'table_orders',
        'room_bookings'
    ]
    
    stats = {
        'total': 0,
        'success': 0,
        'errors': 0,
        'by_table': {}
    }
    
    print("\n" + "=" * 60)
    print("📊 Migration Progress")
    print("=" * 60)
    
    for table in tables:
        try:
            print(f"\n📋 Migrating {table}...", end=" ", flush=True)
            
            # Get all records from JSON
            records = json_store.get_all(table)
            
            if not records:
                print("✓ (empty)")
                stats['by_table'][table] = 0
                continue
            
            migrated = 0
            errors = 0
            
            for record in records:
                try:
                    # Remove any auto-generated fields that should be set by DB
                    record_copy = record.copy()
                    
                    # For sales, ensure items is properly formatted
                    if table == 'sales' and 'items' in record_copy:
                        if isinstance(record_copy['items'], str):
                            try:
                                record_copy['items'] = json.loads(record_copy['items'])
                            except:
                                pass
                    
                    # Create in PostgreSQL
                    pg_store.create(table, record_copy)
                    migrated += 1
                    stats['success'] += 1
                    
                except Exception as e:
                    errors += 1
                    stats['errors'] += 1
                    if errors <= 3:  # Show first 3 errors only
                        print(f"\n  ⚠️  Error with record {record.get('id')}: {str(e)}")
            
            stats['total'] += migrated
            stats['by_table'][table] = migrated
            
            if errors > 0:
                print(f"✓ {migrated} records ({errors} errors)")
            else:
                print(f"✓ {migrated} records")
                
        except Exception as e:
            print(f"❌ Failed: {e}")
            stats['by_table'][table] = 0
    
    # Print summary
    print("\n" + "=" * 60)
    print("📈 Migration Summary")
    print("=" * 60)
    print(f"\n✅ Successfully migrated: {stats['success']} records")
    print(f"❌ Errors: {stats['errors']} records")
    print(f"📊 Total: {stats['total']} records")
    
    print("\n📋 Records by Table:")
    for table, count in stats['by_table'].items():
        if count > 0:
            print(f"  • {table:.<30} {count:>5} records")
    
    print("\n" + "=" * 60)
    
    if stats['errors'] > 0:
        print("\n⚠️  Some records failed to migrate.")
        print("   Check the errors above and fix data if needed.")
        return False
    else:
        print("\n🎉 Migration completed successfully!")
        print("   PostgreSQL is now your primary database.")
        return True

if __name__ == '__main__':
    try:
        success = migrate_data()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
