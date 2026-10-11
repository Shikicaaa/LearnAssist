import uuid

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_start: int | None
    page_end: int | None
    text: str
    score: float


class RetrievalResult(BaseModel):
    chunks: list[RetrievedChunk]
    # True when the session has any searchable material at all, even if nothing was relevant.
    has_material: bool
    # Similarity of the weakest of the top-k hits (0.0 if fewer than k exist). The cache needs
    # it later to decide whether a newly added chunk would have made it into the top-k.
    kth_score: float


class ChunkOut(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    text: str
