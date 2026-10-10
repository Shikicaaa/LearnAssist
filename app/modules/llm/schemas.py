from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Message = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


class LLMTestRequest(BaseModel):
    message: Message
    system: str | None = Field(default=None, max_length=2000)


class LLMTestResponse(BaseModel):
    answer: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
