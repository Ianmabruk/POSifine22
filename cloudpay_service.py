"""
CloudPay Payment Service
=========================
Handles CloudPay M-Pesa STK Push, OAuth, and webhook verification.

API docs: https://pay.cloud.or.ke/docs
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)


class CloudPayService:
    """CloudPay API client for M-Pesa STK Push."""

    def __init__(self):
        self.consumer_key = os.environ.get("CLOUDPAY_CONSUMER_KEY", "")
        self.consumer_secret = os.environ.get("CLOUDPAY_CONSUMER_SECRET", "")
        self.webhook_secret = os.environ.get("CLOUDPAY_WEBHOOK_SECRET", "")
        self.environment = os.environ.get("CLOUDPAY_ENVIRONMENT", "sandbox").lower()

        if self.environment == "production":
            self.base_url = "https://pay.cloud.or.ke"
        else:
            self.base_url = "https://pay.cloud.or.ke/sandbox"

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def _get_basic_auth(self) -> str:
        import base64
        credentials = f"{self.consumer_key}:{self.consumer_secret}"
        return base64.b64encode(credentials.encode()).decode()

    def _get_access_token(self, force_refresh: bool = False) -> Optional[str]:
        """Get cached access token or fetch a new one."""
        if not force_refresh and self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        url = f"{self.base_url}/oauth/token"
        headers = {
            "Authorization": f"Basic {self._get_basic_auth()}",
            "Content-Type": "application/json",
        }

        try:
            resp = requests.post(url, headers=headers, timeout=30)
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {}
                logger.warning("CloudPay OAuth returned non-JSON response: status=%s body=%s", resp.status_code, resp.text[:500])
            if resp.status_code == 200 and data.get("access_token"):
                self._access_token = data["access_token"]
                expires_in = int(data.get("expires_in", 3600))
                self._token_expires_at = time.time() + expires_in - 300
                logger.info("CloudPay access token refreshed, expires in %ds", expires_in)
                return self._access_token
            logger.error("CloudPay OAuth failed: %s", data)
            return None
        except requests.RequestException as exc:
            logger.error("CloudPay OAuth request failed: %s", exc)
            return None

    def initiate_stk_push(
        self,
        phone_number: str,
        amount: float,
        transaction_reference: str,
        description: str = "POS Payment",
    ) -> Dict[str, Any]:
        """
        Initiate M-Pesa STK Push via CloudPay.

        Args:
            phone_number: Customer phone in 254XXXXXXXXX format
            amount: Payment amount in KES (integer)
            transaction_reference: Unique internal reference (e.g., sale ID)
            description: Payment description

        Returns:
            Dict with reference, checkoutRequestId, status, and raw response.
        """
        access_token = self._get_access_token()
        if not access_token:
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "reference": None,
                "checkout_request_id": None,
                "error": "Failed to authenticate with CloudPay",
            }

        url = f"{self.base_url}/api/payments/mpesa/stkpush"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "phone": phone_number,
            "amount": int(amount),
            "transactionReference": transaction_reference,
            "description": description,
        }

        logger.info("CloudPay STK Push request to %s for phone=%s amount=%s ref=%s", url, phone_number, amount, transaction_reference)

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {}
                logger.warning("CloudPay STK Push returned non-JSON response: status=%s body=%s", resp.status_code, resp.text[:500])
            return {
                "success": success,
                "status_code": resp.status_code,
                "data": data,
                "reference": data.get("reference"),
                "checkout_request_id": data.get("checkoutRequestId"),
                "error": data.get("message") if not success else None,
            }
        except requests.RequestException as exc:
            logger.error("CloudPay STK Push request failed: %s", exc)
            return {
                "success": False,
                "status_code": 0,
                "data": {},
                "reference": None,
                "checkout_request_id": None,
                "error": str(exc),
            }

    def verify_payment_status(self, reference: str) -> Dict[str, Any]:
        """
        Query CloudPay for the status of a payment by reference.
        """
        access_token = self._get_access_token()
        if not access_token:
            return {"success": False, "status_code": 0, "data": {}, "status": None, "error": "Failed to authenticate"}

        url = f"{self.base_url}/api/payments/status/{reference}"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            resp = requests.get(url, headers=headers, timeout=30)
            try:
                data = resp.json()
            except (json.JSONDecodeError, ValueError):
                data = {}
                logger.warning("CloudPay verify payment returned non-JSON response: status=%s body=%s", resp.status_code, resp.text[:500])
            return {
                "success": resp.status_code == 200,
                "status_code": resp.status_code,
                "data": data,
                "status": data.get("status"),
                "error": data.get("message") if resp.status_code >= 400 else None,
            }
        except requests.RequestException as exc:
            logger.error("CloudPay verify payment failed: %s", exc)
            return {"success": False, "status_code": 0, "data": {}, "status": None, "error": str(exc)}

    def validate_webhook(self, payload: bytes, headers: Dict[str, str]) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Validate incoming CloudPay webhook signature.

        Returns:
            (is_valid, parsed_event)
        """
        if not self.webhook_secret:
            logger.warning("CloudPay webhook secret not configured, allowing webhook through")
            try:
                event = json.loads(payload.decode("utf-8")) if isinstance(payload, bytes) else json.loads(payload)
                return True, event
            except Exception:
                return False, None

        signature = headers.get("X-CloudPay-Signature", "")
        if not signature:
            logger.warning("CloudPay webhook missing signature header")
            return False, None

        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            payload if isinstance(payload, bytes) else payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("CloudPay webhook signature mismatch")
            return False, None

        try:
            event = json.loads(payload.decode("utf-8")) if isinstance(payload, bytes) else json.loads(payload)
            return True, event
        except Exception as exc:
            logger.error("Failed to parse CloudPay webhook payload: %s", exc)
            return False, None

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normalize Kenyan phone numbers to 254XXXXXXXXX format.

        Accepts:
          0712345678 -> 254712345678
          0722345678 -> 254722345678
          254712345678 -> 254712345678
          0112345678 -> 254112345678
          767767767 -> 254767767767
        """
        phone = (phone or "").strip().replace(" ", "").replace("-", "")
        if not phone:
            return ""

        if phone.startswith("+"):
            phone = phone[1:]

        if phone.startswith("254"):
            if len(phone) == 12:
                return phone
            return phone[:12]

        if phone.startswith("0"):
            return "254" + phone[1:]

        if len(phone) == 9:
            return "254" + phone

        return phone

    @staticmethod
    def map_provider_status(provider_status: str) -> str:
        """Map CloudPay status to internal payment status."""
        normalized = (provider_status or "").lower().strip()
        if normalized in ("completed",):
            return "success"
        if normalized in ("failed",):
            return "failed"
        if normalized in ("cancelled", "canceled"):
            return "cancelled"
        if normalized in ("expired", "timeout", "timed_out"):
            return "expired"
        if normalized in ("pending", "processing"):
            return "pending"
        return "pending"
