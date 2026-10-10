import random

import pytest

from app.modules.embeddings import E5Embedder, FakeEmbedder
from app.modules.sources.chunker import PAGE_SEPARATOR, chunk_document
from app.modules.sources.parsers import ParsedDocument, ParsedPage

count = FakeEmbedder().count_tokens  # one word = one token


def doc(*texts, numbers=None):
    numbers = numbers or [None] * len(texts)
    return ParsedDocument([ParsedPage(n, t) for n, t in zip(numbers, texts, strict=True)], None)


def sentences(n, words_per_sentence=10, prefix="w"):
    return " ".join(
        " ".join(f"{prefix}{s}_{w}" for w in range(words_per_sentence)) + "." for s in range(n)
    )


def full_text(document):
    return PAGE_SEPARATOR.join(p.text for p in document.pages)


class TestBasics:
    def test_short_document_is_a_single_chunk(self):
        d = doc("One short sentence.")
        chunks = chunk_document(d, count, chunk_size=100, overlap=10)
        assert len(chunks) == 1
        assert chunks[0].text == "One short sentence."
        assert (chunks[0].char_start, chunks[0].char_end) == (0, 19)

    def test_empty_document_gives_no_chunks(self):
        assert chunk_document(ParsedDocument([], None), count) == []

    @pytest.mark.parametrize("size,overlap", [(0, 0), (10, 10), (10, 11), (10, -1)])
    def test_invalid_parameters_are_rejected(self, size, overlap):
        with pytest.raises(ValueError):
            chunk_document(doc("x"), count, chunk_size=size, overlap=overlap)


class TestSizeAndOverlap:
    def test_chunks_never_exceed_size_and_offsets_match_text(self):
        d = doc(sentences(120))
        chunks = chunk_document(d, count, chunk_size=50, overlap=10)
        text = full_text(d)
        assert len(chunks) > 5
        for chunk in chunks:
            assert count(chunk.text) <= 50
            assert text[chunk.char_start : chunk.char_end] == chunk.text

    def test_indexes_are_consecutive_and_starts_strictly_increase(self):
        chunks = chunk_document(doc(sentences(120)), count, chunk_size=50, overlap=10)
        assert [c.index for c in chunks] == list(range(len(chunks)))
        starts = [c.char_start for c in chunks]
        assert starts == sorted(set(starts))

    def test_neighbouring_chunks_overlap_but_not_beyond_the_limit(self):
        chunks = chunk_document(doc(sentences(120)), count, chunk_size=50, overlap=20)
        for before, after in zip(chunks, chunks[1:], strict=False):
            assert after.char_start < before.char_end  # they share text
            shared = before.text[after.char_start - before.char_start :]
            assert 0 < count(shared) <= 20

    def test_zero_overlap_gives_disjoint_chunks(self):
        chunks = chunk_document(doc(sentences(120)), count, chunk_size=50, overlap=0)
        for before, after in zip(chunks, chunks[1:], strict=False):
            assert after.char_start >= before.char_end

    def test_every_word_is_covered(self):
        d = doc(sentences(80), sentences(80, prefix="p"))
        chunks = chunk_document(d, count, chunk_size=40, overlap=8)
        covered = " ".join(c.text for c in chunks)
        for word in full_text(d).split():
            assert word in covered

    def test_chunks_split_on_sentence_boundaries_when_possible(self):
        chunks = chunk_document(doc(sentences(60)), count, chunk_size=50, overlap=0)
        assert all(c.text.endswith(".") for c in chunks)


class TestOversizedText:
    def test_one_giant_sentence_is_split_by_words(self):
        giant = " ".join(f"word{i}" for i in range(1200))  # no punctuation at all
        chunks = chunk_document(doc(giant), count, chunk_size=500, overlap=50)
        assert len(chunks) >= 3
        assert all(count(c.text) <= 500 for c in chunks)

    def test_one_giant_word_is_split_by_characters(self):
        # Tokens here are characters / 10, so a 100-character word is 10 tokens.
        def per_ten_chars(text):
            return -(-len(text.replace(" ", "")) // 10)

        chunks = chunk_document(doc("x" * 1000), per_ten_chars, chunk_size=20, overlap=0)
        assert len(chunks) == 5
        assert all(per_ten_chars(c.text) <= 20 for c in chunks)
        assert "".join(c.text for c in chunks) == "x" * 1000

    def test_always_terminates_and_covers_text_for_any_settings(self):
        rng = random.Random(7)
        vocabulary = ["alpha", "beta", "gamma", "delta."] + [f"w{i}" for i in range(30)]
        for _ in range(60):
            text = " ".join(rng.choice(vocabulary) for _ in range(rng.randint(1, 300)))
            size = rng.randint(1, 40)
            overlap = rng.randint(0, size - 1)
            chunks = chunk_document(doc(text), count, chunk_size=size, overlap=overlap)
            assert chunks
            assert all(count(c.text) <= size for c in chunks)
            assert chunks[0].char_start == 0 and chunks[-1].char_end == len(text)


class TestPages:
    def test_chunk_inside_one_page_has_that_page(self):
        d = doc("First page text here.", "Second page text here.", numbers=[1, 2])
        chunks = chunk_document(d, count, chunk_size=4, overlap=0)
        assert [(c.text, c.page_start, c.page_end) for c in chunks] == [
            ("First page text here.", 1, 1),
            ("Second page text here.", 2, 2),
        ]

    def test_chunk_spanning_pages_reports_both(self):
        d = doc("End of page one.", "Start of page two.", numbers=[1, 2])
        chunks = chunk_document(d, count, chunk_size=100, overlap=0)
        assert (chunks[0].page_start, chunks[0].page_end) == (1, 2)

    def test_skipped_pages_keep_their_real_numbers(self):
        d = doc("Alpha beta gamma.", "Delta epsilon zeta.", numbers=[3, 9])
        chunks = chunk_document(d, count, chunk_size=3, overlap=0)
        assert [(c.page_start, c.page_end) for c in chunks] == [(3, 3), (9, 9)]

    def test_documents_without_page_numbers_give_none(self):
        chunks = chunk_document(doc(sentences(30)), count, chunk_size=20, overlap=0)
        assert all(c.page_start is None and c.page_end is None for c in chunks)


@pytest.mark.slow
def test_chunks_fit_the_real_model_limit_with_prefix():
    embedder = E5Embedder("multilingual-e5-small", device="cpu", batch_size=8)
    rng = random.Random(3)
    words = "student ispit predavanje derivacija funkcija granična vrednost teorema dokaz".split()
    sentences_ = (
        " ".join(rng.choice(words) for _ in range(rng.randint(5, 40))) for _ in range(300)
    )
    text = ". ".join(sentences_)
    chunks = chunk_document(doc(text + "."), embedder.count_tokens, chunk_size=500, overlap=50)
    assert len(chunks) > 3
    for chunk in chunks:
        # What the model really receives: the "passage: " prefix plus 2 special tokens.
        assert embedder.count_tokens("passage: " + chunk.text) + 2 <= 512
