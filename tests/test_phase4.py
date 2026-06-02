import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.models import ResearchMetadata, SourceDoc, SportsMetadata
from backend.app.services.document_store import DocumentStore
from scripts.run_eval import ndcg_at_k, recall_at_k, reciprocal_rank


class PhaseFourTests(unittest.TestCase):
    def test_eval_metric_helpers(self):
        ranked = ["a", "b", "c"]
        relevant = {"a", "c"}
        gains = {"a": 3, "c": 2}
        self.assertEqual(recall_at_k(ranked, relevant, 2), 0.5)
        self.assertEqual(reciprocal_rank(ranked, relevant), 1.0)
        self.assertGreater(ndcg_at_k(ranked, gains, 3), 0.9)

    def test_trending_endpoint_returns_topics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase4_trending.db"))
            store.upsert_documents(
                [
                    SourceDoc(
                        title="OpenAI ships new coding agent",
                        summary="OpenAI released a coding agent for software teams.",
                        url="https://example.com/openai-agent",
                        source="Example Tech",
                        category="tech",
                        published_at=datetime.now(timezone.utc),
                        entity_tags=["OpenAI", "Agent"],
                    )
                ]
            )
            from types import SimpleNamespace
            fake_cache = SimpleNamespace(using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False))
            with patch("backend.app.routers.browse.store", store), \
                 patch("backend.app.main.cache", fake_cache), \
                 patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)):
                client = TestClient(main_module.app)
                response = client.get("/v1/trending?category=tech&recency_days=7")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["topics"])

    def test_sports_team_page_filters_team_docs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase4_sports.db"))
            store.upsert_documents(
                [
                    SourceDoc(
                        title="Lakers beat Celtics",
                        summary="Lakers secured a road win over the Celtics.",
                        url="https://example.com/lakers",
                        source="Example Sports",
                        category="sports",
                        published_at=datetime.now(timezone.utc),
                        sports_metadata=SportsMetadata(team="Lakers", opponent="Celtics", league="NBA", scoreline="110-104"),
                    )
                ]
            )
            fake_cache = SimpleNamespace(using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False))
            with patch("backend.app.routers.sports.store", store), \
                 patch("backend.app.main.cache", fake_cache), \
                 patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)):
                client = TestClient(main_module.app)
                response = client.get("/v1/sports/team/Lakers?recency_days=14")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["team"], "Lakers")
                self.assertTrue(response.json()["latest"])

    def test_research_paper_page_returns_related_papers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = DocumentStore(str(Path(tmpdir) / "phase4_research.db"))
            store.upsert_documents(
                [
                    SourceDoc(
                        title="Agentic Planning for Software Tasks",
                        summary="A paper about agents and planning for software tasks.",
                        url="https://arxiv.org/abs/1234.5678",
                        source="arXiv",
                        category="research",
                        published_at=datetime.now(timezone.utc),
                        research_metadata=ResearchMetadata(theme="AI Agents", authors=["Alice"], paper_id="1234.5678"),
                    ),
                    SourceDoc(
                        title="Tool-Using Agents for Coding",
                        summary="Another paper about agentic coding systems.",
                        url="https://arxiv.org/abs/9999.0001",
                        source="arXiv",
                        category="research",
                        published_at=datetime.now(timezone.utc),
                        research_metadata=ResearchMetadata(theme="AI Agents", authors=["Bob"], paper_id="9999.0001"),
                    ),
                ]
            )
            stub_explainer = type("E", (), {"explain": AsyncMock(return_value={
                "provider": "fallback", "explanation": "Summary",
                "key_takeaways": ["One"], "why_it_matters": "Why", "what_changed_last_week": "Week",
            })})()
            fake_cache = SimpleNamespace(using_redis=False, incr=AsyncMock(return_value=1), ping=AsyncMock(return_value=False))
            with patch("backend.app.routers.research.store", store), \
                 patch("backend.app.routers.research.explainer", stub_explainer), \
                 patch("backend.app.main.cache", fake_cache), \
                 patch("backend.app.main.embedding_service", SimpleNamespace(real_embeddings_enabled=True)):
                client = TestClient(main_module.app)
                response = client.get("/v1/research/paper/1234.5678")
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["paper"]["research_metadata"]["paper_id"], "1234.5678")
                self.assertTrue(payload["related_papers"])


if __name__ == "__main__":
    unittest.main()
