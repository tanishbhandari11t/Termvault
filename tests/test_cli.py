"""Tests for the TermVault CLI foundation (Phase 1)."""

from __future__ import annotations

from typer.testing import CliRunner

from termvault import __version__
from termvault.cli import app

runner = CliRunner()


def test_cli_starts_successfully() -> None:
    """Invoking the CLI with no args shows help without crashing."""
    result = runner.invoke(app)
    assert result.exit_code in (0, 2)
    assert "TermVault" in result.output
    assert "Traceback" not in result.output


def test_help_works() -> None:
    """``tv --help`` describes TermVault and exits successfully."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "TermVault - A local-first terminal knowledge base for developers." in result.output
    assert "--version" in result.output
    assert "--help" in result.output
    assert "add" in result.output
    assert "list" in result.output
    assert "search" in result.output
    assert "tags" in result.output
    assert "recent" in result.output
    assert "stats" in result.output
    assert "pin" in result.output
    assert "restore" in result.output
    assert "tui" in result.output


def test_version_works() -> None:
    """``tv --version`` exits successfully."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0


def test_version_output_is_correct() -> None:
    """``tv --version`` prints the canonical package version string."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip() == f"TermVault {__version__}"
    assert __version__ == "0.8.0"


def test_invalid_input_exits_cleanly() -> None:
    """Unknown options fail with a non-zero exit code and no traceback."""
    result = runner.invoke(app, ["--not-a-real-option"])
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "No such option" in result.output
