"""Tests for Phase 2 entry storage and CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault.cli import app
from termvault.config import DATA_DIR_ENV

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolate each test against a temporary vault directory."""
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return data_dir


def test_add_list_show_flow(vault_home: Path) -> None:
    add = runner.invoke(
        app,
        [
            "add",
            "Reset docker desktop",
            "--body",
            "Wipe WSL data, then restart Docker.",
            "--tag",
            "docker",
            "--tag",
            "windows",
        ],
    )
    assert add.exit_code == 0
    assert "Added entry 1" in add.output
    assert (vault_home / "termvault.db").exists()

    listed = runner.invoke(app, ["list"])
    assert listed.exit_code == 0
    assert "Reset docker desktop" in listed.output
    assert "docker" in listed.output

    shown = runner.invoke(app, ["show", "1"])
    assert shown.exit_code == 0
    assert "Wipe WSL data" in shown.output
    assert "Tags:    docker, windows" in shown.output


def test_edit_and_delete(vault_home: Path) -> None:
    runner.invoke(app, ["add", "Old title", "--body", "old body", "--tag", "tmp"])

    edited = runner.invoke(
        app,
        ["edit", "1", "--title", "New title", "--body", "new body", "--tag", "keep"],
    )
    assert edited.exit_code == 0
    assert "Updated entry 1: New title" in edited.output

    shown = runner.invoke(app, ["show", "1"])
    assert "New title" in shown.output
    assert "new body" in shown.output
    assert "Tags:    keep" in shown.output

    deleted = runner.invoke(app, ["delete", "1", "--yes", "--permanent"])
    assert deleted.exit_code == 0
    assert "Permanently deleted entry 1" in deleted.output

    missing = runner.invoke(app, ["show", "1"])
    assert missing.exit_code == 1
    assert "Entry 1 not found" in missing.output
    assert "Traceback" not in missing.output


def test_add_rejects_blank_title(vault_home: Path) -> None:
    result = runner.invoke(app, ["add", "   "])
    assert result.exit_code == 1
    assert "Title is required" in result.output
    assert "Traceback" not in result.output


def test_list_empty_vault_message(vault_home: Path) -> None:
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "No entries yet" in result.output


def test_delete_cancelled_without_yes(vault_home: Path) -> None:
    runner.invoke(app, ["add", "Keep me"])
    result = runner.invoke(app, ["delete", "1"], input="n\n")
    assert result.exit_code == 0
    assert "Cancelled" in result.output

    shown = runner.invoke(app, ["show", "1"])
    assert shown.exit_code == 0
    assert "Keep me" in shown.output
