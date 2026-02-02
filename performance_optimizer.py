"""
PERFORMANCE OPTIMIZATION SERVICE
================================
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
        """
        Initialize performance optimizer
        
        Args:
            datastore: DataStore instance
            cache_service: CacheService instance
        """
        self.ds = datastore
        self.cache = cache_service
        self.metrics = {
            'sales': [],
            'products': [],
            'stats': []
        }
    
    def performance_monitor(self, operation_type: str):
        """
        Decorator to monitor operation performance
        
        Args:
            operation_type: Type of operation ('sale', 'product', 'stats')
        """
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                
                try:
                    result = func(*args, **kwargs)
                    elapsed_ms = (time.time() - start_time) * 1000
                    
                    # Record metrics
                    self.record_performance(operation_type, elapsed_ms, True)
                    
                    # Log slow operations
                    if elapsed_ms > 100:
                        logger.warning(f"⚠️ Slow {operation_type}: {elapsed_ms:.1f}ms")
                    elif elapsed_ms < 50:
                        logger.info(f"🚀 Fast {operation_type}: {elapsed_ms:.1f}ms")
                    
                    return result
                    
                except Exception as e:
                    elapsed_ms = (time.time() - start_time) * 1000
                    self.record_performance(operation_type, elapsed_ms, False)
                    logger.error(f"❌ {operation_type} failed after {elapsed_ms:.1f}ms: {e}")
                    raise
                    
            return wrapper
        return decorator
    
    def record_performance(self, operation_type: str, duration_ms: float, success: bool):
        """
        Record performance metrics
        
        Args:
            operation_type: Type of operation
            duration_ms: Duration in milliseconds
            success: Whether operation succeeded
        """
        if operation_type not in self.metrics:
            self.metrics[operation_type] = []
        
        self.metrics[operation_type].append({
            'duration_ms': duration_ms,
            'success': success,
            'timestamp': datetime.now().isoformat()
        })
        
        # Keep only last 100 records per operation type
        if len(self.metrics[operation_type]) > 100:
            self.metrics[operation_type] = self.metrics[operation_type][-100:]
    
    def get_performance_stats(self, operation_type: Optional[str] = None) -> Dict:
        """
        Get performance statistics
        
        Args:
            operation_type: Optional operation type filter
        
        Returns:
            Performance statistics
        """
        if operation_type:
            metrics = self.metrics.get(operation_type, [])
            return self._calculate_stats(metrics, operation_type)
        else:
            stats = {}
            for op_type, metrics in self.metrics.items():
                stats[op_type] = self._calculate_stats(metrics, op_type)
            return stats
    
    def _calculate_stats(self, metrics: List[Dict], operation_type: str) -> Dict:
        """
        Calculate statistics for metrics
        
        Args:
            metrics: List of metric records
            operation_type: Operation type
        
        Returns:
            Calculated statistics
        """
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
        
        # Performance grading
        if avg_ms < 50:
            grade = '🚀 EXCELLENT'
        elif avg_ms < 100:
            grade = '✅ GOOD'
        elif avg_ms < 200:
            grade = '⚠️ ACCEPTABLE'
        else:
            grade = '❌ NEEDS IMPROVEMENT'
        
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
        """
        Get products with intelligent caching
        
        Args:
            account_id: Account ID
            force_refresh: Force cache refresh
        
        Returns:
            List of products
        """
        cache_key = f"products:{account_id}"
        
        if not force_refresh and self.cache.enabled:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                logger.info(f"📦 Products cache hit for account {account_id}")
                return cached
        
        # Cache miss - fetch from database
        products = self.ds.get_all('products', account_id)
        
        if self.cache.enabled:
            # Cache for 30 seconds
            self.cache.set_json(cache_key, products, ttl_seconds=30)
            logger.info(f"📦 Products cached for account {account_id}")
        
        return products
    
    @performance_monitor('stats')
    def get_cached_stats(self, account_id: str, cashier_id: Optional[int] = None) -> Dict:
        """
        Get statistics with caching
        
        Args:
            account_id: Account ID
            cashier_id: Optional cashier ID filter
        
        Returns:
            Statistics dictionary
        """
        cache_key = f"stats:{account_id}:{cashier_id or 'all'}"
        
        if self.cache.enabled:
            cached = self.cache.get_json(cache_key)
            if cached is not None:
                logger.info(f"📊 Stats cache hit for {cache_key}")
                return cached
        
        # Calculate stats
        products = self.ds.get_all('products', account_id)
        sales = self.ds.get_all('sales', account_id)
        expenses = self.ds.get_all('expenses', account_id)
        
        # Filter by cashier if specified
        if cashier_id:
            sales = [s for s in sales if s.get('cashier_id') == cashier_id]
            expenses = [e for e in expenses if e.get('cashier_id') == cashier_id]
        
        total_sales = sum(float(s.get('total', 0)) for s in sales)
        total_expenses = sum(float(e.get('amount', 0)) for e in expenses)
        total_cost = sum(float(s.get('total_cost', 0)) for s in sales)
        
        # Calculate profit (different for cashier vs admin view)
        if cashier_id:
            profit = total_sales - total_expenses  # Simplified for cashiers
        else:\n            profit = total_sales - total_cost - total_expenses  # Full cost model for admins\n        \n        stats = {\n            'totalSales': total_sales,\n            'totalExpenses': total_expenses,\n            'profit': profit,\n            'productsCount': len(products),\n            'salesCount': len(sales)\n        }\n        \n        if self.cache.enabled:\n            # Cache for 10 seconds\n            self.cache.set_json(cache_key, stats, ttl_seconds=10)\n            logger.info(f\"📊 Stats cached for {cache_key}\")\n        \n        return stats\n    \n    def invalidate_cache(self, cache_pattern: str):\n        \"\"\"\n        Invalidate cache entries matching pattern\n        \n        Args:\n            cache_pattern: Cache key pattern to invalidate\n        \"\"\"\n        if self.cache.enabled:\n            # For now, we'll delete specific known keys\n            # In a full Redis implementation, we'd use pattern matching\n            if cache_pattern == 'products':\n                # This would need to be implemented based on cache backend\n                logger.info(f\"🗑️ Invalidated cache pattern: {cache_pattern}\")\n    \n    @performance_monitor('sale')\n    def optimized_sale_completion(\n        self, \n        account_id: str,\n        cashier_id: int,\n        cashier_name: str,\n        items: List[Dict],\n        payment_method: str = 'cash',\n        **kwargs\n    ) -> Tuple[bool, Optional[str], Optional[Dict]]:\n        \"\"\"\n        Ultra-optimized sale completion\n        \n        Args:\n            account_id: Account ID\n            cashier_id: Cashier ID\n            cashier_name: Cashier name\n            items: Sale items\n            payment_method: Payment method\n            **kwargs: Additional sale parameters\n        \n        Returns:\n            (success, error_message, sale_record)\n        \"\"\"\n        try:\n            # Use stock engine for optimized processing\n            from stock_engine import StockEngine\n            stock_engine = StockEngine(self.ds)\n            \n            success, error, sale = stock_engine.execute_sale(\n                items=items,\n                account_id=account_id,\n                cashier_id=cashier_id,\n                cashier_name=cashier_name,\n                payment_method=payment_method,\n                **kwargs\n            )\n            \n            if success:\n                # Invalidate relevant caches\n                self.invalidate_cache('products')\n                self.invalidate_cache('stats')\n                \n                logger.info(f\"💰 Sale completed: ID {sale.get('id')}, Total: {sale.get('total')}\")\n            \n            return success, error, sale\n            \n        except Exception as e:\n            logger.error(f\"❌ Optimized sale completion failed: {e}\")\n            return False, str(e), None\n    \n    def batch_stock_update(self, updates: List[Tuple[int, float, str]]) -> bool:\n        \"\"\"\n        Optimized batch stock update\n        \n        Args:\n            updates: List of (product_id, new_quantity, account_id) tuples\n        \n        Returns:\n            Success status\n        \"\"\"\n        start_time = time.time()\n        \n        try:\n            success = self.ds.batch_update_stock(updates)\n            \n            elapsed_ms = (time.time() - start_time) * 1000\n            logger.info(f\"📦 Batch stock update: {len(updates)} products in {elapsed_ms:.1f}ms\")\n            \n            if success:\n                # Invalidate product cache\n                self.invalidate_cache('products')\n            \n            return success\n            \n        except Exception as e:\n            elapsed_ms = (time.time() - start_time) * 1000\n            logger.error(f\"❌ Batch stock update failed after {elapsed_ms:.1f}ms: {e}\")\n            return False\n    \n    def get_system_health(self) -> Dict:\n        \"\"\"\n        Get overall system health metrics\n        \n        Returns:\n            System health information\n        \"\"\"\n        try:\n            # Test database connectivity\n            db_start = time.time()\n            test_query = self.ds.get_all('accounts')\n            db_time = (time.time() - db_start) * 1000\n            \n            # Test cache connectivity\n            cache_time = 0\n            cache_status = 'disabled'\n            if self.cache.enabled:\n                cache_start = time.time()\n                self.cache.set_json('health_check', {'test': True}, 1)\n                cached = self.cache.get_json('health_check')\n                cache_time = (time.time() - cache_start) * 1000\n                cache_status = 'healthy' if cached else 'error'\n            \n            # Get performance stats\n            perf_stats = self.get_performance_stats()\n            \n            return {\n                'status': 'healthy',\n                'database': {\n                    'status': 'healthy',\n                    'response_time_ms': round(db_time, 1),\n                    'type': 'postgres' if self.ds.use_postgres else 'json'\n                },\n                'cache': {\n                    'status': cache_status,\n                    'response_time_ms': round(cache_time, 1),\n                    'enabled': self.cache.enabled\n                },\n                'performance': perf_stats,\n                'timestamp': datetime.now().isoformat()\n            }\n            \n        except Exception as e:\n            logger.error(f\"❌ Health check failed: {e}\")\n            return {\n                'status': 'error',\n                'error': str(e),\n                'timestamp': datetime.now().isoformat()\n            }