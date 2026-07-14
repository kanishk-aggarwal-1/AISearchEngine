"""Add MFA and email-change persistence.

Revision ID: 0005_identity_features
Revises: 0004_search_feedback
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_identity_features"
down_revision = "0004_search_feedback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("auth_users") as batch_op:
        batch_op.add_column(sa.Column("mfa_secret", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("mfa_enabled", sa.Integer(), nullable=False, server_default="0"))
    op.create_table(
        "auth_email_change_tokens",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("new_email", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_at", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("auth_email_change_tokens")
    with op.batch_alter_table("auth_users") as batch_op:
        batch_op.drop_column("mfa_enabled")
        batch_op.drop_column("mfa_secret")
