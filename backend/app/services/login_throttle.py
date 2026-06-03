"""
Login brute-force protection.

The global per-IP rate limiter does not stop targeted password guessing against
a single account (an attacker can stay well under 90 req/min and still try
thousands of passwords). This throttle tracks failed login attempts per email
and locks the account out temporarily once a threshold is crossed.

Backed by Redis when available (works across workers); falls back to an
in-process window otherwise so single-worker dev still gets protection.
"""
import time


class LoginThrottle:
    def __init__(self, cache, max_attempts: int = 5, window_seconds: int = 900) -> None:
        self.cache = cache
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # email -> list[timestamp] for the in-process fallback path
        self._buckets: dict[str, list[float]] = {}

    @staticmethod
    def _key(email: str) -> str:
        return f"login_fail:{email.strip().lower()}"

    async def is_locked(self, email: str) -> bool:
        """True when the account has too many recent failures. Read-only — never
        increments the counter (so checking does not lock out a legit user)."""
        if self.cache.using_redis:
            return await self.cache.get_int(self._key(email)) >= self.max_attempts
        return self._recent_failures(email) >= self.max_attempts

    async def record_failure(self, email: str) -> None:
        if self.cache.using_redis:
            await self.cache.incr(self._key(email), ttl_seconds=self.window_seconds)
            return
        now = time.time()
        bucket = self._live_bucket(email, now)
        bucket.append(now)
        self._buckets[email.strip().lower()] = bucket

    async def reset(self, email: str) -> None:
        """Clear the counter after a successful login."""
        if self.cache.using_redis:
            await self.cache.delete(self._key(email))
        self._buckets.pop(email.strip().lower(), None)

    # ── in-process fallback helpers ─────────────────────────────────────────
    def _live_bucket(self, email: str, now: float) -> list[float]:
        window_start = now - self.window_seconds
        return [t for t in self._buckets.get(email.strip().lower(), []) if t >= window_start]

    def _recent_failures(self, email: str) -> int:
        return len(self._live_bucket(email, time.time()))
