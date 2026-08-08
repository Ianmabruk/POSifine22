"""
Auth Routes
===========
Flask blueprints for regular auth and main-admin auth endpoints.
"""

from __future__ import annotations

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from flask import Blueprint, request, jsonify

from auth.manager import AuthManager
from auth.service import AuthService
from auth.decorators import require_auth, require_main_admin

logger = logging.getLogger(__name__)


# ============================================================
# Helpers (inline to keep blueprint self-contained)
# ============================================================

def _build_cookie_path(scope: str = "auth") -> str:
    return "/api/main-admin" if scope == "main_admin" else "/api/auth"


def _set_auth_cookies(response, refresh_token: Optional[str], csrf_token: Optional[str], samesite: str, scope: str = "auth"):
    cookie_path = _build_cookie_path(scope)
    if refresh_token:
        response.set_cookie(
            "refresh_token",
            refresh_token,
            secure=True,
            httponly=True,
            samesite=samesite,
            path=cookie_path,
            max_age=7 * 24 * 60 * 60,
        )
    if csrf_token:
        response.set_cookie(
            "csrf_token",
            csrf_token,
            secure=True,
            httponly=False,
            samesite=samesite,
            path=cookie_path,
            max_age=7 * 24 * 60 * 60,
        )


def _clear_auth_cookies(response, samesite: str, scope: str = "auth"):
    cookie_path = _build_cookie_path(scope)
    response.set_cookie("refresh_token", "", expires=0, secure=True, httponly=True, samesite=samesite, path=cookie_path)
    response.set_cookie("csrf_token", "", expires=0, secure=True, httponly=False, samesite=samesite, path=cookie_path)


# ============================================================
# Blueprints
# ============================================================

def create_auth_blueprint(
    manager: AuthManager,
    service: AuthService,
    datastore=None,
    cache=None,
    time_tracking=None,
    samesite: str = "Lax",
) -> Blueprint:
    bp = Blueprint("auth", __name__)

    # Rate limit state (in-memory fallback when cache unavailable)
    login_attempts: Dict[str, list] = {}
    login_blocked_until: Dict[str, float] = {}
    signup_attempts: Dict[str, list] = {}
    refresh_attempts: Dict[str, list] = {}
    logout_attempts: Dict[str, list] = {}

    def _client_ip() -> str:
        return request.remote_addr or "unknown"

    def _is_rate_limited(attempts: Dict[str, list], blocked: Dict[str, float], window: int, max_attempts: int) -> Tuple[bool, int]:
        key = _client_ip()
        now = __import__("time").time()
        if cache and getattr(cache, "enabled", False):
            blocked_until = cache.get_int(f"rl:block:{key}")
            if blocked_until and blocked_until > cache.now_ts():
                return True, int(blocked_until - cache.now_ts())
            return False, 0
        blocked_until = blocked.get(key)
        if blocked_until and blocked_until > now:
            return True, int(blocked_until - now)
        return False, 0

    def _record_attempt(attempts: Dict[str, list], blocked: Dict[str, float], window: int, max_attempts: int):
        key = _client_ip()
        now = __import__("time").time()
        if cache and getattr(cache, "enabled", False):
            cache.incr_with_ttl(f"rl:fail:{key}", window)
            return
        arr = attempts.get(key, [])
        arr = [t for t in arr if now - t < window]
        arr.append(now)
        attempts[key] = arr
        if len(arr) >= max_attempts:
            blocked[key] = now + window

    def _reset_attempts(attempts: Dict[str, list], blocked: Dict[str, float]):
        key = _client_ip()
        if cache and getattr(cache, "enabled", False):
            cache.delete(f"rl:fail:{key}")
            cache.delete(f"rl:block:{key}")
            return
        attempts.pop(key, None)
        blocked.pop(key, None)

    # ============================================================
    # Signup
    # ============================================================

    @bp.route("/signup", methods=["POST"])
    def signup():
        if _is_rate_limited(signup_attempts, login_blocked_until, 3600, 5)[0]:
            return jsonify({"error": "Too many signup attempts. Please try again later."}), 429
        try:
            data = request.get_json() or {}
            email = (data.get("email") or "").strip()
            password = (data.get("password") or "").strip()
            name = (data.get("name") or "").strip()
            if not email or not password or not name:
                return jsonify({"error": "Email, password, and name are required"}), 400
            if len(password) < 8:
                return jsonify({"error": "Password must be at least 8 characters"}), 400
            if not any(c.isdigit() for c in password):
                return jsonify({"error": "Password must contain at least one number"}), 400
            if not any(c.isupper() for c in password):
                return jsonify({"error": "Password must contain at least one uppercase letter"}), 400

            success, error, result = service.signup(
                email=email,
                password=password,
                name=name,
                plan=data.get("plan", "free"),
                business_type=data.get("business_type"),
            )
            if success:
                _record_attempt(signup_attempts, login_blocked_until, 3600, 5)
                refresh_token = manager.create_refresh_session(
                    user=result.get("user") or {},
                    user_agent=request.headers.get("User-Agent", ""),
                    ip_address=_client_ip(),
                )
                csrf_token = uuid.uuid4().hex
                result["refreshToken"] = refresh_token
                result["csrfToken"] = csrf_token
                try:
                    signup_user = result.get("user") or {}
                    if time_tracking:
                        time_tracking.clock_in(
                            signup_user.get("id"),
                            signup_user.get("name") or signup_user.get("email"),
                            signup_user.get("account_id"),
                        )
                except Exception:
                    pass
                resp = jsonify(result)
                _set_auth_cookies(resp, refresh_token, csrf_token, samesite, "auth")
                return resp, 201
            return jsonify({"error": error or "Signup failed"}), 400
        except ValueError as e:
            logger.error(f"Signup validation error: {str(e)}")
            return jsonify({"error": f"Invalid input: {str(e)}"}), 400
        except Exception as e:
            logger.error(f"Signup error: {str(e)}", exc_info=True)
            return jsonify({"error": "Signup failed. Please try again later."}), 500

    # ============================================================
    # Login
    # ============================================================

    @bp.route("/login", methods=["POST"])
    def login():
        is_limited, retry_after = _is_rate_limited(login_attempts, login_blocked_until, 900, 5)
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429
        data = request.get_json() or {}
        success, error, result = service.login(
            email=data.get("email"),
            password=data.get("password"),
        )
        if success:
            _reset_attempts(login_attempts, login_blocked_until)
            refresh_token = manager.create_refresh_session(
                user=result.get("user") or {},
                user_agent=request.headers.get("User-Agent", ""),
                ip_address=_client_ip(),
            )
            csrf_token = uuid.uuid4().hex
            result["refreshToken"] = refresh_token
            result["csrfToken"] = csrf_token
            try:
                login_user = result.get("user") or {}
                if time_tracking:
                    time_tracking.clock_in(
                        login_user.get("id"),
                        login_user.get("name") or login_user.get("email"),
                        login_user.get("account_id"),
                    )
            except Exception:
                pass
            resp = jsonify(result)
            _set_auth_cookies(resp, refresh_token, csrf_token, samesite, "auth")
            return resp, 200
        _record_attempt(login_attempts, login_blocked_until, 900, 5)
        return jsonify({"error": error or "Invalid credentials"}), 401

    # ============================================================
    # PIN Login
    # ============================================================

    @bp.route("/pin-login", methods=["POST"])
    def pin_login():
        is_limited, retry_after = _is_rate_limited(login_attempts, login_blocked_until, 900, 5)
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429
        data = request.get_json() or {}
        success, error, result = service.pin_login(
            email=data.get("email"),
            pin=data.get("pin"),
        )
        if success:
            _reset_attempts(login_attempts, login_blocked_until)
            refresh_token = manager.create_refresh_session(
                user=result.get("user") or {},
                user_agent=request.headers.get("User-Agent", ""),
                ip_address=_client_ip(),
            )
            csrf_token = uuid.uuid4().hex
            result["refreshToken"] = refresh_token
            result["csrfToken"] = csrf_token
            try:
                pin_user = result.get("user") or {}
                if time_tracking:
                    time_tracking.clock_in(
                        pin_user.get("id"),
                        pin_user.get("name") or pin_user.get("email"),
                        pin_user.get("account_id"),
                    )
            except Exception:
                pass
            resp = jsonify(result)
            _set_auth_cookies(resp, refresh_token, csrf_token, samesite, "auth")
            return resp, 200
        _record_attempt(login_attempts, login_blocked_until, 900, 5)
        return jsonify({"error": error or "Invalid credentials"}), 401

    # ============================================================
    # Refresh
    # ============================================================

    @bp.route("/refresh", methods=["POST"])
    def refresh_token():
        is_limited, retry_after = _is_rate_limited(refresh_attempts, login_blocked_until, 300, 30)
        if is_limited:
            return jsonify({"error": "Too many refresh attempts. Try again later.", "retry_after": retry_after}), 429
        data = request.get_json() or {}
        refresh = request.cookies.get("refresh_token")
        if not refresh:
            refresh = data.get("refreshToken")
        if not refresh:
            return jsonify({"error": "Refresh token required"}), 400
        rotated = manager.rotate_refresh_session(
            refresh_token=refresh,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_client_ip(),
        )
        if not rotated:
            return jsonify({"error": "Invalid or expired refresh token"}), 401
        csrf_token = uuid.uuid4().hex
        next_refresh = rotated.pop("refreshToken", None)
        rotated["csrfToken"] = csrf_token
        resp = jsonify(rotated)
        _set_auth_cookies(resp, next_refresh, csrf_token, samesite, "auth")
        return resp, 200

    # ============================================================
    # Logout
    # ============================================================

    @bp.route("/logout", methods=["POST"])
    def logout():
        is_limited, retry_after = _is_rate_limited(logout_attempts, login_blocked_until, 120, 60)
        if is_limited:
            return jsonify({"error": "Too many logout attempts. Try again later.", "retry_after": retry_after}), 429
        data = request.get_json() or {}
        refresh = request.cookies.get("refresh_token") or (data.get("refreshToken") if False else None)
        if refresh:
            manager.revoke_refresh_session(refresh)
        resp = jsonify({"success": True})
        _clear_auth_cookies(resp, samesite, "auth")
        return resp, 200

    # ============================================================
    # Me / Profile
    # ============================================================

    @bp.route("/me", methods=["GET"])
    @require_auth(manager, datastore)
    def auth_me():
        response_user = manager._build_user_payload(getattr(g, "user", {}) or {})
        return jsonify(response_user), 200

    # ============================================================
    # Change password / PIN
    # ============================================================

    @bp.route("/change-password", methods=["POST"])
    @require_auth(manager, datastore)
    def change_password():
        user = request.user
        data = request.get_json() or {}
        current_password = (data.get("currentPassword") or "").strip()
        new_password = (data.get("newPassword") or "").strip()
        new_pin = data.get("newPin")
        if not current_password:
            return jsonify({"error": "Current password is required"}), 400
        if not new_password and new_pin is None:
            return jsonify({"error": "New password or new PIN is required"}), 400
        if new_password and len(new_password) < 4:
            return jsonify({"error": "New password must be at least 4 characters"}), 400
        ok, msg = service.change_password(user, current_password, new_password, new_pin)
        if not ok:
            return jsonify({"error": msg}), 400
        return jsonify({"message": msg}), 200

    # ============================================================
    # Screen lock
    # ============================================================

    @bp.route("/lock-screen", methods=["POST"])
    @require_auth(manager, datastore)
    def lock_screen():
        user = request.user
        if not datastore:
            return jsonify({"error": "Database not available"}), 500
        datastore.update(
            "users", user.get("id"), {"screen_locked": True}, user.get("account_id")
        )
        updated_user = datastore.get_by_id("users", user.get("id"), user.get("account_id")) or user
        updated_user["screen_locked"] = True
        new_token = manager.generate_token(updated_user)
        return jsonify({"success": True, "token": new_token}), 200

    @bp.route("/unlock-screen", methods=["POST"])
    @require_auth(manager, datastore)
    def unlock_screen():
        _failed_key = f"screen_unlock_fails:{_client_ip()}"
        fails = cache.get_int(_failed_key) if cache else 0
        if fails and fails >= 5:
            return jsonify({"message": "Too many failed attempts. Try again later."}), 429
        data = request.get_json() or {}
        pin = (data.get("pin") or "").strip()
        if not pin:
            return jsonify({"message": "PIN is required"}), 400
        user = request.user
        account = datastore.get_by_id("accounts", user.get("account_id")) if datastore else None
        user_pin = (user.get("pin") or user.get("cashier_pin") or "").strip()
        account_pin = (account.get("screen_lock_password") or "2005") if account else "2005"
        if pin != user_pin and pin != account_pin:
            if cache and getattr(cache, "enabled", False):
                cache.set_int(_failed_key, (fails or 0) + 1, ttl_seconds=300)
            return jsonify({"message": "Incorrect PIN"}), 401
        if cache and getattr(cache, "enabled", False):
            cache.delete(_failed_key)
        if not datastore:
            return jsonify({"error": "Database not available"}), 500
        datastore.update(
            "users", user.get("id"), {"screen_locked": False}, user.get("account_id")
        )
        updated_user = datastore.get_by_id("users", user.get("id"), user.get("account_id")) or user
        updated_user["screen_locked"] = False
        new_token = manager.generate_token(updated_user)
        return jsonify({"success": True, "token": new_token}), 200

    return bp


def create_main_admin_auth_blueprint(
    manager: AuthManager,
    service: AuthService,
    datastore=None,
    cache=None,
    samesite: str = "Lax",
) -> Blueprint:
    bp = Blueprint("main_admin_auth", __name__)

    login_attempts: Dict[str, list] = {}
    login_blocked_until: Dict[str, float] = {}

    def _client_ip() -> str:
        return request.remote_addr or "unknown"

    def _is_rate_limited(window: int = 900, max_attempts: int = 5) -> Tuple[bool, int]:
        key = _client_ip()
        now = __import__("time").time()
        if cache and getattr(cache, "enabled", False):
            blocked_until = cache.get_int(f"rl:block:{key}")
            if blocked_until and blocked_until > cache.now_ts():
                return True, int(blocked_until - cache.now_ts())
            return False, 0
        blocked_until = login_blocked_until.get(key)
        if blocked_until and blocked_until > now:
            return True, int(blocked_until - now)
        return False, 0

    def _record_attempt(window: int = 900, max_attempts: int = 5):
        key = _client_ip()
        now = __import__("time").time()
        if cache and getattr(cache, "enabled", False):
            cache.incr_with_ttl(f"rl:fail:{key}", window)
            return
        arr = login_attempts.get(key, [])
        arr = [t for t in arr if now - t < window]
        arr.append(now)
        login_attempts[key] = arr
        if len(arr) >= max_attempts:
            login_blocked_until[key] = now + window

    def _reset_attempts():
        key = _client_ip()
        if cache and getattr(cache, "enabled", False):
            cache.delete(f"rl:fail:{key}")
            cache.delete(f"rl:block:{key}")
            return
        login_attempts.pop(key, None)
        login_blocked_until.pop(key, None)

    @bp.route("/auth/login", methods=["POST"])
    def main_admin_login():
        def _is_bcrypt_hash(value: str) -> bool:
            return value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")

        def _log_failed_main_admin_login(email_value: str, reason: str, status_code: int = 403):
            _record_attempt()
            return jsonify({"error": "Access denied"}), status_code

        is_limited, retry_after = _is_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        owner = None
        bootstrap_email = (
            os.environ.get("MAIN_ADMIN_EMAIL")
            or os.environ.get("ADMIN_EMAIL")
            or os.environ.get("DEV_ADMIN_EMAIL")
            or ""
        ).strip().lower()
        bootstrap_hash = (
            os.environ.get("MAIN_ADMIN_HASH")
            or os.environ.get("ADMIN_HASH")
            or os.environ.get("DEV_ADMIN_HASH")
            or ""
        ).strip()
        bootstrap_password = (
            os.environ.get("MAIN_ADMIN_PASSWORD")
            or os.environ.get("ADMIN_PASSWORD")
            or os.environ.get("DEV_ADMIN_PASSWORD")
            or ""
        ).strip()

        if bootstrap_email and (bootstrap_hash or bootstrap_password):
            if email == bootstrap_email:
                password_matches = False
                if bootstrap_hash and _is_bcrypt_hash(bootstrap_hash):
                    password_matches = manager.verify_password(password, bootstrap_hash)
                elif bootstrap_password:
                    import secrets
                    password_matches = secrets.compare_digest(password, bootstrap_password)
                if password_matches:
                    persisted_hash = bootstrap_hash if bootstrap_hash and _is_bcrypt_hash(bootstrap_hash) else manager.hash_password(bootstrap_password)
                    owner = service.ensure_main_admin(bootstrap_email, persisted_hash, "Main Admin")
                else:
                    return _log_failed_main_admin_login(email, "invalid_bootstrap_credentials")

        if not owner and datastore:
            owner = datastore.get_user_by_email(email)
            if not owner:
                return _log_failed_main_admin_login(email, "user_not_found", 403)
            if owner.get("role") not in {"main_admin", "owner"}:
                return _log_failed_main_admin_login(email, "role_not_allowed")
            if not owner.get("is_active", True) or owner.get("is_locked"):
                return _log_failed_main_admin_login(email, "account_blocked")
            password_hash = owner.get("password_hash", "")
            if not password_hash or not manager.verify_password(password, password_hash):
                return _log_failed_main_admin_login(email, "invalid_password")

        if not owner:
            return _log_failed_main_admin_login(email, "user_not_found", 403)

        now_iso = datetime.utcnow().isoformat()
        if owner.get("role") == "owner":
            if datastore:
                datastore.update("users", owner.get("id"), {
                    "role": "main_admin",
                    "business_role": "main_admin",
                    "business_type": "main_admin",
                }, owner.get("account_id"))
            owner = datastore.get_user_by_email(email) or owner if datastore else owner

        if datastore:
            datastore.update("users", owner.get("id"), {"last_login": now_iso}, owner.get("account_id"))
            datastore.update("accounts", owner.get("account_id"), {"last_activity_date": now_iso})
            owner = datastore.get_user_by_email(email) or owner

        token = manager.generate_token(owner)
        refresh_token = manager.create_refresh_session(
            user=owner,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_client_ip(),
        )
        csrf_token = uuid.uuid4().hex
        _reset_attempts()
        resp = jsonify({
            "user": manager._build_user_payload(owner),
            "token": token,
            "csrfToken": csrf_token,
        })
        _set_auth_cookies(resp, refresh_token, csrf_token, samesite, "main_admin")
        return resp, 200

    return bp
