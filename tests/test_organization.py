"""Tests for expanded Phase 4 organization features."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.cli import app
from termvault.config import DATA_DIR_ENV, load_settings, save_settings, VaultSettings
from termvault.formatting import body_snippet, format_body_for_show, format_entry_summary

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    return data_dir


def _seed() -> None:
    runner.invoke(
        app,
        [
            "add",
            "Postgres auth",
            "--body",
            "Reset role password",
            "--tag",
            "db",
            "--tag",
            "ops",
            "--kind",
            "command",
        ],
    )
    runner.invoke(
        app,
        [
            "add",
            "Docker stuck",
            "--body",
            "Restart WSL\nThen clear cache",
            "--tag",
            "docker",
            "--kind",
            "error",
        ],
    )
    runner.invoke(
        app,
        ["add", "Git rebase", "--body", "git rebase -i HEAD~3", "--tag", "git", "--kind", "snippet"],
    )


def test_list_filter_by_tag(vault_home: Path) -> None:
    _ = vault_home
    _seed()

    result = runner.invoke(app, ["list", "--tag", "db"])
    assert result.exit_code == 0
    assert "Postgres auth" in result.output
    assert "Docker stuck" not in result.output


def test_list_filter_by_kind(vault_home: Path) -> None:
    _ = vault_home
    _seed()

    result = runner.invoke(app, ["list", "--kind", "snippet", "--no-snippets"])
    assert result.exit_code == 0
    assert "Git rebase" in result.output
    assert "Postgres auth" not in result.output


def test_list_sort_by_title(vault_home: Path) -> None:
    _ = vault_home
    _seed()

    result = runner.invoke(app, ["list", "--sort", "title", "--no-snippets"])
    assert result.exit_code == 0
    titles = []
    for line in result.output.splitlines():
        if line.startswith("["):
            # Format: [id] (kind) Title
            title = line.split(") ", 1)[1]
            titles.append(title)
    assert titles == sorted(titles, key=str.lower)


def test_recent_command(vault_home: Path) -> None:
    _ = vault_home
    _seed()

    result = runner.invoke(app, ["recent", "--limit", "2"])
    assert result.exit_code == 0
    assert result.output.count("[") >= 2


def test_tags_lists_counts(vault_home: Path) -> None:
    _ = vault_home
    _seed()

    result = runner.invoke(app, ["tags"])
    assert result.exit_code == 0
    assert "db\t1 entry" in result.output
    assert "docker\t1 entry" in result.output


def test_tag_add_remove_rename(vault_home: Path) -> None:
    _ = vault_home
    runner.invoke(app, ["add", "Note", "--body", "body", "--tag", "alpha"])

    added = runner.invoke(app, ["tag", "add", "1", "beta"])
    assert added.exit_code == 0
    assert "alpha" in added.output and "beta" in added.output

    renamed = runner.invoke(app, ["tag", "rename", "beta", "gamma"])
    assert renamed.exit_code == 0
    assert "1 entry" in renamed.output

    listed = runner.invoke(app, ["list", "--tag", "gamma"])
    assert "Note" in listed.output

    removed = runner.invoke(app, ["tag", "remove", "1", "alpha"])
    assert removed.exit_code == 0
    assert "alpha" not in removed.output.split(":", 1)[1]


def test_pin_sorts_above_others(vault_home: Path) -> None:
    _ = vault_home
    runner.invoke(app, ["add", "Older", "--body", "a"])
    runner.invoke(app, ["add", "Newer", "--body", "b"])
    pin = runner.invoke(app, ["pin", "1"])
    assert pin.exit_code == 0

    listed = runner.invoke(app, ["list", "--no-snippets"])
    first_title_line = next(
        line for line in listed.output.splitlines() if line.startswith("[")
    )
    assert "Older" in first_title_line
    assert "★" in first_title_line


def test_trash_restore_purge(vault_home: Path) -> None:
    _ = vault_home
    runner.invoke(app, ["add", "Temp", "--body", "x", "--tag", "tmp"])

    trashed = runner.invoke(app, ["delete", "1", "--yes"])
    assert trashed.exit_code == 0
    assert "Trashed entry 1" in trashed.output

    active = runner.invoke(app, ["list"])
    assert "Temp" not in active.output

    in_trash = runner.invoke(app, ["list", "--trash"])
    assert "Temp" in in_trash.output

    restored = runner.invoke(app, ["restore", "1"])
    assert restored.exit_code == 0
    assert "Restored entry 1" in restored.output

    runner.invoke(app, ["delete", "1", "--yes"])
    purged = runner.invoke(app, ["purge", "--yes"])
    assert purged.exit_code == 0
    assert "Purged 1" in purged.output

    missing = runner.invoke(app, ["show", "1"])
    assert missing.exit_code == 1


def test_stats_and_json_output(vault_home: Path) -> None:
    _ = vault_home
    _seed()
    runner.invoke(app, ["pin", "1"])

    stats = runner.invoke(app, ["stats", "--json"])
    assert stats.exit_code == 0
    payload = json.loads(stats.output)
    assert payload["active_entries"] == 3
    assert payload["pinned_entries"] == 1
    assert "command" in payload["kind_counts"]

    listed = runner.invoke(app, ["list", "--json", "--no-snippets"])
    assert listed.exit_code == 0
    rows = json.loads(listed.output)
    assert isinstance(rows, list)
    assert rows[0]["title"]


def test_config_persists_defaults(vault_home: Path) -> None:
    _ = vault_home
    saved = runner.invoke(
        app,
        ["config", "--list-limit", "3", "--sort", "title", "--no-snippets", "--show"],
    )
    assert saved.exit_code == 0
    assert "Saved settings" in saved.output

    settings = load_settings()
    assert settings.default_list_limit == 3
    assert settings.default_sort == "title"
    assert settings.show_snippets is False

    # invalid sort rejected
    bad = VaultSettings(default_sort="nope")
    with pytest.raises(ValueError):
        save_settings(bad)


def test_search_ignores_trashed(vault_home: Path) -> None:
    _ = vault_home
    runner.invoke(app, ["add", "Secret postgres tip", "--body", "hidden", "--tag", "db"])
    runner.invoke(app, ["delete", "1", "--yes"])
    result = runner.invoke(app, ["search", "postgres"])
    assert result.exit_code == 0
    assert "No matches" in result.output


def test_show_preserves_code_indentation(vault_home: Path) -> None:
    _ = vault_home
    body = "def hello():\n    return 1\n"
    runner.invoke(app, ["add", "Snippet", "--body", body, "--kind", "snippet"])
    result = runner.invoke(app, ["show", "1"])
    assert result.exit_code == 0
    assert "    return 1" in result.output
    assert "Kind:    snippet" in result.output


def test_formatting_helpers() -> None:
    from termvault.models import Entry

    assert body_snippet("  a   b  c  ", width=4) == "a b…"
    assert body_snippet("short") == "short"
    assert format_body_for_show("\n  code\n") == "  code"
    assert format_body_for_show("   ") == "(empty body)"

    sample = Entry(
        id=1,
        title="T",
        body="hello world",
        tags=("a",),
        created_at="t",
        updated_at="t",
        kind="note",
        pinned=True,
    )
    text = format_entry_summary(sample)
    assert "★" in text
    assert "hello world" in text


def test_legacy_csv_tags_migrate_to_normalized(vault_home: Path) -> None:
    from termvault import db
    from termvault.config import ensure_data_dir
    from termvault.db import initialize_database

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
            VALUES ('Migrated', 'body', 'alpha,beta', 't', 't');
            """
        )

    initialize_database()
    tags = storage.list_tags()
    names = {tag.name for tag in tags}
    assert names == {"alpha", "beta"}

    listed = storage.list_entries(tag="alpha")
    assert len(listed) == 1
    assert listed[0].title == "Migrated"
