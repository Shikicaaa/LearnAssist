import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base, IdMixin, TimestampMixin


class Artifact(IdMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(30))  # 'quiz'
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | ready | failed
    error: Mapped[str | None] = mapped_column(Text, default=None)
    params: Mapped[dict] = mapped_column(JSONB)
    params_hash: Mapped[str] = mapped_column(String(64))
    context_hash: Mapped[str] = mapped_column(String(64))
    variant: Mapped[int] = mapped_column(default=0)
    content: Mapped[dict | None] = mapped_column(JSONB, default=None)
    llm_provider: Mapped[str | None] = mapped_column(String(30), default=None)
    llm_model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(30))
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "kind",
            "params_hash",
            "context_hash",
            "prompt_version",
            "llm_model",
            "variant",
            name="uq_artifacts_key",
        ),
        CheckConstraint("status IN ('pending', 'ready', 'failed')", name="ck_artifacts_status"),
        Index("ix_artifacts_session_created", "session_id", "created_at"),
    )
