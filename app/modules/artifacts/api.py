import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.modules.artifacts import service
from app.modules.artifacts.constants import ArtifactStatus
from app.modules.artifacts.schemas import ArtifactOut, QuizRequest
from app.modules.auth import UserOut, get_current_user
from app.modules.embeddings import Embedder, get_embedder
from app.modules.jobs import TaskQueue, get_task_queue
from app.modules.llm import LLMProvider, get_llm_provider
from app.modules.sessions import SessionOut, get_owned_session
from app.shared.db import get_db
from app.shared.pagination import Page, PageParams

router = APIRouter(tags=["artifacts"])


@router.post(
    "/sessions/{sid}/quizzes",
    response_model=ArtifactOut,
    responses={
        202: {"model": ArtifactOut, "description": "Being generated; poll GET /artifacts/{id}"}
    },
)
def create_quiz(
    body: QuizRequest,
    response: Response,
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    llm: LLMProvider = Depends(get_llm_provider),
    queue: TaskQueue = Depends(get_task_queue),
):
    """Makes a quiz from the session's material. The same request on the same material returns
    the stored quiz (200) without calling the model; otherwise generation starts and the quiz
    comes back `pending` (202). `regenerate=true` forces a new variant."""
    artifact = service.create_quiz(
        db, user_id=user.id, session=session, request=body, embedder=embedder, llm=llm, queue=queue
    )
    # 202 only while a worker is still busy; a finished quiz (ready or failed) is plain 200.
    response.status_code = 202 if artifact.status == ArtifactStatus.PENDING else 200
    return artifact


@router.get("/sessions/{sid}/artifacts", response_model=Page[ArtifactOut])
def list_artifacts(
    page: PageParams = Depends(),
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The session's quizzes, newest first."""
    items, total = service.list_artifacts(db, user.id, session.id, page.limit, page.offset)
    return Page[ArtifactOut](
        items=[ArtifactOut.model_validate(item) for item in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactOut)
def get_artifact(
    artifact_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return service.get_artifact(db, user.id, artifact_id)


@router.delete("/artifacts/{artifact_id}", status_code=204)
def delete_artifact(
    artifact_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_artifact(db, user.id, artifact_id)
    return Response(status_code=204)
