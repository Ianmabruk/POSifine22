"""
Cashier Controller
==================
Handles complete sale flows with stock deduction.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class CashierController:
    """Cashier operations including complete sale."""

    def __init__(self, datastore, stock_engine):
        self.datastore = datastore
        self.stock_engine = stock_engine

    def complete_sale(
        self,
        account_id: str,
        cashier_id: int,
        cashier_name: str,
        items: List[Dict[str, Any]],
        payment_method: str = "cash",
        amount_paid: float = 0.0,
        tax_rate: float = 0.0,
        discount_amount: float = 0.0,
        service_fee: float = 0.0
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        if not items:
            return False, "Sale items are required", None

        return self.stock_engine.execute_sale(
            items=items,
            account_id=account_id,
            cashier_id=cashier_id,
            cashier_name=cashier_name,
            payment_method=payment_method,
            amount_paid=float(amount_paid or 0.0),
            tax_rate=float(tax_rate or 0.0),
            discount_amount=float(discount_amount or 0.0),
            service_fee=float(service_fee or 0.0)
        )
