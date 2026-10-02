"""Typo-tolerant search over titles, tags, and bodies.

Similarity is computed against the vault's *unique* vocabulary, then mapped
back to entries, so cost grows with distinct words rather than entry count.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from termvault.intelligence.constants import (
    FIELD_WEIGHTS,
    FUZZY_MIN_SCORE,
    PREFIX_MIN_LENGTH,
)
from termvault.intelligence.text import tokenize, unique_tokens
from termvault.models import Entry


def osa_distance(left: str, right: str, max_distance: int | None = None) -> int:
    """Optimal string alignment distance (Levenshtein + adjacent transpositions).

    Returns ``max_distance + 1`` as soon as the result is known to exceed it.
    """
    if left == right:
        return 0
    limit = max_distance if max_distance is not None else max(len(left), len(right))
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    if not left or not right:
        return max(len(left), len(right))

    previous_previous: list[int] = []
    previous = list(range(len(right) + 1))
    for i in range(1, len(left) + 1):
        current = [i] + [0] * len(right)
        row_min = current[0]
        for j in range(1, len(right) + 1):
            cost = 0 if left[i - 1] == right[j - 1] else 1
            value = min(
                previous[j] + 1,
                current[j - 1] + 1,
                previous[j - 1] + cost,
            )
            if (
                i > 1
                and j > 1
                and left[i - 1] == right[j - 2]
                and left[i - 2] == right[j - 1]
            ):
                value = min(value, previous_previous[j - 2] + 1)
            current[j] = value
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous_previous, previous = previous, current
    return previous[-1]


def max_edits_for(token: str) -> int:
    """How many typos to tolerate: none for tiny words, more for long ones."""
    length = len(token)
    if length <= 3:
        return 0
    if length <= 5:
        return 1
    if length <= 9:
        return 2
    return 3


def token_similarity(query: str, candidate: str) -> float:
    """0..1 similarity between a query token and a vocabulary token."""
    if query == candidate:
        return 1.0
    if len(query) >= PREFIX_MIN_LENGTH and candidate.startswith(query):
        return 0.8 + 0.15 * (len(query) / len(candidate))
    allowed = max_edits_for(query)
    if allowed == 0:
        return 0.0
    distance = osa_distance(query, candidate, allowed)
    if distance > allowed:
        return 0.0
    return max(0.0, 1.0 - distance / max(len(query), len(candidate))) * 0.9


@dataclass(frozen=True)
class FuzzyMatch:
    query_token: str
    matched_token: str
    field: str
    similarity: float


@dataclass
class FuzzyHit:
    entry: Entry
    score: float
    matches: list[FuzzyMatch] = field(default_factory=list)

    @property
    def corrections(self) -> list[tuple[str, str]]:
        return [
            (match.query_token, match.matched_token)
            for match in self.matches
            if match.query_token != match.matched_token
        ]


class FuzzyIndex:
    """In-memory vocabulary → (entry, field) postings for a set of entries."""

    def __init__(self, entries: list[Entry]) -> None:
        self.entries: dict[int, Entry] = {entry.id: entry for entry in entries}
        self.postings: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
        self.frequency: dict[str, int] = defaultdict(int)
        for entry in entries:
            self._add(entry)

    def _add(self, entry: Entry) -> None:
        fields = {
            "title": unique_tokens(entry.title),
            "tags": unique_tokens(" ".join(entry.tags)),
            "body": unique_tokens(entry.body),
        }
        for field_name, tokens in fields.items():
            for token in tokens:
                self.postings[token][entry.id].add(field_name)
                self.frequency[token] += 1

    @property
    def vocabulary(self) -> list[str]:
        return list(self.postings)

    def similar_tokens(self, query_token: str) -> list[tuple[str, float]]:
        """Vocabulary tokens similar enough to a query token, best first."""
        allowed = max_edits_for(query_token)
        results: list[tuple[str, float]] = []
        for candidate in self.postings:
            length_gap = len(candidate) - len(query_token)
            if length_gap < -allowed:
                continue
            if length_gap > allowed and not candidate.startswith(query_token):
                continue
            similarity = token_similarity(query_token, candidate)
            if similarity > 0:
                results.append((candidate, similarity))
        results.sort(key=lambda item: (-item[1], -self.frequency[item[0]], item[0]))
        return results

    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        min_score: float = FUZZY_MIN_SCORE,
    ) -> list[FuzzyHit]:
        query_tokens = list(dict.fromkeys(tokenize(query)))
        if not query_tokens or not self.entries:
            return []
        best_weight = max(FIELD_WEIGHTS.values())

        # entry_id -> query_token -> best FuzzyMatch (weighted)
        per_entry: dict[int, dict[str, tuple[float, FuzzyMatch]]] = defaultdict(dict)
        for query_token in query_tokens:
            for candidate, similarity in self.similar_tokens(query_token):
                for entry_id, fields in self.postings[candidate].items():
                    for field_name in fields:
                        weighted = similarity * FIELD_WEIGHTS[field_name]
                        current = per_entry[entry_id].get(query_token)
                        if current is None or weighted > current[0]:
                            per_entry[entry_id][query_token] = (
                                weighted,
                                FuzzyMatch(query_token, candidate, field_name, similarity),
                            )

        hits: list[FuzzyHit] = []
        for entry_id, matched in per_entry.items():
            total = sum(weighted for weighted, _ in matched.values())
            coverage = len(matched) / len(query_tokens)
            score = (total / (best_weight * len(query_tokens))) * (0.5 + 0.5 * coverage)
            if score < min_score:
                continue
            hits.append(
                FuzzyHit(
                    entry=self.entries[entry_id],
                    score=round(score, 4),
                    matches=[match for _, match in matched.values()],
                )
            )
        hits.sort(key=lambda hit: (-hit.score, not hit.entry.pinned, hit.entry.id))
        return hits[:limit]


def fuzzy_search(
    entries: list[Entry],
    query: str,
    *,
    limit: int = 10,
    min_score: float = FUZZY_MIN_SCORE,
) -> list[FuzzyHit]:
    return FuzzyIndex(entries).search(query, limit=limit, min_score=min_score)
