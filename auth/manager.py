"""
Auth Manager
============
Handles JWT tokens, refresh tokens, password hashing, and session storage.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

import bcrypt
import jwt

logger = logging.getLogger(__name__)


class AuthManager:
    """Core authentication primitives: hashing, JWT, refresh tokens."""

    def __init__(self, secret_key: str, session_store=None, datastore=None):
        self.secret_key = secret_key
        self.session_store = session_store
        self.datastore = datastore
        self._auth_cache: Dict[str, Tuple[Any, float]] = {}
        self._AUTH_CACHE_TTL = 300
        self._revoked_tokens: set = set()

    # ============================================================
    # Password hashing
    # ============================================================

    def hash_password(self, password: str) -> str:
        salt = bcrypt.gensalt(rounds=10)
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_password(self, password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
        except Exception:
            return False

    def hash_pin(self, pin: str) -> str:
        salt = bcrypt.gensalt(rounds=10)
        hashed = bcrypt.hashpw(pin.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    def verify_pin(self, pin: str, pin_hash: str) -> bool:
        try:
            return bcrypt.checkpw(pin.encode("utf-8"), pin_hash.encode("utf-8"))
        except Exception:
            return False

    # ============================================================
    # Token handling
    # ============================================================

    def generate_token(self, user: Dict[str, Any]) -> str:
        payload = {
            "jti": uuid.uuid4().hex,
            "user_id": user["id"],
            "email": user["email"],
            "account_id": user["account_id"],
            "role": user.get("role", "cashier"),
            "exp": datetime.utcnow() + timedelta(hours=24),
            "iat": datetime.utcnow(),
        }
        return jwt.encode(payload, self.secret_key, algorithm="HS256")

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            jti = payload.get("jti")
            if jti and jti in self._revoked_tokens:
                return None
            return payload
        except Exception:
            return None

    def revoke_token(self, token: str) -> bool:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"], options={"verify_exp": False})
            jti = payload.get("jti")
            if jti:
                self._revoked_tokens.add(jti)
                return True
        except Exception:
            pass
        return False

    def _hash_refresh_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def create_refresh_session(
        self, user: Dict[str, Any], user_agent: str, ip_address: str
    ) -> str:
        if self.session_store and getattr(self.session_store, "enabled", False):
            refresh_token = self.session_store.create(
                user, user_agent, ip_address
            )
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
                "revoked_at": None,
            }
            if self.datastore:
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
            "revoked_at": None,
        }
        if self.datastore:
            self.datastore.create("sessions", session)
        return refresh_token

    def rotate_refresh_session(
        self, refresh_token: str, user_agent: str, ip_address: str
    ) -> Optional[Dict[str, Any]]:
        if self.session_store and getattr(self.session_store, "enabled", False):
            session = self.session_store.get(refresh_token)
            if not session:
                return None
            self.session_store.revoke(refresh_token)
            token_hash = self._hash_refresh_token(refresh_token)
            if self.datastore:
                sessions = self.datastore.get_by_field(
                    "sessions", "refresh_token_hash", token_hash
                )
                if sessions:
                    self.datastore.update(
                        "sessions",
                        sessions[0].get("id"),
                        {"revoked_at": datetime.utcnow().isoformat()},
                    )
            user = self.datastore.get_by_id(
                "users", session.get("user_id"), session.get("account_id")
            ) if self.datastore else None
            if not user:
                return None
            new_refresh = self.create_refresh_session(user, user_agent, ip_address)
            access_token = self.generate_token(user)
            return {
                "user": self._build_user_payload(user),
                "token": access_token,
                "refreshToken": new_refresh,
            }

        token_hash = self._hash_refresh_token(refresh_token)
        if not self.datastore:
            return None
        sessions = self.datastore.get_by_field(
            "sessions", "refresh_token_hash", token_hash
        )
        if not sessions:
            return None
        session = sessions[0]
        if session.get("revoked_at"):
            return None
        expires_at = session.get("expires_at")
        if expires_at and expires_at < datetime.utcnow().isoformat():
            return None
        self.datastore.update(
            "sessions",
            session.get("id"),
            {"revoked_at": datetime.utcnow().isoformat()},
        )
        user = self.datastore.get_by_id(
            "users", session.get("user_id"), session.get("account_id")
        )
        if not user:
            return None
        new_refresh = self.create_refresh_session(user, user_agent, ip_address)
        access_token = self.generate_token(user)
        return {
            "user": self._build_user_payload(user),
            "token": access_token,
            "refreshToken": new_refresh,
        }

    def revoke_refresh_session(self, refresh_token: str) -> bool:
        if self.session_store and getattr(self.session_store, "enabled", False):
            self.session_store.revoke(refresh_token)
            token_hash = self._hash_refresh_token(refresh_token)
            if self.datastore:
                sessions = self.datastore.get_by_field(
                    "sessions", "refresh_token_hash", token_hash
                )
                if not sessions:
                    return True
                session = sessions[0]
                return self.datastore.update(
                    "sessions",
                    session.get("id"),
                    {"revoked_at": datetime.utcnow().isoformat()},
                )
            return True

        token_hash = self._hash_refresh_token(refresh_token)
        if not self.datastore:
            return False
        sessions = self.datastore.get_by_field(
            "sessions", "refresh_token_hash", token_hash
        )
        if not sessions:
            return False
        session = sessions[0]
        return self.datastore.update(
            "sessions",
            session.get("id"),
            {"revoked_at": datetime.utcnow().isoformat()},
        )

    # ============================================================
    # User payload helpers
    # ============================================================

    @staticmethod
    def _sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(user)
        sanitized.pop("password_hash", None)
        sanitized.pop("pin", None)
        sanitized.pop("cashier_pin", None)
        return sanitized

    def _build_user_payload(self, user: Dict[str, Any]) -> Dict[str, Any]:
        try:
            sanitized = self._sanitize_user(user)
            account_id = user.get("account_id")
            account = (
                self.datastore.get_by_id("accounts", account_id)
                if self.datastore and account_id
                else None
            )
            if account:
                sanitized["plan"] = account.get("plan")
                sanitized["subscription"] = account.get("plan")
                sanitized["active"] = bool(account.get("is_active", True))
                sanitized["account_active"] = bool(account.get("is_active", True))
                if account.get("business_logo") and not sanitized.get("business_logo"):
                    sanitized["business_logo"] = account.get("business_logo")
                if account.get("business_type") and not sanitized.get("business_type"):
                    sanitized["business_type"] = account.get("business_type")

            if account_id and not sanitized.get("business_type") and self.datastore:
                try:
                    profiles = self.datastore.get_by_field(
                        "business_profiles", "account_id", account_id
                    )
                    if profiles:
                        sanitized["business_type"] = profiles[0].get("business_type")
                except Exception:
                    pass

            if "active" not in sanitized:
                sanitized["active"] = bool(sanitized.get("is_active", True))
            return sanitized
        except Exception as exc:
            logger.error("_build_user_payload error: %s", exc, exc_info=True)
            return {
                "id": user.get("id"),
                "email": user.get("email"),
                "name": user.get("name"),
                "role": user.get("role"),
                "account_id": user.get("account_id"),
                "active": bool(user.get("is_active", True)),
            }

    # ============================================================
    # Cache helpers
    # ============================================================

    def _cache_get(self, key: str):
        now = datetime.utcnow().timestamp()
        cached = self._auth_cache.get(key)
        if cached and (now - cached[1]) < self._AUTH_CACHE_TTL:
            return cached[0]
        return None

    def _cache_set(self, key: str, value):
        now = datetime.utcnow().timestamp()
        self._auth_cache[key] = (value, now)
        if len(self._auth_cache) > 200:
            cutoff = now - self._AUTH_CACHE_TTL * 2
            self._auth_cache = {
                k: v for k, v in self._auth_cache.items() if v[1] > cutoff
            }

    @property
    def require_auth(self):
        from auth.decorators import require_auth
        return require_auth(self, self.datastore)

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
                "manageBusiness": True,
            }
        return {
            "viewSales": True,
            "viewInventory": True,
            "viewExpenses": False,
            "manageProducts": False,
        }
