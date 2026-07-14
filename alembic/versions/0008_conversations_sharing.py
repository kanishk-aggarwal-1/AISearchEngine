"""Add conversations and share links.

Revision ID: 0008_conversations_sharing
Revises: 0007_alert_delivery
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_conversations_sharing"
down_revision = "0007_alert_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("conversation_id", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=False), sa.Column("title", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False), sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("conversation_id", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False), sa.Column("content", sa.Text(), nullable=False),
        sa.Column("key_points_json", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "shared_contexts",
        sa.Column("share_token", sa.Text(), primary_key=True), sa.Column("context_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_conversations_user", "conversations", ["user_id", "updated_at"])
    op.create_index("idx_conversation_messages_conversation", "conversation_messages", ["conversation_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_conversation_messages_conversation", table_name="conversation_messages")
    op.drop_index("idx_conversations_user", table_name="conversations")
    op.drop_table("shared_contexts")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
