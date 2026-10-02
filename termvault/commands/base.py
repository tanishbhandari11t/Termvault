"""Shared CLI helpers and command registration for TermVault."""

from __future__ import annotations

import typer

from termvault.commands.backup import register_backup_commands
from termvault.commands.entries import register_entry_commands
from termvault.commands.portability import register_portability_commands
from termvault.commands.tui import register_tui_command


def register_commands(app: typer.Typer) -> None:
    """Attach subcommands to the root Typer application.

    Args:
        app: The root TermVault Typer application.
    """
    register_entry_commands(app)
    register_portability_commands(app)
    register_backup_commands(app)
    register_tui_command(app)
