"""Tunables for Phase 7 search intelligence."""

from __future__ import annotations

from typing import Final

FIND_MODES: Final[tuple[str, ...]] = ("hybrid", "fts", "fuzzy", "semantic")
DEFAULT_FIND_MODE: Final[str] = "hybrid"

# Fuzzy field weights: a hit in the title matters more than one in the body.
FIELD_WEIGHTS: Final[dict[str, float]] = {"title": 3.0, "tags": 2.5, "body": 1.0}
FUZZY_MIN_SCORE: Final[float] = 0.25
PREFIX_MIN_LENGTH: Final[int] = 3

# Reciprocal rank fusion
RRF_K: Final[int] = 60
RRF_WEIGHTS: Final[dict[str, float]] = {"fts": 1.0, "fuzzy": 0.8, "semantic": 0.8}
CANDIDATE_POOL_MIN: Final[int] = 30

# Embeddings
DEFAULT_HASHING_DIM: Final[int] = 512
DEFAULT_ST_MODEL: Final[str] = "all-MiniLM-L6-v2"
SEMANTIC_MIN_SCORE: Final[float] = 0.10
EMBED_BATCH_SIZE: Final[int] = 64

CORPUS_FETCH_CAP: Final[int] = 1_000_000
MAX_SUGGESTIONS: Final[int] = 3
