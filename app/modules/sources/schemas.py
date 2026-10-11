import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class TextSourceCreate(BaseModel):
    title: Title
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must not be blank")
        return value


class ChunkHit(BaseModel):
    """A chunk found by similarity search, with the data a citation needs."""

    chunk_id: uuid.UUID
    source_id: uuid.UUID
    source_title: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    text: str
    score: float  # cosine similarity, 1.0 = identical direction


class ChunkDetail(BaseModel):
    chunk_id: uuid.UUID
    source_id: uuid.UUID
    session_id: uuid.UUID
    source_title: str
    chunk_index: int
    page_start: int | None
    page_end: int | None
    text: str


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    type: str
    title: str
    filename: str | None
    mime: str | None
    size_bytes: int
    status: str
    page_count: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime
