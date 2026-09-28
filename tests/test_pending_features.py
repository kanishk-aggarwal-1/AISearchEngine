import tempfile
from pathlib import Path

from backend.app.models import SourceDoc
from backend.app.services.document_store import DocumentStore
from backend.app.services.passkey_service import PasskeyService


def _source() -> SourceDoc:
    return SourceDoc(
        title="A cited paper",
        summary="Evidence",
        url="https://example.org/paper",
        source="Example",
        category="research",
        source_type="research",
        bias_label="research",
        credibility_score=0.9,
    )


def test_conversation_and_share_lifecycle():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "features.db"))
        user = store.create_user("reader@example.com", "StrongPassword123", "Reader")
        store.save_context("ctx", user.user_id, "evidence query", [_source()])
        conversation = store.create_conversation(user.user_id, "ctx", "Investigation")
        assert conversation
        message = store.add_conversation_message(
            conversation["conversation_id"], user.user_id, "user", "What changed?", []
        )
        assert message and store.get_conversation(conversation["conversation_id"], user.user_id)
        token = store.share_context("ctx", user.user_id)
        shared = store.get_shared_context(token or "")
        assert shared and shared["query"] == "evidence query"


def test_database_scheduler_lease_is_exclusive():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "locks.db"))
        assert store.acquire_scheduler_lock("scheduler", "worker-a", 60)
        assert not store.acquire_scheduler_lock("scheduler", "worker-b", 60)
        store.release_scheduler_lock("scheduler", "worker-a")
        assert store.acquire_scheduler_lock("scheduler", "worker-b", 60)


def test_passkey_registration_options_use_one_time_challenge():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "passkeys.db"))
        user = store.create_user("passkey@example.com", "StrongPassword123", "Passkey User")
        options = PasskeyService(store).begin_registration(user.user_id, user.email, user.display_name)
        assert options["publicKey"]["rp"]["id"]
        challenge = store.consume_passkey_challenge(options["challenge_id"], "registration")
        assert challenge and challenge["user_id"] == user.user_id
        assert store.consume_passkey_challenge(options["challenge_id"], "registration") is None


def test_oauth_identity_reuses_verified_email_account():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "oauth.db"))
        user = store.create_user("oauth@example.com", "StrongPassword123", "Existing")
        session = store.oauth_session("google", "google-subject", user.email, "Google Name")
        assert session.user.user_id == user.user_id
        assert session.user.email_verified
