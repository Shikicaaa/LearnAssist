import math

import pytest

from app.modules.embeddings import E5Embedder, FakeEmbedder, embedding_dim


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b, strict=True))


class TestFakeEmbedder:
    def test_vectors_have_right_dimension_and_unit_length(self):
        vec = FakeEmbedder().embed_query("sta je derivacija")
        assert len(vec) == 384
        assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-6)

    def test_is_deterministic(self):
        e = FakeEmbedder()
        assert e.embed_query("isti tekst") == e.embed_query("isti tekst")

    def test_similar_texts_are_closer_than_unrelated(self):
        e = FakeEmbedder()
        query = e.embed_query("derivacija funkcije")
        related, unrelated = e.embed_passages(
            ["derivacija funkcije se racuna preko granicne vrednosti", "bitka na kosovu 1389"]
        )
        assert cosine(query, related) > cosine(query, unrelated)

    def test_batch_matches_single(self):
        e = FakeEmbedder()
        assert e.embed_passages(["a b", "c d"])[1] == e.embed_passages(["c d"])[0]


class TestModelRegistry:
    def test_dimension_of_known_model(self):
        assert embedding_dim("multilingual-e5-small") == 384

    def test_unknown_model_raises_clear_error(self):
        with pytest.raises(ValueError, match="Unknown embedding model"):
            embedding_dim("nepostojeci-model")


@pytest.fixture(scope="module")
def embedder():
    return E5Embedder("multilingual-e5-small", device="cpu", batch_size=8)


@pytest.mark.slow
class TestRealE5Model:
    def test_shape_and_normalization(self, embedder):
        vec = embedder.embed_query("Šta je derivacija?")
        assert len(vec) == embedder.dim == 384
        assert math.isclose(math.sqrt(sum(v * v for v in vec)), 1.0, rel_tol=1e-4)

    def test_serbian_query_matches_relevant_passage(self, embedder):
        query = embedder.embed_query("Šta je derivacija funkcije?")
        relevant, unrelated = embedder.embed_passages(
            [
                "Derivacija funkcije u tački je granična vrednost količnika priraštaja.",
                "Bitka na Kosovu odigrala se 1389. godine između Srba i Osmanlija.",
            ]
        )
        assert cosine(query, relevant) > cosine(query, unrelated)

    def test_count_tokens_is_positive_and_monotonic(self, embedder):
        short = embedder.count_tokens("kratka rečenica")
        long = embedder.count_tokens("kratka rečenica " * 20)
        assert 0 < short < long
