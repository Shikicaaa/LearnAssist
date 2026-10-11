import re

from app.modules.chat.prompts import NO_ANSWER_SENTINEL

_MARKER = re.compile(r"\[(\d+(?:\s*[,;]\s*\d+)*)\]")
_NOISE = "*\"'`_ \t\r\n"


def extract_cited_ranks(answer: str, max_rank: int) -> list[int]:
    """Ranks the model cited as [1], [2][3] or [1, 2], in order of first mention.

    Numbers that do not exist (the model invented [9] with only 5 sources) are dropped.
    """
    ranks: list[int] = []
    for match in _MARKER.finditer(answer):
        for number in re.split(r"[,;]", match.group(1)):
            rank = int(number)
            if 1 <= rank <= max_rank and rank not in ranks:
                ranks.append(rank)
    return ranks


def is_no_answer(text: str) -> bool:
    return text.strip(_NOISE).startswith(NO_ANSWER_SENTINEL)


class StreamFilter:
    """Keeps the "no answer" sentinel from ever reaching the client while streaming.

    The first characters decide: if the model starts to write NEMA_ODGOVORA we must not show
    it, but we cannot know that before seeing enough text. So the start is held back only as
    long as it could still turn out to be the sentinel; everything else goes straight through.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._decided = False
        self.no_answer = False

    def feed(self, text: str) -> str:
        """Returns the part of `text` (plus anything held back) that is safe to show."""
        if self._decided:
            return "" if self.no_answer else text
        self._buffer += text
        probe = self._buffer.lstrip(_NOISE)
        if probe.startswith(NO_ANSWER_SENTINEL):
            self._decided = self.no_answer = True
            self._buffer = ""
            return ""
        if probe == "" or NO_ANSWER_SENTINEL.startswith(probe):
            return ""  # could still become the sentinel: keep waiting
        self._decided = True
        released, self._buffer = self._buffer, ""
        return released

    def finish(self) -> str:
        """Releases text still held back when the stream ends (a short answer)."""
        if self._decided:
            return ""
        self._decided = True
        released, self._buffer = self._buffer, ""
        return released
