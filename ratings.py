"""
POSIFY Business Network — Ratings & Reputation
===============================================
Ratings are only creatable by a buyer who has a *completed* delivery for the
subject, so reputation is computed from real transaction outcomes (never
fabricated). Aggregates are computed on read from the ratings table.
"""

from __future__ import annotations

import logging
from flask import request as _req

from auth.decorators import require_auth
from network_models import now_iso, BUSINESS_ADMIN_ROLES
from network_notifications import dispatch_notification

logger = logging.getLogger(__name__)


def register_rating_routes(app, datastore, auth_manager, sync_manager=None,
                            notify_service=None, cache=None):
    auth = require_auth(auth_manager, datastore)

    def _broadcast(account, event, data):
        if sync_manager and account:
            try:
                sync_manager.broadcast_to_account(account, event, data)
            except Exception as e:
                logger.warning("broadcast %s failed: %s", event, e)

    def _notify(account_id, user_id, title, body, extra=None):
        dispatch_notification(datastore, sync_manager, notify_service,
                              account_id, user_id, title, body, extra)

    @app.post("/api/ratings")
    @auth
    def create_rating():
        user = _req.user
        account_id = user["account_id"]
        data = _req.get_json(silent=True) or {}
        rtype = data.get("type") or data.get("subject_type")
        if rtype not in ("business", "rider"):
            return {"error": "type must be 'business' or 'rider'"}, 400
        rating = int(data.get("rating") or 0)
        if rating < 1 or rating > 5:
            return {"error": "rating must be between 1 and 5"}, 400

        delivery_id = data.get("delivery_id")
        order_id = data.get("order_id")
        if not delivery_id and not order_id:
            return {"error": "delivery_id or order_id is required"}, 400

        # Verify the rater has a COMPLETED delivery/order with the subject.
        if delivery_id:
            delivery = datastore.get_by_id("deliveries", int(delivery_id), account_id)
            if not delivery or delivery.get("account_id") != account_id:
                return {"error": "Delivery not found"}, 404
            if delivery.get("status") != "completed":
                return {"error": "Cannot rate before delivery is completed"}, 400
            if rtype == "rider" and delivery.get("rider_id") != int(data.get("rider_id") or 0):
                return {"error": "You can only rate the assigned rider"}, 400
            subject_rider_id = delivery.get("rider_id")
            subject_account = delivery.get("rider_account_id")
        else:
            order = datastore.get_by_id("wholesale_orders", int(order_id), account_id)
            if not order or order.get("account_id") != account_id:
                return {"error": "Order not found"}, 404
            if order.get("status") != "completed":
                return {"error": "Cannot rate before order is completed"}, 400
            subject_rider_id = None
            subject_account = order.get("wholesaler_account_id")

        if rtype == "rider":
            rider = datastore.get_by_id("riders", int(data.get("rider_id") or subject_rider_id), None) \
                if data.get("rider_id") else (
                datastore.get_by_id("riders", subject_rider_id, None) if subject_rider_id else None)
            if not rider:
                return {"error": "Rider not found"}, 404
            subject_account = rider.get("account_id")
        else:
            if not subject_account:
                return {"error": "subject is required for business rating"}, 400

        # prevent double-rating on the same transaction
        existing = datastore.find("ratings", {
            "account_id": account_id, "type": rtype,
            "delivery_id": int(delivery_id) if delivery_id else None,
            "order_id": int(order_id) if order_id else None,
        })
        if existing:
            return {"error": "You have already rated this transaction"}, 400

        now = now_iso()
        rating_row = datastore.create("ratings", {
            "account_id": account_id,
            "type": rtype,
            "subject_account_id": subject_account,
            "rider_id": subject_rider_id if rtype == "rider" else None,
            "order_id": int(order_id) if order_id else None,
            "delivery_id": int(delivery_id) if delivery_id else None,
            "rating": rating,
            "review": data.get("review"),
            "created_at": now,
        })
        # update aggregate on the subject row
        _recalculate_aggregate(datastore, rtype, subject_account, subject_rider_id)
        _broadcast(account_id, "rating_created", {"rating": rating, "type": rtype})
        _notify(account_id, user["id"], "Rating submitted",
                f"Your {rtype} rating has been recorded.", {"type": "rating"})
        return {"rating": rating_row, "success": True}, 201

    @app.get("/api/ratings/summary")
    @auth
    def ratings_summary():
        user = _req.user
        account_id = user["account_id"]
        given_business = datastore.find("ratings", {"account_id": account_id, "type": "business"})
        received_business = datastore.find("ratings", {"subject_account_id": account_id, "type": "business"})
        rs = datastore.find("riders", {"account_id": account_id})
        rider_ids = {r["id"] for r in rs}
        received_rider = [r for r in datastore.get_all("ratings", None)
                          if r.get("type") == "rider" and r.get("rider_id") in rider_ids]
        return {
            "given_business": _stats(given_business),
            "received_business": _stats(received_business),
            "received_rider": _stats(received_rider),
            "success": True,
        }, 200

    @app.get("/api/ratings")
    @auth
    def list_ratings():
        user = _req.user
        account_id = user["account_id"]
        mine = datastore.find("ratings", {"account_id": account_id})
        about_me = datastore.find("ratings", {"subject_account_id": account_id, "type": "business"})
        rs = datastore.find("riders", {"account_id": account_id})
        rider_ids = {r["id"] for r in rs}
        about_riders = [r for r in datastore.get_all("ratings", None)
                        if r.get("type") == "rider" and r.get("rider_id") in rider_ids]
        combined = mine + about_me + about_riders
        combined.sort(key=lambda r: r.get("created_at") or "", reverse=True)
        return {"ratings": combined, "count": len(combined), "success": True}, 200

    @app.post("/api/wholesaler/verification")
    @auth
    def verify_wholesaler_request():
        """Business requests wholesaler verification (admin only)."""
        user = _req.user
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can request verification"}, 403
        account_id = user["account_id"]
        w = datastore.find("wholesalers", {"account_id": account_id})
        if not w:
            return {"error": "No wholesaler profile. Create one first."}, 404
        datastore.update("wholesalers", w[0]["id"], {
            "is_verified": False, "verification_status": "pending", "updated_at": now_iso(),
        })
        _notify(account_id, user["id"], "Verification requested",
                "Your wholesaler profile is pending verification.", {"type": "wholesaler"})
        return {"wholesaler": datastore.get_by_id("wholesalers", w[0]["id"], account_id),
                "success": True}, 200


def _recalculate_aggregate(datastore, rtype, subject_account, rider_id):
    rows = datastore.find("ratings", {"subject_account_id": subject_account, "type": rtype})
    if not rows:
        avg, count = 0.0, 0
    else:
        count = len(rows)
        avg = round(sum(r.get("rating", 0) for r in rows) / count, 2)
    if rtype == "business" and subject_account:
        wrows = datastore.find("wholesalers", {"account_id": subject_account})
        if wrows:
            datastore.update("wholesalers", wrows[0]["id"],
                             {"rating": avg, "order_count": count, "updated_at": now_iso()})
    elif rtype == "rider" and rider_id:
        datastore.update("riders", rider_id, {"rating": avg, "updated_at": now_iso()})


def _stats(rows):
    if not rows:
        return {"average": 0.0, "count": 0, "breakdown": {str(i): 0 for i in range(1, 6)}}
    ratings = [r.get("rating", 0) for r in rows]
    breakdown = {str(i): 0 for i in range(1, 6)}
    for r in ratings:
        key = str(int(r)) if r else "0"
        breakdown[key] = breakdown.get(key, 0) + 1
    return {
        "average": round(sum(ratings) / len(ratings), 2),
        "count": len(ratings),
        "breakdown": breakdown,
    }
