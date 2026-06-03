"""
Postgres store contract test.

PostgresDocumentStore inherits DocumentStore and overrides only the connection
layer plus ~12 methods. The other ~48 methods run SQLite-authored SQL through a
naive '?' -> '%s' translation. This test exercises those inherited methods
against a REAL Postgres database so SQLite-isms surface in CI instead of in
production.

Skipped automatically unless TEST_DATABASE_URL (a postgresql:// URL) is set,
so the normal SQLite test run is unaffected.
"""
import os
import unittest
from datetime import datetime, timezone

from backend.app.models import (
    AlertDeliverySettings,
    AlertRule,
    SourceDoc,
    UserProfile,
)

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")
_IS_POSTGRES = TEST_DB_URL.strip().lower().startswith(("postgres://", "postgresql://"))


@unittest.skipUnless(_IS_POSTGRES, "TEST_DATABASE_URL not set to a postgres URL")
class PostgresStoreContractTests(unittest.TestCase):
    """Run the full store contract against real Postgres."""

    @classmethod
    def setUpClass(cls):
        from backend.app.services.postgres_store import PostgresDocumentStore

        cls.store = PostgresDocumentStore(TEST_DB_URL)
        # Schema is created by Alembic migrations in the CI step before this runs.

    def _doc(self, url: str, title: str, category: str = "tech") -> SourceDoc:
        return SourceDoc(
            title=title,
            summary=f"{title} — summary body with enough words to chunk properly.",
            url=url,
            source="Example Source",
            category=category,
            published_at=datetime.now(timezone.utc),
            entity_tags=["OpenAI", "Agents"],
        )

    # ── Auth (get_user_by_token is INHERITED — the auth hot path) ───────────
    def test_auth_full_flow(self):
        import secrets

        email = f"pg_{secrets.token_hex(4)}@example.com"
        user = self.store.create_user(email, "Strongpass123", "PG User")
        self.assertTrue(user.user_id)

        session = self.store.authenticate_user(email, "Strongpass123")
        self.assertIsNotNone(session)

        # get_user_by_token is inherited — must work on Postgres
        looked_up = self.store.get_user_by_token(session.token)
        self.assertIsNotNone(looked_up)
        self.assertEqual(looked_up.email, email)

        # logout (inherited)
        self.store.logout_session(session.token)
        self.assertIsNone(self.store.get_user_by_token(session.token))

    def test_email_verification_flow(self):
        import secrets

        email = f"pg_{secrets.token_hex(4)}@example.com"
        user = self.store.create_user(email, "Strongpass123", "Verify User")
        token, _ = self.store.issue_verification_token(user.user_id)
        verified = self.store.verify_email(token)
        self.assertIsNotNone(verified)
        self.assertTrue(verified.email_verified)

    def test_password_reset_flow(self):
        import secrets

        email = f"pg_{secrets.token_hex(4)}@example.com"
        self.store.create_user(email, "Strongpass123", "Reset User")
        token, _ = self.store.issue_password_reset_token(email)
        result = self.store.reset_password(token, "Newstrongpass456")
        self.assertIsNotNone(result)
        self.assertIsNotNone(self.store.authenticate_user(email, "Newstrongpass456"))

    # ── Documents (upsert/search/chunks all inherited) ──────────────────────
    def test_document_upsert_and_search(self):
        import secrets

        suffix = secrets.token_hex(4)
        docs = [
            self._doc(f"https://ex.com/{suffix}-a", f"AI agents ship code {suffix}"),
            self._doc(f"https://ex.com/{suffix}-b", f"Machine learning models {suffix}"),
        ]
        inserted = self.store.upsert_documents(docs)
        self.assertEqual(inserted, 2)

        found = self.store.search_documents("agents", ["tech"], limit=10)
        self.assertTrue(any(suffix in d.title for d in found))

        recent = self.store.all_recent_documents(["tech"], limit=50)
        self.assertTrue(recent)

        chunks = self.store.search_chunks("agents code", ["tech"], limit=10)
        self.assertTrue(chunks)

    def test_query_cache(self):
        import secrets

        key = f"qk_{secrets.token_hex(4)}"
        self.store.put_query_cache(key, {"answer": "cached"})
        cached = self.store.get_query_cache(key)
        self.assertIsNotNone(cached)

    # ── Personalization (follows/bookmarks/alerts/profile) ──────────────────
    def test_profile_and_follows(self):
        import secrets

        user = self.store.create_user(f"pg_{secrets.token_hex(4)}@example.com", "Strongpass123", "P")
        self.store.upsert_profile(
            UserProfile(user_id=user.user_id, preferred_categories=["tech"], explanation_mode="analyst")
        )
        profile = self.store.get_profile(user.user_id)
        self.assertEqual(profile.explanation_mode, "analyst")

        self.store.add_follow(user.user_id, "OpenAI")
        follows = self.store.get_follows(user.user_id)
        self.assertIn("OpenAI", follows)

    def test_bookmarks(self):
        import secrets

        user = self.store.create_user(f"pg_{secrets.token_hex(4)}@example.com", "Strongpass123", "B")
        doc = self._doc(f"https://ex.com/bm-{secrets.token_hex(4)}", "Bookmark me")
        self.store.add_bookmark(user.user_id, doc)
        bookmarks = self.store.get_bookmarks(user.user_id)
        self.assertTrue(bookmarks)
        self.assertEqual(bookmarks[0].source.url, doc.url)
        self.store.delete_bookmark(user.user_id, bookmarks[0].id)
        self.assertEqual(self.store.get_bookmarks(user.user_id), [])

    def test_alerts(self):
        import secrets

        user = self.store.create_user(f"pg_{secrets.token_hex(4)}@example.com", "Strongpass123", "A")
        self.store.add_alert(AlertRule(user_id=user.user_id, query="AI agents", categories=["tech"], enabled=True))
        alerts = self.store.get_alerts(user.user_id)
        self.assertTrue(alerts)
        self.store.upsert_alert_delivery(
            AlertDeliverySettings(user_id=user.user_id, webhook_url="https://ex.com/wh", digest_mode="instant", enabled=True)
        )
        delivery = self.store.get_alert_delivery(user.user_id)
        self.assertIsNotNone(delivery)
        enabled = self.store.get_enabled_alerts()
        self.assertTrue(enabled)

    # ── History / sessions / context ────────────────────────────────────────
    def test_history_sessions_context(self):
        import secrets

        user = self.store.create_user(f"pg_{secrets.token_hex(4)}@example.com", "Strongpass123", "H")
        ctx = f"ctx_{secrets.token_hex(4)}"
        doc = self._doc(f"https://ex.com/ctx-{secrets.token_hex(4)}", "Context doc")
        self.store.save_context(ctx, user.user_id, "ai agents", [doc])
        self.store.add_search_history(user.user_id, "ai agents", ["tech"], ctx)
        self.store.save_session(user.user_id, ctx, "My session")

        self.assertTrue(self.store.get_search_history(user.user_id))
        self.assertTrue(self.store.get_saved_sessions(user.user_id))
        self.assertIsNotNone(self.store.get_context(ctx, user.user_id))

    # ── Source health / ingestion runs ──────────────────────────────────────
    def test_source_health_and_ingestion(self):
        self.store.record_source_result("PG Source", "tech", 3, error="", latency_ms=100.0)
        statuses = self.store.get_source_statuses(source_name="PG Source")
        self.assertTrue(statuses)
        summary = self.store.source_freshness_summary()
        self.assertIn("healthy_sources", summary)

        run_id = self.store.create_ingestion_run("query", query="ai", categories=["tech"])
        self.store.finish_ingestion_run(run_id, "completed", inserted_count=2, source_count=1)
        runs = self.store.recent_ingestion_runs(limit=5)
        self.assertTrue(runs)

    def test_admin_snapshot(self):
        snapshot = self.store.admin_snapshot()
        self.assertIsInstance(snapshot, dict)

    def test_ping(self):
        self.assertTrue(self.store.ping())


if __name__ == "__main__":
    unittest.main()
