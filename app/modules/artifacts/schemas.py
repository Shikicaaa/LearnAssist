import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Topic = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
QuestionType = Literal["mcq", "true_false", "short_answer"]

# How many options each closed-form type needs; short_answer has none.
OPTION_COUNT: dict[str, int] = {"mcq": 4, "true_false": 2, "short_answer": 0}


class QuizRequest(BaseModel):
    topic: Topic | None = None  # None = the whole material
    source_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)  # [] = all sources
    num_questions: int = Field(default=10, ge=1)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    types: list[QuestionType] = Field(default=["mcq"], min_length=1)
    script: Literal["latin", "cyrillic"] = "latin"
    # True bumps `variant`, so the same parameters produce a new quiz instead of the cached one.
    regenerate: bool = False


class GeneratedQuestion(BaseModel):
    """One question as returned by the model. Untrusted: everything is checked here."""

    type: QuestionType
    question: str = Field(min_length=1)
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None  # mcq and true_false
    correct_answer: str | None = None  # short_answer
    explanation: str
    source_rank: int = Field(ge=1)  # n from <izvor n>; the generator checks the upper bound
    evidence: str

    @model_validator(mode="after")
    def _check(self) -> Self:
        expected = OPTION_COUNT[self.type]
        if len(self.options) != expected:
            raise ValueError(
                f"Expected {expected} options for type {self.type}, got {len(self.options)}"
            )
        if len({o.strip().casefold() for o in self.options}) != len(self.options):
            raise ValueError("Options must be unique (case-insensitive)")

        if self.type == "short_answer":
            if not self.correct_answer or not self.correct_answer.strip():
                raise ValueError("short_answer needs a non-empty correct_answer")
            if self.correct_index is not None:
                raise ValueError("short_answer must not have correct_index")
        else:
            if self.correct_index is None or not 0 <= self.correct_index < len(self.options):
                raise ValueError(
                    f"correct_index out of range for {len(self.options)} options: "
                    f"{self.correct_index}"
                )
        return self


class QuizCitation(BaseModel):
    chunk_id: uuid.UUID | None  # None once the chunk no longer exists
    source_id: uuid.UUID | None
    source_title: str  # snapshot, survives source deletion
    page_start: int | None
    page_end: int | None


class GeneratedQuiz(BaseModel):
    questions: list[GeneratedQuestion] = Field(min_length=1, max_length=50)


class QuizQuestion(BaseModel):
    type: QuestionType
    question: str
    options: list[str]
    correct_index: int | None
    correct_answer: str | None
    explanation: str
    evidence: str
    citation: QuizCitation


class QuizContent(BaseModel):
    questions: list[QuizQuestion]


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    kind: str
    status: Literal["pending", "ready", "failed"]
    error: str | None
    params: dict[str, Any]
    content: QuizContent | None  # None until status == "ready"
    llm_model: str
    tokens_in: int
    tokens_out: int
    created_at: datetime
