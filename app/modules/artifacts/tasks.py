import logging
import uuid

from sqlalchemy.exc import OperationalError

from app.modules.artifacts.constants import QUIZ_TASK, ArtifactStatus
from app.modules.artifacts.generator import InvalidQuizError, NoMaterialError, generate_quiz
from app.modules.artifacts.hashing import context_hash
from app.modules.artifacts.material import select_material
from app.modules.artifacts.repository import ArtifactRepository
from app.modules.embeddings import get_embedder
from app.modules.jobs import PermanentError, TransientError, is_last_attempt, task
from app.modules.llm import LLMError, LLMRateLimitError, LLMUnavailableError, get_llm_provider
from app.shared.db import SessionLocal

logger = logging.getLogger(__name__)

# Errors worth retrying: the database or the model may be back in a moment.
TRANSIENT_ERRORS = (TransientError, OperationalError, ConnectionError, TimeoutError)


@task(QUIZ_TASK)
def generate_quiz_task(artifact_id: str) -> None:
    try:
        _generate(uuid.UUID(artifact_id))
    except PermanentError as exc:
        _fail(artifact_id, str(exc))
    except TRANSIENT_ERRORS as exc:
        if is_last_attempt():
            logger.exception("Giving up on quiz %s after repeated failures", artifact_id)
            _fail(
                artifact_id, "Generating the quiz failed after several attempts. Try again later."
            )
        else:
            raise TransientError(str(exc)) from exc
    except Exception:
        logger.exception("Unexpected error while generating quiz %s", artifact_id)
        _fail(artifact_id, "Generating the quiz failed unexpectedly.")


def _generate(artifact_id: uuid.UUID) -> None:
    embedder = get_embedder()

    with SessionLocal() as db:
        artifact = ArtifactRepository(db).get(artifact_id)
        # Idempotency: a redelivered task, or a quiz deleted in the meantime, is simply skipped.
        if artifact is None or artifact.status != ArtifactStatus.PENDING:
            return
        params = dict(artifact.params)
        expected_context = artifact.context_hash
        source_ids = [uuid.UUID(source_id) for source_id in params["source_ids"]]
        chunks = select_material(
            db,
            embedder=embedder,
            user_id=artifact.user_id,
            session_id=artifact.session_id,
            topic=params["topic"],
            source_ids=source_ids,
        )

    # The slow part runs without any open transaction or row lock.
    if context_hash([chunk.text for chunk in chunks]) != expected_context:
        raise PermanentError("The material changed while the quiz was waiting. Please ask again.")
    try:
        result = generate_quiz(
            get_llm_provider(),
            chunks,
            topic=params["topic"],
            num_questions=params["num_questions"],
            difficulty=params["difficulty"],
            types=params["types"],
            script=params["script"],
        )
    except (LLMRateLimitError, LLMUnavailableError) as exc:
        raise TransientError(exc.message) from exc
    except LLMError as exc:
        raise PermanentError(exc.message) from exc
    except (NoMaterialError, InvalidQuizError) as exc:
        raise PermanentError(str(exc)) from exc

    with SessionLocal() as db:
        artifact = ArtifactRepository(db).get_for_update(artifact_id)
        if artifact is None or artifact.status != ArtifactStatus.PENDING:
            return  # deleted or finished by someone else while the model was working
        artifact.content = result.content.model_dump(mode="json")
        artifact.llm_provider = result.provider
        artifact.tokens_in = result.tokens_in
        artifact.tokens_out = result.tokens_out
        artifact.status = ArtifactStatus.READY.value
        artifact.error = None
        db.commit()


def _fail(artifact_id: str, message: str) -> None:
    with SessionLocal() as db:
        artifact = ArtifactRepository(db).get_for_update(uuid.UUID(artifact_id))
        if artifact is None or artifact.status != ArtifactStatus.PENDING:
            return
        artifact.status = ArtifactStatus.FAILED.value
        artifact.error = message
        db.commit()
