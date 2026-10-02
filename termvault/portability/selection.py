"""Select vault entries for export according to filters."""

from __future__ import annotations

from termvault import storage
from termvault.errors import TermVaultError
from termvault.models import Entry
from termvault.portability.checksums import entry_content_hash
from termvault.portability.errors import ExportError
from termvault.portability.filters import ExportFilters
from termvault.portability.schema import ExportEntry, ExportManifest


# Large enough for typical personal vaults; hard-capped for safety.
_EXPORT_FETCH_CAP = 100_000


def select_vault_entries(filters: ExportFilters) -> list[Entry]:
    """Load vault entries matching export filters."""
    filters.validate()
    try:
        if filters.ids:
            entries: list[Entry] = []
            for entry_id in filters.ids:
                try:
                    entries.append(
                        storage.get_entry(entry_id, include_trashed=True)
                    )
                except TermVaultError as exc:
                    raise ExportError(str(exc)) from exc
            return _apply_local_filters(entries, filters)

        if filters.query:
            hits = storage.search_entries(
                filters.query,
                limit=filters.limit or _EXPORT_FETCH_CAP,
                tag=filters.tag,
                kind=filters.kind,
            )
            entries = [hit.entry for hit in hits]
            return _apply_local_filters(entries, filters)

        limit = filters.limit or _EXPORT_FETCH_CAP
        entries = storage.list_entries(
            limit=limit,
            tag=filters.tag,
            kind=filters.kind,
            sort=filters.sort,
            pinned_only=filters.pinned_only,
            include_trashed=filters.include_trashed and not filters.trashed_only,
            trashed_only=filters.trashed_only,
        )
        return entries
    except TermVaultError as exc:
        raise ExportError(str(exc)) from exc


def _apply_local_filters(entries: list[Entry], filters: ExportFilters) -> list[Entry]:
    result = list(entries)
    if filters.trashed_only:
        result = [e for e in result if e.is_trashed]
    elif not filters.include_trashed:
        result = [e for e in result if not e.is_trashed]
    if filters.pinned_only:
        result = [e for e in result if e.pinned]
    if filters.kind:
        result = [e for e in result if e.kind == filters.kind]
    if filters.tag:
        needle = filters.tag.strip().lower()
        result = [e for e in result if needle in e.tags]
    if filters.limit is not None:
        result = result[: filters.limit]
    return result


def entries_to_export_entries(entries: list[Entry]) -> list[ExportEntry]:
    export_entries: list[ExportEntry] = []
    for entry in entries:
        draft = ExportEntry.from_vault_entry(entry)
        hashed = ExportEntry(
            title=draft.title,
            body=draft.body,
            tags=draft.tags,
            kind=draft.kind,
            pinned=draft.pinned,
            trashed=draft.trashed,
            created_at=draft.created_at,
            updated_at=draft.updated_at,
            source_id=draft.source_id,
            content_hash=entry_content_hash(draft),
        )
        export_entries.append(hashed)
    return export_entries


def build_manifest(
    export_entries: list[ExportEntry],
    *,
    filters: ExportFilters,
    aggregate_hash: str,
) -> ExportManifest:
    kind_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    active = 0
    trashed = 0
    pinned = 0
    for entry in export_entries:
        kind_counts[entry.kind] = kind_counts.get(entry.kind, 0) + 1
        if entry.trashed:
            trashed += 1
        else:
            active += 1
        if entry.pinned:
            pinned += 1
        for tag in entry.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return ExportManifest(
        entry_count=len(export_entries),
        active_count=active,
        trashed_count=trashed,
        pinned_count=pinned,
        kind_counts=dict(sorted(kind_counts.items())),
        tag_counts=dict(sorted(tag_counts.items())),
        content_hash=aggregate_hash,
        filters=filters.to_dict(),
    )
