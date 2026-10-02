"""Domain models for TermVault entries and organization metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Entry:
    """A single knowledge entry stored in the local vault."""

    id: int
    title: str
    body: str
    tags: tuple[str, ...]
    created_at: str
    updated_at: str
    kind: str = "note"
    pinned: bool = False
    trashed_at: str | None = None

    def tags_display(self) -> str:
        """Return a human-readable tag string."""
        return ", ".join(self.tags) if self.tags else "-"

    @property
    def is_trashed(self) -> bool:
        return self.trashed_at is not None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entry for JSON output."""
        return {
            "id": self.id,
            "title": self.title,
            "body": self.body,
            "tags": list(self.tags),
            "kind": self.kind,
            "pinned": self.pinned,
            "trashed_at": self.trashed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class SearchHit:
    """One ranked search result with an optional snippet."""

    entry: Entry
    rank: float
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        payload = self.entry.to_dict()
        payload["rank"] = self.rank
        payload["snippet"] = self.snippet
        return payload


@dataclass(frozen=True)
class TagCount:
    """A tag and how many active entries use it."""

    name: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "count": self.count}


@dataclass(frozen=True)
class VaultStats:
    """Aggregate vault organization metrics."""

    total_entries: int
    active_entries: int
    trashed_entries: int
    pinned_entries: int
    tag_count: int
    kind_counts: dict[str, int]
    top_tags: tuple[TagCount, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_entries": self.total_entries,
            "active_entries": self.active_entries,
            "trashed_entries": self.trashed_entries,
            "pinned_entries": self.pinned_entries,
            "tag_count": self.tag_count,
            "kind_counts": self.kind_counts,
            "top_tags": [tag.to_dict() for tag in self.top_tags],
        }
