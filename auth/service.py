"""
Auth Service
============
Business logic for signup, login, PIN login, screen lock, password changes.
"""

from __future__ import annotations

import os
import uuid
import secrets
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any

from auth.manager import AuthManager

logger = logging.getLogger(__name__)


def _is_strong_password(password: str) -> bool:
    """Basic password policy that blocks clearly weak credentials."""
    if not isinstance(password, str):
        return False
    password = password.strip()
    if len(password) < 8:
        return False
    if password.lower() in {"password", "password123", "pass1234", "admin", "welcome", "letmein"}:
        return False
    has_upper = any(ch.isupper() for ch in password)
    has_lower = any(ch.islower() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_upper and has_lower and has_digit


def _send_welcome_email_async(email_service, to_email, name, business_name, login_url):
    """Send a welcome email in a background thread so it never blocks the signup response."""
    if not email_service or not getattr(email_service, "available", False):
        return

    def _do():
        try:
            email_service.send_welcome_email(to_email, name, business_name, login_url)
        except Exception as exc:
            logger.warning("Async welcome email failed for %s: %s", to_email, exc)

    threading.Thread(target=_do, daemon=True).start()



class AuthService:
    """High-level authentication workflows."""

    def __init__(self, manager: AuthManager, datastore=None, email_service=None):
        self.manager = manager
        self.datastore = datastore
        self.email_service = email_service

    def hash_password(self, password: str) -> str:
        return self.manager.hash_password(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        return self.manager.verify_password(password, password_hash)

    def generate_token(self, user: Dict[str, Any]) -> str:
        return self.manager.generate_token(user)

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        return self.manager.verify_token(token)

    # ============================================================
    # Signup
    # ============================================================

    def signup(
        self,
        email: str,
        password: str,
        name: str,
        business_name: Optional[str] = None,
        plan: str = "trial",
        business_type: Optional[str] = None,
        device_mode: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        email = (email or "").strip().lower()
        name = (name or "").strip()
        business_name = (business_name or name or "").strip()
        if not email or not password or not name:
            return False, "Email, password, and name are required", None
        if not _is_strong_password(password):
            return False, "Password must be at least 8 characters, include upper/lowercase letters and a number", None

        if self.datastore and self.datastore.get_user_by_email(email):
            return False, "Email already registered", None

        if self.datastore and self.datastore.get_account_by_email(email):
            return False, "An account with this email already exists", None

        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()
        trial_end = (datetime.utcnow() + timedelta(days=30)).isoformat()
        normalized_plan = (plan or "starter").strip().lower()
        valid_plans = {"starter", "business", "custom", "trial", "free"}
        if normalized_plan not in valid_plans:
            normalized_plan = "trial"

        is_custom = normalized_plan == "custom"
        account = {
            "id": account_id,
            "owner_email": email,
            "business_name": business_name,
            "plan": "custom" if is_custom else normalized_plan,
            "is_active": True if not is_custom else True,
            "is_locked": False,
            "trial_ends_at": trial_end if not is_custom else None,
            "subscription_ends_at": None,
            "created_at": now,
            "business_logo": None,
            "currency": "KES",
            "tax_rate": 0.0,
            "screen_lock_password": secrets.token_hex(8),
            "days_used": 0,
            "last_activity_date": None,
            "requested_trial": trial_end is not None and not is_custom,
            "business_type": business_type,
        }

        if self.datastore:
            self.datastore.create("accounts", account)

        user = {
            "account_id": account_id,
            "email": email,
            "password_hash": self.manager.hash_password(password),
            "name": name,
            "role": "cashier" if is_custom else "admin",
            "permissions": self.manager._default_permissions("cashier" if is_custom else "admin"),
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": now,
            "created_by": None,
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": business_type,
            "business_role": "cashier" if is_custom else "admin",
            "device_mode": device_mode,
        }

        if self.datastore:
            created_user = self.datastore.create("users", user)
        else:
            created_user = user

        token = self.manager.generate_token(created_user)

        try:
            _send_welcome_email_async(
                self.email_service, email, name, business_name,
                os.environ.get("APP_LOGIN_URL", "https://posify.co.ke/auth/login"),
            )
        except Exception as e:
            logger.warning(f"Failed to queue welcome email to {email}: {str(e)}")

        return True, None, {
            "user": self.manager._build_user_payload(created_user, account),
            "token": token,
        }

    # ============================================================
    # Login
    # ============================================================

    def login(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        email = (email or "").strip().lower()
        if not email or not password:
            return False, "Email and password required", None

        if not self.datastore:
            return False, "Database not available", None

        user = self.datastore.get_user_by_email(email)
        if not user:
            return False, "Invalid credentials", None

        account = self.datastore.get_by_id("accounts", user.get("account_id")) if user.get("account_id") else None
        if not account:
            return False, "Account not found", None
        if account.get("is_locked"):
            return False, "Account locked", None
        if account.get("is_active") is False:
            return False, "Account inactive. Please choose a subscription.", None

        if user.get("is_locked"):
            return False, "Account locked", None

        if not self.manager.verify_password(password, user.get("password_hash", "")):
            return False, "Invalid credentials", None

        token = self.manager.generate_token(user)
        return True, None, {
            "user": self.manager._build_user_payload(user, account),
            "token": token,
        }

    # ============================================================
    # Screen lock
    # ============================================================

    def lock_screen(self, user_id: int, account_id: str) -> bool:
        if not self.datastore:
            return False
        return self.datastore.update(
            "users", user_id, {"screen_locked": True}, account_id
        )

    def unlock_screen(
        self, user_id: int, account_id: str
    ) -> Tuple[bool, Optional[str]]:
        if not self.datastore:
            return False, "Database not available"
        user = self.datastore.get_by_id("users", user_id, account_id)
        if not user:
            return False, "User not found"
        self.datastore.update(
            "users", user_id, {"screen_locked": False}, account_id
        )
        return True, None

    # ============================================================
    # Password / PIN changes
    # ============================================================

    def change_password(
        self,
        user: Dict[str, Any],
        current_password: str,
        new_password: Optional[str] = None,
        new_pin: Optional[str] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not self.datastore:
            return False, "Database not available"
        db_user = self.datastore.get_by_id(
            "users", user.get("id"), user.get("account_id")
        )
        if not db_user:
            return False, "User not found"
        if not self.manager.verify_password(
            current_password, db_user.get("password_hash", "")
        ):
            return False, "Current password is incorrect"
        updates = {}
        changed = []
        if new_password:
            if not _is_strong_password(new_password):
                return False, "New password must be at least 8 characters, include upper/lowercase letters and a number"
            updates["password_hash"] = self.manager.hash_password(new_password)
            changed.append("password")
        if not updates:
            return False, "No changes provided"
        updates["updated_at"] = datetime.utcnow().isoformat()
        success = self.datastore.update(
            "users", user.get("id"), updates, user.get("account_id")
        )
        if not success:
            return False, "Failed to update credentials"
        return True, " and ".join(changed) + " changed successfully"

    # ============================================================
    # Main admin bootstrap / login helper
    # ============================================================

    def ensure_main_admin(
        self, email: str, password_hash: str, display_name: str = "Main Admin"
    ) -> Dict[str, Any]:
        if not self.datastore:
            return {}
        owner_user = self.datastore.get_user_by_email(email)
        if owner_user:
            if owner_user.get("role") in {"main_admin", "owner"}:
                update_data = {"is_active": True, "is_locked": False}
                if password_hash:
                    update_data["password_hash"] = password_hash
                self.datastore.update(
                    "users", owner_user.get("id"), update_data, owner_user.get("account_id")
                )
                return self.datastore.get_user_by_email(email) or owner_user
            return {}

        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        account = {
            "id": account_id,
            "owner_email": email,
            "business_name": "Main Admin",
            "plan": "owner",
            "is_active": True,
            "is_locked": False,
            "trial_ends_at": None,
            "subscription_ends_at": None,
            "created_at": datetime.utcnow().isoformat(),
            "business_logo": None,
            "currency": "KES",
            "tax_rate": 0.0,
            "screen_lock_password": "2005",
            "days_used": 0,
            "last_activity_date": None,
            "requested_trial": False,
            "business_type": "main_admin",
        }
        self.datastore.create("accounts", account)

        return self.datastore.create("users", {
            "account_id": account_id,
            "email": email,
            "password_hash": password_hash,
            "name": display_name,
            "role": "main_admin",
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": None,
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": "main_admin",
            "business_role": "main_admin",
        })

    # ============================================================
    # Helpers
    # ============================================================
