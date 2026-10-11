import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.modules.embeddings import embedding_dim
from app.shared.db import Base, IdMixin, TimestampMixin


class CacheEntry(IdMixin, TimestampMixin, Base):
    """A stored answer, valid for one session and one combination of model and prompt."""

    __tablename__ = "cache_entries"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    question_hash: Mapped[str] = mapped_column(String(64))
    question_norm: Mapped[str] = mapped_column(Text)
    question_embedding: Mapped[list[float]] = mapped_column(Vector(embedding_dim()))
    # The answer is written in the script of the question, so a Latin answer must never be served
    # to a question typed in Cyrillic (or the other way round).
    latin_only: Mapped[bool]
    answer: Mapped[str] = mapped_column(Text)
    # The session's corpus_version this answer is known to be valid for.
    corpus_version: Mapped[int]
    # Similarity of the weakest chunk that made it into the top-k when the answer was made.
    kth_score: Mapped[float] = mapped_column(Float)
    embedding_model: Mapped[str] = mapped_column(String(100))
    llm_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(30))
    top_k: Mapped[int]
    # How many citations the entry was created with: if fewer survive, a source was deleted.
    cited_chunks: Mapped[int]
    hit_count: Mapped[int] = mapped_column(default=0)

    __table_args__ = (Index("ix_cache_entries_session_hash", "session_id", "question_hash"),)


class CacheEntryCitation(IdMixin, TimestampMixin, Base):
    __tablename__ = "cache_entry_citations"

    cache_entry_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cache_entries.id", ondelete="CASCADE"), index=True
    )
    # CASCADE: when a chunk disappears the row disappears with it, and the entry notices (see
    # `cited_chunks`) that it can no longer be trusted.
    chunk_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"))
    source_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sources.id", ondelete="CASCADE"))
    rank: Mapped[int]
    score: Mapped[float] = mapped_column(Float)
    source_title: Mapped[str] = mapped_column(String(255))
    page_start: Mapped[int | None] = mapped_column(default=None)
    page_end: Mapped[int | None] = mapped_column(default=None)
