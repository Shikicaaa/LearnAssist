import logging
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.modules.sessions.models import StudySession
from app.modules.sessions.repository import SessionRepository
from app.shared.config import get_settings
from app.shared.errors import NotFoundError, QuotaExceededError

logger = logging.getLogger(__name__)

# A delete hook runs inside the delete transaction, before the session row disappears, and may
# return a callback that is run only after the commit succeeded (e.g. removing files from disk).
DeleteHook = Callable[[Session, uuid.UUID], Callable[[], None] | None]
_delete_hooks: list[DeleteHook] = []


def register_delete_hook(hook: DeleteHook) -> None:
    if hook not in _delete_hooks:
        _delete_hooks.append(hook)


class SessionService:
    def __init__(self, db: Session):
        self.db = db
        self.repo = SessionRepository(db)

    def create(self, user_id: uuid.UUID, title: str) -> StudySession:
        settings = get_settings()
        self.repo.lock_user_quota(user_id)
        if self.repo.count_for_user(user_id) >= settings.max_sessions_per_user:
            raise QuotaExceededError(
                f"Session limit reached ({settings.max_sessions_per_user}). Delete a session first."
            )
        session = self.repo.add(user_id, title, settings.embedding_model)
        self.db.commit()
        return session

    def get_owned(self, user_id: uuid.UUID, session_id: uuid.UUID) -> StudySession:
        session = self.repo.get_owned(session_id, user_id)
        if session is None:
            raise NotFoundError("Session not found")
        return session

    def list(self, user_id: uuid.UUID, limit: int, offset: int) -> tuple[list[StudySession], int]:
        return (
            self.repo.list_for_user(user_id, limit, offset),
            self.repo.count_for_user(user_id),
        )

    def update(
        self,
        user_id: uuid.UUID,
        session_id: uuid.UUID,
        title: str | None,
        cache_enabled: bool | None,
    ) -> StudySession:
        session = self.get_owned(user_id, session_id)
        if title is not None:
            session.title = title
        if cache_enabled is not None:
            session.cache_enabled = cache_enabled
        self.db.commit()
        return session

    def delete(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        self.get_owned(user_id, session_id)
        after_commit = [hook(self.db, session_id) for hook in _delete_hooks]
        self.repo.delete(session_id, user_id)
        self.db.commit()
        for action in after_commit:
            if action is None:
                continue
            try:
                action()
            except Exception:
                # The session is already gone; a failed cleanup must not turn that into an error.
                logger.exception("Cleanup after session deletion failed")


def bump_corpus_version(db: Session, session_id: uuid.UUID) -> int:
    """Increments corpus_version inside the caller's transaction (does not commit)."""
    new_version = SessionRepository(db).increment_corpus_version(session_id)
    if new_version is None:
        raise NotFoundError("Session not found")
    return new_version
