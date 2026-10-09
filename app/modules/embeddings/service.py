import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from app.shared.config import get_settings

# Internal model names -> (Hugging Face id, vector dimension, question prefix, passage prefix)
MODELS: dict[str, tuple[str, int, str, str]] = {
    "multilingual-e5-small": ("intfloat/multilingual-e5-small", 384, "query: ", "passage: "),
}


def embedding_dim(model_name: str | None = None) -> int:
    return _model_spec(model_name or get_settings().embedding_model)[1]


def _model_spec(model_name: str) -> tuple[str, int, str, str]:
    try:
        return MODELS[model_name]
    except KeyError:
        raise ValueError(f"Unknown embedding model '{model_name}'. Known: {list(MODELS)}") from None


class Embedder(Protocol):
    model_name: str
    dim: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...

    def count_tokens(self, text: str) -> int: ...


class E5Embedder:
    def __init__(self, model_name: str, device: str, batch_size: int):
        self.model_name = model_name
        self._hf_id, self.dim, self._query_prefix, self._passage_prefix = _model_spec(model_name)
        self._device = device
        self._batch_size = batch_size
        self._model = None

    def _load(self):
        # Lazy loading: importing torch and the model takes seconds, but the API doesn't need them at startup.
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._hf_id, device=self._device)
        return self._model

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self._passage_prefix + t for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self._query_prefix + text])[0]

    def count_tokens(self, text: str) -> int:
        return len(self._load().tokenizer(text, add_special_tokens=False)["input_ids"])


class FakeEmbedder:
    """Fake embedder for testing: returns a deterministic vector based on the text hash."""
    def __init__(self, dim: int = 384, model_name: str = "multilingual-e5-small"):
        self.dim = dim
        self.model_name = model_name

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in re.findall(r"\w+", text.lower()):
            bucket = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], "big") % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    return E5Embedder(s.embedding_model, s.embedding_device, s.embedding_batch_size)
