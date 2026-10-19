"""Text embeddings for RAG and de-duplication (384 dimensions).

`e5` uses intfloat/multilingual-e5-small via sentence-transformers (install the `ml` extra on the
server). `hash` is a dependency-free stand-in for tests and laptops without the model: it captures
word overlap only, so it's fine for dedupe tests but not for real retrieval quality.
"""

import hashlib
import math
import re
from functools import lru_cache
from typing import Protocol

from doctune.core.config import get_settings
from doctune.models.document import EMBEDDING_DIM

E5_MODEL = "intfloat/multilingual-e5-small"


class Encoder(Protocol):
    def passages(self, texts: list[str]) -> list[list[float]]: ...
    def query(self, text: str) -> list[float]: ...


class HashingEncoder:
    def _vec(self, text: str) -> list[float]:
        v = [0.0] * EMBEDDING_DIM
        for word in re.findall(r"\w+", text.lower()):
            h = int.from_bytes(hashlib.blake2b(word.encode(), digest_size=8).digest(), "big")
            v[h % EMBEDDING_DIM] += 1.0 if (h >> 32) & 1 else -1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def passages(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def query(self, text: str) -> list[float]:
        return self._vec(text)


class E5Encoder:
    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(E5_MODEL, device="cpu")

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self.model.encode(texts, batch_size=32, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, v)) for v in vectors]

    def passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts])

    def query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]


@lru_cache
def get_encoder() -> Encoder:
    if get_settings().embedding_backend == "hash":
        return HashingEncoder()
    try:
        return E5Encoder()
    except ImportError:
        import structlog

        structlog.get_logger().warning(
            "embeddings_degraded",
            reason="sentence-transformers not installed (uv sync --extra ml); using the word-overlap fallback",
        )
        return HashingEncoder()


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
