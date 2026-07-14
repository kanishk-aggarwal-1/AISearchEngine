"""Add OAuth identities and passkeys.

Revision ID: 0010_oauth_passkeys
Revises: 0009_scheduler_locks
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_oauth_passkeys"
down_revision = "0009_scheduler_locks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("auth_identities", sa.Column("provider", sa.Text(), primary_key=True), sa.Column("subject", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False))
    op.create_table("passkey_credentials", sa.Column("credential_id", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.Column("public_key", sa.Text(), nullable=False), sa.Column("sign_count", sa.Integer(), nullable=False), sa.Column("transports_json", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False), sa.Column("last_used_at", sa.Text()))
    op.create_table("passkey_challenges", sa.Column("challenge_id", sa.Text(), primary_key=True), sa.Column("user_id", sa.Text(), nullable=False), sa.Column("challenge", sa.Text(), nullable=False), sa.Column("purpose", sa.Text(), nullable=False), sa.Column("created_at", sa.Text(), nullable=False), sa.Column("expires_at", sa.Text(), nullable=False))
    op.create_index("idx_passkey_credentials_user", "passkey_credentials", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_passkey_credentials_user", table_name="passkey_credentials")
    op.drop_table("passkey_challenges")
    op.drop_table("passkey_credentials")
    op.drop_table("auth_identities")
