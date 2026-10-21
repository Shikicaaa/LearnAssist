import uuid

from sqlalchemy.orm import Session

from app.modules import sources
from app.modules.embeddings import Embedder
from app.modules.retrieval.schemas import ChunkOut, RetrievalResult, RetrievedChunk
from app.shared.config import get_settings


def embed_question(embedder: Embedder, question: str) -> list[float]:
    """Embeds the question once; the same vector serves the cache lookup and the search."""
    return embedder.embed_query(question)


def retrieve(
    db: Session,
    *,
    embedder: Embedder,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    question_vector: list[float],
    top_k: int | None = None,
    min_score: float | None = None,
) -> RetrievalResult:
    settings = get_settings()
    top_k = top_k if top_k is not None else settings.retrieval_top_k
    min_score = min_score if min_score is not None else settings.retrieval_min_score

    hits = sources.search_chunks(
        db,
        user_id=user_id,
        session_id=session_id,
        embedding_model=embedder.model_name,
        query_vector=question_vector,
        limit=top_k,
    )
    relevant = [hit for hit in hits if hit.score >= min_score]
    return RetrievalResult(
        chunks=[
            RetrievedChunk(
                chunk_id=hit.chunk_id,
                source_id=hit.source_id,
                source_title=hit.source_title,
                page_start=hit.page_start,
                page_end=hit.page_end,
                text=hit.text,
                score=hit.score,
            )
            for hit in relevant
        ],
        has_material=bool(hits),
        kth_score=hits[-1].score if len(hits) == top_k else 0.0,
    )


def best_score_since(
    db: Session,
    *,
    embedding_model: str,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    query_vector: list[float],
    since_version: int,
) -> float | None:
    """How similar the closest chunk added after `since_version` is to the vector (None if no
    chunk was added). The cache uses it to tell whether new material would change an answer."""
    return sources.best_score_since(
        db,
        user_id=user_id,
        session_id=session_id,
        embedding_model=embedding_model,
        query_vector=query_vector,
        since_version=since_version,
    )


def get_chunk(db: Session, *, user_id: uuid.UUID, chunk_id: uuid.UUID) -> ChunkOut:
    detail = sources.get_chunk(db, user_id=user_id, chunk_id=chunk_id)
    return ChunkOut(
        chunk_id=detail.chunk_id,
        source_id=detail.source_id,
        source_title=detail.source_title,
        chunk_index=detail.chunk_index,
        page_start=detail.page_start,
        page_end=detail.page_end,
        text=detail.text,
    )


def sample_material(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    embedding_model: str,
    source_ids: list[uuid.UUID],
    limit: int,
) -> list[RetrievedChunk]:
    """Returns a sample of chunks from the given sources in the session."""
    refs = sources.sample_chunks(
        db,
        user_id=user_id,
        session_id=session_id,
        embedding_model=embedding_model,
        source_ids=source_ids,
        limit=limit,
    )

    return [
        RetrievedChunk(
            chunk_id=ref.chunk_id,
            source_id=ref.source_id,
            source_title=ref.source_title,
            page_start=ref.page_start,
            page_end=ref.page_end,
            text=ref.text,
            score=1.0,
        )
        for ref in refs
    ]
