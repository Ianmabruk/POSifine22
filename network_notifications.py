"""
POSIFY Business Network — In-app notification persistence + dispatch
=====================================================================
Persists notifications in the existing ``notifications`` table and fans them
out through the real-time sync manager (WebSocket). Also exposes the HTTP API
the frontend ``NotificationBell`` already expects:
``/api/notifications/history`` and the mark-read routes.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def create_notification(datastore, account_id, user_id, title, body,
                        extra: Optional[Dict] = None) -> Optional[Dict]:
    """Persist an in-app notification scoped to an account/user.

    ``user_id`` of ``0``/``None`` means "all users on this account".
    """
    try:
        return datastore.create("notifications", {
            "account_id": account_id,
            "user_id": user_id or 0,
            "type": (extra or {}).get("type", "info"),
            "title": title,
            "body": body,
            "data": extra or {},
            "read": False,
            "read_at": None,
            "created_at": datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.warning("create_notification failed: %s", e)
        return None


def dispatch_notification(datastore, sync_manager, notify_service, account_id,
                          user_id, title, body, extra: Optional[Dict] = None):
    """Persist + broadcast (WebSocket) a notification. Email is optional and
    never blocks the request flow; the WebSocket channel is primary."""
    notif = create_notification(datastore, account_id, user_id, title, body, extra)
    if sync_manager is not None and account_id is not None:
        try:
            sync_manager.broadcast_to_account(account_id, "notification", {
                "id": notif.get("id") if notif else None,
                "type": "notification",
                "title": title,
                "body": body,
                "data": extra or {},
                "created_at": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning("notification broadcast failed: %s", e)
    return notif


def register_notification_api(app, datastore, auth_manager):
    """Register the HTTP endpoints the frontend NotificationBell relies on."""
    from auth.decorators import require_auth
    auth = require_auth(auth_manager, datastore)
    from flask import request as _req

    @app.get("/api/notifications/history")
    @auth
    def notifications_history():
        user = _req.user
        account_id = user.get("account_id")
        uid = user.get("id")
        limit = min(int(_req.args.get("limit") or 20), 100)
        all_notifs = datastore.get_all("notifications", account_id)
        mine = [n for n in all_notifs
                if n.get("user_id") == uid or n.get("user_id") in (0, None)]
        mine.sort(key=lambda n: n.get("created_at") or "", reverse=True)
        return {"notifications": mine[:limit], "count": len(mine[:limit]), "success": True}, 200

    @app.post("/api/notifications/mark-read")
    @auth
    def notifications_mark_read():
        data = _req.get_json(silent=True) or {}
        nid = data.get("notification_id")
        account_id = _req.user.get("account_id")
        if nid:
            notifs = datastore.get_by_id("notifications", int(nid), account_id)
            if notifs:
                datastore.update("notifications", notifs["id"],
                                 {"read": True, "read_at": datetime.utcnow().isoformat()},
                                 account_id)
        return {"success": True}, 200

    @app.post("/api/notifications/mark-all-read")
    @auth
    def notifications_mark_all_read():
        account_id = _req.user.get("account_id")
        for n in datastore.get_all("notifications", account_id):
            datastore.update("notifications", n["id"],
                             {"read": True, "read_at": datetime.utcnow().isoformat()}, account_id)
        return {"success": True}, 200
