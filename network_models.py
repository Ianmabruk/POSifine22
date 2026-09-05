"""
POSIFY Business Network — Shared Domain Models
=============================================
Centralized state machines, constants and helper logic for:

* Delivery workflow (CREATED -> COMPLETED)
* Wholesale order workflow
* Payment / settlement workflow
* Compliant / dispute lifecycle
* Rider presence & roles

Kept pure-Python (no Flask imports) so it can be reused by backend route
modules, background jobs and tests without coupling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
BUSINESS_ROLES = {"owner", "admin", "cashier"}
RIDER_ROLE = "rider"
MAIN_ADMIN_ROLE = "main_admin"

# Roles authorised to manage marketplace / wholesale operations on behalf of a
# business (wholesaler onboarding, product management, order acceptance, etc.).
BUSINESS_ADMIN_ROLES = {"owner", "admin"}


# ---------------------------------------------------------------------------
# Delivery state machine
# ---------------------------------------------------------------------------
DELIVERY_STATES = [
    "created",
    "awaiting_rider",
    "rider_requested",
    "rider_assigned",
    "rider_going_to_pickup",
    "rider_at_pickup",
    "goods_collected",
    "in_transit",
    "near_destination",
    "delivered_pending_confirmation",
    "buyer_confirmed",
    "completed",
    "cancelled",
    "failed",
]

# Directed graph of allowed transitions. Every edge must be intentional and
# enforce the rule "a rider cannot deliver goods that were never collected".
DELIVERY_TRANSITIONS: Dict[str, List[str]] = {
    "created": ["awaiting_rider", "rider_requested", "cancelled"],
    "awaiting_rider": ["rider_requested", "rider_assigned", "cancelled"],
    "rider_requested": ["rider_assigned", "awaiting_rider", "cancelled"],
    "rider_assigned": ["rider_going_to_pickup", "awaiting_rider", "cancelled", "failed"],
    "rider_going_to_pickup": ["rider_at_pickup", "rider_assigned", "cancelled", "failed"],
    "rider_at_pickup": ["goods_collected", "rider_going_to_pickup", "failed"],
    "goods_collected": ["in_transit", "rider_at_pickup", "failed"],
    "in_transit": ["near_destination", "goods_collected", "cancelled", "failed"],
    "near_destination": ["delivered_pending_confirmation", "in_transit", "failed"],
    "delivered_pending_confirmation": ["buyer_confirmed", "in_transit", "failed"],
    "buyer_confirmed": ["completed", "failed"],
    "completed": [],
    "cancelled": [],
    "failed": ["created", "awaiting_rider"],
}


def allowed_delivery_transitions(state: str) -> List[str]:
    return DELIVERY_TRANSITIONS.get(state, [])


def can_transition_delivery(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in DELIVERY_TRANSITIONS.get(current, [])


# ---------------------------------------------------------------------------
# Wholesale order state machine
# ---------------------------------------------------------------------------
ORDER_STATES = [
    "created",
    "pending",
    "accepted",
    "preparing",
    "ready_for_pickup",
    "picked_up",
    "in_transit",
    "delivered",
    "completed",
    "cancelled",
    "rejected",
]

ORDER_TRANSITIONS: Dict[str, List[str]] = {
    "created": ["pending", "cancelled"],
    "pending": ["accepted", "rejected", "cancelled"],
    "accepted": ["preparing", "cancelled"],
    "preparing": ["ready_for_pickup", "cancelled"],
    "ready_for_pickup": ["picked_up", "cancelled"],
    "picked_up": ["in_transit", "cancelled"],
    "in_transit": ["delivered", "cancelled"],
    "delivered": ["completed"],
    "completed": [],
    "cancelled": [],
    "rejected": [],
    "failed": ["created", "pending"],
}


def can_transition_order(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in ORDER_TRANSITIONS.get(current, [])


ORDER_COMPLETED_STATES = {"completed"}
SETTLEMENT_ELIGIBLE_ORDER_STATES = {"completed"}


# ---------------------------------------------------------------------------
# Payment / settlement state machine
# ---------------------------------------------------------------------------
PAYMENT_STATES = [
    "pending",
    "payment_initiated",
    "payment_confirmed",
    "held_pending_delivery_confirmation",
    "delivery_confirmed",
    "settlement_requested",
    "settled",
    "failed",
    "cancelled",
    "refunded",
]

PAYMENT_TRANSITIONS: Dict[str, List[str]] = {
    "pending": ["payment_initiated", "cancelled", "failed"],
    "payment_initiated": ["payment_confirmed", "pending", "failed"],
    "payment_confirmed": ["held_pending_delivery_confirmation", "failed"],
    "held_pending_delivery_confirmation": ["delivery_confirmed", "failed", "cancelled"],
    "delivery_confirmed": ["settlement_requested", "failed"],
    "settlement_requested": ["settled", "failed"],
    "settled": ["refunded"],
    "failed": ["payment_initiated", "cancelled"],
    "cancelled": [],
    "refunded": [],
}


def can_transition_payment(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in PAYMENT_TRANSITIONS.get(current, [])


# ---------------------------------------------------------------------------
# Complaint / dispute lifecycle
# ---------------------------------------------------------------------------
COMPLAINT_STATES = ["open", "under_review", "waiting_for_information", "resolved", "rejected"]

COMPLAINT_CATEGORIES = [
    "missing_item",
    "incorrect_quantity",
    "wrong_product",
    "damaged_goods",
    "poor_quality",
    "late_delivery",
    "rider_issue",
    "payment_issue",
    "other",
]

COMPLAINT_TRANSITIONS: Dict[str, List[str]] = {
    "open": ["under_review", "waiting_for_information"],
    "under_review": ["waiting_for_information", "resolved", "rejected"],
    "waiting_for_information": ["under_review", "resolved", "rejected"],
    "resolved": [],
    "rejected": [],
}


def can_transition_complaint(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in COMPLAINT_TRANSITIONS.get(current, [])


# ---------------------------------------------------------------------------
# Rider presence
# ---------------------------------------------------------------------------
RIDER_PRESENCE = ["offline", "online", "available", "busy", "unavailable"]

# GPS freshness thresholds (seconds)
RIDER_LOCATION_FRESH_SECONDS = 30
RIDER_LOCATION_STALE_SECONDS = 60
RIDER_NEARBY_MAX_DISTANCE_KM = 15


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance in kilometers between two points."""
    from math import radians, sin, cos, sqrt, atan2

    if None in (lat1, lng1, lat2, lng2):
        return 0.0
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return r * c


def etamp_from_km(distance_km: float, avg_speed_kmh: float = 25.0) -> float:
    """Optimistic ETA in minutes derived from a straight-line (haversine) distance."""
    if not distance_km or distance_km <= 0:
        return 0.0
    return round((distance_km / max(avg_speed_kmh, 1.0)) * 60.0, 1)


def location_is_fresh(ts: Optional[str], stale_after: int = RIDER_LOCATION_STALE_SECONDS) -> bool:
    if not ts:
        return False
    try:
        delta = (datetime.utcnow() - datetime.fromisoformat(ts)).total_seconds()
        return delta <= stale_after
    except Exception:
        return False
