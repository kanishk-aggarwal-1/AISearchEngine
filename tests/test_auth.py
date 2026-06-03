"""
Auth integration tests.
Tests the full flow: register → login → protected endpoint → logout → token rejected.
Uses a real in-memory DocumentStore — no mocking of auth logic.
"""
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.services.document_store import DocumentStore


@contextmanager
def _auth_context():
    """
    Replace all store/email/rate-limit references with test doubles.
    The DocumentStore is real (in-memory SQLite) so auth logic is exercised.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "auth_test.db"))
        mock_email = SimpleNamespace(send=AsyncMock(return_value=False))
        fake_cache = SimpleNamespace(
            using_redis=False,
            incr=AsyncMock(return_value=1),
            ping=AsyncMock(return_value=False),
        )
        fake_embedding = SimpleNamespace(real_embeddings_enabled=True)

        with (
            patch("backend.app.routers.auth.store", store),
            patch("backend.app.routers.auth.email_service", mock_email),
            patch("backend.app.routers.users.store", store),
            patch("backend.app.dependencies.store", store),
            patch("backend.app.main.cache", fake_cache),
            patch("backend.app.main.embedding_service", fake_embedding),
        ):
            yield store


class TestAuthFlow(unittest.TestCase):
    # ── DocumentStore unit tests (no HTTP) ───────────────────────────────────

    def test_register_creates_user(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            user = store.create_user("alice@example.com", "strongpassword1", "Alice")
            self.assertEqual(user.email, "alice@example.com")
            self.assertEqual(user.display_name, "Alice")
            self.assertFalse(user.email_verified)
            # First registered user becomes admin (initial setup by design)
            self.assertTrue(user.is_admin)

    def test_second_user_is_not_admin(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("admin@example.com", "adminpassword1", "Admin")
            regular = store.create_user("alice@example.com", "strongpassword1", "Alice")
            self.assertFalse(regular.is_admin)

    def test_authenticate_correct_password(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("bob@example.com", "correctpassword!", "Bob")
            session = store.authenticate_user("bob@example.com", "correctpassword!")
            self.assertIsNotNone(session)
            self.assertIsNotNone(session.token)
            self.assertEqual(session.user.email, "bob@example.com")

    def test_authenticate_wrong_password_returns_none(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("carol@example.com", "rightpassword1", "Carol")
            session = store.authenticate_user("carol@example.com", "wrongpassword1")
            self.assertIsNone(session)

    def test_token_valid_after_login(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("dave@example.com", "password12345", "Dave")
            session = store.authenticate_user("dave@example.com", "password12345")
            user = store.get_user_by_token(session.token)
            self.assertIsNotNone(user)
            self.assertEqual(user.user_id, session.user.user_id)

    def test_token_invalid_after_logout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("eve@example.com", "password12345", "Eve")
            session = store.authenticate_user("eve@example.com", "password12345")
            store.logout_session(session.token)
            user = store.get_user_by_token(session.token)
            self.assertIsNone(user)

    def test_duplicate_email_raises(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "test.db"))
            store.create_user("dup@example.com", "password12345", "First")
            # Unique constraint on email — duplicate insert must raise IntegrityError.
            with self.assertRaises(sqlite3.IntegrityError):
                store.create_user("dup@example.com", "password12345", "Second")

    # ── HTTP-level tests ─────────────────────────────────────────────────────

    def _register_and_login(self, client, email="test@example.com", password="Strongpass99"):
        # The first registration always becomes admin. Burn the slot with a throwaway
        # so the test user is a regular (non-admin) member.
        client.post("/v1/auth/register", json={
            "email": "setup-admin@example.com", "password": "Adminsetup1!", "display_name": "Setup"
        })
        client.post("/v1/auth/register", json={
            "email": email, "password": password, "display_name": "Tester"
        })
        resp = client.post("/v1/auth/login", json={"email": email, "password": password})
        return resp.json()["token"]

    def test_register_login_protected_endpoint(self):
        with _auth_context():
            client = TestClient(main_module.app)
            token = self._register_and_login(client)
            resp = client.get(
                "/v1/me/search-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertIsInstance(resp.json(), list)

    def test_protected_endpoint_without_token_returns_401(self):
        """Every /users/{id}/* and /me/* endpoint must reject unauthenticated requests."""
        with _auth_context():
            client = TestClient(main_module.app)
            # Get user_id from the auth response instead of re-authenticating directly
            client.post("/v1/auth/register", json={
                "email": "setup-admin@example.com", "password": "Adminsetup1!", "display_name": "Setup"
            })
            client.post("/v1/auth/register", json={
                "email": "test@example.com", "password": "Strongpass99", "display_name": "Tester"
            })
            login_resp = client.post("/v1/auth/login", json={"email": "test@example.com", "password": "Strongpass99"})
            user_id = login_resp.json()["user"]["user_id"]
            token = login_resp.json()["token"]  # noqa: F841 — registered but not used here

            endpoints = [
                ("GET", f"/v1/users/{user_id}/profile"),
                ("GET", f"/v1/users/{user_id}/follows"),
                ("GET", f"/v1/users/{user_id}/alerts"),
                ("GET", f"/v1/users/{user_id}/bookmarks"),
                ("GET", f"/v1/users/{user_id}/alert-delivery"),
                ("GET", "/v1/me/search-history"),
                ("GET", "/v1/me/saved-sessions"),
                ("GET", "/v1/me/watchlist"),
            ]
            for method, path in endpoints:
                resp = client.request(method, path)
                self.assertEqual(
                    resp.status_code, 401,
                    f"Expected 401 for {method} {path}, got {resp.status_code}"
                )

    def test_cross_user_access_returns_403(self):
        """User A (non-admin) cannot read User B's data even with a valid token."""
        with _auth_context():
            client = TestClient(main_module.app)
            # First registration → admin (throwaway). Subsequent → non-admin.
            client.post("/v1/auth/register", json={
                "email": "setup-admin@example.com", "password": "Adminsetup1!", "display_name": "Setup"
            })
            client.post("/v1/auth/register", json={
                "email": "usera@example.com", "password": "Strongpass99", "display_name": "UserA"
            })
            resp_b = client.post("/v1/auth/register", json={
                "email": "userb@example.com", "password": "Strongpass99", "display_name": "UserB"
            })
            login_a = client.post("/v1/auth/login", json={
                "email": "usera@example.com", "password": "Strongpass99"
            })
            self.assertEqual(login_a.status_code, 200, f"Login failed: {login_a.json()}")
            token_a = login_a.json()["token"]
            user_b_id = resp_b.json()["user_id"]

            resp = client.get(
                f"/v1/users/{user_b_id}/profile",
                headers={"Authorization": f"Bearer {token_a}"},
            )
            self.assertEqual(resp.status_code, 403)

    def test_admin_endpoint_returns_403_for_non_admin(self):
        with _auth_context():
            client = TestClient(main_module.app)
            token = self._register_and_login(client)
            resp = client.get(
                "/v1/admin/dashboard",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 403)

    def test_logout_then_token_rejected(self):
        with _auth_context():
            client = TestClient(main_module.app)
            token = self._register_and_login(client)
            client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
            resp = client.get(
                "/v1/me/search-history",
                headers={"Authorization": f"Bearer {token}"},
            )
            self.assertEqual(resp.status_code, 401)

    # ── Input validation tests (no store needed) ─────────────────────────────

    def test_password_too_short_rejected(self):
        with _auth_context():
            client = TestClient(main_module.app)
            resp = client.post("/v1/auth/register", json={
                "email": "short@example.com",
                "password": "abc12",     # 5 chars — below min_length=10
                "display_name": "Test",
            })
            self.assertEqual(resp.status_code, 422)

    def test_invalid_email_rejected(self):
        with _auth_context():
            client = TestClient(main_module.app)
            resp = client.post("/v1/auth/register", json={
                "email": "not-an-email",
                "password": "validpassword1",
                "display_name": "Test",
            })
            self.assertEqual(resp.status_code, 422)

    def test_password_no_uppercase_rejected(self):
        with _auth_context():
            client = TestClient(main_module.app)
            resp = client.post("/v1/auth/register", json={
                "email": "weak@example.com",
                "password": "alllowercase1",   # no uppercase
                "display_name": "Weak",
            })
            self.assertEqual(resp.status_code, 422)

    def test_password_no_digit_rejected(self):
        with _auth_context():
            client = TestClient(main_module.app)
            resp = client.post("/v1/auth/register", json={
                "email": "weak2@example.com",
                "password": "NoDigitPassword",  # no digit
                "display_name": "Weak",
            })
            self.assertEqual(resp.status_code, 422)

    def test_wrong_credentials_returns_401(self):
        with _auth_context():
            client = TestClient(main_module.app)
            client.post("/v1/auth/register", json={
                "email": "legit@example.com", "password": "Correctpass1", "display_name": "Legit"
            })
            resp = client.post("/v1/auth/login", json={
                "email": "legit@example.com", "password": "Wrongpassword1"
            })
            self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
