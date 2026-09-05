"""
POSIFY Business Network — Marketplace & Wholesaler module
=========================================================
Public B2B marketplace discovery plus wholesaler-owned self-management of
profiles, wholesale products and wholesale orders.

Public (any authenticated business user):
    GET  /api/marketplace/categories
    GET  /api/marketplace/wholesalers
    GET  /api/marketplace/wholesalers/<id>
    GET  /api/marketplace/wholesalers/<id>/products

Wholesaler self-management (business admin only):
    GET/PUT  /api/wholesaler/profile
    GET/POST /api/wholesale/products
    PUT/DELETE /api/wholesale/products/<id>
    GET      /api/wholesale/orders         (orders addressed to this wholesaler)
    POST     /api/wholesale/orders/<id>/accept|reject|mark-ready|mark-picked-up

Retailer ordering (business admin/cashier):
    POST     /api/wholesale/orders          (create from cart)
    GET      /api/wholesale/orders          (buyer's orders)
    GET      /api/wholesale/orders/<id>
    POST     /api/wholesale/orders/<id>/request-rider
"""

from __future__ import annotations

import logging
from datetime import datetime
from flask import request as _req

from auth.decorators import require_auth
from network_models import (
    now_iso, haversine_km, etamp_from_km, can_transition_order,
    BUSINESS_ADMIN_ROLES,
)
from network_notifications import dispatch_notification

logger = logging.getLogger(__name__)

MARKETPLACE_CATEGORIES = [
    "Fish & Seafood", "Vegetables", "Fruits", "Beverages", "Groceries",
    "Electronics", "Clothing", "Furniture", "Construction Materials",
    "Pharmacy", "Bakery", "Dairy", "Meat & Poultry", "Frozen Foods",
    "Office Supplies", "Hardware", "Flowers", "General Merchandise",
]


def register_marketplace_routes(app, datastore, auth_manager, sync_manager=None,
                                notify_service=None, cache=None):
    auth = require_auth(auth_manager, datastore)

    def _to_float(v):
        try:
            return float(v) if v is not None and v != "" else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [v]
        return list(v)

    def _broadcast(account, event, data):
        if sync_manager is None or account is None:
            return
        try:
            sync_manager.broadcast_to_account(account, event, data)
        except Exception as e:
            logger.warning("broadcast %s failed: %s", event, e)

    def _notify(account_id, user_id, title, body, extra=None):
        dispatch_notification(datastore, sync_manager, notify_service,
                              account_id, user_id, title, body, extra)

    def _invalidate_cache(key):
        if cache and getattr(cache, "enabled", False):
            try:
                cache.delete(key)
            except Exception:
                pass

    # ============================================================ PUBLIC CATALOG
    @app.get("/api/marketplace/categories")
    def marketplace_categories():
        return {"categories": MARKETPLACE_CATEGORIES, "success": True}, 200

    @app.get("/api/marketplace/wholesalers")
    @auth
    def marketplace_wholesalers():
        """Public catalog of verified, active wholesalers (cross-account).

        Optional location filtering uses a real haversine distance server-side
        when lat/lng are supplied; a haversine-based ETA is computed (the
        backend /route endpoint can refine this with OSRM when configured).
        """
        lat = _to_float(_req.args.get("lat")) if _req.args.get("lat") else None
        lng = _to_float(_req.args.get("lng")) if _req.args.get("lng") else None
        radius = _to_float(_req.args.get("radius")) or 15.0
        search = _req.args.get("search")
        category = _req.args.get("category")

        wholesalers = datastore.get_all("wholesalers", None)
        results = []
        for w in wholesalers:
            if not w.get("is_active") or not w.get("is_verified"):
                continue
            if search and search.lower() not in (w.get("business_name") or "").lower():
                continue
            cats = w.get("categories") or []
            if category and category not in cats:
                continue
            item = {k: v for k, v in w.items()
                    if k not in ("account_id", "phone", "email")}
            # recompute aggregate reputation on read (never fabricated)
            item["rating"] = _rating_for_wholesaler(w.get("account_id"))
            item["order_count"] = _order_count_for_wholesaler(w.get("account_id"))
            if lat is not None and lng is not None and w.get("lat") and w.get("lng"):
                dist = haversine_km(lat, lng, w["lat"], w["lng"])
                item["distance_km"] = round(dist, 2)
                item["eta_minutes"] = etamp_from_km(dist)
                if dist > radius:
                    continue
            results.append(item)

        results.sort(key=lambda x: (x.get("distance_km", 99999), -(x.get("rating", 0))))
        return {"wholesalers": results, "count": len(results), "success": True}, 200

    @app.get("/api/marketplace/wholesalers/<int:wholesaler_id>")
    @auth
    def marketplace_wholesaler_detail(wholesaler_id):
        w = datastore.get_by_id("wholesalers", wholesaler_id, None)
        if not w or not w.get("is_active"):
            return {"error": "Wholesaler not found"}, 404
        if not w.get("is_verified"):
            return {"error": "Wholesaler not found"}, 404
        public = {k: v for k, v in w.items()
                  if k not in ("account_id", "phone", "email")}
        products = datastore.find("wholesale_products",
                                  {"account_id": w.get("account_id"), "is_active": True})
        safe_products = [{
            "id": p.get("id"), "name": p.get("name"), "sku": p.get("sku"),
            "category": p.get("category"), "unit": p.get("unit"),
            "price": p.get("price"), "available_quantity": p.get("available_quantity"),
            "min_order_quantity": p.get("min_order_quantity"), "image": p.get("image"),
        } for p in products]
        public["products_preview"] = safe_products[:8]
        public["product_count"] = len(safe_products)
        public["rating"] = _rating_for_wholesaler(w.get("account_id"))
        public["order_count"] = _order_count_for_wholesaler(w.get("account_id"))
        return {"wholesaler": public, "products": safe_products, "success": True}, 200

    @app.get("/api/marketplace/wholesalers/<int:wholesaler_id>/products")
    @auth
    def marketplace_wholesaler_products(wholesaler_id):
        w = datastore.get_by_id("wholesalers", wholesaler_id, None)
        if not w or not w.get("is_active"):
            return {"error": "Wholesaler not found"}, 404
        if not w.get("is_verified"):
            return {"error": "Wholesaler not found"}, 404
        products = datastore.find("wholesale_products",
                                  {"account_id": w.get("account_id"), "is_active": True})
        safe = [{k: v for k, v in p.items() if k != "account_id"} for p in products]
        return {"products": safe, "count": len(safe), "success": True}, 200

    # ============================================================ OWN PROFILE
    @app.get("/api/wholesaler/profile")
    @auth
    def get_wholesaler_profile():
        user = _req.user
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can manage a wholesaler profile"}, 403
        profiles = datastore.find("wholesalers", {"account_id": user["account_id"]})
        if not profiles:
            return {"profile": None, "success": True}, 200
        return {"profile": profiles[0], "success": True}, 200

    @app.put("/api/wholesaler/profile")
    @auth
    def upsert_wholesaler_profile():
        user = _req.user
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can manage a wholesaler profile"}, 403
        data = _req.get_json(silent=True) or {}
        account = datastore.get_by_id("accounts", user["account_id"])
        now = now_iso()
        payload = {
            "account_id": user["account_id"],
            "business_name": data.get("business_name") or account.get("business_name") or user.get("name"),
            "description": data.get("description"),
            "phone": data.get("phone"),
            "email": data.get("email") or user.get("email"),
            "address": data.get("address"),
            "city": data.get("city"),
            "country": data.get("country"),
            "lat": _to_float(data.get("lat")),
            "lng": _to_float(data.get("lng")),
            "categories": _as_list(data.get("categories")),
            "min_order_amount": _to_float(data.get("min_order_amount")),
            "delivery_available": bool(data.get("delivery_available", False)),
            "is_verified": bool(data.get("is_verified", False)),
            "is_active": bool(data.get("is_active", True)),
            "updated_at": now,
        }
        existing = datastore.find("wholesalers", {"account_id": user["account_id"]})
        if existing:
            wid = existing[0].get("id")
            payload["created_at"] = existing[0].get("created_at", now)
            datastore.update("wholesalers", wid, payload)
        else:
            payload["created_at"] = now
            datastore.update("accounts", user["account_id"], {"is_wholesaler": True})
            datastore.create("wholesalers", payload)
        datastore.update("accounts", user["account_id"], {
            "is_wholesaler": True,
            "business_phone": payload["phone"],
            "business_address": payload["address"],
            "business_city": payload["city"],
            "business_country": payload["country"],
            "lat": payload["lat"],
            "lng": payload["lng"],
        })
        profiles = datastore.find("wholesalers", {"account_id": user["account_id"]})
        profile = profiles[0] if profiles else payload
        _broadcast(user["account_id"], "wholesaler_profile_updated",
                   {"profile": profile})
        _notify(user["account_id"], user["id"], "Wholesaler profile updated",
                "Your marketplace profile has been saved.", {"type": "wholesaler"})
        return {"profile": profile, "success": True}, 200

    # ============================================================ WHOLESALE PRODUCTS
    @app.get("/api/wholesale/products")
    @auth
    def list_wholesale_products():
        user = _req.user
        account_id = user["account_id"]
        products = datastore.get_all("wholesale_products", account_id)
        return {"products": products, "count": len(products), "success": True}, 200

    @app.post("/api/wholesale/products")
    @auth
    def create_wholesale_product():
        user = _req.user
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can manage wholesale products"}, 403
        data = _req.get_json(silent=True) or {}
        if not data.get("name"):
            return {"error": "Product name is required"}, 400
        account_id = user["account_id"]
        wprofile = datastore.find("wholesalers", {"account_id": account_id})
        now = now_iso()
        product = datastore.create("wholesale_products", {
            "account_id": account_id,
            "wholesaler_id": wprofile[0].get("id") if wprofile else None,
            "name": data.get("name"),
            "description": data.get("description"),
            "sku": data.get("sku"),
            "category": data.get("category", "general"),
            "unit": data.get("unit", "pcs"),
            "price": _to_float(data.get("price")),
            "cost": _to_float(data.get("cost")),
            "available_quantity": _to_float(data.get("available_quantity")),
            "min_order_quantity": _to_float(data.get("min_order_quantity") or 1),
            "image": data.get("image"),
            "is_active": bool(data.get("is_active", True)),
            "created_at": now,
            "updated_at": now,
        })
        _invalidate_cache(f"wholesale_products:{account_id}")
        return {"product": product, "success": True}, 201

    @app.put("/api/wholesale/products/<int:product_id>")
    @auth
    def update_wholesale_product(product_id):
        user = _req.user
        account_id = user["account_id"]
        product = datastore.get_by_id("wholesale_products", product_id, account_id)
        if not product:
            return {"error": "Product not found"}, 404
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Not allowed"}, 403
        data = _req.get_json(silent=True) or {}
        update = {k: data[k] for k in
                  ("name", "description", "sku", "category", "unit", "image", "is_active")
                  if k in data}
        for num_field in ("price", "cost", "available_quantity", "min_order_quantity"):
            if num_field in data:
                update[num_field] = _to_float(data[num_field])
        update["updated_at"] = now_iso()
        datastore.update("wholesale_products", product_id, update, account_id)
        _invalidate_cache(f"wholesale_products:{account_id}")
        return {"product": datastore.get_by_id("wholesale_products", product_id, account_id),
                "success": True}, 200

    @app.delete("/api/wholesale/products/<int:product_id>")
    @auth
    def delete_wholesale_product(product_id):
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can delete wholesale products"}, 403
        if not datastore.get_by_id("wholesale_products", product_id, account_id):
            return {"error": "Product not found"}, 404
        datastore.delete("wholesale_products", product_id, account_id)
        _invalidate_cache(f"wholesale_products:{account_id}")
        return {"success": True}, 200

    # ============================================================ WHOLESALE ORDERS
    @app.get("/api/wholesale/orders")
    @auth
    def list_wholesale_orders():
        user = _req.user
        account_id = user["account_id"]
        orders = datastore.find("wholesale_orders", {"account_id": account_id})
        _annotate_orders(orders)
        return {"orders": orders, "count": len(orders), "success": True}, 200

    @app.post("/api/wholesale/orders")
    @auth
    def create_wholesale_order():
        """Create a wholesale order from a cart submitted by the buying business."""
        user = _req.user
        data = _req.get_json(silent=True) or {}
        account_id = user["account_id"]
        if not data.get("wholesaler_id") and not data.get("wholesaler_account_id"):
            return {"error": "wholesaler is required"}, 400
        items = data.get("items") or []
        if not items:
            return {"error": "Order must contain at least one item"}, 400

        wholesaler = datastore.get_by_id("wholesalers", int(data["wholesaler_id"]), None) \
            if data.get("wholesaler_id") else None
        if not wholesaler:
            wprofiles = datastore.find("wholesalers", {"account_id": data.get("wholesaler_account_id")})
            wholesaler = wprofiles[0] if wprofiles else None
        if not wholesaler:
            return {"error": "Wholesaler not found"}, 404
        if not wholesaler.get("is_active"):
            return {"error": "Wholesaler is not accepting orders"}, 400

        now = now_iso()
        sub_total = 0.0
        resolved_items = []
        for it in items:
            pid = int(it.get("product_id"))
            wp = datastore.get_by_id("wholesale_products", pid, None)
            if not wp or not wp.get("is_active"):
                return {"error": f"Product not available: {it.get('name')}"}, 400
            qty = _to_float(it.get("quantity"))
            if qty <= 0:
                return {"error": f"Invalid quantity for {wp.get('name')}"}, 400
            min_qty = _to_float(wp.get("min_order_quantity") or 1)
            if qty < min_qty:
                return {"error": f"{wp.get('name')} minimum order is {min_qty}"}, 400
            unit_price = _to_float(wp.get("price"))
            line_total = round(qty * unit_price, 2)
            sub_total += line_total
            resolved_items.append({
                "product_id": pid, "name": wp.get("name"), "sku": wp.get("sku"),
                "unit": wp.get("unit", "pcs"), "quantity": qty,
                "unit_price": unit_price, "total": line_total,
            })

        order = datastore.create("wholesale_orders", {
            "account_id": account_id,
            "wholesaler_account_id": wholesaler.get("account_id"),
            "wholesaler_id": wholesaler.get("id"),
            "status": "pending", "order_status": "pending",
            "sub_total": round(sub_total, 2),
            "total_amount": round(sub_total, 2),
            "tax_amount": 0.0, "discount_amount": 0.0,
            "deposit_amount": _to_float(data.get("deposit_amount")),
            "currency": data.get("currency", "KES"),
            "payment_status": "pending",
            "delivery_location": data.get("delivery_location"),
            "pickup_location": data.get("pickup_location"),
            "notes": data.get("notes"),
            "created_at": now, "updated_at": now,
        })
        for ri in resolved_items:
            datastore.create("wholesale_order_items", {
                "order_id": order["id"], "product_id": ri["product_id"],
                "name": ri["name"], "sku": ri["sku"], "unit": ri["unit"],
                "quantity": ri["quantity"], "unit_price": ri["unit_price"],
                "total": ri["total"], "created_at": now,
            })
        _broadcast(wholesaler.get("account_id"), "wholesale_order_new",
                   {"order_id": order["id"], "buyer_account_id": account_id,
                    "amount": order["total_amount"], "created_at": now})
        _notify(wholesaler.get("account_id"), None, "New wholesale order",
                f"New order #{order['id']} has been placed.",
                {"type": "order", "order_id": order["id"]})
        return {"order": order, "success": True}, 201

    @app.get("/api/wholesale/orders/<int:order_id>")
    @auth
    def get_wholesale_order(order_id):
        user = _req.user
        account_id = user["account_id"]
        order = datastore.get_by_id("wholesale_orders", order_id, account_id)
        if not order:
            found = datastore.find("wholesale_orders",
                                   {"wholesaler_account_id": account_id, "id": order_id})
            order = found[0] if found else None
        if not order:
            return {"error": "Order not found"}, 404
        _annotate_order(order)
        order["self_as_wholesaler"] = order.get("wholesaler_account_id") == account_id
        return {"order": order, "success": True}, 200

    # ---- Wholesaler status transitions (seller side) ----
    def _seller_order(order_id):
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return None
        orders = datastore.find("wholesale_orders",
                                {"wholesaler_account_id": account_id, "id": order_id})
        return orders[0] if orders else None

    def _transition_seller_order(order_id, target):
        order = _seller_order(order_id)
        if not order:
            return None, ({"error": "Order not found"}, 404)
        if not can_transition_order(order.get("status"), target):
            return None, ({"error": f"Cannot move order to {target}"}, 400)
        _record_order_event(order["id"], order.get("status"), target, "wholesaler")
        datastore.update("wholesale_orders", order["id"],
                         {"status": target, "order_status": target, "updated_at": now_iso()})
        _broadcast(order.get("wholesaler_account_id"), "wholesale_order_status",
                   {"order_id": order["id"], "status": target})
        if target in ("accepted", "rejected"):
            _notify(order["account_id"], None,
                    f"Order {target}",
                    f"Wholesaler {target} order #{order['id']}.",
                    {"type": "order", "order_id": order["id"]})
        return order, None

    @app.post("/api/wholesale/orders/<int:order_id>/accept")
    @auth
    def accept_wholesale_order(order_id):
        order, err = _transition_seller_order(order_id, "accepted")
        if err:
            return err
        return {"order": _refresh_order(order_id), "success": True}, 200

    @app.post("/api/wholesale/orders/<int:order_id>/reject")
    @auth
    def reject_wholesale_order(order_id):
        order, err = _transition_seller_order(order_id, "rejected")
        if err:
            return err
        return {"order": _refresh_order(order_id), "success": True}, 200

    @app.post("/api/wholesale/orders/<int:order_id>/mark-ready")
    @auth
    def mark_order_ready(order_id):
        order, err = _transition_seller_order(order_id, "ready_for_pickup")
        if err:
            return err
        return {"order": _refresh_order(order_id), "success": True}, 200

    @app.post("/api/wholesale/orders/<int:order_id>/mark-picked-up")
    @auth
    def mark_order_picked_up(order_id):
        order, err = _transition_seller_order(order_id, "picked_up")
        if err:
            return err
        return {"order": _refresh_order(order_id), "success": True}, 200

    @app.get("/api/wholesale/orders/seller")
    @auth
    def seller_orders():
        """Orders addressed to this wholesaler (seller view)."""
        user = _req.user
        account_id = user["account_id"]
        orders = datastore.find("wholesale_orders", {"wholesaler_account_id": account_id})
        _annotate_orders(orders)
        return {"orders": orders, "count": len(orders), "success": True}, 200

    # ============================================================ REQUEST RIDER
    @app.post("/api/wholesale/orders/<int:order_id>/request-rider")
    @auth
    def request_rider_for_order(order_id):
        user = _req.user
        account_id = user["account_id"]
        order = datastore.get_by_id("wholesale_orders", order_id, account_id)
        if not order:
            return {"error": "Order not found"}, 404
        if order.get("status") not in {"pending", "accepted", "preparing", "ready_for_pickup"}:
            return {"error": "Order cannot accept a rider in its current state"}, 400
        now = now_iso()
        pickup = order.get("pickup_location") or {}
        dropoff = order.get("delivery_location") or {}
        delivery = datastore.create("deliveries", {
            "account_id": account_id,
            "wholesale_order_id": order["id"],
            "rider_id": None, "rider_account_id": None,
            "status": "rider_requested",
            "pickup_location": pickup, "dropoff_location": dropoff,
            "route": None, "distance": None, "eta_minutes": None,
            "fare": 0.0, "commission": 0.0, "rider_earnings": 0.0,
            "created_at": now, "updated_at": now,
        })
        datastore.update("wholesale_orders", order["id"],
                         {"delivery_id": delivery["id"], "status": "ready_for_pickup",
                          "order_status": "ready_for_pickup"}, account_id)
        _record_event(delivery["id"], None, "rider_requested", user["id"], None)
        _broadcast(account_id, "delivery_rider_requested",
                   {"delivery_id": delivery["id"], "order_id": order["id"]})
        _notify(account_id, user["id"], "Rider requested",
                "Looking for nearby riders for your order.",
                {"type": "delivery", "delivery_id": delivery["id"]})
        return {"delivery": delivery, "success": True}, 200

    # ============================================================ INTERNAL HELPERS
    def _annotate_orders(orders):
        for o in orders:
            _annotate_order(o)

    def _annotate_order(order):
        oid = order.get("id")
        order["items"] = datastore.find("wholesale_order_items", {"order_id": oid})
        order["item_count"] = len(order["items"])
        payments_tx = datastore.find("payment_transactions", {"order_id": oid})
        order["payment_transaction"] = payments_tx[0] if payments_tx else None
        if order.get("delivery_id"):
            order["delivery"] = datastore.get_by_id("deliveries", order.get("delivery_id"), None)

    def _refresh_order(order_id):
        o = datastore.get_by_id("wholesale_orders", order_id, None)
        if o:
            o["items"] = datastore.find("wholesale_order_items", {"order_id": order_id})
        return o

    def _record_order_event(order_id, from_status, to_status, actor, notes=None):
        datastore.create("delivery_events", {
            "delivery_id": None,
            "status_from": from_status, "status_to": to_status,
            "actor": actor, "actor_id": None, "notes": notes,
            "metadata": {"order_id": order_id, "type": "order"},
            "created_at": now_iso(),
        })

    def _record_event(delivery_id, from_status, to_status, actor_id, location=None):
        datastore.create("delivery_events", {
            "delivery_id": delivery_id,
            "status_from": from_status, "status_to": to_status,
            "actor": "rider" if actor_id else "system",
            "actor_id": actor_id, "notes": None, "latitude": None, "longitude": None,
            "metadata": {"type": "delivery"},
            "created_at": now_iso(),
        })

    def _rating_for_wholesaler(account_id):
        rows = datastore.find("ratings", {"subject_account_id": account_id, "type": "business"})
        if not rows:
            return 0.0
        return round(sum(r.get("rating", 0) for r in rows) / len(rows), 2)

    def _order_count_for_wholesaler(account_id):
        # count completed orders for this wholesaler account
        orders = datastore.get_all("wholesale_orders", None)
        count = sum(1 for o in orders
                    if o.get("wholesaler_account_id") == account_id
                    and o.get("status") in {"completed", "delivered"})
        return count


def register_network_routes(app, datastore, auth_manager, sync_manager=None,
                            notify_service=None, cache=None):
    """Backwards-compatible alias (deprecated). Prefer register_marketplace_routes."""
    register_marketplace_routes(app, datastore, auth_manager, sync_manager,
                                notify_service, cache)
