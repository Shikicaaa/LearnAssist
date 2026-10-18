import hashlib
import json
import unicodedata
import uuid
from collections.abc import Iterable

_SPECIAL = str.maketrans({"đ": "dj", "ł": "l", "ø": "o", "æ": "ae", "œ": "oe"})


def normalize_topic(topic: str) -> str:
    """
    Normalizes a topic string by applying Unicode normalization,
    case folding, and removing extra whitespace and punctuation.
    This is used to ensure that topics are compared in a consistent manner, regardless of formatting
    or case differences.
    For example, "Ćao ljudi!" and "cao ljudi" would be considered the same topic.
    """

    text = unicodedata.normalize("NFKD", topic).casefold()
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.translate(_SPECIAL)
    return " ".join(text.split()).strip(" ?!.,;:\"'")


def params_hash(
    *,
    topic: str | None,
    source_ids: Iterable[uuid.UUID],
    num_questions: int,
    difficulty: str,
    types: Iterable[str],
    script: str,
    variant: int,
) -> str:
    """
    Transforms parameters that define a quiz into a hash that can be used to identify the quiz.
    This is used to detect if the parameters have changed since the last artifact generation.
    """
    payload = {
        "kind": "quiz",
        "topic": (normalize_topic(topic) if topic else "") or None,
        "source_ids": sorted({str(s) for s in source_ids}),
        "num_questions": num_questions,
        "difficulty": difficulty,
        "types": sorted(set(types)),
        "script": script,
        "variant": variant,
    }

    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def context_hash(chunk_texts: list[str]) -> str:
    """
    This is a hash of the content of the source chunks,
    used to detect if the content has changed since the last artifact generation.
    """

    h = hashlib.sha256()
    for text in chunk_texts:
        h.update(hashlib.sha256(text.encode("utf-8")).digest())
    return h.hexdigest()
