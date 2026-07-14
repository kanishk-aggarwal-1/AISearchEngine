import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.dependencies import resolve_search_user
from backend.app.services.document_store import DocumentStore
from backend.app.services.login_throttle import LoginThrottle
from backend.app.services.webhook_security import UnsafeWebhookURL, validate_webhook_url


def _request(headers=None):
    pairs = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return SimpleNamespace(headers=dict(headers or {}), scope={"headers": pairs})


def test_registered_search_identity_requires_authentication():
    with patch("backend.app.dependencies.optional_user", return_value=None):
        try:
            resolve_search_user(_request(), "user_victim")
            assert False, "expected authentication failure"
        except HTTPException as exc:
            assert exc.status_code == 401


def test_authenticated_search_cannot_impersonate_another_user():
    caller = SimpleNamespace(user_id="user_alice")
    with patch("backend.app.dependencies.optional_user", return_value=caller):
        try:
            resolve_search_user(_request(), "user_bob")
            assert False, "expected authorization failure"
        except HTTPException as exc:
            assert exc.status_code == 403


def test_private_webhook_destination_rejected():
    with patch("backend.app.services.webhook_security.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("127.0.0.1", 443))]):
        try:
            asyncio.run(validate_webhook_url("https://localhost/hook"))
            assert False, "expected unsafe webhook rejection"
        except UnsafeWebhookURL:
            pass


def test_login_throttle_falls_back_when_redis_fails():
    cache = SimpleNamespace(
        using_redis=True,
        incr=AsyncMock(return_value=None),
        get_int=AsyncMock(return_value=None),
        delete=AsyncMock(),
    )
    throttle = LoginThrottle(cache, max_attempts=2, window_seconds=60)
    asyncio.run(throttle.record_failure("user@example.com"))
    asyncio.run(throttle.record_failure("user@example.com"))
    assert asyncio.run(throttle.is_locked("user@example.com"))


def test_password_reset_token_hidden_when_preview_disabled_and_email_fails():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "security.db"))
        store.create_user("member@example.com", "StrongPassword123", "Member")
        fake_cache = SimpleNamespace(using_redis=False, ping=AsyncMock(return_value=False))
        with patch("backend.app.routers.auth.store", store), \
             patch("backend.app.routers.auth.email_service.send", AsyncMock(return_value=False)), \
             patch("backend.app.routers.auth.settings.email_preview_tokens", False), \
             patch("backend.app.main.cache", fake_cache):
            client = TestClient(main_module.app)
            response = client.post(
                "/v1/auth/request-password-reset", json={"email": "member@example.com"}
            )
        assert response.status_code == 200
        assert response.json()["token_preview"] == ""


def test_admin_assignment_uses_explicit_bootstrap_email():
    with tempfile.TemporaryDirectory() as tmpdir, patch(
        "backend.app.services.document_store.settings.bootstrap_admin_email", "owner@example.com"
    ):
        store = DocumentStore(str(Path(tmpdir) / "admin.db"))
        member = store.create_user("member@example.com", "StrongPassword123", "Member")
        owner = store.create_user("owner@example.com", "StrongPassword123", "Owner")
        assert not member.is_admin
        assert owner.is_admin
