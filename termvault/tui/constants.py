"""Shared constants for Phase 5 Part 1 TUI."""

from __future__ import annotations

from typing import Final

# Search / list behavior
DEFAULT_LIST_LIMIT: Final[int] = 100
SEARCH_DEBOUNCE_MS: Final[int] = 180
MAX_SEARCH_HISTORY: Final[int] = 20
MAX_RECENT_OPENED: Final[int] = 30

# Draft autosave (new/edit modals)
DRAFT_DIRNAME: Final[str] = "tui-drafts"
DRAFT_NEW_NAME: Final[str] = "new-entry.json"
DRAFT_EDIT_PREFIX: Final[str] = "edit-"

# Form limits
MAX_TITLE_LENGTH: Final[int] = 200
MAX_TAG_LENGTH: Final[int] = 64
MAX_TAG_COUNT: Final[int] = 20
MAX_BODY_LENGTH: Final[int] = 100_000

# UI copy
EMPTY_LIST_HINT: Final[str] = (
    'No matching entries.\n\nPress n to create one, or use:\n  tv add "Title"'
)
STATUS_READY: Final[str] = "Ready.  / search · n new · e edit · p pin · d trash · r refresh · q quit"
SEARCH_PLACEHOLDER: Final[str] = (
    "Search vault…  (/ focus · Esc clear · Enter jump to list)"
)

# Keybinding ids used by the Part 1 app
PART1_BINDING_ACTIONS: Final[tuple[str, ...]] = (
    "quit",
    "refresh",
    "new_entry",
    "edit_entry",
    "toggle_pin",
    "trash_entry",
    "focus_search",
    "clear_search",
    "focus_list",
)

# Part 2 advanced chrome
PART2_BINDING_ACTIONS: Final[tuple[str, ...]] = (
    "restore_entry",
    "copy_body",
    "show_stats",
    "cycle_sort",
    "cycle_kind",
    "toggle_trash",
    "toggle_pinned_only",
    "clear_filters",
    "help",
    "command_palette",
    "focus_sidebar",
    "cursor_down",
    "cursor_up",
    "cursor_top",
    "cursor_bottom",
    "trash_or_delete",
)

SIDEBAR_WIDTH_CHARS: Final[int] = 22
PALETTE_PAGE_SIZE: Final[int] = 12
NAV_PAGE_SIZE: Final[int] = 10
FILTER_SUMMARY_EMPTY: Final[str] = ""
STATUS_READY_PART2: Final[str] = (
    "Ready.  ? help · : palette · t trash · o sort · u restore · y copy · q quit"
)
SEARCH_PLACEHOLDER_PART2: Final[str] = (
    "Search vault…  (/ focus · Esc clear · : palette · t trash view)"
)
