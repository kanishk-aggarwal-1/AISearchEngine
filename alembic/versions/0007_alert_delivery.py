"""Add email alert settings and delivery history.

Revision ID: 0007_alert_delivery
Revises: 0006_bookmark_organization
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_alert_delivery"
down_revision = "0006_bookmark_organization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("alert_delivery_settings") as batch_op:
        batch_op.add_column(sa.Column("email_enabled", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("timezone", sa.Text(), nullable=False, server_default="UTC"))
        batch_op.add_column(sa.Column("delivery_hour", sa.Integer(), nullable=False, server_default="9"))
    op.create_table(
        "alert_delivery_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("alert_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("attempted_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_alert_delivery_attempts_user", "alert_delivery_attempts", ["user_id", "attempted_at"])


def downgrade() -> None:
    op.drop_index("idx_alert_delivery_attempts_user", table_name="alert_delivery_attempts")
    op.drop_table("alert_delivery_attempts")
    with op.batch_alter_table("alert_delivery_settings") as batch_op:
        batch_op.drop_column("delivery_hour")
        batch_op.drop_column("timezone")
        batch_op.drop_column("email_enabled")
