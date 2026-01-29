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

    # CORS
    cors_origins = os.environ.get("CORS_ORIGINS", "*")
    if cors_origins == "*":
        CORS(app)
    else:
        CORS(app, resources={r"/*": {"origins": [o.strip() for o in cors_origins.split(",") if o.strip()]}})

    # Services
    use_postgres = bool(os.environ.get("DATABASE_URL"))
    datastore = DataStore(data_dir=os.environ.get("DATA_DIR"), use_postgres=use_postgres)
    stock_engine = StockEngine(datastore)
    auth_controller = AuthController(datastore, app.config["SECRET_KEY"])
    admin_controller = AdminController(datastore, stock_engine)
    cashier_controller = CashierController(datastore, stock_engine)

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
            return jsonify(result), 201
        return jsonify({"error": error or "Signup failed"}), 400

    @app.post("/api/auth/login")
    def login():
        data = request.get_json() or {}
        success, error, result = auth_controller.login(
            email=data.get("email"),
            password=data.get("password")
        )
        if success:
            return jsonify(result), 200
        return jsonify({"error": error or "Invalid credentials"}), 401

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
    # Products
    # ============================================================

    @app.get("/api/products")
    @auth_controller.require_auth
    def get_products():
        account_id = request.user.get("account_id")
        products = admin_controller.get_products(account_id)
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
        return jsonify(product), 200

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
        products = datastore.get_all("products", account_id)
        sales = datastore.get_all("sales", account_id)
        expenses = datastore.get_all("expenses", account_id)

        total_sales = sum(_safe_float(s.get("total")) for s in sales)
        total_cost = sum(_safe_float(s.get("total_cost")) for s in sales)
        total_expenses = sum(_safe_float(e.get("amount")) for e in expenses)
        profit = total_sales - total_cost - total_expenses

        return jsonify({
            "totalSales": total_sales,
            "totalExpenses": total_expenses,
            "profit": profit,
            "productsCount": len(products),
            "salesCount": len(sales)
        }), 200

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

        for item in data.get("items", []):
            product_id = item.get("product_id") or item.get("productId")
            if not product_id:
                continue
            product = datastore.get_by_id("products", product_id, account_id)
            if product:
                sync_manager.broadcast_stock_update(account_id, product_id, product.get("quantity"))
        return jsonify({"sale": sale}), 201

    # ============================================================
    # WebSocket
    # ============================================================

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
