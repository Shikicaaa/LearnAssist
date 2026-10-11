import itertools
import logging
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.modules import cache, retrieval
from app.modules.cache import CacheContext, CachedCitation, CacheHit
from app.modules.chat.citations import StreamFilter, extract_cited_ranks, is_no_answer
from app.modules.chat.followup import depends_on_history
from app.modules.chat.models import Message, MessageCitation
from app.modules.chat.prompts import (
    NO_ANSWER_MESSAGE,
    NO_SOURCES_MESSAGE,
    build_user_message,
    prompt_version,
    system_prompt,
)
from app.modules.chat.repository import ChatRepository
from app.modules.chat.schemas import CitationOut, MessageOut
from app.modules.chat.script import contains_cyrillic, to_latin
from app.modules.embeddings import Embedder
from app.modules.llm import Finished, LLMError, LLMMessage, LLMProvider, LLMResult, TextDelta
from app.modules.retrieval import RetrievedChunk
from app.modules.sessions import SessionOut
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
    vector: list[float]  # the question embedding, shared by the cache and the search
    corpus_version: int  # the session's version this turn started from
    allow_general: bool  # hybrid mode: the model may add labelled general knowledge
    kth_score: float  # similarity of the weakest top-k chunk (the cache needs it)
    cacheable: bool  # may the answer be stored in (and served from) the cache?
    context: CacheContext
    hit: CacheHit | None = None  # set when a stored answer is reused


class ChatService:
    def __init__(self, db: Session, embedder: Embedder, llm: LLMProvider):
        self.db = db
        self.embedder = embedder
        self.llm = llm
        self.repo = ChatRepository(db)

    # --- asking -----------------------------------------------------------------------------

    def ask(
        self,
        user_id: uuid.UUID,
        session: SessionOut,
        question: str,
        use_cache: bool = True,
        allow_general: bool = False,
    ) -> MessageOut:
        turn = self._prepare(user_id, session, question, use_cache, allow_general)
        if turn.hit is not None:
            return self._save(turn, turn.hit.answer, turn.hit.citations)
        if turn.canned_answer is not None:
            return self._save(turn, turn.canned_answer, [])
        result = self.llm.generate(
            turn.messages,
            system=system_prompt(turn.allow_general),
            max_output_tokens=_max_tokens(),
        )
        return self._finish(turn, result)

    def start_stream(
        self,
        user_id: uuid.UUID,
        session: SessionOut,
        question: str,
        use_cache: bool = True,
        allow_general: bool = False,
    ) -> Iterator[dict]:
        """Prepares the answer and returns an iterator of events (`delta`, `citations`, `done`,
        and `error` if the model fails half-way).

        Everything that can fail before the first byte (retrieval, the model refusing the
        request) happens in here, so the caller can still answer with a proper HTTP error.
        """
        turn = self._prepare(user_id, session, question, use_cache, allow_general)
        if turn.hit is not None:
            message = self._save(turn, turn.hit.answer, turn.hit.citations)
            return iter(self._closing_events(message, shown=turn.hit.answer))
        if turn.canned_answer is not None:
            message = self._save(turn, turn.canned_answer, [])
            return iter(self._closing_events(message, shown=turn.canned_answer))
        events = self._model_events(turn)
        return itertools.chain([next(events)], events)

    def _prepare(
        self,
        user_id: uuid.UUID,
        session: SessionOut,
        question: str,
        use_cache: bool,
        allow_general: bool,
    ) -> _Turn:
        settings = get_settings()
        asked_at = utcnow()
        vector = retrieval.embed_question(self.embedder, question)
        history = [
            LLMMessage(m.role, m.content)  # type: ignore[arg-type]
            for m in self.repo.recent(session.id, user_id, settings.chat_history_messages)
        ]
        latin_only = not contains_cyrillic(question)
        context = CacheContext(
            embedding_model=self.embedder.model_name,
            llm_model=self.llm.model,
            prompt_version=prompt_version(allow_general),
            top_k=settings.retrieval_top_k,
        )
        # A question that leans on the conversation ("and what about that?") has no answer of
        # its own to store, and a stored answer to it could belong to a different conversation.
        cacheable = (
            use_cache and session.cache_enabled and not (history and depends_on_history(question))
        )
        base = {
            "user_id": user_id,
            "session_id": session.id,
            "question": question,
            "asked_at": asked_at,
            "latin_only": latin_only,
            "allow_general": allow_general,
            "vector": vector,
            "corpus_version": session.corpus_version,
            "cacheable": cacheable,
            "context": context,
        }

        if cacheable:
            hit = cache.lookup(
                self.db,
                user_id=user_id,
                session_id=session.id,
                corpus_version=session.corpus_version,
                question=question,
                vector=vector,
                latin_only=latin_only,
                context=context,
            )
            # Lookup may have deleted a stale entry or bumped a counter; keep that even if the
            # rest of the request is rolled back below.
            self.db.commit()
            if hit is not None:
                return _Turn(
                    **base, chunks=[], messages=[], canned_answer=None, kth_score=0.0, hit=hit
                )

        found = retrieval.retrieve(
            self.db,
            embedder=self.embedder,
            user_id=user_id,
            session_id=session.id,
            question_vector=vector,
        )
        # The model call can take many seconds. End the read transaction now, so that this
        # request does not keep a database connection checked out while it waits. Everything
        # needed afterwards has already been copied into plain objects.
        self.db.rollback()

        canned = None
        if not found.has_material:
            canned = NO_SOURCES_MESSAGE
        elif not found.chunks and not allow_general:
            canned = NO_ANSWER_MESSAGE
        messages = [*history, LLMMessage("user", build_user_message(question, found.chunks))]
        return _Turn(
            **base,
            chunks=found.chunks,
            messages=messages,
            canned_answer=canned,
            kth_score=found.kth_score,
        )

    # --- streaming --------------------------------------------------------------------------

    def _model_events(self, turn: _Turn) -> Iterator[dict]:
        sentinel_filter = StreamFilter()
        finished: LLMResult | None = None
        started = False
        try:
            for event in self.llm.stream(
                turn.messages,
                system=system_prompt(turn.allow_general),
                max_output_tokens=_max_tokens(),
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
            return self._save(turn, NO_ANSWER_MESSAGE, [], result=result)
        ranks = extract_cited_ranks(text, max_rank=len(turn.chunks))
        citations = [_citation(rank, turn.chunks[rank - 1]) for rank in ranks]
        return self._save(turn, text, citations, result=result)

    def _save(
        self,
        turn: _Turn,
        answer: str,
        citations: list[CachedCitation],
        result: LLMResult | None = None,
    ) -> MessageOut:
        """Stores the question and its answer. `result` is set when the model produced the
        answer; a reused cache entry is `turn.hit`; otherwise the answer was canned."""
        # Question and answer are stored together, after the answer exists: a failed model call
        # leaves no orphan question behind, and the client can simply ask again.
        self.repo.add_message(
            session_id=turn.session_id,
            user_id=turn.user_id,
            role="user",
            content=turn.question,
            created_at=turn.asked_at,
        )
        assistant_fields: dict = {}
        if result is not None:
            assistant_fields = {
                "llm_provider": result.provider,
                "llm_model": result.model,
                "prompt_version": prompt_version(turn.allow_general),
                "tokens_in": result.tokens_in,
                "tokens_out": result.tokens_out,
            }
        elif turn.hit is not None:
            # Nothing was spent on this answer: no provider, no tokens.
            assistant_fields = {
                "cached": True,
                "cache_entry_id": turn.hit.entry_id,
                "llm_model": turn.hit.llm_model,
                "prompt_version": turn.hit.prompt_version,
            }
        assistant = self.repo.add_message(
            session_id=turn.session_id,
            user_id=turn.user_id,
            role="assistant",
            content=answer,
            **assistant_fields,
        )
        rows = [
            MessageCitation(
                message_id=assistant.id,
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                rank=c.rank,
                score=c.score,
                snapshot_source_title=c.source_title,
                snapshot_page=c.page_start,
                snapshot_page_end=c.page_end,
            )
            for c in citations
        ]
        self.repo.add_citations(rows)
        if result is not None and turn.cacheable:
            self._remember(turn, answer, citations)
        self.db.commit()
        return _to_out(assistant, rows)

    def _remember(self, turn: _Turn, answer: str, citations: list[CachedCitation]) -> None:
        # The cache is an optimisation: if storing fails, the student still gets the answer.
        try:
            with self.db.begin_nested():
                cache.store(
                    self.db,
                    user_id=turn.user_id,
                    session_id=turn.session_id,
                    corpus_version=turn.corpus_version,
                    question=turn.question,
                    vector=turn.vector,
                    latin_only=turn.latin_only,
                    answer=answer,
                    kth_score=turn.kth_score,
                    context=turn.context,
                    citations=citations,
                )
        except Exception:
            logger.exception("Could not store the answer in the cache")

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


def _citation(rank: int, chunk: RetrievedChunk) -> CachedCitation:
    return CachedCitation(
        rank=rank,
        chunk_id=chunk.chunk_id,
        source_id=chunk.source_id,
        source_title=chunk.source_title,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        score=chunk.score,
    )


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
