from pathlib import Path

from backend.app.config import settings
from backend.app.services.document_store import DocumentStore


def _sqlite_path_from_url(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return database_url.replace("sqlite:///", "", 1)
    if database_url.startswith("sqlite://"):
        return database_url.replace("sqlite://", "", 1)
    return database_url


def create_store():
    if settings.using_postgres:
        from backend.app.services.postgres_store import PostgresDocumentStore

        return PostgresDocumentStore(settings.database_url)

    if settings.database_url.strip().lower().startswith("sqlite://"):
        return DocumentStore(_sqlite_path_from_url(settings.database_url))

    return DocumentStore(str(Path(settings.sqlite_database_path)))
