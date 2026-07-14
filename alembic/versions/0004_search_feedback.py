"""Add search feedback storage.

Revision ID: 0004_search_feedback
Revises: 0003_session_expiry
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_search_feedback"
down_revision = "0003_session_expiry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_feedback",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=False),
        sa.Column("helpful", sa.Integer(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_search_feedback_context", "search_feedback", ["context_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_search_feedback_context", table_name="search_feedback")
    op.drop_table("search_feedback")
