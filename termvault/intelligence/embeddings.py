"""Embedding backends.

``HashingBackend`` is dependency-free and fully local: signed feature hashing of
stemmed words, word bigrams, and character trigrams. It captures lexical and
morphological similarity ("restart nginx" ≈ "restarting nginx service").

``SentenceTransformerBackend`` is opt-in (``pip install termvault[semantic]``)
and may download a model on first use.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from typing import Protocol

from termvault.intelligence.constants import DEFAULT_HASHING_DIM, DEFAULT_ST_MODEL
from termvault.intelligence.errors import BackendUnavailableError, IntelligenceError
from termvault.intelligence.text import char_ngrams, tokenize, word_bigrams
from termvault.intelligence.vectors import normalize

HASHING_PREFIX = "hashing"
ST_PREFIX = "st"
ST_ALIASES = ("st", "sentence-transformers", "semantic")

WORD_WEIGHT = 1.0
BIGRAM_WEIGHT = 0.6
TRIGRAM_WEIGHT = 0.3


class EmbeddingBackend(Protocol):
    @property
    def key(self) -> str: ...

    @property
    def dim(self) -> int: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def text_features(text: str) -> Counter[str]:
    words = tokenize(text, stemmed=True, drop_stopwords=True)
    features: Counter[str] = Counter()
    for word in words:
        features[f"w:{word}"] += WORD_WEIGHT
        if len(word) >= 4:
            for gram in char_ngrams(word):
                features[f"c:{gram}"] += TRIGRAM_WEIGHT
    for bigram in word_bigrams(words):
        features[f"b:{bigram}"] += BIGRAM_WEIGHT
    return features


class HashingBackend:
    """Signed feature hashing into a fixed-size, L2-normalized vector."""

    def __init__(self, dim: int = DEFAULT_HASHING_DIM) -> None:
        if dim < 16 or dim > 8192:
            raise IntelligenceError("Hashing dimension must be between 16 and 8192.")
        self._dim = dim

    @property
    def key(self) -> str:
        return f"{HASHING_PREFIX}-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self._dim
        for feature, weight in text_features(text).items():
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self._dim
            sign = 1.0 if digest[4] & 1 else -1.0
            damped = 1.0 + math.log(weight) if weight >= 1 else weight
            vector[index] += sign * damped
        return normalize(vector)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


class SentenceTransformerBackend:
    """Neural embeddings via the optional ``sentence-transformers`` package."""

    def __init__(self, model_name: str = DEFAULT_ST_MODEL) -> None:
        self.model_name = model_name
        self._model = None

    def _load(self):  # pragma: no cover - requires optional dependency
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise BackendUnavailableError(
                    "Semantic backend needs sentence-transformers. "
                    "Install it with: pip install \"termvault[semantic]\""
                ) from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    @property
    def key(self) -> str:
        return f"{ST_PREFIX}:{self.model_name}"

    @property
    def dim(self) -> int:  # pragma: no cover - requires optional dependency
        return int(self._load().get_sentence_embedding_dimension())

    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        model = self._load()
        vectors = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return [list(map(float, vector)) for vector in vectors]


def get_backend(spec: str | None = None) -> EmbeddingBackend:
    """Parse a backend spec: ``hashing``, ``hashing:256``, ``st``, ``st:<model>``."""
    if spec is None or not spec.strip():
        return HashingBackend()
    value = spec.strip()
    name, _, option = value.partition(":")
    name = name.lower()
    if name == HASHING_PREFIX:
        if not option:
            return HashingBackend()
        try:
            return HashingBackend(int(option))
        except ValueError as exc:
            raise IntelligenceError(f"Invalid hashing dimension: {option!r}") from exc
    if name in ST_ALIASES:
        return SentenceTransformerBackend(option or DEFAULT_ST_MODEL)
    raise IntelligenceError(
        f"Unknown embedding backend {spec!r}. Use 'hashing', 'hashing:<dim>', or 'st[:model]'."
    )


def backend_from_key(key: str) -> EmbeddingBackend:
    """Rebuild a backend from the key stored in ``entry_embeddings.backend``."""
    if key.startswith(f"{HASHING_PREFIX}-"):
        return HashingBackend(int(key.split("-", 1)[1]))
    if key.startswith(f"{ST_PREFIX}:"):
        return SentenceTransformerBackend(key.split(":", 1)[1])
    raise IntelligenceError(f"Unrecognized stored backend key {key!r}.")
