"""'Did you mean …?' query corrections built from the vault's own words."""

from __future__ import annotations

from termvault.intelligence.constants import MAX_SUGGESTIONS
from termvault.intelligence.fuzzy import FuzzyIndex, max_edits_for, osa_distance
from termvault.intelligence.text import tokenize
from termvault.models import Entry


def closest_words(
    token: str,
    frequency: dict[str, int],
    *,
    limit: int = MAX_SUGGESTIONS,
) -> list[str]:
    """Vocabulary words within the typo budget, closest then most common first."""
    allowed = max_edits_for(token)
    if allowed == 0:
        return []
    scored: list[tuple[int, int, str]] = []
    for word, count in frequency.items():
        if word == token or abs(len(word) - len(token)) > allowed:
            continue
        distance = osa_distance(token, word, allowed)
        if distance <= allowed:
            scored.append((distance, -count, word))
    scored.sort()
    return [word for _, _, word in scored[:limit]]


def suggest_queries(
    query: str,
    entries: list[Entry] | None = None,
    *,
    index: FuzzyIndex | None = None,
    limit: int = MAX_SUGGESTIONS,
) -> list[str]:
    """Alternative spellings of the whole query, using words that exist in the vault."""
    if index is None:
        index = FuzzyIndex(entries or [])
    frequency = dict(index.frequency)
    tokens = tokenize(query)
    if not tokens or not frequency:
        return []

    options: list[list[str]] = []
    changed = False
    for token in tokens:
        if token in frequency:
            options.append([token])
            continue
        candidates = closest_words(token, frequency, limit=limit)
        if candidates:
            changed = True
            options.append(candidates)
        else:
            options.append([token])
    if not changed:
        return []

    suggestions: list[str] = []
    # Vary one position at a time around the best overall guess.
    best = [choices[0] for choices in options]
    suggestions.append(" ".join(best))
    for position, choices in enumerate(options):
        for alternative in choices[1:]:
            variant = list(best)
            variant[position] = alternative
            suggestions.append(" ".join(variant))
    unique = list(dict.fromkeys(s for s in suggestions if s != " ".join(tokens)))
    return unique[:limit]
