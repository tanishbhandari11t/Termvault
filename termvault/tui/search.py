"""Search history + debounce helpers for Phase 5 Part 1."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from termvault.tui.constants import MAX_SEARCH_HISTORY, SEARCH_DEBOUNCE_MS


@dataclass
class SearchController:
    """Track query text, debounce intent, and recent searches."""

    debounce_ms: int = SEARCH_DEBOUNCE_MS
    max_history: int = MAX_SEARCH_HISTORY
    query: str = ""
    _history: deque[str] = field(default_factory=deque)
    _pending: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self._history, deque):
            self._history = deque(self._history, maxlen=self.max_history)
        else:
            self._history = deque(self._history, maxlen=self.max_history)

    @property
    def history(self) -> tuple[str, ...]:
        return tuple(self._history)

    def set_query(self, value: str, *, commit_history: bool = False) -> str:
        """Update the active query and optionally record history."""
        cleaned = value.strip()
        self.query = cleaned
        self._pending = cleaned
        if commit_history and cleaned:
            self._remember(cleaned)
        return cleaned

    def commit_pending(self) -> str:
        """Promote the pending query into history (Enter / debounce fire)."""
        cleaned = (self._pending if self._pending is not None else self.query).strip()
        self.query = cleaned
        if cleaned:
            self._remember(cleaned)
        self._pending = None
        return cleaned

    def clear(self) -> None:
        self.query = ""
        self._pending = None

    def _remember(self, query: str) -> None:
        # Newest first; avoid immediate duplicates.
        if self._history and self._history[0] == query:
            return
        # Remove older duplicate then insert at front.
        existing = [item for item in self._history if item != query]
        self._history = deque([query, *existing], maxlen=self.max_history)
