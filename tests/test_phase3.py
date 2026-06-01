import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.models import AlertDeliverySettings, AlertRule, SourceDoc
from backend.app.services.alert_service import AlertService
from backend.app.services.document_store import DocumentStore


class FakeHttpResponse:
    status_code = 200


class FakeAsyncClient:
    def __init__(self, *args, **kwargs):
        self.posts = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, json):
        self.posts.append((url, json))
        return FakeHttpResponse()


class PhaseThreeTests(unittest.TestCase):
    def test_auth_register_login_and_me_lookup(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase3_auth.db"))
            user = store.create_user("test@example.com", "supersecret", "Test User")
            session = store.authenticate_user("test@example.com", "supersecret")
            self.assertIsNotNone(session)
            self.assertEqual(session.user.user_id, user.user_id)
            looked_up = store.get_user_by_token(session.token)
            self.assertIsNotNone(looked_up)
            self.assertEqual(looked_up.email, "test@example.com")

    def test_search_history_and_saved_sessions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase3_history.db"))
            user = store.create_user("history@example.com", "supersecret", "History User")
            doc = SourceDoc(
                title="AI agents coordinate software tasks",
                summary="AI agents can plan coding steps.",
                url="https://example.com/agents-history",
                source="Example Tech",
                category="tech",
                published_at=datetime.now(timezone.utc),
            )
            store.save_context("ctx123", user.user_id, "ai agents", [doc])
            store.add_search_history(user.user_id, "ai agents", ["tech"], "ctx123")
            store.save_session(user.user_id, "ctx123", "Agents brief")

            history = store.get_search_history(user.user_id)
            sessions = store.get_saved_sessions(user.user_id)
            self.assertEqual(history[0].context_id, "ctx123")
            self.assertEqual(sessions[0].label, "Agents brief")

    def test_auth_logout_and_verification_reset_flow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase3_auth_flows.db"))
            user = store.create_user("flows@example.com", "supersecret", "Flow User")
            session = store.authenticate_user("flows@example.com", "supersecret")
            self.assertIsNotNone(session)

            verification_token, _ = store.issue_verification_token(user.user_id)
            verified = store.verify_email(verification_token)
            self.assertIsNotNone(verified)
            self.assertTrue(verified.email_verified)

            reset_token, _ = store.issue_password_reset_token("flows@example.com")
            result = store.reset_password(reset_token, "newsupersecret")
            self.assertIsNotNone(result)
            self.assertIsNone(store.get_user_by_token(session.token))

            fresh_session = store.authenticate_user("flows@example.com", "newsupersecret")
            self.assertIsNotNone(fresh_session)
            store.logout_session(fresh_session.token)
            self.assertIsNone(store.get_user_by_token(fresh_session.token))

    def test_alert_service_delivers_due_alerts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase3_alerts.db"))
            user = store.create_user("alerts@example.com", "supersecret", "Alert User")
            store.upsert_alert_delivery(
                AlertDeliverySettings(
                    user_id=user.user_id,
                    webhook_url="https://example.com/webhook",
                    digest_mode="instant",
                    enabled=True,
                )
            )
            store.add_alert(AlertRule(user_id=user.user_id, query="AI agents", categories=["tech"], enabled=True))
            store.upsert_documents(
                [
                    SourceDoc(
                        title="AI agents coordinate software tasks",
                        summary="AI agents can plan coding steps and execute fixes.",
                        url="https://example.com/agents-alert",
                        source="Example Tech",
                        category="tech",
                        published_at=datetime.now(timezone.utc),
                    )
                ]
            )

            service = AlertService(store)
            with patch("backend.app.services.alert_service.httpx.AsyncClient", FakeAsyncClient):
                import asyncio

                delivered = asyncio.run(service.process_alerts())

            self.assertEqual(delivered, 1)
            alerts = store.get_enabled_alerts()
            self.assertTrue(alerts[0]["last_triggered_at"])

    def test_request_verification_uses_smtp_when_available(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase3_verify_email.db"))
            with patch.object(main_module, "store", store), patch.object(
                main_module, "email_service", SimpleNamespace(send=AsyncMock(return_value=True))
            ):
                client = TestClient(main_module.app)
                register = client.post(
                    "/auth/register",
                    json={
                        "email": "mail@example.com",
                        "password": "supersecret123",
                        "display_name": "Mail User",
                    },
                )
                self.assertEqual(register.status_code, 200)
                login = client.post(
                    "/auth/login",
                    json={"email": "mail@example.com", "password": "supersecret123"},
                )
                self.assertEqual(login.status_code, 200)
                token = login.json()["token"]
                response = client.post("/auth/request-verification", headers={"Authorization": f"Bearer {token}"})
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["email_sent"])
                self.assertEqual(payload["delivery_mode"], "smtp")


if __name__ == "__main__":
    unittest.main()
