"""Phase 5 Part 2 browse filters (tag / kind / sort / trash / pinned)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

from termvault.config import VALID_KINDS, VALID_SORTS


@dataclass
class AdvancedFilters:
    """Power-user filter state layered on top of Part 1 search."""

    tag: str | None = None
    kind: str | None = None
    sort: str = "updated"
    trash_mode: bool = False
    pinned_only: bool = False

    def cycle_sort(self) -> str:
        order = list(VALID_SORTS)
        idx = order.index(self.sort) if self.sort in order else 0
        self.sort = order[(idx + 1) % len(order)]
        return self.sort

    def cycle_kind(self) -> str | None:
        options: list[str | None] = [None, *VALID_KINDS]
        try:
            idx = options.index(self.kind)
        except ValueError:
            idx = 0
        self.kind = options[(idx + 1) % len(options)]
        return self.kind

    def set_tag(self, tag: str | None) -> str | None:
        cleaned = tag.strip().lower() if tag else None
        self.tag = cleaned or None
        return self.tag

    def toggle_tag(self, tag: str) -> str | None:
        """Select tag if different; clear if the same tag is chosen again."""
        normalized = tag.strip().lower()
        if self.tag == normalized:
            self.tag = None
        else:
            self.tag = normalized
        return self.tag

    def toggle_trash(self) -> bool:
        self.trash_mode = not self.trash_mode
        return self.trash_mode

    def toggle_pinned_only(self) -> bool:
        self.pinned_only = not self.pinned_only
        return self.pinned_only

    def clear(self) -> None:
        self.tag = None
        self.kind = None
        self.sort = "updated"
        self.trash_mode = False
        self.pinned_only = False

    def clear_soft(self) -> None:
        """Clear tag/kind/pinned/trash but keep the current sort."""
        kept_sort = self.sort
        self.clear()
        self.sort = kept_sort

    def snapshot(self) -> dict:
        return asdict(self)

    def restore(self, data: dict) -> None:
        self.tag = data.get("tag")
        self.kind = data.get("kind")
        self.sort = data.get("sort", "updated")
        self.trash_mode = bool(data.get("trash_mode", False))
        self.pinned_only = bool(data.get("pinned_only", False))

    def copy(self) -> AdvancedFilters:
        return replace(self)

    def summary(self) -> str:
        parts: list[str] = []
        if self.trash_mode:
            parts.append("trash")
        if self.pinned_only:
            parts.append("pinned")
        if self.kind:
            parts.append(f"kind={self.kind}")
        if self.tag:
            parts.append(f"tag={self.tag}")
        parts.append(f"sort={self.sort}")
        return " · ".join(parts)

    def compact_badge(self) -> str:
        """Short badge for the top-bar FilterSummary widget."""
        if not self.active_count():
            return ""
        # Avoid [] — Textual Static markup treats brackets as tags.
        return f"({self.summary()})"

    def active_count(self) -> int:
        count = 0
        if self.trash_mode:
            count += 1
        if self.pinned_only:
            count += 1
        if self.kind:
            count += 1
        if self.tag:
            count += 1
        if self.sort != "updated":
            count += 1
        return count

    def describe(self) -> str:
        """Longer human description for help / palette status."""
        if not self.active_count():
            return "No advanced filters (sort=updated)."
        return f"Active filters ({self.active_count()}): {self.summary()}"

    def applies_to_search(self) -> bool:
        """Whether list should prefer FTS search over plain list_entries."""
        return not self.trash_mode


def filters_from_kwargs(
    *,
    tag: str | None = None,
    kind: str | None = None,
    sort: str = "updated",
    trash_mode: bool = False,
    pinned_only: bool = False,
) -> AdvancedFilters:
    """Factory used by tests and future deep-link / preset loaders."""
    if sort not in VALID_SORTS:
        sort = "updated"
    if kind is not None and kind not in VALID_KINDS:
        kind = None
    return AdvancedFilters(
        tag=tag.lower() if tag else None,
        kind=kind,
        sort=sort,
        trash_mode=trash_mode,
        pinned_only=pinned_only,
    )
