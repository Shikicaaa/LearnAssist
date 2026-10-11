"""Public interface of the retrieval module: other modules may import only this."""

from app.modules.retrieval.schemas import ChunkOut, RetrievalResult, RetrievedChunk
from app.modules.retrieval.service import embed_question, get_chunk, retrieve

__all__ = [
    "ChunkOut",
    "RetrievalResult",
    "RetrievedChunk",
    "embed_question",
    "get_chunk",
    "retrieve",
]
