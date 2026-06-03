"""
Tests for login brute-force protection (LoginThrottle) and the /auth/login
lockout behaviour.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.services.document_store import DocumentStore
from backend.app.services.login_throttle import LoginThrottle


def _run(coro):
    return asyncio.run(coro)


class LoginThrottleUnitTests(unittest.TestCase):
    def _inprocess_cache(self):
        return SimpleNamespace(using_redis=False)

    def test_not_locked_initially(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=3, window_seconds=900)
        self.assertFalse(_run(throttle.is_locked("a@example.com")))

    def test_locks_after_threshold(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=3, window_seconds=900)
        for _ in range(3):
            _run(throttle.record_failure("a@example.com"))
        self.assertTrue(_run(throttle.is_locked("a@example.com")))

    def test_below_threshold_not_locked(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=3, window_seconds=900)
        _run(throttle.record_failure("a@example.com"))
        _run(throttle.record_failure("a@example.com"))
        self.assertFalse(_run(throttle.is_locked("a@example.com")))

    def test_reset_clears_failures(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=3, window_seconds=900)
        for _ in range(3):
            _run(throttle.record_failure("a@example.com"))
        _run(throttle.reset("a@example.com"))
        self.assertFalse(_run(throttle.is_locked("a@example.com")))

    def test_is_locked_does_not_increment(self):
        """Checking lock status must never count as a failed attempt."""
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=3, window_seconds=900)
        _run(throttle.record_failure("a@example.com"))
        for _ in range(10):
            _run(throttle.is_locked("a@example.com"))
        # Still only 1 real failure → not locked
        self.assertFalse(_run(throttle.is_locked("a@example.com")))

    def test_per_email_isolation(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=2, window_seconds=900)
        _run(throttle.record_failure("a@example.com"))
        _run(throttle.record_failure("a@example.com"))
        self.assertTrue(_run(throttle.is_locked("a@example.com")))
        self.assertFalse(_run(throttle.is_locked("b@example.com")))

    def test_email_normalized(self):
        throttle = LoginThrottle(self._inprocess_cache(), max_attempts=2, window_seconds=900)
        _run(throttle.record_failure("A@Example.com"))
        _run(throttle.record_failure(" a@example.com "))
        self.assertTrue(_run(throttle.is_locked("a@example.com")))

    def test_redis_path_uses_counter(self):
        """With Redis available, is_locked reads get_int and never increments."""
        store = {"login_fail:a@example.com": 5}
        cache = SimpleNamespace(
            using_redis=True,
            get_int=AsyncMock(side_effect=lambda k: store.get(k, 0)),
            incr=AsyncMock(),
            delete=AsyncMock(),
        )
        throttle = LoginThrottle(cache, max_attempts=5, window_seconds=900)
        self.assertTrue(_run(throttle.is_locked("a@example.com")))
        cache.incr.assert_not_called()  # read path must not increment


class LoginLockoutHttpTests(unittest.TestCase):
    def test_repeated_failures_return_429(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "throttle_http.db"))
            store.create_user("victim@example.com", "Correctpass123", "Victim")

            fresh_throttle = LoginThrottle(
                SimpleNamespace(using_redis=False), max_attempts=3, window_seconds=900
            )
            fake_cache = SimpleNamespace(
                using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False)
            )
            with (
                patch("backend.app.routers.auth.store", store),
                patch("backend.app.routers.auth.login_throttle", fresh_throttle),
                patch("backend.app.main.cache", fake_cache),
                patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)),
            ):
                client = TestClient(main_module.app)
                # 3 wrong-password attempts → all 401
                for _ in range(3):
                    r = client.post("/v1/auth/login", json={"email": "victim@example.com", "password": "Wrongpass123"})
                    self.assertEqual(r.status_code, 401)
                # 4th attempt is locked out → 429, even with the CORRECT password
                r = client.post("/v1/auth/login", json={"email": "victim@example.com", "password": "Correctpass123"})
                self.assertEqual(r.status_code, 429)
                self.assertIn("Retry-After", r.headers)

    def test_successful_login_resets_counter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "throttle_reset.db"))
            store.create_user("user@example.com", "Correctpass123", "User")

            fresh_throttle = LoginThrottle(
                SimpleNamespace(using_redis=False), max_attempts=3, window_seconds=900
            )
            fake_cache = SimpleNamespace(
                using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False)
            )
            with (
                patch("backend.app.routers.auth.store", store),
                patch("backend.app.routers.auth.login_throttle", fresh_throttle),
                patch("backend.app.main.cache", fake_cache),
                patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)),
            ):
                client = TestClient(main_module.app)
                # 2 failures (under threshold of 3)
                for _ in range(2):
                    client.post("/v1/auth/login", json={"email": "user@example.com", "password": "Wrongpass123"})
                # successful login resets the counter
                ok = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "Correctpass123"})
                self.assertEqual(ok.status_code, 200)
                # counter cleared → 2 more failures still under threshold, not locked
                for _ in range(2):
                    r = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "Wrongpass123"})
                    self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
