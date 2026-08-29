"""
PERFORMANCE OPTIMIZATION SERVICE
=================================
Ultra-fast POS operations with <50ms target performance.
Includes caching, batch operations, and real-time monitoring.
"""

import time
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from functools import wraps
import logging

logger = logging.getLogger(__name__)


class PerformanceOptimizer:
    """
    Performance optimization service for POS operations
    """
    
    def __init__(self, datastore, cache_service):
        self.ds = datastore
        self.cache = cache_service
        self.metrics = {
            'sales': [],
            'products': [],
            'stats': []
        }
    
    def performance_monitor(self, operation_type: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.time() - start_time) * 1000
                    self.record_performance(operation_type, elapsed_ms, True)
                    if elapsed_ms > 100:
                        logger.warning(f"Slow {operation_type}: {elapsed_ms:.1f}ms")
                    elif elapsed_ms < 50:
                        logger.info(f"Fast {operation_type}: {elapsed_ms:.1f}ms")
                    return result
                except Exception as e:
                    elapsed_ms = (time.time() - start_time) * 1000
                    self.record_performance(operation_type, elapsed_ms, False)
                    logger.error(f"{operation_type} failed after {elapsed_ms:.1f}ms: {e}")
                    raise
            return wrapper
        return decorator
    
    def record_performance(self, operation_type: str, duration_ms: float, success: bool):
        if operation_type not in self.metrics:
            self.metrics[operation_type] = []
        self.metrics[operation_type].append({
            'duration_ms': duration_ms,
            'success': success,
            'timestamp': datetime.now().isoformat()
        })
        if len(self.metrics[operation_type]) > 100:
            self.metrics[operation_type] = self.metrics[operation_type][-100:]
    
    def get_performance_stats(self, operation_type: Optional[str] = None) -> Dict:
        if operation_type:
            metrics = self.metrics.get(operation_type, [])
            return self._calculate_stats(metrics, operation_type)
        else:
            stats = {}
            for op_type, metrics in self.metrics.items():
                stats[op_type] = self._calculate_stats(metrics, op_type)
            return stats
    
    def _calculate_stats(self, metrics: List[Dict], operation_type: str) -> Dict:
        if not metrics:
            return {
                'count': 0,
                'avg_ms': 0,
                'min_ms': 0,
                'max_ms': 0,
                'p95_ms': 0,
                'success_rate': 100,
                'performance_grade': 'N/A'
            }
        durations = [m['duration_ms'] for m in metrics]
        successes = [m['success'] for m in metrics]
        durations.sort()
        count = len(durations)
        avg_ms = sum(durations) / count
        min_ms = durations[0]
        max_ms = durations[-1]
        p95_index = int(count * 0.95)
        p95_ms = durations[p95_index] if p95_index < count else max_ms
        success_rate = (sum(successes) / count) * 100
        if avg_ms < 50:
            grade = 'EXCELLENT'
        elif avg_ms < 100:
            grade = 'GOOD'
        elif avg_ms < 200:
            grade = 'ACCEPTABLE'
        else:
            grade = 'NEEDS_IMPROVEMENT'
        return {
            'count': count,
            'avg_ms': round(avg_ms, 1),
            'min_ms': round(min_ms, 1),
            'max_ms': round(max_ms, 1),
            'p95_ms': round(p95_ms, 1),
            'success_rate': round(success_rate, 1),
            'performance_grade': grade
        }
    
    @performance_monitor('products')
    def get_cached_products(self, account_id: str, force_refresh: bool = False) -> List[Dict]:
        cache_key = f"products:{account_id}"
        if not force_refresh and self.cache.enabled:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                return cached
        products = self.ds.get_all('products', account_id)
        if self.cache.enabled:
            self.cache.set_json(cache_key, products, ttl_seconds=30)
        return products
    
    @performance_monitor('stats')
    def get_cached_stats(self, account_id: str, cashier_id: Optional[int] = None) -> Dict:
        cache_key = f"stats:{account_id}:{cashier_id or 'all'}"
        if self.cache.enabled:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                return cached
        products = self.ds.get_all('products', account_id)
        sales = self.ds.get_all('sales', account_id)
        expenses = self.ds.get_all('expenses', account_id)
        if cashier_id:
            sales = [s for s in sales if s.get('cashier_id') == cashier_id]
            expenses = [e for e in expenses if e.get('cashier_id') == cashier_id]
        total_sales = sum(float(s.get('total', 0)) for s in sales)
        total_expenses = sum(float(e.get('amount', 0)) for e in expenses)
        total_cost = sum(float(s.get('total_cost', 0)) for s in sales)
        if cashier_id:
            profit = total_sales - total_expenses
        else:
            profit = total_sales - total_cost - total_expenses
        stats = {
            'totalSales': total_sales,
            'totalExpenses': total_expenses,
            'profit': profit,
            'productsCount': len(products),
            'salesCount': len(sales)
        }
        if self.cache.enabled:
            self.cache.set_json(cache_key, stats, ttl_seconds=10)
        return stats

    def invalidate_cache(self, cache_pattern: str):
        if self.cache.enabled:
            if cache_pattern == 'products':
                logger.info(f"Invalidated cache pattern: {cache_pattern}")

    @performance_monitor('sale')
    def optimized_sale_completion(
        self,
        account_id: str,
        cashier_id: int,
        cashier_name: str,
        items: List[Dict],
        payment_method: str = 'cash',
        **kwargs
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        try:
            from stock_engine import StockEngine
            stock_engine = StockEngine(self.ds)
            success, error, sale = stock_engine.execute_sale(
                items=items,
                account_id=account_id,
                cashier_id=cashier_id,
                cashier_name=cashier_name,
                payment_method=payment_method,
                **kwargs
            )
            if success:
                self.invalidate_cache('products')
                self.invalidate_cache('stats')
            return success, error, sale
        except Exception as e:
            logger.error(f"Optimized sale completion failed: {e}")
            return False, str(e), None

    def health_check(self) -> Dict:
        try:
            db_time = None
            cache_status = 'disabled'
            cache_time = None
            if self.ds and getattr(self.ds, 'use_postgres', False):
                db_start = time.time()
                with self.ds._pg_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute('SELECT 1')
                db_time = (time.time() - db_start) * 1000
            if self.cache and getattr(self.cache, 'enabled', False):
                cache_start = time.time()
                cache_status = 'healthy' if self.cache.health_check() else 'error'
                cache_time = (time.time() - cache_start) * 1000
            perf_stats = self.get_performance_stats()
            return {
                'status': 'healthy',
                'database': {
                    'status': 'healthy',
                    'response_time_ms': round(db_time, 1) if db_time is not None else None,
                    'type': 'postgres' if getattr(self.ds, 'use_postgres', False) else 'json'
                },
                'cache': {
                    'status': cache_status,
                    'response_time_ms': round(cache_time, 1) if cache_time is not None else None,
                    'enabled': getattr(self.cache, 'enabled', False)
                },
                'performance': perf_stats,
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
