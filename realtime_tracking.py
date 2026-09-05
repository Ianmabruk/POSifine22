"""
POSIFY Business Network — Real-time delivery tracking WebSocket
===============================================================
Adds a Flask-Sock websocket ``/api/ws/tracking`` used for:

* Riders streaming live GPS positions (10-15s when cruising, 3-5s when
  delivering) to a single latest-row store + delivery-event log.
* Businesses subscribing to live tracking for a specific delivery.

Position data is persisted by ``rider_network.persist_rider_location`` so the
WebSocket and REST surface share one source of truth. The connection is
authenticated with the existing AuthManager JWT (role-aware) and is scoped so a
client can only subscribe to deliveries it is authorised to see (buyer,
wholesaler or the assigned rider).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from network_models import now_iso, location_is_fresh, RIDER_LOCATION_STALE_SECONDS
from rider_network import persist_rider_location, find_rider_by_user

logger = logging.getLogger(__name__)


def register_tracking_routes(sock, datastore, auth_manager, sync_manager,
                            notify_service=None, geo_proxy=None):

    @sock.route("/api/ws/tracking")
    def ws_tracking(ws):
        from flask import request as _req
        token = _req.args.get("token", "").strip()
        payload = auth_manager.verify_token(token)
        if not payload:
            ws.send(json.dumps({"type": "error", "message": "Invalid token"}))
            return

        account_id = payload.get("account_id")
        user_id = payload.get("user_id")
        role = payload.get("role")
        if not account_id or not user_id:
            ws.send(json.dumps({"type": "error", "message": "Invalid session"}))
            return

        sync_manager.register_connection(ws, account_id, user_id)
        # delivery-scoped subscription registry (delivery_id -> set of ws)
        delivery_subs = {}
        rider = find_rider_by_user(datastore, user_id) if role == "rider" else None

        ws.send(json.dumps({"type": "connected",
                            "account_id": account_id,
                            "user_id": user_id,
                            "role": role}))

        try:
            while True:
                raw = ws.receive()
                if raw is None:
                    break
                if raw == "ping":
                    ws.send(json.dumps({"type": "pong", "timestamp": datetime.utcnow().isoformat()}))
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                mtype = (msg.get("type") or "").lower()

                if mtype == "subscribe_delivery":
                    did = _to_int(msg.get("delivery_id"))
                    if not _can_access_delivery(datastore, did, account_id, user_id, role, rider):
                        ws.send(json.dumps({"type": "error", "message": "Not authorised for this delivery"}))
                        continue
                    delivery_subs.setdefault(did, set()).add(ws)
                    # send latest snapshot of events + current position
                    events = datastore.find("delivery_events", {"delivery_id": did})
                    delivery = datastore.get_by_id("deliveries", did)
                    last_loc = _latest_location(datastore, did)
                    ws.send(json.dumps({
                        "type": "delivery_snapshot",
                        "data": {"delivery": delivery, "events": events,
                                 "rider_position": last_loc},
                    }))
                    continue

                if mtype == "unsubscribe_delivery":
                    did = _to_int(msg.get("delivery_id"))
                    delivery_subs.get(did, set()).discard(ws)
                    continue

                if mtype == "location_update":
                    if role != "rider" or not rider:
                        ws.send(json.dumps({"type": "error", "message": "Only riders send location"}))
                        continue
                    lat = _to_float(msg.get("latitude", msg.get("lat")))
                    lng = _to_float(msg.get("longitude", msg.get("lng")))
                    did = msg.get("current_delivery_id")
                    if not lat or not lng:
                        continue
                    # validate rider is authorised to move this delivery
                    if did and not _rider_owns_delivery(datastore, _to_int(did), rider):
                        continue
                    payload_loc = {
                        "rider_id": rider.get("id"), "user_id": user_id,
                        "latitude": lat, "longitude": lng,
                        "accuracy": _to_float(msg.get("accuracy")),
                        "speed": _to_float(msg.get("speed")),
                        "heading": _to_float(msg.get("heading")),
                        "timestamp": msg.get("timestamp"),
                        "status": msg.get("status") or "available",
                        "current_delivery_id": did,
                    }
                    persist_rider_location(
                        datastore, rider, lat, lng,
                        accuracy=payload_loc["accuracy"], speed=payload_loc["speed"],
                        heading=payload_loc["heading"], timestamp=payload_loc["timestamp"],
                        status=payload_loc["status"], delivery_id=did,
                        on_broadcast=(lambda p: _broadcast_location(delivery_subs, sync_manager,
                            datastore, did, p, rider, account_id)) if did else None,
                    )
                    now_iso_str = now_iso()
                    # emit to subscribers
                    _broadcast_location(delivery_subs, sync_manager, datastore, did, payload_loc, rider, account_id)
                    # log a tracking event for in-transit deliveries (retention)
                    if did:
                        _record_tracking_event(datastore, _to_int(did), rider, payload_loc)
                    continue

                ws.send(json.dumps({"type": "error", "message": "Unknown message type"}))
        finally:
            for did, conns in delivery_subs.items():
                conns.discard(ws)
            sync_manager.unregister_connection(ws)


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------
from flask import request  # noqa: E402  (flask request proxy)


def _can_access_delivery(datastore, delivery_id, account_id, user_id, role, rider):
    if not delivery_id:
        return False
    delivery = datastore.get_by_id("deliveries", delivery_id)
    if not delivery:
        return False
    # buyer
    if delivery.get("account_id") == account_id:
        return True
    # assigned rider
    if role == "rider" and rider and delivery.get("rider_id") == rider.get("id"):
        return True
    # wholesaler (seller) of the linked order
    if delivery.get("wholesale_order_id"):
        order = datastore.get_by_id("wholesale_orders", delivery["wholesale_order_id"])
        if order and order.get("wholesaler_account_id") == account_id:
            return True
    return False


def _rider_owns_delivery(datastore, delivery_id, rider):
    delivery = datastore.get_by_id("deliveries", delivery_id)
    return bool(delivery and delivery.get("rider_id") == rider.get("id"))


def _latest_location(datastore, delivery_id):
    events = datastore.find("delivery_events", {"delivery_id": delivery_id})
    # grab the most recent event that carries a position
    for ev in reversed(events):
        if ev.get("latitude") is not None and ev.get("longitude") is not None:
            return {"latitude": ev.get("latitude"), "longitude": ev.get("longitude"),
                    "accuracy": ev.get("accuracy"), "speed": ev.get("speed"),
                    "heading": ev.get("heading"), "timestamp": ev.get("created_at")}
    riders = datastore.find("riders")
    for r in riders:
        if r.get("lat") and r.get("lng"):
            return {"latitude": r.get("lat"), "longitude": r.get("lng"),
                    "timestamp": r.get("last_location_at")}
    return None


def _record_tracking_event(datastore, delivery_id, rider, payload):
    from network_models import now_iso as _now
    datastore.create("delivery_events", {
        "delivery_id": delivery_id,
        "status_from": None, "status_to": "in_transit",
        "actor": "rider", "actor_id": rider.get("user_id"),
        "latitude": payload.get("latitude"), "longitude": payload.get("longitude"),
        "accuracy": payload.get("accuracy"), "speed": payload.get("speed"),
        "heading": payload.get("heading"), "notes": None,
        "metadata": {"type": "tracking_point"},
        "created_at": _now(),
    })


def _broadcast_location(delivery_subs, sync_manager, datastore, delivery_id, payload, rider, rider_account_id):
    msg = {"type": "rider_location", "delivery_id": delivery_id, **payload,
           "fresh": location_is_fresh(payload.get("timestamp"))}
    blob = json.dumps(msg)
    for ws in list(delivery_subs.get(delivery_id, set())):
        try:
            ws.send(blob)
        except Exception:
            delivery_subs.get(delivery_id, set()).discard(ws)
    # also fan-out through the account-scoped WS channel (desktop/mobile dashboards)
    delivery = datastore.get_by_id("deliveries", delivery_id)
    if delivery:
        try:
            sync_manager.broadcast_to_account(delivery.get("account_id"), "rider_location", msg)
        except Exception:
            pass
        if rider_account_id:
            try:
                sync_manager.broadcast_to_user(rider.get("user_id"), "rider_location", msg)
            except Exception:
                pass


def _to_float(v):
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _to_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def request_args_get(key):
    # convenience kept for readability; real read happens via flask request proxy
    try:
        from flask import request as _r
        return _r.args.get(key)
    except Exception:
        return None
