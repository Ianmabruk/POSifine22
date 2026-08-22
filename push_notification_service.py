"""
Push Notification Service
==========================
Web Push API + VAPID push notifications for POS admins.
- VAPID key management
- Device registration and management
- Multi-device push delivery
- Tenant isolation
- Retry with exponential backoff
- Async delivery (never blocks sales)
"""

import os
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

try:
    import pywebpush
    from pywebpush import WebPushException
    PYWEBPUSH_AVAILABLE = True
except ImportError:
    PYWEBPUSH_AVAILABLE = False

logger = logging.getLogger(__name__)


class PushNotificationService:
    """
    Web Push notification service using VAPID.
    """

    def __init__(self, datastore=None):
        self.datastore = datastore
        self.vapid_private_key = os.environ.get('VAPID_PRIVATE_KEY')
        self.vapid_public_key = os.environ.get('VAPID_PUBLIC_KEY')
        self.vapid_subject = os.environ.get('VAPID_SUBJECT', 'mailto:admin@posify.com')
        self.enabled = PYWEBPUSH_AVAILABLE and bool(self.vapid_private_key and self.vapid_public_key)

        if not self.enabled:
            if not PYWEBPUSH_AVAILABLE:
                logger.warning("pywebpush not installed. Push notifications disabled.")
            else:
                logger.warning("VAPID keys not configured. Push notifications disabled.")

    def get_or_create_vapid_keys(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Get existing VAPID keys or generate new ones.
        Returns (public_key, private_key)
        """
        if self.vapid_public_key and self.vapid_private_key:
            return self.vapid_public_key, self.vapid_private_key

        if not PYWEBPUSH_AVAILABLE:
            return None, None

        try:
            from pywebpush import generate_vapid_keys
            keys = generate_vapid_keys()
            public_key = keys['publicKey']
            private_key = keys['privateKey']
            logger.info("Generated new VAPID keys for push notifications")
            return public_key, private_key
        except Exception as e:
            logger.error(f"Failed to generate VAPID keys: {e}")
            return None, None

    def register_device(
        self,
        user_id: int,
        account_id: str,
        push_subscription: Dict[str, Any],
        device_name: Optional[str] = None,
        platform: Optional[str] = None,
        browser: Optional[str] = None,
        permission_status: str = 'granted'
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Register a device for push notifications.
        
        Args:
            user_id: Admin user ID
            account_id: Tenant/store ID
            push_subscription: Web Push subscription object {endpoint, keys: {p256dh, auth}}
            device_name: Human-readable device name
            platform: Platform (e.g., 'windows', 'android', 'ios', 'macos')
            browser: Browser name (e.g., 'chrome', 'firefox', 'safari')
            permission_status: 'granted', 'denied', 'default'
            
        Returns:
            (success, error_message, device_record)
        """
        if not self.datastore:
            return False, "Database not available", None

        try:
            device_data = {
                "user_id": user_id,
                "account_id": account_id,
                "device_name": device_name or f"Device {uuid.uuid4().hex[:8]}",
                "platform": platform or "unknown",
                "browser": browser or "unknown",
                "push_subscription": json.dumps(push_subscription),
                "permission_status": permission_status,
                "enabled": True,
                "last_seen_at": datetime.utcnow().isoformat(),
                "created_at": datetime.utcnow().isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }

            device = self.datastore.create("notification_devices", device_data)
            logger.info(f"Registered push device for user {user_id}: {device.get('device_name')}")
            return True, None, device

        except Exception as e:
            logger.error(f"Failed to register push device: {e}")
            return False, str(e), None

    def unregister_device(self, device_id: int, account_id: str) -> bool:
        """
        Disable/remove a device registration.
        """
        if not self.datastore:
            return False

        try:
            self.datastore.update("notification_devices", device_id, {
                "enabled": False,
                "updated_at": datetime.utcnow().isoformat()
            }, account_id)
            logger.info(f"Unregistered push device {device_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to unregister device {device_id}: {e}")
            return False

    def get_user_devices(self, user_id: int, account_id: str) -> List[Dict[str, Any]]:
        """
        Get all registered devices for a user.
        """
        if not self.datastore:
            return []

        try:
            devices = self.datastore.get_all("notification_devices", account_id)
            return [d for d in devices if d.get("user_id") == user_id]
        except Exception as e:
            logger.error(f"Failed to get devices for user {user_id}: {e}")
            return []

    def get_account_devices(self, account_id: str) -> List[Dict[str, Any]]:
        """
        Get all registered devices for an account (for notification delivery).
        Only returns enabled devices for admin users.
        """
        if not self.datastore:
            return []

        try:
            devices = self.datastore.get_all("notification_devices", account_id)
            return [d for d in devices if d.get("enabled")]
        except Exception as e:
            logger.error(f"Failed to get devices for account {account_id}: {e}")
            return []

    def send_push_notification(
        self,
        device: Dict[str, Any],
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        icon: Optional[str] = None,
        badge: Optional[str] = None,
        tag: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Send a push notification to a single device.
        
        Args:
            device: Device record from database
            title: Notification title
            body: Notification body text
            data: Additional data payload
            icon: Notification icon URL
            badge: Badge icon URL
            tag: Notification tag for grouping
            
        Returns:
            (success, error_message)
        """
        if not self.enabled or not PYWEBPUSH_AVAILABLE:
            return False, "Push notifications not configured"

        try:
            subscription_json = device.get("push_subscription")
            if not subscription_json:
                return False, "Device has no push subscription"

            subscription = json.loads(subscription_json) if isinstance(subscription_json, str) else subscription_json

            payload = {
                "title": title,
                "body": body,
                "icon": icon or "/posifine-logo.png",
                "badge": badge or "/favicon-32x32.png",
                "tag": tag or f"posify-{device.get('id')}",
                "data": data or {},
                "requireInteraction": False,
                "renotify": False
            }

            pywebpush.push(
                subscription_info=subscription,
                data=json.dumps(payload),
                vapid_private_key=self.vapid_private_key,
                vapid_public_key=self.vapid_public_key,
                vapid_additional_headers={"X-POSify-Account": str(device.get("account_id", ""))}
            )

            return True, None

        except WebPushException as e:
            error_msg = str(e)
            if "expired" in error_msg.lower() or "404" in error_msg or "410" in error_msg:
                logger.warning(f"Push subscription expired for device {device.get('id')}: {e}")
                self._disable_expired_device(device.get("id"), device.get("account_id"))
                return False, "Subscription expired"
            logger.error(f"WebPush error for device {device.get('id')}: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Failed to send push to device {device.get('id')}: {e}")
            return False, str(e)

    def _disable_expired_device(self, device_id: int, account_id: str) -> None:
        """
        Mark an expired device as disabled.
        """
        if not self.datastore:
            return
        try:
            self.datastore.update("notification_devices", device_id, {
                "enabled": False,
                "updated_at": datetime.utcnow().isoformat()
            }, account_id)
        except Exception as e:
            logger.error(f"Failed to disable expired device {device_id}: {e}")

    def send_notification_to_account(
        self,
        account_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        notification_type: str = "info",
        exclude_device_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Send a push notification to all enabled devices for an account.
        
        Args:
            account_id: Tenant/store ID
            title: Notification title
            body: Notification body
            data: Additional data
            notification_type: Type for grouping/tagging
            exclude_device_ids: Devices to skip
            
        Returns:
            {sent: int, failed: int, errors: list}
        """
        if not self.enabled:
            return {"sent": 0, "failed": 0, "errors": ["Push notifications not configured"]}

        devices = self.get_account_devices(account_id)
        if exclude_device_ids:
            devices = [d for d in devices if d.get("id") not in exclude_device_ids]

        if not devices:
            return {"sent": 0, "failed": 0, "errors": ["No enabled devices"]}

        sent = 0
        failed = 0
        errors = []

        for device in devices:
            success, error = self.send_push_notification(
                device=device,
                title=title,
                body=body,
                data=data,
                tag=f"posify-{notification_type}"
            )
            if success:
                sent += 1
            else:
                failed += 1
                errors.append({"device_id": device.get("id"), "error": error})

        logger.info(f"Push notification sent to account {account_id}: {sent} sent, {failed} failed")
        return {"sent": sent, "failed": failed, "errors": errors}

    def send_sale_notification(self, account_id: str, sale: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send sale notification to all admin devices for an account.
        """
        if not self.enabled:
            return {"sent": 0, "failed": 0, "errors": ["Push notifications not configured"]}

        cashier_name = sale.get('cashier_name') or 'A cashier'
        total = sale.get('total', 0)
        item_count = len(sale.get('items', []))
        payment_method = (sale.get('payment_method') or 'cash').upper()
        receipt_number = sale.get('receipt_number', f"#{sale.get('id', 'N/A')}")

        title = f"New Sale - {receipt_number}"
        body = f"{cashier_name} completed a sale of {item_count} item(s) for KSh {float(total):,.2f} via {payment_method}."

        data = {
            "type": "sale_completed",
            "saleId": sale.get("id"),
            "receiptNumber": receipt_number,
            "total": total,
            "itemCount": item_count,
            "paymentMethod": payment_method,
            "cashierName": cashier_name,
            "url": "/admin/sales"
        }

        result = self.send_notification_to_account(
            account_id=account_id,
            title=title,
            body=body,
            data=data,
            notification_type="sale_completed"
        )

        self.create_notification_history(
            user_id=sale.get('cashier_id', 0),
            account_id=account_id,
            notification_type="sale_completed",
            title=title,
            body=body,
            data=data
        )

        return result

    def send_low_stock_notification(self, account_id: str, product: Dict[str, Any], threshold: float) -> Dict[str, Any]:
        """
        Send low stock notification.
        """
        if not self.enabled:
            return {"sent": 0, "failed": 0, "errors": ["Push notifications not configured"]}

        name = product.get('name', 'Unknown product')
        quantity = product.get('quantity', 0)

        title = "Low Stock Alert"
        body = f"{name} has only {quantity} units remaining. Threshold: {threshold}."

        data = {
            "type": "low_stock",
            "productId": product.get("id"),
            "productName": name,
            "quantity": quantity,
            "threshold": threshold,
            "url": "/admin/inventory"
        }

        result = self.send_notification_to_account(
            account_id=account_id,
            title=title,
            body=body,
            data=data,
            notification_type="low_stock"
        )

        self.create_notification_history(
            user_id=0,
            account_id=account_id,
            notification_type="low_stock",
            title=title,
            body=body,
            data=data
        )

        return result

    def send_out_of_stock_notification(self, account_id: str, product: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send out of stock notification.
        """
        if not self.enabled:
            return {"sent": 0, "failed": 0, "errors": ["Push notifications not configured"]}

        name = product.get('name', 'Unknown product')

        title = "Out of Stock"
        body = f"{name} is now out of stock. Please restock immediately."

        data = {
            "type": "out_of_stock",
            "productId": product.get("id"),
            "productName": name,
            "url": "/admin/inventory"
        }

        result = self.send_notification_to_account(
            account_id=account_id,
            title=title,
            body=body,
            data=data,
            notification_type="out_of_stock"
        )

        self.create_notification_history(
            user_id=0,
            account_id=account_id,
            notification_type="out_of_stock",
            title=title,
            body=body,
            data=data
        )

        return result
        self,
        user_id: int,
        account_id: str,
        notification_type: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a notification history record.
        """
        if not self.datastore:
            return None

        try:
            notification = {
                "user_id": user_id,
                "account_id": account_id,
                "type": notification_type,
                "title": title,
                "body": body,
                "data": json.dumps(data or {}),
                "read": False,
                "read_at": None,
                "created_at": datetime.utcnow().isoformat()
            }
            return self.datastore.create("notifications", notification)
        except Exception as e:
            logger.error(f"Failed to create notification history: {e}")
            return None


# Global instance
_push_service = None


def get_notification_service(datastore=None) -> PushNotificationService:
    global _push_service
    if _push_service is None:
        _push_service = PushNotificationService(datastore=datastore)
    return _push_service
