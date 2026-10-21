import uuid

from sqlalchemy.orm import Session

from app.modules import retrieval
from app.modules.embeddings import Embedder
from app.modules.retrieval import RetrievedChunk
from app.shared.config import get_settings


def select_material(
    db: Session,
    *,
    embedder: Embedder,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    topic: str | None,
    source_ids: list[uuid.UUID],
) -> list[RetrievedChunk]:
    """The chunks a quiz is built from.

    With a topic: the chunks most similar to it (a search, like a chat question). Without one: an
    even, deterministic sample of the chosen sources (all of them if none are chosen), so the
    quiz covers the whole material and the same material always gives the same selection.

    The request and the worker both call this; the worker compares the result with the
    `context_hash` stored at request time to notice that the material changed in between.
    """
    settings = get_settings()
    limit = settings.quiz_context_chunks

    if topic:
        vector = retrieval.embed_question(embedder, topic)
        # The search cannot filter by source, so with a source filter ask for more and cut after.
        result = retrieval.retrieve(
            db,
            embedder=embedder,
            user_id=user_id,
            session_id=session_id,
            question_vector=vector,
            top_k=limit * 4 if source_ids else limit,
            min_score=settings.quiz_min_score,
        )
        chunks = result.chunks
        if source_ids:
            wanted = set(source_ids)
            chunks = [chunk for chunk in chunks if chunk.source_id in wanted]
        return chunks[:limit]

    return retrieval.sample_material(
        db,
        user_id=user_id,
        session_id=session_id,
        embedding_model=embedder.model_name,
        source_ids=source_ids,
        limit=limit,
    )
