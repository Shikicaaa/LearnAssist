import itertools
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules import retrieval
from app.modules.chat.citations import StreamFilter, extract_cited_ranks, is_no_answer
from app.modules.chat.models import Message, MessageCitation
from app.modules.chat.prompts import (
    NO_ANSWER_MESSAGE,
    NO_SOURCES_MESSAGE,
    PROMPT_VERSION,
    build_user_message,
    system_prompt,
)
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import CitationOut, MessageOut
from app.modules.chat.script import contains_cyrillic, to_latin
from app.modules.embeddings import Embedder
from app.modules.llm import Finished, LLMError, LLMMessage, LLMProvider, LLMResult, TextDelta
from app.modules.retrieval import RetrievedChunk
from app.shared.config import get_settings
from app.shared.db import utcnow

logger = logging.getLogger(__name__)


@dataclass
class _Turn:
    """Everything decided before the model is called (or skipped)."""

    user_id: uuid.UUID
    session_id: uuid.UUID
    question: str
    asked_at: datetime
    chunks: list[RetrievedChunk]
    messages: list[LLMMessage]
    canned_answer: str | None  # set when no model call is needed
    latin_only: bool  # the question is in Latin script, so the answer must be too


class ChatService:
    def __init__(self, db: Session, embedder: Embedder, llm: LLMProvider):
        self.db = db
        self.embedder = embedder
        self.llm = llm
        self.repo = ChatRepository(db)

    # --- asking -----------------------------------------------------------------------------

    def ask(self, user_id: uuid.UUID, session_id: uuid.UUID, question: str) -> MessageOut:
        turn = self._prepare(user_id, session_id, question)
        if turn.canned_answer is not None:
            return self._save(turn, turn.canned_answer, result=None, ranks=[])
        result = self.llm.generate(
            turn.messages, system=system_prompt(), max_output_tokens=_max_tokens()
        )
        return self._finish(turn, result)

    def start_stream(
        self, user_id: uuid.UUID, session_id: uuid.UUID, question: str
    ) -> Iterator[dict]:
        """Prepares the answer and returns an iterator of events (`delta`, `citations`, `done`,
        and `error` if the model fails half-way).

        Everything that can fail before the first byte (retrieval, the model refusing the
        request) happens in here, so the caller can still answer with a proper HTTP error.
        """
        turn = self._prepare(user_id, session_id, question)
        if turn.canned_answer is not None:
            message = self._save(turn, turn.canned_answer, result=None, ranks=[])
            return iter(self._closing_events(message, shown=turn.canned_answer))
        events = self._model_events(turn)
        return itertools.chain([next(events)], events)

    def _prepare(self, user_id: uuid.UUID, session_id: uuid.UUID, question: str) -> _Turn:
        asked_at = utcnow()
        vector = retrieval.embed_question(self.embedder, question)
        found = retrieval.retrieve(
            self.db,
            embedder=self.embedder,
            user_id=user_id,
            session_id=session_id,
            question_vector=vector,
        )
        history = [
            LLMMessage(m.role, m.content)  # type: ignore[arg-type]
            for m in self.repo.recent(session_id, user_id, get_settings().chat_history_messages)
        ]
        # The model call can take many seconds. End the read transaction now, so that this
        # request does not keep a database connection checked out while it waits. Everything
        # needed afterwards has already been copied into plain objects.
        self.db.rollback()

        canned = None
        if not found.has_material:
            canned = NO_SOURCES_MESSAGE
        elif not found.chunks:
            canned = NO_ANSWER_MESSAGE
        messages = [*history, LLMMessage("user", build_user_message(question, found.chunks))]
        return _Turn(
            user_id,
            session_id,
            question,
            asked_at,
            found.chunks,
            messages,
            canned,
            latin_only=not contains_cyrillic(question),
        )

    # --- streaming --------------------------------------------------------------------------

    def _model_events(self, turn: _Turn) -> Iterator[dict]:
        sentinel_filter = StreamFilter()
        finished: LLMResult | None = None
        started = False
        try:
            for event in self.llm.stream(
                turn.messages, system=system_prompt(), max_output_tokens=_max_tokens()
            ):
                if isinstance(event, TextDelta):
                    piece = to_latin(event.text) if turn.latin_only else event.text
                    if shown := sentinel_filter.feed(piece):
                        started = True
                        yield {"event": "delta", "data": {"text": shown}}
                elif isinstance(event, Finished):
                    finished = event.result
            if tail := sentinel_filter.finish():
                started = True
                yield {"event": "delta", "data": {"text": tail}}
        except LLMError as exc:
            if not started:
                raise  # nothing sent yet: let the API answer with a normal HTTP error
            logger.warning("Model failed mid-stream: %s", exc.code)
            yield {"event": "error", "data": {"code": exc.code, "message": exc.message}}
            return

        assert finished is not None  # providers always end with Finished
        message = self._finish(turn, finished)
        shown = message.content
        if sentinel_filter.no_answer:
            # The client never saw the sentinel; give it the readable replacement instead.
            yield {"event": "delta", "data": {"text": shown}}
        yield from self._closing_events(message, shown=None)

    def _closing_events(self, message: MessageOut, shown: str | None) -> Iterator[dict]:
        if shown is not None:
            yield {"event": "delta", "data": {"text": shown}}
        citations = [c.model_dump(mode="json") for c in message.citations]
        yield {"event": "citations", "data": {"citations": citations}}
        yield {"event": "done", "data": {"message": message.model_dump(mode="json")}}

    # --- finishing --------------------------------------------------------------------------

    def _finish(self, turn: _Turn, result: LLMResult) -> MessageOut:
        # The model sometimes drifts into the script of the sources (Cyrillic) in the middle of a
        # Latin answer, even when told not to. The question decides the script, so enforce it.
        text = to_latin(result.text) if turn.latin_only else result.text
        if is_no_answer(text):
            return self._save(turn, NO_ANSWER_MESSAGE, result, ranks=[])
        ranks = extract_cited_ranks(text, max_rank=len(turn.chunks))
        return self._save(turn, text, result, ranks)

    def _save(
        self, turn: _Turn, answer: str, result: LLMResult | None, ranks: list[int]
    ) -> MessageOut:
        # Question and answer are stored together, after the answer exists: a failed model call
        # leaves no orphan question behind, and the client can simply ask again.
        self.repo.add_message(
            session_id=turn.session_id,
            user_id=turn.user_id,
            role="user",
            content=turn.question,
            created_at=turn.asked_at,
        )
        assistant = self.repo.add_message(
            session_id=turn.session_id,
            user_id=turn.user_id,
            role="assistant",
            content=answer,
            llm_provider=result.provider if result else None,
            llm_model=result.model if result else None,
            prompt_version=PROMPT_VERSION if result else None,
            tokens_in=result.tokens_in if result else 0,
            tokens_out=result.tokens_out if result else 0,
        )
        citations = [
            MessageCitation(
                message_id=assistant.id,
                chunk_id=turn.chunks[rank - 1].chunk_id,
                source_id=turn.chunks[rank - 1].source_id,
                rank=rank,
                score=turn.chunks[rank - 1].score,
                snapshot_source_title=turn.chunks[rank - 1].source_title,
                snapshot_page=turn.chunks[rank - 1].page_start,
                snapshot_page_end=turn.chunks[rank - 1].page_end,
            )
            for rank in ranks
        ]
        self.repo.add_citations(citations)
        self.db.commit()
        return _to_out(assistant, citations)

    # --- history ----------------------------------------------------------------------------

    def history(
        self, user_id: uuid.UUID, session_id: uuid.UUID, limit: int, offset: int
    ) -> tuple[list[MessageOut], int]:
        messages, total = self.repo.page(session_id, user_id, limit, offset)
        citations = self.repo.citations_for([m.id for m in messages])
        return [_to_out(m, citations.get(m.id, [])) for m in messages], total

    def clear_history(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        self.repo.delete_all(session_id, user_id)
        self.db.commit()


def _max_tokens() -> int:
    return get_settings().chat_max_output_tokens


def _to_out(message: Message, citations: list[MessageCitation]) -> MessageOut:
    return MessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        cached=message.cached,
        llm_provider=message.llm_provider,
        llm_model=message.llm_model,
        tokens_in=message.tokens_in,
        tokens_out=message.tokens_out,
        created_at=message.created_at,
        citations=[
            CitationOut(
                rank=c.rank,
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                source_title=c.snapshot_source_title,
                page_start=c.snapshot_page,
                page_end=c.snapshot_page_end,
                score=c.score,
            )
            for c in citations
        ],
    )
