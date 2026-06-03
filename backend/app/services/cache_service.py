import json
from typing import Any

from backend.app.config import settings
from backend.app.services.logging_service import get_logger

try:
    import redis.asyncio as redis
except Exception:  # pragma: no cover
    redis = None


class CacheService:
    def __init__(self) -> None:
        self.logger = get_logger("signalscope.cache")
        self.backend = settings.cache_backend.lower().strip() or "sqlite"
        self.prefix = settings.redis_prefix.strip() or "signalscope"
        self.client = None
        self.enabled = False

        if self.backend == "redis" and redis and settings.redis_url:
            try:
                self.client = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
                self.enabled = True
            except Exception as exc:
                self.logger.warning("redis_cache_init_failed error=%s", exc)
                self.client = None
                self.enabled = False

    @property
    def using_redis(self) -> bool:
        return bool(self.enabled and self.client)

    def _key(self, namespace: str, cache_key: str) -> str:
        return f"{self.prefix}:{namespace}:{cache_key}"

    async def get(self, namespace: str, cache_key: str) -> str | None:
        if not self.using_redis:
            return None
        try:
            return await self.client.get(self._key(namespace, cache_key))
        except Exception as exc:
            self.logger.warning("redis_cache_get_failed namespace=%s error=%s", namespace, exc)
            return None

    async def set_json(self, namespace: str, cache_key: str, payload: dict[str, Any], ttl_minutes: int) -> None:
        if not self.using_redis:
            return
        try:
            await self.client.set(self._key(namespace, cache_key), json.dumps(payload), ex=max(ttl_minutes * 60, 60))
        except Exception as exc:
            self.logger.warning("redis_cache_put_failed namespace=%s error=%s", namespace, exc)

    async def get_query_cache(self, query_key: str) -> str | None:
        return await self.get("query_cache", query_key)

    async def put_query_cache(self, query_key: str, payload: dict[str, Any], ttl_minutes: int) -> None:
        await self.set_json("query_cache", query_key, payload, ttl_minutes)

    async def incr(self, key: str, ttl_seconds: int = 60) -> int:
        """Atomically increment a counter and set TTL on first write. Returns new count.
        Returns 0 when Redis is unavailable so callers fall back to in-process limiting."""
        if not self.using_redis:
            return 0
        full_key = f"{self.prefix}:{key}"
        try:
            count = await self.client.incr(full_key)
            if count == 1:
                await self.client.expire(full_key, ttl_seconds)
            return count
        except Exception as exc:
            self.logger.warning("redis_incr_failed key=%s error=%s — falling back to in-process", key, exc)
            return 0  # fall back to in-process rate limiting in main.py

    async def get_int(self, key: str) -> int:
        """Read an integer counter. Returns 0 when missing or Redis is unavailable."""
        if not self.using_redis:
            return 0
        try:
            raw = await self.client.get(f"{self.prefix}:{key}")
            return int(raw) if raw is not None else 0
        except (ValueError, TypeError):
            return 0
        except Exception as exc:
            self.logger.warning("redis_get_int_failed key=%s error=%s", key, exc)
            return 0

    async def delete(self, key: str) -> None:
        """Delete a prefixed key. No-op when Redis is unavailable."""
        if not self.using_redis:
            return
        try:
            await self.client.delete(f"{self.prefix}:{key}")
        except Exception as exc:
            self.logger.warning("redis_delete_failed key=%s error=%s", key, exc)

    async def ping(self) -> bool:
        if not self.using_redis:
            return False
        try:
            return bool(await self.client.ping())
        except Exception as exc:
            self.logger.warning("redis_cache_ping_failed error=%s", exc)
            return False

    async def close(self) -> None:
        if not self.using_redis:
            return
        try:
            await self.client.aclose()
        except Exception as exc:
            self.logger.warning("redis_cache_close_failed error=%s", exc)
