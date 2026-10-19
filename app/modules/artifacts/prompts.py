from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path
from app.modules.artifacts.schemas import RetrievedChunk

QUIZ_PROMPT_VERSION = "quiz-v1"
NO_MATERIAL_SENTINEL = "NEMA_MATERIJALA"

@lru_cache
def system_prompt() -> str:
    name = QUIZ_PROMPT_VERSION.replace("-", "_") + ".txt"
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").strip()


def _attribute(value: str) -> str:
    return value.replace("\n", " ").replace('"', "'").strip()

def _pages(chunk: RetrievedChunk) -> str | None:
    if chunk.page_start is None:
        return None
    if chunk.page_end is None or chunk.page_end == chunk.page_start:
        return f"str. {chunk.page_start}"
    return f"str. {chunk.page_start}-{chunk.page_end}"


def build_user_message(
    chunks: list[RetrievedChunk], *, topic: str | None, num_questions: int,
    difficulty: str, types: Iterable[str], script: str
) -> str:
    blocks = []
    for rank, chunk in enumerate(chunks, start = 1):
        attributes = f'number={rank}, title="{_attribute(chunk.source_title)}"'
        if (page := _pages(chunk)) is not None:
            attributes += f", pages={page}"

        text = chunk.text.replace("</izvor>", "<\\/izvor>")
        blocks.append(f"<izvor {attributes}>{text}</izvor>")

    task = [
        f"Number of questions: {num_questions}",
        f"Difficulty: {difficulty}",
        f"Allowed types: {', '.join(sorted(set(types)))}",
        f"Script: {'latin' if script == 'latin' else 'cyrillic'}",
    ]

    if topic:
        task.append(f"Topic: {topic}")
    return "SOURCES:\n" + "\n\n".join(blocks) + "\n\nTASK:\n" + "\n".join(task)