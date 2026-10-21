import re

_CYRILLIC = re.compile("[\u0400-\u04ff]")
_PAIRS = {
    "А": "A",
    "Б": "B",
    "В": "V",
    "Г": "G",
    "Д": "D",
    "Ђ": "Đ",
    "Е": "E",
    "Ж": "Ž",
    "З": "Z",
    "И": "I",
    "Ј": "J",
    "К": "K",
    "Л": "L",
    "Љ": "Lj",
    "М": "M",
    "Н": "N",
    "Њ": "Nj",
    "О": "O",
    "П": "P",
    "Р": "R",
    "С": "S",
    "Т": "T",
    "Ћ": "Ć",
    "У": "U",
    "Ф": "F",
    "Х": "H",
    "Ц": "C",
    "Ч": "Č",
    "Џ": "Dž",
    "Ш": "Š",
}
_TABLE = str.maketrans(
    {**_PAIRS, **{cyrillic.lower(): latin.lower() for cyrillic, latin in _PAIRS.items()}}
)


def contains_cyrillic(text: str) -> bool:
    return _CYRILLIC.search(text) is not None


def to_latin(text: str) -> str:
    """Serbian Cyrillic -> Latin. Each letter maps on its own (љ -> lj, њ -> nj, џ -> dž), so the
    result is the same whether a text is converted whole or piece by piece while streaming."""
    return text.translate(_TABLE)
