import re

# Words that point back at something said earlier ("and what about that?", "explain it again").
# English is included because students mix languages. A false positive only means the cache is
# skipped for that question, which is always safe; a false negative could serve a wrong answer.
_POINTERS = frozenset(
    """
    to ovo ono taj ta te ti tom toga tome ovaj ova ove ovog ovom onaj ona one onog tu tamo
    njega njemu nju njom njih njima njen njegov njihov
    prethodni prethodna prethodno prethodnu prethodnog prethodnom pomenut pomenuta pomenuto
    pomenuti pomenutu pomenutog spomenut spomenuta spomenuto
    ranije gore jos detaljnije podrobnije krace opet ponovo ponovi isto takodje dalje nastavi
    primer primere
    it its this that these those them they previous above earlier again more also further
    """.split()
)
_FOLD = str.maketrans({"č": "c", "ć": "c", "š": "s", "ž": "z", "đ": "dj"})


def depends_on_history(question: str) -> bool:
    """Heuristic: does the question only make sense together with the conversation so far?"""
    words = re.findall(r"\w+", question.casefold().translate(_FOLD))
    if not words:
        return False
    # "And ...", "But ..." continue the previous thought.
    return words[0] in {"a", "i", "ali", "and", "but"} or any(w in _POINTERS for w in words)
