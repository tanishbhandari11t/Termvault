"""Load the entries that fuzzy / semantic search operate on."""

from __future__ import annotations

from termvault import storage
from termvault.intelligence.constants import CORPUS_FETCH_CAP
from termvault.models import Entry
from termvault.storage import normalize_kind
from termvault.tags import normalize_tags


def load_corpus(
    *,
    tag: str | None = None,
    kind: str | None = None,
    include_trashed: bool = False,
) -> list[Entry]:
    """Active entries (optionally filtered) in a stable order."""
    entries = storage.list_entries(
        limit=CORPUS_FETCH_CAP,
        include_trashed=include_trashed,
    )
    return filter_entries(entries, tag=tag, kind=kind)


def filter_entries(
    entries: list[Entry],
    *,
    tag: str | None = None,
    kind: str | None = None,
) -> list[Entry]:
    result = entries
    if kind is not None:
        wanted_kind = normalize_kind(kind)
        result = [entry for entry in result if entry.kind == wanted_kind]
    if tag is not None:
        wanted_tag = normalize_tags([tag])[0]
        result = [entry for entry in result if wanted_tag in entry.tags]
    return result
