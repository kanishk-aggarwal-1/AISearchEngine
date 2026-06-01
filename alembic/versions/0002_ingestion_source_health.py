"""ingestion and source health observability

Revision ID: 0002_ingestion_source_health
Revises: 0001_initial_schema
Create Date: 2026-05-12 14:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_ingestion_source_health"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("source_status", sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("source_status", sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("source_status", sa.Column("last_attempt_at", sa.Text(), nullable=True))
    op.add_column("source_status", sa.Column("average_latency_ms", sa.Float(), nullable=True))

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger_type", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("categories_json", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("inserted_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
    )
    op.create_index("idx_ingestion_runs_started", "ingestion_runs", ["started_at"])
    op.create_index("idx_ingestion_runs_status", "ingestion_runs", ["status", "started_at"])


def downgrade() -> None:
    op.drop_index("idx_ingestion_runs_status", table_name="ingestion_runs")
    op.drop_index("idx_ingestion_runs_started", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
    op.drop_column("source_status", "average_latency_ms")
    op.drop_column("source_status", "last_attempt_at")
    op.drop_column("source_status", "failure_count")
    op.drop_column("source_status", "success_count")
