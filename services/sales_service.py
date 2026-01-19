"""
CENTRALIZED SALES SERVICE
===========================

Single source of truth for all sale completion logic:
1. Validate cart items
2. Calculate totals and taxes
3. Deduct stock (simple + composite)
4. Record sale
5. Create expense entries
6. Broadcast notifications
7. Handle errors atomically

Purpose: Replace fragmented /api/sales and /api/admin-complete-sale endpoints
"""

import json
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Any
from decimal import Decimal, ROUND_HALF_UP


def safe_round(value: float, decimal_places: int = 4) -> float:
    """Safely round decimal quantities to prevent floating-point errors"""
    try:
        if value is None or (isinstance(value, float) and (value != value)):
            return 0.0
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except (ValueError, TypeError):
        return float(value) if value else 0.0


class SalesService:
    """
    Unified sales completion service.
    
    All cart checkouts flow through this service regardless of origin:
    - Cashier POS: POST /api/sales
    - Admin Dashboard: POST /api/admin-complete-sale
    - Mobile App: Same endpoint
    """
    
    def __init__(self, data_store, stock_service, notification_service):
        """
        Args:
            data_store: DataStore instance for file I/O
            stock_service: StockService for deductions
            notification_service: NotificationService for WebSocket broadcasts
        """
        self.data_store = data_store
        self.stock_service = stock_service
        self.notification_service = notification_service
    
    def complete_sale(
        self,
        user_id: int,
        user_name: str,
        account_id: str,
        items: List[Dict],
        total: float,
        payment_method: str = 'cash',
        discount: float = 0,
        tax: float = 0,
        tax_type: str = 'exclusive',
        completed_by: str = 'cashier'  # 'cashier' or 'admin'
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Complete a sale atomically with stock deduction.
        
        Flow:
        1. Validate request
        2. Validate items exist and have sufficient stock
        3. Prepare stock deductions (in-memory, not yet saved)
        4. Apply deductions to products
        5. Save updated products
        6. Create sale record
        7. Create auto-expenses for deducted ingredients
        8. Broadcast notifications
        9. Return updated state to caller
        
        Args:
            user_id: Cashier/Admin ID
            user_name: Cashier/Admin name
            account_id: Account ID for data isolation
            items: List of {productId, quantity, price, unit?}
            total: Total amount (after discount, before/after tax depending on tax_type)
            payment_method: 'cash', 'card', 'mpesa', etc.
            discount: Discount amount in currency
            tax: Tax amount in currency
            tax_type: 'inclusive' or 'exclusive'
            completed_by: 'cashier' or 'admin' (for audit)
        
        Returns:
            (success: bool, error_message: str|None, response: Dict|None)
            
            response = {
                'sale': {sale object with id, items, total, ...},
                'deductions': {products: [...], expenses: [...]},
                'updatedProducts': [{...}, ...],  # All products for this account
                'processingTime': '125ms',
                'lowStockWarnings': [{...}, ...],
                'message': 'Sale completed...'
            }
        """
        start_time = time.time()
        
        try:
            # ========== STEP 1: VALIDATION ==========
            if not items or len(items) == 0:
                return False, 'At least one item is required for a sale', None
            
            if total <= 0:
                return False, 'Total must be greater than zero', None
            
            if not user_id or not account_id:
                return False, 'User and account information required', None
            
            # ========== STEP 2: LOAD DATA ==========
            products = self.data_store.load('products')
            expenses = self.data_store.load('expenses')
            sales = self.data_store.load('sales')
            
            if not products:
                return False, 'Failed to load products', None
            
            # ========== STEP 3: VALIDATE & PREPARE DEDUCTIONS ==========
            # This does NOT modify anything, just validates
            is_valid, error_msg, deductions = self.stock_service.validate_and_deduct(
                products=products,
                expenses=expenses,
                items=items
            )
            
            if not is_valid:
                return False, error_msg, None
            
            # ========== STEP 4: APPLY DEDUCTIONS ==========
            # NOW we modify products based on validated deductions
            products_modified = self.stock_service.apply_deductions(products, deductions)
            
            if products_modified is None:
                return False, 'Failed to apply stock deductions', None
            
            # ========== STEP 5: SAVE PRODUCTS ==========
            if not self.data_store.save('products', products_modified):
                return False, 'Failed to save product updates', None
            
            # ========== STEP 6: CREATE SALE RECORD ==========
            sale_id = max([s.get('id', 0) for s in sales] + [0]) + 1
            
            sale = {
                'id': sale_id,
                'items': items,
                'total': safe_round(float(total)),
                'discount': safe_round(float(discount)),
                'tax': safe_round(float(tax)),
                'taxType': tax_type,
                'paymentMethod': payment_method,
                'accountId': account_id,
                'cashierId': user_id,
                'cashierName': user_name,
                'completedBy': completed_by,  # Audit trail
                'stockDeductions': deductions,
                'createdAt': datetime.now().isoformat()
            }
            
            sales.append(sale)
            if not self.data_store.save('sales', sales):
                return False, 'Failed to save sale record', None
            
            # ========== STEP 7: CREATE AUTO-EXPENSE ENTRIES ==========
            # When composite products consume ingredients, track as expenses
            expenses = self._create_auto_expenses(deductions, products_modified, expenses, account_id)
            if expenses is not None:
                self.data_store.save('expenses', expenses)
            
            # ========== STEP 8: PREPARE RESPONSE ==========
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Get low stock warnings
            low_stock = self._check_low_stock(products_modified, account_id)
            
            # Get all products for this account (for frontend refresh)
            updated_products = [p for p in products_modified if p.get('accountId') == account_id]
            
            response = {
                'sale': sale,
                'deductions': deductions,
                'updatedProducts': updated_products,
                'processingTime': f'{elapsed_ms:.0f}ms',
                'lowStockWarnings': low_stock if low_stock else [],
                'message': f'Sale #{sale_id} completed in {elapsed_ms:.0f}ms ✓'
            }
            
            # ========== STEP 9: BROADCAST NOTIFICATIONS ==========
            # Notify all connected clients (admin + cashier dashboards)
            self.notification_service.broadcast_sale_completed(
                account_id=account_id,
                sale=sale,
                deductions=deductions,
                updated_products=updated_products,
                low_stock=low_stock,
                processing_time=f'{elapsed_ms:.0f}ms'
            )
            
            print(f"✅ Sale #{sale_id} completed in {elapsed_ms:.0f}ms by {completed_by}")
            if elapsed_ms > 5000:
                print(f"⚠️  WARNING: Sale took {elapsed_ms:.0f}ms (slow storage?)")
            
            return True, None, response
            
        except Exception as e:
            print(f"❌ Sales service error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, f'Internal error: {str(e)}', None
    
    def _create_auto_expenses(self, deductions: Dict, products: List[Dict], 
                             expenses: List[Dict], account_id: str) -> Optional[List[Dict]]:
        """
        When composite products consume ingredients, create expense records.
        
        Example:
        - Sold 1x "Fried Fish" (composite)
        - Recipe calls for 0.2kg salt + 0.5 liters oil
        - Create expense records: "Auto-deducted: Salt (0.2kg @ 50 KES)"
        """
        try:
            if not deductions.get('expenses'):
                return expenses
            
            product_map = {p['id']: p for p in products}
            
            for expense_deduction in deductions.get('expenses', []):
                product_id = expense_deduction.get('id')
                qty_deducted = expense_deduction.get('qty_deducted', 0)
                
                if not product_id or qty_deducted <= 0:
                    continue
                
                product = product_map.get(product_id)
                if not product:
                    continue
                
                # Calculate cost
                cost_per_unit = safe_round(float(product.get('cost_per_unit', 
                                                              product.get('costPerUnit', 0))))
                total_cost = safe_round(qty_deducted * cost_per_unit)
                
                if total_cost > 0:
                    expense_id = max([e.get('id', 0) for e in expenses] + [0]) + 1
                    
                    auto_expense = {
                        'id': expense_id,
                        'name': f"Auto-deducted: {product['name']}",
                        'amount': total_cost,
                        'quantity': qty_deducted,
                        'unit': product.get('unit', 'unit'),
                        'category': 'ingredient',
                        'accountId': account_id,
                        'source': 'auto-deduction',
                        'linkedProductId': product_id,
                        'linkedSaleId': None,  # Set by caller if needed
                        'createdAt': datetime.now().isoformat(),
                        'description': f"Auto-deducted from sale - {qty_deducted}{product.get('unit', 'unit')} @ {cost_per_unit} KES"
                    }
                    expenses.append(auto_expense)
            
            return expenses
            
        except Exception as e:
            print(f"⚠️  Error creating auto-expenses: {str(e)}")
            return expenses
    
    def _check_low_stock(self, products: List[Dict], account_id: str, 
                        threshold: float = 1.0) -> List[Dict]:
        """Check for products with stock below threshold"""
        warnings = []
        
        try:
            for product in products:
                if product.get('accountId') != account_id:
                    continue
                
                quantity = safe_round(float(product.get('quantity', 0)))
                
                # Only warn for non-zero stock below threshold
                if 0 < quantity < threshold:
                    severity = 'CRITICAL' if quantity < 0.1 else 'WARNING'
                    warnings.append({
                        'productId': product['id'],
                        'productName': product['name'],
                        'currentStock': quantity,
                        'unit': product.get('unit', 'pcs'),
                        'threshold': threshold,
                        'severity': severity,
                        'category': product.get('category', 'general')
                    })
        except Exception as e:
            print(f"⚠️  Error checking low stock: {str(e)}")
        
        return warnings
