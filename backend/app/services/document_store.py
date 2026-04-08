import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from hashlib import md5
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from backend.app.models import AlertDeliverySettings, AlertRule, BookmarkItem, Category, SourceDoc, UserProfile


class DocumentStore:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
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

    def upsert_documents(self, docs: List[SourceDoc], embeddings: dict[str, List[float]] | None = None) -> int:
        inserted = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        embeddings = embeddings or {}
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
            rows = conn.execute(sql, [*categories, limit]).fetchall()
        for row in rows:
            try:
                out[row["canonical_url"]] = json.loads(row["embedding_json"])
            except Exception:
                continue
        return out

    def get_query_cache(self, query_key: str, max_age_minutes: int = 20) -> str | None:
        with self._connect() as conn:
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

    def put_query_cache(self, query_key: str, payload: dict) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
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

    def upsert_profile(self, profile: UserProfile) -> UserProfile:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO user_follows (user_id, entity, created_at) VALUES (?, ?, ?)",
                (user_id, normalized, now_iso),
            )
        return self.get_follows(user_id)

    def get_follows(self, user_id: str) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT entity FROM user_follows WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        return [row["entity"] for row in rows]

    def add_alert(self, rule: AlertRule) -> AlertRule:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO user_alerts (user_id, query, categories_json, enabled, last_triggered_at)
                VALUES (?, ?, ?, ?, NULL)
                """,
                (rule.user_id, rule.query, json.dumps(rule.categories), int(rule.enabled)),
            )
            alert_id = int(cursor.lastrowid)
        return AlertRule(id=alert_id, user_id=rule.user_id, query=rule.query, categories=rule.categories, enabled=rule.enabled)

    def get_alerts(self, user_id: str) -> List[AlertRule]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM user_alerts WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
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

    def upsert_alert_delivery(self, settings_obj: AlertDeliverySettings) -> AlertDeliverySettings:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
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
        with self._connect() as conn:
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
        with self._connect() as conn:
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

    def get_bookmarks(self, user_id: str) -> List[BookmarkItem]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_bookmarks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
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
        with self._connect() as conn:
            conn.execute("DELETE FROM user_bookmarks WHERE user_id = ? AND id = ?", (user_id, bookmark_id))

    def save_context(self, context_id: str, user_id: str, query: str, sources: List[SourceDoc]) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        payload = json.dumps([doc.model_dump(mode="json") for doc in sources])
        with self._connect() as conn:
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
        with self._connect() as conn:
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
