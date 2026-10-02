"""TermVault command-line interface entry point."""

from __future__ import annotations

from typing import Optional

import typer

from termvault import __version__
from termvault.commands.base import register_commands
from termvault.errors import TermVaultError

app = typer.Typer(
    name="tv",
    help="TermVault - A local-first terminal knowledge base for developers.",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["--help"]},
)

register_commands(app)


def _version_callback(value: bool) -> None:
    """Print the package version and exit when ``--version`` is passed."""
    if value:
        typer.echo(f"TermVault {__version__}")
        raise typer.Exit(code=0)


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the installed TermVault version.",
    ),
) -> None:
    """TermVault - A local-first terminal knowledge base for developers."""
    _ = version


def run() -> None:
    """Invoke the CLI with basic error handling for unexpected failures."""
    try:
        app()
    except TermVaultError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from None
    except typer.Exit:
        raise
    except SystemExit:
        raise
    except KeyboardInterrupt:
        typer.echo("Interrupted.", err=True)
        raise SystemExit(130) from None
    except Exception as exc:  # noqa: BLE001 — top-level CLI boundary
        typer.echo(f"Error: {exc}", err=True)
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
