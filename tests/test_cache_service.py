"""
Cache Service Tests
===================
Tests for the Redis-backed CacheService: in-memory fallback behaviour and the
distributed rate limiter, plus the Redis code-path exercised via a lightweight
in-process fake client (no live Redis required).
"""

import time
import threading

import pytest

from services.cache_service import CacheService


# ---------------------------------------------------------------------------
# In-memory fallback (REDIS_URL unset / empty) — used in the test env
# ---------------------------------------------------------------------------
@pytest.fixture
def mem_cache():
    return CacheService(redis_url=None)


class TestInMemoryFallback:
    def test_disabled_without_redis(self, mem_cache):
        assert mem_cache.enabled is False
        assert mem_cache.is_healthy() is False
        info = mem_cache.health_check()
        assert info["status"] == "disabled"
        assert info["configured"] is False

    def test_json_roundtrip(self, mem_cache):
        assert mem_cache.set_json("foo", {"a": 1}, ttl_seconds=5) is False
        assert mem_cache.get_json("foo") == {"a": 1}
        mem_cache.delete("foo")
        assert mem_cache.get_json("foo") is None

    def test_int_roundtrip(self, mem_cache):
        mem_cache.set_int("cnt", 42, ttl_seconds=5)
        assert mem_cache.get_int("cnt") == 42

    def test_incr_with_ttl_tracks_count(self, mem_cache):
        assert mem_cache.incr_with_ttl("hits", 60) == 1
        assert mem_cache.incr_with_ttl("hits", 60) == 2
        assert mem_cache.incr_with_ttl("hits", 60) == 3

    def test_check_rate_limit_allows_then_blocks(self, mem_cache):
        limit = 3
        results = [mem_cache.check_rate_limit("login", "ip", limit, 60, 30) for _ in range(limit + 1)]
        allowed = [r[0] for r in results]
        assert allowed == [True, True, True, False]
        # Blocked entry should report a retry_after within the block window.
        assert 0 < results[-1][1] <= 30

    def test_check_rate_limit_reset(self, mem_cache):
        for _ in range(3):
            mem_cache.check_rate_limit("signup", "ip2", 3, 60, 30)
        allowed_before, _, _ = mem_cache.check_rate_limit("signup", "ip2", 3, 60, 30)
        assert allowed_before is False
        mem_cache.reset_rate_limit("signup", "ip2")
        allowed_after, _, _ = mem_cache.check_rate_limit("signup", "ip2", 3, 60, 30)
        assert allowed_after is True

    def test_namespace_helpers(self, mem_cache):
        assert mem_cache.get_product_cache_key("acc_1") == "cache:products:acc_1"
        assert mem_cache.get_stats_cache_key("acc_1") == "cache:stats:acc_1:all"
        assert mem_cache.get_stats_cache_key("acc_1", "7") == "cache:stats:acc_1:7"


# ---------------------------------------------------------------------------
# Lightweight in-process fake Redis (emulates the subset CacheService uses)
# ---------------------------------------------------------------------------
class FakeRedis:
    def __init__(self):
        self.store = {}
        self.expires = {}
        self.lock = threading.RLock()

    def _touch(self, k):
        if k in self.expires and self.expires[k] < time.time():
            self.store.pop(k, None)
            self.expires.pop(k, None)

    def ping(self):
        return True

    def get(self, k):
        with self.lock:
            self._touch(k)
            return self.store.get(k)

    def setex(self, k, ttl, v):
        with self.lock:
            self.store[k] = v
            self.expires[k] = time.time() + ttl

    def set(self, k, v, ex=None):
        with self.lock:
            self.store[k] = v
            if ex is not None:
                self.expires[k] = time.time() + ex

    def delete(self, *ks):
        with self.lock:
            for k in ks:
                self.store.pop(k, None)
                self.expires.pop(k, None)

    def exists(self, *ks):
        with self.lock:
            for k in ks:
                self._touch(k)
                if k in self.store:
                    return 1
            return 0

    def ttl(self, k):
        with self.lock:
            return max(0, int(self.expires.get(k, 0) - time.time()))

    def eval(self, script, nkeys, *args):
        with self.lock:
            keys = args[:nkeys]
            argv = args[nkeys:]
            counter_key, block_key = keys
            limit = int(argv[0])
            window = int(argv[1])
            block_ttl = int(argv[2])
            now = float(argv[3])
            b = self.get(block_key)
            if b is not None and float(b) > now:
                return 0
            c = self.get(counter_key)
            c = int(c) if c is not None else 0
            n = c + 1
            self.set(counter_key, n, ex=window)
            if n > limit:
                self.set(block_key, now + block_ttl, ex=block_ttl)
                return 0
            return 1


def _make_redis_cache(fake):
    cs = CacheService(redis_url=None)
    # Bypass real network connect: pretend a URL is configured and attach
    # the in-process fake client.
    cs._redis_url = "redis://localhost:6379/0"
    cs.client = fake
    cs.enabled = True
    return cs


class TestRedisBacked:
    def test_redis_health_connected(self):
        fake = FakeRedis()
        cs = _make_redis_cache(fake)
        info = cs.health_check()
        assert info["status"] == "connected"
        assert cs.is_healthy() is True

    def test_json_roundtrip_redis(self):
        cs = _make_redis_cache(FakeRedis())
        assert cs.set_json("k", [1, 2, 3], ttl_seconds=5) is True
        assert cs.get_json("k") == [1, 2, 3]

    def test_rate_limit_is_atomic_and_shared(self):
        shared = FakeRedis()
        csA = _make_redis_cache(shared)
        csB = _make_redis_cache(shared)
        limit = 3
        seen = [
            csA.check_rate_limit("login", "ip", limit, 60, 30)[0],
            csB.check_rate_limit("login", "ip", limit, 60, 30)[0],
            csA.check_rate_limit("login", "ip", limit, 60, 30)[0],
            csB.check_rate_limit("login", "ip", limit, 60, 30)[0],
        ]
        assert seen == [True, True, True, False]

    def test_revoked_token_shared_across_instances(self):
        from auth.manager import AuthManager

        shared = FakeRedis()
        csA = _make_redis_cache(shared)
        csB = _make_redis_cache(shared)
        amA = AuthManager("secret", cache_service=csA)
        amB = AuthManager("secret", cache_service=csB)

        token = amA.generate_token(
            {"id": 1, "email": "u@x.com", "account_id": "acc", "role": "admin"}
        )
        assert amB.verify_token(token) is not None
        amA.revoke_token(token)
        # Revocation recorded in the shared Redis store is visible to B.
        assert amB.verify_token(token) is None

    def test_user_cache_shared_across_instances(self):
        from auth.manager import AuthManager

        shared = FakeRedis()
        csA = _make_redis_cache(shared)
        csB = _make_redis_cache(shared)
        amA = AuthManager("secret", cache_service=csA)
        amB = AuthManager("secret", cache_service=csB)

        user = {"id": 1, "email": "u@x.com", "account_id": "acc", "role": "admin", "is_active": True}
        acct = {"id": "acc", "is_active": True, "is_locked": False, "plan": "trial", "trial_ends_at": None}
        amA._cache_set("auth:1:acc", (user, acct))
        cached = amB._cache_get("auth:1:acc")
        assert cached is not None
        assert cached[0] == user
        amA.invalidate_user_session_cache(1, "acc")
        assert amB._cache_get("auth:1:acc") is None
