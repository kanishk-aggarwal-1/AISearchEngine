"""Add bookmark organization fields.

Revision ID: 0006_bookmark_organization
Revises: 0005_identity_features
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_bookmark_organization"
down_revision = "0005_identity_features"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_bookmarks") as batch_op:
        batch_op.add_column(sa.Column("folder", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("tags_json", sa.Text(), nullable=False, server_default="[]"))
        batch_op.add_column(sa.Column("notes", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    with op.batch_alter_table("user_bookmarks") as batch_op:
        batch_op.drop_column("notes")
        batch_op.drop_column("tags_json")
        batch_op.drop_column("folder")
