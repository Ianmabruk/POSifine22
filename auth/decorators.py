"""
Auth Decorators
===============
Flask decorators for protecting routes and checking roles.
"""

from __future__ import annotations

import time as _time
import logging
from typing import Callable, Optional, Dict, Any
from functools import wraps

from flask import request, jsonify, g

from auth.manager import AuthManager

logger = logging.getLogger(__name__)


class require_auth:
    """Decorator class to require valid JWT auth."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            if request.method == "OPTIONS":
                return ("", 200)
            token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if not token:
                return jsonify({"error": "Authorization token required"}), 401

            payload = self.manager.verify_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            user_id = payload.get("user_id")
            account_id = payload.get("account_id")
            cache_key = f"auth:{user_id}:{account_id}"
            now = _time.time()

            cached = self.manager._cache_get(cache_key)
            if cached:
                user, account = cached
            else:
                if not self.datastore:
                    return jsonify({"error": "Database not available"}), 500
                user = self.datastore.get_by_id("users", user_id, account_id)
                if not user and user_id:
                    user = self.datastore.get_by_id("users", user_id, None)
                    if user:
                        account_id = user.get("account_id")
                if not user:
                    return jsonify({"error": "User not found"}), 401
                account = self.datastore.get_by_id("accounts", account_id)
                if not account:
                    return jsonify({"error": "Account not found"}), 401
                self.manager._cache_set(cache_key, (user, account))

            g.user = user
            g.account = account
            if g.account.get("is_locked"):
                return jsonify({"error": "Account locked"}), 403
            if g.account.get("is_active") is False:
                return jsonify({"error": "Account inactive. Please choose a subscription."}), 403

            trial_end = g.account.get("trial_ends_at")
            plan = g.account.get("plan", "free")
            if plan == "trial" and trial_end:
                try:
                    from datetime import datetime as _dt
                    if _dt.utcnow() > _dt.fromisoformat(trial_end):
                        return jsonify({
                            "error": "Trial expired. Please subscribe to continue.",
                            "code": "TRIAL_EXPIRED"
                        }), 403
                except Exception:
                    pass

            request.user = {
                "id": user["id"],
                "email": user["email"],
                "name": user.get("name"),
                "role": user.get("role"),
                "account_id": user.get("account_id"),
                "business_type": user.get("business_type"),
                "business_role": user.get("business_role"),
                "permissions": user.get("permissions") or self.manager._default_permissions(user.get("role")),
            }
            return f(*args, **kwargs)
        return decorated


class require_admin:
    """Decorator to require admin, main_admin, or owner role."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore
        self._auth = require_auth(manager, datastore)

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            result = self._auth(f)(*args, **kwargs)
            if isinstance(result, tuple) and result[1] >= 400:
                return result
            if request.user.get("role") not in {"admin", "main_admin", "owner"}:
                return jsonify({"error": "Admin access required"}), 403
            return f(*args, **kwargs)
        return decorated


class require_main_admin:
    """Decorator to require main_admin or owner role."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore
        self._auth = require_auth(manager, datastore)

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            result = self._auth(f)(*args, **kwargs)
            if isinstance(result, tuple) and result[1] >= 400:
                return result
            if request.user.get("role") not in {"main_admin", "owner"}:
                return jsonify({"error": "Access denied"}), 403
            return f(*args, **kwargs)
        return decorated


class require_business_admin:
    """Decorator to require business admin role."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore
        self._auth = require_auth(manager, datastore)

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            # Run auth check first
            auth_decorated = self._auth(f)
            # Check role before calling the actual function
            token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
            if not token:
                return jsonify({"error": "Authorization token required"}), 401
            payload = self.manager.verify_token(token)
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401
            user_id = payload.get("user_id")
            account_id = payload.get("account_id")
            if not self.datastore:
                return jsonify({"error": "Database not available"}), 500
            user = self.datastore.get_by_id("users", user_id, account_id)
            if not user:
                return jsonify({"error": "User not found"}), 401
            role = user.get("role", "cashier")
            if role not in {"admin", "main_admin", "owner"}:
                return jsonify({"error": "Admin access required"}), 403
            return auth_decorated(*args, **kwargs)
        return decorated
