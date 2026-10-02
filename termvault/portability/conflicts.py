"""Conflict matching + policy resolution for imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from termvault.models import Entry
from termvault.portability.checksums import entry_content_hash, normalize_for_hash, hash_text
from termvault.portability.constants import (
    CONFLICT_POLICIES,
    DEFAULT_CONFLICT_POLICY,
    DEFAULT_MATCH_STRATEGY,
    MATCH_STRATEGIES,
)
from termvault.portability.errors import ConflictFailError, ImportValidationError
from termvault.portability.schema import ExportEntry


class ConflictAction(str, Enum):
    CREATE = "create"
    SKIP = "skip"
    OVERWRITE = "overwrite"
    FAIL = "fail"


@dataclass(frozen=True)
class ConflictMatch:
    existing: Entry
    strategy: str
    key: str


def normalize_conflict_policy(policy: str | None) -> str:
    value = (policy or DEFAULT_CONFLICT_POLICY).strip().lower()
    if value not in CONFLICT_POLICIES:
        raise ImportValidationError(
            f"Invalid conflict policy {policy!r}; choose: {', '.join(CONFLICT_POLICIES)}"
        )
    return value


def normalize_match_strategy(strategy: str | None) -> str:
    value = (strategy or DEFAULT_MATCH_STRATEGY).strip().lower()
    if value not in MATCH_STRATEGIES:
        raise ImportValidationError(
            f"Invalid match strategy {strategy!r}; choose: {', '.join(MATCH_STRATEGIES)}"
        )
    return value


def match_key(entry: ExportEntry | Entry, strategy: str) -> str:
    strategy = normalize_match_strategy(strategy)
    if isinstance(entry, Entry):
        title = entry.title
        kind = entry.kind
        tags = entry.tags
        body = entry.body
    else:
        title = entry.title
        kind = entry.kind
        tags = entry.tags
        body = entry.body

    if strategy == "title":
        return title.strip().lower()
    if strategy == "title+kind":
        return f"{title.strip().lower()}::{kind}"
    # hash
    return hash_text(
        normalize_for_hash(title=title, body=body, tags=tags, kind=kind)
    )


def build_conflict_index(
    vault_entries: list[Entry],
    *,
    strategy: str,
) -> dict[str, Entry]:
    """Map match-key → existing vault entry (first wins)."""
    strategy = normalize_match_strategy(strategy)
    index: dict[str, Entry] = {}
    for entry in vault_entries:
        if entry.is_trashed:
            continue
        key = match_key(entry, strategy)
        index.setdefault(key, entry)
    return index


def resolve_action(
    incoming: ExportEntry,
    *,
    index: dict[str, Entry],
    strategy: str,
    policy: str,
) -> tuple[ConflictAction, ConflictMatch | None]:
    """Decide create/skip/overwrite/fail for one incoming entry."""
    policy = normalize_conflict_policy(policy)
    strategy = normalize_match_strategy(strategy)
    key = match_key(incoming, strategy)
    existing = index.get(key)
    if existing is None:
        return ConflictAction.CREATE, None

    match = ConflictMatch(existing=existing, strategy=strategy, key=key)
    if policy == "skip":
        return ConflictAction.SKIP, match
    if policy == "overwrite":
        return ConflictAction.OVERWRITE, match
    if policy == "create":
        return ConflictAction.CREATE, match
    # fail
    raise ConflictFailError(incoming.title, existing.id)


def same_content(incoming: ExportEntry, existing: Entry) -> bool:
    left = entry_content_hash(incoming)
    right = hash_text(
        normalize_for_hash(
            title=existing.title,
            body=existing.body,
            tags=existing.tags,
            kind=existing.kind,
        )
    )
    return left == right
