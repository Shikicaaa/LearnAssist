"""messages and message_citations

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-11
"""
import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("cache_entry_id", sa.Uuid(), nullable=True),
        sa.Column("llm_provider", sa.String(30), nullable=True),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(30), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
    )
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])

    op.create_table(
        "message_citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("snapshot_source_title", sa.String(255), nullable=False),
        sa.Column("snapshot_page", sa.Integer(), nullable=True),
        sa.Column("snapshot_page_end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "rank", name="uq_message_citations_rank"),
    )
    op.create_index("ix_message_citations_message_id", "message_citations", ["message_id"])


def downgrade() -> None:
    op.drop_table("message_citations")
    op.drop_table("messages")
