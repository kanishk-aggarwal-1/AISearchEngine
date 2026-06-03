import json
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, List

from backend.app.models import (
    AlertRule,
    AuthUser,
    BookmarkItem,
    Category,
    SavedSessionItem,
    SourceDoc,
)
from backend.app.services.document_store import DocumentStore

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised only when postgres deps are missing
    psycopg = None
    dict_row = None


class _PostgresCompatConnection:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params: tuple | list | None = None):
        translated = sql.replace("?", "%s")
        return self._conn.execute(translated, params or ())

    def commit(self) -> None:
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()


class PostgresDocumentStore(DocumentStore):
    def __init__(self, database_url: str):
        if psycopg is None:
            raise RuntimeError("Postgres support requires psycopg to be installed.")
        self.database_url = self._normalize_database_url(database_url)

    def _normalize_database_url(self, database_url: str) -> str:
        cleaned = database_url.strip()
        if cleaned.startswith("postgresql+psycopg://"):
            return "postgresql://" + cleaned.split("://", 1)[1]
        return cleaned

    def _init_db(self) -> None:
        return None

    def _connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @contextmanager
    def _connection(self):
        conn = self._connect()
        wrapped = _PostgresCompatConnection(conn)
        try:
            yield wrapped
            wrapped.commit()
        finally:
            wrapped.close()

    def create_user(self, email: str, password: str, display_name: str) -> AuthUser:
        normalized_email = email.strip().lower()
        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = f"user_{self.title_hash(normalized_email + now_iso)[:12]}"
        password_hash = self._hash_password(password)
        with self._connection() as conn:
            existing_count = conn.execute("SELECT COUNT(*) AS count FROM auth_users").fetchone()["count"]
            is_admin = 1 if existing_count == 0 else 0
            conn.execute(
                """
                INSERT INTO auth_users (user_id, email, password_hash, display_name, created_at, is_admin, email_verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, normalized_email, password_hash, display_name.strip(), now_iso, is_admin, 0),
            )
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, preferred_categories_json, explanation_mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (user_id, json.dumps([]), "beginner", now_iso),
            )
        return AuthUser(
            user_id=user_id,
            email=normalized_email,
            display_name=display_name.strip(),
            created_at=now_iso,
            is_admin=bool(is_admin),
            email_verified=False,
        )

    def save_session(self, user_id: str, context_id: str, label: str = "") -> SavedSessionItem:
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_label = label.strip()
        with self._connection() as conn:
            row = conn.execute(
                """
                INSERT INTO saved_sessions (user_id, context_id, label, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, context_id) DO UPDATE SET
                    label = EXCLUDED.label,
                    created_at = saved_sessions.created_at
                RETURNING id, user_id, context_id, label, created_at
                """,
                (user_id, context_id, clean_label, now_iso),
            ).fetchone()
        return SavedSessionItem(
            id=row["id"],
            user_id=row["user_id"],
            context_id=row["context_id"],
            label=row["label"],
            created_at=row["created_at"],
        )

    def add_follow(self, user_id: str, entity: str) -> List[str]:
        normalized = entity.strip()
        if not normalized:
            return self.get_follows(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_follows (user_id, entity, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, entity) DO NOTHING
                """,
                (user_id, normalized, now_iso),
            )
        return self.get_follows(user_id)

    def add_alert(self, rule: AlertRule) -> AlertRule:
        with self._connection() as conn:
            row = conn.execute(
                """
                INSERT INTO user_alerts (user_id, query, categories_json, enabled, last_triggered_at)
                VALUES (?, ?, ?, ?, NULL)
                RETURNING id
                """,
                (rule.user_id, rule.query, json.dumps(rule.categories), int(rule.enabled)),
            ).fetchone()
        return AlertRule(id=int(row["id"]), user_id=rule.user_id, query=rule.query, categories=rule.categories, enabled=rule.enabled)

    def admin_snapshot(self, limit: int = 10) -> dict[str, Any]:
        with self._connection() as conn:
            counts = {
                "documents": conn.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"],
                "document_chunks": conn.execute("SELECT COUNT(*) AS count FROM document_chunks").fetchone()["count"],
                "query_cache": conn.execute("SELECT COUNT(*) AS count FROM query_cache").fetchone()["count"],
                "users": conn.execute("SELECT COUNT(*) AS count FROM auth_users").fetchone()["count"],
                "alerts": conn.execute("SELECT COUNT(*) AS count FROM user_alerts").fetchone()["count"],
                "bookmarks": conn.execute("SELECT COUNT(*) AS count FROM user_bookmarks").fetchone()["count"],
            }
            search_rows = conn.execute(
                "SELECT user_id, query, created_at FROM search_history ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return {
            "counts": counts,
            "recent_searches": [
                {"user_id": row["user_id"], "query": row["query"], "created_at": row["created_at"]}
                for row in search_rows
            ],
            "source_status": [item.model_dump() for item in self.get_source_statuses()],
            "recent_ingestion_runs": [item.model_dump() for item in self.recent_ingestion_runs(limit=limit)],
            "source_freshness": self.source_freshness_summary(),
        }

    def add_bookmark(self, user_id: str, source: SourceDoc) -> BookmarkItem:
        canonical_url = self.canonicalize_url(source.url, source.source, source.title)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            row = conn.execute(
                """
                INSERT INTO user_bookmarks (user_id, canonical_url, source_json, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, canonical_url) DO UPDATE SET
                    source_json = EXCLUDED.source_json,
                    created_at = EXCLUDED.created_at
                RETURNING id, user_id, source_json, created_at
                """,
                (user_id, canonical_url, json.dumps(source.model_dump(mode="json")), now_iso),
            ).fetchone()
        return BookmarkItem(
            id=row["id"],
            user_id=row["user_id"],
            source=SourceDoc.model_validate(json.loads(row["source_json"])),
            saved_at=row["created_at"],
        )

    def create_ingestion_run(self, trigger_type: str, query: str = "", categories: List[Category] | None = None) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        categories = categories or []
        with self._connection() as conn:
            row = conn.execute(
                """
                INSERT INTO ingestion_runs (
                    trigger_type, query, categories_json, status, inserted_count, source_count,
                    error_count, error_message, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                RETURNING id
                """,
                (trigger_type, query, json.dumps(categories), "running", 0, 0, 0, "", now_iso),
            ).fetchone()
        return int(row["id"])
