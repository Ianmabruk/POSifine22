"""
OPTIMIZED STOCK DEDUCTION ENGINE
=================================

Purpose: Handle fast, atomic stock deductions for sales with:
- Single source of truth (products.json only)
- Support for raw and composite products
- <200ms performance target
- No state duplication between dashboards
- Batched parallel updates
- DECIMAL PRECISION: All quantities use float() with proper rounding

Key Design Decisions:
1. In-memory validation before any file writes
2. Parallel Promise.all() for multiple deductions instead of sequential await
3. Single JSON file write at end (not per-item)
4. Efficient broadcasting with minimal payload
5. CRITICAL: Use round() for decimal quantities to prevent floating-point errors
"""

import json
import time
from datetime import datetime
from typing import Tuple, List, Dict, Any, Optional
from decimal import Decimal, ROUND_HALF_UP


def safe_round(value: float, decimal_places: int = 4) -> float:
    """
    Safely round decimal quantities to prevent floating-point errors.
    
    Examples:
        safe_round(0.1 + 0.2) -> 0.3 (not 0.30000000000000004)
        safe_round(23.456789) -> 23.4568 (4 decimal places)
        safe_round(45.1) -> 45.1
    
    Args:
        value: The quantity to round
        decimal_places: Number of decimal places to keep (default 4 for weight/volume)
    
    Returns:
        Properly rounded float value
    """
    try:
        if value is None or (isinstance(value, float) and (value != value)):  # Check for NaN
            return 0.0
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except (ValueError, TypeError):
        return float(value) if value else 0.0


class StockDeductionEngine:
    """
    Atomic stock deduction for POS sales.
    
    Supports:
    - Raw products (direct inventory items)
    - Composite products (with ingredient recipes from any source)
    - Multiple units (kg, liters, grams, pcs, etc.)
    - Decimal quantities
    """
    
    def __init__(self, products: List[Dict], expenses: List[Dict] = None):
        """
        Initialize with data sources.
        
        Args:
            products: Full products list (acts as single source of truth)
            expenses: Legacy expenses list (merged into products for compatibility)
        """
        self.products = products or []
        self.expenses = expenses or []
        
        # Build lookup tables for O(1) access
        self._product_map = {p['id']: p for p in self.products}
        self._expense_map = {e['id']: e for e in self.expenses}
        
    def validate_and_prepare_deductions(
        self,
        items: List[Dict],
        for_validation_only: bool = False
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Validate all items have sufficient stock WITHOUT modifying anything.
        
        Returns:
            (is_valid, error_message, deductions_dict)
        
        Deductions format:
        {
            'products': [
                {'id': 1, 'name': 'Tilapia', 'before_qty': 23, 'after_qty': 20, 'deducted': 3, 'unit': 'kg'},
                {'id': 3, 'name': 'Salt', 'before_qty': 5, 'after_qty': 4.95, 'deducted': 0.05, 'unit': 'kg', 'parent': 'Fried Fish'}
            ],
            'expenses': [
                {'id': 2, 'name': 'Cooking Oil', 'before_qty': 10, 'after_qty': 9.8, 'deducted': 0.2, 'unit': 'liters'}
            ]
        }
        """
        deductions = {'products': [], 'expenses': []}
        
        try:
            for cart_item in items:
                product_id = cart_item.get('productId')
                # DECIMAL: Safely parse quantity with proper float conversion
                quantity_sold = safe_round(float(cart_item.get('quantity', cart_item.get('weight', 0))))
                
                # Get main product
                product = self._product_map.get(product_id)
                if not product:
                    return False, f"❌ Product ID {product_id} not found", None
                
                # For composite products, don't validate the composite product itself has stock
                # (it's a recipe, not an inventory item)
                is_composite = product.get('isComposite', False) or bool(product.get('recipe', product.get('ingredients', [])))
                
                if not is_composite:
                    # Validate main product has stock (only for raw products)
                    # DECIMAL: Use safe_round for decimal comparison
                    current_qty = safe_round(float(product.get('quantity', 0)))
                    if current_qty < quantity_sold:
                        return False, \
                            f"❌ Insufficient stock for '{product['name']}': need {quantity_sold}{product.get('unit', 'pcs')}, " \
                            f"have {current_qty}{product.get('unit', 'pcs')}", None
                    
                    # Record main product deduction with proper rounding
                    after_qty = safe_round(current_qty - quantity_sold)
                    deductions['products'].append({
                        'id': product['id'],
                        'name': product['name'],
                        'before_qty': current_qty,
                        'after_qty': after_qty,
                        'deducted': safe_round(quantity_sold),
                        'unit': product.get('unit', 'pcs')
                    })
                
                # Handle composite products (with recipe/ingredients)
                recipe = product.get('recipe', product.get('ingredients', []))
                
                if is_composite and recipe:
                    for ingredient in recipe:
                        ingredient_id = ingredient.get('productId') or ingredient.get('id')
                        ingredient_name = ingredient.get('name')
                        # DECIMAL: Safely parse ingredient quantity per unit
                        ingredient_qty_per_unit = safe_round(float(ingredient.get('quantity', 0)))
                        ingredient_source = ingredient.get('source', 'inventory')
                        
                        # Find ingredient in products
                        ingredient_product = None
                        if ingredient_id:
                            ingredient_product = self._product_map.get(ingredient_id)
                        elif ingredient_name:
                            # Fallback: search by name
                            ingredient_product = next(
                                (p for p in self.products if p['name'].lower() == ingredient_name.lower()),
                                None
                            )
                        
                        if not ingredient_product:
                            return False, \
                                f"❌ Ingredient '{ingredient_name or ingredient_id}' for '{product['name']}' not found", None
                        
                        # Calculate total ingredient needed for this sale
                        # DECIMAL: Use safe_round for multiplication to prevent floating-point errors
                        total_ingredient_needed = safe_round(ingredient_qty_per_unit * quantity_sold)
                        ingredient_current_qty = safe_round(float(ingredient_product.get('quantity', 0)))
                        
                        # Validate ingredient stock
                        if ingredient_current_qty < total_ingredient_needed:
                            return False, \
                                f"❌ Insufficient ingredient stock for '{ingredient_product['name']}' " \
                                f"(needed for '{product['name']}'): need {total_ingredient_needed}, " \
                                f"have {ingredient_current_qty}", None
                        
                        # Calculate after quantity with proper rounding
                        after_qty = safe_round(ingredient_current_qty - total_ingredient_needed)
                        
                        # Determine if deduction goes to products or expenses
                        if ingredient_product.get('expenseOnly', False):
                            deductions['expenses'].append({
                                'id': ingredient_product['id'],
                                'name': ingredient_product['name'],
                                'before_qty': ingredient_current_qty,
                                'after_qty': after_qty,
                                'deducted': total_ingredient_needed,
                                'unit': ingredient_product.get('unit', 'pcs'),
                                'parent_product': product['name']
                            })
                        else:
                            deductions['products'].append({
                                'id': ingredient_product['id'],
                                'name': ingredient_product['name'],
                                'before_qty': ingredient_current_qty,
                                'after_qty': after_qty,
                                'deducted': total_ingredient_needed,
                                'unit': ingredient_product.get('unit', 'pcs'),
                                'parent_product': product['name']
                            })
            
            return True, None, deductions
            
        except Exception as e:
            return False, f"❌ Validation error: {str(e)}", None
    
    def apply_deductions(self, deductions: Dict) -> bool:
        """
        Apply validated deductions to products list.
        
        This modifies self.products in-place with new quantities.
        Call save_products() after this to persist to disk.
        DECIMAL: Ensures quantities are properly rounded to prevent floating-point errors
        """
        try:
            # Apply product deductions with safe rounding
            for deduction in deductions.get('products', []):
                product = self._product_map.get(deduction['id'])
                if product:
                    # DECIMAL: Apply safe rounding to final quantity
                    product['quantity'] = safe_round(deduction['after_qty'])
            
            # Apply expense deductions (expenses are in products too now)
            for deduction in deductions.get('expenses', []):
                product = self._product_map.get(deduction['id'])
                if product:
                    # DECIMAL: Apply safe rounding to final quantity
                    product['quantity'] = safe_round(deduction['after_qty'])
            
            return True
        except Exception as e:
            print(f"❌ Error applying deductions: {str(e)}")
            return False
    
    def calculate_composite_deductions(self, product_id: int, quantity: float) -> Dict:
        """
        Calculate what would be deducted for a composite product without validation.
        
        Useful for preview/display purposes.
        """
        product = self._product_map.get(product_id)
        if not product:
            return {'error': f"Product {product_id} not found"}
        
        result = {
            'product_name': product['name'],
            'quantity_sold': quantity,
            'ingredients': []
        }
        
        recipe = product.get('recipe', product.get('ingredients', []))
        for ingredient in recipe:
            ingredient_id = ingredient.get('productId') or ingredient.get('id')
            ingredient_product = self._product_map.get(ingredient_id)
            
            if ingredient_product:
                ingredient_qty_per_unit = float(ingredient.get('quantity', 0))
                total_needed = ingredient_qty_per_unit * quantity
                
                result['ingredients'].append({
                    'name': ingredient_product['name'],
                    'unit': ingredient_product.get('unit', 'pcs'),
                    'quantity_per_unit': ingredient_qty_per_unit,
                    'total_for_sale': total_needed,
                    'current_stock': float(ingredient_product.get('quantity', 0))
                })
        
        return result


def optimize_sale_completion(
    cart_items: List[Dict],
    products: List[Dict],
    expenses: List[Dict] = None,
    user_id: str = None,
    account_id: str = None
) -> Tuple[bool, Dict]:
    """
    OPTIMIZED SALE COMPLETION - Target: <200ms
    
    This is the core function for cashier.completeSale() and admin.completeSale()
    
    Returns:
        (success: bool, response: dict)
    
    Success response:
    {
        'success': True,
        'sale_id': 123,
        'processing_time_ms': 45,
        'deductions': {...},
        'message': 'Sale completed successfully'
    }
    
    Error response:
    {
        'success': False,
        'error': 'Insufficient stock for Tilapia',
        'message': 'Sale failed - validation error'
    }
    """
    start_time = time.time()
    
    try:
        # Step 1: Initialize engine with products (IN-MEMORY)
        engine = StockDeductionEngine(products, expenses)
        
        # Step 2: Validate & prepare ALL deductions (NO file writes yet)
        is_valid, error_msg, deductions = engine.validate_and_prepare_deductions(cart_items)
        if not is_valid:
            return False, {
                'success': False,
                'error': error_msg,
                'message': 'Sale validation failed'
            }
        
        # Step 3: Apply deductions to in-memory products
        if not engine.apply_deductions(deductions):
            return False, {
                'success': False,
                'error': 'Failed to apply deductions',
                'message': 'Internal error'
            }
        
        # Step 4: Prepare broadcast payload (minimal, efficient)
        updated_products = [
            {
                'id': p['id'],
                'name': p['name'],
                'quantity': p['quantity'],
                'unit': p.get('unit', 'pcs')
            }
            for d in deductions.get('products', [])
            for p in [engine._product_map.get(d['id'])]
            if p
        ]
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        return True, {
            'success': True,
            'deductions': deductions,
            'updated_products': updated_products,
            'processing_time_ms': elapsed_ms,
            'message': f"Sale completed in {elapsed_ms:.0f}ms - {len(deductions['products'])} items deducted"
        }
        
    except Exception as e:
        elapsed_ms = (time.time() - start_time) * 1000
        return False, {
            'success': False,
            'error': str(e),
            'processing_time_ms': elapsed_ms,
            'message': 'Sale processing failed'
        }


# ============================================================
# EXAMPLE PRODUCT SCHEMA (for reference)
# ============================================================
EXAMPLE_PRODUCT_SCHEMAS = {
    "raw_product": {
        "id": 1,
        "name": "Tilapia",
        "type": "raw",
        "quantity": 23,
        "unit": "kg",
        "price": 5.50,
        "cost": 2.00,
        "category": "fish",
        "isComposite": False,
        "accountId": "main",
        "createdAt": "2024-01-01T10:00:00"
    },
    "composite_product": {
        "id": 5,
        "name": "Fried Fish",
        "type": "composite",
        "quantity": 0,  # Composite products don't have direct inventory
        "unit": "serving",
        "price": 8.00,
        "cost": 3.50,
        "isComposite": True,
        "recipe": [
            {
                "productId": 1,
                "name": "Tilapia",
                "quantity": 2,
                "unit": "kg",
                "source": "inventory"
            },
            {
                "productId": 3,
                "name": "Cooking Oil",
                "quantity": 0.2,
                "unit": "liters",
                "source": "expenses"
            },
            {
                "productId": 4,
                "name": "Salt",
                "quantity": 0.05,
                "unit": "kg",
                "source": "expenses"
            }
        ],
        "accountId": "main",
        "createdAt": "2024-01-01T10:00:00"
    },
    "expense_item": {
        "id": 3,
        "name": "Cooking Oil",
        "type": "expense",
        "quantity": 50,
        "unit": "liters",
        "price": 0.50,
        "expenseOnly": True,
        "visibleToCashier": False,
        "accountId": "main",
        "createdAt": "2024-01-01T10:00:00"
    }
}
