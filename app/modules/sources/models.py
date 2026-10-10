import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.embeddings import embedding_dim
from app.shared.db import Base, IdMixin, TimestampMixin


class SourceStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class SourceType(StrEnum):
    FILE = "file"
    TEXT = "text"


class Source(IdMixin, TimestampMixin, Base):
    __tablename__ = "sources"

    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str | None] = mapped_column(String(255), default=None)
    mime: Mapped[str | None] = mapped_column(String(100), default=None)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str | None] = mapped_column(String(512), default=None)
    content_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default=SourceStatus.QUEUED.value)
    page_count: Mapped[int | None] = mapped_column(default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    __table_args__ = (
        # The same content may be added once per session, but a deleted source frees the slot.
        Index(
            "uq_sources_session_hash_active",
            "session_id",
            "content_hash",
            unique=True,
            postgresql_where=sql_text("status <> 'deleted'"),
        ),
        CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed', 'deleted')",
            name="ck_sources_status",
        ),
        CheckConstraint("type IN ('file', 'text')", name="ck_sources_type"),
    )


class Chunk(IdMixin, TimestampMixin, Base):
    __tablename__ = "chunks"

    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    chunk_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    page_start: Mapped[int | None] = mapped_column(default=None)
    page_end: Mapped[int | None] = mapped_column(default=None)
    char_start: Mapped[int]
    char_end: Mapped[int]
    added_in_version: Mapped[int]
    embedding_model: Mapped[str] = mapped_column(String(100))
    embedding: Mapped[list[float]] = mapped_column(Vector(embedding_dim()))

    __table_args__ = (
        UniqueConstraint("source_id", "chunk_index", name="uq_chunks_source_index"),
        Index("ix_chunks_session_id", "session_id"),
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
