import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update
from sqlalchemy.orm import Session

from app.modules.cache.models import CacheEntry, CacheEntryCitation
from app.modules.cache.schemas import CacheContext

SIMILAR_CANDIDATES = 5


class CacheRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _scope(
        session_id: uuid.UUID, user_id: uuid.UUID, latin_only: bool, context: CacheContext
    ) -> tuple:
        return (
            CacheEntry.session_id == session_id,
            CacheEntry.user_id == user_id,
            CacheEntry.latin_only == latin_only,
            CacheEntry.embedding_model == context.embedding_model,
            CacheEntry.llm_model == context.llm_model,
            CacheEntry.prompt_version == context.prompt_version,
            CacheEntry.top_k == context.top_k,
        )

    def find_exact(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        latin_only: bool,
        context: CacheContext,
        question_hash: str,
    ) -> CacheEntry | None:
        stmt = (
            select(CacheEntry)
            .where(
                *self._scope(session_id, user_id, latin_only, context),
                CacheEntry.question_hash == question_hash,
            )
            .order_by(CacheEntry.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def find_similar(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        latin_only: bool,
        context: CacheContext,
        vector: list[float],
        min_similarity: float,
    ) -> list[CacheEntry]:
        """The closest entries above the threshold, best first. Several, because the caller may
        reject the nearest one (see `meaning_markers`)."""
        # No vector index on purpose: a session holds a few dozen entries at most, and the
        # session filter already narrows the scan to those.
        distance = CacheEntry.question_embedding.cosine_distance(vector)
        stmt = (
            select(CacheEntry)
            .where(
                *self._scope(session_id, user_id, latin_only, context),
                distance <= 1 - min_similarity,
            )
            .order_by(distance)
            .limit(SIMILAR_CANDIDATES)
        )
        return list(self.db.scalars(stmt))

    def citations(self, entry_id: uuid.UUID) -> list[CacheEntryCitation]:
        stmt = (
            select(CacheEntryCitation)
            .where(CacheEntryCitation.cache_entry_id == entry_id)
            .order_by(CacheEntryCitation.rank)
        )
        return list(self.db.scalars(stmt))

    def record_hit(self, entry_id: uuid.UUID) -> None:
        self.db.execute(
            update(CacheEntry)
            .where(CacheEntry.id == entry_id)
            .values(hit_count=CacheEntry.hit_count + 1)
        )

    def add(self, entry: CacheEntry, citations: list[CacheEntryCitation]) -> None:
        self.db.add(entry)
        self.db.flush()  # the citations need the entry's row to exist
        self.db.add_all(citations)
        self.db.flush()

    def delete(self, entry_id: uuid.UUID) -> None:
        self.db.execute(delete(CacheEntry).where(CacheEntry.id == entry_id))

    def delete_same_question(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        latin_only: bool,
        context: CacheContext,
        question_hash: str,
    ) -> None:
        self.db.execute(
            delete(CacheEntry).where(
                *self._scope(session_id, user_id, latin_only, context),
                CacheEntry.question_hash == question_hash,
            )
        )

    def delete_session(self, session_id: uuid.UUID, user_id: uuid.UUID) -> int:
        # DELETE yields a CursorResult (has rowcount); Session.execute is typed as plain Result.
        result = cast(
            "CursorResult[Any]",
            self.db.execute(
                delete(CacheEntry).where(
                    CacheEntry.session_id == session_id, CacheEntry.user_id == user_id
                )
            ),
        )
        return result.rowcount
