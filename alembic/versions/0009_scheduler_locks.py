"""Add database scheduler lease fallback.

Revision ID: 0009_scheduler_locks
Revises: 0008_conversations_sharing
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_scheduler_locks"
down_revision = "0008_conversations_sharing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduler_locks",
        sa.Column("lock_name", sa.Text(), primary_key=True),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("scheduler_locks")
