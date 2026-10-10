import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.modules.auth import UserOut, get_current_user
from app.modules.sessions.schemas import SessionCreate, SessionOut, SessionUpdate
from app.modules.sessions.service import SessionService
from app.shared.db import get_db
from app.shared.pagination import Page, PageParams

router = APIRouter(prefix="/sessions", tags=["sessions"])


def get_session_service(db: Session = Depends(get_db)) -> SessionService:
    return SessionService(db)


def get_owned_session(
    sid: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> SessionOut:
    """Loads the session only if it belongs to the user; otherwise 404 (not 403)."""
    return SessionOut.model_validate(service.get_owned(user.id, sid))


@router.post("", response_model=SessionOut, status_code=201)
def create_session(
    body: SessionCreate,
    user: UserOut = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    return service.create(user.id, body.title)


@router.get("", response_model=Page[SessionOut])
def list_sessions(
    page: PageParams = Depends(),
    user: UserOut = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    items, total = service.list(user.id, page.limit, page.offset)
    return Page[SessionOut](
        items=[SessionOut.model_validate(s) for s in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{sid}", response_model=SessionOut)
def get_session(session: SessionOut = Depends(get_owned_session)):
    return session


@router.patch("/{sid}", response_model=SessionOut)
def update_session(
    sid: uuid.UUID,
    body: SessionUpdate,
    user: UserOut = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
):
    return service.update(user.id, sid, body.title, body.cache_enabled)


@router.delete("/{sid}", status_code=204)
def delete_session(
    sid: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    service: SessionService = Depends(get_session_service),
) -> Response:
    service.delete(user.id, sid)
    return Response(status_code=204)
