import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.models import SourceDoc
from backend.app.services.document_store import DocumentStore
from backend.app.services.source_registry import SourceRegistry


class FakeProvider:
    def __init__(self, source_name="Custom Source"):
        self.source_name = source_name

    async def search(self, query: str, limit: int):
        return [
            SourceDoc(
                title="Custom source result",
                summary=f"Result for {query}",
                url="https://example.com/custom-source",
                source=self.source_name,
                category="tech",
                published_at=datetime.now(timezone.utc),
            )
        ]


class PhaseFiveTests(unittest.TestCase):
    def test_source_registry_records_health_and_respects_disabled_sources(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase5_sources.db"))
            registry = SourceRegistry(store)
            registry.providers = {"tech": [FakeProvider("Custom Source")]}

            docs = asyncio.run(registry.gather("agents", ["tech"], 5))
            self.assertEqual(len(docs), 1)
            statuses = store.get_source_statuses(source_name="Custom Source")
            self.assertTrue(statuses and statuses[0].last_item_count == 1)
            self.assertEqual(statuses[0].success_count, 1)
            self.assertEqual(statuses[0].failure_count, 0)
            self.assertIsNotNone(statuses[0].last_attempt_at)
            self.assertIsNotNone(statuses[0].average_latency_ms)

            store.set_source_enabled("Custom Source", False, category="tech")
            docs = asyncio.run(registry.gather("agents", ["tech"], 5))
            self.assertEqual(docs, [])

    def test_ingestion_runs_and_freshness_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase5_runs.db"))
            run_id = store.create_ingestion_run("query", query="ai agents", categories=["tech", "research"])
            store.finish_ingestion_run(run_id, "completed", inserted_count=4, source_count=2)
            runs = store.recent_ingestion_runs(limit=5)
            self.assertEqual(len(runs), 1)
            self.assertEqual(runs[0].status, "completed")
            self.assertEqual(runs[0].inserted_count, 4)
            self.assertEqual(runs[0].source_count, 2)

            store.record_source_result("Custom Source", "tech", 3, error="", latency_ms=120.0)
            freshness = store.source_freshness_summary()
            self.assertEqual(freshness["healthy_sources"], 1)
            self.assertEqual(freshness["stale_sources"], 0)
            self.assertEqual(freshness["errored_sources"], 0)

    def test_admin_dashboard_returns_snapshot(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase5_admin.db"))
            store.record_source_result("Custom Source", "tech", 3, error="")
            fake_cache = SimpleNamespace(
                using_redis=False,
                incr=__import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=1),
                ping=__import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(return_value=False),
            )
            # Patch store in every module that uses it for these requests
            with patch("backend.app.routers.auth.store", store), \
                 patch("backend.app.routers.admin.store", store), \
                 patch("backend.app.dependencies.store", store), \
                 patch("backend.app.main.cache", fake_cache), \
                 patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)):
                client = TestClient(main_module.app)
                register = client.post(
                    "/v1/auth/register",
                    json={
                        "email": "admin@example.com",
                        "password": "Supersecret123",   # uppercase required by complexity validator
                        "display_name": "Admin User",
                    },
                )
                self.assertEqual(register.status_code, 200)
                login = client.post(
                    "/v1/auth/login",
                    json={"email": "admin@example.com", "password": "Supersecret123"},
                )
                self.assertEqual(login.status_code, 200)
                token = login.json()["token"]

                response = client.get(
                    "/v1/admin/dashboard",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertIn("snapshot", payload)
                self.assertIn("counts", payload["snapshot"])
                self.assertTrue(payload["snapshot"]["source_status"])
                self.assertIn("recent_ingestion_runs", payload["snapshot"])
                self.assertIn("source_freshness", payload["snapshot"])


if __name__ == "__main__":
    unittest.main()
