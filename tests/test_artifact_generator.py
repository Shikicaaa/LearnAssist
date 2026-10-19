import json
import uuid
from dataclasses import dataclass, field

import pytest

from app.modules.artifacts.generator import (
    InvalidQuizError,
    NoMaterialError,
    generate_quiz,
    is_grounded,
)
from app.modules.llm import LLMMessage, LLMResult
from app.modules.retrieval import RetrievedChunk

BIOLOGY = "Photosynthesis converts light energy into chemical energy inside chloroplasts."
HISTORY = "The battle of Kosovo was fought in 1389 between Serbian and Ottoman armies."


@dataclass
class SequenceLLM:
    """Answers each call with the next scripted reply and keeps the messages it was sent."""

    replies: list[str]
    name: str = "fake"
    model: str = "fake-model"
    calls: list[list[LLMMessage]] = field(default_factory=list)

    def generate(self, messages, system=None, max_output_tokens=None) -> LLMResult:
        self.calls.append(list(messages))
        return LLMResult(self.replies.pop(0), self.name, self.model, tokens_in=10, tokens_out=20)


def chunk(text: str, title: str = "Notes", page: int | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        source_title=title,
        page_start=page,
        page_end=page,
        text=text,
        score=1.0,
    )


def question(**overrides) -> dict:
    base = {
        "type": "mcq",
        "question": "What does photosynthesis convert?",
        "options": ["Light", "Sound", "Heat", "Wind"],
        "correct_index": 0,
        "correct_answer": None,
        "explanation": "The source says so.",
        "source_rank": 1,
        "evidence": "Photosynthesis converts light energy",
    }
    return {**base, **overrides}


def reply(*questions: dict) -> str:
    return json.dumps({"questions": list(questions)})


def run(llm, chunks=None, **overrides):
    params = dict(topic=None, num_questions=5, difficulty="easy", types=["mcq", "true_false"])
    params |= {"script": "latin", **overrides}
    return generate_quiz(
        llm, chunks or [chunk(BIOLOGY, "Bio", 3), chunk(HISTORY, "Hist")], **params
    )


def test_a_good_reply_becomes_a_quiz_with_citations_and_summed_tokens():
    chunks = [chunk(BIOLOGY, "Bio", 3), chunk(HISTORY, "Hist")]
    llm = SequenceLLM(
        [
            reply(
                question(),
                question(
                    type="true_false",
                    question="Kosovo was fought in 1389.",
                    options=["True", "False"],
                    source_rank=2,
                    evidence="The battle of Kosovo was fought in 1389",
                ),
            )
        ]
    )
    result = run(llm, chunks)

    first, second = result.content.questions
    assert first.citation.source_title == "Bio" and first.citation.page_start == 3
    assert first.citation.chunk_id == chunks[0].chunk_id
    assert second.citation.source_title == "Hist" and second.citation.page_start is None
    assert (result.tokens_in, result.tokens_out) == (10, 20)
    assert len(llm.calls) == 1


def test_json_in_code_fences_is_accepted():
    llm = SequenceLLM([f"```json\n{reply(question())}\n```"])
    assert len(run(llm).content.questions) == 1


def test_the_sentinel_means_not_enough_material():
    with pytest.raises(NoMaterialError):
        run(SequenceLLM(["NEMA_MATERIJALA"]))


def test_invalid_json_is_retried_with_feedback():
    llm = SequenceLLM(["Here is your quiz!", reply(question())])
    result = run(llm)
    assert len(result.content.questions) == 1
    assert len(llm.calls) == 2
    assert (result.tokens_in, result.tokens_out) == (20, 40)  # both calls are counted
    roles = [m.role for m in llm.calls[1]]
    assert roles == ["user", "assistant", "user"]
    assert "nije ispravan" in llm.calls[1][-1].content


def test_a_question_without_a_verbatim_quote_is_dropped_but_the_others_survive():
    llm = SequenceLLM([reply(question(evidence="Something the source never says"), question())])
    result = run(llm)
    assert len(result.content.questions) == 1
    assert len(llm.calls) == 1  # one good question is enough, no retry


def test_when_nothing_is_usable_the_model_is_asked_once_more_and_then_the_quiz_fails():
    bad = reply(question(evidence="Something the source never says"))
    llm = SequenceLLM([bad, bad])
    with pytest.raises(InvalidQuizError, match="verbatim"):
        run(llm)
    assert len(llm.calls) == 2


@pytest.mark.parametrize(
    "bad_question,problem",
    [
        (question(type="true_false", options=["True", "False"]), "was not requested"),
        (question(source_rank=9), "no source number 9"),
        (question(correct_index=7), "out of range"),
        (question(options=["A", "B", "C"]), "options"),
    ],
    ids=["unrequested-type", "unknown-source", "bad-index", "wrong-option-count"],
)
def test_bad_questions_are_dropped(bad_question, problem):
    llm = SequenceLLM([reply(bad_question), reply(bad_question)])
    with pytest.raises(InvalidQuizError, match=problem):
        run(llm, types=["mcq"])


def test_duplicate_questions_are_dropped():
    llm = SequenceLLM([reply(question(), question())])
    assert len(run(llm).content.questions) == 1


def test_the_quiz_is_cut_to_the_requested_size():
    llm = SequenceLLM([reply(*[question(question=f"Question number {i}?") for i in range(6)])])
    assert len(run(llm, num_questions=3).content.questions) == 3


def test_lone_backslashes_of_latex_are_repaired():
    text = reply(question(question="ALPHA"))
    llm = SequenceLLM([text.replace("ALPHA", "What is $\\alpha$?")])  # one backslash in the JSON
    assert run(llm).content.questions[0].question == "What is $\\alpha$?"


def test_latex_that_json_turns_into_a_control_character_is_retried():
    # "\f" is a valid JSON escape (form feed), so "\frac" parses, silently wrong.
    broken = reply(question(question="FRAC")).replace("FRAC", "What is $\\frac{1}{2}$?")
    llm = SequenceLLM([broken, reply(question())])
    result = run(llm)
    assert len(llm.calls) == 2
    assert "doubled" in llm.calls[1][-1].content  # the feedback names the problem
    assert len(result.content.questions) == 1


def test_latin_script_converts_cyrillic_text_but_not_the_quote():
    cyrillic = "Фотосинтеза претвара светлосну енергију у хемијску енергију."
    llm = SequenceLLM(
        [
            reply(
                question(
                    question="Шта претвара фотосинтеза?",
                    options=["Светлост", "Звук", "Топлоту", "Ветар"],
                    explanation="Тако пише.",
                    evidence="Фотосинтеза претвара светлосну енергију",
                )
            )
        ]
    )
    result = run(llm, [chunk(cyrillic, "Bio")], script="latin")
    only = result.content.questions[0]
    assert only.question == "Šta pretvara fotosinteza?"
    assert only.options[0] == "Svetlost"
    assert only.explanation == "Tako piše."
    assert only.evidence.startswith("Фотосинтеза")  # a quote is kept as the source has it


def test_cyrillic_script_leaves_the_text_alone():
    llm = SequenceLLM([reply(question(question="Шта је фотосинтеза?"))])
    assert run(llm, script="cyrillic").content.questions[0].question == "Шта је фотосинтеза?"


class TestIsGrounded:
    def test_ignores_case_punctuation_and_spacing(self):
        assert is_grounded("photosynthesis,  CONVERTS light-energy", BIOLOGY)

    def test_a_quote_that_is_not_in_the_source_fails(self):
        assert not is_grounded("photosynthesis converts sound into heat", BIOLOGY)

    def test_a_too_short_quote_fails(self):
        assert not is_grounded("energy", BIOLOGY)

    def test_a_latin_quote_of_cyrillic_text_counts(self):
        assert is_grounded(
            "Fotosinteza pretvara svetlosnu", "Фотосинтеза претвара светлосну енергију"
        )
