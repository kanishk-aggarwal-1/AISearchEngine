import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.models import SearchRequest, SourceDoc
from backend.app.services.cache_service import CacheService
from backend.app.services.document_store import DocumentStore
import backend.app.main as main_module


class FakeRedisClient:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, ex=None):
        self.values[key] = value

    async def ping(self):
        return True

    async def aclose(self):
        return None


class PhaseOneTests(unittest.TestCase):
    def test_document_store_creates_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "phase1.db"
            store = DocumentStore(str(db_path))
            conn = store._connect()
            try:
                names = {row[1] for row in conn.execute("PRAGMA index_list(documents)").fetchall()}
            finally:
                conn.close()
            self.assertIn("idx_documents_category_published", names)
            self.assertIn("idx_documents_source", names)
            self.assertIn("idx_documents_inserted_at", names)

    def test_cache_service_generic_get_set(self):
        cache = CacheService()
        cache.client = FakeRedisClient()
        cache.enabled = True
        payload = {"ok": True, "value": 3}

        import asyncio
        asyncio.run(cache.set_json("headlines", "sports:4:7", payload, 10))
        raw = asyncio.run(cache.get("headlines", "sports:4:7"))
        self.assertEqual(json.loads(raw), payload)

    def test_no_result_search_returns_suggestions(self):
        with patch.object(main_module, "registry", SimpleNamespace(gather=AsyncMock(return_value=[]))), \
             patch.object(main_module, "enricher", SimpleNamespace(
                 enrich=lambda query, docs: docs,
                 contradictions=lambda docs: [],
                 claim_confidence=lambda docs, contradictions: 0.0,
                 timeline=lambda docs, max_points=8: [],
                 compare=lambda *args, **kwargs: None,
             )), \
             patch.object(main_module, "retriever", SimpleNamespace(
                 analyze_query=lambda query, categories: {"raw_query": query, "rewritten_query": query, "tokens": [], "intent": "mixed"},
                 rank_chunks=AsyncMock(return_value=([], {}, [])),
                 rank=AsyncMock(return_value=([], {}, [])),
             )), \
             patch.object(main_module, "vector_index", SimpleNamespace(search=AsyncMock(return_value=[]), ensure_collection=AsyncMock(), upsert_documents=AsyncMock(return_value=0), enabled=False)), \
             patch.object(main_module, "embedding_service", SimpleNamespace(embed=AsyncMock(return_value=[]), real_embeddings_enabled=False)), \
             patch.object(main_module, "explainer", SimpleNamespace(explain=AsyncMock(return_value={
                 "provider": "fallback",
                 "explanation": "No results found.",
                 "key_takeaways": ["No results found."],
                 "why_it_matters": "Broader retrieval often helps.",
                 "what_changed_last_week": "Not enough context.",
             }))), \
             patch.object(main_module, "cache", SimpleNamespace(get_query_cache=AsyncMock(return_value=None), put_query_cache=AsyncMock(), using_redis=False, ping=AsyncMock(return_value=False))), \
             patch.object(main_module, "store", SimpleNamespace(
                 get_profile=lambda user_id: SimpleNamespace(user_id=user_id, preferred_categories=[], explanation_mode="beginner"),
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
                    "query": "middle east conflict",
                    "categories": ["general"],
                    "user_id": "default",
                    "recency_days": 7,
                    "source_filter": ["BBC World"],
                    "source_type_filter": [],
                    "sort_by": "relevance",
                },
            )
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["sources"], [])
            self.assertTrue(payload["suggested_queries"])

    def test_headlines_endpoint_uses_cache_when_present(self):
        cached_payload = {"updated_at": "2026-01-01T00:00:00+00:00", "categories": {"tech": []}, "recency_days": 7}
        with patch.object(main_module, "cache", SimpleNamespace(
            get=AsyncMock(return_value=json.dumps(cached_payload)),
            set_json=AsyncMock(),
            get_query_cache=AsyncMock(return_value=None),
            put_query_cache=AsyncMock(),
            using_redis=True,
            ping=AsyncMock(return_value=True),
        )):
            client = TestClient(main_module.app)
            response = client.get("/headlines?per_category=4&recency_days=7")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), cached_payload)


if __name__ == "__main__":
    unittest.main()
