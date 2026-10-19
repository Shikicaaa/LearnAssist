from enum import StrEnum

QUIZ_TASK = "artifacts.generate_quiz"
KIND_QUIZ = "quiz"


class ArtifactStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
