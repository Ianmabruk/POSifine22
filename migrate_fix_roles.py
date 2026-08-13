"""
Role Migration: Fix Hijacked Main Admin Roles
=============================================
 Safely migrates users who were incorrectly assigned the main_admin role
 back to business_admin (role = "admin").

 This migration is idempotent and safe to run multiple times.

 Criteria for hijacked users:
   - role = "main_admin"
   - AND account.plan != "owner"
   - AND account.business_type != "main_admin"

 Legitimate main admins are NOT touched:
   - Users with role = "main_admin" whose account has plan = "owner"
   - Users with role = "main_admin" whose account has business_type = "main_admin"
"""

import os
import sys
import logging

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import DataStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_roles():
    datastore = DataStore()
    migrated = 0
    skipped = 0
    errors = 0

    users = datastore.get_all("users")
    accounts = {acc.get("id"): acc for acc in datastore.get_all("accounts")}

    for user in users:
        try:
            if user.get("role") != "main_admin":
                continue

            account_id = user.get("account_id")
            account = accounts.get(account_id) if account_id else None

            if not account:
                skipped += 1
                continue

            plan = str(account.get("plan", "")).lower()
            business_type = str(account.get("business_type", "")).lower()

            if plan == "owner" or business_type == "main_admin":
                skipped += 1
                continue

            datastore.update("users", user.get("id"), {"role": "admin"}, account_id)
            logger.info(
                f"Migrated user {user.get('email')} (id={user.get('id')}) "
                f"from main_admin to admin (account={account_id}, plan={plan})"
            )
            migrated += 1

        except Exception as e:
            logger.error(f"Error migrating user {user.get('id')}: {e}")
            errors += 1

    logger.info(f"Migration complete: {migrated} migrated, {skipped} skipped, {errors} errors")
    return migrated, skipped, errors


if __name__ == "__main__":
    migrate_roles()
