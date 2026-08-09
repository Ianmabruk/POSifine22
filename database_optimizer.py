"""
Database Optimization Module
Adds indexes and query monitoring for performance
"""

import time
import logging
from functools import wraps

class DatabaseOptimizer:
    def __init__(self, datastore):
        self.datastore = datastore
        self.query_stats = {}
        
    def add_indexes(self):
        """Add indexes for frequently queried fields"""
        if not self.datastore.use_postgres:
            return
            
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_products_account_id ON products(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_sales_account_id ON sales(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_sales_created_at ON sales(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_account_id ON users(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_refresh_token_hash ON sessions(refresh_token_hash)",
            "CREATE INDEX IF NOT EXISTS idx_expenses_account_id ON expenses(account_id)",
            "CREATE INDEX IF NOT EXISTS idx_batches_product_id ON batches(productId)",
        ]
        
        for index_sql in indexes:
            try:
                self.datastore.execute_sql(index_sql)
            except Exception as e:
                logging.warning(f"Index creation failed: {e}")
    
    def monitor_query(self, table_name):
        """Decorator to monitor query performance"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                start_time = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                
                if table_name not in self.query_stats:
                    self.query_stats[table_name] = []
                self.query_stats[table_name].append(duration)
                
                if duration > 0.1:  # Log slow queries
                    logging.warning(f"Slow query on {table_name}: {duration:.3f}s")
                
                return result
            return wrapper
        return decorator
    
    def get_query_stats(self):
        """Get query performance statistics"""
        stats = {}
        for table, times in self.query_stats.items():
            stats[table] = {
                'avg_time': sum(times) / len(times),
                'max_time': max(times),
                'query_count': len(times)
            }
        return stats