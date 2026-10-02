"""Help text and key reference for Phase 5 Part 2."""

from __future__ import annotations

HELP_TEXT = """
TermVault TUI — Phase 5 Part 2 keyboard reference

══════════════════════════════════════════════════════════════
 Navigation
══════════════════════════════════════════════════════════════
  j / ↓          Move down in the entry list
  k / ↑          Move up in the entry list
  g              Jump to top of list
  G              Jump to bottom of list
  l              Focus entry list
  b              Focus tag sidebar
  Tab            Cycle focus between panes
  /              Focus search
  Esc            Clear search (when focused) / return focus to list

══════════════════════════════════════════════════════════════
 Browsing & filters
══════════════════════════════════════════════════════════════
  r              Refresh entries + sidebar tags
  o              Cycle sort: updated → created → title
  K              Cycle kind filter (all → note → snippet → …)
  t              Toggle trash view (active ↔ trashed)
  P              Toggle pinned-only filter
  #              Clear advanced filters (+ search)
  Enter on tag   Filter list to that sidebar tag
  All tags       Clear the tag filter

══════════════════════════════════════════════════════════════
 Overlays
══════════════════════════════════════════════════════════════
  ?              Help (this screen)
  s              Vault stats overlay
  : / Ctrl+P     Command palette (filterable action launcher)

══════════════════════════════════════════════════════════════
 Entry actions
══════════════════════════════════════════════════════════════
  n              New entry (validation + draft autosave)
  e              Edit selected (blocked while in trash)
  p              Pin / unpin
  d              Trash (or permanent delete in trash view)
  u              Restore from trash
  y              Copy body to clipboard (falls back to title)
  q              Quit

══════════════════════════════════════════════════════════════
 Command palette tips
══════════════════════════════════════════════════════════════
  Type fragments of a command title, id, or keyword.
  Multi-word needles require every token to match.
  Palette also exposes copy-title and copy-meta.

══════════════════════════════════════════════════════════════
 Notes
══════════════════════════════════════════════════════════════
  Part 1 still owns drafts, validation, and core list/detail.
  CLI remains the stable API underneath the TUI.
  Soft-deleted entries are recoverable via `tv restore <id>`.
""".strip()


HELP_SECTIONS: tuple[tuple[str, str], ...] = (
    (
        "Navigation",
        "j/k move · g/G top/bottom · / search · l list · b tags · Esc clear",
    ),
    (
        "Filters",
        "o sort · K kind · t trash view · P pinned · # clear · sidebar tags",
    ),
    (
        "Overlays",
        "? help · s stats · : / Ctrl+P command palette",
    ),
    (
        "Entries",
        "n new · e edit · p pin · d trash/delete · u restore · y copy · q quit",
    ),
)


STATUS_HINTS_PART2 = (
    "[b]?[/b] help  [b]:[/b] palette  [b]t[/b] trash  [b]o[/b] sort  "
    "[b]K[/b] kind  [b]u[/b] restore  [b]y[/b] copy  [b]j/k[/b] move"
)


def format_help_sections() -> str:
    """Compact multi-section help used by tests and alternate overlays."""
    lines: list[str] = ["TermVault TUI — quick reference", ""]
    for title, body in HELP_SECTIONS:
        lines.append(f"{title}")
        lines.append(f"  {body}")
        lines.append("")
    return "\n".join(lines).rstrip()


def binding_cheat_sheet() -> dict[str, str]:
    """Machine-readable key → action map for docs / tests."""
    return {
        "j": "cursor_down",
        "k": "cursor_up",
        "g": "cursor_top",
        "G": "cursor_bottom",
        "/": "focus_search",
        "l": "focus_list",
        "b": "focus_sidebar",
        "r": "refresh",
        "o": "cycle_sort",
        "K": "cycle_kind",
        "t": "toggle_trash",
        "P": "toggle_pinned_only",
        "#": "clear_filters",
        "?": "help",
        "s": "show_stats",
        ":": "command_palette",
        "n": "new_entry",
        "e": "edit_entry",
        "p": "toggle_pin",
        "d": "trash_or_delete",
        "u": "restore_entry",
        "y": "copy_body",
        "q": "quit",
    }
