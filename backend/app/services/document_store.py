import json
import re
import sqlite3
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import md5, pbkdf2_hmac
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.app.config import settings
from backend.app.services.logging_service import get_logger
from backend.app.models import (
    AlertDeliverySettings,
    AlertRule,
    AuthMessage,
    AuthSessionResponse,
    AuthUser,
    BookmarkItem,
    Category,
    ChunkHit,
    IngestionRunRecord,
    SavedSessionItem,
    SearchHistoryItem,
    SourceStatus,
    SourceDoc,
    UserProfile,
)


class DocumentStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("signalscope.store")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def ping(self) -> bool:
        try:
            with self._connection() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except Exception:
            return False

    def last_successful_ingestion_at(self) -> str | None:
        try:
            with self._connection() as conn:
                row = conn.execute(
                    "SELECT MAX(last_success_at) AS latest_success FROM source_status WHERE last_success_at IS NOT NULL"
                ).fetchone()
            if not row:
                return None
            return row["latest_success"]
        except Exception:
            return None

    def corpus_stats(self) -> dict:
        """Non-sensitive counts for the public metrics dashboard:
        total documents indexed and the number of distinct sources."""
        try:
            with self._connection() as conn:
                documents = conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
                distinct_sources = conn.execute(
                    "SELECT COUNT(DISTINCT source) AS n FROM documents"
                ).fetchone()["n"]
            return {"documents_indexed": int(documents), "distinct_sources": int(distinct_sources)}
        except Exception:
            return {"documents_indexed": 0, "distinct_sources": 0}

    @contextmanager
    def _connection(self):
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connection() as conn:
            # WAL mode allows concurrent reads alongside writes, eliminating
            # "database is locked" errors under async FastAPI workloads.
            if str(self.db_path) != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    canonical_url TEXT NOT NULL UNIQUE,
                    raw_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    title_hash TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    source_type TEXT NOT NULL,
                    bias_label TEXT NOT NULL,
                    credibility_score REAL NOT NULL,
                    published_at TEXT,
                    inserted_at TEXT NOT NULL,
                    embedding_json TEXT,
                    entity_tags_json TEXT,
                    research_json TEXT,
                    sports_json TEXT
                )
                """
            )
            self._migrate_documents_table_if_needed(conn)

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_cache (
                    query_key TEXT PRIMARY KEY,
                    response_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    preferred_categories_json TEXT NOT NULL,
                    explanation_mode TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_users (
                    user_id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    email_verified INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_verification_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS auth_password_reset_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_follows (
                    user_id TEXT NOT NULL,
                    entity TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, entity)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS search_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS saved_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, context_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS source_status (
                    source_name TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    last_attempt_at TEXT,
                    last_success_at TEXT,
                    last_error TEXT NOT NULL,
                    last_error_at TEXT,
                    last_item_count INTEGER NOT NULL,
                    average_latency_ms REAL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    last_triggered_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_delivery_settings (
                    user_id TEXT PRIMARY KEY,
                    webhook_url TEXT NOT NULL,
                    digest_mode TEXT NOT NULL,
                    enabled INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    canonical_url TEXT NOT NULL,
                    source_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(user_id, canonical_url)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contexts (
                    context_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    sources_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    canonical_url TEXT NOT NULL,
                    chunk_id TEXT NOT NULL PRIMARY KEY,
                    chunk_index INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    category TEXT NOT NULL,
                    published_at TEXT,
                    chunk_text TEXT NOT NULL,
                    embedding_json TEXT,
                    inserted_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trigger_type TEXT NOT NULL,
                    query TEXT NOT NULL,
                    categories_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    inserted_count INTEGER NOT NULL,
                    source_count INTEGER NOT NULL,
                    error_count INTEGER NOT NULL,
                    error_message TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_category_published ON documents (category, published_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_source ON documents (source)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_inserted_at ON documents (inserted_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_query_cache_updated_at ON query_cache (updated_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_alerts_user_enabled ON user_alerts (user_id, enabled)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user_created ON user_bookmarks (user_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_category_published ON document_chunks (category, published_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_document_chunks_canonical ON document_chunks (canonical_url, chunk_index)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_user ON auth_sessions (user_id, last_seen_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_search_history_user_created ON search_history (user_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_saved_sessions_user_created ON saved_sessions (user_id, created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_source_status_category ON source_status (category, enabled)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_runs_started ON ingestion_runs (started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_ingestion_runs_status ON ingestion_runs (status, started_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_verification_user ON auth_verification_tokens (user_id, expires_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_password_reset_user ON auth_password_reset_tokens (user_id, expires_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_auth_sessions_expires ON auth_sessions (expires_at)")
            self._migrate_auth_tables_if_needed(conn)
            self._migrate_source_status_table_if_needed(conn)

    def _migrate_auth_tables_if_needed(self, conn: sqlite3.Connection) -> None:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(auth_users)").fetchall()}
        if "is_admin" not in cols:
            conn.execute("ALTER TABLE auth_users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0")
        if "email_verified" not in cols:
            conn.execute("ALTER TABLE auth_users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0")

        session_cols = {row["name"] for row in conn.execute("PRAGMA table_info(auth_sessions)").fetchall()}
        if "expires_at" not in session_cols:
            # Backfill existing sessions with a 30-day expiry from their creation date
            conn.execute("ALTER TABLE auth_sessions ADD COLUMN expires_at TEXT NOT NULL DEFAULT ''")
            conn.execute(
                """
                UPDATE auth_sessions
                SET expires_at = datetime(created_at, '+30 days')
                WHERE expires_at = ''
                """
            )

    def _migrate_source_status_table_if_needed(self, conn: sqlite3.Connection) -> None:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(source_status)").fetchall()}
        if "success_count" not in cols:
            conn.execute("ALTER TABLE source_status ADD COLUMN success_count INTEGER NOT NULL DEFAULT 0")
        if "failure_count" not in cols:
            conn.execute("ALTER TABLE source_status ADD COLUMN failure_count INTEGER NOT NULL DEFAULT 0")
        if "last_attempt_at" not in cols:
            conn.execute("ALTER TABLE source_status ADD COLUMN last_attempt_at TEXT")
        if "average_latency_ms" not in cols:
            conn.execute("ALTER TABLE source_status ADD COLUMN average_latency_ms REAL")

    def _migrate_documents_table_if_needed(self, conn: sqlite3.Connection) -> None:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(documents)").fetchall()}
        if "canonical_url" in cols:
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS documents_v2 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical_url TEXT NOT NULL UNIQUE,
                raw_url TEXT NOT NULL,
                title TEXT NOT NULL,
                title_hash TEXT NOT NULL,
                summary TEXT NOT NULL,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                source_type TEXT NOT NULL,
                bias_label TEXT NOT NULL,
                credibility_score REAL NOT NULL,
                published_at TEXT,
                inserted_at TEXT NOT NULL,
                embedding_json TEXT,
                entity_tags_json TEXT,
                research_json TEXT,
                sports_json TEXT
            )
            """
        )

        legacy_rows = conn.execute("SELECT * FROM documents").fetchall()
        now_iso = datetime.now(timezone.utc).isoformat()
        for row in legacy_rows:
            raw_url = row["url"] if "url" in cols else row["raw_url"] if "raw_url" in cols else ""
            title = row["title"] if "title" in cols else ""
            source = row["source"] if "source" in cols else "unknown"
            category = row["category"] if "category" in cols else "general"
            summary = row["summary"] if "summary" in cols else ""
            published_at = row["published_at"] if "published_at" in cols else None
            inserted_at = row["inserted_at"] if "inserted_at" in cols else now_iso
            canonical_url = self.canonicalize_url(raw_url, source, title)
            conn.execute(
                """
                INSERT OR IGNORE INTO documents_v2 (
                    canonical_url, raw_url, title, title_hash, summary, source, category,
                    source_type, bias_label, credibility_score, published_at, inserted_at,
                    embedding_json, entity_tags_json, research_json, sports_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    canonical_url,
                    raw_url,
                    title,
                    self.title_hash(title),
                    summary,
                    source,
                    category,
                    "news",
                    "reporting",
                    0.62,
                    published_at,
                    inserted_at,
                    None,
                    json.dumps([]),
                    json.dumps(None),
                    json.dumps(None),
                ),
            )

        conn.execute("DROP TABLE documents")
        conn.execute("ALTER TABLE documents_v2 RENAME TO documents")

    def upsert_documents(
        self,
        docs: List[SourceDoc],
        embeddings: dict[str, List[float]] | None = None,
        chunk_embeddings: dict[str, List[float]] | None = None,
    ) -> int:
        inserted = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        embeddings = embeddings or {}
        chunk_embeddings = chunk_embeddings or {}
        with self._connection() as conn:
            for doc in docs:
                canonical_url = self.canonicalize_url(doc.url, doc.source, doc.title)
                title_hash = self.title_hash(doc.title)
                existing = conn.execute("SELECT id FROM documents WHERE canonical_url = ?", (canonical_url,)).fetchone()
                values = (
                    doc.url,
                    doc.title,
                    title_hash,
                    doc.summary,
                    doc.source,
                    doc.category,
                    doc.source_type,
                    doc.bias_label,
                    float(doc.credibility_score),
                    doc.published_at.isoformat() if doc.published_at else None,
                    now_iso,
                    json.dumps(embeddings.get(canonical_url)) if embeddings.get(canonical_url) else None,
                    json.dumps(doc.entity_tags),
                    json.dumps(doc.research_metadata.model_dump() if doc.research_metadata else None),
                    json.dumps(doc.sports_metadata.model_dump() if doc.sports_metadata else None),
                    canonical_url,
                )
                if existing:
                    conn.execute(
                        """
                        UPDATE documents
                        SET raw_url = ?, title = ?, title_hash = ?, summary = ?, source = ?, category = ?,
                            source_type = ?, bias_label = ?, credibility_score = ?, published_at = ?,
                            inserted_at = ?, embedding_json = COALESCE(?, embedding_json), entity_tags_json = ?,
                            research_json = ?, sports_json = ?
                        WHERE canonical_url = ?
                        """,
                        values,
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO documents (
                            raw_url, title, title_hash, summary, source, category, source_type, bias_label,
                            credibility_score, published_at, inserted_at, embedding_json, entity_tags_json,
                            research_json, sports_json, canonical_url
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        values,
                    )
                    inserted += 1
                conn.execute("DELETE FROM document_chunks WHERE canonical_url = ?", (canonical_url,))
                chunks = self._chunk_doc(doc)
                for idx, chunk_text in enumerate(chunks):
                    chunk_id = self.chunk_id(canonical_url, idx)
                    conn.execute(
                        """
                        INSERT INTO document_chunks (
                            canonical_url, chunk_id, chunk_index, source, category, published_at,
                            chunk_text, embedding_json, inserted_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            canonical_url,
                            chunk_id,
                            idx,
                            doc.source,
                            doc.category,
                            doc.published_at.isoformat() if doc.published_at else None,
                            chunk_text,
                            json.dumps(chunk_embeddings.get(chunk_id)) if chunk_embeddings.get(chunk_id) else None,
                            now_iso,
                        ),
                    )
        return inserted

    def search_documents(self, query: str, categories: List[Category], limit: int) -> List[SourceDoc]:
        if not categories:
            return []
        terms = [f"%{token.lower()}%" for token in query.split() if token.strip()]
        if not terms:
            return []
        where_terms = " OR ".join(["LOWER(title) LIKE ? OR LOWER(summary) LIKE ?" for _ in terms])
        params: list = []
        for term in terms:
            params.extend([term, term])
        placeholders = ",".join(["?" for _ in categories])
        params.extend(categories)
        params.append(limit)
        sql = f"""
            SELECT * FROM documents
            WHERE ({where_terms})
              AND category IN ({placeholders})
            ORDER BY COALESCE(published_at, inserted_at) DESC
            LIMIT ?
        """
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_doc(row) for row in rows]

    def all_recent_documents(self, categories: List[Category], limit: int = 120) -> List[SourceDoc]:
        if not categories:
            return []
        placeholders = ",".join(["?" for _ in categories])
        sql = f"""
            SELECT * FROM documents
            WHERE category IN ({placeholders})
            ORDER BY COALESCE(published_at, inserted_at) DESC
            LIMIT ?
        """
        with self._connection() as conn:
            rows = conn.execute(sql, [*categories, limit]).fetchall()
        return [self._row_to_doc(row) for row in rows]

    def embedding_map(self, categories: List[Category], limit: int = 200) -> dict[str, List[float]]:
        if not categories:
            return {}
        placeholders = ",".join(["?" for _ in categories])
        sql = f"""
            SELECT canonical_url, embedding_json
            FROM documents
            WHERE category IN ({placeholders}) AND embedding_json IS NOT NULL
            ORDER BY inserted_at DESC
            LIMIT ?
        """
        out: dict[str, List[float]] = {}
        with self._connection() as conn:
            rows = conn.execute(sql, [*categories, limit]).fetchall()
        for row in rows:
            try:
                out[row["canonical_url"]] = json.loads(row["embedding_json"])
            except Exception:
                continue
        return out

    def chunk_embedding_map(self, categories: List[Category], limit: int = 400) -> dict[str, List[float]]:
        if not categories:
            return {}
        placeholders = ",".join(["?" for _ in categories])
        sql = f"""
            SELECT chunk_id, embedding_json
            FROM document_chunks
            WHERE category IN ({placeholders}) AND embedding_json IS NOT NULL
            ORDER BY inserted_at DESC
            LIMIT ?
        """
        out: dict[str, List[float]] = {}
        with self._connection() as conn:
            rows = conn.execute(sql, [*categories, limit]).fetchall()
        for row in rows:
            try:
                out[row["chunk_id"]] = json.loads(row["embedding_json"])
            except Exception:
                continue
        return out

    def search_chunks(self, query: str, categories: List[Category], limit: int = 40) -> List[ChunkHit]:
        if not categories:
            return []
        terms = [f"%{token.lower()}%" for token in query.split() if token.strip()]
        if not terms:
            return []
        where_terms = " OR ".join(["LOWER(chunk_text) LIKE ?" for _ in terms])
        params: list = []
        params.extend(terms)
        placeholders = ",".join(["?" for _ in categories])
        params.extend(categories)
        params.append(limit)
        sql = f"""
            SELECT canonical_url, chunk_id, chunk_index, source, category, published_at, chunk_text
            FROM document_chunks
            WHERE ({where_terms})
              AND category IN ({placeholders})
            ORDER BY COALESCE(published_at, inserted_at) DESC
            LIMIT ?
        """
        with self._connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [
            ChunkHit(
                canonical_url=row["canonical_url"],
                chunk_id=row["chunk_id"],
                chunk_index=int(row["chunk_index"]),
                source=row["source"],
                category=row["category"],
                published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
                text=row["chunk_text"],
            )
            for row in rows
        ]

    def get_query_cache(self, query_key: str, max_age_minutes: int = 20) -> str | None:
        with self._connection() as conn:
            row = conn.execute("SELECT response_json, updated_at FROM query_cache WHERE query_key = ?", (query_key,)).fetchone()
        if not row:
            return None
        try:
            updated_at = datetime.fromisoformat(row["updated_at"])
        except Exception:
            return None
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - updated_at > timedelta(minutes=max_age_minutes):
            return None
        return row["response_json"]

    def create_user(self, email: str, password: str, display_name: str) -> AuthUser:
        normalized_email = email.strip().lower()
        now_iso = datetime.now(timezone.utc).isoformat()
        user_id = f"user_{secrets.token_hex(6)}"
        password_hash = self._hash_password(password)
        try:
            with self._connection() as conn:
                existing = conn.execute("SELECT 1 FROM auth_users WHERE email = ?", (normalized_email,)).fetchone()
                if existing:
                    raise ValueError("An account with this email already exists")
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
                    INSERT OR IGNORE INTO user_profiles (user_id, preferred_categories_json, explanation_mode, updated_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, json.dumps([]), "beginner", now_iso),
                )
        except sqlite3.IntegrityError:
            # A concurrent registration with the same email beat us to the INSERT.
            # Re-raise as a friendly ValueError so auth_register surfaces a 400
            # with a clean message instead of leaking the raw SQLite error text
            # ("UNIQUE constraint failed: auth_users.email").
            raise ValueError("An account with this email already exists")
        return AuthUser(
            user_id=user_id,
            email=normalized_email,
            display_name=display_name.strip(),
            created_at=now_iso,
            is_admin=bool(is_admin),
            email_verified=False,
        )

    def authenticate_user(self, email: str, password: str) -> AuthSessionResponse | None:
        normalized_email = email.strip().lower()
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email = ?", (normalized_email,)).fetchone()
            if not row or not self._verify_password(password, row["password_hash"]):
                self.logger.warning("audit login_failed email=%s", normalized_email)
                return None
            token = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat()
            expires_iso = (now + timedelta(days=30)).isoformat()
            conn.execute(
                """
                INSERT INTO auth_sessions (token, user_id, created_at, last_seen_at, expires_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token, row["user_id"], now_iso, now_iso, expires_iso),
            )
        self.logger.info("audit login_success user_id=%s", row["user_id"])
        return AuthSessionResponse(
            token=token,
            user=AuthUser(
                user_id=row["user_id"],
                email=row["email"],
                display_name=row["display_name"],
                created_at=row["created_at"],
                is_admin=bool(row["is_admin"]),
                email_verified=bool(row["email_verified"]),
            ),
        )

    def get_user_by_token(self, token: str) -> AuthUser | None:
        if not token.strip():
            return None
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT u.user_id, u.email, u.display_name, u.created_at
                    , u.is_admin, u.email_verified
                FROM auth_sessions s
                JOIN auth_users u ON u.user_id = s.user_id
                WHERE s.token = ? AND s.expires_at > ?
                """,
                (token.strip(), now_iso),
            ).fetchone()
            if not row:
                return None
            conn.execute("UPDATE auth_sessions SET last_seen_at = ? WHERE token = ?", (now_iso, token.strip()))
        return AuthUser(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            is_admin=bool(row["is_admin"]),
            email_verified=bool(row["email_verified"]),
        )

    def logout_session(self, token: str) -> AuthMessage:
        with self._connection() as conn:
            conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token.strip(),))
        return AuthMessage(message="Signed out successfully.")

    def issue_verification_token(self, user_id: str) -> tuple[str, str]:
        token = secrets.token_urlsafe(24)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=24)
        with self._connection() as conn:
            conn.execute("DELETE FROM auth_verification_tokens WHERE user_id = ? AND used_at IS NULL", (user_id,))
            conn.execute(
                """
                INSERT INTO auth_verification_tokens (token, user_id, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (token, user_id, now.isoformat(), expires_at.isoformat()),
            )
        return token, expires_at.isoformat()

    def verify_email(self, token: str) -> AuthUser | None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT t.user_id, t.expires_at, t.used_at, u.email, u.display_name, u.created_at, u.is_admin
                FROM auth_verification_tokens t
                JOIN auth_users u ON u.user_id = t.user_id
                WHERE t.token = ?
                """,
                (token.strip(),),
            ).fetchone()
            if not row or row["used_at"]:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                return None
            conn.execute("UPDATE auth_verification_tokens SET used_at = ? WHERE token = ?", (now_iso, token.strip()))
            conn.execute("UPDATE auth_users SET email_verified = 1 WHERE user_id = ?", (row["user_id"],))
        self.logger.info("audit email_verified user_id=%s", row["user_id"])
        return AuthUser(
            user_id=row["user_id"],
            email=row["email"],
            display_name=row["display_name"],
            created_at=row["created_at"],
            is_admin=bool(row["is_admin"]),
            email_verified=True,
        )

    def issue_password_reset_token(self, email: str) -> tuple[str, str] | None:
        normalized_email = email.strip().lower()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=1)
        with self._connection() as conn:
            row = conn.execute("SELECT user_id FROM auth_users WHERE email = ?", (normalized_email,)).fetchone()
            if not row:
                self.logger.warning("audit password_reset_unknown_email email=%s", normalized_email)
                return None
            token = secrets.token_urlsafe(24)
            conn.execute("DELETE FROM auth_password_reset_tokens WHERE user_id = ? AND used_at IS NULL", (row["user_id"],))
            conn.execute(
                """
                INSERT INTO auth_password_reset_tokens (token, user_id, created_at, expires_at, used_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (token, row["user_id"], now.isoformat(), expires_at.isoformat()),
            )
        self.logger.info("audit password_reset_issued user_id=%s", row["user_id"])
        return token, expires_at.isoformat()

    def reset_password(self, token: str, new_password: str) -> AuthMessage | None:
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT user_id, expires_at, used_at FROM auth_password_reset_tokens WHERE token = ?",
                (token.strip(),),
            ).fetchone()
            if not row or row["used_at"]:
                return None
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                return None
            conn.execute("UPDATE auth_password_reset_tokens SET used_at = ? WHERE token = ?", (now_iso, token.strip()))
            conn.execute("UPDATE auth_users SET password_hash = ? WHERE user_id = ?", (self._hash_password(new_password), row["user_id"]))
            conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (row["user_id"],))
        self.logger.info("audit password_reset_completed user_id=%s", row["user_id"])
        return AuthMessage(message="Password updated. Please sign in again.")

    def put_query_cache(self, query_key: str, payload: dict) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO query_cache (query_key, response_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(query_key) DO UPDATE SET
                    response_json = excluded.response_json,
                    updated_at = excluded.updated_at
                """,
                (query_key, json.dumps(payload), now_iso),
            )

    def add_search_history(self, user_id: str, query: str, categories: List[Category], context_id: str) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO search_history (user_id, query, categories_json, context_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, query, json.dumps(categories), context_id, now_iso),
            )

    def get_search_history(self, user_id: str, limit: int = 25) -> List[SearchHistoryItem]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM search_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            SearchHistoryItem(
                id=row["id"],
                user_id=row["user_id"],
                query=row["query"],
                categories=json.loads(row["categories_json"]),
                context_id=row["context_id"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_session(self, user_id: str, context_id: str, label: str = "") -> SavedSessionItem:
        now_iso = datetime.now(timezone.utc).isoformat()
        clean_label = label.strip()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO saved_sessions (id, user_id, context_id, label, created_at)
                VALUES (
                    (SELECT id FROM saved_sessions WHERE user_id = ? AND context_id = ?),
                    ?, ?, ?, COALESCE((SELECT created_at FROM saved_sessions WHERE user_id = ? AND context_id = ?), ?)
                )
                """,
                (user_id, context_id, user_id, context_id, clean_label, user_id, context_id, now_iso),
            )
            row = conn.execute(
                "SELECT * FROM saved_sessions WHERE user_id = ? AND context_id = ?",
                (user_id, context_id),
            ).fetchone()
        return SavedSessionItem(
            id=row["id"],
            user_id=row["user_id"],
            context_id=row["context_id"],
            label=row["label"],
            created_at=row["created_at"],
        )

    def get_saved_sessions(self, user_id: str, limit: int = 25) -> List[SavedSessionItem]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM saved_sessions WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        return [
            SavedSessionItem(
                id=row["id"],
                user_id=row["user_id"],
                context_id=row["context_id"],
                label=row["label"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def record_source_result(self, source_name: str, category: str, item_count: int, error: str = "", latency_ms: float | None = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            current = conn.execute(
                "SELECT enabled, success_count, failure_count, average_latency_ms FROM source_status WHERE source_name = ?",
                (source_name,),
            ).fetchone()
            enabled = int(current["enabled"]) if current else 1
            success_count = int(current["success_count"]) if current and current["success_count"] is not None else 0
            failure_count = int(current["failure_count"]) if current and current["failure_count"] is not None else 0
            prior_latency = float(current["average_latency_ms"]) if current and current["average_latency_ms"] is not None else None
            next_success = success_count + (0 if error else 1)
            next_failure = failure_count + (1 if error else 0)
            next_latency = prior_latency
            if latency_ms is not None:
                total_runs = max(success_count + failure_count, 0)
                if prior_latency is None:
                    next_latency = round(float(latency_ms), 2)
                else:
                    next_latency = round(((prior_latency * total_runs) + float(latency_ms)) / max(total_runs + 1, 1), 2)
            conn.execute(
                """
                INSERT INTO source_status (
                    source_name, category, enabled, success_count, failure_count, last_attempt_at,
                    last_success_at, last_error, last_error_at, last_item_count, average_latency_ms, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_name) DO UPDATE SET
                    category = excluded.category,
                    enabled = source_status.enabled,
                    success_count = excluded.success_count,
                    failure_count = excluded.failure_count,
                    last_attempt_at = excluded.last_attempt_at,
                    last_success_at = excluded.last_success_at,
                    last_error = excluded.last_error,
                    last_error_at = excluded.last_error_at,
                    last_item_count = excluded.last_item_count,
                    average_latency_ms = excluded.average_latency_ms,
                    updated_at = excluded.updated_at
                """,
                (
                    source_name,
                    category,
                    enabled,
                    next_success,
                    next_failure,
                    now_iso,
                    None if error else now_iso,
                    error,
                    now_iso if error else None,
                    item_count,
                    next_latency,
                    now_iso,
                ),
            )

    def set_source_enabled(self, source_name: str, enabled: bool, category: str = "unknown") -> SourceStatus:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            existing = conn.execute("SELECT * FROM source_status WHERE source_name = ?", (source_name,)).fetchone()
            if existing:
                conn.execute("UPDATE source_status SET enabled = ?, updated_at = ? WHERE source_name = ?", (int(enabled), now_iso, source_name))
            else:
                conn.execute(
                    """
                    INSERT INTO source_status (
                        source_name, category, enabled, success_count, failure_count, last_attempt_at,
                        last_success_at, last_error, last_error_at, last_item_count, average_latency_ms, updated_at
                    ) VALUES (?, ?, ?, 0, 0, NULL, NULL, '', NULL, 0, NULL, ?)
                    """,
                    (source_name, category, int(enabled), now_iso),
                )
        return self.get_source_statuses(source_name=source_name)[0]

    def get_source_statuses(self, category: str | None = None, source_name: str | None = None) -> List[SourceStatus]:
        clauses = []
        params = []
        if category:
            clauses.append("category = ?")
            params.append(category)
        if source_name:
            clauses.append("source_name = ?")
            params.append(source_name)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as conn:
            rows = conn.execute(f"SELECT * FROM source_status {where} ORDER BY category, source_name", params).fetchall()
        return [
            SourceStatus(
                source_name=row["source_name"],
                category=row["category"],
                enabled=bool(row["enabled"]),
                success_count=int(row["success_count"]) if row["success_count"] is not None else 0,
                failure_count=int(row["failure_count"]) if row["failure_count"] is not None else 0,
                last_attempt_at=row["last_attempt_at"],
                last_success_at=row["last_success_at"],
                last_error=row["last_error"],
                last_error_at=row["last_error_at"],
                last_item_count=int(row["last_item_count"]),
                average_latency_ms=float(row["average_latency_ms"]) if row["average_latency_ms"] is not None else None,
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def source_enabled(self, source_name: str) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT enabled FROM source_status WHERE source_name = ?", (source_name,)).fetchone()
        return True if not row else bool(row["enabled"])

    def create_ingestion_run(self, trigger_type: str, query: str = "", categories: List[Category] | None = None) -> int:
        now_iso = datetime.now(timezone.utc).isoformat()
        categories = categories or []
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO ingestion_runs (
                    trigger_type, query, categories_json, status, inserted_count, source_count,
                    error_count, error_message, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (trigger_type, query, json.dumps(categories), "running", 0, 0, 0, "", now_iso),
            )
            return int(cursor.lastrowid)

    def finish_ingestion_run(
        self,
        run_id: int,
        status: str,
        inserted_count: int,
        source_count: int,
        error_count: int = 0,
        error_message: str = "",
    ) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                UPDATE ingestion_runs
                SET status = ?, inserted_count = ?, source_count = ?, error_count = ?, error_message = ?, completed_at = ?
                WHERE id = ?
                """,
                (status, inserted_count, source_count, error_count, error_message, now_iso, run_id),
            )

    def recent_ingestion_runs(self, limit: int = 10) -> List[IngestionRunRecord]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            IngestionRunRecord(
                id=row["id"],
                trigger_type=row["trigger_type"],
                query=row["query"],
                categories=json.loads(row["categories_json"]),
                status=row["status"],
                inserted_count=int(row["inserted_count"]),
                source_count=int(row["source_count"]),
                error_count=int(row["error_count"]),
                error_message=row["error_message"],
                started_at=row["started_at"],
                completed_at=row["completed_at"],
            )
            for row in rows
        ]

    def source_freshness_summary(self) -> dict:
        statuses = self.get_source_statuses()
        now = datetime.now(timezone.utc)
        buckets = {"healthy": 0, "stale": 0, "unknown": 0, "errored": 0}
        freshest_at = None
        stalest_at = None
        for status in statuses:
            if status.last_error:
                buckets["errored"] += 1
            if not status.last_success_at:
                buckets["unknown"] += 1
                continue
            try:
                ts = datetime.fromisoformat(status.last_success_at)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
            except Exception:
                buckets["unknown"] += 1
                continue
            freshest_at = ts.isoformat() if freshest_at is None or ts > datetime.fromisoformat(freshest_at) else freshest_at
            stalest_at = ts.isoformat() if stalest_at is None or ts < datetime.fromisoformat(stalest_at) else stalest_at
            if now - ts <= timedelta(hours=24):
                buckets["healthy"] += 1
            else:
                buckets["stale"] += 1
        return {
            "healthy": buckets["healthy"],
            "stale": buckets["stale"],
            "unknown": buckets["unknown"],
            "errored": buckets["errored"],
            "healthy_sources": buckets["healthy"],
            "stale_sources": buckets["stale"],
            "unknown_sources": buckets["unknown"],
            "errored_sources": buckets["errored"],
            "freshest_success_at": freshest_at,
            "stalest_success_at": stalest_at,
        }

    def admin_snapshot(self, limit: int = 10) -> dict:
        with self._connection() as conn:
            counts = {
                "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
                "document_chunks": conn.execute("SELECT COUNT(*) FROM document_chunks").fetchone()[0],
                "query_cache": conn.execute("SELECT COUNT(*) FROM query_cache").fetchone()[0],
                "users": conn.execute("SELECT COUNT(*) FROM auth_users").fetchone()[0],
                "alerts": conn.execute("SELECT COUNT(*) FROM user_alerts").fetchone()[0],
                "bookmarks": conn.execute("SELECT COUNT(*) FROM user_bookmarks").fetchone()[0],
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

    def upsert_profile(self, profile: UserProfile) -> UserProfile:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO user_profiles (user_id, preferred_categories_json, explanation_mode, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_categories_json = excluded.preferred_categories_json,
                    explanation_mode = excluded.explanation_mode,
                    updated_at = excluded.updated_at
                """,
                (profile.user_id, json.dumps(profile.preferred_categories), profile.explanation_mode, now_iso),
            )
        return profile

    def get_profile(self, user_id: str) -> UserProfile:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return UserProfile(user_id=user_id, preferred_categories=[], explanation_mode="beginner")
        return UserProfile(
            user_id=row["user_id"],
            preferred_categories=json.loads(row["preferred_categories_json"]),
            explanation_mode=row["explanation_mode"],
        )

    def add_follow(self, user_id: str, entity: str) -> List[str]:
        normalized = entity.strip()
        if not normalized:
            return self.get_follows(user_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_follows (user_id, entity, created_at) VALUES (?, ?, ?)",
                (user_id, normalized, now_iso),
            )
        return self.get_follows(user_id)

    def get_follows(self, user_id: str, limit: int = 200, offset: int = 0) -> List[str]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT entity FROM user_follows WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        return [row["entity"] for row in rows]

    def add_alert(self, rule: AlertRule) -> AlertRule:
        with self._connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO user_alerts (user_id, query, categories_json, enabled, last_triggered_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (rule.user_id, rule.query, json.dumps(rule.categories), int(rule.enabled)),
            )
            alert_id = int(cursor.lastrowid)
        return AlertRule(id=alert_id, user_id=rule.user_id, query=rule.query, categories=rule.categories, enabled=rule.enabled)

    def get_alerts(self, user_id: str, limit: int = 200, offset: int = 0) -> List[AlertRule]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_alerts WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        return [
            AlertRule(
                id=row["id"],
                user_id=row["user_id"],
                query=row["query"],
                categories=json.loads(row["categories_json"]),
                enabled=bool(row["enabled"]),
            )
            for row in rows
        ]

    def get_enabled_alerts(self) -> List[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT a.*, d.webhook_url, d.digest_mode, d.enabled AS delivery_enabled
                FROM user_alerts a
                LEFT JOIN alert_delivery_settings d ON d.user_id = a.user_id
                WHERE a.enabled = 1
                """
            ).fetchall()
        alerts = []
        for row in rows:
            alerts.append(
                {
                    "id": row["id"],
                    "user_id": row["user_id"],
                    "query": row["query"],
                    "categories": json.loads(row["categories_json"]),
                    "last_triggered_at": row["last_triggered_at"],
                    "webhook_url": row["webhook_url"] or "",
                    "digest_mode": row["digest_mode"] or "daily",
                    "delivery_enabled": bool(row["delivery_enabled"]),
                }
            )
        return alerts

    def mark_alert_triggered(self, alert_id: int) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute("UPDATE user_alerts SET last_triggered_at = ? WHERE id = ?", (now_iso, alert_id))

    def upsert_alert_delivery(self, settings_obj: AlertDeliverySettings) -> AlertDeliverySettings:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO alert_delivery_settings (user_id, webhook_url, digest_mode, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    webhook_url = excluded.webhook_url,
                    digest_mode = excluded.digest_mode,
                    enabled = excluded.enabled,
                    updated_at = excluded.updated_at
                """,
                (settings_obj.user_id, settings_obj.webhook_url, settings_obj.digest_mode, int(settings_obj.enabled), now_iso),
            )
        return settings_obj

    def get_alert_delivery(self, user_id: str) -> AlertDeliverySettings:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM alert_delivery_settings WHERE user_id = ?", (user_id,)).fetchone()
        if not row:
            return AlertDeliverySettings(user_id=user_id, webhook_url="", digest_mode="daily", enabled=False)
        return AlertDeliverySettings(
            user_id=row["user_id"],
            webhook_url=row["webhook_url"],
            digest_mode=row["digest_mode"],
            enabled=bool(row["enabled"]),
        )

    def add_bookmark(self, user_id: str, source: SourceDoc) -> BookmarkItem:
        canonical_url = self.canonicalize_url(source.url, source.source, source.title)
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO user_bookmarks (id, user_id, canonical_url, source_json, created_at)
                VALUES (
                    (SELECT id FROM user_bookmarks WHERE user_id = ? AND canonical_url = ?),
                    ?, ?, ?, ?
                )
                """,
                (user_id, canonical_url, user_id, canonical_url, json.dumps(source.model_dump(mode="json")), now_iso),
            )
            row = conn.execute(
                "SELECT id, source_json, created_at FROM user_bookmarks WHERE user_id = ? AND canonical_url = ?",
                (user_id, canonical_url),
            ).fetchone()
        return BookmarkItem(
            id=row["id"],
            user_id=user_id,
            source=SourceDoc.model_validate(json.loads(row["source_json"])),
            saved_at=row["created_at"],
        )

    def get_bookmarks(self, user_id: str, limit: int = 200, offset: int = 0) -> List[BookmarkItem]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT * FROM user_bookmarks WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        return [
            BookmarkItem(
                id=row["id"],
                user_id=row["user_id"],
                source=SourceDoc.model_validate(json.loads(row["source_json"])),
                saved_at=row["created_at"],
            )
            for row in rows
        ]

    def delete_bookmark(self, user_id: str, bookmark_id: int) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM user_bookmarks WHERE user_id = ? AND id = ?", (user_id, bookmark_id))

    def save_context(self, context_id: str, user_id: str, query: str, sources: List[SourceDoc]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = json.dumps([doc.model_dump(mode="json") for doc in sources])
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO contexts (context_id, user_id, query, sources_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(context_id) DO UPDATE SET
                    query = excluded.query,
                    sources_json = excluded.sources_json,
                    created_at = excluded.created_at
                """,
                (context_id, user_id, query, payload, now_iso),
            )

    def get_context(self, context_id: str, user_id: str) -> tuple[str, List[SourceDoc]] | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT query, sources_json FROM contexts WHERE context_id = ? AND user_id = ?",
                (context_id, user_id),
            ).fetchone()
        if not row:
            return None
        docs_raw = json.loads(row["sources_json"])
        docs = [SourceDoc.model_validate(item) for item in docs_raw]
        return row["query"], docs

    def canonicalize_url(self, url: str, source: str, title: str) -> str:
        clean = (url or "").strip()
        if not clean:
            return f"urn:{source}:{self.title_hash(title)}"
        parsed = urlparse(clean)
        netloc = parsed.netloc.lower().replace("www.", "")
        path = re.sub(r"/+", "/", parsed.path or "/")
        query_pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
        query = urlencode(sorted(query_pairs))
        return urlunparse((parsed.scheme or "https", netloc, path.rstrip("/") or "/", "", query, ""))

    def title_hash(self, title: str) -> str:
        clean = " ".join((title or "").lower().split())
        return md5(clean.encode("utf-8")).hexdigest()

    def chunk_id(self, canonical_url: str, chunk_index: int) -> str:
        return f"{canonical_url}::chunk::{chunk_index}"

    def _chunk_doc(self, doc: SourceDoc) -> List[str]:
        parts = [doc.title.strip()]
        if doc.summary.strip():
            parts.append(doc.summary.strip())
        if doc.citation_snippet.strip() and doc.citation_snippet.strip() not in doc.summary:
            parts.append(doc.citation_snippet.strip())
        combined = " ".join(part for part in parts if part).strip()
        if not combined:
            return []

        sentences = [item.strip() for item in re.split(r"(?<=[.!?])\s+", combined) if item.strip()]
        if not sentences:
            sentences = [combined]

        chunks: List[str] = []
        buffer = ""
        for sentence in sentences:
            proposed = f"{buffer} {sentence}".strip() if buffer else sentence
            if buffer and len(proposed) > settings.chunk_max_chars:
                chunks.append(buffer)
                buffer = sentence
            else:
                buffer = proposed
        if buffer:
            chunks.append(buffer)
        return chunks[:8]

    def _row_to_doc(self, row: sqlite3.Row) -> SourceDoc:
        published = None
        if row["published_at"]:
            try:
                published = datetime.fromisoformat(row["published_at"])
            except Exception:
                published = None

        research = None
        sports = None
        entity_tags = []
        try:
            if row["research_json"]:
                research = json.loads(row["research_json"])
            if row["sports_json"]:
                sports = json.loads(row["sports_json"])
            if row["entity_tags_json"]:
                entity_tags = json.loads(row["entity_tags_json"])
        except Exception:
            pass

        return SourceDoc(
            title=row["title"],
            summary=row["summary"],
            url=row["raw_url"],
            source=row["source"],
            category=row["category"],
            published_at=published,
            source_type=row["source_type"],
            bias_label=row["bias_label"],
            credibility_score=float(row["credibility_score"]),
            entity_tags=entity_tags,
            research_metadata=research,
            sports_metadata=sports,
        )

    def _hash_password(self, password: str) -> str:
        salt = secrets.token_hex(16)
        digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
        return f"{salt}${digest}"

    def _verify_password(self, password: str, stored_value: str) -> bool:
        try:
            salt, expected = stored_value.split("$", 1)
        except ValueError:
            return False
        digest = pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()
        return secrets.compare_digest(digest, expected)
