"""
IntaSend M-Pesa STK Push Service
==================================
Handles IntaSend API authentication and STK Push requests.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)


class IntaSendService:
    """IntaSend API client for M-Pesa STK Push."""

    def __init__(self):
        self.secret_key = os.environ.get("INTASEND_SECRET_KEY", "")
        self.publishable_key = os.environ.get("INTASEND_PUBLISHABLE_KEY", "")
        self.environment = os.environ.get("INTASEND_ENVIRONMENT", "sandbox").lower()
        self.webhook_secret = os.environ.get("INTASEND_WEBHOOK_SECRET", "")

        if self.environment == "production":
            self.base_url = "https://production.intasend.com/api/v1"
        else:
            self.base_url = "https://sandbox.intasend.com/api/v1"

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json",
        }

    def _get_common_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
        }

    def initiate_stk_push(
        self,
        phone_number: str,
        amount: float,
        account_ref: str,
        narrative: str = "POS Payment",
        currency: str = "KES",
    ) -> Dict[str, Any]:
        """
        Initiate M-Pesa STK Push via IntaSend.

        Returns:
            Dict with provider_reference, status, and raw response.
        """
        url = f"{self.base_url}/payment/stk-push/"
        payload = {
            "phone_number": phone_number,
            "amount": str(int(amount)),
            "account_ref": account_ref,
            "narrative": narrative,
            "currency": currency,
        }

        logger.info("IntaSend STK Push request to %s for phone=%s amount=%s", url, phone_number, amount)

        try:
            resp = requests.post(
                url,
                json=payload,
                headers={**self._get_common_headers(), "Authorization": f"Bearer {self.secret_key}"},
                timeout=30,
            )
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {}
                logger.warning("IntaSend STK Push returned non-JSON response: status=%s body=%s", resp.status_code, resp.text[:500])

            logger.info("IntaSend STK Push response: status=%s body=%s", resp.status_code, data)
            return {
                "success": resp.status_code in (200, 201),
                "status_code": resp.status_code,
                "data": data,
                "provider_reference": data.get("reference") or data.get("invoice_number") or data.get("tracking_id"),
                "error": data.get("error") or data.get("message") if resp.status_code >= 400 else None,
            }
        except requests.RequestException as exc:
            logger.error("IntaSend STK Push request failed: %s", exc)
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "provider_reference": None,
                "error": str(exc),
            }

    def verify_payment_status(self, provider_reference: str) -> Dict[str, Any]:
        """
        Query IntaSend for the status of a payment by reference.
        """
        url = f"{self.base_url}/payment/status/{provider_reference}/"
        try:
            resp = requests.get(url, headers=self._get_auth_headers(), timeout=30)
            data = resp.json()
            return {
                "success": resp.status_code == 200,
                "status_code": resp.status_code,
                "data": data,
                "status": data.get("state") or data.get("status"),
                "error": data.get("error") or data.get("message") if resp.status_code >= 400 else None,
            }
        except requests.RequestException as exc:
            logger.error("IntaSend verify payment failed: %s", exc)
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "status": None,
                "error": str(exc),
            }

    def validate_webhook(self, payload: Dict[str, Any], headers: Dict[str, str]) -> bool:
        """
        Validate incoming IntaSend webhook.

        If INTASEND_WEBHOOK_SECRET is configured, verify it matches.
        Otherwise, allow the webhook through (sandbox mode).
        """
        if not self.webhook_secret:
            return True
        received_secret = headers.get("X-IntaSend-Secret") or headers.get("X-Webhook-Secret") or ""
        return received_secret == self.webhook_secret

    def normalize_phone(self, phone: str) -> str:
        """
        Normalize Kenyan phone numbers to 254XXXXXXXXX format.

        Accepts:
          0712345678 -> 254712345678
          0722345678 -> 254722345678
          254712345678 -> 254712345678
          0112345678 -> 254112345678
        """
        phone = (phone or "").strip().replace(" ", "").replace("-", "")
        if not phone:
            return ""

        if phone.startswith("+"):
            phone = phone[1:]

        if phone.startswith("254"):
            return phone

        if phone.startswith("0"):
            return "254" + phone[1:]

        if len(phone) == 9:
            return "254" + phone

        return phone
