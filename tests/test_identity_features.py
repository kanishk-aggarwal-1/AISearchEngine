import tempfile
from pathlib import Path
from unittest.mock import patch

from backend.app.services.document_store import DocumentStore
from backend.app.services.totp_service import _code, generate_secret, verify_code


def test_totp_round_trip():
    secret = generate_secret()
    now = 1_800_000_000
    code = _code(secret, now // 30)
    assert verify_code(secret, code, now=now)


def test_mfa_blocks_password_only_login():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "identity.db"))
        user = store.create_user("mfa@example.com", "StrongPassword123", "MFA User")
        secret = generate_secret()
        store.set_mfa_secret(user.user_id, secret)
        with (
            patch("backend.app.services.totp_service.time.time", return_value=1_800_000_000),
            patch(
                "backend.app.services.document_store.verify_code",
                side_effect=lambda s, c: verify_code(s, c, now=1_800_000_000),
            ),
        ):
            code = _code(secret, 1_800_000_000 // 30)
            assert store.enable_mfa(user.user_id, code)
            assert store.authenticate_user(user.email, "StrongPassword123") is None
            assert store.authenticate_user(user.email, "StrongPassword123", code)


def test_email_change_and_export():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = DocumentStore(str(Path(tmpdir) / "identity.db"))
        user = store.create_user("old@example.com", "StrongPassword123", "User")
        token, _ = store.issue_email_change_token(user.user_id, "new@example.com")
        changed = store.confirm_email_change(token)
        assert changed and changed.email == "new@example.com"
        exported = store.export_user_data(user.user_id)
        assert exported["account"]["email"] == "new@example.com"
        assert "password_hash" not in exported["account"]
