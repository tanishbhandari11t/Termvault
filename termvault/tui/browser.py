"""Entry loading + selection helpers for Phase 5 Part 1."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from termvault import storage
from termvault.config import load_settings
from termvault.errors import TermVaultError
from termvault.models import Entry
from termvault.tui.constants import DEFAULT_LIST_LIMIT, MAX_RECENT_OPENED


@dataclass
class BrowseSession:
    """In-memory session state for the Part 1 browser."""

    query: str = ""
    selected_id: int | None = None
    entries: list[Entry] = field(default_factory=list)
    recent_opened: deque[int] = field(default_factory=deque)
    last_error: str | None = None

    def __post_init__(self) -> None:
        self.recent_opened = deque(self.recent_opened, maxlen=MAX_RECENT_OPENED)

    def remember_opened(self, entry_id: int) -> None:
        ids = [item for item in self.recent_opened if item != entry_id]
        self.recent_opened = deque([entry_id, *ids], maxlen=MAX_RECENT_OPENED)


def resolve_list_limit() -> int:
    """Prefer user config list limit, but keep a sane TUI maximum floor."""
    settings = load_settings()
    return max(settings.default_list_limit, DEFAULT_LIST_LIMIT)


def load_active_entries(*, query: str = "", limit: int | None = None) -> list[Entry]:
    """Return active entries, optionally filtered by full-text search."""
    cleaned = query.strip()
    resolved_limit = resolve_list_limit() if limit is None else limit
    if cleaned:
        hits = storage.search_entries(cleaned, limit=resolved_limit)
        return [hit.entry for hit in hits]
    return storage.list_entries(limit=resolved_limit, sort="updated")


def safe_load_active_entries(*, query: str = "", limit: int | None = None) -> tuple[list[Entry], str | None]:
    """Like ``load_active_entries`` but captures expected vault errors."""
    try:
        return load_active_entries(query=query, limit=limit), None
    except TermVaultError as exc:
        return [], str(exc)


def format_status_count(count: int) -> str:
    """Human-friendly status line for the entry list size."""
    if count == 0:
        return "No matching entries."
    noun = "entry" if count == 1 else "entries"
    return f"{count} {noun}"


def next_index_after_reload(
    entries: list[Entry],
    selected_id: int | None,
) -> int:
    """Keep selection stable across reloads when possible."""
    if not entries:
        return 0
    if selected_id is None:
        return 0
    for index, entry in enumerate(entries):
        if entry.id == selected_id:
            return index
    return 0


def find_entry(entries: list[Entry], entry_id: int | None) -> Entry | None:
    if entry_id is None:
        return None
    for entry in entries:
        if entry.id == entry_id:
            return entry
    return None
