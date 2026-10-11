import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class AskRequest(BaseModel):
    question: Question


class CitationOut(BaseModel):
    rank: int
    chunk_id: uuid.UUID | None  # None once the chunk no longer exists
    source_id: uuid.UUID | None
    source_title: str
    page_start: int | None
    page_end: int | None
    score: float


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    cached: bool
    llm_provider: str | None
    llm_model: str | None
    tokens_in: int
    tokens_out: int
    created_at: datetime
    citations: list[CitationOut]
