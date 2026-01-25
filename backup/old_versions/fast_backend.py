"""
ULTRA-FAST BACKEND OPTIMIZATION MODULE
========================================

Targets:
- Sale completion: <20ms
- Stock deduction: <5ms  
- Record creation: <10ms

Key optimizations:
1. In-memory caching with smart invalidation
2. Batch file I/O operations
3. Minimal JSON serialization
4. Lazy loading of non-critical data
5. Parallel processing for independent operations
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from functools import lru_cache
from decimal import Decimal, ROUND_HALF_UP


# ============================================================
# GLOBAL CACHE SYSTEM
# ============================================================

class FileCache:
    """Ultra-fast in-memory file cache with TTL"""
    
    def __init__(self, ttl_seconds=5):
        self.cache = {}
        self.timestamps = {}
        self.ttl = ttl_seconds
        self.lock = threading.RLock()
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        with self.lock:
            if key not in self.cache:
                self.misses += 1
                return None
            
            # Check TTL
            if time.time() - self.timestamps[key] > self.ttl:
                del self.cache[key]
                del self.timestamps[key]
                self.misses += 1
                return None
            
            self.hits += 1
            return self.cache[key]
    
    def set(self, key: str, value: Any):
        """Set cache value with timestamp"""
        with self.lock:
            self.cache[key] = value
            self.timestamps[key] = time.time()
    
    def invalidate(self, key: str):
        """Invalidate specific cache entry"""
        with self.lock:
            self.cache.pop(key, None)
            self.timestamps.pop(key, None)
    
    def clear(self):
        """Clear entire cache"""
        with self.lock:
            self.cache.clear()
            self.timestamps.clear()
    
    def stats(self):
        """Get cache statistics"""
        with self.lock:
            total = self.hits + self.misses
            hit_rate = (self.hits / total * 100) if total > 0 else 0
            return {
                'hits': self.hits,
                'misses': self.misses,
                'hitRate': f"{hit_rate:.1f}%",
                'entries': len(self.cache)
            }


# Global cache instance - reduced TTL to 2 seconds for faster invalidation
file_cache = FileCache(ttl_seconds=2)


# ============================================================
# ULTRA-FAST FILE OPERATIONS
# ============================================================

def load_data_cached(filename: str, use_cache=True) -> List[Dict]:
    """Load JSON with cache - typically <1ms with cache hit"""
    if use_cache:
        cached = file_cache.get(filename)
        if cached is not None:
            return cached
    
    try:
        start = time.time()
        with open(filename, 'r') as f:
            data = json.load(f)
        elapsed_ms = (time.time() - start) * 1000
        
        # Cache for next 3 seconds
        if use_cache:
            file_cache.set(filename, data)
        
        if elapsed_ms > 5:
            print(f"⚠️ File load took {elapsed_ms:.1f}ms: {filename}")
        
        return data
    except FileNotFoundError:
        return []
    except Exception as e:
        print(f"❌ Error loading {filename}: {e}")
        return []


def save_data_fast(filename: str, data: List[Dict], invalidate_cache=True):
    """Save JSON with minimal overhead - typically <2ms"""
    try:
        start = time.time()
        
        # Use compact separators to reduce JSON size and speed up serialization
        json_str = json.dumps(data, separators=(',', ':'), default=str)
        
        # Write to file with minimal buffering
        with open(filename, 'w', buffering=1024) as f:
            f.write(json_str)
        
        elapsed_ms = (time.time() - start) * 1000
        
        # Invalidate cache after write
        if invalidate_cache:
            file_cache.invalidate(filename)
        
        if elapsed_ms > 5:
            print(f"⚠️ File save took {elapsed_ms:.1f}ms: {filename}")
        
        return True
    except Exception as e:
        print(f"❌ Error saving {filename}: {e}")
        return False


# ============================================================
# ULTRA-FAST STOCK DEDUCTION (Optimized from stock_engine.py)
# ============================================================

def safe_round(value: float, decimal_places: int = 4) -> float:
    """Safely round with Decimal to prevent floating-point errors"""
    try:
        if value is None or (isinstance(value, float) and value != value):
            return 0.0
        d = Decimal(str(value))
        rounded = d.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_HALF_UP)
        return float(rounded)
    except (ValueError, TypeError):
        return float(value) if value else 0.0


class UltraFastStockEngine:
    """Lightning-fast stock deduction - optimized for <2ms execution"""
    
    def __init__(self, products: List[Dict], expenses: List[Dict] = None):
        self.products = products
        self.expenses = expenses or []
        
        # Build ULTRA-FAST lookup maps (O(1) access instead of O(n) search)
        # Pre-compute to save time in validate_and_deduct_fast
        self._product_map = {p['id']: p for p in products}
        self._expense_map = {e['id']: e for e in self.expenses}
    
    def validate_and_deduct_fast(self, items: List[Dict]) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Ultra-fast validation and deduction in a single pass.
        Targets: <2ms execution time for typical operations
        """
        deductions = {'products': [], 'expenses': []}
        
        try:
            # Single pass through items - no sorting, no filtering
            for item in items:
                product_id = item.get('productId')
                qty = safe_round(float(item.get('quantity', 0)))
                
                # Fast O(1) lookup
                product = self._product_map.get(product_id)
                if not product:
                    return False, f"Product {product_id} not found", None
                
                # Check if composite (fast boolean check)
                is_composite = product.get('isComposite', False) or bool(product.get('recipe'))
                
                if not is_composite:
                    # Fast quantity check without function call
                    current_qty = float(product.get('quantity', 0))
                    if current_qty < qty:
                        return False, f"Insufficient stock for {product['name']}", None
                    
                    # Record deduction immediately (in-place mutation is fastest)
                    new_qty = safe_round(current_qty - qty)
                    product['quantity'] = new_qty
                    
                    # Get cost price for COGS calculation
                    cost_price = float(product.get('cost', 0))
                    total_cost = cost_price * qty
                    
                    deductions['products'].append({
                        'id': product_id,
                        'name': product['name'],
                        'before': current_qty,
                        'after': new_qty,
                        'deducted': qty,
                        'quantity': qty,
                        'unit': product.get('unit', 'pcs'),
                        'cost': cost_price,
                        'total_cost': total_cost
                    })
                
                # Handle recipe (if any) - fast path
                recipe = product.get('recipe', [])
                if recipe:  # Only iterate if recipe exists
                    for ingredient in recipe:
                        ing_id = ingredient.get('productId', ingredient.get('id'))
                        ing_qty = safe_round(float(ingredient.get('quantity', 0)) * qty)
                        
                        # Fast O(1) lookup
                        ing_product = self._product_map.get(ing_id)
                        if ing_product:
                            ing_current = float(ing_product.get('quantity', 0))
                            if ing_current >= ing_qty:
                                ing_product['quantity'] = safe_round(ing_current - ing_qty)
                                
                                # Get cost price for ingredient
                                ing_cost_price = float(ing_product.get('cost', 0))
                                ing_total_cost = ing_cost_price * ing_qty
                                
                                deductions['products'].append({
                                    'id': ing_id,
                                    'name': ing_product['name'],
                                    'before': ing_current,
                                    'after': ing_product['quantity'],
                                    'deducted': ing_qty,
                                    'quantity': ing_qty,
                                    'unit': ing_product.get('unit', 'pcs'),
                                    'cost': ing_cost_price,
                                    'total_cost': ing_total_cost
                                })
            
            return True, None, deductions
        
        except Exception as e:
            return False, str(e), None


# ============================================================
# ULTRA-FAST RESPONSE BUILDERS (Minimal serialization)
# ============================================================

def build_minimal_response(sale_id: int, deductions: Dict, elapsed_ms: float, products: List[Dict], account_id: str) -> Dict:
    """Build response in <1ms by avoiding unnecessary data copies"""
    
    # Only include essential product data for UI update
    updated_products = [
        {
            'id': p['id'],
            'name': p['name'],
            'quantity': p.get('quantity', 0),
            'unit': p.get('unit', 'pcs'),
            'price': p.get('price', 0)
        }
        for p in products 
        if p.get('accountId') == account_id
    ]
    
    return {
        'success': True,
        'saleId': sale_id,
        'deductions': deductions,
        'processingTime': f"{elapsed_ms:.1f}ms",
        'updatedProducts': updated_products,
        'status': '✅ FAST' if elapsed_ms < 20 else '⚠️ SLOW'
    }


# ============================================================
# ASYNC HELPERS FOR NON-BLOCKING OPERATIONS
# ============================================================

def async_save(filename: str, data: List[Dict]):
    """Save file in background thread (non-blocking)"""
    def save_thread():
        save_data_fast(filename, data)
    
    thread = threading.Thread(target=save_thread, daemon=True)
    thread.start()


def batch_broadcast_async(updates: List[Dict], broadcast_func):
    """Broadcast updates in background (non-blocking)"""
    def broadcast_thread():
        for update in updates:
            broadcast_func(update['type'], update['data'], update.get('account_id'))
    
    thread = threading.Thread(target=broadcast_thread, daemon=True)
    thread.start()


# ============================================================
# PERFORMANCE METRICS
# ============================================================

class PerformanceMonitor:
    """Track performance metrics across operations"""
    
    def __init__(self):
        self.metrics = {
            'sales_created': 0,
            'avg_sale_time_ms': 0,
            'stock_deductions': 0,
            'cache_hits': 0,
            'cache_misses': 0
        }
        self.lock = threading.Lock()
    
    def record_sale(self, elapsed_ms: float):
        with self.lock:
            self.metrics['sales_created'] += 1
            # Running average
            old_avg = self.metrics['avg_sale_time_ms']
            count = self.metrics['sales_created']
            self.metrics['avg_sale_time_ms'] = (old_avg * (count - 1) + elapsed_ms) / count
    
    def get_metrics(self) -> Dict:
        with self.lock:
            return dict(self.metrics)


performance = PerformanceMonitor()
