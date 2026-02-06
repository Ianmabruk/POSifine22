"""
Main Flask Application
======================
Unified entrypoint for API endpoints.
"""

from __future__ import annotations

import os
import logging
import uuid
import json
import secrets
from datetime import datetime
import time
from typing import Dict, Any

from flask import Flask, jsonify, request, g
from flask_sock import Sock
from flask_cors import CORS

from database import DataStore
from stock_engine import StockEngine
from auth_controller import AuthController
from admin_controller import AdminController
from cashier_controller import CashierController
from sync_manager import sync_manager
from services.cache_service import CacheService
from services.session_store import SessionStore
from time_tracking_controller import TimeTrackingController
from reminders_controller import RemindersController
from credit_requests_controller import CreditRequestsController
from discounts_service_fees_controller import DiscountsController, ServiceFeesController
from business_routes import create_business_routes
from ai_controller import create_ai_routes
from ai_controller import create_ai_routes
from message_routes import message_bp

# Optional optimization imports - graceful fallback if not available
try:
    from database_optimizer import DatabaseOptimizer
    from cache_manager import CacheManager, SessionCache, cache_api_response
    from security_manager import SecurityManager, require_csrf, validate_json
    from monitoring import PerformanceMonitor, UserAnalytics, ErrorTracker
    OPTIMIZATIONS_AVAILABLE = True
except ImportError:
    OPTIMIZATIONS_AVAILABLE = False
    print("Optimization modules not available - running in basic mode")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)
    sock = Sock(app)

    # Config
    app.config["SECRET_KEY"] = os.environ.get(
        "JWT_SECRET",
        os.environ.get("SECRET_KEY", "dev-secret-change-me")
    )
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    app.config["PREFERRED_URL_SCHEME"] = "https"

    # CORS
    cors_origins = os.environ.get("CORS_ORIGINS", "*")
    if cors_origins == "*":
        CORS(app, supports_credentials=True)
    else:
        allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
        # Always allow Netlify production frontend if not explicitly set
        if "https://posifine11.netlify.app" not in allowed_origins:
            allowed_origins.append("https://posifine11.netlify.app")
        CORS(
            app,
            resources={r"/*": {"origins": allowed_origins}},
            supports_credentials=True,
            allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
            methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
        )

    # Global preflight handler
    @app.before_request
    def _handle_preflight():
        if request.method == "OPTIONS":
            return ("", 200)

    # Global preflight handler (avoid non-OK preflight responses)
    @app.before_request
    def handle_options_preflight():
        if request.method == "OPTIONS":
            return ("", 200)

    # Services
    use_postgres = bool(os.environ.get("DATABASE_URL"))
    datastore = DataStore(data_dir=os.environ.get("DATA_DIR"), use_postgres=use_postgres)
    stock_engine = StockEngine(datastore)
    session_store = SessionStore()
    auth_controller = AuthController(datastore, app.config["SECRET_KEY"], session_store=session_store)
    admin_controller = AdminController(datastore, stock_engine)
    cashier_controller = CashierController(datastore, stock_engine)
    cache = CacheService()
    
    # 🔥 NEW COMPREHENSIVE CONTROLLERS
    time_tracking = TimeTrackingController(datastore)
    reminders = RemindersController(datastore)
    credit_requests = CreditRequestsController(datastore)
    discounts = DiscountsController(datastore)
    service_fees = ServiceFeesController(datastore)
    
    # Optional optimization services
    if OPTIMIZATIONS_AVAILABLE:
        db_optimizer = DatabaseOptimizer(datastore)
        cache_manager = CacheManager(os.environ.get("REDIS_URL"))
        session_cache = SessionCache(cache_manager)
        security_manager = SecurityManager()
        performance_monitor = PerformanceMonitor()
        user_analytics = UserAnalytics()
        error_tracker = ErrorTracker()
        db_optimizer.add_indexes()
    else:
        # Fallback objects
        security_manager = type('SecurityManager', (), {
            'rate_limit': lambda *args, **kwargs: lambda f: f,
            'validate_csrf_token': lambda *args: True
        })()
        cache_manager = type('CacheManager', (), {
            'get': lambda *args: None,
            'set': lambda *args: None
        })()

    # Helper function for optional decorators
    def optional_decorator(decorator_func, *args, **kwargs):
        if OPTIMIZATIONS_AVAILABLE:
            return decorator_func(*args, **kwargs)
        return lambda f: f
    
    def optional_cache_decorator(cache_manager, ttl=30):
        if OPTIMIZATIONS_AVAILABLE:
            return cache_api_response(cache_manager, ttl)
        return lambda f: f

    # Register business management routes
    business_bp = create_business_routes(datastore, auth_controller)
    app.register_blueprint(business_bp, url_prefix="/api/business")
    app.register_blueprint(message_bp)

    # AI routes
    ai_bp = create_ai_routes(datastore, auth_controller.require_auth)
    app.register_blueprint(ai_bp)

    # Register AI routes
    ai_bp = create_ai_routes(datastore, auth_controller.require_auth)
    app.register_blueprint(ai_bp)

    # Simple in-memory rate limiting for auth endpoints
    login_attempts = {}
    login_blocked_until = {}

    def _rate_limit_key():
        return request.headers.get("X-Forwarded-For", request.remote_addr) or "unknown"

    def _is_rate_limited():
        key = _rate_limit_key()
        if cache.enabled:
            blocked_until = cache.get_int(f"rl:block:{key}")
            if blocked_until and blocked_until > cache.now_ts():
                return True, int(blocked_until - cache.now_ts())
            return False, 0

        blocked_until = login_blocked_until.get(key)
        if blocked_until and blocked_until > time.time():
            return True, int(blocked_until - time.time())
        return False, 0

    def _record_failed_login():
        key = _rate_limit_key()
        if cache.enabled:
            attempts = cache.incr_with_ttl(f"rl:fail:{key}", 900)
            if attempts >= 5:
                cache.set_int(f"rl:block:{key}", cache.now_ts() + 900, 900)
            return

        now = time.time()
        attempts = login_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < 900]
        attempts.append(now)
        login_attempts[key] = attempts
        if len(attempts) >= 5:
            login_blocked_until[key] = now + 900

    def _reset_login_attempts():
        key = _rate_limit_key()
        if cache.enabled:
            cache.delete(f"rl:fail:{key}")
            cache.delete(f"rl:block:{key}")
            return

        login_attempts.pop(key, None)
        login_blocked_until.pop(key, None)

    def _log_activity(action: str, account_id: str | None, user_id: int | None, metadata: Dict[str, Any] | None = None):
        try:
            datastore.create("activity_logs", {
                "account_id": account_id,
                "user_id": user_id,
                "action": action,
                "resource": request.path,
                "metadata": metadata or {},
                "ip_address": _rate_limit_key(),
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception:
            pass

    def _log_audit(action: str, actor: Dict[str, Any] | None, target: str, metadata: Dict[str, Any] | None = None):
        try:
            datastore.create("audit_logs", {
                "account_id": actor.get("account_id") if actor else None,
                "actor_id": actor.get("id") if actor else None,
                "actor_role": actor.get("role") if actor else None,
                "action": action,
                "target": target,
                "metadata": metadata or {},
                "ip_address": _rate_limit_key(),
                "created_at": datetime.utcnow().isoformat()
            })
        except Exception:
            pass

    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    def _apply_fields(items, fields_param: str | None):
        if not fields_param:
            return items
        fields = [f.strip() for f in fields_param.split(",") if f.strip()]
        if not fields:
            return items
        return [{k: item.get(k) for k in fields if k in item} for item in items]

    def _apply_limit(items, limit_param: str | None):
        if not limit_param:
            return items
        try:
            limit = int(limit_param)
        except (TypeError, ValueError):
            return items
        if limit <= 0:
            return []
        return items[:limit]

    def _apply_sort(items, sort_param: str | None):
        if not sort_param:
            return items
        reverse = sort_param.startswith("-")
        key = sort_param[1:] if reverse else sort_param
        return sorted(items, key=lambda x: x.get(key) or "", reverse=reverse)

    # ============================================================
    # Health
    # ============================================================

    @app.before_request
    def start_timer():
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            if request.path.startswith("/api/auth") or request.path.startswith("/api/main-admin/auth"):
                pass
            else:
                csrf_cookie = request.cookies.get("csrf_token")
                csrf_header = request.headers.get("X-CSRF-Token")
                if csrf_cookie and csrf_header != csrf_cookie:
                    return jsonify({"error": "Invalid CSRF token"}), 403
        if os.environ.get("ENFORCE_HTTPS") == "1":
            proto = request.headers.get("X-Forwarded-Proto", request.scheme)
            if proto != "https":
                url = request.url.replace("http://", "https://", 1)
                return jsonify({"error": "HTTPS required", "redirect": url}), 403
        request._start_time = time.time()
        request._request_id = uuid.uuid4().hex

    @app.after_request
    def add_timing_headers(response):
        start_time = getattr(request, "_start_time", None)
        request_id = getattr(request, "_request_id", None)
        if start_time is not None:
            duration_ms = (time.time() - start_time) * 1000
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"
            if request_id:
                response.headers["X-Request-Id"] = request_id
            if duration_ms > 800:
                logger.warning("Slow request: %s %s took %.2fms", request.method, request.path, duration_ms)

            account_id = None
            try:
                account_id = getattr(request, "user", {}).get("account_id")
            except Exception:
                account_id = None

            logger.info(
                "REQ %s",
                json.dumps({
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "account_id": account_id
                })
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response

    @app.get("/health")
    def health_check():
        return jsonify({
            "status": "ok",
            "services": {
                "database": "postgres" if datastore.use_postgres else "json"
            },
            "timestamp": datetime.utcnow().isoformat()
        }), 200

    # ============================================================
    # Auth
    # ============================================================

    @app.post("/api/auth/signup")
    def signup():
        data = request.get_json() or {}
        success, error, result = auth_controller.signup(
            email=data.get("email"),
            password=data.get("password"),
            name=data.get("name"),
            plan=data.get("plan", "free"),
            business_type=data.get("business_type")
        )
        if success:
            refresh_token = auth_controller.create_refresh_session(
                user=result.get("user") or {},
                user_agent=request.headers.get("User-Agent", ""),
                ip_address=_rate_limit_key()
            )
            csrf_token = uuid.uuid4().hex
            result["refreshToken"] = refresh_token
            result["csrfToken"] = csrf_token
            resp = jsonify(result)
            resp.set_cookie("csrf_token", csrf_token, secure=True, httponly=False, samesite="Strict")
            return resp, 201
        return jsonify({"error": error or "Signup failed"}), 400

    @app.post("/api/auth/login")
    def login():
        is_limited, retry_after = _is_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        success, error, result = auth_controller.login(
            email=data.get("email"),
            password=data.get("password")
        )
        if success:
            _reset_login_attempts()
            refresh_token = auth_controller.create_refresh_session(
                user=result.get("user") or {},
                user_agent=request.headers.get("User-Agent", ""),
                ip_address=_rate_limit_key()
            )
            csrf_token = uuid.uuid4().hex
            result["refreshToken"] = refresh_token
            result["csrfToken"] = csrf_token
            _log_activity("login", result.get("user", {}).get("account_id"), result.get("user", {}).get("id"))
            resp = jsonify(result)
            resp.set_cookie("csrf_token", csrf_token, secure=True, httponly=False, samesite="Strict")
            return resp, 200
        _record_failed_login()
        return jsonify({"error": error or "Invalid credentials"}), 401

    @app.post("/api/auth/refresh")
    def refresh_token():
        data = request.get_json() or {}
        refresh = data.get("refreshToken")
        if not refresh:
            return jsonify({"error": "Refresh token required"}), 400

        rotated = auth_controller.rotate_refresh_session(
            refresh_token=refresh,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_rate_limit_key()
        )
        if not rotated:
            return jsonify({"error": "Invalid or expired refresh token"}), 401

        _log_activity("refresh_token", rotated.get("user", {}).get("account_id"), rotated.get("user", {}).get("id"))
        csrf_token = uuid.uuid4().hex
        rotated["csrfToken"] = csrf_token
        resp = jsonify(rotated)
        resp.set_cookie("csrf_token", csrf_token, secure=True, httponly=False, samesite="Strict")
        return resp, 200

    @app.post("/api/auth/logout")
    def logout():
        data = request.get_json() or {}
        refresh = data.get("refreshToken")
        if refresh:
            auth_controller.revoke_refresh_session(refresh)
        _log_activity("logout", None, None)
        return jsonify({"success": True}), 200

    @app.get("/api/auth/me")
    @auth_controller.require_auth
    def auth_me():
        user = getattr(request, "user", None)
        account_id = user.get("account_id") if user else None
        account = datastore.get_by_id("accounts", account_id) if account_id else None

        response_user = dict(g.user) if hasattr(g, "user") else dict(user or {})
        response_user.pop("password_hash", None)

        if account:
            response_user["plan"] = account.get("plan")
            response_user["subscription"] = account.get("plan")
            response_user["active"] = bool(account.get("is_active", True))
            response_user["account_active"] = bool(account.get("is_active", True))

        if "active" not in response_user:
            response_user["active"] = bool(response_user.get("is_active", True))

        return jsonify(response_user), 200

    # ============================================================
    # Main Admin (Owner)
    # ============================================================

    def _require_main_admin():
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return None, (jsonify({"error": "Authorization token required"}), 401)

        payload = auth_controller.verify_token(token)
        if not payload:
            return None, (jsonify({"error": "Invalid or expired token"}), 401)

        user = datastore.get_by_id("users", payload.get("user_id"), payload.get("account_id"))
        if not user:
            return None, (jsonify({"error": "User not found"}), 401)

        if user.get("role") != "main_admin":
            return None, (jsonify({"error": "Access denied"}), 403)

        return user, None

    @app.post("/api/main-admin/auth/login")
    def main_admin_login():
        is_limited, retry_after = _is_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        owner_email = os.environ.get("MAIN_ADMIN_EMAIL", "").strip().lower()
        owner_hash = os.environ.get("MAIN_ADMIN_HASH", "").strip()
        owner_password = os.environ.get("MAIN_ADMIN_PASSWORD", "").strip()
        if not owner_email or (not owner_hash and not owner_password):
            return jsonify({"error": "Main admin credentials not configured"}), 500

        def _is_bcrypt_hash(value: str) -> bool:
            return value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")

        def _password_valid(candidate: str) -> bool:
            if owner_hash:
                if _is_bcrypt_hash(owner_hash):
                    return auth_controller.verify_password(candidate, owner_hash)
                if not owner_password:
                    return secrets.compare_digest(candidate, owner_hash)
            if owner_password:
                return secrets.compare_digest(candidate, owner_password)
            return False

        if email != owner_email or not _password_valid(password):
            _record_failed_login()
            return jsonify({"error": "Access denied"}), 403

        owner = datastore.get_user_by_email(email)
        if not owner:
            account = datastore.get_account_by_email(owner_email)
            if not account:
                account_id = f"acc_{uuid.uuid4().hex[:12]}"
                account = {
                    "id": account_id,
                    "owner_email": owner_email,
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
                    "business_type": "main_admin"
                }
                datastore.create("accounts", account)
            account_id = account.get("id")

            if owner_hash and _is_bcrypt_hash(owner_hash):
                password_hash = owner_hash
            else:
                password_hash = auth_controller.hash_password(owner_password or owner_hash)

            owner = datastore.create("users", {
                "account_id": account_id,
                "email": owner_email,
                "password_hash": password_hash,
                "name": "Main Admin",
                "role": "main_admin",
                "pin": None,
                "cashier_pin": None,
                "is_active": True,
                "is_locked": False,
                "screen_locked": False,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": None,
                "last_login": None,
                "hourly_rate": 0.0,
                "business_type": "main_admin",
                "business_role": "main_admin"
            })
        elif owner.get("role") != "main_admin":
            datastore.update("users", owner.get("id"), {"role": "main_admin", "business_role": "main_admin"}, owner.get("account_id"))
            owner = datastore.get_user_by_email(email)

        token = auth_controller.generate_token(owner)
        refresh_token = auth_controller.create_refresh_session(
            user=owner,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_rate_limit_key()
        )
        csrf_token = uuid.uuid4().hex
        _reset_login_attempts()
        _log_activity("main_admin_login", owner.get("account_id"), owner.get("id"))
        resp = jsonify({
            "user": auth_controller._build_user_payload(owner),
            "token": token,
            "refreshToken": refresh_token,
            "csrfToken": csrf_token
        })
        resp.set_cookie("csrf_token", csrf_token, secure=True, httponly=False, samesite="Strict")
        return resp, 200

    @app.get("/api/main-admin/users")
    def main_admin_users():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        all_users = datastore.get_all("users")
        accounts = {acc.get("id"): acc for acc in datastore.get_all("accounts")}

        response = []
        for u in all_users:
            sanitized = dict(u)
            sanitized.pop("password_hash", None)
            account = accounts.get(u.get("account_id"))
            if account:
                sanitized["plan"] = account.get("plan")
                sanitized["subscription"] = account.get("plan")
                sanitized["active"] = bool(account.get("is_active", True))
                sanitized["account_active"] = bool(account.get("is_active", True))
                if account.get("business_type") and not sanitized.get("business_type"):
                    sanitized["business_type"] = account.get("business_type")
                if account.get("business_name") and not sanitized.get("business_name"):
                    sanitized["business_name"] = account.get("business_name")
            response.append(sanitized)

        return jsonify(response), 200

    @app.post("/api/main-admin/users")
    def main_admin_create_user():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        success, error, result = auth_controller.signup(
            email=data.get("email"),
            password=data.get("password"),
            name=data.get("name"),
            plan=data.get("plan", "free"),
            business_type=data.get("business_type")
        )
        if success:
            return jsonify(result), 201
        return jsonify({"error": error or "Failed to create user"}), 400

    @app.post("/api/main-admin/users/<int:user_id>/lock")
    def main_admin_lock_user(user_id: int):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        locked = bool(data.get("locked", False))

        target = datastore.get_by_id("users", user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        account_id = target.get("account_id")
        if account_id:
            datastore.update("accounts", account_id, {
                "is_locked": locked,
                "is_active": not locked
            })

            # Update all users in the account
            all_users = datastore.get_all("users")
            for acct_user in all_users:
                if acct_user.get("account_id") == account_id:
                    datastore.update("users", acct_user.get("id"), {
                        "is_locked": locked,
                        "is_active": not locked
                    }, account_id)

        _log_audit("account_lock" if locked else "account_unlock", user, f"user:{user_id}", {
            "locked": locked
        })

        return jsonify({"message": "User lock status updated"}), 200

    @app.post("/api/main-admin/users/<int:user_id>/plan")
    def main_admin_change_plan(user_id: int):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        plan = data.get("plan")
        if not plan:
            return jsonify({"error": "Plan is required"}), 400

        target = datastore.get_by_id("users", user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        account_id = target.get("account_id")
        if account_id:
            datastore.update("accounts", account_id, {
                "plan": plan,
                "is_active": True
            })

            profiles = datastore.get_by_field("business_profiles", "account_id", account_id)
            for profile in profiles:
                datastore.update("business_profiles", profile.get("id"), {"plan": plan}, account_id)

        _log_audit("plan_change", user, f"user:{user_id}", {
            "plan": plan
        })

        return jsonify({"message": "Plan updated", "plan": plan}), 200

    @app.post("/api/main-admin/users/<int:user_id>/reset-password")
    def main_admin_reset_password(user_id: int):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        temp_password = (data.get("temp_password") or data.get("password") or "").strip()
        if not temp_password:
            temp_password = uuid.uuid4().hex[:8]

        target = datastore.get_by_id("users", user_id)
        if not target:
            return jsonify({"error": "User not found"}), 404

        hashed = auth_controller.hash_password(temp_password)
        account_id = target.get("account_id")
        updated = datastore.update("users", user_id, {"password_hash": hashed}, account_id)
        if not updated:
            return jsonify({"error": "Failed to reset password"}), 400

        _log_audit("reset_password", user, f"user:{user_id}", {})

        return jsonify({"message": "Password reset", "tempPassword": temp_password}), 200

    @app.get("/api/main-admin/activities")
    def main_admin_activities():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        activities = datastore.get_all("activity_logs")
        activities = sorted(activities, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(activities[:500]), 200

    @app.get("/api/main-admin/audit-logs")
    def main_admin_audit_logs():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        logs = datastore.get_all("audit_logs")
        logs = sorted(logs, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(logs[:500]), 200

    @app.get("/api/main-admin/sessions")
    def main_admin_sessions():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        sessions = datastore.get_all("sessions")
        sessions = sorted(sessions, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(sessions[:500]), 200

    @app.post("/api/main-admin/sessions/<int:session_id>/revoke")
    def main_admin_revoke_session(session_id: int):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        updated = datastore.update("sessions", session_id, {"revoked_at": datetime.utcnow().isoformat()})
        if not updated:
            return jsonify({"error": "Session not found"}), 404

        _log_audit("revoke_session", user, f"session:{session_id}", {})
        return jsonify({"message": "Session revoked"}), 200

    @app.get("/api/main-admin/stats")
    def main_admin_stats():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        all_users = datastore.get_all("users")
        accounts = datastore.get_all("accounts")
        sales = datastore.get_all("sales")

        total_users = len(all_users)
        active_users = len([u for u in all_users if u.get("is_active", True) and not u.get("is_locked")])
        locked_users = len([u for u in all_users if u.get("is_locked")])
        total_revenue = sum(_safe_float(sale.get("total")) for sale in sales)

        return jsonify({
            "totalUsers": total_users,
            "activeUsers": active_users,
            "lockedUsers": locked_users,
            "totalRevenue": total_revenue,
            "pendingPayments": 0,
            "overduePayments": 0
        }), 200

    @app.get("/api/main-admin/sales-all")
    def main_admin_sales_all():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        return jsonify(datastore.get_all("sales")), 200

    @app.post("/api/main-admin/send-email")
    def main_admin_send_email():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        return jsonify({"success": True}), 200

    # ============================================================
    # Settings
    # ============================================================

    @app.get("/api/settings")
    @auth_controller.require_auth
    def get_settings():
        account_id = request.user.get("account_id")
        profiles = datastore.get_by_field("business_profiles", "account_id", account_id)
        if profiles:
            return jsonify(profiles[0].get("settings") or {}), 200
        return jsonify({}), 200

    @app.put("/api/settings")
    @auth_controller.require_auth
    def update_settings():
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        profiles = datastore.get_by_field("business_profiles", "account_id", account_id)
        now = datetime.utcnow().isoformat()

        if profiles:
            profile = profiles[0]
            merged = {**(profile.get("settings") or {}), **data}
            datastore.update("business_profiles", profile.get("id"), {
                "settings": merged,
                "updated_at": now
            }, account_id)
            return jsonify(merged), 200

        profile = {
            "account_id": account_id,
            "business_type": (g.account or {}).get("business_type") or "general",
            "plan": (g.account or {}).get("plan") or "basic",
            "created_at": now,
            "settings": data
        }
        created = datastore.create("business_profiles", profile)
        return jsonify(created.get("settings") or {}), 200

    # ============================================================
    # Products
    # ============================================================

    @app.get("/api/products")
    @auth_controller.require_auth
    def get_products():
        account_id = request.user.get("account_id")
        has_query = bool(request.args)
        cache_key = f"cache:products:{account_id}"
        if cache.enabled and not has_query:
            cached = cache.get_json(cache_key)
            if cached is not None:
                return jsonify(cached), 200

        products = admin_controller.get_products(account_id)
        if cache.enabled and not has_query:
            cache.set_json(cache_key, products, ttl_seconds=15)
        products = _apply_sort(products, request.args.get("sort"))
        products = _apply_limit(products, request.args.get("limit"))
        products = _apply_fields(products, request.args.get("fields"))
        return jsonify(products), 200

    @app.post("/api/products")
    @auth_controller.require_auth
    def create_product():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")

        allowed_fields = {
            "barcode",
            "sku",
            "image",
            "reorder_level",
            "max_stock_level",
            "cost_per_unit",
            "enable_weight_pricing",
            "product_type"
        }

        extra_fields = {k: data.get(k) for k in allowed_fields if k in data}
        if "enable_weight_pricing" in extra_fields:
            extra_fields["enable_weight_pricing"] = bool(extra_fields.get("enable_weight_pricing"))
        for float_field in ("reorder_level", "max_stock_level", "cost_per_unit"):
            if float_field in extra_fields:
                extra_fields[float_field] = _safe_float(extra_fields.get(float_field))

        success, error, product = admin_controller.create_product(
            account_id=account_id,
            created_by=created_by,
            name=data.get("name"),
            price=data.get("price", 0),
            cost=data.get("cost", 0),
            quantity=data.get("quantity", 0),
            category=data.get("category", "general"),
            unit=data.get("unit", "pcs"),
            is_composite=bool(data.get("is_composite") or data.get("isComposite", False)),
            recipe=data.get("recipe"),
            **extra_fields
        )

        if not success:
            return jsonify({"error": error or "Failed to create product"}), 400
        sync_manager.broadcast_product_update(account_id, product, action='created')
        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
        return jsonify(product), 201

    @app.put("/api/products/<int:product_id>")
    @auth_controller.require_auth
    def update_product(product_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")

        allowed_fields = {
            "name",
            "price",
            "cost",
            "quantity",
            "category",
            "unit",
            "is_composite",
            "recipe",
            "product_type",
            "barcode",
            "sku",
            "image",
            "reorder_level",
            "max_stock_level",
            "cost_per_unit",
            "enable_weight_pricing"
        }

        updates = {k: data.get(k) for k in allowed_fields if k in data}
        if "is_composite" not in updates and "isComposite" in data:
            updates["is_composite"] = bool(data.get("isComposite"))
        if "enable_weight_pricing" in updates:
            updates["enable_weight_pricing"] = bool(updates.get("enable_weight_pricing"))

        for float_field in ("price", "cost", "quantity", "reorder_level", "max_stock_level", "cost_per_unit"):
            if float_field in updates:
                updates[float_field] = _safe_float(updates.get(float_field))

        success, error, product = admin_controller.update_product(
            product_id=product_id,
            account_id=account_id,
            **updates
        )

        if not success:
            return jsonify({"error": error or "Failed to update product"}), 400
        sync_manager.broadcast_product_update(account_id, product, action='updated')
        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
        return jsonify(product), 200

    @app.put("/api/products/<int:product_id>/stock")
    @auth_controller.require_auth
    def update_product_stock(product_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        quantity = _safe_float(data.get("quantity"))

        success, error = admin_controller.update_stock(product_id, account_id, quantity)
        if not success:
            return jsonify({"error": error or "Failed to update stock"}), 400
        product = datastore.get_by_id("products", product_id, account_id)
        sync_manager.broadcast_stock_update(account_id, product_id, product.get("quantity") if product else 0)
        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
        return jsonify(product), 200

    @app.get("/api/products/low-stock-warnings")
    @auth_controller.require_auth
    def get_low_stock_warnings():
        account_id = request.user.get("account_id")
        products = datastore.get_all("products", account_id)
        warnings = []
        for product in products:
            threshold = _safe_float(product.get("reorder_level") or 0)
            if threshold > 0 and _safe_float(product.get("quantity")) <= threshold:
                warnings.append(product)
        return jsonify(warnings), 200

    # ============================================================
    # Batches (Stock Additions)
    # ============================================================

    @app.get("/api/batches")
    @auth_controller.require_auth
    def get_batches():
        account_id = request.user.get("account_id")
        product_id = request.args.get("productId")
        batches = datastore.get_all("batches", account_id)
        if product_id is not None:
            try:
                product_id_int = int(product_id)
            except ValueError:
                return jsonify({"error": "Invalid productId"}), 400
            batches = [b for b in batches if int(b.get("productId")) == product_id_int]
        return jsonify(batches), 200

    @app.post("/api/batches")
    @auth_controller.require_auth
    def create_batch():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        product_id = data.get("productId")
        quantity = _safe_float(data.get("quantity"))
        if not product_id or quantity <= 0:
            return jsonify({"error": "productId and positive quantity are required"}), 400

        product = datastore.get_by_id("products", int(product_id), account_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404

        batch = {
            "account_id": account_id,
            "productId": int(product_id),
            "quantity": quantity,
            "expiryDate": data.get("expiryDate"),
            "batchNumber": data.get("batchNumber") or f"BATCH-{uuid.uuid4().hex[:8]}",
            "cost": _safe_float(data.get("cost")),
            "created_at": datetime.utcnow().isoformat()
        }

        created_batch = datastore.create("batches", batch)

        new_quantity = _safe_float(product.get("quantity")) + quantity
        datastore.update("products", int(product_id), {
            "quantity": new_quantity,
            "updated_at": datetime.utcnow().isoformat()
        }, account_id)

        updated_product = datastore.get_by_id("products", int(product_id), account_id)
        sync_manager.broadcast_stock_update(account_id, int(product_id), updated_product.get("quantity") if updated_product else new_quantity)
        if updated_product:
            sync_manager.broadcast_product_update(account_id, updated_product, action='updated')

        return jsonify(created_batch), 201

    # ============================================================
    # Sales
    # ============================================================

    @app.get("/api/sales")
    @auth_controller.require_auth
    def get_sales():
        account_id = request.user.get("account_id")
        sales = admin_controller.get_sales(account_id)
        sales = _apply_sort(sales, request.args.get("sort") or "-created_at")
        sales = _apply_limit(sales, request.args.get("limit"))
        sales = _apply_fields(sales, request.args.get("fields"))
        return jsonify(sales), 200

    @app.get("/api/stats")
    @auth_controller.require_auth
    def get_stats():
        account_id = request.user.get("account_id")
        cashier_id = request.args.get("cashierId")
        cache_key = f"cache:stats:{account_id}:{cashier_id or 'all'}"
        cached = cache.get_json(cache_key) if cache.enabled else None
        if cached is not None:
            response = jsonify(cached)
            response.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=30"
            response.headers["X-Cache"] = "HIT"
            return response, 200

        products = datastore.get_all("products", account_id)
        sales = datastore.get_all("sales", account_id)
        expenses = datastore.get_all("expenses", account_id)

        if cashier_id:
            try:
                cashier_id_int = int(cashier_id)
                sales = [s for s in sales if s.get("cashier_id") == cashier_id_int or s.get("cashierId") == cashier_id_int]
                expenses = [e for e in expenses if e.get("cashier_id") == cashier_id_int or e.get("cashierId") == cashier_id_int]
            except (TypeError, ValueError):
                pass

        cashier_id_param = request.args.get("cashierId") or request.args.get("cashier_id")
        cashier_id = None
        if cashier_id_param:
            try:
                cashier_id = int(cashier_id_param)
            except (TypeError, ValueError):
                cashier_id = None

        # If cashier is requesting stats, default to their own ID
        if request.user.get("role") == "cashier" and cashier_id is None:
            cashier_id = request.user.get("id")

        if cashier_id is not None:
            sales = [s for s in sales if int(s.get("cashier_id") or s.get("cashierId") or 0) == cashier_id]
            expenses = [e for e in expenses if int(e.get("cashier_id") or e.get("cashierId") or 0) == cashier_id]

        total_sales = sum(_safe_float(s.get("total")) for s in sales)
        total_expenses = sum(_safe_float(e.get("amount")) for e in expenses)
        total_cogs = sum(_safe_float(s.get("total_cost")) for s in sales)

        # Cashier monitor uses sales - expenses, admin uses full cost model
        if cashier_id is not None:
            profit = total_sales - total_expenses
        else:
            profit = total_sales - total_cogs - total_expenses

        response = {
            "totalSales": total_sales,
            "totalExpenses": total_expenses,
            "totalCOGS": total_cogs,
            "grossProfit": total_sales - total_cogs,
            "profit": profit,
            "productsCount": len(products),
            "salesCount": len(sales)
        }

        if cache.enabled:
            cache.set_json(cache_key, response, ttl_seconds=10)

        response_payload = jsonify(response)
        response_payload.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=30"
        response_payload.headers["X-Cache"] = "MISS"
        return response_payload, 200

    @app.get("/api/v2/monitor/stats")
    @auth_controller.require_auth
    def get_monitor_stats_v2():
        account_id = request.user.get("account_id")
        today = datetime.utcnow().date()
        cache_key = f"cache:monitor_stats:{account_id}:{today.isoformat()}"
        cached = cache.get_json(cache_key) if cache.enabled else None
        if cached is not None:
            response = jsonify(cached)
            response.headers["Cache-Control"] = "private, max-age=5, stale-while-revalidate=30"
            response.headers["X-Cache"] = "HIT"
            return response, 200

        sales = datastore.get_all("sales", account_id)
        expenses = datastore.get_all("expenses", account_id)

        def _is_today(item):
            value = item.get("created_at") or item.get("createdAt")
            if not value:
                return False
            try:
                if isinstance(value, (int, float)):
                    return datetime.utcfromtimestamp(value).date() == today
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                return parsed.date() == today
            except Exception:
                return False

        today_sales = [s for s in sales if _is_today(s)]
        today_expenses = [e for e in expenses if _is_today(e)]

        total_sales = sum(_safe_float(s.get("total")) for s in today_sales)
        total_expenses = sum(_safe_float(e.get("amount")) for e in today_expenses)
        transaction_count = len(today_sales)
        avg_transaction = (total_sales / transaction_count) if transaction_count else 0

        response_data = {
            "totalSales": total_sales,
            "totalExpenses": total_expenses,
            "netProfit": total_sales - total_expenses,
            "transactionCount": transaction_count,
            "avgTransaction": avg_transaction,
            "timestamp": datetime.utcnow().isoformat()
        }

        if cache.enabled:
            cache.set_json(cache_key, response_data, ttl_seconds=5)

        response_payload = jsonify(response_data)
        response_payload.headers["Cache-Control"] = "private, max-age=5, stale-while-revalidate=30"
        response_payload.headers["X-Cache"] = "MISS"
        return response_payload, 200

    # ============================================================
    # Expenses
    # ============================================================

    @app.get("/api/expenses")
    @auth_controller.require_auth
    def get_expenses():
        account_id = request.user.get("account_id")
        expenses = datastore.get_all("expenses", account_id)
        expenses = _apply_sort(expenses, request.args.get("sort") or "-created_at")
        expenses = _apply_limit(expenses, request.args.get("limit"))
        return jsonify(expenses), 200

    @app.post("/api/expenses")
    @auth_controller.require_auth
    def create_expense():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        cashier_id = request.user.get("id")
        cashier_name = request.user.get("email")

        amount = _safe_float(data.get("amount"))
        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400

        expense = {
            "account_id": account_id,
            "name": data.get("name") or data.get("description") or "Expense",
            "description": data.get("description") or data.get("name") or "",
            "amount": amount,
            "category": data.get("category") or "general",
            "cashier_id": cashier_id,
            "cashier_name": cashier_name,
            "created_at": datetime.utcnow().isoformat()
        }

        created = datastore.create("expenses", expense)
        sync_manager.broadcast_expense_created(account_id, created)
        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
            cache.delete(f"cache:stats:{account_id}:{cashier_id}")
        return jsonify(created), 201

    @app.put("/api/expenses/<int:expense_id>")
    @auth_controller.require_auth
    def update_expense(expense_id: int):
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        data["updated_at"] = datetime.utcnow().isoformat()
        if "amount" in data:
            data["amount"] = _safe_float(data.get("amount"))

        ok = datastore.update("expenses", expense_id, data, account_id)
        if not ok:
            return jsonify({"error": "Expense not found"}), 404
        updated = datastore.get_by_id("expenses", expense_id, account_id)
        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
        return jsonify(updated), 200

    @app.delete("/api/expenses/<int:expense_id>")
    @auth_controller.require_auth
    def delete_expense(expense_id: int):
        account_id = request.user.get("account_id")
        ok = datastore.delete("expenses", expense_id, account_id)
        if not ok:
            return jsonify({"error": "Expense not found"}), 404
        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
        return jsonify({"success": True}), 200

    @app.post("/api/sales")
    @auth_controller.require_auth
    def complete_sale():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        cashier_id = request.user.get("id")
        cashier_name = request.user.get("email")

        success, error, sale = cashier_controller.complete_sale(
            account_id=account_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            items=data.get("items", []),
            payment_method=data.get("payment_method") or data.get("paymentMethod", "cash"),
            amount_paid=data.get("amount_paid") if "amount_paid" in data else data.get("amountPaid", 0),
            tax_rate=data.get("tax_rate") if "tax_rate" in data else data.get("taxRate", 0),
            discount_amount=data.get("discount_amount") if "discount_amount" in data else data.get("discount", 0),
            service_fee=data.get("service_fee") if "service_fee" in data else data.get("serviceFee", 0)
        )

        if not success:
            return jsonify({"error": error or "Failed to complete sale"}), 400
        sync_manager.broadcast_sale_completed(account_id, sale)

        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
            cache.delete(f"cache:stats:{account_id}:{cashier_id}")
            cache.delete(f"cache:products:{account_id}")

        for item in data.get("items", []):
            product_id = item.get("product_id") or item.get("productId")
            if not product_id:
                continue
            product = datastore.get_by_id("products", product_id, account_id)
            if product:
                sync_manager.broadcast_stock_update(account_id, product_id, product.get("quantity"))
        return jsonify({"sale": sale}), 201

    # ============================================================
    # Sales (V2 Atomic)
    # ============================================================

    @app.post("/api/v2/sales/complete")
    @auth_controller.require_auth
    def complete_sale_v2():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        cashier_id = request.user.get("id")
        cashier_name = request.user.get("email")

        raw_items = data.get("items", [])
        items = []
        for item in raw_items:
            normalized = dict(item)
            if "productId" in normalized and "product_id" not in normalized:
                normalized["product_id"] = normalized.get("productId")
            items.append(normalized)

        is_valid, error, deduction_plan = stock_engine.validate_and_prepare_sale(items, account_id)
        if not is_valid:
            return jsonify({"success": False, "error": error or "Invalid sale"}), 400

        # Derive tax rate from provided tax amount if possible
        product_map = deduction_plan.get("product_map", {})
        subtotal = 0.0
        for item in items:
            product_id = item.get("product_id") or item.get("id") or item.get("productId")
            quantity = _safe_float(item.get("quantity"))
            product = product_map.get(product_id)
            if product:
                subtotal += _safe_float(product.get("price")) * quantity

        tax_amount = _safe_float(data.get("tax") or data.get("taxAmount"))
        tax_rate = (tax_amount / subtotal) * 100 if subtotal > 0 and tax_amount > 0 else 0.0

        success, error, sale = stock_engine.execute_sale(
            items=items,
            account_id=account_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            payment_method=data.get("paymentMethod") or data.get("payment_method") or "cash",
            amount_paid=_safe_float(data.get("amountPaid") or data.get("amount_paid")),
            tax_rate=tax_rate,
            discount_amount=_safe_float(data.get("discount")),
            service_fee=_safe_float(data.get("serviceFee"))
        )

        if not success:
            return jsonify({"success": False, "error": error or "Failed to complete sale"}), 400

        product_map = deduction_plan.get("product_map", {})
        raw_material_map = deduction_plan.get("raw_material_map", {})
        product_deductions = []
        for product_id, qty in deduction_plan.get("deductions", {}).items():
            product = product_map.get(product_id)
            if not product:
                continue
            before = _safe_float(product.get("quantity"))
            after = round(before - _safe_float(qty), 4)
            product_deductions.append({
                "id": product_id,
                "name": product.get("name"),
                "before": before,
                "after": after,
                "deducted": qty,
                "unit": product.get("unit", "pcs")
            })

        raw_material_deductions = []
        for material_id, qty in deduction_plan.get("raw_material_deductions", {}).items():
            material = raw_material_map.get(material_id)
            if not material:
                continue
            before = _safe_float(material.get("quantity"))
            after = round(before - _safe_float(qty), 4)
            raw_material_deductions.append({
                "id": material_id,
                "name": material.get("name"),
                "before": before,
                "after": after,
                "deducted": qty,
                "unit": material.get("unit", "unit")
            })

        updated_products = datastore.get_all("products", account_id)
        low_stock = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "quantity": p.get("quantity"),
                "unit": p.get("unit", "pcs")
            }
            for p in updated_products
            if _safe_float(p.get("quantity")) <= _safe_float(p.get("reorder_level")) and _safe_float(p.get("reorder_level")) > 0
        ]

        sync_manager.broadcast_sale_completed(account_id, sale)
        for deduction in product_deductions:
            sync_manager.broadcast_stock_update(account_id, deduction.get("id"), deduction.get("after"))

        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
            cache.delete(f"cache:stats:{account_id}:all")
            cache.delete(f"cache:stats:{account_id}:{cashier_id}")

        return jsonify({
            "success": True,
            "saleId": sale.get("id"),
            "sale": sale,
            "updatedProducts": updated_products,
            "stockDeductions": {
                "products": product_deductions,
                "raw_materials": raw_material_deductions
            },
            "lowStockWarnings": low_stock,
            "timestamp": datetime.utcnow().isoformat(),
            "processingTime": "ok"
        }), 201

    # ============================================================
    # Petroleum Module
    # ============================================================

    def _require_petroleum_subscription():
        account = g.account
        plan = (account or {}).get("plan")
        if plan != "PRO_PETROLEUM":
            return jsonify({"error": "Petroleum module requires PRO_PETROLEUM subscription"}), 403
        return None

    @app.get("/api/petroleum/tanks")
    @auth_controller.require_auth
    def get_petroleum_tanks():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        tanks = datastore.get_all("petroleum_tanks", account_id)
        return jsonify(tanks), 200

    @app.post("/api/petroleum/tanks")
    @auth_controller.require_auth
    def create_petroleum_tank():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}

        fuel_type = (data.get("fuel_type") or data.get("fuelType") or "").strip()
        capacity = _safe_float(data.get("capacity"))
        current_volume = _safe_float(data.get("current_volume") or data.get("currentVolume"))
        price_per_liter = _safe_float(data.get("price_per_liter") or data.get("pricePerLiter"))

        if not fuel_type or capacity <= 0 or price_per_liter <= 0:
            return jsonify({"error": "fuel_type, capacity, price_per_liter are required"}), 400

        tank = {
            "account_id": account_id,
            "fuel_type": fuel_type,
            "capacity": capacity,
            "current_volume": current_volume,
            "price_per_liter": price_per_liter,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }

        created = datastore.create("petroleum_tanks", tank)
        return jsonify(created), 201

    @app.put("/api/petroleum/tanks/<int:tank_id>")
    @auth_controller.require_auth
    def update_petroleum_tank(tank_id: int):
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        if "capacity" in data:
            data["capacity"] = _safe_float(data.get("capacity"))
        if "current_volume" in data or "currentVolume" in data:
            data["current_volume"] = _safe_float(data.get("current_volume") or data.get("currentVolume"))
        if "price_per_liter" in data or "pricePerLiter" in data:
            data["price_per_liter"] = _safe_float(data.get("price_per_liter") or data.get("pricePerLiter"))
        if "fuelType" in data and "fuel_type" not in data:
            data["fuel_type"] = data.get("fuelType")
        data["updated_at"] = datetime.utcnow().isoformat()

        ok = datastore.update("petroleum_tanks", tank_id, data, account_id)
        if not ok:
            return jsonify({"error": "Tank not found"}), 404
        updated = datastore.get_by_id("petroleum_tanks", tank_id, account_id)
        return jsonify(updated), 200

    @app.delete("/api/petroleum/tanks/<int:tank_id>")
    @auth_controller.require_auth
    def delete_petroleum_tank(tank_id: int):
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        ok = datastore.delete("petroleum_tanks", tank_id, account_id)
        if not ok:
            return jsonify({"error": "Tank not found"}), 404
        return jsonify({"success": True}), 200

    @app.get("/api/petroleum/staff")
    @auth_controller.require_auth
    def get_petroleum_staff():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        staff = datastore.get_all("petroleum_staff", account_id)
        for s in staff:
            s.pop("password_hash", None)
        return jsonify(staff), 200

    @app.post("/api/petroleum/staff")
    @auth_controller.require_auth
    def create_petroleum_staff():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}

        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        role = data.get("role") or "pump_attendant"

        if not name or not email or not password:
            return jsonify({"error": "name, email, password are required"}), 400

        password_hash = auth_controller.hash_password(password)

        staff = {
            "account_id": account_id,
            "name": name,
            "email": email,
            "password_hash": password_hash,
            "role": role,
            "is_active": True,
            "created_at": datetime.utcnow().isoformat()
        }

        created = datastore.create("petroleum_staff", staff)

        # Create a corresponding user for login
        user = {
            "account_id": account_id,
            "email": email,
            "password_hash": password_hash,
            "name": name,
            "role": "cashier",
            "pin": None,
            "cashier_pin": None,
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": request.user.get("id"),
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": "petrol",
            "business_role": role
        }
        datastore.create("users", user)

        created.pop("password_hash", None)
        return jsonify(created), 201

    @app.put("/api/petroleum/staff/<int:staff_id>")
    @auth_controller.require_auth
    def update_petroleum_staff(staff_id: int):
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}

        if "password" in data:
            data["password_hash"] = auth_controller.hash_password(data.get("password"))
            data.pop("password", None)

        ok = datastore.update("petroleum_staff", staff_id, data, account_id)
        if not ok:
            return jsonify({"error": "Staff not found"}), 404
        updated = datastore.get_by_id("petroleum_staff", staff_id, account_id)
        if updated:
            updated.pop("password_hash", None)
        return jsonify(updated), 200

    @app.delete("/api/petroleum/staff/<int:staff_id>")
    @auth_controller.require_auth
    def delete_petroleum_staff(staff_id: int):
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        ok = datastore.delete("petroleum_staff", staff_id, account_id)
        if not ok:
            return jsonify({"error": "Staff not found"}), 404
        return jsonify({"success": True}), 200

    @app.get("/api/petroleum/sales")
    @auth_controller.require_auth
    def get_petroleum_sales():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        sales = datastore.get_all("petroleum_sales", account_id)
        sales = _apply_sort(sales, request.args.get("sort") or "-created_at")
        sales = _apply_limit(sales, request.args.get("limit"))
        return jsonify(sales), 200

    @app.post("/api/petroleum/sales")
    @auth_controller.require_auth
    def create_petroleum_sale():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}

        fuel_type = (data.get("fuel_type") or data.get("fuelType") or "").strip()
        liters = _safe_float(data.get("liters"))
        pump_number = data.get("pump_number") or data.get("pumpNumber")

        if not fuel_type or liters <= 0:
            return jsonify({"error": "fuel_type and liters are required"}), 400

        # Find matching tank by fuel type
        tanks = datastore.get_all("petroleum_tanks", account_id)
        tank = next((t for t in tanks if (t.get("fuel_type") or "").lower() == fuel_type.lower()), None)
        if not tank:
            return jsonify({"error": "Tank not found for fuel type"}), 404

        current_volume = _safe_float(tank.get("current_volume"))
        if current_volume < liters:
            return jsonify({"error": "Insufficient tank volume"}), 400

        amount = round(liters * _safe_float(tank.get("price_per_liter")), 2)

        # Deduct tank volume
        new_volume = round(current_volume - liters, 4)
        datastore.update("petroleum_tanks", tank.get("id"), {
            "current_volume": new_volume,
            "updated_at": datetime.utcnow().isoformat()
        }, account_id)

        sale = {
            "account_id": account_id,
            "staff_id": request.user.get("id"),
            "staff_name": request.user.get("email"),
            "fuel_type": fuel_type,
            "liters": liters,
            "amount": amount,
            "pump_number": pump_number,
            "created_at": datetime.utcnow().isoformat()
        }

        created = datastore.create("petroleum_sales", sale)
        return jsonify(created), 201

    # ============================================================
    # TIME TRACKING SYSTEM
    # ============================================================
    
    @app.post("/api/clock-in")
    @auth_controller.require_auth
    def clock_in():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        user_name = request.user.get("name") or request.user.get("email")
        
        success, error, time_entry = time_tracking.clock_in(user_id, user_name, account_id)
        
        if success:
            # Broadcast clock in event
            sync_manager.broadcast_clock_in(account_id, user_id, user_name, time_entry)
            return jsonify(time_entry), 201
        else:
            return jsonify({"error": error}), 400
    
    @app.post("/api/clock-out")
    @auth_controller.require_auth
    def clock_out():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        user_name = request.user.get("name") or request.user.get("email")
        
        success, error, time_entry = time_tracking.clock_out(user_id, user_name, account_id)
        
        if success:
            # Broadcast clock out event
            sync_manager.broadcast_clock_out(account_id, user_id, user_name, time_entry)
            return jsonify(time_entry), 200
        else:
            return jsonify({"error": error}), 400
    
    @app.get("/api/clock-status")
    @auth_controller.require_auth
    def get_clock_status():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        
        status = time_tracking.get_clock_status(user_id, account_id)
        return jsonify(status), 200
    
    @app.get("/api/time-entries")
    @auth_controller.require_auth
    def get_time_entries():
        account_id = request.user.get("account_id")
        user_id = request.args.get("userId")
        date = request.args.get("date")
        
        if user_id:
            try:
                user_id = int(user_id)
            except ValueError:
                return jsonify({"error": "Invalid userId"}), 400
        
        entries = time_tracking.get_time_entries(account_id, user_id, date)
        return jsonify(entries), 200
    
    @app.get("/api/clock-entries")
    @auth_controller.require_auth
    def get_clock_entries():
        # Alias for time-entries
        return get_time_entries()
    
    # ============================================================
    # REMINDERS SYSTEM
    # ============================================================
    
    @app.get("/api/reminders")
    @auth_controller.require_auth
    def get_reminders():
        account_id = request.user.get("account_id")
        include_expired = request.args.get("includeExpired") == "true"
        
        all_reminders = reminders.get_all_reminders(account_id, include_expired)
        return jsonify(all_reminders), 200
    
    @app.post("/api/reminders")
    @auth_controller.require_auth
    def create_reminder():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create reminders
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can create reminders"}), 403
        
        success, error, reminder = reminders.create_reminder(
            account_id=account_id,
            created_by=created_by,
            title=data.get("title"),
            message=data.get("message"),
            priority=data.get("priority", "normal"),
            expires_at=data.get("expiresAt"),
            target_users=data.get("targetUsers")
        )
        
        if success:
            # Broadcast new reminder
            sync_manager.broadcast_reminder(account_id, reminder)
            return jsonify(reminder), 201
        else:
            return jsonify({"error": error}), 400
    
    @app.get("/api/reminders/today")
    @auth_controller.require_auth
    def get_todays_reminders():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        
        unseen_reminders = reminders.get_unseen_reminders(account_id, user_id)
        return jsonify(unseen_reminders), 200
    
    @app.put("/api/reminders/<int:reminder_id>")
    @auth_controller.require_auth
    def mark_reminder_seen(reminder_id: int):
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        
        success = reminders.mark_reminder_seen(reminder_id, user_id, account_id)
        
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Failed to mark reminder as seen"}), 400
    
    @app.delete("/api/reminders/<int:reminder_id>")
    @auth_controller.require_auth
    def delete_reminder(reminder_id: int):
        account_id = request.user.get("account_id")
        
        # Only admins can delete reminders
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can delete reminders"}), 403
        
        success = reminders.delete_reminder(reminder_id, account_id)
        
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Reminder not found"}), 404
    
    # ============================================================
    # CREDIT REQUESTS SYSTEM
    # ============================================================
    
    @app.get("/api/credit-requests")
    @auth_controller.require_auth
    def get_credit_requests():
        account_id = request.user.get("account_id")
        user_role = request.user.get("role")
        user_id = request.user.get("id")
        
        if user_role in ["admin", "owner"]:
            # Admins see all requests
            requests = credit_requests.get_all_requests(account_id)
        else:
            # Cashiers see only their requests
            requests = credit_requests.get_cashier_requests(account_id, user_id)
        
        return jsonify(requests), 200
    
    @app.post("/api/credit-requests")
    @auth_controller.require_auth
    def create_credit_request():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        cashier_id = request.user.get("id")
        cashier_name = request.user.get("name") or request.user.get("email")
        
        success, error, credit_request = credit_requests.create_request(
            account_id=account_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            customer_name=data.get("customerName"),
            amount=_safe_float(data.get("amount")),
            reason=data.get("reason"),
            notes=data.get("notes")
        )
        
        if success:
            # Broadcast credit request to admins
            sync_manager.broadcast_credit_request(account_id, credit_request)
            return jsonify(credit_request), 201
        else:
            return jsonify({"error": error}), 400
    
    @app.put("/api/credit-requests/<int:request_id>")
    @auth_controller.require_auth
    def update_credit_request(request_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        admin_id = request.user.get("id")
        
        # Only admins can approve/reject
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can approve/reject credit requests"}), 403
        
        action = data.get("action")  # 'approve' or 'reject'
        admin_notes = data.get("adminNotes")
        
        if action == "approve":
            success, error, updated_request = credit_requests.approve_request(
                request_id, account_id, admin_id, admin_notes
            )
        elif action == "reject":
            success, error, updated_request = credit_requests.reject_request(
                request_id, account_id, admin_id, admin_notes
            )
        else:
            return jsonify({"error": "Action must be 'approve' or 'reject'"}), 400
        
        if success:
            # Broadcast response to cashier
            cashier_id = updated_request.get("cashier_id")
            sync_manager.broadcast_credit_response(account_id, cashier_id, updated_request)
            return jsonify(updated_request), 200
        else:
            return jsonify({"error": error}), 400
    
    @app.delete("/api/credit-requests/<int:request_id>")
    @auth_controller.require_auth
    def delete_credit_request(request_id: int):
        account_id = request.user.get("account_id")
        
        # Only admins can delete
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can delete credit requests"}), 403
        
        success = credit_requests.delete_request(request_id, account_id)
        
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Credit request not found"}), 404
    
    # ============================================================
    # DISCOUNTS SYSTEM
    # ============================================================
    
    @app.get("/api/discounts")
    @auth_controller.require_auth
    def get_discounts():
        account_id = request.user.get("account_id")
        active_only = request.args.get("activeOnly") == "true"
        
        if active_only:
            discount_list = discounts.get_active_discounts(account_id)
        else:
            discount_list = datastore.get_all("discounts", account_id)
        
        return jsonify(discount_list), 200
    
    @app.post("/api/discounts")
    @auth_controller.require_auth
    def create_discount():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create discounts
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can create discounts"}), 403
        
        success, error, discount = discounts.create_discount(
            account_id=account_id,
            name=data.get("name"),
            discount_type=data.get("type"),
            value=_safe_float(data.get("value")),
            valid_from=data.get("validFrom"),
            valid_to=data.get("validTo"),
            product_ids=data.get("productIds"),
            min_purchase_amount=_safe_float(data.get("minPurchaseAmount")) if data.get("minPurchaseAmount") else None,
            max_discount_amount=_safe_float(data.get("maxDiscountAmount")) if data.get("maxDiscountAmount") else None,
            usage_limit=int(data.get("usageLimit")) if data.get("usageLimit") else None,
            created_by=created_by
        )
        
        if success:
            return jsonify(discount), 201
        else:
            return jsonify({"error": error}), 400
    
    # ============================================================
    # SERVICE FEES SYSTEM
    # ============================================================
    
    @app.get("/api/service-fees")
    @auth_controller.require_auth
    def get_service_fees():
        account_id = request.user.get("account_id")
        active_only = request.args.get("activeOnly") == "true"
        
        if active_only:
            fees = service_fees.get_active_service_fees(account_id)
        else:
            fees = service_fees.get_all_service_fees(account_id)
        
        return jsonify(fees), 200
    
    @app.post("/api/service-fees")
    @auth_controller.require_auth
    def create_service_fee():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create service fees
        if request.user.get("role") not in ["admin", "owner"]:
            return jsonify({"error": "Only admins can create service fees"}), 403
        
        success, error, service_fee = service_fees.create_service_fee(
            account_id=account_id,
            name=data.get("name"),
            amount=_safe_float(data.get("amount")),
            fee_type=data.get("type", "fixed"),
            description=data.get("description"),
            is_active=data.get("isActive", True),
            created_by=created_by
        )
        
        if success:
            return jsonify(service_fee), 201
        else:
            return jsonify({"error": error}), 400

    @sock.route("/api/ws/products")
    def ws_products(ws):
        token = request.args.get("token", "").strip()
        payload = auth_controller.verify_token(token)
        if not payload:
            ws.send(json.dumps({"type": "error", "message": "Invalid token"}))
            return

        account_id = payload.get("account_id")
        user_id = payload.get("user_id")
        if not account_id or not user_id:
            ws.send(json.dumps({"type": "error", "message": "Invalid session"}))
            return

        sync_manager.register_connection(ws, account_id, user_id)

        products = datastore.get_all("products", account_id)
        ws.send(json.dumps({
            "type": "products_snapshot",
            "data": {"allProducts": products},
            "timestamp": datetime.utcnow().isoformat()
        }))

        try:
            while True:
                msg = ws.receive()
                if msg is None:
                    break
                if msg == "ping":
                    ws.send(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
        finally:
            sync_manager.unregister_connection(ws)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
