"""
EXTRACTED STOCK SERVICE
=======================

Handles stock deduction logic extracted from stock_engine.py.
Used by SalesService to atomically validate and deduct stock.

Key responsibilities:
1. Validate item quantities are available
2. Handle simple products (direct deduction)
3. Handle composite products (recursive ingredient deduction)
4. Return detailed deduction records for audit trail
5. Support decimal quantities (kg, liters, etc.)
"""

from typing import Dict, List, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP


def safe_round(value: float, decimal_places: int = 4) -> float:
    """Safely round decimal quantities"""
    try:
        if value is None or (isinstance(value, float) and (value != value)):
            return 0.0
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except (ValueError, TypeError):
        return float(value) if value else 0.0


class StockService:
    """Stock validation and deduction"""
    
    def __init__(self, data_store=None):
        self.data_store = data_store
    
    def validate_and_deduct(
        self,
        products: List[Dict],
        expenses: List[Dict],
        items: List[Dict]
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate all items have sufficient stock WITHOUT modifying anything.
        
        Args:
            products: Full products list
            expenses: Full expenses list (for backward compat)
            items: Cart items [{productId, quantity, ...}, ...]
        
        Returns:
            (is_valid: bool, error_msg: str|None, deductions: Dict|None)
            
            deductions = {
                'products': [
                    {
                        'id': 1,
                        'name': 'Tilapia',
                        'before_qty': 23.0,
                        'after_qty': 20.0,
                        'deducted': 3.0,
                        'unit': 'kg',
                        'type': 'simple'
                    },
                    {
                        'id': 3,
                        'name': 'Salt',
                        'before_qty': 5.0,
                        'after_qty': 4.95,
                        'deducted': 0.05,
                        'unit': 'kg',
                        'type': 'composite',
                        'parent': 'Fried Fish'
                    }
                ],
                'expenses': [...]
            }
        """
        try:
            # Build lookup maps
            product_map = {p['id']: p for p in products}
            
            # Collect all deductions (don't modify yet)
            all_deductions = {
                'products': [],
                'expenses': []
            }
            
            # Track what we would deduct
            pending_deductions = {}  # product_id -> qty_to_deduct
            
            # ===== STEP 1: Validate requested items =====
            for item in items:
                product_id = item.get('productId')
                requested_qty = safe_round(float(item.get('quantity', 0)))
                
                if requested_qty <= 0:
                    return False, f'Invalid quantity for item: {requested_qty}', None
                
                if product_id not in product_map:
                    return False, f'Product not found: ID {product_id}', None
                
                product = product_map[product_id]
                current_qty = safe_round(float(product.get('quantity', 0)))
                
                # Check if we have enough
                if current_qty < requested_qty:
                    return False, (
                        f'Insufficient stock for {product["name"]}: '
                        f'need {requested_qty}{product.get("unit", "pcs")}, '
                        f'have {current_qty}{product.get("unit", "pcs")}'
                    ), None
                
                pending_deductions[product_id] = requested_qty
            
            # ===== STEP 2: Validate composite product ingredients =====
            for item in items:
                product_id = item.get('productId')
                product = product_map[product_id]
                requested_qty = pending_deductions[product_id]
                
                if product.get('isComposite'):
                    # Get ingredients
                    ingredients = product.get('recipe', product.get('ingredients', []))
                    
                    for ingredient in ingredients:
                        # Get ingredient product
                        ingredient_id = ingredient.get('productId')
                        if not ingredient_id:
                            ingredient_name = ingredient.get('name', 'Unknown')
                            ingredient_id = next(
                                (p['id'] for p in products if p['name'].lower() == ingredient_name.lower()),
                                None
                            )
                        
                        if not ingredient_id:
                            return False, (
                                f'Ingredient not found in {product["name"]}: '
                                f'{ingredient.get("name", "Unknown")}'
                            ), None
                        
                        ingredient_product = product_map.get(ingredient_id)
                        if not ingredient_product:
                            return False, f'Ingredient product not found: {ingredient_id}', None
                        
                        # Calculate how much ingredient is needed
                        qty_per_unit = safe_round(float(ingredient.get('quantity', 0)))
                        total_ingredient_needed = safe_round(requested_qty * qty_per_unit)
                        
                        # Check stock
                        current_ingredient_qty = safe_round(float(ingredient_product.get('quantity', 0)))
                        
                        if current_ingredient_qty < total_ingredient_needed:
                            return False, (
                                f'Insufficient ingredient for {product["name"]}: '
                                f'need {total_ingredient_needed}{ingredient_product.get("unit", "pcs")} of '
                                f'{ingredient_product["name"]}, '
                                f'have {current_ingredient_qty}{ingredient_product.get("unit", "pcs")}'
                            ), None
                        
                        # Add to pending
                        if ingredient_id not in pending_deductions:
                            pending_deductions[ingredient_id] = 0
                        pending_deductions[ingredient_id] += total_ingredient_needed
            
            # ===== STEP 3: Build deduction records (without modifying) =====
            processed_ingredients = set()
            
            for item in items:
                product_id = item.get('productId')
                product = product_map[product_id]
                requested_qty = pending_deductions[product_id]
                current_qty = safe_round(float(product.get('quantity', 0)))
                
                # Record main product deduction
                all_deductions['products'].append({
                    'id': product_id,
                    'name': product['name'],
                    'before_qty': current_qty,
                    'after_qty': safe_round(current_qty - requested_qty),
                    'deducted': requested_qty,
                    'unit': product.get('unit', 'pcs'),
                    'type': 'composite' if product.get('isComposite') else 'simple'
                })
                
                # Record ingredient deductions
                if product.get('isComposite'):
                    ingredients = product.get('recipe', product.get('ingredients', []))
                    
                    for ingredient in ingredients:
                        ingredient_id = ingredient.get('productId')
                        if not ingredient_id:
                            ingredient_id = next(
                                (p['id'] for p in products if p['name'].lower() == ingredient['name'].lower()),
                                None
                            )
                        
                        if ingredient_id not in processed_ingredients:
                            ingredient_product = product_map[ingredient_id]
                            qty_per_unit = safe_round(float(ingredient.get('quantity', 0)))
                            total_needed = safe_round(requested_qty * qty_per_unit)
                            current_ing_qty = safe_round(float(ingredient_product.get('quantity', 0)))
                            
                            all_deductions['products'].append({
                                'id': ingredient_id,
                                'name': ingredient_product['name'],
                                'before_qty': current_ing_qty,
                                'after_qty': safe_round(current_ing_qty - total_needed),
                                'deducted': total_needed,
                                'unit': ingredient_product.get('unit', 'pcs'),
                                'type': 'ingredient',
                                'parent': product['name']
                            })
                            
                            processed_ingredients.add(ingredient_id)
            
            # ===== STEP 4: Record expense deductions (for auto-expense creation) =====
            for deduction in all_deductions['products']:
                if deduction.get('type') == 'ingredient':
                    all_deductions['expenses'].append({
                        'id': deduction['id'],
                        'name': deduction['name'],
                        'qty_deducted': deduction['deducted'],
                        'unit': deduction['unit']
                    })
            
            return True, None, all_deductions
            
        except Exception as e:
            print(f"❌ Stock validation error: {str(e)}")
            import traceback
            traceback.print_exc()
            return False, f'Stock validation failed: {str(e)}', None
    
    def apply_deductions(
        self,
        products: List[Dict],
        deductions: Dict
    ) -> Optional[List[Dict]]:
        """
        Apply validated deductions to products (in-memory).
        
        Args:
            products: Product list (will be modified)
            deductions: Deductions dict from validate_and_deduct()
        
        Returns:
            Modified products list, or None if error
        """
        try:
            # Build map for quick lookup
            product_map = {p['id']: p for p in products}
            
            # Apply each deduction
            for deduction in deductions.get('products', []):
                product_id = deduction['id']
                deduct_qty = safe_round(float(deduction['deducted']))
                
                if product_id not in product_map:
                    continue
                
                product = product_map[product_id]
                current_qty = safe_round(float(product.get('quantity', 0)))
                new_qty = safe_round(current_qty - deduct_qty)
                
                # Prevent negative stock
                if new_qty < 0:
                    print(f"⚠️  Would go negative: {product['name']} {new_qty} -> setting to 0")
                    new_qty = 0
                
                product['quantity'] = new_qty
            
            return products
            
        except Exception as e:
            print(f"❌ Error applying deductions: {str(e)}")
            return None
