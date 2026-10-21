import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.modules.artifacts.constants import ArtifactStatus
from app.modules.artifacts.models import Artifact
from app.shared.errors import ConflictError


@dataclass(frozen=True)
class ArtifactKey:
    """Everything of the unique key except `variant`: what was asked, from which material, with
    which prompt and model."""

    session_id: uuid.UUID
    kind: str
    params_hash: str
    context_hash: str
    prompt_version: str
    llm_model: str


class ArtifactRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _matches(key: ArtifactKey):
        return (
            Artifact.session_id == key.session_id,
            Artifact.kind == key.kind,
            Artifact.params_hash == key.params_hash,
            Artifact.context_hash == key.context_hash,
            Artifact.prompt_version == key.prompt_version,
            Artifact.llm_model == key.llm_model,
        )

    def find(self, key: ArtifactKey, variant: int) -> Artifact | None:
        stmt = select(Artifact).where(*self._matches(key), Artifact.variant == variant)
        return self.db.scalar(stmt)

    def next_variant(self, key: ArtifactKey) -> int:
        current = self.db.scalar(select(func.max(Artifact.variant)).where(*self._matches(key)))
        return 0 if current is None else current + 1

    def claim(
        self, key: ArtifactKey, *, variant: int, user_id: uuid.UUID, params: dict
    ) -> tuple[Artifact, bool]:
        """Inserts a pending row for this key, or returns the row that is already there.

        The unique key is the lock: two identical requests at the same time cannot both insert,
        the second waits for the first and then gets its row. Only the one that returns
        `created=True` may start the generation.
        """
        stmt = (
            pg_insert(Artifact)
            .values(
                user_id=user_id,
                session_id=key.session_id,
                kind=key.kind,
                params=params,
                params_hash=key.params_hash,
                context_hash=key.context_hash,
                prompt_version=key.prompt_version,
                llm_model=key.llm_model,
                variant=variant,
                status=ArtifactStatus.PENDING.value,
            )
            .on_conflict_do_nothing(constraint="uq_artifacts_key")
            .returning(Artifact.id)
        )
        new_id = self.db.execute(stmt).scalar_one_or_none()
        if new_id is not None:
            return self.db.execute(select(Artifact).where(Artifact.id == new_id)).scalar_one(), True
        existing = self.find(key, variant)
        if existing is None:  # deleted between the conflict and the read
            raise ConflictError("The quiz was just removed. Please try again.")
        return existing, False

    def count_active(self, session_id: uuid.UUID, user_id: uuid.UUID, kind: str) -> int:
        """Quizzes that count against the per-session limit: everything that did not fail."""
        stmt = select(func.count()).where(
            Artifact.session_id == session_id,
            Artifact.user_id == user_id,
            Artifact.kind == kind,
            Artifact.status != ArtifactStatus.FAILED.value,
        )
        return self.db.scalar(stmt) or 0

    def get(self, artifact_id: uuid.UUID) -> Artifact | None:
        """No ownership check: for the worker, which acts on behalf of the system."""
        return self.db.get(Artifact, artifact_id)

    def get_for_update(self, artifact_id: uuid.UUID) -> Artifact | None:
        stmt = select(Artifact).where(Artifact.id == artifact_id).with_for_update()
        return self.db.scalar(stmt)

    def get_owned(self, artifact_id: uuid.UUID, user_id: uuid.UUID) -> Artifact | None:
        stmt = select(Artifact).where(Artifact.id == artifact_id, Artifact.user_id == user_id)
        return self.db.scalar(stmt)

    def list_for_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[Artifact], int]:
        scope = (Artifact.session_id == session_id, Artifact.user_id == user_id)
        total = self.db.scalar(select(func.count()).where(*scope)) or 0
        stmt = (
            select(Artifact)
            .where(*scope)
            .order_by(Artifact.created_at.desc(), Artifact.id)
            .limit(limit)
            .offset(offset)
        )
        return list(self.db.scalars(stmt)), total

    def delete(self, artifact: Artifact) -> None:
        self.db.delete(artifact)
