import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.models import SourceDoc, UserProfile
from backend.app.services.document_store import DocumentStore
from backend.app.services.explainer import ExplainerService
from backend.app.services.retriever import RetrieverService


class FakeEmbeddingService:
    real_embeddings_enabled = False

    async def embed(self, text: str):
        tokens = max(len((text or "").split()), 1)
        return [float(tokens), 0.5, 0.25]

    def cosine(self, a, b):
        return 0.6


class PhaseTwoTests(unittest.TestCase):
    def test_document_store_creates_and_searches_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "phase2.db"
            store = DocumentStore(str(db_path))
            doc = SourceDoc(
                title="AI agents coordinate software tasks",
                summary="AI agents can plan coding steps. They can also execute fixes and summarize results for developers.",
                url="https://example.com/agents",
                source="Example Tech",
                category="tech",
                published_at=datetime.now(timezone.utc),
                citation_snippet="AI agents can plan coding steps.",
            )
            store.upsert_documents([doc])

            conn = store._connect()
            try:
                chunk_count = conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0]
            finally:
                conn.close()

            self.assertGreaterEqual(chunk_count, 1)
            hits = store.search_chunks("AI agents coding", ["tech"], limit=5)
            self.assertTrue(hits)
            self.assertIn("AI agents", hits[0].text)

    def test_retriever_rewrites_broad_world_query(self):
        retriever = RetrieverService(FakeEmbeddingService())
        analysis = retriever.analyze_query("What is happening in middle east", ["general"])
        self.assertIn("world news", str(analysis["rewritten_query"]))
        self.assertNotIn("what", str(analysis["rewritten_query"]).lower())
        self.assertEqual(analysis["intent"], "general")

    def test_fallback_explanation_includes_inline_citations(self):
        explainer = ExplainerService()
        docs = [
            SourceDoc(
                title="Iran tensions affect oil markets",
                summary="Oil markets reacted sharply as regional tensions increased.",
                url="https://example.com/iran-oil",
                source="Example World",
                category="general",
                published_at=datetime.now(timezone.utc),
                freshness_label="2h ago",
                citation_snippet="Oil markets reacted sharply as regional tensions increased.",
            ),
            SourceDoc(
                title="Shipping routes disrupted in Hormuz",
                summary="Commercial shipping slowed after new threats near the strait.",
                url="https://example.com/hormuz",
                source="Example World",
                category="general",
                published_at=datetime.now(timezone.utc),
                freshness_label="4h ago",
                citation_snippet="Commercial shipping slowed after new threats near the strait.",
            ),
        ]
        payload = explainer._fallback_explanation("middle east conflict", docs, "beginner", [], "standard")
        self.assertIn("[1]", payload["explanation"])
        self.assertTrue(payload["key_takeaways"][0].startswith("[1]"))

    def test_search_uses_rewritten_query_for_registry_fetch(self):
        gather_mock = AsyncMock(return_value=[])
        with patch.object(main_module, "registry", SimpleNamespace(gather=gather_mock)), \
             patch.object(main_module, "enricher", SimpleNamespace(
                 enrich=lambda query, docs: docs,
                 contradictions=lambda docs: [],
                 claim_confidence=lambda docs, contradictions: 0.0,
                 timeline=lambda docs, max_points=8: [],
                 compare=lambda *args, **kwargs: None,
             )), \
             patch.object(main_module, "retriever", RetrieverService(FakeEmbeddingService())), \
             patch.object(main_module, "vector_index", SimpleNamespace(search=AsyncMock(return_value=[]), ensure_collection=AsyncMock(), upsert_documents=AsyncMock(return_value=0), enabled=False)), \
             patch.object(main_module, "embedding_service", FakeEmbeddingService()), \
             patch.object(main_module, "explainer", SimpleNamespace(explain=AsyncMock(return_value={
                 "provider": "fallback",
                 "explanation": "No results found.",
                 "key_takeaways": ["No results found."],
                 "why_it_matters": "Broader retrieval often helps.",
                 "what_changed_last_week": "Not enough context.",
             }))), \
             patch.object(main_module, "cache", SimpleNamespace(get_query_cache=AsyncMock(return_value=None), put_query_cache=AsyncMock(), using_redis=False, ping=AsyncMock(return_value=False))), \
             patch.object(main_module, "store", SimpleNamespace(
                 get_profile=lambda user_id: UserProfile(user_id=user_id, preferred_categories=[], explanation_mode="beginner"),
                 get_follows=lambda user_id: [],
                 get_query_cache=lambda *args, **kwargs: None,
                 all_recent_documents=lambda categories, limit=180: [],
                 embedding_map=lambda categories, limit=300: {},
                 chunk_embedding_map=lambda categories, limit=800: {},
                 search_chunks=lambda query, categories, limit=40: [],
                 put_query_cache=lambda *args, **kwargs: None,
                 save_context=lambda *args, **kwargs: None,
                 add_search_history=lambda *args, **kwargs: None,
                 upsert_documents=lambda *args, **kwargs: 0,
                 canonicalize_url=lambda url, source, title: f"{source}:{title}",
             )):
            client = TestClient(main_module.app)
            response = client.post(
                "/search",
                json={
                    "query": "What is happening in middle east",
                    "categories": ["general"],
                    "user_id": "default",
                },
            )
            self.assertEqual(response.status_code, 200)
            called_query = gather_mock.await_args.args[0]
            self.assertIn("world news", called_query)

    def test_retriever_diversifies_duplicate_sources(self):
        import asyncio

        retriever = RetrieverService(FakeEmbeddingService())
        profile = UserProfile(user_id="demo", preferred_categories=[], explanation_mode="beginner")
        docs = [
            SourceDoc(
                title="AI agents improve code reviews",
                summary="AI agents automate code review suggestions.",
                url="https://example.com/source-a-1",
                source="Source A",
                category="tech",
                published_at=datetime.now(timezone.utc),
            ),
            SourceDoc(
                title="AI agents reduce deployment toil",
                summary="AI agents automate deployment workflows.",
                url="https://example.com/source-a-2",
                source="Source A",
                category="tech",
                published_at=datetime.now(timezone.utc),
            ),
            SourceDoc(
                title="AI agents help incident response",
                summary="AI agents help production incident response teams.",
                url="https://example.com/source-b-1",
                source="Source B",
                category="tech",
                published_at=datetime.now(timezone.utc),
            ),
        ]

        ranked, _, _ = asyncio.run(
            retriever.rank(
                query="AI agents",
                docs=docs,
                top_k=3,
                profile=profile,
                follows=[],
            )
        )

        self.assertGreaterEqual(len(ranked), 2)
        self.assertNotEqual(ranked[0].source, ranked[1].source)


if __name__ == "__main__":
    unittest.main()
