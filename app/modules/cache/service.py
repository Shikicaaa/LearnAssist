import logging
import uuid

from sqlalchemy.orm import Session

from app.modules import retrieval
from app.modules.cache.models import CacheEntry, CacheEntryCitation
from app.modules.cache.normalize import meaning_markers, normalize_question, question_hash
from app.modules.cache.repository import CacheRepository
from app.modules.cache.schemas import CacheContext, CachedCitation, CacheHit
from app.shared.config import get_settings

logger = logging.getLogger(__name__)


def lookup(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    corpus_version: int,
    question: str,
    vector: list[float],
    latin_only: bool,
    context: CacheContext,
) -> CacheHit | None:
    """Returns a stored answer that is still valid for this question, or None.

    Looks for the identical question first (hash), then for a very similar one. A candidate is
    used only if it passes `_still_valid`; one that fails is deleted. Writes to the database
    (hit counter, deletions) but does not commit: that is the caller's decision.
    """
    repo = CacheRepository(db)
    normalized = normalize_question(question)
    entry = repo.find_exact(
        session_id=session_id,
        user_id=user_id,
        latin_only=latin_only,
        context=context,
        question_hash=question_hash(normalized),
    )
    if entry is None:
        markers = meaning_markers(normalized)
        entry = next(
            (
                candidate
                for candidate in repo.find_similar(
                    session_id=session_id,
                    user_id=user_id,
                    latin_only=latin_only,
                    context=context,
                    vector=vector,
                    min_similarity=get_settings().cache_similarity_threshold,
                )
                if meaning_markers(candidate.question_norm) == markers
            ),
            None,
        )
    if entry is None:
        return None

    citations = repo.citations(entry.id)
    if not _still_valid(db, repo, entry, citations, corpus_version, context):
        repo.delete(entry.id)
        return None

    entry.corpus_version = corpus_version
    repo.record_hit(entry.id)
    return CacheHit(
        entry_id=entry.id,
        answer=entry.answer,
        llm_model=entry.llm_model,
        prompt_version=entry.prompt_version,
        citations=[
            CachedCitation(
                rank=c.rank,
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                source_title=c.source_title,
                page_start=c.page_start,
                page_end=c.page_end,
                score=c.score,
            )
            for c in citations
        ],
    )


def _still_valid(
    db: Session,
    repo: CacheRepository,
    entry: CacheEntry,
    citations: list[CacheEntryCitation],
    corpus_version: int,
    context: CacheContext,
) -> bool:
    # A cited chunk was deleted (its citation row went with it): the answer rests on material
    # that no longer exists.
    if len(citations) < entry.cited_chunks:
        return False
    if entry.corpus_version == corpus_version:
        return True
    if entry.corpus_version > corpus_version:
        return False  # cannot happen in normal operation; do not trust it

    # Lazy revalidation. Material was added since the answer was made. It matters only if a new
    # chunk is closer to the question than the weakest chunk the answer was built from, because
    # only then would it have been part of the top-k.
    best_new = retrieval.best_score_since(
        db,
        embedding_model=context.embedding_model,
        user_id=entry.user_id,
        session_id=entry.session_id,
        query_vector=list(entry.question_embedding),
        since_version=entry.corpus_version,
    )
    return best_new is None or best_new <= entry.kth_score


def store(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    corpus_version: int,
    question: str,
    vector: list[float],
    latin_only: bool,
    answer: str,
    kth_score: float,
    context: CacheContext,
    citations: list[CachedCitation],
) -> None:
    """Saves an answer (replacing an earlier one for the same question). Does not commit."""
    repo = CacheRepository(db)
    normalized = normalize_question(question)
    digest = question_hash(normalized)
    repo.delete_same_question(
        session_id=session_id,
        user_id=user_id,
        latin_only=latin_only,
        context=context,
        question_hash=digest,
    )
    entry = CacheEntry(
        id=uuid.uuid4(),  # the citations below need it before the row is flushed
        session_id=session_id,
        user_id=user_id,
        question_hash=digest,
        question_norm=normalized,
        question_embedding=vector,
        latin_only=latin_only,
        answer=answer,
        corpus_version=corpus_version,
        kth_score=kth_score,
        embedding_model=context.embedding_model,
        llm_model=context.llm_model,
        prompt_version=context.prompt_version,
        top_k=context.top_k,
        cited_chunks=len(citations),
        hit_count=0,
    )
    repo.add(
        entry,
        [
            CacheEntryCitation(
                cache_entry_id=entry.id,
                chunk_id=c.chunk_id,
                source_id=c.source_id,
                rank=c.rank,
                score=c.score,
                source_title=c.source_title,
                page_start=c.page_start,
                page_end=c.page_end,
            )
            for c in citations
        ],
    )


def clear_session(db: Session, *, user_id: uuid.UUID, session_id: uuid.UUID) -> int:
    """Removes every cached answer of the session. Does not commit."""
    return CacheRepository(db).delete_session(session_id, user_id)
