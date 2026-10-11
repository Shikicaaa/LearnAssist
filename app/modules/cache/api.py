from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.modules.auth import UserOut, get_current_user
from app.modules.cache import service
from app.modules.sessions import SessionOut, get_owned_session
from app.shared.db import get_db

router = APIRouter(tags=["cache"])


@router.post("/sessions/{sid}/cache/clear", status_code=204)
def clear_cache(
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Forgets every stored answer of the session; the next questions are answered afresh."""
    service.clear_session(db, user_id=user.id, session_id=session.id)
    db.commit()
    return Response(status_code=204)
