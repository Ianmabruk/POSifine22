"""
Authentication Controller
========================
Handles signup, login, JWT generation/verification, and screen lock.
"""

from __future__ import annotations

import os
import uuid
import logging
import secrets
import hashlib
import time as _time
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, Callable
from functools import wraps

import bcrypt
import jwt
from flask import request, jsonify, g

logger = logging.getLogger(__name__)


class AuthController:
    """Authentication and authorization controller."""

    def __init__(self, datastore, secret_key: str, session_store=None):
        self.datastore = datastore
        self.secret_key = secret_key
        self.session_store = session_store
        # Simple in-memory TTL cache to reduce DB hits on every authenticated request
        self._auth_cache: Dict[str, Tuple[Any, float]] = {}
        self._AUTH_CACHE_TTL = 30  # seconds

    # ============================================================
    # Password hashing
    # ============================================================

    def hash_password(self, password: str) -> str:
        """Hash password using bcrypt."""
        salt = bcrypt.gensalt(rounds=10)
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
        """Generate JWT token for user with expiration."""
        payload = {
            "user_id": user["id"],
            "email": user["email"],
            "account_id": user["account_id"],
            "role": user.get("role", "cashier"),
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def _hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_refresh_session(self, user: Dict[str, Any], user_agent: str, ip_address: str) -> str:
        if self.session_store and getattr(self.session_store, "enabled", False):
            refresh_token = self.session_store.create(user, user_agent, ip_address)
            token_hash = self._hash_refresh_token(refresh_token)
            now = datetime.utcnow()
            expires_at = now + timedelta(days=7)

            session = {
                "account_id": user.get("account_id"),
                "user_id": user.get("id"),
                "refresh_token_hash": token_hash,
                "user_agent": user_agent,
                "ip_address": ip_address,
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "revoked_at": None
            }
            self.datastore.create("sessions", session)
            return refresh_token

        refresh_token = secrets.token_urlsafe(48)
        token_hash = self._hash_refresh_token(refresh_token)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=7)

        session = {
            "account_id": user.get("account_id"),
            "user_id": user.get("id"),
            "refresh_token_hash": token_hash,
            "user_agent": user_agent,
            "ip_address": ip_address,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "revoked_at": None
        }
        self.datastore.create("sessions", session)
        return refresh_token

    def rotate_refresh_session(self, refresh_token: str, user_agent: str, ip_address: str) -> Optional[Dict[str, Any]]:
        if self.session_store and getattr(self.session_store, "enabled", False):
            session = self.session_store.get(refresh_token)
            if not session:
                return None

            self.session_store.revoke(refresh_token)
            token_hash = self._hash_refresh_token(refresh_token)
            sessions = self.datastore.get_by_field("sessions", "refresh_token_hash", token_hash)
            if sessions:
                self.datastore.update("sessions", sessions[0].get("id"), {"revoked_at": datetime.utcnow().isoformat()})

            user = self.datastore.get_by_id("users", session.get("user_id"), session.get("account_id"))
            if not user:
                return None

            new_refresh = self.create_refresh_session(user, user_agent, ip_address)
            access_token = self.generate_token(user)
            return {
                "user": self._build_user_payload(user),
                "token": access_token,
                "refreshToken": new_refresh
            }

        token_hash = self._hash_refresh_token(refresh_token)
        sessions = self.datastore.get_by_field("sessions", "refresh_token_hash", token_hash)
        if not sessions:
            return None

        session = sessions[0]
        if session.get("revoked_at"):
            return None

        expires_at = session.get("expires_at")
        if expires_at and expires_at < datetime.utcnow().isoformat():
            return None

        # Revoke existing session
        self.datastore.update("sessions", session.get("id"), {"revoked_at": datetime.utcnow().isoformat()})

        user = self.datastore.get_by_id("users", session.get("user_id"), session.get("account_id"))
        if not user:
            return None

        new_refresh = self.create_refresh_session(user, user_agent, ip_address)
        access_token = self.generate_token(user)
        return {
            "user": self._build_user_payload(user),
            "token": access_token,
            "refreshToken": new_refresh
        }

    def revoke_refresh_session(self, refresh_token: str) -> bool:
        if self.session_store and getattr(self.session_store, "enabled", False):
            self.session_store.revoke(refresh_token)
            token_hash = self._hash_refresh_token(refresh_token)
            sessions = self.datastore.get_by_field("sessions", "refresh_token_hash", token_hash)
            if not sessions:
                return True
            session = sessions[0]
            return self.datastore.update("sessions", session.get("id"), {"revoked_at": datetime.utcnow().isoformat()})

        token_hash = self._hash_refresh_token(refresh_token)
        sessions = self.datastore.get_by_field("sessions", "refresh_token_hash", token_hash)
        if not sessions:
            return False
        session = sessions[0]
        return self.datastore.update("sessions", session.get("id"), {"revoked_at": datetime.utcnow().isoformat()})

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return payload."""
        try:
            return jwt.decode(token, self.secret_key, algorithms=["HS256"])
        except Exception:
            return None

    @staticmethod
    def _default_permissions(role: Optional[str]) -> Dict[str, bool]:
        normalized_role = (role or "cashier").strip().lower()
        if normalized_role in {"admin", "main_admin", "owner"}:
            return {
                "all": True,
                "manageUsers": True,
                "viewSales": True,
                "viewInventory": True,
                "viewExpenses": True,
                "manageProducts": True,
                "manageSettings": True,
                "manageReports": True,
                "manageBusiness": True
            }

        return {
            "viewSales": True,
            "viewInventory": True,
            "viewExpenses": False,
            "manageProducts": False
        }

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
        trial_duration_days = 15
        trial_end = (datetime.utcnow() + timedelta(days=trial_duration_days)).isoformat() if (plan or "").lower() in {"trial", "free_trial", "starter"} else None

        account = {
            "id": account_id,
            "owner_email": email,
            "business_name": name,
            "plan": plan or "free",
            "is_active": True,
            "is_locked": False,
            "trial_ends_at": trial_end,
            "subscription_ends_at": None,
            "created_at": now,
            "business_logo": None,
            "currency": "KES",
            "tax_rate": 0.0,
            "screen_lock_password": "2005",
            "days_used": 0,
            "last_activity_date": None,
            "requested_trial": trial_end is not None,
            "business_type": business_type
        }

        self.datastore.create("accounts", account)

        user = {
            "account_id": account_id,
            "email": email,
            "password_hash": self.hash_password(password),
            "name": name,
            "role": "admin",
            "permissions": self._default_permissions("admin"),
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

        try:
            # Fetch the created user to ensure all fields are properly set
            created_user = self.datastore.get_by_id("users", user.get("id"), account_id)
            if not created_user:
                created_user = user
            
            # Ensure screen_locked is False for new signups
            if created_user.get("screen_locked") != False:
                logger.warning(f"Signup: User {email} had screen_locked={created_user.get('screen_locked')}, resetting to False")
                self.datastore.update("users", created_user.get("id"), {"screen_locked": False}, account_id)
                created_user["screen_locked"] = False
            
            token = self.generate_token(created_user)
            
            return True, None, {
                "user": self._build_user_payload(created_user),
                "token": token
            }
        except Exception as e:
            logger.error(f"Error finalizing signup for {email}: {str(e)}")
            # Still return success since account and user were created
            return True, None, {
                "user": {"email": email, "name": name, "role": "admin", "active": True},
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

    def pin_login(self, email: str, pin: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """Login user by email + PIN."""
        email = (email or "").strip().lower()
        pin = str(pin or "").strip()
        if not email or not pin:
            return False, "Email and PIN are required", None

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

        stored_pin = str(user.get("pin") or user.get("cashier_pin") or "").strip()
        if not stored_pin:
            return False, "PIN not set for this user", None
        if stored_pin != pin:
            return False, "Invalid PIN", None

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
            # Allow CORS preflight requests without auth
            if request.method == "OPTIONS":
                return ("", 200)
            token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if not token:
                return jsonify({"error": "Authorization token required"}), 401

            payload = self.verify_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            user_id = payload.get("user_id")
            account_id = payload.get("account_id")
            cache_key = f"auth:{user_id}:{account_id}"
            now = _time.time()

            cached = self._auth_cache.get(cache_key)
            if cached and (now - cached[1]) < self._AUTH_CACHE_TTL:
                user, account = cached[0]
            else:
                user = self.datastore.get_by_id("users", user_id, account_id)
                # Fallback: try without account_id filter (handles account_id drift)
                if not user and user_id:
                    user = self.datastore.get_by_id("users", user_id, None)
                    if user:
                        account_id = user.get("account_id")
                if not user:
                    return jsonify({"error": "User not found"}), 401
                account = self.datastore.get_by_id("accounts", account_id)
                if not account:
                    return jsonify({"error": "Account not found"}), 401
                self._auth_cache[cache_key] = ((user, account), now)
                # Prune stale entries periodically
                if len(self._auth_cache) > 200:
                    cutoff = now - self._AUTH_CACHE_TTL * 2
                    self._auth_cache = {k: v for k, v in self._auth_cache.items() if v[1] > cutoff}

            g.user = user
            g.account = account
            if g.account.get("is_locked"):
                return jsonify({"error": "Account locked"}), 403
            if g.account.get("is_active") is False:
                return jsonify({"error": "Account inactive. Please choose a subscription."}), 403
            request.user = {
                "id": user["id"],
                "email": user["email"],
                "name": user.get("name"),
                "role": user.get("role"),
                "account_id": user.get("account_id"),
                "business_type": user.get("business_type"),
                "business_role": user.get("business_role"),
                "permissions": user.get("permissions") or self._default_permissions(user.get("role"))
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
        sanitized.pop("pin", None)
        sanitized.pop("cashier_pin", None)
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
            if account.get("business_logo") and not sanitized.get("business_logo"):
                sanitized["business_logo"] = account.get("business_logo")
            if account.get("business_type") and not sanitized.get("business_type"):
                sanitized["business_type"] = account.get("business_type")

        if account_id and not sanitized.get("business_type"):
            try:
                profiles = self.datastore.get_by_field("business_profiles", "account_id", account_id)
                if profiles:
                    sanitized["business_type"] = profiles[0].get("business_type")
            except Exception:
                pass

        if "active" not in sanitized:
            sanitized["active"] = bool(sanitized.get("is_active", True))

        if not sanitized.get("permissions"):
            sanitized["permissions"] = self._default_permissions(sanitized.get("role"))

        return sanitized
