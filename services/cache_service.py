import json
import importlib
import os
import time
from typing import Any, Optional

try:
    redis = importlib.import_module("redis")
except Exception:
    redis = None


class CacheService:
    def __init__(self):
        self.enabled: bool = False
        self.client: Any = None  # Redis client when connected, None otherwise
        redis_url = os.environ.get("REDIS_URL")
        if redis and redis_url:
            try:
                self.client = redis.Redis.from_url(redis_url, decode_responses=True)
                self.client.ping()
                self.enabled = True
            except Exception:
                self.client = None
                self.enabled = False

    def get_json(self, key: str) -> Optional[Any]:
        if not self.enabled:
            return None
        try:
            value = self.client.get(key)
            return json.loads(value) if value else None
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 30) -> bool:
        if not self.enabled:
            return False
        try:
            payload = json.dumps(value)
            self.client.setex(key, ttl_seconds, payload)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> None:
        if not self.enabled:
            return
        try:
            self.client.delete(key)
        except Exception:
            pass

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        if not self.enabled:
            return 0
        try:
            pipe = self.client.pipeline()
            pipe.incr(key)
            pipe.expire(key, ttl_seconds)
            value, _ = pipe.execute()
            return int(value)
        except Exception:
            return 0

    def get_int(self, key: str) -> Optional[int]:
        if not self.enabled:
            return None
        try:
            value = self.client.get(key)
            return int(value) if value is not None else None
        except Exception:
            return None

    def set_int(self, key: str, value: int, ttl_seconds: int = 60) -> None:
        if not self.enabled:
            return
        try:
            self.client.setex(key, ttl_seconds, int(value))
        except Exception:
            pass

    def now_ts(self) -> int:
        return int(time.time())
