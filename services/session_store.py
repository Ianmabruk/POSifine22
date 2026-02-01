import os
import json
import secrets
import hashlib
from datetime import datetime, timedelta

try:
    import redis
except Exception:
    redis = None


class SessionStore:
    def __init__(self):
        self.enabled = False
        self.client = None
        redis_url = os.environ.get("REDIS_URL")
        if redis and redis_url:
            try:
                self.client = redis.Redis.from_url(redis_url, decode_responses=True)
                self.client.ping()
                self.enabled = True
            except Exception:
                self.client = None
                self.enabled = False

    def _hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _session_key(self, token_hash: str) -> str:
        return f"session:{token_hash}"

    def _revoked_key(self, token_hash: str) -> str:
        return f"session:revoked:{token_hash}"

    def create(self, user: dict, user_agent: str, ip_address: str, ttl_days: int = 7) -> str:
        if not self.enabled:
            raise RuntimeError("SessionStore not enabled")

        refresh_token = secrets.token_urlsafe(48)
        token_hash = self._hash(refresh_token)
        now = datetime.utcnow()
        expires_at = now + timedelta(days=ttl_days)

        payload = {
            "account_id": user.get("account_id"),
            "user_id": user.get("id"),
            "user_agent": user_agent,
            "ip_address": ip_address,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "revoked_at": None
        }

        key = self._session_key(token_hash)
        self.client.setex(key, int(ttl_days * 86400), json.dumps(payload))
        return refresh_token

    def get(self, refresh_token: str) -> dict | None:
        if not self.enabled:
            return None
        token_hash = self._hash(refresh_token)
        if self.client.get(self._revoked_key(token_hash)):
            return None

        key = self._session_key(token_hash)
        value = self.client.get(key)
        if not value:
            return None
        try:
            return json.loads(value)
        except Exception:
            return None

    def revoke(self, refresh_token: str) -> bool:
        if not self.enabled:
            return False
        token_hash = self._hash(refresh_token)
        key = self._session_key(token_hash)
        value = self.client.get(key)
        if not value:
            return False
        try:
            session = json.loads(value)
        except Exception:
            session = {}
        expires_at = session.get("expires_at")
        ttl_seconds = 86400
        if expires_at:
            try:
                exp_ts = datetime.fromisoformat(expires_at)
                ttl_seconds = max(60, int((exp_ts - datetime.utcnow()).total_seconds()))
            except Exception:
                ttl_seconds = 86400

        self.client.setex(self._revoked_key(token_hash), ttl_seconds, "1")
        self.client.delete(key)
        return True
