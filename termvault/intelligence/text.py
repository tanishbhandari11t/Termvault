"""Tokenizing, light stemming, and n-grams shared by fuzzy and semantic search."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator

_TOKEN_RE = re.compile(r"[a-z0-9]+")

STOPWORDS: frozenset[str] = frozenset(
    """
    a an and are as at be but by for from has have i if in into is it its of on or
    so than that the then there these this to was were will with you your we our
    not no do does did can could should would how what when where which who why
    """.split()
)

# Longest suffix first; each maps to its replacement.
_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("ations", "ate"),
    ("ation", "ate"),
    ("ingly", ""),
    ("ies", "y"),
    ("ing", ""),
    ("edly", ""),
    ("ed", ""),
    ("es", ""),
    ("s", ""),
)


def fold(text: str) -> str:
    """Lowercase and strip accents so 'Café' matches 'cafe'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def stem(token: str) -> str:
    """Very light suffix stripping; keeps at least three characters."""
    if len(token) <= 4 or token.isdigit():
        return token
    for suffix, replacement in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            if suffix == "s" and token.endswith("ss"):
                return token
            return token[: -len(suffix)] + replacement
    return token


def tokenize(
    text: str,
    *,
    stemmed: bool = False,
    drop_stopwords: bool = False,
) -> list[str]:
    tokens = _TOKEN_RE.findall(fold(text))
    if drop_stopwords:
        tokens = [token for token in tokens if token not in STOPWORDS]
    if stemmed:
        tokens = [stem(token) for token in tokens]
    return tokens


def unique_tokens(text: str) -> list[str]:
    """Tokens in first-seen order without duplicates."""
    seen: set[str] = set()
    ordered: list[str] = []
    for token in tokenize(text):
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def char_ngrams(token: str, n: int = 3) -> Iterator[str]:
    """Boundary-marked character n-grams: 'git' -> '^gi', 'git', 'it$'."""
    padded = f"^{token}$"
    if len(padded) <= n:
        yield padded
        return
    for index in range(len(padded) - n + 1):
        yield padded[index : index + n]


def word_bigrams(tokens: list[str]) -> Iterator[str]:
    for left, right in zip(tokens, tokens[1:]):
        yield f"{left}_{right}"
