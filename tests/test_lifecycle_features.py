import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from backend.app.models import AlertRule, SourceDoc
from backend.app.routers.search import _apply_search_filters
from backend.app.models import SearchRequest
from backend.app.services.document_store import DocumentStore


def _store(tmpdir: str) -> DocumentStore:
    return DocumentStore(str(Path(tmpdir) / "lifecycle.db"))


def test_follow_and_alert_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _store(tmpdir)
        user = store.create_user("member@example.com", "StrongPassword123", "Member")
        store.add_follow(user.user_id, "OpenAI")
        assert store.remove_follow(user.user_id, "OpenAI") == []
        alert = store.add_alert(AlertRule(user_id=user.user_id, query="AI", categories=["tech"]))
        updated = store.update_alert(
            user.user_id, alert.id, AlertRule(user_id=user.user_id, query="agents", categories=["research"], enabled=False)
        )
        assert updated and updated.query == "agents" and not updated.enabled
        assert store.delete_alert(user.user_id, alert.id)


def test_account_password_session_and_deletion_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _store(tmpdir)
        user = store.create_user("member@example.com", "StrongPassword123", "Member")
        assert store.authenticate_user(user.email, "StrongPassword123")
        assert store.change_password(user.user_id, "StrongPassword123", "NewPassword456")
        assert store.authenticate_user(user.email, "StrongPassword123") is None
        assert store.authenticate_user(user.email, "NewPassword456")
        store.delete_account(user.user_id)
        assert store.authenticate_user(user.email, "NewPassword456") is None


def test_saved_context_feedback_and_cleanup():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = _store(tmpdir)
        source = SourceDoc(title="Result", summary="Evidence", url="https://example.com/a", source="Example", category="tech")
        store.save_context("context-123", "anonymous", "query", [source])
        store.add_search_feedback("anonymous", "context-123", True, "useful")
        with store._connection() as conn:
            old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
            conn.execute("UPDATE contexts SET created_at = ? WHERE context_id = ?", (old, "context-123"))
        with patch("backend.app.services.document_store.settings.context_retention_days", 30):
            counts = store.cleanup_expired()
        assert counts["contexts"] == 1


def test_advanced_search_filters():
    docs = [
        SourceDoc(title="Paper", summary="x", url="https://openalex.org/work", source="OpenAlex", category="research", credibility_score=0.9),
        SourceDoc(title="News", summary="x", url="https://example.com/news", source="Example", category="tech", credibility_score=0.4),
    ]
    request = SearchRequest(query="test", domain_filter=["openalex.org"], min_credibility=0.8)
    assert [doc.title for doc in _apply_search_filters(docs, request)] == ["Paper"]
