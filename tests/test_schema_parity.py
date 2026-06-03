"""
Schema parity guard.

The application has two schema sources:
  * DocumentStore._init_db()  — used by SQLite (dev/CI/tests)
  * Alembic migrations        — used by Postgres (production)

If these drift, production breaks in ways the SQLite test suite can't see.
This test builds both schemas on a throwaway SQLite database and asserts they
produce the same tables and columns, turning silent drift into a CI failure.
"""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config

from backend.app.services.document_store import DocumentStore

# documents_v2 is a transient SQLite-only migration artifact (created, copied,
# then renamed to `documents`). It never exists in a finished schema.
_TRANSIENT_TABLES = {"documents_v2", "sqlite_sequence", "alembic_version"}


def _columns_for(db_path: str) -> dict[str, set[str]]:
    """Return {table_name: {column_names}} for a SQLite database."""
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        tables -= _TRANSIENT_TABLES
        schema: dict[str, set[str]] = {}
        for table in tables:
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
            schema[table] = cols
        return schema
    finally:
        conn.close()


class SchemaParityTests(unittest.TestCase):
    def test_init_db_matches_alembic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Schema produced by DocumentStore._init_db()
            init_db_path = str(Path(tmpdir) / "init_db.db")
            DocumentStore(init_db_path)  # __init__ calls _init_db()
            init_schema = _columns_for(init_db_path)

            # 2. Schema produced by running Alembic migrations
            alembic_db_path = str(Path(tmpdir) / "alembic.db")
            cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            with patch(
                "backend.app.config.settings.sqlite_database_path", alembic_db_path
            ), patch("backend.app.config.settings.database_url", ""):
                command.upgrade(cfg, "head")
            alembic_schema = _columns_for(alembic_db_path)

            # 3. Same tables
            init_tables = set(init_schema)
            alembic_tables = set(alembic_schema)
            missing_in_alembic = init_tables - alembic_tables
            missing_in_init = alembic_tables - init_tables
            self.assertEqual(
                missing_in_alembic, set(),
                f"Tables in _init_db() but missing from Alembic migrations: {missing_in_alembic}",
            )
            self.assertEqual(
                missing_in_init, set(),
                f"Tables in Alembic but missing from _init_db(): {missing_in_init}",
            )

            # 4. Same columns per table
            for table in sorted(init_tables & alembic_tables):
                init_cols = init_schema[table]
                alembic_cols = alembic_schema[table]
                self.assertEqual(
                    init_cols, alembic_cols,
                    f"Column drift in '{table}':\n"
                    f"  only in _init_db(): {init_cols - alembic_cols}\n"
                    f"  only in Alembic:    {alembic_cols - init_cols}",
                )


if __name__ == "__main__":
    unittest.main()
