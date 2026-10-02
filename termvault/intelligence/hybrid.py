"""``tv find``: combine full-text, fuzzy, and semantic rankings.

Hybrid mode uses weighted reciprocal rank fusion (RRF): each ranker contributes
``weight / (k + rank)`` per entry, so agreement across rankers wins without
having to calibrate their raw scores against each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from termvault import storage
from termvault.errors import ValidationError
from termvault.intelligence.constants import (
    CANDIDATE_POOL_MIN,
    DEFAULT_FIND_MODE,
    FIND_MODES,
    RRF_K,
    RRF_WEIGHTS,
)
from termvault.intelligence.corpus import load_corpus
from termvault.intelligence.embeddings import EmbeddingBackend
from termvault.intelligence.errors import IntelligenceError
from termvault.intelligence.fuzzy import FuzzyIndex
from termvault.intelligence.index import resolve_backend, semantic_search
from termvault.intelligence.suggest import suggest_queries
from termvault.models import Entry


@dataclass(frozen=True)
class SourceRank:
    rank: int
    score: float
    detail: str = ""


@dataclass
class FindHit:
    entry: Entry
    score: float
    sources: dict[str, SourceRank] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry.to_dict(),
            "score": self.score,
            "sources": {
                name: {"rank": source.rank, "score": source.score, "detail": source.detail}
                for name, source in self.sources.items()
            },
        }


@dataclass
class FindResult:
    query: str
    mode: str
    hits: list[FindHit]
    suggestions: list[str] = field(default_factory=list)
    backend_key: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "mode": self.mode,
            "backend": self.backend_key,
            "count": len(self.hits),
            "hits": [hit.to_dict() for hit in self.hits],
            "suggestions": list(self.suggestions),
        }


def normalize_mode(mode: str | None) -> str:
    value = (mode or DEFAULT_FIND_MODE).strip().lower()
    if value not in FIND_MODES:
        raise ValidationError("Mode must be one of: " + ", ".join(FIND_MODES))
    return value


def _fts_ranking(query: str, pool: int, tag: str | None, kind: str | None) -> list[tuple[Entry, SourceRank]]:
    try:
        hits = storage.search_entries(query, limit=pool, tag=tag, kind=kind)
    except ValidationError:
        return []
    return [
        (hit.entry, SourceRank(rank=index + 1, score=round(-hit.rank, 4)))
        for index, hit in enumerate(hits)
    ]


def _fuzzy_ranking(index: FuzzyIndex, query: str, pool: int) -> list[tuple[Entry, SourceRank]]:
    ranked: list[tuple[Entry, SourceRank]] = []
    for position, hit in enumerate(index.search(query, limit=pool)):
        detail = ", ".join(f"{wrong}->{right}" for wrong, right in hit.corrections)
        ranked.append((hit.entry, SourceRank(rank=position + 1, score=hit.score, detail=detail)))
    return ranked


def _semantic_ranking(
    query: str,
    pool: int,
    tag: str | None,
    kind: str | None,
    backend: EmbeddingBackend,
) -> list[tuple[Entry, SourceRank]]:
    hits = semantic_search(query, limit=pool, tag=tag, kind=kind, backend=backend)
    return [
        (hit.entry, SourceRank(rank=index + 1, score=hit.score))
        for index, hit in enumerate(hits)
    ]


def fuse_rankings(
    rankings: dict[str, list[tuple[Entry, SourceRank]]],
    *,
    k: int = RRF_K,
    weights: dict[str, float] | None = None,
) -> list[FindHit]:
    """Weighted RRF. Scores are scaled so #1 in every ranker that ran scores 1.0."""
    weights = weights or RRF_WEIGHTS
    ceiling = sum(weights.get(name, 1.0) / (k + 1) for name in rankings) or 1.0
    combined: dict[int, FindHit] = {}
    for name, ranked in rankings.items():
        weight = weights.get(name, 1.0)
        for entry, source in ranked:
            hit = combined.setdefault(entry.id, FindHit(entry=entry, score=0.0))
            hit.score += weight / (k + source.rank)
            hit.sources[name] = source
    hits = list(combined.values())
    for hit in hits:
        hit.score = round(hit.score / ceiling, 4)
    hits.sort(key=lambda hit: (-hit.score, -len(hit.sources), not hit.entry.pinned, hit.entry.id))
    return hits


def find_entries(
    query: str,
    *,
    mode: str = DEFAULT_FIND_MODE,
    limit: int = 10,
    tag: str | None = None,
    kind: str | None = None,
    backend: str | EmbeddingBackend | None = None,
    suggest: bool = True,
) -> FindResult:
    if not query.strip():
        raise IntelligenceError("Query must not be empty.")
    if limit < 1:
        raise ValidationError("Limit must be at least 1.")
    chosen_mode = normalize_mode(mode)
    pool = max(limit * 3, CANDIDATE_POOL_MIN)

    corpus = load_corpus(tag=tag, kind=kind)
    fuzzy_index = FuzzyIndex(corpus)

    chosen_backend: EmbeddingBackend | None = None
    if chosen_mode in {"semantic", "hybrid"}:
        chosen_backend = backend if not isinstance(backend, (str, type(None))) else resolve_backend(backend)

    rankings: dict[str, list[tuple[Entry, SourceRank]]] = {}
    if chosen_mode in {"fts", "hybrid"}:
        rankings["fts"] = _fts_ranking(query, pool, tag, kind)
    if chosen_mode in {"fuzzy", "hybrid"}:
        rankings["fuzzy"] = _fuzzy_ranking(fuzzy_index, query, pool)
    if chosen_mode in {"semantic", "hybrid"} and chosen_backend is not None:
        rankings["semantic"] = _semantic_ranking(query, pool, tag, kind, chosen_backend)

    if chosen_mode == "hybrid":
        hits = fuse_rankings(rankings)
    else:
        ranked = rankings[chosen_mode]
        hits = [
            FindHit(entry=entry, score=source.score, sources={chosen_mode: source})
            for entry, source in ranked
        ]

    suggestions: list[str] = []
    if suggest:
        exact_hits = rankings.get("fts")
        if exact_hits is None:
            exact_hits = _fts_ranking(query, 1, tag, kind)
        if not exact_hits:
            suggestions = suggest_queries(query, index=fuzzy_index)

    return FindResult(
        query=query,
        mode=chosen_mode,
        hits=hits[:limit],
        suggestions=suggestions,
        backend_key=chosen_backend.key if chosen_backend is not None else None,
    )
