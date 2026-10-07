import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.shared.db import Base, IdMixin, TimestampMixin


class StudySession(IdMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    corpus_version: Mapped[int] = mapped_column(default=0)
    cache_enabled: Mapped[bool] = mapped_column(default=True)
    embedding_model: Mapped[str] = mapped_column(String(100))
