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


_user_action_attempts: Dict[str, list] = {}
_user_action_blocked_until: Dict[str, float] = {}


def _user_rate_limit_key(user: Dict[str, Any]) -> Optional[str]:
    if user and user.get("id") and user.get("account_id"):
        return f"user:{user.get('account_id')}:{user.get('id')}"
    return None


def _is_user_rate_limited(user: Dict[str, Any], window_seconds: int = 60, max_attempts: int = 120) -> (bool, int):
    key = _user_rate_limit_key(user)
    if not key:
        return False, 0
    now = _time.time()
    blocked_until = _user_action_blocked_until.get(key)
    if blocked_until and blocked_until > now:
        return True, int(blocked_until - now)
    return False, 0


def _record_user_action(user: Dict[str, Any]) -> None:
    key = _user_rate_limit_key(user)
    if not key:
        return
    now = _time.time()
    attempts = _user_action_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < 60]
    attempts.append(now)
    _user_action_attempts[key] = attempts
    if len(attempts) > 120:
        _user_action_blocked_until[key] = now + 60


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

            try:
                payload = self.manager.verify_token(token)
            except Exception as exc:
                logger.error("Token verification failed: %s", exc)
                return jsonify({"error": "Invalid or expired token"}), 401
            if not payload:
                return jsonify({"error": "Invalid or expired token"}), 401

            user_id = payload.get("user_id")
            account_id = payload.get("account_id")
            cache_key = f"auth:{user_id}:{account_id}"
            now = _time.time()

            try:
                cached = self.manager._cache_get(cache_key)
                if cached:
                    user, account = cached
                else:
                    if not self.datastore:
                        return jsonify({"error": "Database not available"}), 500
                    user = self.datastore.get_by_id("users", user_id, account_id)
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
                elif plan not in ("free",):
                    sub_end = g.account.get("subscription_ends_at")
                    if sub_end:
                        try:
                            from datetime import datetime as _dt
                            if _dt.utcnow() > _dt.fromisoformat(sub_end):
                                return jsonify({
                                    "error": "Subscription expired. Please renew to continue.",
                                    "code": "SUBSCRIPTION_EXPIRED"
                                }), 403
                        except Exception:
                            pass

                if g.account.get("payment_required"):
                    return jsonify({
                        "error": "Kindly make payment to continue using the service.",
                        "code": "PAYMENT_REQUIRED"
                    }), 403

                # Per-user/account abuse rate limiting (token-cycling protection)
                is_limited, retry_after = _is_user_rate_limited(user)
                if is_limited:
                    return jsonify({"error": "Too many requests. Try again later.", "retry_after": retry_after}), 429
                _record_user_action(user)

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
            except Exception as exc:
                from werkzeug.exceptions import HTTPException
                if isinstance(exc, HTTPException):
                    raise exc
                logger.error("Auth middleware error: %s", exc, exc_info=True)
                return jsonify({"error": "Authentication error"}), 500
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
            return result
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
            return result
        return decorated


class require_business_admin:
    """Decorator to require business admin role (NOT main_admin)."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore
        self._auth = require_auth(manager, datastore)

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            result = self._auth(f)(*args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2 and result[1] >= 400:
                return result
            if request.user.get("role") not in {"admin", "main_admin", "owner"}:
                return jsonify({"error": "Business admin access required"}), 403
            return result
        return decorated


class require_cashier:
    """Decorator to require cashier role."""

    def __init__(self, manager: AuthManager, datastore=None):
        self.manager = manager
        self.datastore = datastore
        self._auth = require_auth(manager, datastore)

    def __call__(self, f: Callable) -> Callable:
        @wraps(f)
        def decorated(*args, **kwargs):
            result = self._auth(f)(*args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2 and result[1] >= 400:
                return result
            if request.user.get("role") != "cashier":
                return jsonify({"error": "Cashier access required"}), 403
            return result
        return decorated
