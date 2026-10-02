"""High-level export orchestration for Phase 6 Part 1."""

from __future__ import annotations

from pathlib import Path

from termvault.portability.checksums import hash_entries
from termvault.portability.constants import DEFAULT_CODEC, EXPORT_CODECS
from termvault.portability.errors import ExportError, UnsupportedFormatError
from termvault.portability.filters import ExportFilters
from termvault.portability.json_format import dumps_export_json
from termvault.portability.markdown_format import dumps_export_markdown
from termvault.portability.paths import resolve_export_path, write_text_file
from termvault.portability.report import ExportReport
from termvault.portability.schema import ExportDocument
from termvault.portability.selection import (
    build_manifest,
    entries_to_export_entries,
    select_vault_entries,
)


def normalize_codec(codec: str | None) -> str:
    value = (codec or DEFAULT_CODEC).strip().lower()
    if value in {"md", "markdown"}:
        value = "markdown"
    if value not in EXPORT_CODECS:
        raise UnsupportedFormatError(
            f"Unsupported codec {codec!r}; choose: {', '.join(EXPORT_CODECS)}"
        )
    return value


def export_vault(
    filters: ExportFilters | None = None,
    *,
    codec: str = DEFAULT_CODEC,
) -> ExportDocument:
    """Build an in-memory export document from the current vault."""
    flt = filters or ExportFilters()
    vault_entries = select_vault_entries(flt)
    export_entries = entries_to_export_entries(vault_entries)
    aggregate = hash_entries(export_entries)
    manifest = build_manifest(
        export_entries,
        filters=flt,
        aggregate_hash=aggregate,
    )
    return ExportDocument(
        entries=export_entries,
        manifest=manifest,
        codec_hint=normalize_codec(codec),
    )


def serialize_document(document: ExportDocument, *, codec: str, pretty: bool = True) -> str:
    codec = normalize_codec(codec)
    if codec == "json":
        return dumps_export_json(document, pretty=pretty)
    if codec == "markdown":
        return dumps_export_markdown(document)
    raise UnsupportedFormatError(f"Unsupported codec: {codec}")


def write_export(
    destination: str | Path,
    *,
    filters: ExportFilters | None = None,
    codec: str = DEFAULT_CODEC,
    pretty: bool = True,
    force: bool = False,
    dry_run: bool = False,
) -> ExportReport:
    """Export the vault to a file path (or preview with dry_run)."""
    codec = normalize_codec(codec)
    flt = filters or ExportFilters()
    document = export_vault(flt, codec=codec)
    text = serialize_document(document, codec=codec, pretty=pretty)
    titles = [entry.title for entry in document.entries]

    if dry_run:
        return ExportReport(
            path=None,
            codec=codec,
            entry_count=len(document.entries),
            filters_summary=flt.describe(),
            content_hash=document.manifest.content_hash,
            dry_run=True,
            preview_titles=titles,
        )

    path = resolve_export_path(destination, codec=codec)
    try:
        written = write_text_file(path, text, overwrite=force)
    except ExportError:
        raise
    except OSError as exc:
        raise ExportError(str(exc)) from exc

    return ExportReport(
        path=written,
        codec=codec,
        entry_count=len(document.entries),
        filters_summary=flt.describe(),
        content_hash=document.manifest.content_hash,
        dry_run=False,
        preview_titles=titles,
    )
