import uuid

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session

from app.modules.sessions.models import StudySession


class SessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def lock_user_quota(self, user_id: uuid.UUID) -> None:
        # The advisory lock lasts until the end of the transaction and serializes concurrent
        # session creation by the same user.
        self.db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"sessions:{user_id}"},
        )

    def count_for_user(self, user_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(StudySession).where(StudySession.user_id == user_id)
        return self.db.scalar(stmt) or 0

    def add(self, user_id: uuid.UUID, title: str, embedding_model: str) -> StudySession:
        session = StudySession(user_id=user_id, title=title, embedding_model=embedding_model)
        self.db.add(session)
        self.db.flush()
        return session

    def get_owned(self, session_id: uuid.UUID, user_id: uuid.UUID) -> StudySession | None:
        stmt = select(StudySession).where(
            StudySession.id == session_id, StudySession.user_id == user_id
        )
        return self.db.scalar(stmt)

    def list_for_user(self, user_id: uuid.UUID, limit: int, offset: int) -> list[StudySession]:
        stmt = (
            select(StudySession)
            .where(StudySession.user_id == user_id)
            .order_by(StudySession.created_at.desc(), StudySession.id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt))

    def delete(self, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.db.execute(
            delete(StudySession).where(
                StudySession.id == session_id, StudySession.user_id == user_id
            )
        )

    def increment_corpus_version(self, session_id: uuid.UUID) -> int | None:
        stmt = (
            update(StudySession)
            .where(StudySession.id == session_id)
            .values(corpus_version=StudySession.corpus_version + 1)
            .returning(StudySession.corpus_version)
        )
        return self.db.scalar(stmt)
