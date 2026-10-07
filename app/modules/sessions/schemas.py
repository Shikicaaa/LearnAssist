import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class SessionCreate(BaseModel):
    title: Title


class SessionUpdate(BaseModel):
    title: Title | None = None
    cache_enabled: bool | None = None


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    corpus_version: int
    cache_enabled: bool
    embedding_model: str
    created_at: datetime
    updated_at: datetime
