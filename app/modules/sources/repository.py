import uuid

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.modules.sources.models import Chunk, Source, SourceStatus


class SourceRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock_session_sources(self, session_id: uuid.UUID) -> None:
        # Serializes concurrent uploads into one session until the transaction ends, so the
        # "at most N sources" check cannot be raced.
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"sources:{session_id}"},
        )

    def count_active(self, session_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Source)
            .where(Source.session_id == session_id, Source.status != SourceStatus.DELETED)
        )
        return self.db.scalar(stmt) or 0

    def active_hashes(self, session_id: uuid.UUID) -> set[str]:
        stmt = select(Source.content_hash).where(
            Source.session_id == session_id, Source.status != SourceStatus.DELETED
        )
        return set(self.db.scalars(stmt))

    def add(self, **fields) -> Source:
        source = Source(**fields)
        self.db.add(source)
        self.db.flush()
        return source

    def get_owned(
        self, source_id: uuid.UUID, user_id: uuid.UUID, for_update: bool = False
    ) -> Source | None:
        stmt = select(Source).where(
            Source.id == source_id,
            Source.user_id == user_id,
            Source.status != SourceStatus.DELETED,
        )
        if for_update:
            stmt = stmt.with_for_update()
        return self.db.scalar(stmt)

    def list_for_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> list[Source]:
        stmt = (
            select(Source)
            .where(
                Source.session_id == session_id,
                Source.user_id == user_id,
                Source.status != SourceStatus.DELETED,
            )
            .order_by(Source.created_at.desc(), Source.id)
        )
        return list(self.db.scalars(stmt))

    def get_for_update(self, source_id: uuid.UUID) -> Source | None:
        """Any status, no ownership check: for the worker, which acts on behalf of the system."""
        return self.db.scalar(select(Source).where(Source.id == source_id).with_for_update())

    def delete_chunks(self, source_id: uuid.UUID) -> None:
        self.db.execute(delete(Chunk).where(Chunk.source_id == source_id))

    def add_chunks(self, chunks: list[Chunk]) -> None:
        self.db.add_all(chunks)
        self.db.flush()

    def storage_keys_for_session(self, session_id: uuid.UUID) -> list[str]:
        stmt = select(Source.storage_key).where(
            Source.session_id == session_id, Source.storage_key.is_not(None)
        )
        return list(self.db.scalars(stmt))

    def mark_failed(self, source_id: uuid.UUID, message: str) -> Source | None:
        """Returns the updated source, or None if it is gone (the caller commits)."""
        source = self.get_for_update(source_id)
        if source is None or source.status == SourceStatus.DELETED:
            return None
        source.status = SourceStatus.FAILED.value
        source.error = message
        return source
