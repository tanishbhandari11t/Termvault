"""Compact float32 vector storage and similarity helpers."""

from __future__ import annotations

import heapq
import math
from array import array
from collections.abc import Iterable, Sequence


def pack(vector: Sequence[float]) -> bytes:
    return array("f", vector).tobytes()


def unpack(blob: bytes) -> array:
    values = array("f")
    values.frombytes(blob)
    return values


def norm(vector: Sequence[float]) -> float:
    return math.sqrt(sum(value * value for value in vector))


def normalize(vector: Sequence[float]) -> list[float]:
    length = norm(vector)
    if length == 0:
        return [0.0] * len(vector)
    return [value / length for value in vector]


def dot(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError(f"Vector size mismatch: {len(left)} vs {len(right)}")
    return sum(a * b for a, b in zip(left, right))


def cosine(left: Sequence[float], right: Sequence[float]) -> float:
    denominator = norm(left) * norm(right)
    if denominator == 0:
        return 0.0
    return dot(left, right) / denominator


def top_k(
    query: Sequence[float],
    candidates: Iterable[tuple[int, Sequence[float]]],
    k: int,
    *,
    min_score: float = 0.0,
) -> list[tuple[int, float]]:
    """Best ``k`` (id, cosine) pairs; candidates are assumed L2-normalized."""
    scored = (
        (key, dot(query, vector))
        for key, vector in candidates
        if len(vector) == len(query)
    )
    best = heapq.nlargest(k, (item for item in scored if item[1] >= min_score), key=lambda item: (item[1], -item[0]))
    return [(key, round(score, 4)) for key, score in best]
