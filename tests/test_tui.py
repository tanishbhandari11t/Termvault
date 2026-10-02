"""Tests for Phase 5 Part 1 (expanded core TUI)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.cli import app
from termvault.config import DATA_DIR_ENV
from termvault.tui.app import TermVaultApp
from termvault.tui.browser import (
    BrowseSession,
    format_status_count,
    load_active_entries,
    next_index_after_reload,
    safe_load_active_entries,
)
from termvault.tui.constants import MAX_TITLE_LENGTH
from termvault.tui.display import confirm_trash_message, list_label, status_with_query
from termvault.tui.drafts import (
    clear_draft,
    load_draft,
    new_draft_path,
    save_draft,
)
from termvault.tui.search import SearchController
from termvault.tui.validation import FormData, forms_equal, parse_tags, validate_entry_form

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    storage.add_entry(
        "Postgres auth",
        body="Reset role password",
        tags=["db"],
        kind="command",
    )
    storage.add_entry(
        "Docker stuck",
        body="Restart WSL",
        tags=["docker"],
        kind="error",
        pinned=True,
    )
    return data_dir


def test_tui_command_listed_in_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "tui" in result.output
    assert "ui" in result.output


def test_tui_help() -> None:
    result = runner.invoke(app, ["tui", "--help"])
    assert result.exit_code == 0
    lowered = result.output.lower()
    assert "interactive" in lowered
    assert "vault" in lowered


def test_validation_accepts_and_rejects() -> None:
    ok = validate_entry_form(
        title="  Hello   world ",
        body="body",
        kind="note",
        tags_raw="Db, db, ops",
    )
    assert ok.ok and ok.data is not None
    assert ok.data.title == "Hello world"
    assert ok.data.tags == ("db", "ops")

    blank = validate_entry_form(title="  ", body="", kind="note", tags_raw="")
    assert blank.ok is False

    long_title = validate_entry_form(
        title="x" * (MAX_TITLE_LENGTH + 1),
        body="",
        kind="note",
        tags_raw="",
    )
    assert long_title.ok is False

    bad_kind = validate_entry_form(title="A", body="", kind="nope", tags_raw="")
    assert bad_kind.ok is False

    assert parse_tags("a, b, a") == ("a", "b")
    left = FormData("t", "b", "note", ("a",))
    right = FormData("t", "b", "note", ("a",))
    assert forms_equal(left, right)


def test_drafts_roundtrip(vault_home: Path) -> None:
    _ = vault_home
    path = new_draft_path()
    clear_draft(path)
    data = FormData(title="Draft", body="hello", kind="snippet", tags=("x",))
    save_draft(path, data)
    loaded = load_draft(path)
    assert loaded is not None
    assert loaded.title == "Draft"
    assert loaded.kind == "snippet"
    clear_draft(path)
    assert load_draft(path) is None


def test_search_controller_history() -> None:
    ctl = SearchController()
    ctl.set_query("alpha", commit_history=True)
    ctl.set_query("beta", commit_history=True)
    ctl.set_query("alpha", commit_history=True)
    assert ctl.history[0] == "alpha"
    assert ctl.history.count("alpha") == 1
    ctl.clear()
    assert ctl.query == ""


def test_browser_helpers(vault_home: Path) -> None:
    _ = vault_home
    all_entries = load_active_entries()
    assert len(all_entries) == 2
    filtered = load_active_entries(query="postgres")
    assert len(filtered) == 1
    entries, err = safe_load_active_entries(query="docker")
    assert err is None
    assert len(entries) == 1
    assert format_status_count(0) == "No matching entries."
    assert "2 entries" in format_status_count(2)
    assert next_index_after_reload(all_entries, all_entries[1].id) == 1

    session = BrowseSession()
    session.remember_opened(2)
    session.remember_opened(1)
    session.remember_opened(2)
    assert list(session.recent_opened)[:2] == [2, 1]


def test_display_helpers(vault_home: Path) -> None:
    entry = storage.get_entry(2)
    assert "Docker" in list_label(entry)
    assert "trash" in confirm_trash_message(entry).lower()
    assert "filter:" in status_with_query("ok", "db")


@pytest.mark.asyncio
async def test_tui_loads_entries_and_quits(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        assert len(app_ui._entries) == 2
        titles = {entry.title for entry in app_ui._entries}
        assert titles == {"Postgres auth", "Docker stuck"}
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_search_filters_list(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        app_ui._query = "docker"
        app_ui.query_one("#search").value = "docker"
        app_ui.reload_entries()
        await pilot.pause()
        assert len(app_ui._entries) == 1
        assert app_ui._entries[0].title == "Docker stuck"
        assert "docker" in app_ui.search.history or app_ui.search.query == "docker"
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_toggle_pin(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        target = next(e for e in app_ui._entries if e.title == "Postgres auth")
        for index, entry in enumerate(app_ui._entries):
            if entry.id == target.id:
                app_ui.query_one("#entry-list").index = index
                app_ui.show_entry(entry)
                break
        await pilot.press("p")
        await pilot.pause()
        assert storage.get_entry(target.id).pinned is True
        assert target.id in app_ui.session.recent_opened
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_trash_with_confirm(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        target = next(e for e in app_ui._entries if e.title == "Docker stuck")
        for index, entry in enumerate(app_ui._entries):
            if entry.id == target.id:
                app_ui.query_one("#entry-list").index = index
                app_ui.show_entry(entry)
                break
        app_ui.action_trash_entry()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        remaining = {e.title for e in load_active_entries()}
        assert "Docker stuck" not in remaining
        assert "Postgres auth" in remaining
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_refresh_and_clear_search(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        app_ui._query = "missing"
        app_ui.reload_entries()
        assert app_ui._entries == []
        await pilot.press("r")
        await pilot.pause()
        search = app_ui.query_one("#search")
        search.value = "missing"
        search.focus()
        await pilot.press("escape")
        await pilot.pause()
        assert app_ui._query == ""
        assert len(app_ui._entries) == 2
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_shortcut_hints_present(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        hints = app_ui.query_one("#shortcut-hints")
        assert hints.id == "shortcut-hints"
        await pilot.press("q")
