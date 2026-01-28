"""
Main Flask Application
======================
Unified entrypoint for API endpoints.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime
from typing import Dict, Any

from flask import Flask, jsonify, request
from flask_cors import CORS

from database import DataStore
from stock_engine import StockEngine
from auth_controller import AuthController
from admin_controller import AdminController
from cashier_controller import CashierController

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    app = Flask(__name__)

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

    # ============================================================
    # Health
    # ============================================================

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

    # ============================================================
    # Products
    # ============================================================

    @app.get("/api/products")
    @auth_controller.require_auth
    def get_products():
        account_id = request.user.get("account_id")
        products = admin_controller.get_products(account_id)
        return jsonify(products), 200

    @app.post("/api/products")
    @auth_controller.require_auth
    def create_product():
        data = request.get_json() or {}
        account_id = request.user.get("account_id")
        created_by = request.user.get("id")

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
            recipe=data.get("recipe")
        )

        if not success:
            return jsonify({"error": error or "Failed to create product"}), 400
        return jsonify(product), 201

    @app.put("/api/products/<int:product_id>")
    @auth_controller.require_auth
    def update_product(product_id: int):
        data = request.get_json() or {}
        account_id = request.user.get("account_id")

        success, error, product = admin_controller.update_product(
            product_id=product_id,
            account_id=account_id,
            **data
        )

        if not success:
            return jsonify({"error": error or "Failed to update product"}), 400
        return jsonify(product), 200

    # ============================================================
    # Sales
    # ============================================================

    @app.get("/api/sales")
    @auth_controller.require_auth
    def get_sales():
        account_id = request.user.get("account_id")
        sales = admin_controller.get_sales(account_id)
        return jsonify(sales), 200

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
        return jsonify({"sale": sale}), 201

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
