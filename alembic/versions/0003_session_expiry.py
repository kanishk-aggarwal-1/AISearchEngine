"""Add expires_at to auth_sessions for token TTL enforcement

Revision ID: 0003_session_expiry
Revises: 0002_ingestion_source_health
Create Date: 2026-06-01 00:00:00.000000

Why: Sessions previously had no expiry, so a stolen token remained valid
forever.  This migration adds a 30-day TTL column and backfills existing
rows so the column satisfies NOT NULL without breaking live deployments.
"""

from alembic import op
import sqlalchemy as sa


revision = "0003_session_expiry"
down_revision = "0002_ingestion_source_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add the column as nullable first so the backfill can run before
    # we enforce NOT NULL — avoids a full table lock on Postgres.
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("expires_at", sa.Text(), nullable=True)
        )

    # Backfill: grant existing sessions 30 days from their creation date.
    # Use dialect-specific SQL for SQLite vs PostgreSQL
    from alembic.migration import MigrationContext
    ctx = MigrationContext.configure(op.get_bind())
    dialect = ctx.dialect.name

    if dialect == "sqlite":
        # SQLite syntax
        op.execute(
            "UPDATE auth_sessions SET expires_at = datetime(created_at, '+30 days') "
            "WHERE expires_at IS NULL"
        )
    else:
        # PostgreSQL syntax
        op.execute(
            "UPDATE auth_sessions SET expires_at = (created_at + interval '30 days') "
            "WHERE expires_at IS NULL"
        )

    # Tighten to NOT NULL now that every row has a value.
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.alter_column("expires_at", nullable=False)

    op.create_index(
        "idx_auth_sessions_expires",
        "auth_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_auth_sessions_expires", table_name="auth_sessions")
    with op.batch_alter_table("auth_sessions") as batch_op:
        batch_op.drop_column("expires_at")
