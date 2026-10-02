"""Command palette definitions for Phase 5 Part 2.

The palette is a filterable launcher over the same actions the keybindings
expose. Keeping the catalog declarative makes it easy to grow without
touching Textual screen code.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PaletteCategory(str, Enum):
    NAVIGATION = "navigation"
    FILTERS = "filters"
    ENTRY = "entry"
    OVERLAYS = "overlays"
    SESSION = "session"


@dataclass(frozen=True)
class PaletteCommand:
    """One command-palette entry."""

    id: str
    title: str
    description: str
    keywords: tuple[str, ...] = ()
    category: PaletteCategory = PaletteCategory.SESSION
    shortcut: str | None = None

    def matches(self, needle: str) -> bool:
        if not needle:
            return True
        tokens = [t for t in needle.lower().split() if t]
        if not tokens:
            return True
        hay = " ".join(
            (
                self.id,
                self.title,
                self.description,
                self.category.value,
                self.shortcut or "",
                " ".join(self.keywords),
            )
        ).lower()
        return all(token in hay for token in tokens)

    def score(self, needle: str) -> int:
        """Lower is better. Used to rank filtered palette results."""
        if not needle:
            return 0
        n = needle.lower().strip()
        if self.id == n:
            return -100
        if self.title.lower().startswith(n):
            return -50
        if n in self.id:
            return -20
        if n in self.title.lower():
            return -10
        return 0

    def display_label(self) -> str:
        shortcut = f"  [{self.shortcut}]" if self.shortcut else ""
        return f"{self.title}{shortcut} — {self.description}"


PALETTE_COMMANDS: tuple[PaletteCommand, ...] = (
    PaletteCommand(
        "refresh",
        "Refresh",
        "Reload entries and tags",
        ("reload", "r"),
        PaletteCategory.SESSION,
        "r",
    ),
    PaletteCommand(
        "new",
        "New entry",
        "Create a vault entry",
        ("create", "add", "n"),
        PaletteCategory.ENTRY,
        "n",
    ),
    PaletteCommand(
        "edit",
        "Edit entry",
        "Edit the selected entry",
        ("update", "e"),
        PaletteCategory.ENTRY,
        "e",
    ),
    PaletteCommand(
        "pin",
        "Toggle pin",
        "Pin or unpin the selected entry",
        ("star", "p"),
        PaletteCategory.ENTRY,
        "p",
    ),
    PaletteCommand(
        "trash",
        "Trash / delete",
        "Trash active entry or permanently delete in trash view",
        ("delete", "d"),
        PaletteCategory.ENTRY,
        "d",
    ),
    PaletteCommand(
        "restore",
        "Restore",
        "Restore selected entry from trash",
        ("undelete", "u"),
        PaletteCategory.ENTRY,
        "u",
    ),
    PaletteCommand(
        "copy",
        "Copy body",
        "Copy selected entry body to clipboard",
        ("yank", "y"),
        PaletteCategory.ENTRY,
        "y",
    ),
    PaletteCommand(
        "copy-title",
        "Copy title",
        "Copy selected entry title to clipboard",
        ("yank title",),
        PaletteCategory.ENTRY,
        None,
    ),
    PaletteCommand(
        "copy-meta",
        "Copy metadata",
        "Copy id/title/kind/tags block to clipboard",
        ("yank meta", "meta"),
        PaletteCategory.ENTRY,
        None,
    ),
    PaletteCommand(
        "toggle-trash-view",
        "Toggle trash view",
        "Switch between active and trashed entries",
        ("trash view", "t"),
        PaletteCategory.FILTERS,
        "t",
    ),
    PaletteCommand(
        "toggle-pinned-only",
        "Pinned only",
        "Show only pinned entries",
        ("filter pin",),
        PaletteCategory.FILTERS,
        "P",
    ),
    PaletteCommand(
        "cycle-sort",
        "Cycle sort",
        "updated → created → title",
        ("sort", "o"),
        PaletteCategory.FILTERS,
        "o",
    ),
    PaletteCommand(
        "cycle-kind",
        "Cycle kind",
        "Filter by entry kind",
        ("kind", "K"),
        PaletteCategory.FILTERS,
        "K",
    ),
    PaletteCommand(
        "clear-filters",
        "Clear filters",
        "Reset tag/kind/trash/pinned/sort filters",
        ("reset", "#"),
        PaletteCategory.FILTERS,
        "#",
    ),
    PaletteCommand(
        "stats",
        "Vault stats",
        "Show organization statistics",
        ("metrics", "s"),
        PaletteCategory.OVERLAYS,
        "s",
    ),
    PaletteCommand(
        "help",
        "Help",
        "Show keyboard reference",
        ("keys", "?"),
        PaletteCategory.OVERLAYS,
        "?",
    ),
    PaletteCommand(
        "focus-search",
        "Focus search",
        "Jump to the search box",
        ("/", "find"),
        PaletteCategory.NAVIGATION,
        "/",
    ),
    PaletteCommand(
        "focus-list",
        "Focus list",
        "Jump to the entry list",
        ("list",),
        PaletteCategory.NAVIGATION,
        "l",
    ),
    PaletteCommand(
        "focus-sidebar",
        "Focus tags",
        "Jump to the tag sidebar",
        ("tags", "b"),
        PaletteCategory.NAVIGATION,
        "b",
    ),
    PaletteCommand(
        "quit",
        "Quit",
        "Exit the TUI",
        ("exit", "q"),
        PaletteCategory.SESSION,
        "q",
    ),
)


def filter_palette_commands(needle: str) -> list[PaletteCommand]:
    """Return palette commands matching a free-text needle, ranked."""
    matched = [cmd for cmd in PALETTE_COMMANDS if cmd.matches(needle)]
    matched.sort(key=lambda cmd: (cmd.score(needle), cmd.title.lower()))
    return matched


def get_palette_command(command_id: str) -> PaletteCommand | None:
    for cmd in PALETTE_COMMANDS:
        if cmd.id == command_id:
            return cmd
    return None


def palette_commands_by_category() -> dict[PaletteCategory, list[PaletteCommand]]:
    grouped: dict[PaletteCategory, list[PaletteCommand]] = {
        category: [] for category in PaletteCategory
    }
    for cmd in PALETTE_COMMANDS:
        grouped[cmd.category].append(cmd)
    return grouped


def palette_command_ids() -> tuple[str, ...]:
    return tuple(cmd.id for cmd in PALETTE_COMMANDS)
