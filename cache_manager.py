"""
Caching Strategy Implementation
Redis for sessions, API caching, image optimization
"""

import redis
import json
import hashlib
from datetime import timedelta

class CacheManager:
    def __init__(self, redis_url=None):
        try:
            self.redis_client = redis.from_url(redis_url or 'redis://localhost:6379')
            self.redis_available = True
        except:
            self.redis_client = None
            self.redis_available = False
            self.memory_cache = {}
    
    def get(self, key):
        if self.redis_available:
            try:
                value = self.redis_client.get(key)
                return json.loads(value) if value else None
            except:
                return None
        return self.memory_cache.get(key)
    
    def set(self, key, value, ttl=300):
        if self.redis_available:
            try:
                self.redis_client.setex(key, ttl, json.dumps(value))
            except:
                pass
        else:
            self.memory_cache[key] = value
    
    def delete(self, key):
        if self.redis_available:
            try:
                self.redis_client.delete(key)
            except:
                pass
        else:
            self.memory_cache.pop(key, None)

# Session storage
class SessionCache:
    def __init__(self, cache_manager):
        self.cache = cache_manager
    
    def store_session(self, user_id, session_data):
        key = f"session:{user_id}"
        self.cache.set(key, session_data, ttl=3600)  # 1 hour
    
    def get_session(self, user_id):
        key = f"session:{user_id}"
        return self.cache.get(key)

# API response caching
def cache_api_response(cache_manager, ttl=60):
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Create cache key from function name and args
            cache_key = f"api:{func.__name__}:{hashlib.md5(str(args).encode()).hexdigest()}"
            
            # Try to get from cache
            cached = cache_manager.get(cache_key)
            if cached:
                return cached
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache_manager.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator

# Image optimization
class ImageCache:
    def __init__(self, cache_manager):
        self.cache = cache_manager
    
    def optimize_image(self, image_data):
        # Simple base64 image compression
        if len(image_data) > 100000:  # 100KB
            # In production, use proper image compression
            return image_data[:100000] + "..."
        return image_data
    
    def cache_image(self, image_id, image_data):
        optimized = self.optimize_image(image_data)
        self.cache.set(f"img:{image_id}", optimized, ttl=86400)  # 24 hours