"""
Feature coverage tests for all API routes.

Tests are organized by router. Each class covers one feature area.
All tests use a real in-memory SQLite DocumentStore — no DB mocking.
HTTP layer is exercised via FastAPI TestClient.

Coverage map:
  Browse:   headlines (all / by-category), category page, trending, topic
  Search:   basic search, streaming, feedback, conversations, compare, follow-up, share
  Users:    profile, follows, alerts, alert-delivery, bookmarks, history, saved-sessions
  Auth:     account update, password change, MFA, email change, export, session revocation, delete
  Admin:    dashboard, sources, ingestion-runs, reingest (admin-gated)
"""

import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.models import SourceDoc
from backend.app.services.document_store import DocumentStore

# ── Test-double infrastructure ───────────────────────────────────────────────


def _make_store(tmpdir: str) -> DocumentStore:
    return DocumentStore(str(Path(tmpdir) / "features.db"))


def _source_doc(title: str, category: str = "tech", url: str | None = None) -> SourceDoc:
    return SourceDoc(
        title=title,
        summary=f"Summary of {title}",
        url=url or f"https://example.com/{title.lower().replace(' ', '-')}",
        source="TestSource",
        category=category,
        published_at=None,
    )


@contextmanager
def _client(store: DocumentStore, *, admin_email: str | None = None):
    """
    Yield a TestClient with all container singletons replaced by test doubles.
    Patches are scoped to one test; nothing leaks between tests.
    """
    fake_cache = SimpleNamespace(
        using_redis=False,
        get=AsyncMock(return_value=None),
        set_json=AsyncMock(),
        incr=AsyncMock(return_value=1),
        ping=AsyncMock(return_value=False),
        delete=AsyncMock(),
        get_int=AsyncMock(return_value=None),
        get_query_cache=AsyncMock(return_value=None),
        put_query_cache=AsyncMock(),
        set_query_cache=AsyncMock(),
    )
    fake_embedding = SimpleNamespace(
        real_embeddings_enabled=False,
        embed=AsyncMock(return_value=[0.0] * 64),
    )
    fake_registry = SimpleNamespace(
        gather=AsyncMock(return_value=[]),
        get_source_statuses=MagicMock(return_value=[]),
    )
    fake_enricher = SimpleNamespace(
        enrich=lambda q, docs: docs,
        contradictions=MagicMock(return_value=[]),
        claim_confidence=MagicMock(return_value=0.8),
        timeline=MagicMock(return_value=[]),
        compare=MagicMock(return_value=__import__("backend.app.models", fromlist=["ComparisonResult"]).ComparisonResult(
            baseline_query="", compared_query="", baseline_summary="", compared_summary="",
            overlap_topics=[], divergence_topics=[],
        )),
    )
    fake_explainer = SimpleNamespace(
        explain=AsyncMock(return_value={
            "explanation": "test explanation",
            "key_takeaways": [],
            "why_it_matters": "",
            "what_changed_last_week": "",
            "suggested_queries": [],
            "provider": "fallback",
        }),
        followup=AsyncMock(return_value=("test answer", [])),
    )
    fake_email = SimpleNamespace(send=AsyncMock(return_value=False))
    fake_metrics = SimpleNamespace(
        inc=MagicMock(),
        observe=MagicMock(),
        summary=MagicMock(return_value={"total_searches": 0}),
        snapshot=MagicMock(return_value={"total_searches": 0, "avg_latency_ms": 0.0}),
    )

    fake_query_analysis = {
        "rewritten_query": "test",
        "is_question": False,
        "entities": [],
        "topics": [],
        "time_filter": None,
        "suggested_categories": [],
    }
    fake_retriever = SimpleNamespace(
        search=AsyncMock(return_value=[]),
        analyze_query=MagicMock(return_value=fake_query_analysis),
        rank=AsyncMock(return_value=([], {}, [0.0] * 64)),
        rank_chunks=AsyncMock(return_value=([], {}, [0.0] * 64)),
    )
    fake_vector = SimpleNamespace(search=AsyncMock(return_value=[]))
    fake_metrics_store = SimpleNamespace(record_search=AsyncMock())
    fake_ingestion = SimpleNamespace(
        gather=AsyncMock(return_value=[]),
        run_sources=AsyncMock(return_value=0),
        ingest_event=AsyncMock(return_value=0),
    )
    fake_logger = MagicMock()

    patches = [
        patch("backend.app.routers.auth.store", store),
        patch("backend.app.routers.auth.email_service", fake_email),
        patch("backend.app.routers.users.store", store),
        patch("backend.app.routers.browse.store", store),
        patch("backend.app.routers.browse.cache", fake_cache),
        patch("backend.app.routers.browse.registry", fake_registry),
        patch("backend.app.routers.browse.enricher", fake_enricher),
        patch("backend.app.routers.browse.metrics", fake_metrics),
        patch("backend.app.routers.search.store", store),
        patch("backend.app.routers.search.cache", fake_cache),
        patch("backend.app.routers.search.metrics", fake_metrics),
        patch("backend.app.routers.search.registry", fake_registry),
        patch("backend.app.routers.search.retriever", fake_retriever),
        patch("backend.app.routers.search.vector_index", fake_vector),
        patch("backend.app.routers.search.enricher", fake_enricher),
        patch("backend.app.routers.search.explainer", fake_explainer),
        patch("backend.app.routers.search.embedding_service", fake_embedding),
        patch("backend.app.routers.search.metrics_store", fake_metrics_store),
        patch("backend.app.routers.search.logger", fake_logger),
        patch("backend.app.routers.admin.store", store),
        patch("backend.app.routers.admin.metrics", fake_metrics),
        patch("backend.app.routers.admin.ingestion", fake_ingestion),
        patch("backend.app.dependencies.store", store),
        patch("backend.app.main.cache", fake_cache),
        patch("backend.app.main.embedding_service", fake_embedding),
        # Bypass rate limiter so bulk test runs don't hit 429
        patch("backend.app.main._is_rate_limited", AsyncMock(return_value=False)),
    ]
    admin_patch = (
        [patch("backend.app.services.document_store.settings.bootstrap_admin_email", admin_email)]
        if admin_email
        else []
    )
    with tempfile.TemporaryDirectory():
        # Clear module-level rate-limit state carried over from previous tests
        main_module._RATE_LIMIT_BUCKETS.clear()
        ctx = [p.start() for p in patches + admin_patch]
        try:
            yield TestClient(main_module.app, raise_server_exceptions=False)
        finally:
            for p in patches + admin_patch:
                p.stop()
            del ctx


def _register_and_login(client: TestClient, email: str = "user@example.com", password: str = "StrongPass1") -> str:
    """Register, login, return Bearer token."""
    client.post("/v1/auth/register", json={"email": email, "password": password, "display_name": "Test"})
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    return r.json()["token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Browse ───────────────────────────────────────────────────────────────────


class TestBrowse(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_headlines_returns_all_categories(self):
        with _client(self.store) as client:
            r = client.get("/v1/headlines?per_category=2&recency_days=7")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("categories", body)
            self.assertIn("updated_at", body)
            # Four categories always present even if empty
            for cat in ("tech", "research", "sports", "general"):
                self.assertIn(cat, body["categories"])

    def test_headlines_per_category_clamped(self):
        with _client(self.store) as client:
            # per_category > 8 is clamped to 8
            r = client.get("/v1/headlines?per_category=100")
            self.assertEqual(r.status_code, 200)

    def test_headlines_by_category_valid(self):
        with _client(self.store) as client:
            r = client.get("/v1/headlines/tech")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("headlines", body)
            self.assertIn("category", body)

    def test_headlines_by_category_invalid(self):
        with _client(self.store) as client:
            r = client.get("/v1/headlines/nonexistent")
            self.assertEqual(r.status_code, 422)

    def test_trending_returns_topics(self):
        with _client(self.store) as client:
            r = client.get("/v1/trending")
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("topics", body)
            self.assertIn("categories", body)

    def test_topic_endpoint(self):
        with _client(self.store) as client:
            r = client.get("/v1/topic/artificial-intelligence")
            self.assertEqual(r.status_code, 200)

    def test_category_page(self):
        with _client(self.store) as client:
            r = client.get("/v1/category/tech")
            self.assertEqual(r.status_code, 200)

    def test_category_page_invalid_category(self):
        with _client(self.store) as client:
            r = client.get("/v1/category/invalid")
            self.assertEqual(r.status_code, 422)


# ── Search ───────────────────────────────────────────────────────────────────


class TestSearch(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _seed(self, *docs: SourceDoc):
        self.store.upsert_documents(list(docs))

    def test_basic_search_unauthenticated(self):
        self._seed(_source_doc("AI breakthrough", "tech", "https://example.com/ai"))
        with _client(self.store) as client:
            r = client.post("/v1/search", json={"query": "AI", "user_id": "default"})
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("sources", body)
            self.assertIn("context_id", body)

    def test_search_authenticated_uses_session_user(self):
        self._seed(_source_doc("GPU news", "tech"))
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            r = client.post(
                "/v1/search",
                json={"query": "GPU", "user_id": me["user_id"]},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)

    def test_search_authenticated_cannot_impersonate(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.post(
                "/v1/search",
                json={"query": "test", "user_id": "some-other-user"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 403)

    def test_search_with_category_filter(self):
        self._seed(
            _source_doc("Tech article", "tech"),
            _source_doc("Sports article", "sports"),
        )
        with _client(self.store) as client:
            r = client.post("/v1/search", json={"query": "article", "categories": ["tech"], "user_id": "default"})
            self.assertEqual(r.status_code, 200)

    def test_search_with_sort_by_latest(self):
        with _client(self.store) as client:
            r = client.post("/v1/search", json={"query": "test", "sort_by": "latest", "user_id": "default"})
            self.assertEqual(r.status_code, 200)

    def test_search_streaming_endpoint_exists(self):
        with _client(self.store) as client:
            r = client.post("/v1/search/stream", json={"query": "test", "user_id": "default"})
            # Streaming responds 200 (even if empty)
            self.assertIn(r.status_code, (200, 204))

    def test_search_feedback_accepted(self):
        self._seed(_source_doc("Feedback test", "tech"))
        with _client(self.store) as client:
            # First create a context
            search = client.post("/v1/search", json={"query": "Feedback", "user_id": "default"})
            ctx_id = search.json()["context_id"]
            r = client.post("/v1/search/feedback", json={"context_id": ctx_id, "helpful": True, "comment": "Great"})
            self.assertEqual(r.status_code, 200)

    def test_compare_two_queries(self):
        self._seed(
            _source_doc("OpenAI article", "tech"),
            _source_doc("Anthropic article", "tech"),
        )
        with _client(self.store) as client:
            r = client.post(
                "/v1/compare",
                json={"query_a": "OpenAI", "query_b": "Anthropic", "user_id": "default"},
            )
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("comparison", body)

    def test_follow_up_question(self):
        self._seed(_source_doc("LLM scaling laws", "research"))
        with _client(self.store) as client:
            search = client.post("/v1/search", json={"query": "LLM scaling", "user_id": "default"})
            ctx_id = search.json()["context_id"]
            r = client.post(
                "/v1/followup",
                json={"context_id": ctx_id, "question": "What are the implications?", "user_id": "default"},
            )
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("response", body)
            self.assertIn("context_id", body)


# ── Conversations ─────────────────────────────────────────────────────────────


class TestConversations(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_create_and_list_conversations(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # Create — ConversationCreateRequest has context_id and title, no user_id
            # Context must be owned by this user, so search as authenticated user
            search = client.post("/v1/search", json={"query": "conversation test", "user_id": uid}, headers=_auth(token))
            ctx_id = search.json()["context_id"]
            r = client.post(
                "/v1/conversations",
                json={"context_id": ctx_id, "title": "My first conversation"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)
            conv_id = r.json()["conversation_id"]
            # List
            r2 = client.get("/v1/conversations", headers=_auth(token))
            self.assertEqual(r2.status_code, 200)
            ids = [c["conversation_id"] for c in r2.json()]
            self.assertIn(conv_id, ids)

    def test_add_message_to_conversation(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            search = client.post("/v1/search", json={"query": "msg test", "user_id": uid}, headers=_auth(token))
            ctx_id = search.json()["context_id"]
            conv = client.post(
                "/v1/conversations",
                json={"context_id": ctx_id, "title": "Test"},
                headers=_auth(token),
            ).json()
            r = client.post(
                f"/v1/conversations/{conv['conversation_id']}/messages",
                json={"question": "Hello"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)


# ── Share ─────────────────────────────────────────────────────────────────────


class TestShare(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)
        doc = _source_doc("Shareable doc", "tech")
        self.store.upsert_documents([doc])

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_share_and_retrieve_context(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            search = client.post("/v1/search", json={"query": "Shareable", "user_id": uid}, headers=_auth(token))
            ctx_id = search.json()["context_id"]
            r = client.post(f"/v1/contexts/{ctx_id}/share", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            share_token = r.json()["share_token"]
            # Retrieve shared context
            r2 = client.get(f"/v1/shared/{share_token}")
            self.assertEqual(r2.status_code, 200)

    def test_retrieve_invalid_share_token(self):
        with _client(self.store) as client:
            r = client.get("/v1/shared/nonexistent-token")
            self.assertEqual(r.status_code, 404)


# ── Users – Profile ───────────────────────────────────────────────────────────


class TestUserProfile(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_and_update_profile(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            r = client.get(f"/v1/users/{uid}/profile", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["user_id"], uid)
            # Update — explanation_mode must be one of: tldr, beginner, deep, analyst
            r2 = client.put(
                f"/v1/users/{uid}/profile",
                json={"user_id": uid, "preferred_categories": ["tech"], "explanation_mode": "tldr"},
                headers=_auth(token),
            )
            self.assertEqual(r2.status_code, 200)
            self.assertIn("tech", r2.json()["preferred_categories"])

    def test_profile_requires_auth(self):
        with _client(self.store) as client:
            r = client.get("/v1/users/some-id/profile")
            self.assertEqual(r.status_code, 401)


# ── Users – Follows ───────────────────────────────────────────────────────────


class TestFollows(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_add_follow_list_remove(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # Add — FollowRequest requires user_id
            r = client.post(f"/v1/users/{uid}/follows", json={"user_id": uid, "entity": "OpenAI"}, headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            # List
            r2 = client.get(f"/v1/users/{uid}/follows", headers=_auth(token))
            self.assertIn("OpenAI", r2.json()["entities"])
            # Remove
            r3 = client.delete(f"/v1/users/{uid}/follows/OpenAI", headers=_auth(token))
            self.assertEqual(r3.status_code, 200)
            r4 = client.get(f"/v1/users/{uid}/follows", headers=_auth(token))
            self.assertNotIn("OpenAI", r4.json()["entities"])

    def test_watchlist_endpoint(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.get("/v1/me/watchlist", headers=_auth(token))
            self.assertEqual(r.status_code, 200)


# ── Users – Alerts ────────────────────────────────────────────────────────────


class TestAlerts(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_create_list_update_delete_alert(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # Create — AlertRule requires user_id
            r = client.post(
                f"/v1/users/{uid}/alerts",
                json={"user_id": uid, "query": "AI safety", "categories": ["research"]},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)
            alert_id = r.json()["id"]
            # List
            r2 = client.get(f"/v1/users/{uid}/alerts", headers=_auth(token))
            self.assertEqual(len(r2.json()), 1)
            # Update — AlertRule requires user_id
            r3 = client.put(
                f"/v1/users/{uid}/alerts/{alert_id}",
                json={"user_id": uid, "query": "AI alignment", "categories": ["research"], "enabled": False},
                headers=_auth(token),
            )
            self.assertEqual(r3.status_code, 200)
            self.assertFalse(r3.json()["enabled"])
            # Delete
            r4 = client.delete(f"/v1/users/{uid}/alerts/{alert_id}", headers=_auth(token))
            self.assertEqual(r4.status_code, 200)
            r5 = client.get(f"/v1/users/{uid}/alerts", headers=_auth(token))
            self.assertEqual(r5.json(), [])


# ── Users – Alert Delivery ────────────────────────────────────────────────────


class TestAlertDelivery(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_get_and_save_delivery_settings(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            r = client.get(f"/v1/users/{uid}/alert-delivery", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            # AlertDeliverySettings requires user_id
            r2 = client.put(
                f"/v1/users/{uid}/alert-delivery",
                json={"user_id": uid, "webhook_url": "", "digest_mode": "daily", "enabled": False},
                headers=_auth(token),
            )
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.json()["digest_mode"], "daily")


# ── Users – Bookmarks ─────────────────────────────────────────────────────────


class TestBookmarks(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_bookmark_crud(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # BookmarkRequest.source is a SourceDoc; user_id is also required
            source_doc = {
                "title": "Interesting paper",
                "summary": "A great paper",
                "url": "https://example.com/paper",
                "source": "ArXiv",
                "category": "research",
            }
            r = client.post(
                f"/v1/users/{uid}/bookmarks",
                json={"user_id": uid, "source": source_doc, "folder": "research"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)
            bm_id = r.json()["id"]
            # List
            r2 = client.get(f"/v1/users/{uid}/bookmarks", headers=_auth(token))
            self.assertEqual(len(r2.json()), 1)
            # Update
            r3 = client.put(
                f"/v1/users/{uid}/bookmarks/{bm_id}",
                json={"notes": "Must read", "tags": ["llm"]},
                headers=_auth(token),
            )
            self.assertEqual(r3.status_code, 200)
            self.assertEqual(r3.json()["notes"], "Must read")
            # Delete
            r4 = client.delete(f"/v1/users/{uid}/bookmarks/{bm_id}", headers=_auth(token))
            self.assertEqual(r4.status_code, 200)
            r5 = client.get(f"/v1/users/{uid}/bookmarks", headers=_auth(token))
            self.assertEqual(r5.json(), [])


# ── Users – History & Saved Sessions ─────────────────────────────────────────


class TestHistoryAndSessions(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_search_history_populated_and_cleared(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # Run authenticated search to populate history
            client.post("/v1/search", json={"query": "history test", "user_id": uid}, headers=_auth(token))
            r = client.get("/v1/me/search-history", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertGreater(len(r.json()), 0)
            # Delete single entry
            history_id = r.json()[0]["id"]
            r2 = client.delete(f"/v1/me/search-history/{history_id}", headers=_auth(token))
            self.assertEqual(r2.status_code, 200)
            # Clear all
            r3 = client.delete("/v1/me/search-history", headers=_auth(token))
            self.assertEqual(r3.status_code, 200)
            r4 = client.get("/v1/me/search-history", headers=_auth(token))
            self.assertEqual(r4.json(), [])

    def test_saved_sessions_lifecycle(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            me = client.get("/v1/auth/me", headers=_auth(token)).json()
            uid = me["user_id"]
            # Create a context to save
            search = client.post("/v1/search", json={"query": "save me", "user_id": uid}, headers=_auth(token))
            ctx_id = search.json()["context_id"]
            # Save session
            r = client.post(
                f"/v1/me/saved-sessions/{ctx_id}",
                json={"label": "My saved session"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)
            # List
            r2 = client.get("/v1/me/saved-sessions", headers=_auth(token))
            session_id = r2.json()[0]["id"]
            self.assertEqual(r2.json()[0]["label"], "My saved session")
            # Retrieve context
            r3 = client.get(f"/v1/me/saved-sessions/{ctx_id}/context", headers=_auth(token))
            self.assertEqual(r3.status_code, 200)
            # Delete
            r4 = client.delete(f"/v1/me/saved-sessions/{session_id}", headers=_auth(token))
            self.assertEqual(r4.status_code, 200)
            r5 = client.get("/v1/me/saved-sessions", headers=_auth(token))
            self.assertEqual(r5.json(), [])


# ── Auth – Extended Account Management ───────────────────────────────────────


class TestAccountManagement(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_update_account_display_name(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.put("/v1/auth/account", json={"display_name": "New Name"}, headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["display_name"], "New Name")

    def test_change_password(self):
        with _client(self.store) as client:
            token = _register_and_login(client, password="OldPassword1")
            r = client.post(
                "/v1/auth/change-password",
                json={"current_password": "OldPassword1", "new_password": "NewPassword2"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)
            # Old password no longer works
            r2 = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "OldPassword1"})
            self.assertEqual(r2.status_code, 401)
            # New password works
            r3 = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "NewPassword2"})
            self.assertEqual(r3.status_code, 200)

    def test_change_password_wrong_current(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.post(
                "/v1/auth/change-password",
                json={"current_password": "WrongPassword1", "new_password": "NewPassword2"},
                headers=_auth(token),
            )
            # Wrong current password → 400 (Bad Request) or 401
            self.assertIn(r.status_code, (400, 401))

    def test_revoke_other_sessions(self):
        with _client(self.store) as client:
            token1 = _register_and_login(client)
            # Second login creates a second session
            r = client.post("/v1/auth/login", json={"email": "user@example.com", "password": "StrongPass1"})
            token2 = r.json()["token"]
            # Revoke other sessions from token1's perspective
            r2 = client.post("/v1/auth/revoke-other-sessions", headers=_auth(token1))
            self.assertEqual(r2.status_code, 200)
            # token2 should now be invalid
            r3 = client.get("/v1/auth/me", headers=_auth(token2))
            self.assertEqual(r3.status_code, 401)
            # token1 is still valid
            r4 = client.get("/v1/auth/me", headers=_auth(token1))
            self.assertEqual(r4.status_code, 200)

    def test_export_user_data(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.get("/v1/auth/export", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            body = r.json()
            # Export includes: account, profile, follows, search_history, bookmarks, etc.
            self.assertIn("account", body)
            self.assertIn("exported_at", body)

    def test_delete_account(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.delete("/v1/auth/account", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            # Token is now invalid
            r2 = client.get("/v1/auth/me", headers=_auth(token))
            self.assertEqual(r2.status_code, 401)

    def test_mfa_setup_and_enable(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.post("/v1/auth/mfa/setup", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("secret", body)
            # Returns provisioning_uri (OTP URI) not totp_uri
            self.assertIn("provisioning_uri", body)

    def test_request_email_change(self):
        with _client(self.store) as client:
            token = _register_and_login(client)
            r = client.post(
                "/v1/auth/request-email-change",
                json={"new_email": "new@example.com", "password": "StrongPass1"},
                headers=_auth(token),
            )
            self.assertEqual(r.status_code, 200)


# ── Admin ─────────────────────────────────────────────────────────────────────


class TestAdmin(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.store = _make_store(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _admin_token(self, client: TestClient) -> str:
        return _register_and_login(client, email="admin@example.com")

    def test_dashboard_requires_admin(self):
        with _client(self.store) as client:
            # Non-admin gets 403
            token = _register_and_login(client, email="regular@example.com")
            r = client.get("/v1/admin/dashboard", headers=_auth(token))
            self.assertEqual(r.status_code, 403)

    def test_dashboard_accessible_by_admin(self):
        with _client(self.store, admin_email="admin@example.com") as client:
            token = self._admin_token(client)
            r = client.get("/v1/admin/dashboard", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertIn("snapshot", body)
            self.assertIn("metrics", body)

    def test_sources_list_admin_only(self):
        with _client(self.store, admin_email="admin@example.com") as client:
            token = self._admin_token(client)
            r = client.get("/v1/admin/sources", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertIsInstance(r.json(), list)

    def test_toggle_source_enabled(self):
        with _client(self.store, admin_email="admin@example.com") as client:
            token = self._admin_token(client)
            # First list sources to find a name
            sources = client.get("/v1/admin/sources", headers=_auth(token)).json()
            if not sources:
                self.skipTest("No sources configured in test environment")
            name = sources[0]["source_name"]
            r = client.put(f"/v1/admin/sources/{name}", json={"enabled": False}, headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertFalse(r.json()["enabled"])

    def test_ingestion_runs_returns_list(self):
        with _client(self.store, admin_email="admin@example.com") as client:
            token = self._admin_token(client)
            r = client.get("/v1/admin/ingestion-runs", headers=_auth(token))
            self.assertEqual(r.status_code, 200)
            self.assertIsInstance(r.json(), list)

    def test_reingest_triggers_background_job(self):
        with _client(self.store, admin_email="admin@example.com") as client:
            token = self._admin_token(client)
            r = client.post("/v1/admin/reingest", json={"topic": "AI", "categories": ["tech"]}, headers=_auth(token))
            self.assertIn(r.status_code, (200, 202))

    def test_unauthenticated_admin_rejected(self):
        with _client(self.store) as client:
            r = client.get("/v1/admin/dashboard")
            self.assertEqual(r.status_code, 401)
