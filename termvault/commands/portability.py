"""Phase 6 Part 1 CLI: ``tv export`` / ``tv import``."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from termvault.errors import TermVaultError
from termvault.formatting import dumps_json
from termvault.portability.constants import (
    CONFLICT_POLICIES,
    EXPORT_CODECS,
    MATCH_STRATEGIES,
)
from termvault.portability.exporter import write_export
from termvault.portability.filters import ExportFilters
from termvault.portability.importer import import_vault, plan_import, read_import
from termvault.portability.report import (
    dumps_report_json,
    format_document_preview,
)

portability_app = typer.Typer(
    help="Export / import vault knowledge (Phase 6 Part 1).",
)


def _fail(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from None


def _parse_ids(raw: Optional[str]) -> tuple[int, ...]:
    if not raw:
        return ()
    parts = [part.strip() for part in raw.split(",") if part.strip()]
    ids: list[int] = []
    for part in parts:
        try:
            ids.append(int(part))
        except ValueError:
            raise typer.BadParameter(f"Invalid entry id: {part!r}") from None
    return tuple(ids)


def export_command(
    destination: str = typer.Argument(
        ...,
        help="Output file path, or a directory to write a default filename into.",
    ),
    format_: str = typer.Option(
        "json",
        "--format",
        "-f",
        help=f"Export codec: {', '.join(EXPORT_CODECS)}.",
    ),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Only entries with tag."),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Only this kind."),
    pinned: bool = typer.Option(False, "--pinned", help="Only pinned entries."),
    include_trashed: bool = typer.Option(
        False,
        "--include-trashed",
        help="Include trashed entries alongside active ones.",
    ),
    trashed_only: bool = typer.Option(
        False,
        "--trashed-only",
        help="Export only trashed entries.",
    ),
    query: Optional[str] = typer.Option(
        None,
        "--query",
        "-q",
        help="Only entries matching a search query.",
    ),
    ids: Optional[str] = typer.Option(
        None,
        "--ids",
        help="Comma-separated entry ids to export.",
    ),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Max entries to export.",
    ),
    sort: str = typer.Option("updated", "--sort", "-s", help="Sort for export order."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite the destination file if it already exists.",
    ),
    pretty: bool = typer.Option(
        True,
        "--pretty/--compact",
        help="Pretty-print JSON (ignored for markdown).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Build the export and print a preview without writing a file.",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the export report as JSON.",
    ),
) -> None:
    """Export vault entries to JSON or Markdown."""
    filters = ExportFilters(
        tag=tag,
        kind=kind,
        pinned_only=pinned,
        include_trashed=include_trashed,
        trashed_only=trashed_only,
        sort=sort,
        limit=limit,
        ids=_parse_ids(ids),
        query=query,
    )
    try:
        report = write_export(
            destination,
            filters=filters,
            codec=format_,
            pretty=pretty,
            force=force,
            dry_run=dry_run,
        )
    except TermVaultError as exc:
        _fail(exc)
    if as_json:
        typer.echo(dumps_report_json(report.to_dict()), nl=False)
    else:
        typer.echo(report.format_text())


def import_command(
    source: str = typer.Argument(
        ...,
        help="Import file (.json / .md) or a directory of markdown files.",
    ),
    format_: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help=f"Force codec: {', '.join(EXPORT_CODECS)} (auto-detect by default).",
    ),
    conflict: str = typer.Option(
        "skip",
        "--conflict",
        "-c",
        help=f"On match: {', '.join(CONFLICT_POLICIES)}.",
    ),
    match: str = typer.Option(
        "title",
        "--match",
        "-m",
        help=f"How to match existing entries: {', '.join(MATCH_STRATEGIES)}.",
    ),
    include_trashed: bool = typer.Option(
        False,
        "--include-trashed",
        help="Import entries marked trashed in the file.",
    ),
    no_skip_identical: bool = typer.Option(
        False,
        "--no-skip-identical",
        help="Do not auto-skip when content hashes match.",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Treat manifest mismatches as errors (via re-validation).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show the import plan without writing to the vault.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="List every planned create/skip/overwrite step.",
    ),
    preview: bool = typer.Option(
        False,
        "--preview",
        help="Only show the parsed document summary (no plan / apply).",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the import report as JSON.",
    ),
) -> None:
    """Import entries from a TermVault export file."""
    _ = strict  # reserved for stricter CLI path; planner validate is default
    try:
        if preview:
            document = read_import(source, codec=format_)
            if as_json:
                typer.echo(dumps_json(document.to_dict()))
            else:
                typer.echo(format_document_preview(document))
            return

        if dry_run:
            plan = plan_import(
                source,
                codec=format_,
                policy=conflict,
                strategy=match,
                include_trashed_imports=include_trashed,
                skip_identical=not no_skip_identical,
            )
            from termvault.portability.report import ImportApplyReport

            report = ImportApplyReport(plan=plan, dry_run=True)
        else:
            report = import_vault(
                source,
                codec=format_,
                policy=conflict,
                strategy=match,
                include_trashed_imports=include_trashed,
                skip_identical=not no_skip_identical,
                dry_run=False,
            )
    except TermVaultError as exc:
        _fail(exc)

    if as_json:
        typer.echo(dumps_report_json(report.to_dict()), nl=False)
    else:
        typer.echo(report.format_text(verbose=verbose))


def register_portability_commands(app: typer.Typer) -> None:
    """Register ``tv export`` and ``tv import``."""
    app.command("export")(export_command)
    app.command("import")(import_command)
