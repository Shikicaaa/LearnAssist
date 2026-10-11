import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base, IdMixin, TimestampMixin


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(10))
    content: Mapped[str] = mapped_column(Text)
    cached: Mapped[bool] = mapped_column(Boolean, default=False)
    # Filled in by the cache (a later phase); there is no table to point a foreign key at yet.
    cache_entry_id: Mapped[uuid.UUID | None] = mapped_column(default=None)
    llm_provider: Mapped[str | None] = mapped_column(String(30), default=None)
    llm_model: Mapped[str | None] = mapped_column(String(100), default=None)
    prompt_version: Mapped[str | None] = mapped_column(String(30), default=None)
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        Index("ix_messages_session_created", "session_id", "created_at"),
    )


class MessageCitation(IdMixin, TimestampMixin, Base):
    __tablename__ = "message_citations"

    message_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), index=True
    )
    # SET NULL, not CASCADE: deleting a source must not erase what an old answer cited.
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="SET NULL"), default=None
    )
    source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), default=None
    )
    rank: Mapped[int]
    score: Mapped[float] = mapped_column(Float)
    # Copied at answer time so the citation stays readable after the source is gone.
    snapshot_source_title: Mapped[str] = mapped_column(String(255))
    snapshot_page: Mapped[int | None] = mapped_column(default=None)
    snapshot_page_end: Mapped[int | None] = mapped_column(default=None)

    __table_args__ = (
        UniqueConstraint("message_id", "rank", name="uq_message_citations_rank"),
    )
