import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from app.modules.artifacts.prompts import NO_MATERIAL_SENTINEL, build_user_message, system_prompt
from app.modules.artifacts.schemas import (
    GeneratedQuestion,
    QuizCitation,
    QuizContent,
    QuizQuestion,
)
from app.modules.llm import LLMMessage, LLMProvider
from app.modules.retrieval import RetrievedChunk
from app.shared.config import get_settings
from app.shared.script import to_latin

# The first call, plus one more in which the model is told what was wrong with its reply.
MAX_ATTEMPTS = 2
# Evidence shorter than this (letters and digits only) would match almost anywhere.
MIN_EVIDENCE_CHARS = 8

# A single backslash in JSON ("\frac") is read as a control character (form feed), and "\beta",
# "\rho", "\theta" and "\nu" the same way. None of these belong in a quiz, so they mean the
# model forgot to double the backslashes of its LaTeX.
_CONTROL_CHARS = re.compile(r"[\x00-\x09\x0b-\x1f]")


class NoMaterialError(Exception):
    """The model says the sources do not contain enough to build a quiz."""


class InvalidQuizError(Exception):
    """The model never produced a usable quiz, even after being told what was wrong."""


@dataclass(frozen=True)
class GeneratedQuizResult:
    content: QuizContent
    provider: str
    model: str
    tokens_in: int
    tokens_out: int


def generate_quiz(
    provider: LLMProvider,
    chunks: list[RetrievedChunk],
    *,
    topic: str | None,
    num_questions: int,
    difficulty: str,
    types: Iterable[str],
    script: str,
) -> GeneratedQuizResult:
    """Asks the model for a quiz and keeps only the questions that check out.

    The reply is untrusted. Each question is validated on its own, so one bad question does not
    cost the others, and it must quote its source word for word (`evidence`), which is checked
    against the chunk the question claims to come from. Only if nothing survives is the model
    asked once more, with the problems listed.
    """
    allowed = set(types)
    messages = [
        LLMMessage(
            "user",
            build_user_message(
                chunks,
                topic=topic,
                num_questions=num_questions,
                difficulty=difficulty,
                types=allowed,
                script=script,
            ),
        )
    ]
    tokens_in = tokens_out = 0
    problems: list[str] = []

    for _ in range(MAX_ATTEMPTS):
        result = provider.generate(
            messages,
            system=system_prompt(),
            max_output_tokens=get_settings().quiz_max_output_tokens,
        )
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        reply = result.text.strip()

        if reply.startswith(NO_MATERIAL_SENTINEL):
            raise NoMaterialError("The material does not contain enough to build a quiz.")

        questions, problems = parse_reply(reply, chunks, allowed)
        if questions:
            return GeneratedQuizResult(
                content=_to_content(questions[:num_questions], chunks, script),
                provider=result.provider,
                model=result.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
            )
        messages = [
            *messages,
            LLMMessage("assistant", reply),
            LLMMessage("user", _feedback(problems)),
        ]

    raise InvalidQuizError(
        "The model did not return a usable quiz: " + "; ".join(problems[:3] or ["empty reply"])
    )


def parse_reply(
    reply: str, chunks: list[RetrievedChunk], allowed_types: set[str]
) -> tuple[list[GeneratedQuestion], list[str]]:
    """The valid questions of a reply, and a list of what was wrong with the others."""
    try:
        data = _loads(_extract_json(reply))
    except ValueError as exc:
        return [], [f"the reply is not valid JSON ({exc})"]
    items = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return [], ['the JSON must be an object with a "questions" list']

    questions: list[GeneratedQuestion] = []
    problems: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(items, start=1):
        label = f"question {index}"
        try:
            question = GeneratedQuestion.model_validate(item)
        except ValidationError as exc:
            problems.append(f"{label}: {exc.errors()[0]['msg']}")
            continue
        if question.type not in allowed_types:
            problems.append(f"{label}: type {question.type} was not requested")
        elif question.source_rank > len(chunks):
            problems.append(f"{label}: there is no source number {question.source_rank}")
        elif _has_control_chars(question):
            problems.append(f"{label}: backslashes in LaTeX must be doubled in JSON")
        elif not is_grounded(question.evidence, chunks[question.source_rank - 1].text):
            problems.append(
                f"{label}: evidence is not a verbatim quote of source {question.source_rank}"
            )
        elif (key := _squash(question.question)) in seen:
            problems.append(f"{label}: duplicate question")
        else:
            seen.add(key)
            questions.append(question)
    return questions, problems


def is_grounded(evidence: str, source_text: str) -> bool:
    """Is `evidence` a quote of `source_text`? Compared on letters and digits only, so quote
    marks, dashes, spacing and line breaks (which the model and the PDF parser disagree on) do
    not matter. A Latin quote of Cyrillic text counts too."""
    quote = _squash(evidence)
    if len(quote) < MIN_EVIDENCE_CHARS:
        return False
    return quote in _squash(source_text) or quote in _squash(to_latin(source_text))


def _squash(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())


def _has_control_chars(question: GeneratedQuestion) -> bool:
    texts = [question.question, question.explanation, question.evidence, *question.options]
    if question.correct_answer:
        texts.append(question.correct_answer)
    return any(_CONTROL_CHARS.search(text) for text in texts)


def _extract_json(reply: str) -> str:
    """The JSON object in a reply, even if the model wrapped it in ``` fences or added a line
    of text around it despite being told not to."""
    start, end = reply.find("{"), reply.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return reply[start : end + 1]


def _loads(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # LaTeX such as \alpha has a lone backslash, which JSON rejects. Escape every backslash
        # that is not already part of a valid JSON escape, then try once more.
        repaired = re.sub(
            r'\\(["\\/bfnrt]|u[0-9a-fA-F]{4})|\\',
            lambda m: m.group(0) if m.group(1) else "\\\\",
            raw,
        )
        return json.loads(repaired)


def _feedback(problems: list[str]) -> str:
    listed = "; ".join(problems[:5]) or "the reply could not be used"
    return (
        f"Prethodni odgovor nije ispravan: {listed}. "
        "Vrati ponovo ceo JSON objekat, bez ikakvog dodatnog teksta."
    )


def _to_content(
    questions: list[GeneratedQuestion], chunks: list[RetrievedChunk], script: str
) -> QuizContent:
    def convert(text: str) -> str:
        return to_latin(text) if script == "latin" else text

    out = []
    for question in questions:
        chunk = chunks[question.source_rank - 1]
        out.append(
            QuizQuestion(
                type=question.type,
                question=convert(question.question),
                options=[convert(option) for option in question.options],
                correct_index=question.correct_index,
                correct_answer=convert(question.correct_answer)
                if question.correct_answer
                else None,
                explanation=convert(question.explanation),
                evidence=question.evidence,
                citation=QuizCitation(
                    chunk_id=chunk.chunk_id,
                    source_id=chunk.source_id,
                    source_title=chunk.source_title,
                    page_start=chunk.page_start,
                    page_end=chunk.page_end,
                ),
            )
        )
    return QuizContent(questions=out)
