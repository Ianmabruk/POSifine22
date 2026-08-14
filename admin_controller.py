"""
Admin Controller
================
Product and sales management for admin workflows.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class AdminController:
    """Admin operations for products and reporting."""

    def __init__(self, datastore, stock_engine):
        self.datastore = datastore
        self.stock_engine = stock_engine

    @staticmethod
    def _normalize_product(product: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not product:
            return product
        normalized = dict(product)
        visible = normalized.get("visible_to_cashier")
        if visible is None:
            visible = normalized.get("visibleToCashier", True)
        normalized["visible_to_cashier"] = bool(visible)
        normalized["visibleToCashier"] = bool(visible)
        return normalized

    # ============================================================
    # Products
    # ============================================================

    def create_product(
        self,
        account_id: str,
        created_by: int,
        name: str,
        price: float,
        cost: float = 0.0,
        quantity: float = 0.0,
        category: str = "general",
        unit: str = "pcs",
        is_composite: bool = False,
        recipe: Optional[List[Dict[str, Any]]] = None,
        product_type: Optional[str] = None,
        **extra_fields
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if not name:
            return False, "Product name is required", None

        now = datetime.utcnow().isoformat()
        # Keep both cost fields synchronized at creation time.
        base_cost = float(cost or 0.0)
        base_cost_per_unit = extra_fields.get("cost_per_unit")
        try:
            base_cost_per_unit = float(base_cost_per_unit) if base_cost_per_unit is not None else base_cost
        except (TypeError, ValueError):
            base_cost_per_unit = base_cost

        try:
            product_data = {
                "account_id": account_id,
                "name": name,
                "price": float(price or 0),
                "cost": base_cost,
                "quantity": float(quantity or 0.0),
                "category": category or "general",
                "unit": unit or "pcs",
                "is_composite": bool(is_composite),
                "recipe": recipe or [],
                "product_type": product_type or ("composite" if is_composite else "regular"),
                "created_at": now,
                "created_by": created_by,
                "updated_at": None,
                "reorder_level": float(extra_fields.get("reorder_level") or 0.0),
                "max_stock_level": float(extra_fields.get("max_stock_level") or 0.0),
                "cost_per_unit": base_cost_per_unit,
                "enable_weight_pricing": bool(extra_fields.get("enable_weight_pricing") or False),
                "barcode": extra_fields.get("barcode"),
                "sku": extra_fields.get("sku"),
                "image": extra_fields.get("image"),
                "visible_to_cashier": bool(extra_fields.get("visible_to_cashier", True))
            }
        except (TypeError, ValueError) as exc:
            logger.error("Product data validation error: %s", exc, exc_info=True)
            return False, "Invalid product data. Please check numeric fields.", None

        try:
            product = self.datastore.create("products", product_data)
        except Exception as exc:
            logger.error("Failed to create product in datastore: %s", exc, exc_info=True)
            return False, "Failed to save product. Please try again.", None

        return True, None, self._normalize_product(product)

    def get_products(self, account_id: str) -> List[Dict[str, Any]]:
        return [self._normalize_product(product) for product in self.datastore.get_all("products", account_id)]

    def update_product(
        self,
        product_id: int,
        account_id: str,
        **updates
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if not updates:
            return False, "No updates provided", None

        # Keep both cost fields in sync regardless of which one the client sends.
        if "cost" in updates and "cost_per_unit" not in updates:
            updates["cost_per_unit"] = updates.get("cost")
        if "cost_per_unit" in updates and "cost" not in updates:
            updates["cost"] = updates.get("cost_per_unit")

        updates["updated_at"] = datetime.utcnow().isoformat()
        success = self.datastore.update("products", product_id, updates, account_id)
        if not success:
            return False, "Product not found", None

        updated = self.datastore.get_by_id("products", product_id, account_id)
        return True, None, self._normalize_product(updated)

    def update_stock(self, product_id: int, account_id: str, quantity: float) -> Tuple[bool, Optional[str]]:
        success = self.datastore.update("products", product_id, {
            "quantity": float(quantity),
            "updated_at": datetime.utcnow().isoformat()
        }, account_id)
        if not success:
            return False, "Product not found"
        return True, None

    def delete_product(self, product_id: int, account_id: str) -> Tuple[bool, Optional[str]]:
        success = self.datastore.delete("products", product_id, account_id)
        if not success:
            return False, "Product not found"
        return True, None

    def check_low_stock(self, account_id: str) -> List[Dict[str, Any]]:
        products = self.datastore.get_all("products", account_id)
        warnings = []
        for product in products:
            reorder_level = float(product.get("reorder_level") or 0.0)
            quantity = float(product.get("quantity") or 0.0)
            if reorder_level > 0 and quantity < reorder_level:
                warnings.append(product)
        return warnings

    # ============================================================
    # Sales
    # ============================================================

    def get_sales(self, account_id: str) -> List[Dict[str, Any]]:
        return self.datastore.get_all("sales", account_id)
