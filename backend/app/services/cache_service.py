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
                self.client = redis.from_url(
                    settings.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                    retry_on_timeout=False,
                )
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

    async def incr(self, key: str, ttl_seconds: int = 60) -> int | None:
        """Atomically increment a counter and set TTL on first write. Returns new count.
        Returns None when Redis is unavailable so callers can use a fallback."""
        if not self.using_redis:
            return None
        full_key = f"{self.prefix}:{key}"
        try:
            count = await self.client.incr(full_key)
            if count == 1:
                await self.client.expire(full_key, ttl_seconds)
            return count
        except Exception as exc:
            self.logger.warning("redis_incr_failed key=%s error=%s — falling back to in-process", key, exc)
            self.enabled = False
            return None

    async def get_int(self, key: str) -> int | None:
        """Read a counter, returning None when Redis is unavailable."""
        if not self.using_redis:
            return None
        try:
            raw = await self.client.get(f"{self.prefix}:{key}")
            return int(raw) if raw is not None else 0
        except (ValueError, TypeError):
            return 0
        except Exception as exc:
            self.logger.warning("redis_get_int_failed key=%s error=%s", key, exc)
            return None

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
            self.enabled = False
            return False

    async def close(self) -> None:
        if not self.using_redis:
            return
        try:
            await self.client.aclose()
        except Exception as exc:
            self.logger.warning("redis_cache_close_failed error=%s", exc)

    async def acquire_lock(self, name: str, owner: str, ttl_seconds: int) -> bool:
        if not self.using_redis:
            return True
        try:
            return bool(await self.client.set(self._key("locks", name), owner, ex=max(5, ttl_seconds), nx=True))
        except Exception as exc:
            self.logger.warning("redis_lock_acquire_failed name=%s error=%s", name, exc)
            self.enabled = False
            return False

    async def release_lock(self, name: str, owner: str) -> None:
        if not self.using_redis:
            return
        key = self._key("locks", name)
        script = "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
        try:
            await self.client.eval(script, 1, key, owner)
        except Exception as exc:
            self.logger.warning("redis_lock_release_failed name=%s error=%s", name, exc)
