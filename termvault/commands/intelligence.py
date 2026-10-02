"""Phase 7 CLI: ``tv find``, ``tv related``, and ``tv index …``."""

from __future__ import annotations

from typing import Optional

import typer

from termvault.errors import TermVaultError
from termvault.formatting import dumps_json
from termvault.intelligence.constants import DEFAULT_FIND_MODE, FIND_MODES
from termvault.intelligence.hybrid import find_entries
from termvault.intelligence.index import (
    build_index,
    clear_index,
    index_status,
    related_entries,
    resolve_backend,
)
from termvault.intelligence.report import (
    format_build_report,
    format_find_result,
    format_index_status,
    format_related,
)

index_app = typer.Typer(
    help="Local embedding index used by semantic search and 'tv related'.",
    no_args_is_help=True,
)

_BACKEND_HELP = (
    "Embedding backend: 'hashing' (default, offline), 'hashing:<dim>', "
    "or 'st[:model]' (needs: pip install \"termvault[semantic]\")."
)


def _fail(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from None


def find_command(
    query: list[str] = typer.Argument(..., help="What you are looking for (typos are fine)."),
    mode: str = typer.Option(
        DEFAULT_FIND_MODE,
        "--mode",
        "-m",
        help="Ranking: " + ", ".join(FIND_MODES) + ".",
    ),
    limit: int = typer.Option(10, "--limit", "-n", min=1, help="Max results."),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Require this tag."),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Require this kind."),
    backend: Optional[str] = typer.Option(None, "--backend", help=_BACKEND_HELP),
    explain: bool = typer.Option(False, "--explain", "-x", help="Show which rankers matched."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Smart search: full-text + fuzzy (typo-tolerant) + semantic, fused."""
    joined = " ".join(query).strip()
    if not joined:
        typer.echo("Error: search query is required.", err=True)
        raise typer.Exit(code=1)
    try:
        result = find_entries(
            joined,
            mode=mode,
            limit=limit,
            tag=tag,
            kind=kind,
            backend=backend,
        )
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(result.to_dict()) if as_json else format_find_result(result, explain=explain))


def related_command(
    entry_id: int = typer.Argument(..., help="Entry ID to find neighbours for."),
    limit: int = typer.Option(5, "--limit", "-n", min=1, help="Max results."),
    backend: Optional[str] = typer.Option(None, "--backend", help=_BACKEND_HELP),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """List entries similar to an existing one."""
    try:
        source, hits = related_entries(
            entry_id,
            limit=limit,
            backend=resolve_backend(backend),
        )
    except TermVaultError as exc:
        _fail(exc)
    if as_json:
        typer.echo(
            dumps_json(
                {
                    "entry": source.to_dict(),
                    "related": [
                        {"entry": hit.entry.to_dict(), "score": hit.score} for hit in hits
                    ],
                }
            )
        )
    else:
        typer.echo(format_related(source, hits))


@index_app.command("build")
def index_build_command(
    backend: Optional[str] = typer.Option(None, "--backend", help=_BACKEND_HELP),
    rebuild: bool = typer.Option(False, "--rebuild", help="Re-embed everything from scratch."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Embed new or edited entries (incremental unless --rebuild)."""
    try:
        report = build_index(resolve_backend(backend), rebuild=rebuild)
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(report.to_dict()) if as_json else format_build_report(report))


@index_app.command("status")
def index_status_command(
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Show how many entries are indexed, stale, or missing."""
    try:
        status = index_status()
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(status.to_dict()) if as_json else format_index_status(status))


@index_app.command("clear")
def index_clear_command(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete all stored embeddings (they are rebuilt on demand)."""
    if not yes and not typer.confirm("Delete all stored embeddings?", default=False):
        typer.echo("Cancelled.")
        raise typer.Exit(code=1)
    removed = clear_index()
    typer.echo(f"Removed {removed} embedding(s).")


def register_intelligence_commands(app: typer.Typer) -> None:
    app.command("find")(find_command)
    app.command("related")(related_command)
    app.add_typer(index_app, name="index")
