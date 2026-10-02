"""Phase 7 search intelligence: fuzzy matching, local embeddings, hybrid ranking."""

from __future__ import annotations

from termvault.intelligence.embeddings import HashingBackend, get_backend
from termvault.intelligence.errors import BackendUnavailableError, IntelligenceError
from termvault.intelligence.fuzzy import FuzzyIndex, fuzzy_search, osa_distance
from termvault.intelligence.hybrid import FindHit, FindResult, find_entries, fuse_rankings
from termvault.intelligence.index import (
    build_index,
    clear_index,
    index_status,
    related_entries,
    semantic_search,
)
from termvault.intelligence.suggest import suggest_queries

__all__ = [
    "BackendUnavailableError",
    "FindHit",
    "FindResult",
    "FuzzyIndex",
    "HashingBackend",
    "IntelligenceError",
    "build_index",
    "clear_index",
    "find_entries",
    "fuse_rankings",
    "fuzzy_search",
    "get_backend",
    "index_status",
    "osa_distance",
    "related_entries",
    "semantic_search",
    "suggest_queries",
]
