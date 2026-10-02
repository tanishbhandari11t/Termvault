"""Tests for Phase 3 full-text search."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.cli import app
from termvault.config import DATA_DIR_ENV, ensure_data_dir
from termvault.db import initialize_database
from termvault import db

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return data_dir


def _seed(vault_home: Path) -> None:
    _ = vault_home
    storage.add_entry(
        "Fix postgres auth",
        body="Reset role password, then reload pg_hba.conf",
        tags=["db", "ops"],
    )
    storage.add_entry(
        "Docker Desktop stuck",
        body="Restart WSL and clear Docker cache",
        tags=["docker"],
    )
    storage.add_entry(
        "Git rebase notes",
        body="Use git rebase -i to clean commits",
        tags=["git"],
    )


def test_search_finds_by_title_and_body(vault_home: Path) -> None:
    _seed(vault_home)

    result = runner.invoke(app, ["search", "postgres"])
    assert result.exit_code == 0
    assert "Fix postgres auth" in result.output
    assert "Docker Desktop stuck" not in result.output


def test_search_prefix_match(vault_home: Path) -> None:
    _seed(vault_home)

    result = runner.invoke(app, ["search", "post"])
    assert result.exit_code == 0
    assert "Fix postgres auth" in result.output


def test_search_matches_tags(vault_home: Path) -> None:
    _seed(vault_home)

    result = runner.invoke(app, ["search", "docker"])
    assert result.exit_code == 0
    assert "Docker Desktop stuck" in result.output


def test_search_no_matches(vault_home: Path) -> None:
    _seed(vault_home)

    result = runner.invoke(app, ["search", "kubernetes"])
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_search_rejects_empty_tokens(vault_home: Path) -> None:
    _ = vault_home
    result = runner.invoke(app, ["search", "***"])
    assert result.exit_code == 1
    assert "letters or numbers" in result.output
    assert "Traceback" not in result.output


def test_search_ranks_relevant_first(vault_home: Path) -> None:
    _ = vault_home
    storage.add_entry("Auth overview", body="General notes", tags=["docs"])
    storage.add_entry(
        "Fix postgres auth",
        body="Detailed postgres authentication steps",
        tags=["db"],
    )

    hits = storage.search_entries("postgres auth")
    assert hits
    assert hits[0].entry.title == "Fix postgres auth"


def test_fts_backfill_for_existing_rows(vault_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Legacy CSV-only rows become searchable after migrations."""
    monkeypatch.setenv(DATA_DIR_ENV, str(vault_home))
    ensure_data_dir()
    with db.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            INSERT INTO entries (title, body, tags, created_at, updated_at)
            VALUES ('Legacy note', 'legacy searchable body', 'old', 't', 't');
            """
        )

    initialize_database()
    hits = storage.search_entries("legacy")
    assert len(hits) == 1
    assert hits[0].entry.title == "Legacy note"
