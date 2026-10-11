import hashlib
import re
import unicodedata

_DIACRITICS = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj"})


def normalize_question(question: str) -> str:
    """Lower-cases, folds Serbian diacritics and trims whitespace and trailing punctuation, so
    "Šta je ARIES?" and "sta  je aries" are the same question.

    Symbols inside the question are kept on purpose: "2+3" and "2-3" must stay different.
    """
    text = unicodedata.normalize("NFKC", question).casefold().translate(_DIACRITICS)
    return " ".join(text.split()).strip(" ?!.,;:")


def question_hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode()).hexdigest()


# Words that flip the meaning of a question. Embeddings barely notice them: "What is X?" and
# "What is not X?" are almost the same vector, but their answers are opposite.
_NEGATIONS = frozenset(
    """
    ne nije nisu nisam nismo niste nema nemoj nemaju bez nikad nikada nista niko nikako ni
    не није нису нисам нема немој без никад никада ништа нико
    not no never without cannot cant dont doesnt isnt arent wasnt
    """.split()
)


def meaning_markers(normalized: str) -> frozenset[str]:
    """The negations and the numbers in a question. Two questions may share a cached answer
    on similarity alone only if these match: "2+3" vs "2+4" and "is" vs "is not" are almost
    identical to an embedding model, yet need different answers."""
    tokens = re.findall(r"[\w'^+*/=-]+", normalized)
    return frozenset(
        t.replace("'", "")
        for t in tokens
        if t.replace("'", "") in _NEGATIONS or re.search(r"\d", t)
    )
