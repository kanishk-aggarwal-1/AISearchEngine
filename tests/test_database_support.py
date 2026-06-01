import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app.services.document_store import DocumentStore
from backend.app.services.store_factory import create_store


class DatabaseSupportTests(unittest.TestCase):
    def test_create_store_uses_sqlite_fallback_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "fallback.db")
            with patch("backend.app.services.store_factory.settings.database_url", ""), patch(
                "backend.app.services.store_factory.settings.sqlite_database_path", db_path
            ):
                store = create_store()
            self.assertIsInstance(store, DocumentStore)
            self.assertEqual(store.db_path, Path(db_path))

    def test_create_store_accepts_sqlite_database_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "url_store.db"
            database_url = f"sqlite:///{db_path.as_posix()}"
            with patch("backend.app.services.store_factory.settings.database_url", database_url), patch(
                "backend.app.services.store_factory.settings.sqlite_database_path", "unused.db"
            ):
                store = create_store()
            self.assertIsInstance(store, DocumentStore)
            self.assertEqual(store.db_path, db_path)


if __name__ == "__main__":
    unittest.main()
