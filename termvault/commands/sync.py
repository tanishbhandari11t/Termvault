"""Phase 7 CLI: ``tv sync …`` (explicit opt-in folder sync)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from termvault.errors import TermVaultError
from termvault.formatting import dumps_json
from termvault.sync.config import disable_sync, init_sync
from termvault.sync.constants import MERGE_POLICIES
from termvault.sync.engine import run_sync, sync_status
from termvault.sync.report import format_config, format_result, format_status

sync_app = typer.Typer(
    help=(
        "Opt-in sync through a shared folder (Dropbox, OneDrive, Syncthing, USB...). "
        "Off until you run 'tv sync init'. No network code; you choose the folder."
    ),
    no_args_is_help=True,
)

_POLICY_HELP = "Conflict policy: " + ", ".join(MERGE_POLICIES) + " (newest = last writer wins)."


def _fail(exc: Exception) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from None


@sync_app.command("init")
def sync_init_command(
    folder: Path = typer.Argument(..., help="Shared folder every device can see."),
    name: Optional[str] = typer.Option(None, "--name", help="Friendly name for this device."),
    policy: Optional[str] = typer.Option(None, "--policy", help=_POLICY_HELP),
    create: bool = typer.Option(False, "--create", help="Create the folder if it does not exist."),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Enable sync for this vault using FOLDER."""
    try:
        config = init_sync(folder, device_name=name, policy=policy, create_folder=create)
    except TermVaultError as exc:
        _fail(exc)
    if as_json:
        typer.echo(dumps_json(config.to_dict()))
        return
    typer.echo("Sync enabled.\n" + format_config(config))
    typer.echo("Run 'tv sync run --dry-run' to preview, then 'tv sync run'.")


@sync_app.command("status")
def sync_status_command(
    policy: Optional[str] = typer.Option(None, "--policy", help=_POLICY_HELP),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Show sync settings, other devices, and pending changes."""
    try:
        status = sync_status(policy=policy)
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(status.to_dict()) if as_json else format_status(status))


@sync_app.command("run")
def sync_run_command(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the plan without changing anything."),
    policy: Optional[str] = typer.Option(None, "--policy", help=_POLICY_HELP),
    no_copies: bool = typer.Option(
        False,
        "--no-conflict-copies",
        help="Drop the losing side of a conflict instead of keeping a copy.",
    ),
    backup: bool = typer.Option(
        False,
        "--backup",
        help="Take a safety backup first if this sync will change local entries.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print as JSON."),
) -> None:
    """Merge other devices' changes in and publish this device's snapshot."""
    try:
        result = run_sync(
            dry_run=dry_run,
            policy=policy,
            conflict_copies=not no_copies,
            backup=backup,
        )
    except TermVaultError as exc:
        _fail(exc)
    typer.echo(dumps_json(result.to_dict()) if as_json else format_result(result))


@sync_app.command("disable")
def sync_disable_command(
    forget: bool = typer.Option(False, "--forget", help="Also delete the local sync settings."),
) -> None:
    """Turn sync off. Files in the shared folder are left untouched."""
    config = disable_sync(forget=forget)
    if config is None:
        typer.echo("Sync was not enabled.")
        return
    typer.echo("Sync settings removed." if forget else "Sync disabled.")


def register_sync_commands(app: typer.Typer) -> None:
    app.add_typer(sync_app, name="sync")
