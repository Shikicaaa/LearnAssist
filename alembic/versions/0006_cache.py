"""cache entries and their citations; messages.cache_entry_id becomes a foreign key

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-11
"""

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

EMBEDDING_DIM = 384  # must match the chunks table; changing the model means a new migration


def upgrade() -> None:
    op.create_table(
        "cache_entries",
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
        sa.Column("question_hash", sa.String(64), nullable=False),
        sa.Column("question_norm", sa.Text(), nullable=False),
        sa.Column("question_embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("latin_only", sa.Boolean(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("corpus_version", sa.Integer(), nullable=False),
        sa.Column("kth_score", sa.Float(), nullable=False),
        sa.Column("embedding_model", sa.String(100), nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(30), nullable=False),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("cited_chunks", sa.Integer(), nullable=False),
        sa.Column("hit_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cache_entries_session_hash", "cache_entries", ["session_id", "question_hash"]
    )

    op.create_table(
        "cache_entry_citations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "cache_entry_id",
            sa.Uuid(),
            sa.ForeignKey("cache_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "chunk_id", sa.Uuid(), sa.ForeignKey("chunks.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("source_title", sa.String(255), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_cache_entry_citations_cache_entry_id", "cache_entry_citations", ["cache_entry_id"]
    )

    op.create_foreign_key(
        "fk_messages_cache_entry_id",
        "messages",
        "cache_entries",
        ["cache_entry_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_messages_cache_entry_id", "messages", type_="foreignkey")
    op.drop_table("cache_entry_citations")
    op.drop_table("cache_entries")
