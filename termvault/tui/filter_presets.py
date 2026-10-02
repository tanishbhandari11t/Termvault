"""Named filter presets for Phase 5 Part 2.

Presets are small recipes over AdvancedFilters so the palette (and future
bookmarking) can jump to common views without re-cycling keys.
"""

from __future__ import annotations

from dataclasses import dataclass

from termvault.tui.filters import AdvancedFilters


@dataclass(frozen=True)
class FilterPreset:
    id: str
    title: str
    description: str
    trash_mode: bool = False
    pinned_only: bool = False
    kind: str | None = None
    sort: str = "updated"

    def apply_to(self, filters: AdvancedFilters) -> AdvancedFilters:
        filters.clear()
        filters.trash_mode = self.trash_mode
        filters.pinned_only = self.pinned_only
        filters.kind = self.kind
        filters.sort = self.sort
        return filters

    def as_filters(self) -> AdvancedFilters:
        return self.apply_to(AdvancedFilters())


FILTER_PRESETS: tuple[FilterPreset, ...] = (
    FilterPreset(
        "active-updated",
        "Active · updated",
        "Default view: active entries sorted by updated",
    ),
    FilterPreset(
        "pinned",
        "Pinned only",
        "Only pinned active entries",
        pinned_only=True,
    ),
    FilterPreset(
        "trash",
        "Trash",
        "Soft-deleted entries",
        trash_mode=True,
    ),
    FilterPreset(
        "errors",
        "Errors",
        "Active entries with kind=error",
        kind="error",
    ),
    FilterPreset(
        "commands",
        "Commands",
        "Active entries with kind=command",
        kind="command",
    ),
    FilterPreset(
        "snippets-title",
        "Snippets A→Z",
        "Snippet entries sorted by title",
        kind="snippet",
        sort="title",
    ),
    FilterPreset(
        "newest",
        "Newest created",
        "Active entries sorted by created",
        sort="created",
    ),
)


def get_filter_preset(preset_id: str) -> FilterPreset | None:
    for preset in FILTER_PRESETS:
        if preset.id == preset_id:
            return preset
    return None


def list_filter_preset_ids() -> tuple[str, ...]:
    return tuple(preset.id for preset in FILTER_PRESETS)


def apply_filter_preset(filters: AdvancedFilters, preset_id: str) -> bool:
    preset = get_filter_preset(preset_id)
    if preset is None:
        return False
    preset.apply_to(filters)
    return True
