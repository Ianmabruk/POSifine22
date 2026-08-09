"""
Cache Service
==============
Redis-backed cache, distributed rate limiting and shared-state primitives for
the multi-server POS architecture.

Three server instances share a single Redis instance (configured once via the
REDIS_URL environment variable that every server reads):

    - AUTH-1  (authentication / token rotation / main-admin)
    - API-1   (POS business logic)
    - API-2   (POS business logic)

Because every process reads the *same* REDIS_URL, they all connect to the
*same* Redis instance and therefore share:

    * rate-limit counters (login attempts, signups, refresh, logout, ...)
    * revoked JWT token identifiers (so a logout/revoke on AUTH-1
      invalidates the token for API-1 / API-2 immediately)
    * authenticated-user lookup cache (so a user lookup performed on one
      server is visible to the others)
    * session / refresh-token store (see services/session_store.py)
    * product cache
    * dashboard stats cache

When Redis is unreachable or REDIS_URL is unset, every server transparently
falls back to a process-local in-memory store so the application keeps serving
requests (the rate-limit counts simply degrade to single-node accounting).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Redis dependency
# ---------------------------------------------------------------------------
try:
    redis = importlib.import_module("redis")
    _REDIS_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only when redis is missing
    redis = None
    _REDIS_AVAILABLE = False

_REDIS_SOCKET_TIMEOUT = int(os.environ.get("REDIS_SOCKET_TIMEOUT", "3"))
_REDIS_CONNECT_TIMEOUT = int(os.environ.get("REDIS_CONNECT_TIMEOUT", "3"))
_REDIS_MAX_CONNECTIONS = int(os.environ.get("REDIS_MAX_CONNECTIONS", "50"))
_DEFAULT_REVOKED_TTL = int(os.environ.get("JWT_REVOKED_TTL_SECONDS", str(8 * 86400)))


# ---------------------------------------------------------------------------
# Distributed rate limiter backed by a single atomic Lua script.
# The script:
#   * rejects immediately when the *block* key is set (lockout window)
#   * otherwise atomically increments the *counter* key
#   * when the counter crosses the threshold, arms the *block* key for the
#     configured block duration
# returns: 1 == allowed, 0 == blocked
# ---------------------------------------------------------------------------
_RATE_LIMIT_LUA = r"""
local counter_key = KEYS[1]
local block_key   = KEYS[2]
local limit       = tonumber(ARGV[1])
local window      = tonumber(ARGV[2])
local block_ttl   = tonumber(ARGV[3])
local now         = tonumber(ARGV[4])

local blocked = redis.call('GET', block_key)
if blocked then
    local b = tonumber(blocked)
    if b > now then
        return 0
    end
end

local count = redis.call('GET', counter_key)
count = count and tonumber(count) or 0
local new_count = count + 1
redis.call('SET', counter_key, new_count, 'EX', window)

if new_count > limit then
    redis.call('SET', block_key, now + block_ttl, 'EX', block_ttl)
    return 0
end
return 1
"""


class CacheService:
    """Redis-backed cache service with graceful in-memory fallback.

    Thread-safe. All public methods are safe to call from concurrent request
    handlers. When Redis is available every operation is served from the
    shared Redis instance; otherwise the process-local in-memory store is
    used (counters use a sliding window with a lock).
    """

    # Namespace constants used across the codebase.
    NS_RATE = "rl"
    NS_REVOKED = "auth:revoked"
    NS_USER_CACHE = "auth:user"
    NS_SESSION = "session"
    NS_PRODUCTS = "cache:products"
    NS_STATS = "cache:stats"
    NS_MONITOR = "cache:monitor_stats"

    def __init__(self, redis_url: Optional[str] = None) -> None:
        self._redis_url: Optional[str] = redis_url or os.environ.get("REDIS_URL")
        self.enabled: bool = False
        self.client: Any = None  # Redis client when connected, None otherwise
        self._connect_lock = threading.Lock()
        self._memory: Dict[str, Tuple[Any, float]] = {}
        # Process-local fallback counters: key -> list[ts]
        self._counters: Dict[str, List[float]] = {}
        self._mem_lock = threading.Lock()

        self._last_health: Dict[str, Any] = {"enabled": False, "status": "not_checked"}
        self._connect()

    # ------------------------------------------------------------------
    # Connection handling
    # ------------------------------------------------------------------
    def _connect(self) -> bool:
        if not _REDIS_AVAILABLE:
            return False
        if not self._redis_url:
            return False
        with self._connect_lock:
            if self.enabled and self.client is not None:
                return True
            try:
                self.client = redis.Redis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=_REDIS_CONNECT_TIMEOUT,
                    socket_timeout=_REDIS_SOCKET_TIMEOUT,
                    max_connections=_REDIS_MAX_CONNECTIONS,
                )
                self.client.ping()
                self.enabled = True
                logger.info("Redis cache service connected to %s", self._redis_url)
                return True
            except Exception as exc:
                self.client = None
                self.enabled = False
                logger.warning(
                    "Redis unavailable, falling back to in-memory cache: %s", exc
                )
                return False

    def ensure_connected(self) -> bool:
        """Return True when the Redis connection is live, (re)connecting if needed."""
        if self.enabled and self.client is not None:
            try:
                self.client.ping()
                return True
            except Exception:
                self.enabled = False
                self.client = None
        return self._connect()

    def disconnect(self) -> None:
        """Drop the Redis connection (forces a reconnect on next use)."""
        with self._connect_lock:
            if self.client is not None:
                try:
                    self.client.close()
                except Exception:
                    pass
            self.client = None
            self.enabled = False

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------
    def health_check(self) -> Dict[str, Any]:
        """Probe Redis and return a structured status payload."""
        if not self._redis_url:
            self._last_health = {
                "enabled": False,
                "status": "disabled",
                "configured": False,
            }
            return self._last_health

        if not self.enabled or self.client is None:
            if not self._connect():
                self._last_health = {
                    "enabled": False,
                    "status": "disconnected",
                    "configured": True,
                    "url": self._redis_url,
                }
                return self._last_health

        try:
            start = time.time()
            self.client.ping()
            latency_ms = round((time.time() - start) * 1000, 2)
            info = {
                "enabled": True,
                "status": "connected",
                "configured": True,
                "latency_ms": latency_ms,
                "url": self._redis_url,
            }
            self._last_health = info
            return info
        except Exception as exc:
            self.enabled = False
            self.client = None
            self._last_health = {
                "enabled": False,
                "status": "error",
                "configured": True,
                "error": str(exc),
                "url": self._redis_url,
            }
            return self._last_health

    def is_healthy(self) -> bool:
        return self.health_check().get("status") == "connected"

    @property
    def redis_url(self) -> Optional[str]:
        return self._redis_url

    @property
    def redis_available(self) -> bool:
        """Alias kept for compatibility with services that check ``cache.redis_available``."""
        return bool(self.enabled and self.client is not None)

    def now_ts(self) -> int:
        return int(time.time())

    # ------------------------------------------------------------------
    # JSON value storage
    # ------------------------------------------------------------------
    def get_json(self, key: str) -> Optional[Any]:
        if self.enabled and self.client is not None:
            try:
                value = self.client.get(key)
                return json.loads(value) if value else None
            except Exception:
                # Fall through to memory on a transient Redis error.
                pass
        with self._mem_lock:
            entry = self._memory.get(key)
            if entry and time.time() < entry[1]:
                return entry[0]
            self._memory.pop(key, None)
        return None

    def set_json(self, key: str, value: Any, ttl_seconds: int = 30) -> bool:
        if self.enabled and self.client is not None:
            try:
                payload = json.dumps(value)
                self.client.setex(key, ttl_seconds, payload)
                return True
            except Exception:
                self.enabled = False
                self.client = None
        now = time.time()
        with self._mem_lock:
            self._memory[key] = (value, now + ttl_seconds)
        return False

    def delete(self, key: str) -> None:
        if self.enabled and self.client is not None:
            try:
                self.client.delete(key)
                return
            except Exception:
                pass
        with self._mem_lock:
            self._memory.pop(key, None)

    def get_int(self, key: str) -> Optional[int]:
        if self.enabled and self.client is not None:
            try:
                value = self.client.get(key)
                return int(value) if value is not None else None
            except Exception:
                pass
        with self._mem_lock:
            entry = self._memory.get(key)
            if entry and time.time() < entry[1]:
                return int(entry[0]) if entry[0] is not None else None
            self._memory.pop(key, None)
        return None

    def set_int(self, key: str, value: int, ttl_seconds: int = 60) -> None:
        if self.enabled and self.client is not None:
            try:
                self.client.setex(key, ttl_seconds, int(value))
                return
            except Exception:
                pass
        now = time.time()
        with self._mem_lock:
            self._memory[key] = (int(value), now + ttl_seconds)

    def incr_with_ttl(self, key: str, ttl_seconds: int) -> int:
        if self.enabled and self.client is not None:
            try:
                pipe = self.client.pipeline()
                pipe.incr(key)
                pipe.expire(key, ttl_seconds)
                value, _ = pipe.execute()
                return int(value)
            except Exception:
                pass
        now = time.time()
        with self._mem_lock:
            arr = [t for t in self._counters.get(key, []) if now - t < ttl_seconds]
            arr.append(now)
            self._counters[key] = arr
            return len(arr)

    # ------------------------------------------------------------------
    # Distributed rate limiting (atomic)
    # ------------------------------------------------------------------
    def check_rate_limit(
        self,
        category: str,
        identifier: str,
        limit: int,
        window_seconds: int,
        block_seconds: Optional[int] = None,
    ) -> Tuple[bool, int, int]:
        """Distributed, atomic rate-limit check-and-record.

        Args:
            category: logical bucket (e.g. ``"login"``, ``"signup"``).
            identifier: scoped key, typically the client IP.
            limit: maximum attempts allowed within the window before blocking.
            window_seconds: TTL for the attempt counter (sliding).
            block_seconds: lockout TTL once the limit is exceeded. Defaults to
                ``window_seconds``.

        Returns:
            ``(allowed, retry_after_seconds, current_count)``. ``allowed`` is
            False when the client is currently in a lockout window.
        """
        if block_seconds is None:
            block_seconds = window_seconds
        counter_key = f"{self.NS_RATE}:hit:{category}:{identifier}"
        block_key = f"{self.NS_RATE}:block:{category}:{identifier}"
        now = self.now_ts()

        if self.enabled and self.client is not None:
            try:
                allowed = bool(self.client.eval(
                    _RATE_LIMIT_LUA,
                    2,
                    counter_key,
                    block_key,
                    int(limit),
                    int(window_seconds),
                    int(block_seconds),
                    now,
                ))
                # If not allowed, compute remaining lockout from the block key TTL.
                retry_after = 0
                count = 0
                if not allowed:
                    try:
                        ttl = self.client.ttl(block_key)
                        retry_after = max(0, int(ttl))
                    except Exception:
                        retry_after = block_seconds
                try:
                    raw_count = self.client.get(counter_key)
                    count = int(raw_count) if raw_count else 0
                except Exception:
                    count = 0
                return allowed, retry_after, count
            except Exception as exc:
                logger.warning("Distributed rate limit error (%s), falling back to memory: %s", category, exc)

        # In-memory fallback (single-node accounting only).

        # In-memory fallback (single-node accounting only).
        with self._mem_lock:
            # Block check
            blocked_entry = self._memory.get(block_key)
            if blocked_entry and time.time() < blocked_entry[1]:
                retry_after = max(0, int(blocked_entry[1] - time.time()))
                count = len([t for t in self._counters.get(counter_key, []) if time.time() - t < window_seconds])
                return False, retry_after, count
            # Increment counter
            counter = [t for t in self._counters.get(counter_key, []) if time.time() - t < window_seconds]
            counter.append(time.time())
            self._counters[counter_key] = counter
            count = len(counter)
            if count > limit:
                self._memory[block_key] = (True, time.time() + block_seconds)
                return False, block_seconds, count
            return True, 0, count

    def reset_rate_limit(self, category: str, identifier: str) -> None:
        """Clear both the counter and block keys for a rate-limit bucket."""
        counter_key = f"{self.NS_RATE}:hit:{category}:{identifier}"
        block_key = f"{self.NS_RATE}:block:{category}:{identifier}"
        if self.enabled and self.client is not None:
            try:
                self.client.delete(counter_key, block_key)
                return
            except Exception:
                pass
        with self._mem_lock:
            self._memory.pop(counter_key, None)
            self._memory.pop(block_key, None)
            self._counters.pop(counter_key, None)

    # ------------------------------------------------------------------
    # Convenience helpers for the cache namespaces used by the app
    # ------------------------------------------------------------------
    def get_product_cache_key(self, account_id: str) -> str:
        return f"{self.NS_PRODUCTS}:{account_id}"

    def get_stats_cache_key(self, account_id: str, cashier_id: Optional[str] = None) -> str:
        return f"{self.NS_STATS}:{account_id}:{cashier_id or 'all'}"

    def get_monitor_stats_cache_key(self, account_id: str) -> str:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        return f"{self.NS_MONITOR}:{account_id}:{today}"
