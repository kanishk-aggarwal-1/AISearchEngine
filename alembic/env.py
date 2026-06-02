from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.app.config import settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _alembic_database_url() -> str:
    """
    Returns the SQLAlchemy URL for Alembic.

    * PostgreSQL  — used in production; full migration support.
    * SQLite      — used in development/CI; schema is managed by
                    DocumentStore._init_db(), so migrations are only run to
                    validate the migration files themselves.  The data directory
                    is created automatically so the CI runner never hits
                    'unable to open database file'.
    """
    if settings.using_postgres:
        return settings.database_url

    db_path = settings.sqlite_database_path
    if db_path and db_path not in (":memory:", ""):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    return f"sqlite:///{db_path}"


config.set_main_option("sqlalchemy.url", _alembic_database_url())
target_metadata = None


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
