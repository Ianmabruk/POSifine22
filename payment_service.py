"""
Payment Service
===============
Business logic for M-Pesa payments via IntaSend.
"""

from __future__ import annotations

import logging
import secrets
import string
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from intasend_service import IntaSendService

logger = logging.getLogger(__name__)


class PaymentService:
    """High-level payment workflows for M-Pesa STK Push."""

    STATUS_PENDING = "pending"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"

    def __init__(self, intasend: Optional[IntaSendService] = None, datastore=None):
        self.intasend = intasend or IntaSendService()
        self.datastore = datastore

    def initiate_mpesa_payment(
        self,
        account_id: str,
        sale_id: int,
        cashier_id: int,
        amount: float,
        phone_number: str,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Initiate an M-Pesa STK Push payment for a sale.

        Returns:
            (success, error, payment_data)
        """
        if not self.datastore:
            return False, "Database not available", None

        existing_pending = self._find_pending_payment(account_id, sale_id)
        if existing_pending:
            return (
                False,
                "Payment already in progress. Waiting for customer confirmation...",
                {"payment_id": existing_pending.get("id"), "status": existing_pending.get("status")},
            )

        normalized_phone = self.intasend.normalize_phone(phone_number)
        if not normalized_phone or len(normalized_phone) < 12:
            return False, "Invalid M-Pesa phone number. Please enter a valid Kenyan mobile number.", None

        account_ref = f"POS-{account_id}-{sale_id}-{secrets.token_hex(4)}"
        stk_result = self.intasend.initiate_stk_push(
            phone_number=normalized_phone,
            amount=amount,
            account_ref=account_ref,
            narrative=f"POS Sale #{sale_id}",
            currency="KES",
        )

        if not stk_result.get("success"):
            error_msg = stk_result.get("error") or "Failed to initiate M-Pesa payment"
            logger.error("IntaSend STK Push failed for sale %s: %s", sale_id, error_msg)
            return False, error_msg, None

        provider_reference = stk_result.get("provider_reference")
        payment_record = {
            "account_id": account_id,
            "sale_id": sale_id,
            "cashier_id": cashier_id,
            "amount": amount,
            "currency": "KES",
            "customer_phone": normalized_phone,
            "provider": "intasend",
            "provider_reference": provider_reference,
            "account_ref": account_ref,
            "status": self.STATUS_PENDING,
            "failure_reason": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }

        payment = self.datastore.create("payments", payment_record)
        self.datastore.update(
            "sales",
            sale_id,
            {"payment_status": self.STATUS_PENDING, "payment_method": "mpesa"},
            account_id,
        )

        logger.info("M-Pesa payment initiated: payment_id=%s sale_id=%s ref=%s", payment.get("id"), sale_id, provider_reference)
        return True, None, {
            "payment_id": payment.get("id"),
            "status": self.STATUS_PENDING,
            "provider_reference": provider_reference,
            "account_ref": account_ref,
            "customer_phone": normalized_phone,
            "amount": amount,
        }

    def handle_webhook(
        self, provider_reference: str, event_data: Dict[str, Any]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Process IntaSend webhook event.

        Idempotent: safe to process the same webhook multiple times.
        """
        if not self.datastore:
            return False, "Database not available", None

        payment = self._find_payment_by_provider_reference(provider_reference)
        if not payment:
            logger.warning("Webhook received for unknown payment reference: %s", provider_reference)
            return False, "Payment not found", None

        payment_id = payment.get("id")
        sale_id = payment.get("sale_id")
        account_id = payment.get("account_id")
        current_status = (payment.get("status") or "").lower()

        if current_status in (self.STATUS_SUCCESS, self.STATUS_FAILED, self.STATUS_CANCELLED):
            logger.info("Webhook ignored for completed payment_id=%s status=%s", payment_id, current_status)
            return True, None, {"payment_id": payment_id, "status": current_status, "idempotent": True}

        provider_status = (event_data.get("state") or event_data.get("status") or "").lower()
        mapped_status = self._map_provider_status(provider_status)

        updates = {
            "status": mapped_status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if event_data.get("failure_reason"):
            updates["failure_reason"] = event_data.get("failure_reason")
        if event_data.get("provider_reference") and not payment.get("provider_reference"):
            updates["provider_reference"] = event_data.get("provider_reference")

        self.datastore.update("payments", payment_id, updates, account_id)

        if mapped_status == self.STATUS_SUCCESS and sale_id:
            self._finalize_sale(sale_id, account_id, payment_id, payment.get("amount"))

        logger.info("Payment updated via webhook: payment_id=%s sale_id=%s status=%s", payment_id, sale_id, mapped_status)
        return True, None, {"payment_id": payment_id, "status": mapped_status, "sale_id": sale_id}

    def get_payment_status(self, payment_id: int, account_id: str) -> Optional[Dict[str, Any]]:
        """Get current payment status from database."""
        if not self.datastore:
            return None
        payment = self.datastore.get_by_id("payments", payment_id, account_id)
        if not payment:
            return None
        sale = self.datastore.get_by_id("sales", payment.get("sale_id"), account_id) if payment.get("sale_id") else None
        return {
            "payment_id": payment.get("id"),
            "sale_id": payment.get("sale_id"),
            "status": payment.get("status"),
            "amount": payment.get("amount"),
            "currency": payment.get("currency"),
            "customer_phone": payment.get("customer_phone"),
            "provider": payment.get("provider"),
            "provider_reference": payment.get("provider_reference"),
            "failure_reason": payment.get("failure_reason"),
            "created_at": payment.get("created_at"),
            "updated_at": payment.get("updated_at"),
            "sale_payment_status": sale.get("payment_status") if sale else None,
        }

    def _find_pending_payment(self, account_id: str, sale_id: int) -> Optional[Dict[str, Any]]:
        if not self.datastore:
            return None
        payments = self.datastore.get_by_field("payments", "account_id", account_id)
        for p in payments or []:
            if p.get("sale_id") == sale_id and (p.get("status") or "").lower() in (
                self.STATUS_PENDING,
            ):
                return p
        return None

    def _find_payment_by_provider_reference(self, provider_reference: str) -> Optional[Dict[str, Any]]:
        if not self.datastore:
            return None
        payments = self.datastore.get_by_field("payments", "provider_reference", provider_reference)
        if payments:
            return payments[0]
        return None

    def _map_provider_status(self, provider_status: str) -> str:
        normalized = (provider_status or "").lower().strip()
        success_keys = {"success", "completed", "paid", "approved", "fulfilled"}
        failed_keys = {"failed", "error", "declined", "rejected"}
        cancelled_keys = {"cancelled", "canceled", "void"}
        expired_keys = {"expired", "timeout", "timed_out"}

        if normalized in success_keys:
            return self.STATUS_SUCCESS
        if normalized in failed_keys:
            return self.STATUS_FAILED
        if normalized in cancelled_keys:
            return self.STATUS_CANCELLED
        if normalized in expired_keys:
            return self.STATUS_EXPIRED
        return self.STATUS_PENDING

    def _finalize_sale(self, sale_id: int, account_id: str, payment_id: int, amount: float) -> None:
        try:
            self.datastore.update(
                "sales",
                sale_id,
                {
                    "payment_status": "paid",
                    "amount_paid": amount,
                    "change": 0.0,
                },
                account_id,
            )
            logger.info("Sale finalized: sale_id=%s payment_id=%s", sale_id, payment_id)
        except Exception as exc:
            logger.error("Failed to finalize sale %s: %s", sale_id, exc)
