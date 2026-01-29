"""
Authentication Controller
========================
Handles signup, login, JWT generation/verification, and screen lock.
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, Callable
from functools import wraps

import bcrypt
import jwt
from flask import request, jsonify, g

logger = logging.getLogger(__name__)


class AuthController:
    """Authentication and authorization controller."""

    def __init__(self, datastore, secret_key: str):
        self.datastore = datastore
        self.secret_key = secret_key

    # ============================================================
    # Password hashing
    # ============================================================

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against stored hash."""
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    # ============================================================
    # Token handling
    # ============================================================

    def generate_token(self, user: Dict[str, Any]) -> str:
        """Generate JWT token for user."""
        payload = {
            "user_id": user["id"],
            "email": user["email"],
            "account_id": user["account_id"],
            "role": user.get("role", "cashier"),
            "exp": datetime.utcnow() + timedelta(days=7)
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload."""
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except Exception:
            return None

    # ============================================================
    # Auth flows
    # ============================================================

    def signup(
        self,
        email: str,
        password: str,
        name: str,
        plan: str = "free",
        business_type: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Create account + first user."""
        email = (email or "").strip().lower()
        name = (name or "").strip()
        if not email or not password or not name:
            return False, "Email, password, and name are required", None

        if self.datastore.get_user_by_email(email):
            return False, "Email already registered", None

        account_id = f"acc_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow().isoformat()

        account = {
            "id": account_id,
            "owner_email": email,
            "business_name": name,
            "plan": plan or "free",
            "is_active": True,
            "is_locked": False,
            "trial_ends_at": None,
            "subscription_ends_at": None,
            "created_at": now,
            "business_logo": None,
            "currency": "KES",
            "tax_rate": 0.0,
            "screen_lock_password": "2005",
            "days_used": 0,
            "last_activity_date": None,
            "requested_trial": False,
            "business_type": business_type
        }

        self.datastore.create("accounts", account)

        user = {
            "account_id": account_id,
            "email": email,
            "password_hash": self.hash_password(password),
            "name": name,
            "role": "admin",
            "pin": None,
            "cashier_pin": None,
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": now,
            "created_by": None,
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": business_type,
            "business_role": "admin"
        }

        user = self.datastore.create("users", user)
        token = self.generate_token(user)

        return True, None, {
            "user": self._build_user_payload(user),
            "token": token
        }

    def login(self, email: str, password: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Login user by email/password."""
        email = (email or "").strip().lower()
        if not email or not password:
            return False, "Email and password required", None

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

        if not self.verify_password(password, user.get("password_hash", "")):
            return False, "Invalid credentials", None

        self.datastore.update("users", user["id"], {"last_login": datetime.utcnow().isoformat()}, user.get("account_id"))
        token = self.generate_token(user)

        return True, None, {
            "user": self._build_user_payload(user),
            "token": token
        }

    # ============================================================
    # Screen lock
    # ============================================================

    def lock_screen(self, user_id: int, account_id: str) -> bool:
        """Lock user screen."""
        return self.datastore.update("users", user_id, {"screen_locked": True}, account_id)

    def unlock_screen(self, user_id: int, pin: str, account_id: str) -> Tuple[bool, Optional[str]]:
        """Unlock screen if pin matches."""
        user = self.datastore.get_by_id("users", user_id, account_id)
        if not user:
            return False, "User not found"

        valid_pin = user.get("pin") or user.get("cashier_pin")
        if not valid_pin or str(valid_pin) != str(pin):
            return False, "Invalid PIN"

        self.datastore.update("users", user_id, {"screen_locked": False}, account_id)
        return True, None

    # ============================================================
    # Decorators
    # ============================================================

    def require_auth(self, f: Callable) -> Callable:
        """Decorator to require valid JWT auth."""
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if not token:
                return jsonify({"error": "Authorization token required"}), 401

            payload = self.verify_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            user = self.datastore.get_by_id("users", payload.get("user_id"), payload.get("account_id"))
            if not user:
                return jsonify({"error": "User not found"}), 401

            g.user = user
            g.account = self.datastore.get_by_id("accounts", payload.get("account_id"))
            if not g.account:
                return jsonify({"error": "Account not found"}), 401
            if g.account.get("is_locked"):
                return jsonify({"error": "Account locked"}), 403
            if g.account.get("is_active") is False:
                return jsonify({"error": "Account inactive. Please choose a subscription."}), 403
            request.user = {
                "id": user["id"],
                "email": user["email"],
                "role": user.get("role"),
                "account_id": user.get("account_id")
            }
            return f(*args, **kwargs)
        return decorated

    # ============================================================
    # Helpers
    # ============================================================

    @staticmethod
    def _sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(user)
        sanitized.pop("password_hash", None)
        return sanitized

    def _build_user_payload(self, user: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = self._sanitize_user(user)
        account_id = user.get("account_id")
        account = self.datastore.get_by_id("accounts", account_id) if account_id else None

        if account:
            sanitized["plan"] = account.get("plan")
            sanitized["subscription"] = account.get("plan")
            sanitized["active"] = bool(account.get("is_active", True))
            sanitized["account_active"] = bool(account.get("is_active", True))
            if account.get("business_type") and not sanitized.get("business_type"):
                sanitized["business_type"] = account.get("business_type")

        if "active" not in sanitized:
            sanitized["active"] = bool(sanitized.get("is_active", True))

        return sanitized
