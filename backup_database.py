#!/usr/bin/env python3
"""
Database Backup Script
======================
Automated backup script for PostgreSQL database with rotation.

Usage:
    python backup_database.py                    # Manual backup
    python backup_database.py --restore latest   # Restore from latest backup
    
Schedule with cron:
    0 2 * * * cd /path/to/backend && python backup_database.py  # Daily at 2 AM
"""

import os
import sys
import subprocess
import gzip
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import argparse


# Configuration
BACKUP_DIR = os.environ.get('BACKUP_DIR', os.path.join(os.path.dirname(__file__), 'backups'))
RETENTION_DAYS = int(os.environ.get('BACKUP_RETENTION_DAYS', '30'))  # Keep backups for 30 days
MAX_BACKUPS = int(os.environ.get('MAX_BACKUPS', '100'))  # Maximum number of backups to keep

# PostgreSQL connection
DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)


def ensure_backup_directory():
    """Create backup directory if it doesn't exist"""
    Path(BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    print(f"📁 Backup directory: {BACKUP_DIR}")


def get_backup_filename():
    """Generate backup filename with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return f"pos_backup_{timestamp}.sql.gz"


def backup_postgresql():
    """Backup PostgreSQL database"""
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not set")
        return False
    
    print("🔄 Starting PostgreSQL backup...")
    
    filename = get_backup_filename()
    filepath = os.path.join(BACKUP_DIR, filename)
    
    try:
        # Use pg_dump to create backup
        print(f"📦 Creating backup: {filename}")
        
        # Run pg_dump and pipe to gzip
        pg_dump_cmd = f"pg_dump {DATABASE_URL}"
        with open(filepath, 'wb') as f:
            pg_dump = subprocess.Popen(
                pg_dump_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            gzip_proc = subprocess.Popen(
                ['gzip'],
                stdin=pg_dump.stdout,
                stdout=f,
                stderr=subprocess.PIPE
            )
            
            pg_dump.stdout.close()
            gzip_proc.communicate()
        
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"✅ Backup completed: {filename} ({size_mb:.2f} MB)")
            
            # Save metadata
            metadata = {
                'filename': filename,
                'timestamp': datetime.now().isoformat(),
                'size_bytes': os.path.getsize(filepath),
                'database_url': DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else 'unknown'
            }
            
            metadata_file = filepath.replace('.sql.gz', '.json')
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            return True
        else:
            print("❌ Backup file not created")
            return False
            
    except Exception as e:
        print(f"❌ Backup failed: {e}")
        return False


def backup_json_files():
    """Backup JSON data files"""
    data_dir = os.environ.get('DATA_DIR', os.path.join(os.path.dirname(__file__), 'data'))
    
    if not os.path.exists(data_dir):
        print("⚠️  No JSON data directory found")
        return False
    
    print("🔄 Starting JSON files backup...")
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f"pos_json_backup_{timestamp}"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        # Create tar.gz archive of data directory
        shutil.make_archive(backup_path, 'gztar', data_dir)
        
        filepath = f"{backup_path}.tar.gz"
        if os.path.exists(filepath):
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            print(f"✅ JSON backup completed: {backup_name}.tar.gz ({size_mb:.2f} MB)")
            return True
        else:
            print("❌ JSON backup file not created")
            return False
            
    except Exception as e:
        print(f"❌ JSON backup failed: {e}")
        return False


def cleanup_old_backups():
    """Remove backups older than retention period"""
    print(f"🧹 Cleaning up backups older than {RETENTION_DAYS} days...")
    
    cutoff_date = datetime.now() - timedelta(days=RETENTION_DAYS)
    removed_count = 0
    
    for filename in os.listdir(BACKUP_DIR):
        filepath = os.path.join(BACKUP_DIR, filename)
        
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            if file_time < cutoff_date:
                os.remove(filepath)
                removed_count += 1
                print(f"  🗑️  Removed old backup: {filename}")
    
    if removed_count > 0:
        print(f"✅ Removed {removed_count} old backup(s)")
    else:
        print("✅ No old backups to remove")


def list_backups():
    """List all available backups"""
    print("📋 Available backups:")
    print("-" * 80)
    
    backups = []
    for filename in sorted(os.listdir(BACKUP_DIR), reverse=True):
        if filename.endswith(('.sql.gz', '.tar.gz')):
            filepath = os.path.join(BACKUP_DIR, filename)
            size_mb = os.path.getsize(filepath) / (1024 * 1024)
            mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
            
            backups.append({
                'filename': filename,
                'size_mb': size_mb,
                'created': mtime
            })
    
    if backups:
        for i, backup in enumerate(backups, 1):
            age = datetime.now() - backup['created']
            age_str = f"{age.days}d ago" if age.days > 0 else f"{age.seconds // 3600}h ago"
            print(f"{i}. {backup['filename']:<50} {backup['size_mb']:>8.2f} MB  {age_str}")
    else:
        print("No backups found")
    
    print("-" * 80)
    return backups


def restore_backup(backup_file):
    """Restore database from backup"""
    filepath = os.path.join(BACKUP_DIR, backup_file) if not os.path.isabs(backup_file) else backup_file
    
    if not os.path.exists(filepath):
        print(f"❌ Backup file not found: {filepath}")
        return False
    
    if not DATABASE_URL:
        print("❌ ERROR: DATABASE_URL not set")
        return False
    
    print(f"⚠️  WARNING: This will overwrite the current database!")
    print(f"📦 Restoring from: {backup_file}")
    
    confirm = input("Type 'YES' to continue: ")
    if confirm != 'YES':
        print("❌ Restore cancelled")
        return False
    
    try:
        print("🔄 Restoring database...")
        
        # Decompress and restore
        gunzip = subprocess.Popen(['gunzip', '-c', filepath], stdout=subprocess.PIPE)
        psql = subprocess.Popen(
            f"psql {DATABASE_URL}",
            shell=True,
            stdin=gunzip.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        gunzip.stdout.close()
        stdout, stderr = psql.communicate()
        
        if psql.returncode == 0:
            print("✅ Database restored successfully")
            return True
        else:
            print(f"❌ Restore failed: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"❌ Restore failed: {e}")
        return False


def main():
    """Main backup script"""
    parser = argparse.ArgumentParser(description='Database backup and restore utility')
    parser.add_argument('--restore', metavar='BACKUP_FILE', help='Restore from backup file')
    parser.add_argument('--list', action='store_true', help='List available backups')
    parser.add_argument('--cleanup-only', action='store_true', help='Only run cleanup, no backup')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("🗄️  POS Database Backup Utility")
    print("=" * 80)
    
    ensure_backup_directory()
    
    if args.list:
        list_backups()
        return 0
    
    if args.restore:
        if args.restore == 'latest':
            backups = list_backups()
            if backups:
                success = restore_backup(backups[0]['filename'])
            else:
                print("❌ No backups available")
                return 1
        else:
            success = restore_backup(args.restore)
        
        return 0 if success else 1
    
    # Perform backup
    if not args.cleanup_only:
        if DATABASE_URL:
            success_pg = backup_postgresql()
        else:
            print("⚠️  PostgreSQL not configured, skipping")
            success_pg = True
        
        success_json = backup_json_files()
        
        if not (success_pg or success_json):
            print("❌ All backups failed")
            return 1
    
    # Cleanup old backups
    cleanup_old_backups()
    
    print("=" * 80)
    print("✅ Backup process completed")
    print("=" * 80)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
