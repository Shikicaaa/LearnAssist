from collections.abc import Iterable
from functools import lru_cache
from pathlib import Path

from app.modules.retrieval import RetrievedChunk

# Bump this whenever quiz_v1.txt (or the way the sources and the task are laid out below)
# changes. A stored quiz is only valid for the prompt version that produced it.
QUIZ_PROMPT_VERSION = "quiz-v1"
NO_MATERIAL_SENTINEL = "NEMA_MATERIJALA"


@lru_cache
def system_prompt() -> str:
    name = QUIZ_PROMPT_VERSION.replace("-", "_") + ".txt"
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").strip()


def _attribute(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ").strip()


def _pages(chunk: RetrievedChunk) -> str | None:
    if chunk.page_start is None:
        return None
    if chunk.page_end is None or chunk.page_end == chunk.page_start:
        return str(chunk.page_start)
    return f"{chunk.page_start}-{chunk.page_end}"


def build_user_message(
    chunks: list[RetrievedChunk],
    *,
    topic: str | None,
    num_questions: int,
    difficulty: str,
    types: Iterable[str],
    script: str,
) -> str:
    """The only message of the conversation: numbered sources, then the task.

    A source's number is its position in `chunks` (from 1). The model returns it as
    `source_rank`, and the generator maps it back to the same chunk, so the two always match.
    """
    blocks = []
    for rank, chunk in enumerate(chunks, start=1):
        attributes = f'broj="{rank}" naslov="{_attribute(chunk.source_title)}"'
        if (pages := _pages(chunk)) is not None:
            attributes += f' strana="{pages}"'
        # A document must not be able to close its own block and write instructions after it.
        text = chunk.text.replace("</izvor>", "<\\/izvor>")
        blocks.append(f"<izvor {attributes}>\n{text}\n</izvor>")

    task = [
        f"Broj pitanja: {num_questions}",
        f"Težina: {difficulty}",
        f"Dozvoljeni tipovi: {', '.join(sorted(set(types)))}",
        f"Pismo: {'latinica' if script == 'latin' else 'ćirilica'}",
    ]
    if topic:
        task.append(f"Tema: {topic}")
    return "IZVORI:\n" + "\n".join(blocks) + "\n\nZADATAK:\n" + "\n".join(task)
