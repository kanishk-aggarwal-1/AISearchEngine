"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-11 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonical_url", sa.Text(), nullable=False, unique=True),
        sa.Column("raw_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_hash", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("bias_label", sa.Text(), nullable=False),
        sa.Column("credibility_score", sa.Float(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("inserted_at", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("entity_tags_json", sa.Text(), nullable=True),
        sa.Column("research_json", sa.Text(), nullable=True),
        sa.Column("sports_json", sa.Text(), nullable=True),
    )
    op.create_index("idx_documents_category_published", "documents", ["category", "published_at"])
    op.create_index("idx_documents_source", "documents", ["source"])
    op.create_index("idx_documents_inserted_at", "documents", ["inserted_at"])

    op.create_table(
        "query_cache",
        sa.Column("query_key", sa.Text(), primary_key=True),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_query_cache_updated_at", "query_cache", ["updated_at"])

    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("preferred_categories_json", sa.Text(), nullable=False),
        sa.Column("explanation_mode", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "auth_users",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("is_admin", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("email_verified", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "auth_sessions",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("last_seen_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_auth_sessions_user", "auth_sessions", ["user_id", "last_seen_at"])

    op.create_table(
        "auth_verification_tokens",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_at", sa.Text(), nullable=True),
    )

    op.create_table(
        "auth_password_reset_tokens",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
        sa.Column("used_at", sa.Text(), nullable=True),
    )

    op.create_table(
        "user_follows",
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("entity", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "entity", name="uq_user_follows_user_entity"),
    )

    op.create_table(
        "search_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("categories_json", sa.Text(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_search_history_user_created", "search_history", ["user_id", "created_at"])

    op.create_table(
        "saved_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("context_id", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "context_id", name="uq_saved_sessions_user_context"),
    )

    op.create_table(
        "source_status",
        sa.Column("source_name", sa.Text(), primary_key=True),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("last_success_at", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=False),
        sa.Column("last_error_at", sa.Text(), nullable=True),
        sa.Column("last_item_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "user_alerts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("categories_json", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("last_triggered_at", sa.Text(), nullable=True),
    )
    op.create_index("idx_user_alerts_user_enabled", "user_alerts", ["user_id", "enabled"])

    op.create_table(
        "alert_delivery_settings",
        sa.Column("user_id", sa.Text(), primary_key=True),
        sa.Column("webhook_url", sa.Text(), nullable=False),
        sa.Column("digest_mode", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "user_bookmarks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint("user_id", "canonical_url", name="uq_user_bookmarks_user_url"),
    )
    op.create_index("idx_user_bookmarks_user_created", "user_bookmarks", ["user_id", "created_at"])

    op.create_table(
        "contexts",
        sa.Column("context_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "document_chunks",
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("chunk_id", sa.Text(), primary_key=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Text(), nullable=True),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.Text(), nullable=True),
        sa.Column("inserted_at", sa.Text(), nullable=False),
    )
    op.create_index("idx_document_chunks_category_published", "document_chunks", ["category", "published_at"])
    op.create_index("idx_document_chunks_canonical", "document_chunks", ["canonical_url", "chunk_index"])


def downgrade() -> None:
    op.drop_index("idx_document_chunks_canonical", table_name="document_chunks")
    op.drop_index("idx_document_chunks_category_published", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("contexts")
    op.drop_index("idx_user_bookmarks_user_created", table_name="user_bookmarks")
    op.drop_table("user_bookmarks")
    op.drop_table("alert_delivery_settings")
    op.drop_index("idx_user_alerts_user_enabled", table_name="user_alerts")
    op.drop_table("user_alerts")
    op.drop_table("source_status")
    op.drop_table("saved_sessions")
    op.drop_index("idx_search_history_user_created", table_name="search_history")
    op.drop_table("search_history")
    op.drop_table("user_follows")
    op.drop_table("auth_password_reset_tokens")
    op.drop_table("auth_verification_tokens")
    op.drop_index("idx_auth_sessions_user", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
    op.drop_table("user_profiles")
    op.drop_index("idx_query_cache_updated_at", table_name="query_cache")
    op.drop_table("query_cache")
    op.drop_index("idx_documents_inserted_at", table_name="documents")
    op.drop_index("idx_documents_source", table_name="documents")
    op.drop_index("idx_documents_category_published", table_name="documents")
    op.drop_table("documents")
