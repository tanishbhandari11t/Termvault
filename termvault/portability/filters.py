"""Export selection filters for Phase 6 Part 1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from termvault.config import VALID_KINDS, VALID_SORTS
from termvault.portability.errors import ExportError


@dataclass
class ExportFilters:
    """Which vault entries to include in an export."""

    tag: str | None = None
    kind: str | None = None
    pinned_only: bool = False
    include_trashed: bool = False
    trashed_only: bool = False
    sort: str = "updated"
    limit: int | None = None
    ids: tuple[int, ...] = ()
    query: str | None = None

    def validate(self) -> None:
        if self.kind is not None and self.kind not in VALID_KINDS:
            raise ExportError(f"Invalid kind filter: {self.kind!r}")
        if self.sort not in VALID_SORTS:
            raise ExportError(f"Invalid sort: {self.sort!r}")
        if self.limit is not None and self.limit < 1:
            raise ExportError("limit must be >= 1")
        if self.trashed_only and not self.include_trashed:
            # trashed_only implies include
            self.include_trashed = True
        if self.ids:
            bad = [i for i in self.ids if i < 1]
            if bad:
                raise ExportError(f"Invalid entry ids: {bad}")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["ids"] = list(self.ids)
        return {key: value for key, value in data.items() if value not in (None, (), [], False)}

    def describe(self) -> str:
        parts: list[str] = []
        if self.trashed_only:
            parts.append("trashed-only")
        elif self.include_trashed:
            parts.append("include-trashed")
        if self.pinned_only:
            parts.append("pinned")
        if self.kind:
            parts.append(f"kind={self.kind}")
        if self.tag:
            parts.append(f"tag={self.tag}")
        if self.query:
            parts.append(f"query={self.query!r}")
        if self.ids:
            parts.append(f"ids={len(self.ids)}")
        if self.limit:
            parts.append(f"limit={self.limit}")
        parts.append(f"sort={self.sort}")
        return " · ".join(parts)
