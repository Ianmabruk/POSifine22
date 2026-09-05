"""
POSIFY Business Network — Complaints & Disputes
================================================
Complaints are raised by a buyer against a delivery/order/rider/wholesaler.
They carry evidence (photos), progress through a workflow, and can trigger a
refund (via the payment module) when resolved in the buyer's favour.
"""

from __future__ import annotations

import logging
from flask import request as _req

from auth.decorators import require_auth
from network_models import (now_iso, can_transition_complaint, COMPLAINT_STATES,
    BUSINESS_ADMIN_ROLES)
from network_notifications import dispatch_notification

logger = logging.getLogger(__name__)


def register_complaint_routes(app, datastore, auth_manager, sync_manager=None,
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

    def _load_complaint(complaint_id, account_id):
        return datastore.get_by_id("complaints", complaint_id, account_id)

    @app.post("/api/complaints")
    @auth
    def create_complaint():
        user = _req.user
        account_id = user["account_id"]
        data = _req.get_json(silent=True) or {}
        delivery_id = data.get("delivery_id")
        order_id = data.get("order_id")
        rider_id = data.get("rider_id")
        if not delivery_id and not order_id:
            return {"error": "delivery_id or order_id is required"}, 400
        # authorise: buyer must own the delivery/order
        if delivery_id:
            delivery = datastore.get_by_id("deliveries", int(delivery_id), account_id)
            if not delivery:
                return {"error": "Delivery not found"}, 404
            order_id = delivery.get("wholesale_order_id") or order_id
        if order_id and not delivery_id:
            order = datastore.get_by_id("wholesale_orders", int(order_id), account_id)
            if not order:
                return {"error": "Order not found"}, 404
        now = now_iso()
        complaint = datastore.create("complaints", {
            "account_id": account_id,
            "order_id": int(order_id) if order_id else None,
            "delivery_id": int(delivery_id) if delivery_id else None,
            "rider_id": int(rider_id) if rider_id else None,
            "wholesaler_account_id": data.get("wholesaler_account_id"),
            "category": data.get("category", "other"),
            "subject": data.get("subject"),
            "description": data.get("description"),
            "evidence": [],
            "status": "open",
            "resolution_notes": None,
            "resolved_by": None,
            "resolved_at": None,
            "created_at": now,
            "updated_at": now,
        })
        _broadcast(account_id, "complaint_created", {"complaint_id": complaint["id"], "status": "open"})
        _notify(account_id, user["id"], "Complaint filed",
                f"Complaint #{complaint['id']} is open and under review.",
                {"type": "complaint", "complaint_id": complaint["id"]})
        return {"complaint": complaint, "success": True}, 201

    @app.get("/api/complaints")
    @auth
    def list_complaints():
        user = _req.user
        account_id = user["account_id"]
        complaints = datastore.find("complaints", {"account_id": account_id})
        complaints.sort(key=lambda c: c.get("created_at") or "", reverse=True)
        return {"complaints": complaints, "count": len(complaints), "success": True}, 200

    @app.get("/api/complaints/<int:complaint_id>")
    @auth
    def get_complaint(complaint_id):
        user = _req.user
        account_id = user["account_id"]
        complaint = _load_complaint(complaint_id, account_id)
        if not complaint:
            return {"error": "Complaint not found"}, 404
        _annotate(complaint)
        return {"complaint": complaint, "success": True}, 200

    @app.put("/api/complaints/<int:complaint_id>")
    @auth
    def update_complaint(complaint_id):
        user = _req.user
        account_id = user["account_id"]
        complaint = _load_complaint(complaint_id, account_id)
        if not complaint:
            return {"error": "Complaint not found"}, 404
        if complaint.get("status") not in {"open", "waiting_for_information"}:
            return {"error": "Complaint can no longer be edited"}, 400
        data = _req.get_json(silent=True) or {}
        update = {k: data[k] for k in ("subject", "description") if k in data}
        update["updated_at"] = now_iso()
        datastore.update("complaints", complaint_id, update, account_id)
        return {"complaint": datastore.get_by_id("complaints", complaint_id, account_id),
                "success": True}, 200

    @app.post("/api/complaints/<int:complaint_id>/evidence")
    @auth
    def add_evidence(complaint_id):
        user = _req.user
        account_id = user["account_id"]
        complaint = _load_complaint(complaint_id, account_id)
        if not complaint:
            return {"error": "Complaint not found"}, 404
        data = _req.get_json(silent=True) or {}
        evidence = (complaint.get("evidence") or []) + (data.get("evidence") or [data.get("file")])
        datastore.update("complaints", complaint_id, {"evidence": evidence, "updated_at": now_iso()}, account_id)
        return {"complaint": datastore.get_by_id("complaints", complaint_id, account_id),
                "success": True}, 200

    @app.post("/api/complaints/<int:complaint_id>/respond")
    @auth
    def respond_to_complaint(complaint_id):
        """Admin moves the complaint and adds resolution notes."""
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can respond to complaints"}, 403
        complaint = _load_complaint(complaint_id, account_id)
        if not complaint:
            return {"error": "Complaint not found"}, 404
        data = _req.get_json(silent=True) or {}
        notes = data.get("resolution_notes")
        next_status = data.get("status")
        if next_status and next_status != complaint.get("status"):
            if not can_transition_complaint(complaint.get("status"), next_status):
                return {"error": f"Invalid status transition to {next_status}"}, 400
            update = {"status": next_status, "updated_at": now_iso()}
            if notes:
                update["resolution_notes"] = notes
            if next_status in {"resolved", "rejected"}:
                update["resolved_by"] = user["id"]
                update["resolved_at"] = now_iso()
            datastore.update("complaints", complaint_id, update, account_id)
            _broadcast(account_id, "complaint_status",
                       {"complaint_id": complaint_id, "status": next_status})
            _notify(account_id, None, f"Complaint {next_status.title()}",
                    f"Complaint #{complaint_id} moved to {next_status}.", {"type": "complaint"})
            _maybe_refund(datastore, complaint, next_status, _notify, account_id)
        elif notes:
            datastore.update("complaints", complaint_id, {"resolution_notes": notes, "updated_at": now_iso()}, account_id)
        return {"complaint": datastore.get_by_id("complaints", complaint_id, account_id),
                "success": True}, 200

    def _annotate(complaint):
        if complaint.get("delivery_id"):
            complaint["delivery"] = datastore.get_by_id("deliveries", complaint["delivery_id"], None)
        if complaint.get("order_id"):
            complaint["order"] = datastore.get_by_id("wholesale_orders", complaint["order_id"], None)
        if complaint.get("rider_id"):
            complaint["rider"] = datastore.get_by_id("riders", complaint["rider_id"], None)


def _maybe_refund(datastore, complaint, status, notify, account_id):
    """If a complaint is resolved in the buyer's favour, refund the linked payment."""
    if status != "resolved":
        return
    order_id = complaint.get("order_id")
    if not order_id:
        return
    txs = datastore.find("payment_transactions", {"order_id": order_id})
    for tx in txs:
        if tx.get("status") == "payment_confirmed":
            datastore.update("payment_transactions", tx["id"], {
                "status": "refunded", "payment_status": "refunded",
                "updated_at": now_iso(),
            })
            notify(account_id, None, "Payment refunded",
                   f"Order #{order_id} payment was refunded due to a resolved complaint.",
                   {"type": "payment", "order_id": order_id})
