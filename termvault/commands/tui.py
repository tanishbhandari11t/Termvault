"""CLI command to launch the TermVault TUI."""

from __future__ import annotations

import typer


def tui_command() -> None:
    """Open the interactive terminal UI for browsing the vault."""
    from termvault.tui.app import run_tui

    run_tui()


def register_tui_command(app: typer.Typer) -> None:
    """Register ``tv tui`` and ``tv ui`` aliases."""
    app.command("tui")(tui_command)
    app.command("ui")(tui_command)
