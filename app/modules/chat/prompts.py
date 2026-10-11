import re
from functools import lru_cache
from pathlib import Path

from app.modules.retrieval import RetrievedChunk

# Bump this whenever answer_v1.txt (or the way the context is built) changes. Cached answers
# are only valid for the prompt version that produced them.
PROMPT_VERSION = "answer-v2"
NO_ANSWER_SENTINEL = "NEMA_ODGOVORA"

NO_ANSWER_MESSAGE = (
    "Ne mogu da odgovorim na to pitanje na osnovu priloženog materijala. "
    "Pokušaj da ga preformulišeš ili dodaj izvor koji sadrži odgovor."
)
NO_SOURCES_MESSAGE = (
    "U ovoj sesiji još nema obrađenih izvora. "
    "Dodaj materijal (PDF, DOCX, TXT ili MD), pa postavi pitanje."
)


@lru_cache
def system_prompt() -> str:
    name = PROMPT_VERSION.replace("-", "_") + ".txt"
    return (Path(__file__).parent / "prompts" / name).read_text(encoding="utf-8").strip()


# Documents often contain their own references such as [1] or [2, 3] (theses, papers). Our
# citations use the same notation, so inside a source they are rewritten as (1) to keep
# "[n] means source n of this prompt" unambiguous for the model and for our parser.
# Not preceded by a word character or a bracket, so code like a[0] or m[i][j] is left alone.
_OWN_REFERENCE = re.compile(r"(?<![\w\])])\[(\d+(?:\s*[,;\u2013-]\s*\d+)*)\]")


def _attribute(value: str) -> str:
    return value.replace('"', "'").replace("\n", " ")


def _pages(chunk: RetrievedChunk) -> str | None:
    if chunk.page_start is None:
        return None
    if chunk.page_end is None or chunk.page_end == chunk.page_start:
        return str(chunk.page_start)
    return f"{chunk.page_start}-{chunk.page_end}"


def build_user_message(question: str, chunks: list[RetrievedChunk]) -> str:
    """The last message of the conversation: numbered sources, then the question.

    A source's number is its rank: the model cites it as [rank], and we later store that same
    rank in the citation, so the two always match.
    """
    blocks = []
    for rank, chunk in enumerate(chunks, start=1):
        attributes = f'broj="{rank}" naslov="{_attribute(chunk.source_title)}"'
        if (pages := _pages(chunk)) is not None:
            attributes += f' strana="{pages}"'
        # A document must not be able to close its own block and write instructions after it.
        text = _OWN_REFERENCE.sub(r"(\1)", chunk.text).replace("</izvor>", "<\\/izvor>")
        blocks.append(f"<izvor {attributes}>\n{text}\n</izvor>")
    return "IZVORI:\n" + "\n".join(blocks) + f"\n\nPITANJE: {question}"
