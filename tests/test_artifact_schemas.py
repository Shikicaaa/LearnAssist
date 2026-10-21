import json
import uuid

import pytest
from pydantic import ValidationError

from app.modules.artifacts.schemas import (
    GeneratedQuestion,
    GeneratedQuiz,
    QuizCitation,
    QuizContent,
    QuizQuestion,
    QuizRequest,
)


def make_question(**overrides) -> dict:
    question = {
        "type": "mcq",
        "question": "What is the capital of France?",
        "options": ["Paris", "London", "Berlin", "Madrid"],
        "correct_index": 0,
        "correct_answer": "Paris",
        "explanation": "Paris is the capital of France.",
        "source_rank": 1,
        "evidence": "Source evidence text.",
    }

    return {**question, **overrides}


def test_request_defaults():
    request = QuizRequest()

    assert request.topic is None
    assert request.source_ids == []
    assert request.difficulty == "medium"
    assert request.types == ["mcq"]
    assert request.script == "latin"
    assert request.regenerate is False


def test_request_strips_topic():
    request = QuizRequest(topic="   Some Topic   ")
    assert request.topic == "Some Topic"


@pytest.mark.parametrize(
    "payload",
    [
        {"types": []},
        {"types": ["essay"]},
        {"difficulty": "impossible"},
        {"num_questions": 0},
        {"script": "chinese"},
        {"source_ids": ["not-a-uuid"]},
        {"topic": "x" * 201},
    ],
)
def test_request_rejects_bad_input(payload):
    with pytest.raises(ValidationError):
        QuizRequest(**payload)


def test_valid_mcq_and_tf_are_accepted():
    GeneratedQuestion(**make_question())
    GeneratedQuestion(**make_question(type="true_false", options=["True", "False"]))


@pytest.mark.parametrize(
    "overrides",
    [
        {"options": ["A", "B", "C"]},  # mcq needs 4
        {"options": ["A", "B", "C", "D", "E"]},
        {"type": "true_false"},  # 4 options for true_false
        {"options": ["A", "a", "C", "D"]},  # duplicates, case-insensitive
        {"correct_index": 4},  # out of range
        {"correct_index": -1},
        {"question": ""},
        {"type": "essay"},
    ],
    ids=[
        "3-options",
        "5-options",
        "tf-with-4",
        "duplicate",
        "index-high",
        "index-negative",
        "empty-question",
        "unknown-type",
    ],
)
def test_invalid_generated_question_is_rejected(overrides):
    with pytest.raises(ValidationError):
        GeneratedQuestion(**make_question(**overrides))


def test_missing_field_is_rejected():
    data = make_question()
    del data["explanation"]

    with pytest.raises(ValidationError, match="explanation"):
        GeneratedQuestion(**data)


def test_error_message_names_the_problem():
    with pytest.raises(ValidationError, match="out of range"):
        GeneratedQuestion(**make_question(correct_index=9))


def test_generated_quiz_parses_json_text():
    raw = json.dumps({"questions": [make_question(), make_question(correct_index=0)]})
    assert len(GeneratedQuiz.model_validate_json(raw).questions) == 2


def test_generated_quiz_requires_questions_key():
    with pytest.raises(ValidationError):
        GeneratedQuiz.model_validate_json('{"quiz": []}')


def test_generated_quiz_rejects_non_json():
    with pytest.raises(ValidationError):
        GeneratedQuiz.model_validate_json("Here is your quiz: ...")


def make_content(chunk_id: uuid.UUID | None) -> QuizContent:
    return QuizContent(
        questions=[
            QuizQuestion(
                type="mcq",
                question="Q?",
                options=["A", "B", "C", "D"],
                correct_index=2,
                explanation="E",
                evidence="ev",
                citation=QuizCitation(
                    chunk_id=chunk_id,
                    source_id=uuid.uuid4(),
                    source_title="Notes",
                    page_start=3,
                    page_end=4,
                ),
            )
        ]
    )
