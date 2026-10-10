import re
from collections.abc import Callable
from dataclasses import dataclass

from app.modules.sources.parsers import ParsedDocument

PAGE_SEPARATOR = "\n\n"
_PARAGRAPH = re.compile(r"(?:[^\n]|\n(?!\s*\n))+")
_SENTENCE = re.compile(r"\S.*?(?:(?<=[.!?])(?=\s)|\Z)", re.DOTALL)
_WORD = re.compile(r"\S+")


@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    char_start: int  # offsets into the document text: pages joined with a blank line
    char_end: int


@dataclass(frozen=True)
class _Unit:
    start: int
    end: int
    tokens: int


def chunk_document(
    document: ParsedDocument,
    count_tokens: Callable[[str], int],
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[Chunk]:
    """Splits a document into chunks of at most `chunk_size` tokens.

    Chunks follow natural boundaries (paragraphs, then sentences), and consecutive chunks share
    up to `overlap` tokens so that an answer on a boundary is not cut in half.
    """
    if chunk_size < 1 or not 0 <= overlap < chunk_size:
        raise ValueError("chunk_size must be >= 1 and 0 <= overlap < chunk_size")

    full_text, page_spans = _join_pages(document)
    units = _split_units(full_text, count_tokens, chunk_size)

    chunks: list[Chunk] = []
    i = 0
    while i < len(units):
        j, total = i, 0
        while j < len(units) and (j == i or total + units[j].tokens <= chunk_size):
            total += units[j].tokens
            j += 1
        start, end = units[i].start, units[j - 1].end
        page_start, page_end = _page_range(page_spans, start, end)
        chunks.append(Chunk(len(chunks), full_text[start:end], page_start, page_end, start, end))
        if j >= len(units):
            break
        # Step back over trailing units to form the overlap, always moving forward by one unit.
        k, shared = j, 0
        while k - 1 > i and shared + units[k - 1].tokens <= overlap:
            k -= 1
            shared += units[k].tokens
        i = k
    return chunks


def _join_pages(document: ParsedDocument) -> tuple[str, list[tuple[int, int, int | None]]]:
    parts: list[str] = []
    spans: list[tuple[int, int, int | None]] = []
    position = 0
    for index, page in enumerate(document.pages):
        if index > 0:
            parts.append(PAGE_SEPARATOR)
            position += len(PAGE_SEPARATOR)
        parts.append(page.text)
        spans.append((position, position + len(page.text), page.number))
        position += len(page.text)
    return "".join(parts), spans


def _page_range(
    spans: list[tuple[int, int, int | None]], start: int, end: int
) -> tuple[int | None, int | None]:
    numbers = [n for s, e, n in spans if s < end and e > start and n is not None]
    return (min(numbers), max(numbers)) if numbers else (None, None)


def _split_units(text: str, count_tokens: Callable[[str], int], limit: int) -> list[_Unit]:
    units: list[_Unit] = []
    for paragraph in _PARAGRAPH.finditer(text):
        for sentence in _SENTENCE.finditer(paragraph.group()):
            start = paragraph.start() + sentence.start()
            end = paragraph.start() + sentence.end()
            tokens = count_tokens(text[start:end])
            if tokens <= limit:
                units.append(_Unit(start, end, tokens))
            else:
                units.extend(_split_oversized(text, start, end, count_tokens, limit))
    return units


def _split_oversized(
    text: str, start: int, end: int, count_tokens: Callable[[str], int], limit: int
) -> list[_Unit]:
    """Splits a sentence longer than the limit by words, and a single huge word by characters."""
    pieces: list[_Unit] = []
    group_start = group_end = None
    group_tokens = 0
    for word in _WORD.finditer(text[start:end]):
        w_start, w_end = start + word.start(), start + word.end()
        w_tokens = count_tokens(text[w_start:w_end])
        if w_tokens > limit:
            if group_start is not None:
                pieces.append(_Unit(group_start, group_end, group_tokens))
                group_start = group_end = None
                group_tokens = 0
            pieces.extend(_split_long_word(text, w_start, w_end, count_tokens, limit))
            continue
        if group_start is not None and group_tokens + w_tokens > limit:
            pieces.append(_Unit(group_start, group_end, group_tokens))
            group_start, group_tokens = None, 0
        if group_start is None:
            group_start = w_start
        group_end = w_end
        group_tokens += w_tokens
    if group_start is not None:
        pieces.append(_Unit(group_start, group_end, group_tokens))
    return pieces


def _split_long_word(
    text: str, start: int, end: int, count_tokens: Callable[[str], int], limit: int
) -> list[_Unit]:
    pieces: list[_Unit] = []
    position = start
    while position < end:
        # Binary search for the longest piece that still fits; one character is the minimum
        # so that we always make progress.
        low, high = 1, end - position
        while low < high:
            middle = (low + high + 1) // 2
            if count_tokens(text[position : position + middle]) <= limit:
                low = middle
            else:
                high = middle - 1
        piece_end = position + low
        pieces.append(_Unit(position, piece_end, count_tokens(text[position:piece_end])))
        position = piece_end
    return pieces
