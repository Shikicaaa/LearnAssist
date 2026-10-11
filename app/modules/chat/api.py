import json
import uuid
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.modules import retrieval
from app.modules.auth import UserOut, get_current_user
from app.modules.chat.schemas import AskRequest, MessageOut
from app.modules.chat.service import ChatService
from app.modules.embeddings import Embedder, get_embedder
from app.modules.llm import LLMProvider, get_llm_provider
from app.modules.retrieval import ChunkOut
from app.modules.sessions import SessionOut, get_owned_session
from app.shared.config import get_settings
from app.shared.db import get_db
from app.shared.pagination import Page, PageParams
from app.shared.rate_limit import enforce_rate_limit

router = APIRouter(tags=["chat"])


def get_chat_service(
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ChatService:
    return ChatService(db, embedder, llm)


def _sse(events: Iterator[dict]) -> Iterator[str]:
    for event in events:
        data = json.dumps(event["data"], ensure_ascii=False)
        yield f"event: {event['event']}\ndata: {data}\n\n"


@router.post(
    "/sessions/{sid}/messages",
    response_model=None,
    responses={200: {"model": MessageOut, "description": "The answer (or an SSE stream)"}},
)
def ask(
    body: AskRequest,
    stream: bool = False,
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """Asks a question about the session's sources. `?stream=true` returns server-sent events:
    `delta` (pieces of text), then `citations`, then `done` (the stored message)."""
    enforce_rate_limit(
        f"rl:chat:{user.id}",
        limit=get_settings().chat_requests_per_minute,
        window_seconds=60,
    )
    if not stream:
        return service.ask(user.id, session.id, body.question)
    events = service.start_stream(user.id, session.id, body.question)
    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(_sse(events), media_type="text/event-stream", headers=headers)


@router.get("/sessions/{sid}/messages", response_model=Page[MessageOut])
def list_messages(
    page: PageParams = Depends(),
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    """The conversation, newest message first."""
    items, total = service.history(user.id, session.id, page.limit, page.offset)
    return Page[MessageOut](items=items, total=total, limit=page.limit, offset=page.offset)


@router.delete("/sessions/{sid}/messages", status_code=204)
def clear_messages(
    session: SessionOut = Depends(get_owned_session),
    user: UserOut = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
) -> Response:
    service.clear_history(user.id, session.id)
    return Response(status_code=204)


@router.get("/chunks/{chunk_id}", response_model=ChunkOut)
def get_chunk(
    chunk_id: uuid.UUID,
    user: UserOut = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The text behind a citation."""
    return retrieval.get_chunk(db, user_id=user.id, chunk_id=chunk_id)
