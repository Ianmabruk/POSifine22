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
import threading
import base64
import re
from datetime import datetime, timedelta
import time
import asyncio
from typing import Dict, Any

from dotenv import load_dotenv
_runtime_env = (os.environ.get("NODE_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
if _runtime_env not in {"production", "prod"}:
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

from flask import Flask, jsonify, request, g
from flask_sock import Sock

from database import DataStore
from stock_engine import StockEngine
from auth import AuthManager, AuthService, require_auth, require_admin, require_main_admin, require_business_admin
from auth.routes import _build_cookie_path
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
from message_routes import message_bp
from notify_service import get_notification_service
from email_service import email_service as email_service_instance

# Optional optimization imports - graceful fallback if not available
DatabaseOptimizer: Any = None
CacheManager: Any = None
SessionCache: Any = None
cache_api_response: Any = None
SecurityManager: Any = None
require_csrf: Any = None
validate_json: Any = None
PerformanceMonitor: Any = None
UserAnalytics: Any = None
ErrorTracker: Any = None

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

    runtime_env = (os.environ.get("NODE_ENV") or os.environ.get("FLASK_ENV") or "").strip().lower()
    is_production = runtime_env in {"production", "prod"}
    configured_secret = (
        os.environ.get("JWT_SECRET")
        or os.environ.get("JWT_SECRET_KEY")
        or os.environ.get("JWT_KEY")
        or os.environ.get("SECRET_KEY")
        or os.environ.get("FLASK_SECRET_KEY")
        or os.environ.get("APP_SECRET_KEY")
        or os.environ.get("SESSION_SECRET")
    )
    if not configured_secret:
        if is_production:
            raise RuntimeError(
                "A production app secret is required. Set one of: "
                "JWT_SECRET, JWT_SECRET_KEY, JWT_KEY, SECRET_KEY, FLASK_SECRET_KEY, APP_SECRET_KEY, SESSION_SECRET"
            )
        configured_secret = "dev-secret-change-me"
    auth_cookie_samesite = os.environ.get("AUTH_COOKIE_SAMESITE", "None" if is_production else "Lax").strip().title()
    if auth_cookie_samesite not in {"Lax", "Strict", "None"}:
        auth_cookie_samesite = "None" if is_production else "Lax"

    # Config
    app.config["SECRET_KEY"] = configured_secret
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
    app.config["PREFERRED_URL_SCHEME"] = "https"
    app.config["MAX_CONTENT_LENGTH"] = 15 * 1024 * 1024

    # CORS
    cors_origins = os.environ.get("CORS_ORIGINS", os.environ.get("CORS_ORIGIN", ""))
    allowed_origins = [o.strip() for o in cors_origins.split(",") if o.strip()]
    netlify_prod_origins = [
        "https://posifine11.netlify.app",
    ]
    for origin in netlify_prod_origins:
        if origin not in allowed_origins:
            allowed_origins.append(origin)

    @app.after_request
    def apply_cors(response):
        origin = request.headers.get("Origin")
        if not origin:
            return response
        is_allowed = origin in allowed_origins or origin.endswith(".netlify.app")
        if is_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-CSRF-Token"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            response.headers["Vary"] = "Origin"
        return response

    @app.before_request
    def _handle_preflight():
        if request.method == "OPTIONS":
            return ("", 200)

    # ============================================================
    # MULTI-SERVER MODE: Route filtering by SERVER_MODE env var
    # ============================================================
    _SERVER_MODE = (os.environ.get("SERVER_MODE") or "").strip().lower()
    _AUTH_PREFIXES = ("/api/auth", "/api/main-admin", "/health", "/ready", "/static")
    _API_PREFIXES = ("/api/", "/health", "/ready", "/static")

    if _SERVER_MODE == "auth":
        _ALLOWED_PREFIXES = _AUTH_PREFIXES
    elif _SERVER_MODE == "api":
        # API servers need /api/auth/me and /api/auth/refresh for session validation
        _ALLOWED_PREFIXES = (
            "/api/",
            "/api/auth/me",
            "/api/auth/refresh",
            "/health",
            "/ready",
            "/static",
        )
    else:
        _ALLOWED_PREFIXES = None  # full app

    if _ALLOWED_PREFIXES is not None:
        @app.before_request
        def _filter_routes_by_server_mode():
            path = request.path
            for prefix in _ALLOWED_PREFIXES:
                if path == prefix or path.startswith(prefix) or path.startswith(prefix + "?"):
                    return None
            # Allow exact matches for specific auth endpoints on API servers
            if _SERVER_MODE == "api" and path in ("/api/auth/me", "/api/auth/refresh"):
                return None
            logger.warning("Blocked route %s on %s server", path, _SERVER_MODE)
            return jsonify({"error": "This endpoint is not available on this server", "server_mode": _SERVER_MODE, "path": path}), 404

    # Server identification
    _SERVER_ID = os.environ.get("SERVER_ID", ("AUTH-1" if _SERVER_MODE == "auth" else "API-1"))

    @app.after_request
    def _add_server_headers(response):
        response.headers["X-Server-ID"] = _SERVER_ID
        response.headers["X-Server-Mode"] = _SERVER_MODE or "full"
        return response

    # Services
    use_postgres = bool(os.environ.get("DATABASE_URL"))
    datastore = DataStore(data_dir=os.environ.get("DATA_DIR"), use_postgres=use_postgres)
    stock_engine = StockEngine(datastore)
    session_store = SessionStore()
    notify_service = get_notification_service()
    cache = CacheService()
    auth_manager = AuthManager(app.config["SECRET_KEY"], session_store=session_store, datastore=datastore, cache_service=cache)
    auth_service = AuthService(auth_manager, datastore=datastore, email_service=notify_service)
    admin_controller = AdminController(datastore, stock_engine)
    cashier_controller = CashierController(datastore, stock_engine)
    
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
    business_bp = create_business_routes(datastore, auth_manager)
    app.register_blueprint(business_bp, url_prefix="/api/business")
    app.register_blueprint(message_bp)

    # Simple in-memory rate limiting for auth endpoints
    login_attempts = {}
    login_blocked_until = {}
    refresh_attempts = {}
    signup_attempts = {}

    trusted_proxy_ips = {
        ip.strip()
        for ip in os.environ.get("TRUSTED_PROXY_IPS", "").split(",")
        if ip.strip()
    }
    trust_proxy_headers = os.environ.get("TRUST_PROXY_HEADERS", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _client_ip():
        remote = request.remote_addr or "unknown"
        if not (trust_proxy_headers or remote in trusted_proxy_ips):
            return remote
        forwarded_for = request.headers.get("X-Forwarded-For", "")
        if forwarded_for:
            first_hop = forwarded_for.split(",")[0].strip()
            if first_hop:
                return first_hop
        return remote

    def _rate_limit_key():
        return _client_ip()

    def _set_auth_cookies(resp, refresh_token: str | None, csrf_token: str | None, scope: str = "auth"):
        cookie_path = _build_cookie_path(scope)
        if refresh_token:
            resp.set_cookie(
                "refresh_token",
                refresh_token,
                secure=True,
                httponly=True,
                samesite=auth_cookie_samesite,
                path=cookie_path,
                max_age=7 * 24 * 60 * 60,
            )
        if csrf_token:
            resp.set_cookie(
                "csrf_token",
                csrf_token,
                secure=True,
                httponly=False,
                samesite=auth_cookie_samesite,
                path=cookie_path,
                max_age=7 * 24 * 60 * 60,
            )

    def _clear_auth_cookies(resp, scope: str = "auth"):
        cookie_path = _build_cookie_path(scope)
        resp.set_cookie("refresh_token", "", expires=0, secure=True, httponly=True, samesite=auth_cookie_samesite, path=cookie_path)
        resp.set_cookie("csrf_token", "", expires=0, secure=True, httponly=False, samesite=auth_cookie_samesite, path=cookie_path)

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

    def _is_signup_rate_limited():
        """Allow max 5 signups per IP per hour."""
        key = _rate_limit_key()
        now = time.time()
        if cache.enabled:
            attempts = cache.incr_with_ttl(f"rl:signup:{key}", 3600)
            if attempts > 5:
                return True
            return False
        attempts = signup_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < 3600]
        signup_attempts[key] = attempts
        if len(attempts) >= 5:
            return True
        return False

    def _record_signup():
        key = _rate_limit_key()
        now = time.time()
        if cache.enabled:
            return  # already incremented in _is_signup_rate_limited
        attempts = signup_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < 3600]
        attempts.append(now)
        signup_attempts[key] = attempts

    def _is_refresh_rate_limited(window_seconds: int = 300, max_attempts: int = 30):
        key = _rate_limit_key()
        if cache.enabled:
            attempts = cache.incr_with_ttl(f"rl:refresh:{key}", window_seconds)
            if attempts > max_attempts:
                return True, window_seconds
            return False, 0

        now = time.time()
        attempts = refresh_attempts.get(key, [])
        attempts = [t for t in attempts if now - t < window_seconds]
        attempts.append(now)
        refresh_attempts[key] = attempts
        if len(attempts) > max_attempts:
            return True, int(window_seconds)
        return False, 0

    def _is_logout_rate_limited(window_seconds: int = 120, max_attempts: int = 60):
        key = _rate_limit_key()
        if cache.enabled:
            attempts = cache.incr_with_ttl(f"rl:logout:{key}", window_seconds)
            if attempts > max_attempts:
                return True, window_seconds
            return False, 0

        now = time.time()
        attempts = refresh_attempts.get(f"logout:{key}", [])
        attempts = [t for t in attempts if now - t < window_seconds]
        attempts.append(now)
        refresh_attempts[f"logout:{key}"] = attempts
        if len(attempts) > max_attempts:
            return True, int(window_seconds)
        return False, 0

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

    def _render_template(text: str | None, variables: Dict[str, Any] | None) -> str | None:
        if not text:
            return text
        if not variables:
            return text
        rendered = text
        for key, value in variables.items():
            placeholder = f"{{{{{key}}}}}"
            placeholder_spaced = f"{{{{ {key} }}}}"
            rendered = rendered.replace(placeholder, str(value))
            rendered = rendered.replace(placeholder_spaced, str(value))
        return rendered

    def _safe_float(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    _MAX_IMAGE_SIZE = 10 * 1024 * 1024
    _ALLOWED_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

    def _validate_product_image(image: Any) -> tuple[bool, str | None]:
        if not image or not isinstance(image, str):
            return True, None
        if not image.startswith("data:image/"):
            return False, "Invalid image format"
        mime_match = re.match(r"data:([^;]+);base64,", image)
        if not mime_match:
            return False, "Invalid image encoding"
        mime_type = mime_match.group(1)
        if mime_type not in _ALLOWED_IMAGE_MIMES:
            return False, "Unsupported image type"
        try:
            decoded = base64.b64decode(image.split(",", 1)[1])
        except Exception:
            return False, "Invalid image data"
        if len(decoded) > _MAX_IMAGE_SIZE:
            return False, "Image exceeds the maximum allowed size of 10 MB."
        return True, None

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
            csrf_cookie = request.cookies.get("csrf_token")
            csrf_header = request.headers.get("X-CSRF-Token")
            csrf_strict_paths = {
                "/api/auth/refresh",
                "/api/auth/logout",
                "/api/main-admin/auth/refresh",
                "/api/main-admin/auth/logout",
            }
            if request.path in csrf_strict_paths:
                if not csrf_cookie or not csrf_header or csrf_header != csrf_cookie:
                    return jsonify({"error": "Invalid CSRF token"}), 403
            # Removed non-strict CSRF check that was blocking product/user/stock
            # operations due to cookie/header mismatches in cross-origin setups.
            # Bearer token auth is sufficient for API mutation endpoints.
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
            is_ws = request.path.startswith("/api/ws/") or request.headers.get("Upgrade", "").lower() == "websocket"
            if not is_ws and duration_ms > 800:
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
        return response

    @app.get("/health")
    def health_check():
        redis_info = cache.health_check() if cache else {
            "enabled": False,
            "status": "disabled",
        }
        overall_ok = datastore is not None
        return jsonify({
            "status": "ok" if overall_ok else "degraded",
            "services": {
                "database": "postgres" if datastore.use_postgres else "json",
                "redis": redis_info,
                "shared_state": "redis" if redis_info.get("enabled") else "in-memory",
                "servers": {
                    "mode": _SERVER_MODE or "full",
                    "id": _SERVER_ID,
                },
            },
            "timestamp": datetime.utcnow().isoformat()
        }), 200 if overall_ok else 503

    @app.get("/ready")
    def ready_check():
        """Readiness probe: verifies the datastore.

        Redis is optional (graceful in-memory fallback), so its availability
        is reported but does not gate readiness — the app can still serve
        requests when Redis is unreachable.
        """
        redis_info = {}
        if cache:
            redis_info = cache.health_check()
        db_ok = datastore is not None
        status = 200 if db_ok else 503
        return jsonify({
            "ready": status == 200,
            "database": bool(db_ok),
            "redis": redis_info,
            "shared_state": "redis" if (redis_info.get("enabled")) else "in-memory",
        }), status

    @app.get("/health/redis")
    def redis_health_check():
        """Dedicated Redis health-check endpoint for the 3-server cluster."""
        if not cache:
            return jsonify({
                "status": "unavailable",
                "configured": False,
                "message": "CacheService not initialized",
            }), 503
        info = cache.health_check()
        status_code = 200 if info.get("status") == "connected" else 503
        return jsonify(info), status_code

    # ============================================================
    # Auth
    # ============================================================

    @app.post("/api/auth/signup")
    def signup():
        if _is_signup_rate_limited():
            return jsonify({"error": "Too many signup attempts. Please try again later."}), 429
        try:
            data = request.get_json() or {}
            
            # Validate required fields first
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
            
            success, error, result = auth_service.signup(
                email=email,
                password=password,
                name=name,
                plan=data.get("plan", "free"),
                business_type=data.get("business_type"),
                device_mode=data.get("device_mode"),
            )
            
            if success:
                _record_signup()
                refresh_token = auth_manager.create_refresh_session(
                    user=result.get("user") or {},
                    user_agent=request.headers.get("User-Agent", ""),
                    ip_address=_rate_limit_key()
                )
                csrf_token = uuid.uuid4().hex
                result["refreshToken"] = refresh_token
                result["csrfToken"] = csrf_token
                _log_activity("signup", result.get("user", {}).get("account_id"), result.get("user", {}).get("id"))
                resp = jsonify(result)
                _set_auth_cookies(resp, refresh_token, csrf_token, "auth")
                return resp, 201
            
            return jsonify({"error": error or "Signup failed"}), 400
            
        except ValueError as e:
            logger.error(f"Signup validation error: {str(e)}")
            _log_activity("signup_failed", None, None, {"reason": str(e)})
            return jsonify({"error": f"Invalid input: {str(e)}"}), 400
        except Exception as e:
            logger.error(f"Signup error: {str(e)}", exc_info=True)
            return jsonify({"error": "Signup failed. Please try again later."}), 500

    @app.post("/api/auth/login")
    def login():
        is_limited, retry_after = _is_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        success, error, result = auth_service.login(
            email=data.get("email"),
            password=data.get("password")
        )
        if success:
            _reset_login_attempts()
            refresh_token = auth_manager.create_refresh_session(
                user=result.get("user") or {},
                user_agent=request.headers.get("User-Agent", ""),
                ip_address=_rate_limit_key()
            )
            csrf_token = uuid.uuid4().hex
            result["refreshToken"] = refresh_token
            result["csrfToken"] = csrf_token
            _log_activity("login", result.get("user", {}).get("account_id"), result.get("user", {}).get("id"))
            resp = jsonify(result)
            _set_auth_cookies(resp, refresh_token, csrf_token, "auth")
            return resp, 200
        
        _log_activity("login_failed", None, None, {"email": data.get("email"), "reason": error})
        return jsonify({"error": error or "Invalid credentials"}), 401

    @app.post("/api/auth/refresh")
    def refresh_token():
        is_limited, retry_after = _is_refresh_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many refresh attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        refresh = request.cookies.get("refresh_token")
        if not refresh:
            refresh = data.get("refreshToken")
        if not refresh:
            return jsonify({"error": "Refresh token required"}), 400

        rotated = auth_manager.rotate_refresh_session(
            refresh_token=refresh,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_rate_limit_key()
        )
        if not rotated:
            return jsonify({"error": "Invalid or expired refresh token"}), 401

        csrf_token = uuid.uuid4().hex
        next_refresh = rotated.pop("refreshToken", None)
        rotated["csrfToken"] = csrf_token
        resp = jsonify(rotated)
        _set_auth_cookies(resp, next_refresh, csrf_token, "auth")
        return resp, 200

    @app.post("/api/auth/logout")
    def logout():
        is_limited, retry_after = _is_logout_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many logout attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        refresh = data.get("refreshToken") or request.cookies.get("refresh_token")
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if refresh:
            auth_manager.revoke_refresh_session(refresh)
        if token:
            auth_manager.revoke_token(token)
        _log_activity("logout", None, None)
        resp = jsonify({"success": True})
        _clear_auth_cookies(resp, "auth")
        return resp, 200

    @app.post("/api/auth/lock-screen")
    @require_auth(auth_manager, datastore)
    def lock_screen():
        user = request.user
        datastore.update("users", user.get("id"), {"screen_locked": True}, user.get("account_id"))
        auth_manager.invalidate_user_session_cache(user.get("id"), user.get("account_id"))
        updated_user = dict(user)
        updated_user["screen_locked"] = True
        updated_user["id"] = user.get("id")
        updated_user["account_id"] = user.get("account_id")
        updated_user["email"] = user.get("email")
        updated_user["name"] = user.get("name")
        updated_user["role"] = user.get("role")
        new_token = auth_manager.generate_token(updated_user)
        return jsonify({"success": True, "token": new_token}), 200

    @app.post("/api/auth/unlock-screen")
    @require_auth(auth_manager, datastore)
    def unlock_screen():
        _failed_key = f"screen_unlock_fails:{_client_ip()}"
        fails = cache.get_int(_failed_key) or 0
        if fails >= 5:
            return jsonify({"message": "Too many failed attempts. Try again later."}), 429

        data = request.get_json() or {}
        user = g.user

        datastore.update("users", user.get("id"), {"screen_locked": False}, user.get("account_id"))
        auth_manager.invalidate_user_session_cache(user.get("id"), user.get("account_id"))
        updated_user = dict(user)
        updated_user["screen_locked"] = False
        updated_user["id"] = user.get("id")
        updated_user["account_id"] = user.get("account_id")
        updated_user["email"] = user.get("email")
        updated_user["name"] = user.get("name")
        updated_user["role"] = user.get("role")
        new_token = auth_manager.generate_token(updated_user)
        return jsonify({"success": True, "token": new_token}), 200

    @app.get("/api/auth/me")
    @require_auth(auth_manager, datastore)
    def auth_me():
        try:
            response_user = auth_manager._build_user_payload(getattr(g, "user", {}) or {}, getattr(g, "account", None))
            resp = jsonify(response_user)
            resp.headers["Cache-Control"] = "private, max-age=30, stale-while-revalidate=60"
            return resp, 200
        except Exception as exc:
            logger.error("auth_me error: %s", exc, exc_info=True)
            return jsonify({"error": "Failed to load user profile"}), 500

    @app.post("/api/auth/change-password")
    @require_auth(auth_manager, datastore)
    def change_password():
        user = request.user
        data = request.get_json() or {}
        current_password = (data.get("currentPassword") or "").strip()
        new_password = (data.get("newPassword") or "").strip()
        new_pin = data.get("newPin")  # optional

        if not current_password:
            return jsonify({"error": "Current password is required"}), 400
        if not new_password:
            return jsonify({"error": "New password is required"}), 400
        if len(new_password) < 4:
            return jsonify({"error": "New password must be at least 4 characters"}), 400

        # Re-fetch full user from DB to get password_hash
        db_user = datastore.get_by_id("users", user.get("id"), user.get("account_id"))
        if not db_user:
            return jsonify({"error": "User not found"}), 404

        if not auth_manager.verify_password(current_password, db_user.get("password_hash", "")):
            return jsonify({"error": "Current password is incorrect"}), 401

        updates = {}
        changed_items = []
        if new_password:
            updates["password_hash"] = auth_manager.hash_password(new_password)
            changed_items.append("password")

        updates["updated_at"] = datetime.utcnow().isoformat()
        success = datastore.update("users", user.get("id"), updates, user.get("account_id"))
        if not success:
            return jsonify({"error": "Failed to update credentials"}), 400
        auth_manager.invalidate_user_session_cache(user.get("id"), user.get("account_id"))

        changed_str = " and ".join(changed_items)
        _log_audit("change_password", user, f"user:{user.get('id')}", {"changed": changed_items})
        return jsonify({"message": f"{changed_str} changed successfully"}), 200

    # ============================================================
    # Subscription Management
    # ============================================================

    def _require_active_subscription():
        account = datastore.get_by_id("accounts", request.user.get("account_id"))
        if not account:
            return False, (jsonify({"error": "Account not found"}), 404)
        if not account.get("is_active", True) or account.get("is_locked"):
            return False, (jsonify({"error": "Account suspended. Please contact support."}), 403)
        plan = account.get("plan", "free")
        if plan == "free":
            return True, None

        trial_end = account.get("trial_ends_at")
        if trial_end:
            try:
                if datetime.utcnow() > datetime.fromisoformat(trial_end):
                    return False, (jsonify({"error": "Trial expired. Please subscribe to continue.", "code": "TRIAL_EXPIRED"}), 403)
            except Exception:
                pass
            return True, None

        sub_end = account.get("subscription_ends_at")
        if sub_end:
            try:
                if datetime.utcnow() > datetime.fromisoformat(sub_end):
                    return False, (jsonify({"error": "Subscription expired. Please renew to continue.", "code": "SUBSCRIPTION_EXPIRED"}), 403)
            except Exception:
                pass
        return True, None

    @app.get("/api/subscription/status")
    @require_auth(auth_manager, datastore)
    def subscription_status():
        account = datastore.get_by_id("accounts", request.user.get("account_id"))
        if not account:
            return jsonify({"error": "Account not found"}), 404
        now = datetime.utcnow().isoformat()
        plan = account.get("plan", "free")
        trial_end = account.get("trial_ends_at")
        sub_end = account.get("subscription_ends_at")
        status = "active"
        days_remaining = None
        if trial_end:
            days_remaining = max(0, (datetime.fromisoformat(trial_end) - datetime.utcnow()).days)
            if now > trial_end:
                status = "expired"
        elif plan not in ("free",):
            if sub_end:
                days_remaining = max(0, (datetime.fromisoformat(sub_end) - datetime.utcnow()).days)
                if now > sub_end:
                    status = "expired"
        return jsonify({
            "plan": plan,
            "status": status,
            "trial_ends_at": trial_end,
            "subscription_ends_at": sub_end,
            "days_remaining": days_remaining,
            "is_active": bool(account.get("is_active")),
        }), 200

    @app.post("/api/subscription/renew")
    @require_auth(auth_manager, datastore)
    def subscription_renew():
        ok, err_resp = _require_active_subscription()
        if not ok:
            return err_resp
        current, error_response = _require_account_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        plan_id = data.get("plan_id") or "business"
        valid_plans = {"starter", "business", "custom", "free", "trial"}
        if plan_id not in valid_plans:
            return jsonify({"error": "Invalid plan"}), 400
        if plan_id == "custom":
            return jsonify({"error": "Custom plan requests must be submitted through the custom plan request form. Our team will contact you."}), 400
        method = data.get("payment_method", "mpesa")
        now = datetime.utcnow()
        new_end = (now + timedelta(days=30)).isoformat()
        success = datastore.update("accounts", request.user.get("account_id"), {
            "plan": plan_id,
            "subscription_ends_at": new_end,
            "trial_ends_at": None,
            "updated_at": now.isoformat(),
        })
        if not success:
            return jsonify({"error": "Failed to update subscription"}), 400
        return jsonify({
            "success": True,
            "plan": plan_id,
            "subscription_ends_at": new_end,
            "payment_method": method,
            "message": f"Subscription renewed until {now + timedelta(days=30):%B %d, %Y}",
        }), 200

    @app.get("/api/subscription/plans")
    def subscription_plans():
        return jsonify({
            "plans": [
                {"id": "starter", "name": "Starter", "price": 1000, "currency": "KES", "trial_days": 30, "max_admins": 1, "max_cashiers": 1},
                {"id": "business", "name": "Business", "price": 1500, "currency": "KES", "trial_days": 30, "max_admins": None, "max_cashiers": None},
                {"id": "custom", "name": "Custom", "price": None, "currency": "KES", "trial_days": 0, "max_admins": None, "max_cashiers": None},
            ]
        }), 200

    @app.post("/api/custom-plan-request")
    def custom_plan_request():
        data = request.get_json() or {}
        business_name = (data.get("businessName") or "").strip()
        contact_name = (data.get("contactName") or "").strip()
        email = (data.get("email") or "").strip().lower()
        phone = (data.get("phone") or "").strip()
        industry = (data.get("industry") or "").strip()
        expected_users = data.get("expectedUsers")
        expected_branches = data.get("expectedBranches")
        features_needed = (data.get("featuresNeeded") or "").strip()
        additional_notes = (data.get("additionalNotes") or "").strip()

        if not business_name or not contact_name or not email:
            return jsonify({"error": "Business name, contact name, and email are required"}), 400

        account_id = None
        if hasattr(request, "user") and request.user:
            account_id = request.user.get("account_id")

        now = datetime.utcnow().isoformat()
        record = {
            "business_name": business_name,
            "contact_name": contact_name,
            "email": email,
            "phone": phone,
            "industry": industry,
            "expected_users": int(expected_users) if expected_users else None,
            "expected_branches": int(expected_branches) if expected_branches else None,
            "features_needed": features_needed,
            "additional_notes": additional_notes,
            "status": "pending",
            "admin_notes": None,
            "reviewed_by": None,
            "reviewed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        if account_id:
            record["account_id"] = account_id

        created = datastore.create("custom_plan_requests", record)

        # Notify main admin asynchronously
        try:
            main_admin_email = os.environ.get("MAIN_ADMIN_EMAIL") or os.environ.get("ADMIN_EMAIL") or "support@micrologic.co.ke"
            email_service_instance.send_custom_plan_notification(
                to_email=main_admin_email,
                business_name=business_name,
                contact_name=contact_name,
                industry=industry,
                requirements=features_needed or additional_notes,
            )
        except Exception as exc:
            logger.warning("Custom plan notification email failed: %s", exc)

        return jsonify({"success": True, "message": "Custom plan request received. Our team will contact you shortly.", "request_id": created.get("id")}), 201

    @app.get("/api/ai/status")
    @require_auth(auth_manager, datastore)
    def ai_status():
        return jsonify({"status": "ok", "mode": "basic"}), 200

    @app.get("/api/ai/forecast")
    @require_auth(auth_manager, datastore)
    def ai_forecast():
        account_id = request.user.get("account_id")
        periods = int(request.args.get("periods", 4))
        sales = datastore.get_all("sales", account_id)
        sales = [s for s in sales if s.get("total") and s.get("created_at")]
        sales = sorted(sales, key=lambda s: s.get("created_at", ""))[-30:]
        if not sales:
            labels = [f"Period {i+1}" for i in range(periods)]
            return jsonify({"labels": labels, "revenue": [0] * periods, "profit": [0] * periods}), 200

        totals = [float(s.get("total") or 0) for s in sales]
        cogs = [float(s.get("total_cost") or 0) for s in sales]
        avg_revenue = sum(totals) / len(totals) if totals else 0
        avg_profit = sum(totals[i] - cogs[i] for i in range(len(totals))) / len(totals) if totals else 0
        labels = [f"Period {i+1}" for i in range(periods)]
        revenue = [round(avg_revenue, 2)] * periods
        profit = [round(avg_profit, 2)] * periods
        return jsonify({"labels": labels, "revenue": revenue, "profit": profit}), 200

    @app.post("/api/trials/create")
    def create_trial():
        data = request.get_json() or {}
        package_type = data.get("packageType") or data.get("plan") or "business"
        valid_plans = {"starter", "business", "custom"}
        if package_type not in valid_plans:
            return jsonify({"error": "Invalid plan"}), 400

        trial_days = 30
        trial_end = (datetime.utcnow() + timedelta(days=trial_days)).isoformat()

        return jsonify({
            "success": True,
            "message": "Trial created successfully",
            "trial": {
                "plan": package_type,
                "trial_days": trial_days,
                "trial_ends_at": trial_end,
                "started_at": datetime.utcnow().isoformat(),
            }
        }), 201
  
    # ============================================================
    # Account User Management (Admin/Cashier Management)
    # ============================================================
  
    def _require_account_admin():
        current = request.user
        if current.get("role") not in {"admin", "main_admin", "owner"}:
            return None, (jsonify({"error": "Admin access required"}), 403)
        return current, None
 
    @app.get("/api/users")
    @require_auth(auth_manager, datastore)
    def get_users():
        account_id = request.user.get("account_id")
        try:
            page = request.args.get("page")
            limit = request.args.get("limit")
            search = request.args.get("search")
            sort = request.args.get("sort") or "-id"
            
            # Backward compatibility: return array if no pagination params
            if not page and not limit:
                users = datastore.get_all("users", account_id)
                response = []
                for u in users:
                    sanitized = dict(u)
                    sanitized.pop("password_hash", None)
                    response.append(sanitized)
                return jsonify(response), 200
            
            # Paginated response
            page = int(page or 1)
            limit = min(int(limit or 20), 100)
            
            result = datastore.get_paginated(
                table="users",
                account_id=account_id,
                page=page,
                limit=limit,
                search=search,
                sort=sort,
                search_fields=["name", "email", "role"]
            )
            
            # Sanitize sensitive fields
            for user in result.get("items", []):
                user.pop("password_hash", None)
            
            return jsonify(result), 200
        except Exception as exc:
            logger.error("Failed to load users: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/users")
    @require_auth(auth_manager, datastore)
    def create_user():
        current, error_response = _require_account_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not name or not email or not password:
            return jsonify({"error": "Name, email, and password are required"}), 400

        existing = datastore.get_user_by_email(email)
        # Email is globally unique in storage, so reject early with a clear message.
        if existing:
            return jsonify({"error": "User with this email already exists"}), 400

        account = datastore.get_by_id("accounts", current.get("account_id"))
        plan = str(account.get("plan") or "free").lower() if account else "free"
        role_value = "cashier"
        if data.get("role"):
            requested_role = (data.get("role") or "").strip().lower()
            if requested_role in {"cashier"}:
                role_value = requested_role
        if plan in {"starter"}:
            all_account_users = datastore.get_all("users", current.get("account_id")) or []
            admin_count = sum(1 for u in all_account_users if u.get("role") in {"admin", "main_admin", "owner"})
            cashier_count = sum(1 for u in all_account_users if u.get("role") == "cashier")
            if role_value == "admin" and admin_count >= 1:
                return jsonify({"error": "Starter plan allows only 1 admin. Upgrade to Business to add more admins."}), 403
            if role_value == "cashier" and cashier_count >= 1:
                return jsonify({"error": "Starter plan allows only 1 cashier. Upgrade to Business to add more cashiers."}), 403

        permissions_value = data.get("permissions") or AuthManager._default_permissions(role_value)

        user_payload = {
            "account_id": current.get("account_id"),
            "email": email,
            "password_hash": auth_manager.hash_password(password),
            "name": name,
            "role": role_value,
            "permissions": permissions_value,
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": current.get("id"),
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": data.get("businessType") or data.get("business_type") or current.get("business_type"),
            "business_role": data.get("businessRole") or data.get("business_role") or role_value,
            "profile_picture": data.get("profilePicture") or data.get("profile_picture")
        }

        try:
            created = datastore.create("users", user_payload)
        except Exception as exc:
            logger.error("Failed to create user: %s", exc, exc_info=True)
            return jsonify({"error": "Unable to create cashier right now. Please try again."}), 500

        created.pop("password_hash", None)
        return jsonify(created), 201

    @app.put("/api/users/<int:user_id>")
    @require_auth(auth_manager, datastore)
    def update_user(user_id: int):
        current, error_response = _require_account_admin()
        if error_response:
            return error_response

        target = datastore.get_by_id("users", user_id, current.get("account_id"))
        if not target:
            return jsonify({"error": "User not found"}), 404

        data = request.get_json() or {}
        updates = {}

        if "name" in data:
            updates["name"] = (data.get("name") or "").strip()
        if "email" in data:
            updates["email"] = (data.get("email") or "").strip().lower()
        if "permissions" in data:
            updates["permissions"] = data.get("permissions") or {}
        if "password" in data and data.get("password"):
            updates["password_hash"] = auth_manager.hash_password(str(data.get("password")))

        if "active" in data:
            updates["is_active"] = bool(data.get("active"))
        if "locked" in data:
            updates["is_locked"] = bool(data.get("locked"))
        if "role" in data:
            requested_role = str(data.get("role") or target.get("role") or "cashier").strip().lower()
            if requested_role not in {"cashier"}:
                updates.pop("role", None)
            else:
                updates["role"] = requested_role
        if "businessType" in data or "business_type" in data:
            updates["business_type"] = data.get("businessType") or data.get("business_type")
        if "businessRole" in data or "business_role" in data:
            updates["business_role"] = data.get("businessRole") or data.get("business_role")
        if "profilePicture" in data or "profile_picture" in data:
            updates["profile_picture"] = data.get("profilePicture") or data.get("profile_picture")

        if not updates:
            return jsonify({"error": "No updates provided"}), 400

        updates["updated_at"] = datetime.utcnow().isoformat()
        success = datastore.update("users", user_id, updates, current.get("account_id"))
        if not success:
            return jsonify({"error": "Failed to update user"}), 400

        updated = datastore.get_by_id("users", user_id, current.get("account_id")) or target
        updated.pop("password_hash", None)
        auth_manager.invalidate_user_session_cache(user_id, current.get("account_id"))
        return jsonify(updated), 200

    @app.delete("/api/users/<int:user_id>")
    @require_auth(auth_manager, datastore)
    def delete_user(user_id: int):
        current, error_response = _require_account_admin()
        if error_response:
            return error_response

        if user_id == current.get("id"):
            return jsonify({"error": "You cannot delete your own account"}), 400

        target = datastore.get_by_id("users", user_id, current.get("account_id"))
        if not target:
            return jsonify({"error": "User not found"}), 404

        success = datastore.delete("users", user_id, current.get("account_id"))
        if not success:
            return jsonify({"error": "Failed to delete user"}), 400
        auth_manager.invalidate_user_session_cache(user_id, current.get("account_id"))
        return jsonify({"message": "User deleted successfully"}), 200

    @app.post("/api/users/<int:user_id>/lock")
    @require_auth(auth_manager, datastore)
    def lock_user(user_id: int):
        current, error_response = _require_account_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        locked = bool(data.get("locked", False))
        success = datastore.update("users", user_id, {
            "is_locked": locked,
            "is_active": not locked,
            "updated_at": datetime.utcnow().isoformat()
        }, current.get("account_id"))
        if not success:
            return jsonify({"error": "User not found"}), 404
        auth_manager.invalidate_user_session_cache(user_id, current.get("account_id"))
        return jsonify({"message": "User lock status updated"}), 200

    @app.post("/api/users/<int:user_id>/activate")
    @require_auth(auth_manager, datastore)
    def activate_user(user_id: int):
        current, error_response = _require_account_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        is_active = bool(data.get("active", True))
        success = datastore.update("users", user_id, {
            "is_active": is_active,
            "updated_at": datetime.utcnow().isoformat()
        }, current.get("account_id"))
        if not success:
            return jsonify({"error": "User not found"}), 404
        auth_manager.invalidate_user_session_cache(user_id, current.get("account_id"))
        return jsonify({"message": "User active status updated"}), 200

    @app.post("/api/clear-data")
    @require_auth(auth_manager, datastore)
    def clear_data():
        if request.user.get("role") not in {"admin", "main_admin", "owner"}:
            return jsonify({"error": "Only admins can clear data"}), 403

        data = request.get_json() or {}
        clear_type = data.get("type", "all")
        account_id = request.user.get("account_id")
        cleared = []

        if clear_type in ("all", "sales"):
            sales = datastore.get_all("sales", account_id)
            for sale in sales:
                datastore.delete("sales", sale.get("id"), account_id)
            cleared.append("sales")

        if clear_type in ("all", "expenses"):
            expenses = datastore.get_all("expenses", account_id)
            for expense in expenses:
                datastore.delete("expenses", expense.get("id"), account_id)
            cleared.append("expenses")

        if clear_type in ("all", "products"):
            products = datastore.get_all("products", account_id)
            for product in products:
                datastore.delete("products", product.get("id"), account_id)
            cleared.append("products")

        if clear_type in ("all", "users"):
            users = datastore.get_all("users", account_id)
            for user in users:
                if user.get("role") not in {"main_admin", "owner"}:
                    datastore.delete("users", user.get("id"), account_id)
            cleared.append("users")

        return jsonify({"success": True, "cleared": cleared}), 200

    # ============================================================
    # Main Admin (Owner)
    # ============================================================

    def _require_main_admin():
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if not token:
            return None, (jsonify({"error": "Authorization token required"}), 401)

        payload = auth_manager.verify_token(token)
        if not payload:
            return None, (jsonify({"error": "Invalid or expired token"}), 401)

        user = datastore.get_by_id("users", payload.get("user_id"), payload.get("account_id"))
        if not user:
            return None, (jsonify({"error": "User not found"}), 401)

        if user.get("role") not in {"main_admin", "owner"}:
            return None, (jsonify({"error": "Access denied"}), 403)

        return user, None

    @app.post("/api/main-admin/auth/login")
    def main_admin_login():
        def _is_bcrypt_hash(value: str) -> bool:
            return value.startswith("$2a$") or value.startswith("$2b$") or value.startswith("$2y$")

        def _log_failed_main_admin_login(email_value: str, reason: str, status_code: int = 403):
            _record_failed_login()
            _log_activity("main_admin_login_failed", None, None, {
                "email": email_value,
                "reason": reason,
                "status_code": status_code,
                "user_agent": request.headers.get("User-Agent", "")
            })
            return jsonify({"error": "Access denied"}), status_code

        def _ensure_main_admin_user(email_value: str, password_hash: str, display_name: str = "Main Admin"):
            owner_user = datastore.get_user_by_email(email_value)
            if owner_user:
                if owner_user.get("role") in {"main_admin", "owner"}:
                    update_data = {"is_active": True, "is_locked": False}
                    if password_hash:
                        update_data["password_hash"] = password_hash
                    datastore.update("users", owner_user.get("id"), update_data, owner_user.get("account_id"))
                    owner_user.update(update_data)
                    return owner_user
                return None

            account_id = f"acc_{uuid.uuid4().hex[:12]}"
            account = {
                "id": account_id,
                "owner_email": email_value,
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
                "screen_lock_password": "",
                "days_used": 0,
                "last_activity_date": None,
                "requested_trial": False,
                "business_type": "main_admin"
            }
            datastore.create("accounts", account)

            return datastore.create("users", {
                "account_id": account_id,
                "email": email_value,
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
                "business_role": "main_admin"
            })

        is_limited, retry_after = _is_rate_limited()
        if is_limited:
            return jsonify({"error": "Too many attempts. Try again later.", "retry_after": retry_after}), 429

        data = request.get_json() or {}
        email = (data.get("email") or "").strip().lower()
        password = (data.get("password") or "").strip()

        if not email or not password:
            return jsonify({"error": "Email and password required"}), 400

        owner = None
        # --- Production bootstrap via ADMIN_EMAIL + ADMIN_PASSWORD/ADMIN_HASH env vars ---
        # These work in any environment (dev or prod) when set, allowing first-time setup.
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
                    password_matches = auth_manager.verify_password(password, bootstrap_hash)
                elif bootstrap_password:
                    password_matches = secrets.compare_digest(password, bootstrap_password)

                if password_matches:
                    persisted_hash = bootstrap_hash if bootstrap_hash and _is_bcrypt_hash(bootstrap_hash) else auth_manager.hash_password(bootstrap_password)
                    owner = _ensure_main_admin_user(bootstrap_email, persisted_hash, "Main Admin")
                else:
                    return _log_failed_main_admin_login(email, "invalid_bootstrap_credentials")

        if not owner:
            owner = datastore.get_user_by_email(email)
            if not owner:
                return _log_failed_main_admin_login(email, "user_not_found", 403)
            if owner.get("role") not in {"main_admin", "owner"}:
                return _log_failed_main_admin_login(email, "role_not_allowed")
            if not owner.get("is_active", True) or owner.get("is_locked"):
                return _log_failed_main_admin_login(email, "account_blocked")

            password_hash = owner.get("password_hash", "")
            if not password_hash or not auth_manager.verify_password(password, password_hash):
                return _log_failed_main_admin_login(email, "invalid_password")

        now_iso = datetime.utcnow().isoformat()
        account = datastore.get_by_id("accounts", owner.get("account_id")) if datastore else None
        # Migrate legacy owner role to main_admin to avoid repeated access denials.
        if owner.get("role") == "owner":
            datastore.update("users", owner.get("id"), {
                "role": "main_admin",
                "business_role": "main_admin",
                "business_type": "main_admin",
            }, owner.get("account_id"))
            owner["role"] = "main_admin"
            owner["business_role"] = "main_admin"
            owner["business_type"] = "main_admin"
            if account:
                account["business_type"] = "main_admin"

        # Non-blocking last_login / last_activity telemetry — fire and forget
        _record_activity_async = threading.Thread(
            target=lambda: (
                datastore.update("users", owner.get("id"), {"last_login": now_iso}, owner.get("account_id"))
                if datastore else None,
                datastore.update("accounts", owner.get("account_id"), {"last_activity_date": now_iso})
                if datastore else None,
            ),
            daemon=True
        )
        _record_activity_async.start()

        token = auth_manager.generate_token(owner)
        refresh_token = auth_manager.create_refresh_session(
            user=owner,
            user_agent=request.headers.get("User-Agent", ""),
            ip_address=_rate_limit_key()
        )
        csrf_token = uuid.uuid4().hex
        _reset_login_attempts()
        _log_activity("main_admin_login", owner.get("account_id"), owner.get("id"))
        resp = jsonify({
            "user": auth_manager._build_user_payload(owner, account),
            "token": token,
            "refreshToken": refresh_token,
            "csrfToken": csrf_token
        })
        _set_auth_cookies(resp, refresh_token, csrf_token, "main_admin")
        return resp, 200

    @app.get("/api/main-admin/users")
    def main_admin_users():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        all_users = datastore.get_all("users")
        accounts = {acc.get("id"): acc for acc in datastore.get_all("accounts")}

        def _days_since(date_str: str | None) -> int | None:
            if not date_str:
                return None
            try:
                parsed = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                return (datetime.utcnow() - parsed).days
            except Exception:
                return None

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
                billing_anchor = account.get("subscription_ends_at") or account.get("created_at")
                days_since = _days_since(billing_anchor)
                sanitized["days_since_plan_start"] = days_since
                sanitized["days_used"] = days_since if days_since is not None else int(account.get("days_used") or 0)
                sanitized["daysUsed"] = sanitized["days_used"]
                sanitized["billing_due"] = bool(days_since is not None and days_since >= 31 and (account.get("plan") or "free") not in ["free", "trial"])
            response.append(sanitized)

        return jsonify(response), 200

    @app.post("/api/main-admin/users")
    def main_admin_create_user():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        data = request.get_json() or {}
        plan_value = str(data.get("plan") or "free").lower()
        plan_limits = {
            "starter": 10,
            "business": 10
        }
        plan_limit = plan_limits.get(plan_value)
        if plan_limit is not None:
            all_users = datastore.get_all("users") or []
            users_on_plan = 0
            for candidate in all_users:
                account = datastore.get_by_id("accounts", candidate.get("account_id"))
                candidate_plan = str((account or {}).get("plan") or "free").lower()
                if candidate_plan == plan_value:
                    users_on_plan += 1
            if users_on_plan >= plan_limit:
                return jsonify({"error": f"{plan_value.title()} plan supports a maximum of {plan_limit} users"}), 403

        success, error, result = auth_service.signup(
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

        hashed = auth_manager.hash_password(temp_password)
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

    @app.get("/api/main-admin/metrics")
    def main_admin_metrics():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        all_accounts = datastore.get_all("accounts")
        all_users = datastore.get_all("users")
        sales = datastore.get_all("sales")

        total_businesses = len(all_accounts)
        active_businesses = len([a for a in all_accounts if a.get("is_active") and not a.get("is_locked")])
        total_revenue = sum(_safe_float(s.get("total")) for sale in sales)
        now = datetime.utcnow()

        active_trials = 0
        expired_trials = 0
        paying_customers = 0
        for a in all_accounts:
            trial_end = a.get("trial_ends_at")
            plan = a.get("plan", "free")
            if plan == "trial" or a.get("status") == "trial":
                if trial_end and now.isoformat() > trial_end:
                    expired_trials += 1
                else:
                    active_trials += 1
            if plan not in ("free", "trial"):
                paying_customers += 1

        return jsonify({
            "totalBusinesses": total_businesses,
            "activeBusinesses": active_businesses,
            "trialAccounts": active_trials,
            "expiredTrials": expired_trials,
            "totalRevenue": total_revenue,
            "payingCustomers": paying_customers,
            "recentRegistrations": len([a for a in all_accounts if a.get("created_at") and (now - datetime.fromisoformat(a.get("created_at").replace("Z", "+00:00"))).days <= 30]),
            "lastUpdated": now.isoformat()
        }), 200

    @app.get("/api/main-admin/businesses")
    def main_admin_businesses():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        accounts = datastore.get_all("accounts")
        users = datastore.get_all("users")
        sales = datastore.get_all("sales")

        users_by_account = {}
        for u in users:
            aid = u.get("account_id")
            users_by_account.setdefault(aid, []).append(u)

        business_list = []
        for account in accounts:
            account_id = account.get("id")
            account_users = users_by_account.get(account_id, [])
            owner = next((u for u in account_users if u.get("role") in ("main_admin", "owner")), account_users[0] if account_users else {})

            trial_end = account.get("trial_ends_at")
            plan = account.get("plan", "free")
            now = datetime.utcnow()
            days_remaining = 0
            trial_status = "none"

            if trial_end:
                try:
                    end_dt = datetime.fromisoformat(trial_end.replace("Z", "+00:00"))
                    days_remaining = max(0, (end_dt - now).days)
                    if now.isoformat() > trial_end:
                        trial_status = "expired"
                    else:
                        trial_status = "active"
                except Exception:
                    pass

            created_at = account.get("created_at")
            days_used = 0
            if created_at:
                try:
                    created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    days_used = (now - created_dt).days
                except Exception:
                    pass

            account_sales = [s for s in sales if s.get("account_id") == account_id]
            total_revenue = sum(_safe_float(s.get("total")) for s in account_sales)

            business_list.append({
                "_id": account_id,
                "id": account_id,
                "name": account.get("business_name") or owner.get("name") or "Unknown",
                "email": account.get("owner_email") or owner.get("email") or "",
                "ownerName": owner.get("name") or "Unknown",
                "plan": plan,
                "status": account.get("status", "active"),
                "isActive": bool(account.get("is_active", True)),
                "isLocked": bool(account.get("is_locked", False)),
                "paymentRequired": bool(account.get("payment_required", False)),
                "trialStatus": trial_status,
                "trialEndsAt": trial_end,
                "daysRemaining": days_remaining,
                "daysUsed": days_used,
                "totalRevenue": total_revenue,
                "subscriptionStatus": account.get("subscriptionStatus", "active"),
                "subscriptionPlan": account.get("subscriptionPlan"),
                "subscriptionEndsAt": account.get("subscriptionEndsAt"),
                "createdAt": created_at,
                "industry": account.get("industry"),
                "currency": account.get("currency", "KES"),
                "userCount": len(account_users),
                "lastActivityDate": account.get("last_activity_date"),
            })

        return jsonify(business_list), 200

    @app.get("/api/main-admin/trials/active")
    def main_admin_active_trials():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        now = datetime.utcnow().isoformat()
        accounts = datastore.get_all("accounts")
        users = datastore.get_all("users")
        users_by_account = {u.get("account_id"): u for u in users}

        active = []
        for a in accounts:
            trial_end = a.get("trial_ends_at")
            plan = a.get("plan", "free")
            if (plan == "trial" or a.get("status") == "trial") and trial_end and now <= trial_end:
                owner = users_by_account.get(a.get("id"), {})
                active.append({
                    "_id": a.get("id"),
                    "businessId": {"name": a.get("business_name"), "email": a.get("owner_email")},
                    "packageType": plan,
                    "startDate": a.get("trial_started_at") or a.get("created_at"),
                    "endDate": trial_end,
                    "ownerName": owner.get("name"),
                    "businessName": a.get("business_name"),
                })

        active.sort(key=lambda x: x.get("endDate") or "", reverse=True)
        return jsonify(active), 200

    @app.get("/api/main-admin/trials/expired")
    def main_admin_expired_trials():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        now = datetime.utcnow().isoformat()
        accounts = datastore.get_all("accounts")
        users = datastore.get_all("users")
        users_by_account = {u.get("account_id"): u for u in users}

        expired = []
        for a in accounts:
            trial_end = a.get("trial_ends_at")
            plan = a.get("plan", "free")
            if (plan == "trial" or a.get("status") == "trial") and trial_end and now > trial_end:
                owner = users_by_account.get(a.get("id"), {})
                expired.append({
                    "_id": a.get("id"),
                    "businessId": {"name": a.get("business_name"), "email": a.get("owner_email")},
                    "packageType": plan,
                    "startDate": a.get("trial_started_at") or a.get("created_at"),
                    "endDate": trial_end,
                    "ownerName": owner.get("name"),
                    "businessName": a.get("business_name"),
                })

        expired.sort(key=lambda x: x.get("endDate") or "", reverse=True)
        return jsonify(expired), 200

    @app.get("/api/main-admin/subscriptions/all")
    def main_admin_subscriptions():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        accounts = datastore.get_all("accounts")
        users = datastore.get_all("users")
        users_by_account = {u.get("account_id"): u for u in users}

        subs = []
        for a in accounts:
            plan = a.get("plan", "free")
            if plan in ("free", "trial"):
                continue
            owner = users_by_account.get(a.get("id"), {})
            subs.append({
                "_id": a.get("id"),
                "businessId": {"name": a.get("business_name")},
                "packageType": plan,
                "status": "active" if a.get("is_active") else "inactive",
                "amount": 0,
                "startDate": a.get("subscription_started_at") or a.get("created_at"),
                "endDate": a.get("subscription_ends_at"),
                "ownerName": owner.get("name"),
                "businessName": a.get("business_name"),
            })

        subs.sort(key=lambda x: x.get("startDate") or "", reverse=True)
        return jsonify(subs), 200

    @app.get("/api/main-admin/payments")
    def main_admin_payments():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        payments = datastore.get_all("payments")
        users = datastore.get_all("users")
        users_by_account = {u.get("account_id"): u for u in users}

        result = []
        for p in payments:
            account_id = p.get("account_id")
            owner = users_by_account.get(account_id, {})
            result.append({
                "_id": p.get("id"),
                "businessId": {"name": p.get("business_name")},
                "amount": p.get("amount"),
                "paymentStatus": p.get("payment_status", "pending"),
                "paymentMethod": p.get("payment_method", ""),
                "createdAt": p.get("created_at"),
                "ownerName": owner.get("name"),
            })

        result.sort(key=lambda x: x.get("createdAt") or "", reverse=True)
        return jsonify(result), 200

    @app.get("/api/main-admin/revenue")
    def main_admin_revenue():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        sales = datastore.get_all("sales")
        daily = {}
        for s in sales:
            created = s.get("created_at") or ""
            if not created:
                continue
            try:
                day = datetime.fromisoformat(created.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except Exception:
                continue
            daily[day] = daily.get(day, 0) + _safe_float(s.get("total"))

        daily_revenue = [{"_id": day, "revenue": total} for day, total in sorted(daily.items())]

        return jsonify({
            "dailyRevenue": daily_revenue[-30:],
            "totalRevenue": sum(_safe_float(s.get("total")) for s in sales),
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
        data = request.get_json() or {}
        user_ids = data.get("userIds") or []
        direct_emails = data.get("emails") or []
        template_id = data.get("templateId")
        variables = data.get("variables") or {}

        if not user_ids and not direct_emails:
            return jsonify({"error": "Recipients are required"}), 400

        template = None
        if template_id:
            template = datastore.get_by_id("email_templates", template_id)
            if not template:
                return jsonify({"error": "Template not found"}), 404

        subject = data.get("subject") or (template.get("subject") if template else None)
        text_message = data.get("message") or data.get("text") or (template.get("text") if template else None)
        html_message = data.get("html") or (template.get("html") if template else None)

        subject = _render_template(subject, variables)
        text_message = _render_template(text_message, variables)
        html_message = _render_template(html_message, variables)

        if not subject or not (text_message or html_message):
            return jsonify({"error": "Subject and message are required"}), 400

        recipients = []
        if user_ids:
            for user_id in user_ids:
                target = datastore.get_by_id("users", user_id)
                if target and target.get("email"):
                    recipients.append(target.get("email"))
        recipients.extend([email for email in direct_emails if email])
        recipients = list(dict.fromkeys(recipients))

        if not recipients:
            return jsonify({"error": "No valid recipient emails found"}), 400

        if not notify_service.email_enabled:
            return jsonify({"error": "Email service is not configured"}), 503

        sent = []
        failed = []
        for recipient in recipients:
            try:
                success = asyncio.run(notify_service.send_email_alert(
                    to=recipient,
                    subject=subject,
                    message=text_message or html_message,
                    html=html_message
                ))
                if success:
                    sent.append(recipient)
                else:
                    failed.append(recipient)
            except Exception:
                failed.append(recipient)

        _log_audit("send_email", user, "email", {
            "recipients": recipients,
            "template_id": template_id,
            "sent": len(sent),
            "failed": len(failed)
        })

        return jsonify({
            "success": len(failed) == 0,
            "sent": sent,
            "failed": failed
        }), 200

    @app.get("/api/main-admin/email-templates")
    def main_admin_get_email_templates():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        templates = datastore.get_all("email_templates")
        templates = sorted(templates, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(templates), 200

    @app.post("/api/main-admin/email-templates")
    def main_admin_create_email_template():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Template name is required"}), 400

        now = datetime.utcnow().isoformat()
        template = {
            "id": f"tmpl_{uuid.uuid4().hex[:12]}",
            "name": name,
            "subject": data.get("subject") or "",
            "text": data.get("text") or data.get("message") or "",
            "html": data.get("html") or "",
            "created_by": user.get("email"),
            "created_at": now,
            "updated_at": now
        }
        created = datastore.create("email_templates", template)
        _log_audit("create_email_template", user, f"email_template:{created.get('id')}")
        return jsonify(created), 201

    @app.put("/api/main-admin/email-templates/<template_id>")
    def main_admin_update_email_template(template_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        updates = {}
        for field in ["name", "subject", "text", "html"]:
            if field in data:
                updates[field] = data.get(field)
        if not updates:
            return jsonify({"error": "No updates provided"}), 400
        updates["updated_at"] = datetime.utcnow().isoformat()
        updated = datastore.update("email_templates", template_id, updates)
        if not updated:
            return jsonify({"error": "Template not found"}), 404
        _log_audit("update_email_template", user, f"email_template:{template_id}")
        return jsonify({"success": True}), 200

    @app.delete("/api/main-admin/email-templates/<template_id>")
    def main_admin_delete_email_template(template_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        deleted = datastore.delete("email_templates", template_id)
        if not deleted:
            return jsonify({"error": "Template not found"}), 404
        _log_audit("delete_email_template", user, f"email_template:{template_id}")
        return jsonify({"success": True}), 200

    @app.post("/api/main-admin/businesses/<string:business_id>/request-payment")
    def main_admin_request_payment(business_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        account = datastore.get_by_id("accounts", business_id)
        if not account:
            return jsonify({"error": "Business not found"}), 404

        datastore.update("accounts", business_id, {
            "payment_required": True,
        })

        _log_audit("request_payment", user, f"account:{business_id}", {
            "business_name": account.get("business_name"),
        })

        return jsonify({
            "success": True,
            "message": "Payment requested. The business will be notified to make payment to continue using the service.",
        }), 200

    @app.post("/api/main-admin/businesses/<string:business_id>/clear-payment")
    def main_admin_clear_payment(business_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        account = datastore.get_by_id("accounts", business_id)
        if not account:
            return jsonify({"error": "Business not found"}), 404

        datastore.update("accounts", business_id, {
            "payment_required": False,
            "is_active": True,
            "is_locked": False,
        })

        _log_audit("clear_payment", user, f"account:{business_id}", {
            "business_name": account.get("business_name"),
        })

        return jsonify({
            "success": True,
            "message": "Payment status cleared. The business can now access the service.",
        }), 200

    # ============================================================
    # Custom Plan Requests
    # ============================================================

    @app.get("/api/main-admin/custom-plan-requests")
    def main_admin_get_custom_plan_requests():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        requests = datastore.get_all("custom_plan_requests")
        requests = sorted(requests, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(requests), 200

    @app.post("/api/main-admin/custom-plan-requests/<int:request_id>/review")
    def main_admin_review_custom_plan_request(request_id: int):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        record = datastore.get_by_id("custom_plan_requests", request_id)
        if not record:
            return jsonify({"error": "Request not found"}), 404

        data = request.get_json() or {}
        status = (data.get("status") or "").strip().lower()
        valid_statuses = {"pending", "under_review", "contacted", "approved", "rejected"}
        if status not in valid_statuses:
            return jsonify({"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"}), 400

        updates = {
            "status": status,
            "admin_notes": data.get("admin_notes"),
            "reviewed_by": user.get("id"),
            "reviewed_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        if status == "approved":
            account_id = record.get("account_id")
            if account_id:
                datastore.update("accounts", account_id, {
                    "plan": "custom",
                    "is_active": True,
                    "is_locked": False,
                    "subscription_ends_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
                    "trial_ends_at": None,
                    "updated_at": datetime.utcnow().isoformat(),
                })

        updated = datastore.update("custom_plan_requests", request_id, updates)
        if not updated:
            return jsonify({"error": "Failed to update request"}), 400

        _log_audit("review_custom_plan_request", user, f"custom_plan_request:{request_id}", {
            "status": status,
            "business_name": record.get("business_name"),
        })

        return jsonify({"success": True, "status": status}), 200

    @app.post("/api/main-admin/businesses/<string:business_id>/send-payment-reminder")
    def main_admin_send_payment_reminder(business_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response

        account = datastore.get_by_id("accounts", business_id)
        if not account:
            return jsonify({"error": "Business not found"}), 404

        data = request.get_json() or {}
        subject = data.get("subject") or f"Payment Reminder — {account.get('business_name')}"
        message = data.get("message")
        amount_due = data.get("amountDue")
        due_date = data.get("dueDate")
        recipient = account.get("owner_email") or data.get("recipient")

        if not recipient:
            return jsonify({"error": "Recipient email is required"}), 400

        if not notify_service.email_enabled:
            return jsonify({"error": "Email service is not configured"}), 503

        try:
            result = email_service_instance.send_payment_reminder(
                to_email=recipient,
                business_name=account.get("business_name", ""),
                plan=account.get("plan", ""),
                amount_due=float(amount_due) if amount_due is not None else None,
                due_date=due_date,
                support_email=os.environ.get("REPLY_TO", "support@micrologic.co.ke"),
            )
        except Exception as exc:
            logger.error("Payment reminder email failed: %s", exc)
            return jsonify({"error": "Failed to send email"}), 500

        datastore.create("email_logs", {
            "account_id": business_id,
            "recipient": recipient,
            "subject": subject,
            "template_type": "payment_reminder",
            "status": "sent" if result.get("success") else "failed",
            "failure_reason": result.get("error") if not result.get("success") else None,
            "sent_at": datetime.utcnow().isoformat() if result.get("success") else None,
            "created_by": user.get("id"),
            "created_at": datetime.utcnow().isoformat(),
        })

        _log_audit("send_payment_reminder", user, f"account:{business_id}", {
            "recipient": recipient,
            "subject": subject,
        })

        return jsonify({"success": result.get("success", False), "message": result.get("error") or "Email sent"}), 200 if result.get("success") else 500

    @app.get("/api/main-admin/email-logs")
    def main_admin_get_email_logs():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        logs = datastore.get_all("email_logs")
        logs = sorted(logs, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(logs), 200

    # ============================================================
    # Admin Support Messaging (Admin -> Main Admin)
    # ============================================================

    @app.post("/api/admin-support/messages")
    @require_auth(auth_manager, datastore)
    def admin_support_send_message():
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can send support messages"}), 403

        data = request.get_json() or {}
        subject = (data.get("subject") or "").strip()
        message = (data.get("message") or data.get("content") or "").strip()
        if not subject or not message:
            return jsonify({"error": "Subject and message are required"}), 400

        now = datetime.utcnow().isoformat()
        record = {
            "id": f"support_{uuid.uuid4().hex[:12]}",
            "account_id": request.user.get("account_id"),
            "admin_user_id": request.user.get("id"),
            "admin_email": request.user.get("email"),
            "admin_name": (g.user or {}).get("name") or request.user.get("email"),
            "subject": subject,
            "message": message,
            "category": data.get("category") or "general",
            "priority": data.get("priority") or "normal",
            "status": "open",
            "response": None,
            "responded_at": None,
            "created_at": now,
            "updated_at": now
        }
        created = datastore.create("admin_support_messages", record)
        _log_activity("admin_support_message", request.user.get("account_id"), request.user.get("id"), {
            "priority": record.get("priority"),
            "category": record.get("category")
        })
        return jsonify(created), 201

    @app.get("/api/admin-support/messages")
    @require_auth(auth_manager, datastore)
    def admin_support_get_messages():
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can view support messages"}), 403

        account_id = request.user.get("account_id")
        messages = datastore.get_by_field("admin_support_messages", "account_id", account_id)
        messages = sorted(messages, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify({"messages": messages}), 200

    @app.post("/api/admin-support/messages/<message_id>/close")
    @require_auth(auth_manager, datastore)
    def admin_support_close_message(message_id: str):
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can close support messages"}), 403

        existing = datastore.get_by_id("admin_support_messages", message_id)
        if not existing:
            return jsonify({"error": "Message not found"}), 404
        if existing.get("account_id") and existing.get("account_id") != request.user.get("account_id"):
            return jsonify({"error": "Access denied"}), 403

        updated = datastore.update("admin_support_messages", message_id, {
            "status": "closed",
            "updated_at": datetime.utcnow().isoformat()
        }, request.user.get("account_id"))
        if not updated:
            return jsonify({"error": "Message not found"}), 404
        return jsonify({"success": True}), 200

    @app.get("/api/main-admin/support/messages")
    def main_admin_support_messages():
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        messages = datastore.get_all("admin_support_messages")
        status = request.args.get("status")
        if status:
            messages = [msg for msg in messages if msg.get("status") == status]
        messages = sorted(messages, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify({"messages": messages}), 200

    @app.post("/api/main-admin/support/messages/<message_id>/reply")
    def main_admin_support_reply(message_id: str):
        user, error_response = _require_main_admin()
        if error_response:
            return error_response
        data = request.get_json() or {}
        response_message = (data.get("response") or data.get("message") or "").strip()
        if not response_message:
            return jsonify({"error": "Response message is required"}), 400

        updated = datastore.update("admin_support_messages", message_id, {
            "response": response_message,
            "status": "responded",
            "responded_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        })
        if not updated:
            return jsonify({"error": "Message not found"}), 404
        _log_audit("support_reply", user, f"support_message:{message_id}")
        return jsonify({"success": True}), 200

    # ============================================================
    # Settings
    # ============================================================

    @app.get("/api/settings")
    @require_auth(auth_manager, datastore)
    def get_settings():
        try:
            account_id = request.user.get("account_id")
            profiles = datastore.get_by_field("business_profiles", "account_id", account_id)
            account = datastore.get_by_id("accounts", account_id)
            is_admin = request.user.get("role") in {"admin", "main_admin", "owner"}
            if profiles:
                settings_payload = profiles[0].get("settings") or {}
                if account:
                    if account.get("business_logo") and not settings_payload.get("logo"):
                        settings_payload["logo"] = account.get("business_logo")
                    if is_admin and account.get("screen_lock_password") and not settings_payload.get("screenLockPassword"):
                        settings_payload["screenLockPassword"] = account.get("screen_lock_password")
                resp = jsonify(settings_payload)
                resp.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=120"
                return resp, 200

            fallback = {}
            if account:
                if account.get("business_logo"):
                    fallback["logo"] = account.get("business_logo")
                if is_admin and account.get("screen_lock_password"):
                    fallback["screenLockPassword"] = account.get("screen_lock_password")
            resp = jsonify(fallback)
            resp.headers["Cache-Control"] = "private, max-age=60, stale-while-revalidate=120"
            return resp, 200
        except Exception as exc:
            logger.error("get_settings error: %s", exc, exc_info=True)
            return jsonify({"error": "Failed to load settings"}), 500

    @app.put("/api/settings")
    @require_business_admin(auth_manager, datastore)
    def update_settings():
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        profiles = datastore.get_by_field("business_profiles", "account_id", account_id)
        now = datetime.utcnow().isoformat()

        account_updates = {}
        if "logo" in data:
            account_updates["business_logo"] = data.get("logo")
        if "screenLockPassword" in data:
            account_updates["screen_lock_password"] = data.get("screenLockPassword")
        if account_updates:
            account_updates["last_activity_date"] = now
            datastore.update("accounts", account_id, account_updates)

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
            "plan": (g.account or {}).get("plan") or "starter",
            "created_at": now,
            "settings": data
        }
        created = datastore.create("business_profiles", profile)
        return jsonify(created.get("settings") or {}), 200

    # ============================================================
    # Products
    # ============================================================

    @app.get("/api/products")
    @require_auth(auth_manager, datastore)
    def get_products():
        account_id = request.user.get("account_id")
        try:
            page = request.args.get("page")
            limit = request.args.get("limit")
            search = request.args.get("search")
            sort = request.args.get("sort")
            
            # Backward compatibility: return array if no pagination params
            if not page and not limit:
                try:
                    products = admin_controller.get_products(account_id)
                except Exception as exc:
                    logger.error("Failed to load products from controller: %s", exc, exc_info=True)
                    return jsonify({"error": "Server error - please try again"}), 500
                products = _apply_sort(products, sort)
                products = _apply_limit(products, request.args.get("limit"))
                products = _apply_fields(products, request.args.get("fields"))
                resp = jsonify(products)
                resp.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
                return resp, 200
            
            # Paginated response
            page = int(page or 1)
            limit = min(int(limit or 20), 100)
            
            result = datastore.get_paginated(
                table="products",
                account_id=account_id,
                page=page,
                limit=limit,
                search=search,
                sort=sort,
                search_fields=["name", "sku", "barcode", "category"]
            )
            
            resp = jsonify(result)
            resp.headers["Cache-Control"] = "private, max-age=15, stale-while-revalidate=30"
            return resp, 200
        except Exception as exc:
            logger.error("Unexpected error in get_products: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/products")
    @require_business_admin(auth_manager, datastore)
    def create_product():
        try:
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
            if "cost_per_unit" not in extra_fields and data.get("cost") is not None:
                extra_fields["cost_per_unit"] = data.get("cost")
            if "enable_weight_pricing" in extra_fields:
                extra_fields["enable_weight_pricing"] = bool(extra_fields.get("enable_weight_pricing"))
            for float_field in ("reorder_level", "max_stock_level", "cost_per_unit"):
                if float_field in extra_fields and extra_fields.get(float_field) != "":
                    extra_fields[float_field] = _safe_float(extra_fields.get(float_field))
            visible = data.get("visibleToCashier") if "visibleToCashier" in data else data.get("visible_to_cashier")
            if visible is not None:
                extra_fields["visible_to_cashier"] = bool(visible)

            image_valid, image_error = _validate_product_image(extra_fields.get("image"))
            if not image_valid:
                return jsonify({"error": image_error}), 400

            try:
                resolved_cost = data.get("cost")
                if (resolved_cost is None or resolved_cost == "") and extra_fields.get("cost_per_unit") is not None:
                    resolved_cost = extra_fields.get("cost_per_unit")

                success, error, product = admin_controller.create_product(
                    account_id=account_id,
                    created_by=created_by,
                    name=data.get("name"),
                    price=_safe_float(data.get("price")),
                    cost=_safe_float(resolved_cost) if resolved_cost not in (None, "") else 0.0,
                    quantity=_safe_float(data.get("quantity")),
                    category=data.get("category", "general"),
                    unit=data.get("unit", "pcs"),
                    is_composite=bool(data.get("is_composite") or data.get("isComposite", False) or str(data.get("category", "")).lower() == "composite"),
                    recipe=data.get("recipe"),
                    **extra_fields
                )
            except (TypeError, ValueError) as exc:
                logger.error("Product creation validation error: %s", exc, exc_info=True)
                return jsonify({"error": "Invalid product data. Please check price, cost, and quantity fields."}), 400
            except Exception as exc:
                logger.error("Product creation error: %s", exc, exc_info=True)
                return jsonify({"error": "Server error while creating product. Please try again."}), 500

            if not success:
                return jsonify({"error": error or "Failed to create product"}), 400
            try:
                sync_manager.broadcast_product_update(account_id, product, action='created')
            except Exception as exc:
                logger.warning("Product broadcast failed: %s", exc, exc_info=True)
            if cache.enabled:
                cache.delete(f"cache:products:{account_id}")
            return jsonify(product), 201
        except Exception as exc:
            logger.error("Unexpected product creation error: %s", exc, exc_info=True)
            return jsonify({"error": "Server error while creating product. Please try again."}), 500

    @app.put("/api/products/<int:product_id>")
    @require_business_admin(auth_manager, datastore)
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

        # Ignore blank numeric fields during partial updates to avoid accidental zero-overwrites.
        for numeric_field in ("price", "cost", "quantity", "reorder_level", "max_stock_level", "cost_per_unit"):
            if numeric_field in updates and updates.get(numeric_field) == "":
                updates.pop(numeric_field, None)

        if "cost" in updates and "cost_per_unit" not in updates:
            updates["cost_per_unit"] = updates.get("cost")
        if "cost_per_unit" in updates and "cost" not in updates:
            updates["cost"] = updates.get("cost_per_unit")
        if "is_composite" not in updates and "isComposite" in data:
            updates["is_composite"] = bool(data.get("isComposite"))
        if "enable_weight_pricing" in updates:
            updates["enable_weight_pricing"] = bool(updates.get("enable_weight_pricing"))
        # Handle visibleToCashier
        if "visibleToCashier" in data:
            updates["visible_to_cashier"] = bool(data.get("visibleToCashier"))
        elif "visible_to_cashier" in data:
            updates["visible_to_cashier"] = bool(data.get("visible_to_cashier"))


        for float_field in ("price", "cost", "quantity", "reorder_level", "max_stock_level", "cost_per_unit"):
            if float_field in updates:
                updates[float_field] = _safe_float(updates.get(float_field))

        if "image" in updates:
            image_valid, image_error = _validate_product_image(updates.get("image"))
            if not image_valid:
                return jsonify({"error": image_error}), 400

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
            # Invalidate stats cache when cost changes so COGS reflects latest costs
            if "cost" in updates or "cost_per_unit" in updates:
                cache.delete(f"cache:stats:{account_id}:all")
        return jsonify(product), 200

    @app.put("/api/products/<int:product_id>/stock")
    @require_business_admin(auth_manager, datastore)
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

    @app.delete("/api/products/<int:product_id>")
    @require_business_admin(auth_manager, datastore)
    def delete_product(product_id: int):
        account_id = request.user.get("account_id")

        existing = datastore.get_by_id("products", product_id, account_id)
        if not existing:
            return jsonify({"error": "Product not found"}), 404

        success, error = admin_controller.delete_product(product_id, account_id)
        if not success:
            return jsonify({"error": error or "Failed to delete product"}), 400

        sync_manager.broadcast_product_update(account_id, existing, action='deleted')
        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
        return jsonify({"message": "Product deleted successfully"}), 200

    @app.get("/api/products/low-stock-warnings")
    @require_auth(auth_manager, datastore)
    def get_low_stock_warnings():
        account_id = request.user.get("account_id")
        products = datastore.get_all("products", account_id)
        warnings = []
        for product in products:
            threshold = _safe_float(product.get("reorder_level") or product.get("reorderLevel") or 0)
            quantity = _safe_float(product.get("quantity"))
            if threshold > 0 and quantity <= threshold:
                warnings.append({
                    "id": product.get("id"),
                    "productId": product.get("id"),
                    "name": product.get("name"),
                    "productName": product.get("name"),
                    "quantity": quantity,
                    "current": quantity,
                    "currentStock": quantity,
                    "unit": product.get("unit") or "pcs",
                    "threshold": threshold,
                    "category": product.get("category") or "general",
                    "reorder_level": threshold,
                })
        return jsonify(warnings), 200

    # ============================================================
    # Recipes
    # ============================================================

    @app.get("/api/recipes")
    @require_auth(auth_manager, datastore)
    def get_recipes():
        account_id = request.user.get("account_id")
        try:
            recipes = datastore.get_all("recipes", account_id)
            products = {p.get("id"): p for p in datastore.get_all("products", account_id)}
            result = []
            for recipe in recipes:
                product = products.get(recipe.get("product_id"))
                result.append({
                    "id": recipe.get("id"),
                    "account_id": recipe.get("account_id"),
                    "product_id": recipe.get("product_id"),
                    "name": recipe.get("name"),
                    "active": recipe.get("active"),
                    "created_at": recipe.get("created_at"),
                    "updated_at": recipe.get("updated_at"),
                    "product": {
                        "id": product.get("id") if product else None,
                        "name": product.get("name") if product else None,
                        "price": product.get("price") if product else None,
                        "unit": product.get("unit") if product else None,
                    } if product else None,
                })
            return jsonify(result), 200
        except Exception as exc:
            logger.error("Failed to load recipes: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.get("/api/recipes/<int:recipe_id>")
    @require_auth(auth_manager, datastore)
    def get_recipe(recipe_id: int):
        account_id = request.user.get("account_id")
        try:
            recipe = datastore.get_by_id("recipes", recipe_id, account_id)
            if not recipe:
                return jsonify({"error": "Recipe not found"}), 404

            ingredients = [
                ing for ing in datastore.get_all("recipe_ingredients", account_id)
                if ing.get("recipe_id") == recipe_id
            ]
            return jsonify({
                "id": recipe.get("id"),
                "account_id": recipe.get("account_id"),
                "product_id": recipe.get("product_id"),
                "name": recipe.get("name"),
                "active": recipe.get("active"),
                "created_at": recipe.get("created_at"),
                "updated_at": recipe.get("updated_at"),
                "ingredients": ingredients,
            }), 200
        except Exception as exc:
            logger.error("Failed to load recipe: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/recipes")
    @require_business_admin(auth_manager, datastore)
    def create_recipe():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")

        product_id = data.get("product_id")
        name = (data.get("name") or "").strip()
        ingredients = data.get("ingredients") or []
        active = data.get("active", True)

        if not product_id:
            return jsonify({"error": "product_id is required"}), 400
        if not name:
            return jsonify({"error": "name is required"}), 400
        if not isinstance(ingredients, list) or len(ingredients) == 0:
            return jsonify({"error": "ingredients must be a non-empty array"}), 400

        product = datastore.get_by_id("products", int(product_id), account_id)
        if not product:
            return jsonify({"error": "Product not found"}), 404

        for ingredient in ingredients:
            qty = _safe_float(ingredient.get("quantity"))
            if qty <= 0:
                return jsonify({"error": "Ingredient quantities must be positive"}), 400

        recipe = datastore.create("recipes", {
            "account_id": account_id,
            "product_id": int(product_id),
            "name": name,
            "active": bool(active),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        })

        for ingredient in ingredients:
            datastore.create("recipe_ingredients", {
                "recipe_id": recipe.get("id"),
                "inventory_item_id": int(ingredient.get("inventory_item_id") or ingredient.get("inventoryItemId") or 0),
                "quantity": _safe_float(ingredient.get("quantity")),
                "unit": (ingredient.get("unit") or "pcs").strip() or "pcs",
                "created_at": datetime.utcnow().isoformat(),
            })

        datastore.update("products", int(product_id), {
            "is_composite": True,
            "product_type": "recipe",
            "recipe": ingredients,
            "updated_at": datetime.utcnow().isoformat(),
        }, account_id)

        return jsonify(recipe), 201

    @app.put("/api/recipes/<int:recipe_id>")
    @require_business_admin(auth_manager, datastore)
    def update_recipe(recipe_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")

        recipe = datastore.get_by_id("recipes", recipe_id, account_id)
        if not recipe:
            return jsonify({"error": "Recipe not found"}), 404

        updates = {}
        if "name" in data:
            updates["name"] = (data.get("name") or "").strip()
        if "active" in data:
            updates["active"] = bool(data.get("active"))
        if updates:
            updates["updated_at"] = datetime.utcnow().isoformat()
            datastore.update("recipes", recipe_id, updates, account_id)

        if "ingredients" in data:
            ingredients = data.get("ingredients") or []
            if not isinstance(ingredients, list) or len(ingredients) == 0:
                return jsonify({"error": "ingredients must be a non-empty array"}), 400

            for ingredient in ingredients:
                qty = _safe_float(ingredient.get("quantity"))
                if qty <= 0:
                    return jsonify({"error": "Ingredient quantities must be positive"}), 400

            existing = [
                ing for ing in datastore.get_all("recipe_ingredients", account_id)
                if ing.get("recipe_id") == recipe_id
            ]
            for ing in existing:
                datastore.delete("recipe_ingredients", ing.get("id"), account_id)

            for ingredient in ingredients:
                datastore.create("recipe_ingredients", {
                    "recipe_id": recipe_id,
                    "inventory_item_id": int(ingredient.get("inventory_item_id") or ingredient.get("inventoryItemId") or 0),
                    "quantity": _safe_float(ingredient.get("quantity")),
                    "unit": (ingredient.get("unit") or "pcs").strip() or "pcs",
                    "created_at": datetime.utcnow().isoformat(),
                })

            datastore.update("products", recipe.get("product_id"), {
                "recipe": ingredients,
                "updated_at": datetime.utcnow().isoformat(),
            }, account_id)

        updated = datastore.get_by_id("recipes", recipe_id, account_id)
        return jsonify(updated), 200

    @app.delete("/api/recipes/<int:recipe_id>")
    @require_business_admin(auth_manager, datastore)
    def delete_recipe(recipe_id: int):
        account_id = request.user.get("account_id")

        recipe = datastore.get_by_id("recipes", recipe_id, account_id)
        if not recipe:
            return jsonify({"error": "Recipe not found"}), 404

        product_id = recipe.get("product_id")

        stock_deductions = datastore.get_by_field("stock_deductions", "product_id", product_id)
        sales_items = []
        for sale in datastore.get_all("sales", account_id):
            for item in sale.get("items", []):
                if item.get("product_id") == product_id:
                    sales_items.append(sale)
                    break
        if stock_deductions or sales_items:
            return jsonify({"error": "Cannot delete recipe: sales or stock deductions exist for this product"}), 400

        existing_ingredients = [
            ing for ing in datastore.get_all("recipe_ingredients", account_id)
            if ing.get("recipe_id") == recipe_id
        ]
        for ing in existing_ingredients:
            datastore.delete("recipe_ingredients", ing.get("id"), account_id)

        datastore.delete("recipes", recipe_id, account_id)
        datastore.update("products", product_id, {
            "is_composite": False,
            "product_type": "regular",
            "recipe": [],
            "updated_at": datetime.utcnow().isoformat(),
        }, account_id)

        return jsonify({"message": "Recipe deleted successfully"}), 200

    # ============================================================
    # Batches (Stock Additions)
    # ============================================================

    @app.get("/api/batches")
    @require_auth(auth_manager, datastore)
    def get_batches():
        account_id = request.user.get("account_id")
        product_id = request.args.get("productId")
        page = request.args.get("page")
        limit = request.args.get("limit")
        sort = request.args.get("sort") or "-created_at"
        
        try:
            if not page and not limit:
                batches = datastore.get_all("batches", account_id)
                batches = _apply_sort(batches, sort)
                batches = _apply_limit(batches, request.args.get("limit"))
                if product_id is not None:
                    try:
                        product_id_int = int(product_id)
                    except ValueError:
                        return jsonify({"error": "Invalid productId"}), 400
                    batches = [b for b in batches if int(b.get("productid") or b.get("product_id") or 0) == product_id_int]
                return jsonify(batches), 200
            
            page = int(page or 1)
            limit = min(int(limit or 20), 100)
            
            if product_id is not None:
                try:
                    product_id_int = int(product_id)
                except ValueError:
                    return jsonify({"error": "Invalid productId"}), 400
                
                result = datastore.get_paginated(
                    table="batches",
                    account_id=account_id,
                    page=page,
                    limit=limit,
                    sort=sort,
                    search_fields=["productid", "batchnumber"]
                )
                items = [b for b in result["items"] if int(b.get("productid") or b.get("product_id") or 0) == product_id_int]
                result["items"] = items
                result["total"] = len(items)
                result["total_pages"] = max(1, (result["total"] + limit - 1) // limit)
                return jsonify(result), 200
            else:
                result = datastore.get_paginated(
                    table="batches",
                    account_id=account_id,
                    page=page,
                    limit=limit,
                    sort=sort,
                    search_fields=["batchnumber"]
                )
                return jsonify(result), 200
        except Exception as exc:
            logger.error("Failed to load batches: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/batches")
    @require_business_admin(auth_manager, datastore)
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
        product_update = {
            "quantity": new_quantity,
            "updated_at": datetime.utcnow().isoformat()
        }
        # If a cost was provided with this batch, update the product's cost fields so
        # COGS calculations always use the latest purchase cost.
        batch_cost = _safe_float(data.get("cost"))
        if batch_cost > 0:
            product_update["cost"] = batch_cost
            product_update["cost_per_unit"] = batch_cost
        datastore.update("products", int(product_id), product_update, account_id)

        updated_product = datastore.get_by_id("products", int(product_id), account_id)
        sync_manager.broadcast_stock_update(account_id, int(product_id), updated_product.get("quantity") if updated_product else new_quantity)
        if updated_product:
            sync_manager.broadcast_product_update(account_id, updated_product, action='updated')

        if cache.enabled:
            cache.delete(f"cache:products:{account_id}")
            if batch_cost > 0:
                cache.delete(f"cache:stats:{account_id}:all")

        return jsonify({
            "batch": created_batch,
            "product": updated_product
        }), 201

    # ============================================================
    # Sales
    # ============================================================

    @app.get("/api/sales")
    @require_auth(auth_manager, datastore)
    def get_sales():
        account_id = request.user.get("account_id")
        try:
            page = request.args.get("page")
            limit = request.args.get("limit")
            search = request.args.get("search")
            sort = request.args.get("sort") or "-created_at"
            
            # Backward compatibility: return array if no pagination params
            if not page and not limit:
                sales = admin_controller.get_sales(account_id)
                sales = _apply_sort(sales, sort)
                sales = _apply_limit(sales, request.args.get("limit"))
                sales = _apply_fields(sales, request.args.get("fields"))
                resp = jsonify(sales)
                resp.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=30"
                return resp, 200
            
            # Paginated response
            page = int(page or 1)
            limit = min(int(limit or 20), 100)
            
            result = datastore.get_paginated(
                table="sales",
                account_id=account_id,
                page=page,
                limit=limit,
                search=search,
                sort=sort,
                search_fields=["receipt_number", "payment_method", "cashier_name"]
            )
            
            resp = jsonify(result)
            resp.headers["Cache-Control"] = "private, max-age=10, stale-while-revalidate=30"
            return resp, 200
        except Exception as exc:
            logger.error("Failed to load sales: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.delete("/api/sales/<int:sale_id>")
    @require_auth(auth_manager, datastore)
    def delete_sale(sale_id: int):
        account_id = request.user.get("account_id")
        sale = datastore.get_by_id("sales", sale_id, account_id)
        if not sale:
            return jsonify({"error": "Sale not found"}), 404
        success = datastore.delete("sales", sale_id, account_id)
        if not success:
            return jsonify({"error": "Failed to delete sale"}), 400
        return jsonify({"message": "Sale deleted successfully"}), 200

    @app.post("/api/sales/bulk-delete")
    @require_auth(auth_manager, datastore)
    def bulk_delete_sales():
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        sale_ids = data.get("saleIds") or []
        if not sale_ids:
            return jsonify({"error": "No sale IDs provided"}), 400
        deleted = 0
        for sid in sale_ids:
            try:
                sid_int = int(sid)
            except (TypeError, ValueError):
                continue
            sale = datastore.get_by_id("sales", sid_int, account_id)
            if sale:
                datastore.delete("sales", sid_int, account_id)
                deleted += 1
        return jsonify({"success": True, "deletedCount": deleted}), 200

    @app.get("/api/stats")
    @require_auth(auth_manager, datastore)
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
        today = datetime.utcnow().date()
        week_start = today - timedelta(days=today.weekday())

        def _sale_date(sale: Dict[str, Any]):
            created_at = sale.get("created_at") or sale.get("createdAt") or ""
            if not created_at:
                return None
            try:
                return datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
            except Exception:
                return None

        daily_sales = 0.0
        weekly_sales = 0.0
        for sale in sales:
            sale_date = _sale_date(sale)
            sale_total = _safe_float(sale.get("total"))
            if sale_date == today:
                daily_sales += sale_total
            if sale_date and sale_date >= week_start:
                weekly_sales += sale_total

        # Cashier monitor uses sales - expenses, admin uses full cost model
        if cashier_id is not None:
            profit = total_sales - total_expenses
        else:
            profit = total_sales - total_cogs - total_expenses

        gross_profit = total_sales - total_cogs
        net_profit = profit

        response = {
            "totalSales": total_sales,
            "totalExpenses": total_expenses,
            "totalCOGS": total_cogs,
            "grossProfit": gross_profit,
            "netProfit": net_profit,
            "profit": profit,
            "dailySales": daily_sales,
            "weeklySales": weekly_sales,
            "productCount": len(products),
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
    @require_auth(auth_manager, datastore)
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
        total_cogs = sum(_safe_float(s.get("total_cost")) for s in today_sales)
        transaction_count = len(today_sales)
        avg_transaction = (total_sales / transaction_count) if transaction_count else 0

        response_data = {
            "totalSales": total_sales,
            "totalExpenses": total_expenses,
            "totalCOGS": total_cogs,
            "grossProfit": total_sales - total_cogs,
            "netProfit": total_sales - total_expenses,
            "profit": total_sales - total_expenses,
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
    @require_auth(auth_manager, datastore)
    def get_expenses():
        account_id = request.user.get("account_id")
        try:
            page = request.args.get("page")
            limit = request.args.get("limit")
            search = request.args.get("search")
            sort = request.args.get("sort") or "-created_at"
            
            # Backward compatibility
            if not page and not limit:
                expenses = datastore.get_all("expenses", account_id)
                expenses = _apply_sort(expenses, sort)
                expenses = _apply_limit(expenses, request.args.get("limit"))
                return jsonify(expenses), 200
            
            page = int(page or 1)
            limit = min(int(limit or 20), 100)
            
            result = datastore.get_paginated(
                table="expenses",
                account_id=account_id,
                page=page,
                limit=limit,
                search=search,
                sort=sort,
                search_fields=["category", "description"]
            )
            
            return jsonify(result), 200
        except Exception as exc:
            logger.error("Failed to load expenses: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/expenses")
    @require_business_admin(auth_manager, datastore)
    def create_expense():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        cashier_id = request.user.get("id")
        cashier_name = request.user.get("email")

        amount = _safe_float(data.get("amount"))
        if amount <= 0:
            return jsonify({"error": "Amount must be positive"}), 400

        category = (data.get("category") or "general").strip().lower()
        quantity = _safe_float(data.get("quantity") or 1)
        unit = (data.get("unit") or "unit").strip() or "unit"
        track_stock = bool(data.get("track_stock") or data.get("trackStock") or category == "ingredient")

        if track_stock and quantity <= 0:
            return jsonify({"error": "Quantity must be positive for stock-tracked ingredient expenses"}), 400

        expense = {
            "account_id": account_id,
            "name": data.get("name") or data.get("description") or "Expense",
            "description": data.get("description") or data.get("name") or "",
            "amount": amount,
            "quantity": quantity,
            "unit": unit,
            "category": category,
            "source": data.get("source") or ("ingredient-stock" if track_stock else "manual"),
            "cashier_id": cashier_id,
            "cashier_name": cashier_name,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": cashier_id
        }

        # Allow ingredient purchases in Expenses to refill ingredient stock.
        if track_stock:
            ingredient_name = (expense.get("name") or "").strip()
            if not ingredient_name:
                return jsonify({"error": "Ingredient name is required for stock-tracked expenses"}), 400

            raw_materials = datastore.get_all("raw_materials", account_id)
            existing_material = next(
                (m for m in raw_materials if str(m.get("name") or "").strip().lower() == ingredient_name.lower()),
                None
            )

            if existing_material:
                current_qty = _safe_float(existing_material.get("quantity"))
                new_qty = round(current_qty + quantity, 4)
                material_updates = {
                    "quantity": new_qty,
                    "unit": unit,
                    "updated_at": datetime.utcnow().isoformat()
                }
                unit_cost = amount / quantity if quantity > 0 else 0.0
                if unit_cost > 0:
                    material_updates["cost_per_unit"] = round(unit_cost, 6)
                datastore.update("raw_materials", existing_material.get("id"), material_updates, account_id)
                expense["linked_raw_material_id"] = existing_material.get("id")
                
                # Create inventory transaction for purchase
                try:
                    datastore.create("inventory_transactions", {
                        "account_id": account_id,
                        "inventory_item_id": existing_material.get("id"),
                        "transaction_type": "PURCHASE",
                        "quantity": round(quantity, 4),
                        "unit": unit,
                        "before_quantity": round(current_qty, 4),
                        "after_quantity": round(new_qty, 4),
                        "reference_type": "expense",
                        "reference_id": None,
                        "reason": f"Purchased: {ingredient_name}",
                        "created_by": cashier_id,
                        "created_at": datetime.utcnow().isoformat()
                    })
                except Exception:
                    pass
            else:
                unit_cost = amount / quantity if quantity > 0 else 0.0
                created_material = datastore.create("raw_materials", {
                    "account_id": account_id,
                    "name": ingredient_name,
                    "quantity": quantity,
                    "unit": unit,
                    "cost_per_unit": round(unit_cost, 6),
                    "reorder_level": _safe_float(data.get("reorder_level") or 0),
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": None
                })
                expense["linked_raw_material_id"] = created_material.get("id")
                
                # Create inventory transaction for initial purchase
                try:
                    datastore.create("inventory_transactions", {
                        "account_id": account_id,
                        "inventory_item_id": created_material.get("id"),
                        "transaction_type": "PURCHASE",
                        "quantity": round(quantity, 4),
                        "unit": unit,
                        "before_quantity": 0.0,
                        "after_quantity": round(quantity, 4),
                        "reference_type": "expense",
                        "reference_id": None,
                        "reason": f"Initial purchase: {ingredient_name}",
                        "created_by": cashier_id,
                        "created_at": datetime.utcnow().isoformat()
                    })
                except Exception:
                    pass

        created = datastore.create("expenses", expense)
        
        # Update inventory transactions with expense reference_id
        if track_stock and created:
            try:
                transactions = datastore.get_all("inventory_transactions", account_id)
                for txn in transactions:
                    if (txn.get("reference_type") == "expense" and txn.get("reference_id") is None 
                        and txn.get("inventory_item_id") == expense.get("linked_raw_material_id")
                        and txn.get("reason", "").startswith("Purchased:")):
                        datastore.update("inventory_transactions", txn.get("id"), {
                            "reference_id": created.get("id")
                        }, account_id)
                        break
            except Exception:
                pass
        
        sync_manager.broadcast_expense_created(account_id, created)
        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
            cache.delete(f"cache:stats:{account_id}:{cashier_id}")
        return jsonify(created), 201

    @app.put("/api/expenses/<int:expense_id>")
    @require_business_admin(auth_manager, datastore)
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
    @require_business_admin(auth_manager, datastore)
    def delete_expense(expense_id: int):
        account_id = request.user.get("account_id")
        ok = datastore.delete("expenses", expense_id, account_id)
        if not ok:
            return jsonify({"error": "Expense not found"}), 404
        if cache.enabled:
            cache.delete(f"cache:stats:{account_id}:all")
        return jsonify({"success": True}), 200

    # ============================================================
    # Raw Materials (Ingredient Stock)
    # ============================================================

    @app.get("/api/raw-materials")
    @require_auth(auth_manager, datastore)
    def get_raw_materials():
        account_id = request.user.get("account_id")
        try:
            raw_materials = datastore.get_all("raw_materials", account_id)
            raw_materials = _apply_sort(raw_materials, request.args.get("sort") or "name")
            raw_materials = _apply_limit(raw_materials, request.args.get("limit"))
            return jsonify(raw_materials), 200
        except Exception as exc:
            logger.error("Failed to load raw materials: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/raw-materials")
    @require_business_admin(auth_manager, datastore)
    def create_raw_material():
        account_id = request.user.get("account_id")
        data = request.get_json() or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Name is required"}), 400
        record = {
            "account_id": account_id,
            "name": name,
            "quantity": _safe_float(data.get("quantity") or 0),
            "unit": (data.get("unit") or "unit").strip() or "unit",
            "cost_per_unit": _safe_float(data.get("cost_per_unit") or data.get("costPerUnit") or 0),
            "reorder_level": _safe_float(data.get("reorder_level") or data.get("reorderLevel") or 0),
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        created = datastore.create("raw_materials", record)
        return jsonify(created), 201

    @app.get("/api/inventory-transactions")
    @require_auth(auth_manager, datastore)
    def get_inventory_transactions():
        account_id = request.user.get("account_id")
        try:
            transactions = datastore.get_all("inventory_transactions", account_id)
            transactions = _apply_sort(transactions, request.args.get("sort") or "-created_at")
            transactions = _apply_limit(transactions, request.args.get("limit"))
            
            # Filter by inventory_item_id if provided
            inventory_item_id = request.args.get("inventory_item_id")
            if inventory_item_id:
                transactions = [t for t in transactions if t.get("inventory_item_id") == int(inventory_item_id)]
            
            # Filter by transaction_type if provided
            transaction_type = request.args.get("transaction_type")
            if transaction_type:
                transactions = [t for t in transactions if t.get("transaction_type") == transaction_type]
            
            return jsonify(transactions), 200
        except Exception as exc:
            logger.error("Failed to load inventory transactions: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.get("/api/admin/analytics/top-products")
    @require_business_admin(auth_manager, datastore)
    def get_top_products():
        account_id = request.user.get("account_id")
        period = (request.args.get("period") or "month").strip().lower()
        
        try:
            sales = datastore.get_all("sales", account_id)
            products = {p.get("id"): p for p in datastore.get_all("products", account_id)}
            
            now = datetime.utcnow()
            if period == "today":
                start_date = now.date()
            elif period == "week":
                start_date = (now - timedelta(days=now.weekday())).date()
            elif period == "30days":
                start_date = (now - timedelta(days=30)).date()
            else:  # month
                start_date = now.replace(day=1).date()
            
            product_sales = {}
            for sale in sales:
                created_at = sale.get("created_at") or ""
                if not created_at:
                    continue
                try:
                    sale_date = datetime.fromisoformat(str(created_at).replace("Z", "+00:00")).date()
                except Exception:
                    continue
                if sale_date < start_date:
                    continue
                
                for item in sale.get("items", []):
                    pid = item.get("product_id") or item.get("productId")
                    qty = _safe_float(item.get("quantity"))
                    if not pid or qty <= 0:
                        continue
                    product_sales[pid] = product_sales.get(pid, 0) + qty
            
            result = []
            for pid, qty in product_sales.items():
                product = products.get(pid)
                if not product:
                    continue
                result.append({
                    "productId": pid,
                    "name": product.get("name"),
                    "image": product.get("image"),
                    "quantitySold": qty,
                    "unit": product.get("unit") or "pcs",
                })
            
            result.sort(key=lambda x: x["quantitySold"], reverse=True)
            return jsonify(result[:20]), 200
        except Exception as exc:
            logger.error("Failed to load top products: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    # ============================================================
    # School - Students
    # ============================================================

    @app.get("/api/students")
    @require_auth(auth_manager, datastore)
    def get_students():
        account_id = request.user.get("account_id")
        try:
            students = datastore.get_all("students", account_id)
            students = _apply_sort(students, request.args.get("sort") or "-created_at")
            return jsonify(students), 200
        except Exception as exc:
            logger.error("Failed to load students: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/students")
    @require_business_admin(auth_manager, datastore)
    def create_student():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")

        name = (data.get("name") or "").strip()
        admission_no = (data.get("admissionNumber") or data.get("admission_number") or "").strip()
        class_name = (data.get("className") or data.get("class_name") or "").strip()

        if not name:
            return jsonify({"error": "Student name is required"}), 400

        student = {
            "account_id": account_id,
            "name": name,
            "admission_number": admission_no,
            "class_name": class_name,
            "parent_name": data.get("parentName") or data.get("parent_name") or "",
            "parent_phone": data.get("parentPhone") or data.get("parent_phone") or "",
            "student_image": data.get("studentImage") or data.get("student_image") or "",
            "id_image": data.get("idImage") or data.get("id_image") or "",
            "notes": data.get("notes") or "",
            "created_by": created_by,
            "created_at": datetime.utcnow().isoformat()
        }

        created_student = datastore.create("students", student)
        return jsonify(created_student), 201

    # ---- Fee payments -------------------------------------------------------

    @app.get("/api/students/<int:student_id>/fees")
    @require_auth(auth_manager, datastore)
    def get_student_fees(student_id: int):
        account_id = request.user.get("account_id")
        all_fees = datastore.get_all("fee_payments", account_id)
        return jsonify([f for f in all_fees if f.get("student_id") == student_id]), 200

    @app.post("/api/students/<int:student_id>/fees")
    @require_auth(auth_manager, datastore)
    def add_fee_payment(student_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        record = {
            "account_id": account_id,
            "student_id": student_id,
            "term": data.get("term") or "",
            "year": int(data.get("year") or datetime.utcnow().year),
            "amount_due": float(data.get("amount_due") or 0),
            "amount_paid": float(data.get("amount_paid") or 0),
            "payment_date": data.get("payment_date") or datetime.utcnow().isoformat(),
            "payment_method": data.get("payment_method") or "cash",
            "notes": data.get("notes") or "",
            "created_by": request.user.get("id"),
            "created_at": datetime.utcnow().isoformat()
        }
        return jsonify(datastore.create("fee_payments", record)), 201

    # ---- Exam results -------------------------------------------------------

    @app.get("/api/students/<int:student_id>/results")
    @require_auth(auth_manager, datastore)
    def get_exam_results(student_id: int):
        account_id = request.user.get("account_id")
        all_results = datastore.get_all("exam_results", account_id)
        return jsonify([r for r in all_results if r.get("student_id") == student_id]), 200

    @app.post("/api/exam-results")
    @require_auth(auth_manager, datastore)
    def add_exam_result():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        record = {
            "account_id": account_id,
            "student_id": int(data.get("student_id") or 0),
            "subject": data.get("subject") or "",
            "score": float(data.get("score") or 0),
            "max_score": float(data.get("max_score") or 100),
            "grade": data.get("grade") or "",
            "term": data.get("term") or "",
            "year": int(data.get("year") or datetime.utcnow().year),
            "exam_type": data.get("exam_type") or "end_term",
            "notes": data.get("notes") or "",
            "created_by": request.user.get("id"),
            "created_at": datetime.utcnow().isoformat()
        }
        return jsonify(datastore.create("exam_results", record)), 201

    # ---- Assignments --------------------------------------------------------

    @app.get("/api/assignments")
    @require_auth(auth_manager, datastore)
    def get_assignments():
        account_id = request.user.get("account_id")
        class_name = request.args.get("class")
        items = datastore.get_all("assignments", account_id)
        if class_name:
            items = [a for a in items if a.get("class_name") == class_name]
        return jsonify(items), 200

    @app.post("/api/assignments")
    @require_auth(auth_manager, datastore)
    def create_assignment():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        record = {
            "account_id": account_id,
            "class_name": data.get("class_name") or data.get("className") or "",
            "subject": data.get("subject") or "",
            "title": data.get("title") or "",
            "description": data.get("description") or "",
            "due_date": data.get("due_date") or data.get("dueDate") or "",
            "created_by": request.user.get("id"),
            "created_at": datetime.utcnow().isoformat()
        }
        return jsonify(datastore.create("assignments", record)), 201

    # ---- School notices -----------------------------------------------------

    @app.get("/api/school-notices")
    @require_auth(auth_manager, datastore)
    def get_school_notices():
        account_id = request.user.get("account_id")
        return jsonify(datastore.get_all("school_notices", account_id)), 200

    @app.post("/api/school-notices")
    @require_auth(auth_manager, datastore)
    def create_school_notice():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        record = {
            "account_id": account_id,
            "title": data.get("title") or "",
            "body": data.get("body") or "",
            "audience": data.get("audience") or "all",
            "created_by": request.user.get("id"),
            "created_at": datetime.utcnow().isoformat()
        }
        return jsonify(datastore.create("school_notices", record)), 201

    @app.post("/api/sales")
    @require_auth(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
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

        # === PHASE 1: Validate and prepare (fast, in-memory) ===
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
        tax_type = (data.get("taxType") or "exclusive").strip().lower()
        tax_rate = (tax_amount / subtotal) * 100 if subtotal > 0 and tax_amount > 0 else 0.0

        payment_method = data.get("paymentMethod") or data.get("payment_method") or "cash"

        # === PHASE 2: Execute sale (stock deduction + sale record) ===
        success, error, sale = stock_engine.execute_sale(
            items=items,
            account_id=account_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            payment_method=payment_method,
            amount_paid=_safe_float(data.get("amountPaid") or data.get("amount_paid")),
            tax_rate=tax_rate,
            tax_type=tax_type,
            discount_amount=_safe_float(data.get("discount")),
            service_fee=_safe_float(data.get("serviceFee")),
            deduction_plan=deduction_plan   # pass pre-validated plan — skips second DB load
        )

        if not success:
            return jsonify({"success": False, "error": error or "Failed to complete sale"}), 400

        # === PHASE 3: Build response using the pre-validated plan ===
        product_map = deduction_plan.get("product_map", {})
        raw_material_map = deduction_plan.get("raw_material_map", {})
        deduction_details = deduction_plan.get("details", [])

        deduction_sources = {}
        for detail in deduction_details:
            pid = detail.get("product_id")
            parent = detail.get("parent_product")
            if not pid or not parent:
                continue
            deduction_sources.setdefault(int(pid), set()).add(parent)

        product_deductions = []
        affected_product_ids = set()
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
            affected_product_ids.add(product_id)

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

        # === Record ingredient deductions for stock dashboard ===
        now_iso = datetime.utcnow().isoformat()
        for d in product_deductions:
            source_products = sorted(list(deduction_sources.get(int(d["id"]), set())))
            deduction_reason = (
                f"Ingredient used in: {', '.join(source_products)}"
                if source_products
                else "Direct sale"
            )
            deduction_record = {
                "account_id": account_id,
                "item_type": "product",
                "product_id": d["id"],
                "product_name": d["name"],
                "quantity_before": d["before"],
                "quantity_after": d["after"],
                "quantity_deducted": d["deducted"],
                "unit": d["unit"],
                "sale_id": sale.get("id"),
                "payment_method": payment_method,
                "cashier_id": cashier_id,
                "cashier_name": cashier_name,
                "created_at": now_iso,
                "deduction_type": "ingredient",
                "parent_product": source_products[0] if source_products else None,
                "deduction_reason": deduction_reason
            }
            try:
                datastore.create("stock_deductions", deduction_record)
            except Exception:
                pass  # non-critical

        for d in raw_material_deductions:
            deduction_record = {
                "account_id": account_id,
                "item_type": "raw_material",
                "raw_material_id": d["id"],
                "product_name": d["name"],
                "quantity_before": d["before"],
                "quantity_after": d["after"],
                "quantity_deducted": d["deducted"],
                "unit": d["unit"],
                "sale_id": sale.get("id"),
                "payment_method": payment_method,
                "cashier_id": cashier_id,
                "cashier_name": cashier_name,
                "created_at": now_iso,
                "deduction_type": "ingredient",
                "deduction_reason": "Ingredient usage from composite sale"
            }
            try:
                datastore.create("stock_deductions", deduction_record)
            except Exception:
                pass  # non-critical

        # Only return affected products instead of ALL products (faster)
        updated_products = []
        for pid in affected_product_ids:
            p = datastore.get_by_id("products", pid, account_id)
            if p:
                updated_products.append(p)

        # Check low stock only among affected products
        low_stock = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "quantity": p.get("quantity"),
                "unit": p.get("unit", "pcs"),
                "reorder_level": p.get("reorder_level", 0)
            }
            for p in updated_products
            if _safe_float(p.get("quantity")) <= _safe_float(p.get("reorder_level")) and _safe_float(p.get("reorder_level")) > 0
        ]

        # Broadcast updates
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
    # Stock Deductions History (for Stock Dashboard)
    # ============================================================

    @app.get("/api/stock-deductions")
    @require_auth(auth_manager, datastore)
    def get_stock_deductions():
        account_id = request.user.get("account_id")
        limit = int(request.args.get("limit", 200))
        product_id = request.args.get("product_id") or request.args.get("productId")

        deductions = datastore.get_all("stock_deductions", account_id)
        if product_id:
            try:
                pid = int(product_id)
                deductions = [d for d in deductions if int(d.get("product_id") or 0) == pid]
            except (ValueError, TypeError):
                pass

        deductions = sorted(deductions, key=lambda x: x.get("created_at") or "", reverse=True)
        return jsonify(deductions[:limit]), 200

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
    @require_auth(auth_manager, datastore)
    def get_petroleum_tanks():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        tanks = datastore.get_all("petroleum_tanks", account_id)
        return jsonify(tanks), 200

    @app.post("/api/petroleum/tanks")
    @require_business_admin(auth_manager, datastore)
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
    @require_business_admin(auth_manager, datastore)
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
    @require_business_admin(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
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
    @require_business_admin(auth_manager, datastore)
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

        password_hash = auth_manager.hash_password(password)

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
    @require_business_admin(auth_manager, datastore)
    def update_petroleum_staff(staff_id: int):
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        data = request.get_json() or {}

        if "password" in data:
            data["password_hash"] = auth_manager.hash_password(data.get("password"))
            data.pop("password", None)

        ok = datastore.update("petroleum_staff", staff_id, data, account_id)
        if not ok:
            return jsonify({"error": "Staff not found"}), 404
        updated = datastore.get_by_id("petroleum_staff", staff_id, account_id)
        if updated:
            updated.pop("password_hash", None)
        return jsonify(updated), 200

    @app.delete("/api/petroleum/staff/<int:staff_id>")
    @require_business_admin(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
    def get_petroleum_sales():
        deny = _require_petroleum_subscription()
        if deny:
            return deny
        account_id = request.user.get("account_id")
        try:
            sales = datastore.get_all("petroleum_sales", account_id)
            sales = _apply_sort(sales, request.args.get("sort") or "-created_at")
            sales = _apply_limit(sales, request.args.get("limit"))
            return jsonify(sales), 200
        except Exception as exc:
            logger.error("Failed to load petroleum sales: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500

    @app.post("/api/petroleum/sales")
    @require_auth(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
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

    def _normalize_time_entry(entry: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not entry:
            return entry
        normalized = dict(entry)
        normalized["userId"] = normalized.get("user_id")
        normalized["userName"] = normalized.get("user_name")
        normalized["clockInTime"] = normalized.get("clock_in_time")
        normalized["clockOutTime"] = normalized.get("clock_out_time")
        duration_minutes = normalized.get("duration_minutes")
        if duration_minutes is not None:
            normalized["durationMinutes"] = duration_minutes
            normalized["duration"] = duration_minutes
        normalized["status"] = "clocked_out" if normalized.get("clock_out_time") else "clocked_in"
        return normalized

    @app.post("/api/time-entries")
    @require_auth(auth_manager, datastore)
    def create_time_entry():
        data = request.get_json() or {}
        action = (data.get("action") or "").lower()
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        user_name = request.user.get("name") or request.user.get("email")

        if action not in ["clock_in", "clock_out"]:
            return jsonify({"error": "Invalid action"}), 400

        if action == "clock_in":
            success, error, time_entry = time_tracking.clock_in(user_id, user_name, account_id)
            if success:
                sync_manager.broadcast_clock_in(account_id, user_id, user_name, time_entry)
                return jsonify(_normalize_time_entry(time_entry)), 201
            return jsonify({"error": error}), 400

        success, error, time_entry = time_tracking.clock_out(user_id, user_name, account_id)
        if success:
            sync_manager.broadcast_clock_out(account_id, user_id, user_name, time_entry)
            return jsonify(_normalize_time_entry(time_entry)), 200
        return jsonify({"error": error}), 400
    
    @app.get("/api/clock-status")
    @require_auth(auth_manager, datastore)
    def get_clock_status():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        
        status = time_tracking.get_clock_status(user_id, account_id)
        return jsonify(status), 200
    
    @app.get("/api/time-entries")
    @require_auth(auth_manager, datastore)
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
        normalized_entries = [_normalize_time_entry(entry) for entry in entries]
        return jsonify(normalized_entries), 200
    
    @app.get("/api/clock-entries")
    @require_auth(auth_manager, datastore)
    def get_clock_entries():
        # Alias for time-entries
        return get_time_entries()
    
    # ============================================================
    # REMINDERS SYSTEM
    # ============================================================
    
    @app.get("/api/reminders")
    @require_auth(auth_manager, datastore)
    def get_reminders():
        account_id = request.user.get("account_id")
        include_expired = request.args.get("includeExpired") == "true"
        try:
            page = int(request.args.get("page", 1))
            limit = min(int(request.args.get("limit", 20)), 100)
            search = request.args.get("search")
            sort = request.args.get("sort") or "-created_at"
            
            all_reminders = reminders.get_all_reminders(account_id, include_expired)
            
            # Filter by search
            if search:
                search_lower = search.lower()
                all_reminders = [r for r in all_reminders 
                               if search_lower in (r.get("title", "").lower() + " " + r.get("message", "").lower())]
            
            # Sort
            reverse = sort.startswith("-")
            sort_field = sort[1:] if sort.startswith("-") else sort
            all_reminders.sort(key=lambda r: str(r.get(sort_field) or ''), reverse=reverse)
            
            # Paginate
            total = len(all_reminders)
            start = (page - 1) * limit
            end = start + limit
            items = all_reminders[start:end]
            
            return jsonify({
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": max(1, (total + limit - 1) // limit)
            }), 200
        except Exception as exc:
            logger.error("Failed to load reminders: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500
    
    @app.post("/api/reminders")
    @require_auth(auth_manager, datastore)
    def create_reminder():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create reminders
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
    @require_auth(auth_manager, datastore)
    def get_todays_reminders():
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        
        unseen_reminders = reminders.get_unseen_reminders(account_id, user_id)
        return jsonify(unseen_reminders), 200
    
    @app.put("/api/reminders/<int:reminder_id>")
    @require_auth(auth_manager, datastore)
    def mark_reminder_seen(reminder_id: int):
        account_id = request.user.get("account_id")
        user_id = request.user.get("id")
        role = request.user.get("role")
        data = request.get_json(silent=True) or {}

        updates = {}
        if "status" in data:
            updates["status"] = data.get("status")

        if role in ["admin", "main_admin", "owner"]:
            if "note" in data:
                updates["admin_note"] = data.get("note")
            if "signature" in data:
                updates["admin_signature"] = data.get("signature")
                updates["admin_signed_at"] = datetime.utcnow().isoformat()
        else:
            if "note" in data:
                updates["cashier_note"] = data.get("note")
            if "signature" in data:
                updates["cashier_signature"] = data.get("signature")
                updates["cashier_signed_at"] = datetime.utcnow().isoformat()

        if updates:
            reminders.update_reminder(reminder_id, account_id, updates)
        
        success = reminders.mark_reminder_seen(reminder_id, user_id, account_id)
        
        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Failed to mark reminder as seen"}), 400
    
    @app.delete("/api/reminders/<int:reminder_id>")
    @require_auth(auth_manager, datastore)
    def delete_reminder(reminder_id: int):
        account_id = request.user.get("account_id")
        
        # Only admins can delete reminders
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
    @require_auth(auth_manager, datastore)
    def get_credit_requests():
        account_id = request.user.get("account_id")
        user_role = request.user.get("role")
        user_id = request.user.get("id")
        
        try:
            page = int(request.args.get("page", 1))
            limit = min(int(request.args.get("limit", 20)), 100)
            search = request.args.get("search")
            sort = request.args.get("sort") or "-created_at"
            
            if user_role in ["admin", "main_admin", "owner"]:
                # Admins see all requests
                requests_list = credit_requests.get_all_requests(account_id)
            else:
                # Cashiers see only their requests
                requests_list = credit_requests.get_cashier_requests(account_id, user_id)
            
            # Search
            if search:
                search_lower = search.lower()
                requests_list = [r for r in requests_list 
                               if search_lower in (r.get("customer_name", "").lower() + " " + str(r.get("amount", "")))]
            
            # Sort
            reverse = sort.startswith("-")
            sort_field = sort[1:] if sort.startswith("-") else sort
            requests_list.sort(key=lambda r: str(r.get(sort_field) or ''), reverse=reverse)
            
            # Paginate
            total = len(requests_list)
            start = (page - 1) * limit
            end = start + limit
            items = requests_list[start:end]
            
            return jsonify({
                "items": items,
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": max(1, (total + limit - 1) // limit)
            }), 200
        except Exception as exc:
            logger.error("Failed to load credit requests: %s", exc, exc_info=True)
            return jsonify({"error": "Server error - please try again"}), 500
    
    @app.post("/api/credit-requests")
    @require_auth(auth_manager, datastore)
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
    @require_auth(auth_manager, datastore)
    def update_credit_request(request_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        admin_id = request.user.get("id")
        
        # Only admins can approve/reject
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
    @require_auth(auth_manager, datastore)
    def delete_credit_request(request_id: int):
        account_id = request.user.get("account_id")
        
        # Only admins can delete
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
    @require_auth(auth_manager, datastore)
    def get_discounts():
        account_id = request.user.get("account_id")
        active_only = request.args.get("activeOnly") == "true"
        
        if active_only:
            discount_list = discounts.get_active_discounts(account_id)
        else:
            discount_list = datastore.get_all("discounts", account_id)
        
        return jsonify(discount_list), 200
    
    @app.post("/api/discounts")
    @require_auth(auth_manager, datastore)
    def create_discount():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create discounts
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
    @require_auth(auth_manager, datastore)
    def get_service_fees():
        account_id = request.user.get("account_id")
        active_only = request.args.get("activeOnly") == "true"
        
        if active_only:
            fees = service_fees.get_active_service_fees(account_id)
        else:
            fees = service_fees.get_all_service_fees(account_id)
        
        return jsonify(fees), 200
    
    @app.post("/api/service-fees")
    @require_auth(auth_manager, datastore)
    def create_service_fee():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        # Only admins can create service fees
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
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
        payload = auth_manager.verify_token(token)
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

    @sock.route("/ws")
    def ws_generic(ws):
        token = request.args.get("token", "").strip()
        if not token:
            try:
                raw = ws.receive()
                if raw:
                    body = json.loads(raw)
                    token = (body.get("token") or "").strip()
            except Exception:
                pass
        payload = auth_manager.verify_token(token)
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

    @app.post("/api/frontend-errors")
    def frontend_errors():
        data = request.get_json(silent=True) or {}
        logger.warning(f"Frontend error report: {data}")
        return jsonify({"received": True}), 200

    def _bootstrap_main_admin():
        bootstrap_email = (
            os.environ.get("MAIN_ADMIN_EMAIL")
            or os.environ.get("ADMIN_EMAIL")
            or os.environ.get("DEV_ADMIN_EMAIL")
            or ""
        ).strip().lower()
        bootstrap_password = (
            os.environ.get("MAIN_ADMIN_PASSWORD")
            or os.environ.get("ADMIN_PASSWORD")
            or os.environ.get("DEV_ADMIN_PASSWORD")
            or ""
        ).strip()
        bootstrap_hash = (
            os.environ.get("MAIN_ADMIN_HASH")
            or os.environ.get("ADMIN_HASH")
            or os.environ.get("DEV_ADMIN_HASH")
            or ""
        ).strip()

        if not bootstrap_email or not (bootstrap_password or bootstrap_hash):
            return

        try:
            persisted_hash = bootstrap_hash if bootstrap_hash and (bootstrap_hash.startswith("$2a$") or bootstrap_hash.startswith("$2b$") or bootstrap_hash.startswith("$2y$")) else auth_manager.hash_password(bootstrap_password)
            existing = datastore.get_user_by_email(bootstrap_email)
            if existing:
                if existing.get("role") in {"main_admin", "owner"}:
                    if persisted_hash:
                        datastore.update("users", existing.get("id"), {"password_hash": persisted_hash}, existing.get("account_id"))
                    return
                return

            account_id = f"acc_{uuid.uuid4().hex[:12]}"
            account = {
                "id": account_id,
                "owner_email": bootstrap_email,
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
                "screen_lock_password": "",
                "days_used": 0,
                "last_activity_date": None,
                "requested_trial": False,
                "business_type": "main_admin"
            }
            datastore.create("accounts", account)

            datastore.create("users", {
                "account_id": account_id,
                "email": bootstrap_email,
                "password_hash": persisted_hash,
                "name": "Main Admin",
                "role": "main_admin",
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
            logger.info(f"Bootstrapped main admin user: {bootstrap_email}")
        except Exception as e:
            logger.error(f"Main admin bootstrap failed: {e}")

    _bootstrap_main_admin()

    # ============================================================
    # VENDORS SYSTEM
    # ============================================================
    
    @app.get("/api/vendors")
    @require_auth(auth_manager, datastore)
    def get_vendors():
        account_id = request.user.get("account_id")
        vendor_list = datastore.get_all("vendors", account_id)
        return jsonify(vendor_list), 200
    
    @app.post("/api/vendors")
    @require_auth(auth_manager, datastore)
    def create_vendor():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")
        
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can create vendors"}), 403
        
        vendor_data = {
            "account_id": account_id,
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "phone": data.get("phone", ""),
            "address": data.get("address", ""),
            "city": data.get("city", ""),
            "country": data.get("country", ""),
            "product_or_service": data.get("products", ""),
            "created_at": datetime.utcnow().isoformat()
        }
        
        vendor = datastore.create("vendors", vendor_data)
        return jsonify(vendor), 201
    
    @app.put("/api/vendors/<int:vendor_id>")
    @require_auth(auth_manager, datastore)
    def update_vendor(vendor_id):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can update vendors"}), 403
        
        vendor = datastore.get_by_id("vendors", vendor_id, account_id)
        if not vendor:
            return jsonify({"error": "Vendor not found"}), 404
        
        update_data = {
            "name": data.get("name", vendor.get("name")),
            "email": data.get("email", vendor.get("email")),
            "phone": data.get("phone", vendor.get("phone")),
            "address": data.get("address", vendor.get("address")),
            "city": data.get("city", vendor.get("city")),
            "country": data.get("country", vendor.get("country")),
            "product_or_service": data.get("products", vendor.get("product_or_service"))
        }
        
        datastore.update("vendors", vendor_id, update_data, account_id)
        updated_vendor = datastore.get_by_id("vendors", vendor_id, account_id)
        return jsonify(updated_vendor), 200
    
    @app.delete("/api/vendors/<int:vendor_id>")
    @require_auth(auth_manager, datastore)
    def delete_vendor(vendor_id):
        account_id = request.user.get("account_id")
        
        if request.user.get("role") not in ["admin", "main_admin", "owner"]:
            return jsonify({"error": "Only admins can delete vendors"}), 403
        
        vendor = datastore.get_by_id("vendors", vendor_id, account_id)
        if not vendor:
            return jsonify({"error": "Vendor not found"}), 404
        
        datastore.delete("vendors", vendor_id, account_id)
        return jsonify({"success": True}), 200

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
