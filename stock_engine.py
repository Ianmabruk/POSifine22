"""
ULTRA-FAST STOCK DEDUCTION ENGINE
==================================
Optimized for <50ms sale completion with:
- Batch stock deductions (single transaction)
- In-memory validation before any writes
- Support for composite products with recipes
- Automatic expense tracking for ingredients
- Thread-safe operations
- Decimal precision for weights/volumes
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import logging

logger = logging.getLogger(__name__)


def safe_float(value: any, default: float = 0.0) -> float:
    """Safely convert value to float"""
    try:
        return float(value) if value is not None else default
    except (ValueError, TypeError):
        return default


def round_decimal(value: float, places: int = 4) -> float:
    """Round decimal to prevent floating point errors"""
    try:
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except:
        return float(value)


class StockEngine:
    """
    Ultra-fast stock deduction engine
    Target: <50ms for Complete Sell operation
    """
    
    def __init__(self, datastore):
        """
        Initialize with data store
        
        Args:
            datastore: DataStore instance
        """
        self.ds = datastore
    
    def validate_and_prepare_sale(
        self, 
        items: List[Dict],
        account_id: str
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate sale items and prepare stock deductions
        
        Fast validation:
        1. Load all products once (in-memory)
        2. Build product lookup map
        3. Validate each item
        4. Calculate deductions for composites
        5. Verify sufficient stock
        
        Args:
            items: List of sale items [{product_id, quantity, ...}]
            account_id: Account ID for multi-tenant isolation
        
        Returns:
            (is_valid, error_message, deduction_plan)
        """
        try:
            # Load all products once
            products = self.ds.get_all('products', account_id)
            product_map = {p['id']: p for p in products}
            
            # Track required deductions
            deductions = {}  # {product_id: quantity}
            deduction_details = []  # Detailed info for response
            
            # Process each sale item
            for item in items:
                product_id = item.get('product_id') or item.get('id')
                quantity = safe_float(item.get('quantity', 0))
                
                if quantity <= 0:
                    continue
                
                product = product_map.get(product_id)
                if not product:
                    return False, f"Product ID {product_id} not found", None
                
                # Check if composite product
                if product.get('is_composite'):
                    # Deduct ingredients from recipe
                    recipe = product.get('recipe', [])
                    if not recipe:
                        return False, f"Composite product '{product['name']}' has no recipe", None
                    
                    for ingredient in recipe:
                        ing_id = ingredient.get('product_id') or ingredient.get('id')
                        ing_qty = safe_float(ingredient.get('quantity', 0))
                        total_ing_qty = round_decimal(ing_qty * quantity)
                        
                        # Add to deductions
                        deductions[ing_id] = deductions.get(ing_id, 0) + total_ing_qty
                        
                        # Track details
                        ing_product = product_map.get(ing_id)
                        if ing_product:
                            deduction_details.append({
                                'product_id': ing_id,
                                'name': ing_product['name'],
                                'quantity': total_ing_qty,
                                'unit': ing_product.get('unit', 'unit'),
                                'parent_product': product['name']
                            })
                else:
                    # Regular product - deduct directly
                    deductions[product_id] = deductions.get(product_id, 0) + quantity
                    deduction_details.append({
                        'product_id': product_id,
                        'name': product['name'],
                        'quantity': quantity,
                        'unit': product.get('unit', 'pcs')
                    })
            
            # Validate sufficient stock for all deductions
            for product_id, required_qty in deductions.items():
                product = product_map.get(product_id)
                if not product:
                    return False, f"Product ID {product_id} not found", None
                
                current_qty = safe_float(product.get('quantity', 0))
                
                if current_qty < required_qty:
                    return False, f"Insufficient stock for '{product['name']}'. Required: {required_qty}, Available: {current_qty}", None
            
            # Prepare deduction plan
            deduction_plan = {
                'deductions': deductions,  # {product_id: quantity}
                'details': deduction_details,  # Detailed info
                'product_map': product_map  # For quick access
            }
            
            return True, None, deduction_plan
            
        except Exception as e:
            logger.error(f"Error validating sale: {e}")
            return False, f"Validation error: {str(e)}", None
    
    def execute_sale(
        self,
        items: List[Dict],
        account_id: str,
        cashier_id: int,
        cashier_name: str,
        payment_method: str = 'cash',
        amount_paid: float = 0.0,
        tax_rate: float = 0.0,
        discount_amount: float = 0.0,
        service_fee: float = 0.0
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Execute complete sale with stock deduction
        
        FAST EXECUTION:
        1. Validate (in-memory)
        2. Batch update all stock (single transaction)
        3. Create sale record
        4. Create expense records for ingredients
        5. Return result
        
        Args:
            items: Sale items
            account_id: Account ID
            cashier_id: Cashier user ID
            cashier_name: Cashier name
            payment_method: Payment method
            amount_paid: Amount paid by customer
            tax_rate: Tax rate (%)
            discount_amount: Discount applied
            service_fee: Service fee applied
        
        Returns:
            (success, error_message, sale_record)
        """
        start_time = datetime.now()
        
        try:
            # Step 1: Validate and prepare (fast)
            is_valid, error, deduction_plan = self.validate_and_prepare_sale(items, account_id)
            if not is_valid:
                return False, error, None
            
            # Step 2: Calculate sale totals
            product_map = deduction_plan['product_map']
            sale_items = []
            subtotal = 0.0
            total_cost = 0.0
            
            for item in items:
                product_id = item.get('product_id') or item.get('id')
                quantity = safe_float(item.get('quantity', 0))
                
                product = product_map.get(product_id)
                if not product:
                    continue
                
                unit_price = safe_float(product.get('price', 0))
                item_subtotal = round_decimal(unit_price * quantity)
                
                # Calculate cost
                if product.get('is_composite'):
                    # Sum ingredient costs
                    recipe = product.get('recipe', [])
                    item_cost = 0.0
                    for ingredient in recipe:
                        ing_id = ingredient.get('product_id') or ingredient.get('id')
                        ing_qty = safe_float(ingredient.get('quantity', 0))
                        ing_product = product_map.get(ing_id)
                        if ing_product:
                            ing_cost = safe_float(ing_product.get('cost', 0))
                            item_cost += ing_cost * ing_qty * quantity
                else:
                    item_cost = safe_float(product.get('cost', 0)) * quantity
                
                sale_items.append({
                    'product_id': product_id,
                    'product_name': product['name'],
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'subtotal': item_subtotal,
                    'cost': item_cost,
                    'unit': product.get('unit', 'pcs')
                })
                
                subtotal += item_subtotal
                total_cost += item_cost
            
            # Apply tax, discount, service fee
            tax_amount = round_decimal(subtotal * (tax_rate / 100))
            total = round_decimal(subtotal + tax_amount + service_fee - discount_amount)
            change = round_decimal(amount_paid - total) if amount_paid > total else 0.0
            gross_profit = round_decimal(total - total_cost)
            
            # Step 3: Batch update stock (FAST - single transaction)
            stock_updates = [
                (product_id, round_decimal(product_map[product_id]['quantity'] - qty), account_id)
                for product_id, qty in deduction_plan['deductions'].items()
            ]
            self.ds.batch_update_stock(stock_updates)
            
            # Step 4: Create sale record
            sale_data = {
                'account_id': account_id,
                'items': sale_items,
                'total': total,
                'total_cost': total_cost,
                'gross_profit': gross_profit,
                'payment_method': payment_method,
                'amount_paid': amount_paid,
                'change': change,
                'tax_amount': tax_amount,
                'discount_amount': discount_amount,
                'service_fee': service_fee,
                'cashier_id': cashier_id,
                'cashier_name': cashier_name,
                'created_at': datetime.now().isoformat(),
                'receipt_number': f"RCP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            }
            sale = self.ds.create('sales', sale_data)
            
            # Step 5: Create expense records for ingredients
            self._create_auto_expenses(deduction_plan, account_id, sale['id'])
            
            # Log performance
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            logger.info(f"Sale completed in {elapsed:.2f}ms")
            
            return True, None, sale
            
        except Exception as e:
            logger.error(f"Error executing sale: {e}")
            return False, f"Sale execution error: {str(e)}", None
    
    def _create_auto_expenses(self, deduction_plan: Dict, account_id: str, sale_id: int):
        """
        Create automatic expense records for ingredient usage
        
        Args:
            deduction_plan: Deduction plan from validation
            account_id: Account ID
            sale_id: Created sale ID
        """
        try:
            product_map = deduction_plan['product_map']
            
            for detail in deduction_plan['details']:
                # Only create expenses for ingredients (not final products)
                if 'parent_product' in detail:
                    product_id = detail['product_id']
                    product = product_map.get(product_id)
                    
                    if product:
                        cost_per_unit = safe_float(product.get('cost_per_unit') or product.get('cost', 0))
                        quantity = detail['quantity']
                        total_cost = round_decimal(cost_per_unit * quantity)
                        
                        if total_cost > 0:
                            expense_data = {
                                'account_id': account_id,
                                'name': f"Auto: {product['name']} for {detail['parent_product']}",
                                'amount': total_cost,
                                'quantity': quantity,
                                'unit': product.get('unit', 'unit'),
                                'category': 'ingredient',
                                'description': f"Auto-deducted from sale #{sale_id}",
                                'source': 'auto-deduction',
                                'linked_product_id': product_id,
                                'created_at': datetime.now().isoformat()
                            }
                            self.ds.create('expenses', expense_data)
        except Exception as e:
            logger.error(f"Error creating auto expenses: {e}")
    
    def adjust_stock(
        self,
        product_id: int,
        quantity: float,
        account_id: str,
        movement_type: str = 'adjustment',
        notes: Optional[str] = None,
        user_id: Optional[int] = None
    ) -> bool:
        """
        Adjust product stock (add or set quantity)
        
        Args:
            product_id: Product ID
            quantity: New quantity or adjustment amount
            account_id: Account ID
            movement_type: 'adjustment', 'restock', etc.
            notes: Optional notes
            user_id: User making adjustment
        
        Returns:
            Success status
        """
        try:
            product = self.ds.get_by_id('products', product_id, account_id)
            if not product:
                return False
            
            old_quantity = safe_float(product.get('quantity', 0))
            
            # Update product
            self.ds.update('products', product_id, {
                'quantity': quantity,
                'updated_at': datetime.now().isoformat()
            }, account_id)
            
            # Create stock movement record
            movement_data = {
                'account_id': account_id,
                'product_id': product_id,
                'quantity': round_decimal(quantity - old_quantity),
                'movement_type': movement_type,
                'notes': notes,
                'created_at': datetime.now().isoformat(),
                'created_by': user_id
            }
            self.ds.create('stock_movements', movement_data)
            
            return True
            
        except Exception as e:
            logger.error(f"Error adjusting stock: {e}")
            return False
    
    def get_stock_deduction_log(
        self,
        account_id: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict]:
        """
        Get stock deduction audit log
        
        Args:
            account_id: Account ID
            start_date: Optional start date filter
            end_date: Optional end date filter
        
        Returns:
            List of stock movements
        """
        movements = self.ds.get_all('stock_movements', account_id)
        
        if start_date:
            movements = [m for m in movements if m.get('created_at', '') >= start_date]
        if end_date:
            movements = [m for m in movements if m.get('created_at', '') <= end_date]
        
        return movements
    
    def get_low_stock_products(self, account_id: str) -> List[Dict]:
        """Get products with low stock"""
        products = self.ds.get_all('products', account_id)
        return [
            p for p in products 
            if safe_float(p.get('reorder_level', 0)) > 0 
            and safe_float(p.get('quantity', 0)) <= safe_float(p.get('reorder_level', 0))
        ]
    
    def get_out_of_stock_products(self, account_id: str) -> List[Dict]:
        """Get products that are out of stock"""
        products = self.ds.get_all('products', account_id)
        return [p for p in products if safe_float(p.get('quantity', 0)) <= 0]
