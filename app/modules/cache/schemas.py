import uuid
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class CacheContext:
    """What an answer depends on besides the question and the material: change any of these
    and a stored answer is no longer the answer the system would give today."""

    embedding_model: str
    llm_model: str
    prompt_version: str
    top_k: int


class CachedCitation(BaseModel):
    rank: int
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    page_start: int | None
    page_end: int | None
    score: float


class CacheHit(BaseModel):
    entry_id: uuid.UUID
    answer: str
    llm_model: str
    prompt_version: str
    citations: list[CachedCitation]
