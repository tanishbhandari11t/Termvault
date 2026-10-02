"""Phase 5 Part 2 data loading for filtered views, tags, and stats."""

from __future__ import annotations

from dataclasses import dataclass

from termvault import storage
from termvault.errors import TermVaultError
from termvault.models import Entry, TagCount, VaultStats
from termvault.tui.browser import resolve_list_limit
from termvault.tui.filters import AdvancedFilters


@dataclass(frozen=True)
class FilteredLoadResult:
    """Result bundle for filtered list loads (handy for tests/status)."""

    entries: list[Entry]
    error: str | None = None
    used_search: bool = False
    trash_mode: bool = False

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def count(self) -> int:
        return len(self.entries)


def load_filtered_entries(
    *,
    query: str = "",
    filters: AdvancedFilters | None = None,
    limit: int | None = None,
) -> list[Entry]:
    """Load entries honoring Part 2 advanced filters."""
    return load_filtered_result(query=query, filters=filters, limit=limit).entries


def load_filtered_result(
    *,
    query: str = "",
    filters: AdvancedFilters | None = None,
    limit: int | None = None,
) -> FilteredLoadResult:
    """Load entries and return metadata about how the query was satisfied."""
    flt = filters or AdvancedFilters()
    resolved = resolve_list_limit() if limit is None else limit

    if flt.trash_mode:
        entries = storage.list_entries(
            limit=resolved,
            tag=flt.tag,
            kind=flt.kind,
            sort=flt.sort,
            pinned_only=flt.pinned_only,
            trashed_only=True,
        )
        return FilteredLoadResult(
            entries=entries,
            used_search=False,
            trash_mode=True,
        )

    cleaned = query.strip()
    if cleaned:
        hits = storage.search_entries(
            cleaned,
            limit=resolved,
            tag=flt.tag,
            kind=flt.kind,
        )
        entries = [hit.entry for hit in hits]
        if flt.pinned_only:
            entries = [entry for entry in entries if entry.pinned]
        entries = apply_post_search_sort(entries, flt.sort)
        return FilteredLoadResult(
            entries=entries,
            used_search=True,
            trash_mode=False,
        )

    entries = storage.list_entries(
        limit=resolved,
        tag=flt.tag,
        kind=flt.kind,
        sort=flt.sort,
        pinned_only=flt.pinned_only,
        trashed_only=False,
    )
    return FilteredLoadResult(
        entries=entries,
        used_search=False,
        trash_mode=False,
    )


def apply_post_search_sort(entries: list[Entry], sort: str) -> list[Entry]:
    """Search results are relevance-ordered; optionally re-sort locally."""
    if sort == "title":
        return sorted(entries, key=lambda e: e.title.lower())
    if sort == "created":
        return sorted(entries, key=lambda e: e.created_at, reverse=True)
    return entries


def safe_load_filtered_entries(
    *,
    query: str = "",
    filters: AdvancedFilters | None = None,
    limit: int | None = None,
) -> tuple[list[Entry], str | None]:
    try:
        result = load_filtered_result(query=query, filters=filters, limit=limit)
        return result.entries, None
    except TermVaultError as exc:
        return [], str(exc)


def safe_load_filtered_result(
    *,
    query: str = "",
    filters: AdvancedFilters | None = None,
    limit: int | None = None,
) -> FilteredLoadResult:
    try:
        return load_filtered_result(query=query, filters=filters, limit=limit)
    except TermVaultError as exc:
        return FilteredLoadResult(entries=[], error=str(exc))


def load_sidebar_tags() -> list[TagCount]:
    try:
        return storage.list_tags()
    except TermVaultError:
        return []


def load_vault_stats() -> VaultStats | None:
    try:
        return storage.vault_stats()
    except TermVaultError:
        return None


def restore_entry(entry_id: int) -> Entry:
    return storage.restore_entry(entry_id)


def permanently_delete_entry(entry_id: int) -> Entry:
    return storage.delete_entry(entry_id, permanent=True)


def format_filter_load_status(result: FilteredLoadResult, filters: AdvancedFilters) -> str:
    """Status-line fragment describing the current filtered load."""
    if result.error:
        return f"Error: {result.error}"
    mode = "trash" if result.trash_mode else ("search" if result.used_search else "list")
    base = f"{result.count} via {mode}"
    if filters.active_count():
        return f"{base} · {filters.summary()}"
    return base


def count_pinned(entries: list[Entry]) -> int:
    return sum(1 for entry in entries if entry.pinned)


def count_trashed(entries: list[Entry]) -> int:
    return sum(1 for entry in entries if entry.is_trashed)
