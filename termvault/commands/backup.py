"""Phase 6 Part 2 CLI: ``tv backup …`` and ``tv copy``."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from termvault import storage
from termvault.backup.archive import load_manifest
from termvault.backup.constants import LATEST_ALIAS
from termvault.backup.creator import create_backup
from termvault.backup.report import (
    format_backup_list,
    format_backup_result,
    format_manifest,
    format_prune_plan,
    format_restore_plan,
    format_restore_result,
    format_verify_report,
)
from termvault.backup.restorer import apply_restore, plan_restore
from termvault.backup.store import apply_prune, list_backups, plan_prune, resolve_backup_path
from termvault.backup.verifier import verify_backup
from termvault.clipboard import COPY_FIELDS, copy_text, entry_clip_text
from termvault.errors import TermVaultError
from termvault.formatting import dumps_json

backup_app = typer.Typer(
    help="Full-vault backup archives: create, list, verify, restore, prune.",
    no_args_is_help=True,
)

_ARCHIVE_HELP = f"Backup path, a filename in the backup folder, or '{LATEST_ALIAS}'."


def _fail(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from None


def _dir_option(value: Optional[Path]) -> Optional[Path]:
    return value.expanduser().resolve() if value else None


@backup_app.command("create")
def backup_create_command(
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Archive path or folder (default: <data dir>/backups).",
    ),
    label: Optional[str] = typer.Option(None, "--label", "-l", help="Short note, e.g. 'before-cleanup'."),
    no_config: bool = typer.Option(False, "--no-config", help="Leave config.json out."),
    with_drafts: bool = typer.Option(False, "--with-drafts", help="Include unsaved TUI drafts."),
    with_export: bool = typer.Option(
        False,
        "--with-export",
        help="Also store a readable export.json of every entry.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite --output if it exists."),
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print the result as JSON."),
) -> None:
    """Snapshot the whole vault (database + config) into a zip archive."""
    try:
        result = create_backup(
            output,
            label=label,
            include_config=not no_config,
            include_drafts=with_drafts,
            include_export=with_export,
            backup_dir=_dir_option(backup_dir),
            overwrite=force,
        )
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(result.to_dict()) if as_json else format_backup_result(result))


@backup_app.command("list")
def backup_list_command(
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """List backups in the backup folder, newest first."""
    infos = list_backups(_dir_option(backup_dir))
    if as_json:
        typer.echo(dumps_json([info.to_dict() for info in infos]))
    else:
        typer.echo(format_backup_list(infos))


@backup_app.command("info")
def backup_info_command(
    archive: str = typer.Argument(..., help=_ARCHIVE_HELP),
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Show what a backup contains without verifying it."""
    try:
        path = resolve_backup_path(archive, _dir_option(backup_dir))
        manifest = load_manifest(path)
    except TermVaultError as exc:
        _fail(exc)
    if as_json:
        typer.echo(dumps_json({"path": str(path), "manifest": manifest.to_dict()}))
    else:
        typer.echo(format_manifest(manifest, path=str(path)))


@backup_app.command("verify")
def backup_verify_command(
    archive: str = typer.Argument(..., help=_ARCHIVE_HELP),
    quick: bool = typer.Option(False, "--quick", help="Checksums only; skip the SQLite check."),
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Check checksums, database health, and compatibility. Exits 1 on failure."""
    try:
        path = resolve_backup_path(archive, _dir_option(backup_dir))
    except TermVaultError as exc:
        _fail(exc)
    report = verify_backup(path, deep=not quick)
    typer.echo(dumps_json(report.to_dict()) if as_json else format_verify_report(report))
    if not report.ok:
        raise typer.Exit(code=1)


@backup_app.command("restore")
def backup_restore_command(
    archive: str = typer.Argument(..., help=_ARCHIVE_HELP),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan; change nothing."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
    no_config: bool = typer.Option(False, "--no-config", help="Keep the current config.json."),
    with_drafts: bool = typer.Option(False, "--with-drafts", help="Also restore TUI drafts."),
    no_safety_backup: bool = typer.Option(
        False,
        "--no-safety-backup",
        help="Do not back up the current vault first (not recommended).",
    ),
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Replace the current vault with a backup (a safety backup is taken first)."""
    directory = _dir_option(backup_dir)
    try:
        plan = plan_restore(
            archive,
            include_config=not no_config,
            include_drafts=with_drafts,
            safety_backup=not no_safety_backup,
            backup_dir=directory,
        )
    except TermVaultError as exc:
        _fail(exc)

    if dry_run:
        typer.echo(dumps_json(plan.to_dict()) if as_json else format_restore_plan(plan))
        return

    if not yes:
        typer.echo(format_restore_plan(plan))
        if not typer.confirm("Replace the current vault with this backup?"):
            typer.echo("Cancelled.")
            raise typer.Exit(code=0)

    try:
        result = apply_restore(plan, backup_dir=directory)
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(result.to_dict()) if as_json else format_restore_result(result))


@backup_app.command("prune")
def backup_prune_command(
    keep: Optional[int] = typer.Option(None, "--keep", "-k", min=1, help="Keep the newest N backups."),
    older_than: Optional[int] = typer.Option(
        None,
        "--older-than",
        min=0,
        help="Delete backups older than N days.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Actually delete (default is a preview)."),
    backup_dir: Optional[Path] = typer.Option(None, "--dir", help="Backup folder override."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Delete old backups. Previews unless --yes; the newest backup is always kept."""
    try:
        plan = plan_prune(
            keep_last=keep,
            older_than_days=older_than,
            directory=_dir_option(backup_dir),
        )
        if yes:
            apply_prune(plan)
    except TermVaultError as exc:
        _fail(exc)
    if as_json:
        payload = plan.to_dict()
        payload["applied"] = yes
        typer.echo(dumps_json(payload))
    else:
        typer.echo(format_prune_plan(plan, applied=yes))


def copy_command(
    entry_id: int = typer.Argument(..., help="Entry id to copy."),
    field: str = typer.Option(
        "body",
        "--field",
        "-f",
        help=f"What to copy: {', '.join(COPY_FIELDS)}.",
    ),
    print_only: bool = typer.Option(
        False,
        "--print",
        "-p",
        help="Write to stdout instead of the clipboard.",
    ),
    include_trashed: bool = typer.Option(
        False,
        "--include-trashed",
        help="Allow copying an entry that is in the trash.",
    ),
) -> None:
    """Copy an entry's body, title, metadata, or export snippet to the clipboard."""
    try:
        entry = storage.get_entry(entry_id, include_trashed=include_trashed)
        text = entry_clip_text(entry, field)
        if print_only:
            typer.echo(text)
            return
        backend = copy_text(text)
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(f"Copied {field} of entry {entry.id} ({len(text)} chars) via {backend.name}.")


def register_backup_commands(app: typer.Typer) -> None:
    """Register ``tv backup`` and ``tv copy``."""
    app.add_typer(backup_app, name="backup")
    app.command("copy")(copy_command)
