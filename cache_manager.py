"""
Cache Manager Module
====================
Centralized caching utilities for the POS backend.
"""

import json
import logging
from typing import Any, Optional
from functools import wraps
import hashlib

logger = logging.getLogger(__name__)

# Cache instance (will be initialized by app.py)
_redis_client = None


def init_cache(redis_client):
    """Initialize cache with Redis client"""
    global _redis_client
    _redis_client = redis_client
    if redis_client:
        logger.info("✅ Cache manager initialized with Redis")
    else:
        logger.warning("⚠️ Cache manager running without Redis")


def get(key: str, default=None) -> Any:
    """
    Get value from cache
    
    Args:
        key: Cache key
        default: Default value if not found
    
    Returns:
        Cached value or default
    """
    if not _redis_client:
        return default
    
    try:
        value = _redis_client.get(key)
        if value:
            return json.loads(value)
        return default
    except Exception as e:
        logger.warning(f"Cache get error for {key}: {e}")
        return default


def set(key: str, value: Any, ttl: int = 300) -> bool:
    """
    Set value in cache with TTL
    
    Args:
        key: Cache key
        value: Value to cache (will be JSON serialized)
        ttl: Time to live in seconds (default 5 minutes)
    
    Returns:
        True if successful, False otherwise
    """
    if not _redis_client:
        return False
    
    try:
        _redis_client.setex(key, ttl, json.dumps(value, default=str))
        return True
    except Exception as e:
        logger.warning(f"Cache set error for {key}: {e}")
        return False


def delete(key: str) -> bool:
    """Delete key from cache"""
    if not _redis_client:
        return False
    
    try:
        _redis_client.delete(key)
        return True
    except Exception as e:
        logger.warning(f"Cache delete error for {key}: {e}")
        return False


def invalidate_pattern(pattern: str) -> int:
    """
    Invalidate all keys matching pattern
    
    Args:
        pattern: Redis key pattern (e.g., 'products:*')
    
    Returns:
        Number of keys deleted
    """
    if not _redis_client:
        return 0
    
    try:
        keys = _redis_client.keys(pattern)
        if keys:
            deleted = _redis_client.delete(*keys)
            logger.debug(f"Invalidated {deleted} keys matching {pattern}")
            return deleted
        return 0
    except Exception as e:
        logger.warning(f"Cache invalidation error for {pattern}: {e}")
        return 0


def cached(ttl: int = 300, key_prefix: str = ''):
    """
    Decorator to cache function results
    
    Usage:
        @cached(ttl=600, key_prefix='products')
        def get_products(account_id):
            # Expensive database query
            return products
    
    Args:
        ttl: Cache TTL in seconds
        key_prefix: Prefix for cache key
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            
            # Add positional args
            for arg in args:
                if isinstance(arg, (str, int, float, bool)):
                    key_parts.append(str(arg))
            
            # Add keyword args (sorted for consistency)
            for k, v in sorted(kwargs.items()):
                if isinstance(v, (str, int, float, bool)):
                    key_parts.append(f"{k}:{v}")
            
            cache_key = ':'.join(key_parts)
            
            # Try to get from cache
            cached_value = get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key}")
            result = func(*args, **kwargs)
            
            # Store in cache
            set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator


def cache_key(*parts) -> str:
    """
    Generate consistent cache key from parts
    
    Example:
        key = cache_key('products', account_id, 'active')
        # Returns: 'products:abc123:active'
    """
    return ':'.join(str(p) for p in parts)


class CacheStats:
    """Track cache hit/miss statistics"""
    
    def __init__(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0
    
    def hit(self):
        self.hits += 1
    
    def miss(self):
        self.misses += 1
    
    def error(self):
        self.errors += 1
    
    def get_stats(self):
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            'hits': self.hits,
            'misses': self.misses,
            'errors': self.errors,
            'total_requests': total,
            'hit_rate': round(hit_rate, 2)
        }
    
    def reset(self):
        self.hits = 0
        self.misses = 0
        self.errors = 0


# Global stats tracker
_stats = CacheStats()


def get_stats():
    """Get cache statistics"""
    return _stats.get_stats()
