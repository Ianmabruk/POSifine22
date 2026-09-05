"""
POSIFY Business Network — Rider Network & Delivery Logistics
============================================================
Rider registration/profile/verification, online presence, latest-location
persistence, nearby-rider discovery (real haversine distance), the delivery
state machine, and per-delivery event audit trail.

Routes
------
Rider self-service (role == rider):
    PUT    /api/rider/profile
    GET    /api/rider/profile
    PUT    /api/rider/verification
    POST   /api/rider/location          (REST fallback for latest position)
    GET    /api/rider/availability

Rider registration (public):
    POST   /api/rider/register

Business (admin/cashier):
    GET    /api/riders/nearby?lat=&lng=&radius=
    GET    /api/riders/<rider_id>

Deliveries (state machine driven by rider; confirmed by buyer):
    GET    /api/deliveries
    GET    /api/deliveries/<id>
    GET    /api/deliveries/<id>/events
    POST   /api/deliveries/<id>/assign        (buyer assigns a rider)
    POST   /api/deliveries/<id>/update-status (rider drives transitions)
    POST   /api/deliveries/<id>/confirm       (buyer confirms)
    POST   /api/deliveries/<id>/cancel        (buyer/rejects)
"""

from __future__ import annotations

import logging
from datetime import datetime
from flask import request as _req

from auth.decorators import require_auth, require_rider
from network_models import (
    now_iso, haversine_km, etamp_from_km, location_is_fresh,
    can_transition_delivery, allowed_delivery_transitions, RIDER_LOCATION_FRESH_SECONDS,
)
from network_notifications import dispatch_notification

logger = logging.getLogger(__name__)

RIDER_ROLES = ("rider",)


def persist_rider_location(datastore, rider, lat, lng, accuracy=0.0, speed=0.0,
                           heading=0.0, timestamp=None, status="available",
                           delivery_id=None, on_broadcast=None):
    """Persist a rider's latest position (single-latest-row policy) and mirror
    lat/lng onto the rider row for proximity discovery.

    `on_broadcast(location_payload)` is invoked, if provided, so the caller can fan
    the position out to active delivery subscribers.
    """
    if not lat or not lng:
        return None
    now = now_iso()
    ts = timestamp or now
    prev = datastore.find("rider_locations", {"rider_id": rider["id"]})
    loc_payload = {
        "rider_id": rider["id"], "user_id": rider.get("user_id"),
        "latitude": lat, "longitude": lng, "accuracy": accuracy,
        "speed": speed, "heading": heading, "timestamp": ts,
        "status": status, "current_delivery_id": delivery_id,
        "is_fresh": True, "created_at": now,
    }
    if prev:
        datastore.update("rider_locations", prev[0]["id"], loc_payload, rider.get("account_id"))
    else:
        datastore.create("rider_locations", loc_payload)
    datastore.update("riders", rider["id"], {
        "lat": lat, "lng": lng, "last_location_at": ts, "is_online": True,
    }, rider.get("account_id"))
    if on_broadcast and delivery_id:
        on_broadcast({"rider_id": rider["id"], "user_id": rider.get("user_id"),
                      "latitude": lat, "longitude": lng, "accuracy": accuracy,
                      "speed": speed, "heading": heading, "timestamp": ts})
    return loc_payload


def find_rider_by_user(datastore, user_id):
    riders = datastore.find("riders", {"user_id": user_id})
    return riders[0] if riders else None


def register_rider_routes(app, datastore, auth_manager, sync_manager=None,
                          notify_service=None, cache=None, geo_proxy=None):
    auth = require_auth(auth_manager, datastore)
    rider_auth = require_rider(auth_manager, datastore)

    def _to_float(v):
        try:
            return float(v) if v is not None and v != "" else 0.0
        except (TypeError, ValueError):
            return 0.0

    def _broadcast(account, event, data):
        if sync_manager is None or account is None:
            return
        try:
            sync_manager.broadcast_to_account(account, event, data)
        except Exception as e:
            logger.warning("broadcast %s failed: %s", event, e)

    def _broadcast_user(user_id, event, data):
        if sync_manager is None or user_id is None:
            return
        try:
            sync_manager.broadcast_to_user(user_id, event, data)
        except Exception as e:
            logger.warning("user broadcast %s failed: %s", event, e)

    def _notify(account_id, user_id, title, body, extra=None):
        dispatch_notification(datastore, sync_manager, notify_service,
                              account_id, user_id, title, body, extra)

    # ============================================================ RIDER REGISTER
    @app.post("/api/rider/register")
    def rider_register():
        data = _req.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        name = (data.get("name") or "").strip()
        password = data.get("password")
        phone = (data.get("phone") or "").strip()
        vehicle_type = data.get("vehicle_type") or "motorcycle"
        if not email or not name or not password:
            return {"error": "email, name and password are required"}, 400
        if len(password) < 6:
            return {"error": "Password must be at least 6 characters"}, 400
        existing = datastore.get_user_by_email(email)
        if existing:
            return {"error": "Email already registered"}, 400

        import bcrypt
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        now = now_iso()
        account_id = f"rider_{email.split('@')[0]}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        account_id = f"rdr_{account_id[-12:]}"

        account = {
            "id": account_id,
            "owner_email": email,
            "business_name": data.get("business_name") or name,
            "plan": "rider",
            "is_active": True,
            "is_locked": False,
            "trial_ends_at": None,
            "subscription_ends_at": None,
            "created_at": now,
            "business_logo": None,
            "currency": data.get("currency", "KES"),
            "tax_rate": 0.0,
            "screen_lock_password": "",
            "days_used": 0,
            "last_activity_date": None,
            "requested_trial": False,
            "business_type": "rider",
            "is_wholesaler": False,
            "payment_required": False,
        }
        datastore.create("accounts", account)

        user = datastore.create("users", {
            "account_id": account_id,
            "email": email,
            "password_hash": password_hash,
            "name": name,
            "role": "rider",
            "is_active": True,
            "is_locked": False,
            "screen_locked": False,
            "created_at": now,
            "created_by": None,
            "last_login": None,
            "hourly_rate": 0.0,
            "business_type": "rider",
            "business_role": "rider",
            "profile_picture": data.get("profile_picture"),
        })
        rider = datastore.create("riders", {
            "account_id": account_id,
            "user_id": user.get("id"),
            "name": name,
            "phone": phone,
            "email": email,
            "vehicle_type": vehicle_type,
            "license_plate": data.get("license_plate"),
            "license_number": data.get("license_number"),
            "license_image": data.get("license_image"),
            "is_verified": False,
            "verification_status": "pending",
            "verification_notes": None,
            "is_online": False,
            "is_available": False,
            "current_status": "offline",
            "rating": 0.0,
            "completed_deliveries": 0,
            "cancellation_rate": 0.0,
            "earnings": 0.0,
            "lat": _to_float(data.get("lat")),
            "lng": _to_float(data.get("lng")),
            "last_location_at": None,
            "created_at": now,
            "updated_at": now,
        })

        token = auth_manager.generate_token(user)
        _notify(account_id, user["id"], "Rider account created",
                "Welcome to Posify Rider. Submit vehicle documents to start accepting deliveries.",
                {"type": "rider"})
        return ({"token": token, "user": _safe_user(user), "rider": _public_rider(rider),
                 "success": True}, 201)

    # ============================================================ RIDER PROFILE
    @app.get("/api/rider/profile")
    @rider_auth
    def get_rider_profile():
        rider = getattr(_req, "rider", None)
        return {"rider": _public_rider(rider), "success": True}, 200

    @app.put("/api/rider/profile")
    @rider_auth
    def update_rider_profile():
        rider = getattr(_req, "rider", None)
        data = _req.get_json(silent=True) or {}
        now = now_iso()
        updates = {k: v for k, v in {
            "name": data.get("name") or rider.get("name"),
            "phone": data.get("phone") if "phone" in data else rider.get("phone"),
            "vehicle_type": data.get("vehicle_type") if "vehicle_type" in data else rider.get("vehicle_type"),
            "license_plate": data.get("license_plate") if "license_plate" in data else rider.get("license_plate"),
            "updated_at": now,
        }.items() if v is not None}
        datastore.update("riders", rider["id"], updates, rider.get("account_id"))
        return {"rider": _public_rider(datastore.get_by_id("riders", rider["id"], rider.get("account_id"))),
                "success": True}, 200

    @app.put("/api/rider/verification")
    @rider_auth
    def submit_verification():
        rider = getattr(_req, "rider", None)
        data = _req.get_json(silent=True) or {}
        now = now_iso()
        # Only allow moving from pending/rejected back to pending (resubmit)
        datastore.update("riders", rider["id"], {
            "license_image": data.get("license_image", rider.get("license_image")),
            "license_number": data.get("license_number", rider.get("license_number")),
            "license_plate": data.get("license_plate", rider.get("license_plate")),
            "verification_status": "pending",
            "is_verified": False,
            "verification_notes": None,
            "vehicle_type": data.get("vehicle_type", rider.get("vehicle_type")),
            "updated_at": now,
        }, rider.get("account_id"))
        _notify(rider.get("account_id"), rider.get("user_id"), "Verification submitted",
                "Your rider documents are under review.", {"type": "verification"})
        return {"rider": _public_rider(datastore.get_by_id("riders", rider["id"], rider.get("account_id"))),
                "success": True}, 200

    # ============================================================ RIDER LOCATION
    @app.post("/api/rider/location")
    @rider_auth
    def update_rider_location():
        """Persist the rider's latest location. The WebSocket handler also calls
        this so all position updates have a single source of truth."""
        rider = getattr(_req, "rider", None)
        data = _req.get_json(silent=True) or {}
        lat = _to_float(data.get("latitude", data.get("lat")))
        lng = _to_float(data.get("longitude", data.get("lng")))
        if not lat or not lng:
            return {"error": "latitude and longitude are required"}, 400
        delivery_id = data.get("current_delivery_id")

        def _broadcast(delivery_id, event, payload):
            _broadcast_delivery(delivery_id, event, payload)

        loc = persist_rider_location(
            datastore, rider, lat, lng,
            accuracy=_to_float(data.get("accuracy")),
            speed=_to_float(data.get("speed")),
            heading=_to_float(data.get("heading")),
            timestamp=data.get("timestamp"),
            status=data.get("status") or "available",
            delivery_id=delivery_id,
            on_broadcast=(lambda p: _broadcast(delivery_id, "rider_location", p)) if delivery_id else None,
        )
        return {"location": loc, "success": True}, 200

    @app.get("/api/rider/availability")
    @rider_auth
    def rider_availability():
        rider = getattr(_req, "rider", None)
        return {"rider": _public_rider(rider),
                "available": bool(rider.get("is_available")),
                "success": True}, 200

    # ============================================================ NEARBY DISCOVERY
    @app.get("/api/riders/nearby")
    @auth
    def nearby_riders():
        """Businesses see nearby available + verified riders (pre-assignment)."""
        lat = _to_float(_req.args.get("lat")) if _req.args.get("lat") else None
        lng = _to_float(_req.args.get("lng")) if _req.args.get("lng") else None
        radius = _to_float(_req.args.get("radius")) or 15.0
        if lat is None or lng is None:
            return {"error": "lat and lng query params are required"}, 400
        riders = datastore.get_all("riders", None)
        result = []
        for r in riders:
            if not (r.get("is_online") and r.get("is_available") and r.get("is_verified")):
                continue
            rl = r.get("lat"), r.get("lng")
            if not r.get("lat") or not r.get("lng"):
                continue
            dist = haversine_km(lat, lng, r["lat"], r["lng"])
            if dist > radius:
                continue
            eta = etamp_from_km(dist)
            # use OSRM ETA when configured
            eta = _eta_route(lat, lng, r["lat"], r["lng"], eta, geo_proxy)
            result.append({
                "id": r.get("id"), "name": r.get("name"),
                "vehicle_type": r.get("vehicle_type"),
                "rating": r.get("rating"),
                "completed_deliveries": r.get("completed_deliveries"),
                "distance_km": round(dist, 2),
                "eta_minutes": eta,
            })
        result.sort(key=lambda x: (x["distance_km"], -x["rating"]))
        return {"riders": result, "count": len(result), "success": True}, 200

    @app.get("/api/riders/<int:rider_id>")
    @auth
    def rider_detail(rider_id):
        rider = datastore.get_by_id("riders", rider_id, None)
        if not rider:
            return {"error": "Rider not found"}, 404
        return {"rider": _public_rider(rider), "success": True}, 200

    @app.post("/api/riders/<int:rider_id>/verify")
    @auth
    def verify_rider(rider_id):
        """Platform admin verifies a rider so they can accept deliveries."""
        user = _req.user
        if user.get("role") not in {"main_admin", "owner"}:
            return {"error": "Only platform admins can verify riders"}, 403
        rider = datastore.get_by_id("riders", rider_id, None)
        if not rider:
            return {"error": "Rider not found"}, 404
        data = _req.get_json(silent=True) or {}
        now = now_iso()
        datastore.update("riders", rider_id, {
            "is_verified": True,
            "verification_status": "verified",
            "verification_notes": data.get("notes"),
            "updated_at": now,
        })
        # propagate to the rider's user row so discovery/availability reflect it
        if rider.get("user_id"):
            try:
                datastore.update("users", rider["user_id"], {"is_active": True}, rider.get("account_id"))
            except Exception:
                pass
        _broadcast(rider.get("account_id"), "rider_verified", {"rider_id": rider_id})
        _notify(rider.get("account_id"), rider.get("user_id"), "Rider verified",
                "Your rider account has been verified.", {"type": "verification"})
        return {"rider": _public_rider(datastore.get_by_id("riders", rider_id, None)),
                "success": True}, 200

    @app.put("/api/rider/availability")
    @rider_auth
    def set_rider_availability():
        rider = getattr(_req, "rider", None)
        data = _req.get_json(silent=True) or {}
        now = now_iso()
        is_online = bool(data.get("is_online", rider.get("is_online")))
        is_available = bool(data.get("is_available", False)) if is_online else False
        status = "available" if is_available else ("online" if is_online else "offline")
        datastore.update("riders", rider["id"], {
            "is_online": is_online, "is_available": is_available,
            "current_status": status, "updated_at": now,
        }, rider.get("account_id"))
        _broadcast(rider.get("account_id"), "rider_availability",
                   {"rider_id": rider["id"], "is_online": is_online, "is_available": is_available})
        return {"rider": _public_rider(datastore.get_by_id("riders", rider["id"], rider.get("account_id"))),
                "success": True}, 200


    # ============================================================ DELIVERIES
    @app.get("/api/deliveries")
    @auth
    def list_deliveries():
        user = _req.user
        account_id = user["account_id"]
        # buyer sees deliveries where account_id == buyer; rider sees own deliveries
        if user.get("role") == "rider":
            rider = datastore.find("riders", {"user_id": user["id"]})
            if not rider:
                return {"deliveries": [], "count": 0, "success": True}, 200
            deliveries = datastore.find("deliveries", {"rider_id": rider[0]["id"]})
        else:
            deliveries = datastore.find("deliveries", {"account_id": account_id})
        _annotate_deliveries(deliveries)
        return {"deliveries": deliveries, "count": len(deliveries), "success": True}, 200

    @app.get("/api/deliveries/<int:delivery_id>")
    @auth
    def get_delivery(delivery_id):
        user = _req.user
        delivery = _get_accessible_delivery(delivery_id, user)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        _annotate_delivery(delivery)
        delivery["allowed_transitions"] = allowed_delivery_transitions(delivery.get("status"))
        return {"delivery": delivery, "success": True}, 200

    @app.get("/api/deliveries/<int:delivery_id>/events")
    @auth
    def delivery_events(delivery_id):
        user = _req.user
        delivery = _get_accessible_delivery(delivery_id, user)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        events = datastore.find("delivery_events", {"delivery_id": delivery_id})
        events.sort(key=lambda e: e.get("created_at") or "")
        return {"events": events, "count": len(events), "success": True}, 200

    @app.post("/api/deliveries/<int:delivery_id>/assign")
    @auth
    def assign_rider(delivery_id):
        user = _req.user
        if user.get("role") not in {"main_admin", "owner", "admin", "cashier"}:
            return {"error": "Only business users can assign riders"}, 403
        account_id = user["account_id"]
        delivery = datastore.get_by_id("deliveries", delivery_id, account_id)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        if delivery.get("status") not in {"rider_requested", "awaiting_rider"}:
            return {"error": "Delivery is not awaiting a rider"}, 400
        data = _req.get_json(silent=True) or {}
        rider_id = data.get("rider_id")
        if not rider_id:
            return {"error": "rider_id is required"}, 400
        rider = datastore.get_by_id("riders", int(rider_id), None)
        if not rider:
            return {"error": "Rider not found"}, 404
        if not (rider.get("is_online") and rider.get("is_available") and rider.get("is_verified")):
            return {"error": "Rider is not available"}, 400
        now = now_iso()
        datastore.update("deliveries", delivery["id"], {
            "rider_id": rider["id"], "rider_account_id": rider.get("account_id"),
            "status": "rider_assigned", "updated_at": now,
        }, account_id)
        _record_delivery_event(delivery["id"], "rider_requested", "rider_assigned", "buyer", user["id"])
        # make rider busy + broadcast assignment
        datastore.update("riders", rider["id"], {"is_available": False, "current_status": "busy"}, rider.get("account_id"))
        _broadcast(user["account_id"], "delivery_assigned",
                   {"delivery_id": delivery["id"], "rider": _public_rider(rider)})
        _broadcast_user(rider.get("user_id"), "delivery_assigned",
                        {"delivery_id": delivery["id"], "buyer_account_id": account_id})
        _notify(rider.get("account_id"), rider.get("user_id"), "New delivery",
                f"You've been assigned delivery #{delivery['id']}.", {"type": "delivery", "delivery_id": delivery["id"]})
        _notify(user["account_id"], user["id"], "Rider assigned",
                f"Rider {rider.get('name')} accepted your delivery.", {"type": "delivery", "delivery_id": delivery["id"]})
        return {"delivery": _annotate_delivery(datastore.get_by_id("deliveries", delivery["id"], account_id)),
                "success": True}, 200

    @app.post("/api/deliveries/<int:delivery_id>/update-status")
    @rider_auth
    def rider_update_status(delivery_id):
        rider = getattr(_req, "rider", None)
        delivery = datastore.get_by_id("deliveries", delivery_id)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        if delivery.get("rider_id") != rider.get("id"):
            return {"error": "This delivery is not assigned to you"}, 403
        data = _req.get_json(silent=True) or {}
        target = data.get("status") or data.get("to_status")
        from_loc = delivery.get("status")
        if not target or target == from_loc:
            return {"error": "status is required"}, 400
        if not can_transition_delivery(from_loc, target):
            return {"error": f"Cannot transition from {from_loc} to {target}"}, 400
        # Riders may only drive logistics-side transitions
        allowed_for_rider = {"rider_going_to_pickup", "rider_at_pickup", "goods_collected",
                             "in_transit", "near_destination",
                             "delivered_pending_confirmation", "failed", "cancelled"}
        if target not in allowed_for_rider:
            return {"error": f"Riders cannot move to {target}"}, 400
        now = now_iso()
        datastore.update("deliveries", delivery["id"], {"status": target, "updated_at": now})
        lat = _to_float(data.get("latitude")) or _to_float(data.get("lat"))
        lng = _to_float(data.get("longitude")) or _to_float(data.get("lng"))
        _record_delivery_event(delivery["id"], from_loc, target, "rider", rider.get("user_id"),
                               location=(lat, lng) if lat and lng else None,
                               notes=data.get("notes"))
        _broadcast(delivery.get("account_id"), "delivery_status",
                   {"delivery_id": delivery["id"], "status": target, "from": from_loc})
        _broadcast_user(rider.get("user_id"), "delivery_status",
                        {"delivery_id": delivery["id"], "status": target})
        if target in {"goods_collected", "in_transit", "near_destination",
                      "delivered_pending_confirmation", "failed", "cancelled"}:
            _notify(delivery.get("account_id"), None, "Delivery update",
                    f"Delivery #{delivery['id']}: {target.replace('_', ' ')}.",
                    {"type": "delivery", "delivery_id": delivery["id"]})
        if target == "delivered_pending_confirmation":
            _notify(delivery.get("account_id"), None, "Awaiting your confirmation",
                    "The rider has arrived. Confirm the delivery to complete.",
                    {"type": "delivery", "delivery_id": delivery["id"]})
        return {"delivery": _annotate_delivery(datastore.get_by_id("deliveries", delivery["id"])),
                "success": True}, 200

    @app.post("/api/deliveries/<int:delivery_id>/confirm")
    @auth
    def confirm_delivery(delivery_id):
        user = _req.user
        account_id = user["account_id"]
        delivery = datastore.get_by_id("deliveries", delivery_id, account_id)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        if delivery.get("status") != "delivered_pending_confirmation":
            return {"error": "Delivery is not awaiting confirmation"}, 400
        now = now_iso()
        datastore.update("deliveries", delivery["id"], {"status": "buyer_confirmed", "updated_at": now}, account_id)
        _record_delivery_event(delivery["id"], "delivered_pending_confirmation", "buyer_confirmed", "buyer", user["id"])
        _finalize_delivery(delivery, user, account_id, buyer_confirmed=True)
        _broadcast(account_id, "delivery_status",
                   {"delivery_id": delivery["id"], "status": "buyer_confirmed"})
        _notify(account_id, user["id"], "Delivery confirmed",
                f"You confirmed delivery #{delivery['id']}.", {"type": "delivery", "delivery_id": delivery["id"]})
        return {"delivery": _annotate_delivery(datastore.get_by_id("deliveries", delivery["id"], account_id)),
                "success": True}, 200

    @app.post("/api/deliveries/<int:delivery_id>/cancel")
    @auth
    def cancel_delivery(delivery_id):
        user = _req.user
        account_id = user["account_id"]
        delivery = _get_accessible_delivery(delivery_id, user)
        if not delivery:
            return {"error": "Delivery not found"}, 404
        if delivery.get("status") in {"completed", "cancelled", "failed"}:
            return {"error": "Delivery cannot be cancelled from this state"}, 400
        now = now_iso()
        datastore.update("deliveries", delivery["id"], {"status": "cancelled", "updated_at": now}, account_id)
        _record_delivery_event(delivery["id"], delivery.get("status"), "cancelled", "buyer", user["id"])
        # free the rider
        if delivery.get("rider_id"):
            datastore.update("riders", delivery["rider_id"], {"is_available": True, "current_status": "available"})
        _broadcast(account_id, "delivery_status", {"delivery_id": delivery["id"], "status": "cancelled"})
        _notify(account_id, user["id"], "Delivery cancelled",
                f"Delivery #{delivery['id']} was cancelled.", {"type": "delivery", "delivery_id": delivery["id"]})
        return {"success": True}, 200

    # ============================================================ INTERNAL HELPERS
    def _get_accessible_delivery(delivery_id, user):
        account_id = user["account_id"]
        if user.get("role") == "rider":
            rs = datastore.find("riders", {"user_id": user["id"]})
            if not rs:
                return None
            riders_by_id = datastore.find("deliveries", {"rider_id": rs[0]["id"]})
            # also allow if the delivery references the rider's account
            all = datastore.get_by_id("deliveries", delivery_id)
            if all and all.get("rider_id") == rs[0]["id"] and all.get("status") != "completed":
                return all
            owned = [d for d in riders_by_id if d["id"] == delivery_id]
            return owned[0] if owned else None
        return datastore.get_by_id("deliveries", delivery_id, account_id)

    def _annotate_deliveries(deliveries):
        for d in deliveries:
            _annotate_delivery(d)

    def _annotate_delivery(d):
        if not d:
            return d
        oid = d.get("wholesale_order_id")
        if oid:
            o = datastore.get_by_id("wholesale_orders", oid, None)
            d["order"] = o
            if o:
                d["order"]["items"] = datastore.find("wholesale_order_items", {"order_id": oid})
        if d.get("rider_id"):
            d["rider"] = _public_rider(datastore.get_by_id("riders", d["rider_id"], None))
        d["events"] = datastore.find("delivery_events", {"delivery_id": d.get("id")})
        return d

    def _record_delivery_event(delivery_id, from_status, to_status, actor, actor_id,
                               location=None, notes=None):
        ev = {
            "delivery_id": delivery_id, "status_from": from_status, "status_to": to_status,
            "actor": actor, "actor_id": actor_id, "notes": notes, "metadata": {"type": "delivery"},
            "created_at": now_iso(),
        }
        if location:
            ev["latitude"], ev["longitude"] = location
        datastore.create("delivery_events", ev)

    def _finalize_delivery(delivery, user, account_id, buyer_confirmed):
        """Mark delivery completed, update rider stats + buyer/seller payments."""
        now = now_iso()
        datastore.update("deliveries", delivery["id"], {"status": "completed", "updated_at": now}, account_id)
        _record_delivery_event(delivery["id"], "buyer_confirmed", "completed", "buyer", user["id"])
        # rider stats
        if delivery.get("rider_id"):
            r = datastore.get_by_id("riders", delivery["rider_id"], None)
            if r:
                completed = (r.get("completed_deliveries") or 0) + 1
                earnings = (r.get("earnings") or 0.0) + (delivery.get("rider_earnings") or 0.0)
                rate_sum = (r.get("rating") or 0.0) * (r.get("completed_deliveries") or 0)
                new_rating = (rate_sum + 5.0) / completed  # placeholder until rated
                datastore.update("riders", delivery["rider_id"], {
                    "completed_deliveries": completed, "earnings": round(earnings, 2),
                    "rating": round(new_rating, 2), "is_available": True,
                    "current_status": "available", "updated_at": now,
                })
        # advance the linked wholesale order
        if delivery.get("wholesale_order_id"):
            order = datastore.get_by_id("wholesale_orders", delivery["wholesale_order_id"], None)
            if order and order.get("status") not in {"completed", "cancelled"}:
                from network_models import can_transition_order
                to = "completed" if buyer_confirmed else "delivered"
                if can_transition_order(order.get("status"), to):
                    datastore.update("wholesale_orders", order["id"],
                                   {"status": to, "order_status": to, "payment_status": "payment_confirmed" if buyer_confirmed else order.get("payment_status"),
                                    "updated_at": now})
        _broadcast(account_id, "delivery_completed", {"delivery_id": delivery["id"]})
        _broadcast_user(delivery.get("rider_id") and (datastore.get_by_id("riders", delivery["rider_id"], None) or {}).get("user_id"),
                        "delivery_completed", {"delivery_id": delivery["id"]})

    def _broadcast_delivery(delivery_id, event, data):
        """Broadcast to the buyer account owning a delivery + the assigned rider."""
        delivery = datastore.get_by_id("deliveries", delivery_id)
        if not delivery:
            return
        data = dict(data)
        data["delivery_id"] = delivery_id
        _broadcast(delivery.get("account_id"), event, data)
        if delivery.get("rider_id"):
            rider = datastore.get_by_id("riders", delivery["rider_id"], None)
            if rider and rider.get("user_id"):
                _broadcast_user(rider["user_id"], event, data)

    def _eta_route(lat, lng, tlat, tlng, fallback, geo_proxy):
        if geo_proxy and geo_proxy.server_configured() and lat and lng and tlat and tlng:
            try:
                route = geo_proxy.route_line(lat, lng, tlat, tlng)
                if route and route.get("duration_s"):
                    return round(route["duration_s"] / 60.0, 1)
            except Exception:
                pass
        return fallback

    def _safe_user(user):
        return {k: v for k, v in (user or {}).items() if k != "password_hash"}

    def _public_rider(rider):
        if not rider:
            return None
        return {
            "id": rider.get("id"), "name": rider.get("name"),
            "vehicle_type": rider.get("vehicle_type"), "phone": rider.get("phone"),
            "rating": rider.get("rating"),
            "completed_deliveries": rider.get("completed_deliveries"),
            "cancellation_rate": rider.get("cancellation_rate"),
            "is_verified": rider.get("is_verified"),
            "is_online": rider.get("is_online"), "is_available": rider.get("is_available"),
            "lat": rider.get("lat"), "lng": rider.get("lng"),
        }


def register_rider_network(app, datastore, auth_manager, sync_manager=None,
                           notify_service=None, cache=None, geo_proxy=None):
    """Backwards-compatible alias (deprecated). Prefer register_rider_routes."""
    register_rider_routes(app, datastore, auth_manager, sync_manager,
                          notify_service, cache, geo_proxy=geo_proxy)
