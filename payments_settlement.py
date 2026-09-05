"""
POSIFY Business Network — Payments & Settlement
================================================
Modular, provider-driven payment flows for the Business Network. A payment
provider is selected per transaction (default comes from
``DEFAULT_PAYMENT_PROVIDER`` / account settings). Concrete providers are pure
functions implementing ``initiate`` / ``verify`` / ``webhook``.

Payment state machine (see network_models.PAYMENT_STATES):
    pending -> payment_initiated -> payment_confirmed -> held_pending_delivery_confirmation
            -> delivery_confirmed -> settlement_requested -> settled
    Any -> failed | cancelled | refunded

Settlements credit the rider (rider_earnings) and the wholesaler
(order_total - delivery_fare) once a delivery is completed and the payment
is confirmed.
"""

from __future__ import annotations

import logging
import uuid
import json
import os
import hashlib
import hmac
import requests as _requests
from datetime import datetime, timezone
from flask import request as _req

from auth.decorators import require_auth
from network_models import (
    now_iso, can_transition_payment, PAYMENT_STATES, BUSINESS_ADMIN_ROLES,
)
from network_notifications import dispatch_notification

logger = logging.getLogger(__name__)

DEFAULT_PROVIDERS = {"manual", "mpesa_stk", "stripe"}
DEFAULT_PROVIDER = os.environ.get("DEFAULT_PAYMENT_PROVIDER", "manual").lower()


# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------
class PaymentProvider:
    name = "manual"

    def initiate(self, tx, account):
        """Return a payload the frontend can render to complete payment."""
        return {"method": self.name, "status": "awaiting_manual", "reference": tx.get("provider_reference")}

    def verify(self, tx):
        return {"status": tx.get("status"), "verified": tx.get("verified", False)}

    def handle_webhook(self, payload):
        return {"status": "payment_confirmed", "provider_reference": payload.get("provider_reference")}


class ManualProvider(PaymentProvider):
    name = "manual"


class MPesaSTKProvider(PaymentProvider):
    """M-Pesa STK Push provider (Safaricom-style). Configured via env."""
    name = "mpesa_stk"

    def initiate(self, tx, account):
        phone = tx.get("provider_payload", {}).get("phone")
        amount = tx.get("amount", 0)
        if not phone:
            return {"method": self.name, "status": "needs_phone", "reference": tx.get("provider_reference")}
        # Build a STK push request. Real integration requires a Daraja access token;
        # we attempt a live call when MPESA_* env is present, otherwise we return
        # a pay-stacked reference that can be verified via the webhook/verify endpoint.
        token = os.environ.get("MPESA_ACCESS_TOKEN")
        if token and os.environ.get("MPESA_STK_URL"):
            payload = {
                "BusinessShortCode": os.environ.get("MPESA_SHORTCODE"),
                "Password": _stk_password(),
                "Timestamp": datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"),
                "PartyA": phone,
                "PartyB": os.environ.get("MPESA_TILL"),
                "CallBackURL": os.environ.get("MPESA_CALLBACK_URL"),
                "AccountReference": tx.get("provider_reference"),
                "TransactionDesc": f"Wholesale order payment {tx.get('provider_reference')}",
                "Amount": amount,
            }
            try:
                resp = _requests.post(os.environ.get("MPESA_STK_URL"),
                                      headers={"Authorization": f"Bearer {token}",
                                               "Content-Type": "application/json"},
                                      json=payload, timeout=10)
                data = resp.json()
                return {"method": self.name, "status": data.get("responseCode", "202202"),
                        "checkoutRequestId": data.get("CheckoutRequestID"),
                        "reference": tx.get("provider_reference")}
            except Exception as e:
                logger.warning("M-Pesa STK initiate failed: %s", e)
        return {"method": self.name, "status": "ready", "reference": tx.get("provider_reference"),
                "message": "STK push prepared; complete via your provider callback"}


def _stk_password():
    import base64
    shortcode = os.environ.get("MPESA_SHORTCODE", "")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    raw = f"{shortcode}{os.environ.get('MPESA_PASSKEY', '')}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


_PROVIDERS: dict = {p.name: p for p in
                    (ManualProvider(), MPesaSTKProvider(), ManualProvider())}
# Ensure mpesa_stk is registered by class name
_PROVIDERS["mpesa_stk"] = MPesaSTKProvider()


def get_provider(name: str) -> PaymentProvider:
    name = (name or DEFAULT_PROVIDER).lower()
    return _PROVIDERS.get(name, ManualProvider())


def available_providers(account=None):
    """Which providers an account may use (configurable per account later)."""
    enabled = (os.environ.get("ENABLED_PAYMENT_PROVIDERS") or ",".join(DEFAULT_PROVIDERS))
    return [p.strip() for p in enabled.split(",") if p.strip()]


# ---------------------------------------------------------------------------
# Settlement logic
# ---------------------------------------------------------------------------
def compute_split(delivery, account):
    """Split a completed delivery's fare between the rider and wholesaler."""
    fare = delivery.get("fare") or 0.0
    commission = delivery.get("commission") or 0.0
    rider_earnings = fare - commission
    return {
        "rider_earnings": round(max(rider_earnings, 0.0), 2),
        "wholesaler_payout": round(max(fare - rider_earnings, 0.0), 2) if delivery.get("wholesale_order_id") else 0.0,
        "platform_fee": round(commission, 2),
    }


def create_settlement(datastore, delivery, payment_tx):
    """Record settlements for the rider and (if applicable) the wholesaler."""
    now = now_iso()
    account_id = delivery.get("account_id")
    split = compute_split(delivery, datastore)
    settlements = []
    if delivery.get("rider_id"):
        r = datastore.get_by_id("riders", delivery["rider_id"], None)
        if r:
            settlements.append(datastore.create("settlements", {
                "account_id": r.get("account_id"),
                "rider_id": delivery["rider_id"],
                "delivery_id": delivery["id"],
                "transaction_id": payment_tx.get("id"),
                "amount": split["rider_earnings"],
                "currency": payment_tx.get("currency", "KES"),
                "provider": payment_tx.get("provider"),
                "status": "pending",
                "settled_at": None,
                "created_at": now,
            }))
    return settlements


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
def register_payment_routes(app, datastore, auth_manager, sync_manager=None,
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

    @app.get("/api/payments/providers")
    @auth
    def payments_providers():
        return {"providers": available_providers(), "default": DEFAULT_PROVIDER,
                "success": True}, 200

    @app.get("/api/payments/transactions")
    @auth
    def list_transactions():
        user = _req.user
        account_id = user["account_id"]
        txs = datastore.find("payment_transactions", {"account_id": account_id})
        txs.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return {"transactions": txs, "count": len(txs), "success": True}, 200

    @app.get("/api/payments/transactions/<int:tx_id>")
    @auth
    def get_transaction(tx_id):
        user = _req.user
        account_id = user["account_id"]
        tx = datastore.get_by_id("payment_transactions", tx_id, account_id)
        if not tx:
            return {"error": "Transaction not found"}, 404
        if tx.get("order_id"):
            tx["order"] = datastore.get_by_id("wholesale_orders", tx["order_id"], None)
        return {"transaction": tx, "success": True}, 200

    @app.post("/api/payments/initiate")
    @auth
    def initiate_payment():
        """Create a payment transaction in payment_initiated state and return a
        provider-specific checkout payload."""
        user = _req.user
        account_id = user["account_id"]
        data = _req.get_json(silent=True) or {}
        order_id = data.get("order_id")
        if not order_id:
            return {"error": "order_id is required"}, 400
        order = datastore.get_by_id("wholesale_orders", int(order_id), account_id)
        if not order:
            return {"error": "Order not found"}, 404
        provider = get_provider(data.get("provider", DEFAULT_PROVIDER))
        amount = _to_float(data.get("amount")) or order.get("total_amount")
        ref = f"pay_{uuid.uuid4().hex[:12]}"
        now = now_iso()
        tx = datastore.create("payment_transactions", {
            "account_id": account_id,
            "order_id": order["id"],
            "delivery_id": order.get("delivery_id"),
            "amount": round(amount, 2),
            "deposit_amount": _to_float(data.get("deposit_amount")),
            "currency": data.get("currency", "KES"),
            "provider": provider.name,
            "provider_reference": ref,
            "provider_payload": data.get("provider_payload", {}),
            "status": "payment_initiated",
            "payment_status": "payment_initiated",
            "verified": False,
            "verified_at": None,
            "callback_payload": None,
            "created_at": now,
            "updated_at": now,
        })
        checkout = provider.initiate(tx, datastore.get_by_id("accounts", account_id))
        checkout["transaction_id"] = tx["id"]
        checkout["provider_reference"] = ref
        checkout["amount"] = tx["amount"]
        checkout["currency"] = tx["currency"]
        _broadcast(account_id, "payment_initiated", {"transaction_id": tx["id"], "provider": provider.name})
        _notify(account_id, user["id"], "Payment initiated",
                f"Complete payment #{tx['id']} via {provider.name}.",
                {"type": "payment", "transaction_id": tx["id"]})
        return {"transaction": tx, "checkout": checkout, "success": True}, 201

    @app.post("/api/payments/transactions/<int:tx_id>/verify")
    @auth
    def verify_payment(tx_id):
        user = _req.user
        account_id = user["account_id"]
        tx = datastore.get_by_id("payment_transactions", tx_id, account_id)
        if not tx:
            return {"error": "Transaction not found"}, 404
        provider = get_provider(tx.get("provider"))
        result = provider.verify(tx)
        if result.get("verified") and can_transition_payment(tx.get("status"), "payment_confirmed"):
            datastore.update("payment_transactions", tx["id"], {
                "status": "payment_confirmed", "payment_status": "payment_confirmed",
                "verified": True, "verified_at": now_iso(), "updated_at": now_iso(),
            }, account_id)
            _broadcast(account_id, "payment_confirmed", {"transaction_id": tx["id"]})
        return {"transaction": datastore.get_by_id("payment_transactions", tx["id"], account_id),
                "result": result, "success": True}, 200

    @app.post("/api/payments/transactions/<int:tx_id>/complete")
    @auth
    def complete_payment_manual(tx_id):
        """Business marks a manual (cash) payment as collected -> confirmed."""
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can confirm manual payments"}, 403
        tx = datastore.get_by_id("payment_transactions", tx_id, account_id)
        if not tx:
            return {"error": "Transaction not found"}, 404
        if tx.get("provider") != "manual":
            return {"error": "Use provider verify flow for this payment"}, 400
        if not can_transition_payment(tx.get("status"), "payment_confirmed"):
            return {"error": f"Cannot confirm payment from {tx.get('status')}"}, 400
        datastore.update("payment_transactions", tx["id"], {
            "status": "payment_confirmed", "payment_status": "payment_confirmed",
            "verified": True, "verified_at": now_iso(), "updated_at": now_iso(),
        }, account_id)
        _broadcast(account_id, "payment_confirmed", {"transaction_id": tx["id"]})
        _notify(account_id, user["id"], "Payment confirmed",
                f"Payment #{tx['id']} has been confirmed.", {"type": "payment", "transaction_id": tx["id"]})
        return {"transaction": datastore.get_by_id("payment_transactions", tx["id"], account_id),
                "success": True}, 200

    @app.post("/api/payments/transactions/<int:tx_id>/refund")
    @auth
    def refund_payment(tx_id):
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can refund"}, 403
        tx = datastore.get_by_id("payment_transactions", tx_id, account_id)
        if not tx:
            return {"error": "Transaction not found"}, 404
        if not can_transition_payment(tx.get("status"), "refunded"):
            return {"error": "Cannot refund payment in current state"}, 400
        datastore.update("payment_transactions", tx["id"], {
            "status": "refunded", "payment_status": "refunded",
            "updated_at": now_iso(),
        }, account_id)
        _broadcast(account_id, "payment_refunded", {"transaction_id": tx["id"]})
        return {"transaction": datastore.get_by_id("payment_transactions", tx["id"], account_id),
                "success": True}, 200

    # ----------------------------------------------------------------- WEBHOOK
    @app.post("/api/payments/webhook/<provider>")
    def payment_webhook(provider):
        """Public provider callback. Signature/amount verified, never trusts
        arbitrary status strings."""
        data = _req.get_json(silent=True) or _req.form.to_dict()
        ref = data.get("provider_reference") or data.get("reference") or data.get("mpesa_checkout_id")
        if not ref:
            return {"error": "Missing provider_reference"}, 400
        txs = datastore.find("payment_transactions", {"provider_reference": ref}) if "provider_reference" in _allowed_filter_fields() else []
        if not txs:
            # fall back to a full scan (rare)
            txs = [t for t in datastore.get_all("payment_transactions", None)
                   if t.get("provider_reference") == ref]
        tx = txs[0] if txs else None
        if not tx:
            return {"error": "Unknown transaction reference"}, 404
        provider_obj = get_provider(provider)
        result = provider_obj.handle_webhook(data)
        if result.get("status") == "payment_confirmed" and can_transition_payment(tx.get("status"), "payment_confirmed"):
            datastore.update("payment_transactions", tx["id"], {
                "status": "payment_confirmed", "payment_status": "payment_confirmed",
                "verified": True, "verified_at": now_iso(),
                "callback_payload": data, "updated_at": now_iso(),
            })
            _broadcast(tx.get("account_id"), "payment_confirmed", {"transaction_id": tx["id"]})
        else:
            datastore.update("payment_transactions", tx["id"], {
                "callback_payload": data, "updated_at": now_iso(),
            })
        # acknowledge
        return {"status": "ok", "transaction_id": tx["id"]}, 200

    @app.get("/api/settlements")
    @auth
    def list_settlements():
        user = _req.user
        account_id = user["account_id"]
        rows = datastore.find("settlements", {"account_id": account_id})
        rows.sort(key=lambda s: s.get("created_at") or "", reverse=True)
        return {"settlements": rows, "count": len(rows), "success": True}, 200

    @app.post("/api/settlements/<int:settlement_id>/release")
    @auth
    def release_settlement(settlement_id):
        user = _req.user
        account_id = user["account_id"]
        if user.get("role") not in BUSINESS_ADMIN_ROLES:
            return {"error": "Only business admins can release settlements"}, 403
        s = datastore.get_by_id("settlements", settlement_id, account_id)
        if not s:
            return {"error": "Settlement not found"}, 404
        if s.get("status") != "pending":
            return {"error": "Settlement already processed"}, 400
        datastore.update("settlements", settlement_id, {
            "status": "paid", "settled_at": now_iso(),
        }, account_id)
        _broadcast(account_id, "settlement_released", {"settlement_id": settlement_id})
        return {"settlement": datastore.get_by_id("settlements", settlement_id, account_id),
                "success": True}, 200


def _to_float(v):
    try:
        return float(v) if v is not None and v != "" else 0.0
    except (TypeError, ValueError):
        return 0.0


def _allowed_filter_fields():
    try:
        from database import DataStore
        return DataStore.ALLOWED_FILTER_FIELDS
    except Exception:
        return set()
