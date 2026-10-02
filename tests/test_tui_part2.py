"""Tests for Phase 5 Part 2 (advanced TUI chrome)."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.cli import app
from termvault.config import DATA_DIR_ENV, VALID_KINDS, VALID_SORTS
from termvault.tui.actions_advanced import (
    apply_post_search_sort,
    count_pinned,
    format_filter_load_status,
    load_filtered_entries,
    load_filtered_result,
    load_sidebar_tags,
    load_vault_stats,
    permanently_delete_entry,
    restore_entry,
    safe_load_filtered_entries,
)
from termvault.tui.app import TermVaultApp
from termvault.tui.clipboard_util import (
    CopyMode,
    body_for_clipboard,
    format_copy_status,
    format_entry_meta_block,
    resolve_clipboard_payload,
    truncate_for_preview,
)
from termvault.tui.constants import PART2_BINDING_ACTIONS
from termvault.tui.display import confirm_permanent_delete_message
from termvault.tui.filter_presets import (
    FILTER_PRESETS,
    apply_filter_preset,
    get_filter_preset,
    list_filter_preset_ids,
)
from termvault.tui.filters import AdvancedFilters, filters_from_kwargs
from termvault.tui.helptext import (
    HELP_TEXT,
    binding_cheat_sheet,
    format_help_sections,
)
from termvault.tui.navigation import (
    bottom_index,
    clamp_index,
    describe_position,
    half_page_down,
    index_of_id,
    move_index,
    move_index_wrap,
    page_down,
    page_up,
    select_relative,
    top_index,
)
from termvault.tui.palette import (
    PALETTE_COMMANDS,
    filter_palette_commands,
    get_palette_command,
    palette_command_ids,
    palette_commands_by_category,
)

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
    storage.add_entry(
        "Snippet cache",
        body="redis-cli FLUSHDB",
        tags=["db", "cache"],
        kind="snippet",
    )
    return data_dir


def test_tui_help_mentions_interactive() -> None:
    result = runner.invoke(app, ["tui", "--help"])
    assert result.exit_code == 0


def test_advanced_filters_cycle_and_summary() -> None:
    flt = AdvancedFilters()
    assert flt.active_count() == 0
    assert "sort=updated" in flt.summary()

    sorts = [flt.cycle_sort() for _ in range(len(VALID_SORTS))]
    assert set(sorts) == set(VALID_SORTS)

    kinds = []
    for _ in range(len(VALID_KINDS) + 1):
        kinds.append(flt.cycle_kind())
    assert None in kinds
    assert set(k for k in kinds if k is not None) == set(VALID_KINDS)

    assert flt.toggle_trash() is True
    assert flt.toggle_pinned_only() is True
    assert flt.set_tag("  Db ") == "db"
    assert flt.active_count() >= 3
    assert "trash" in flt.summary()
    assert flt.compact_badge().startswith("(")

    snap = flt.snapshot()
    flt.clear()
    assert flt.active_count() == 0
    flt.restore(snap)
    assert flt.trash_mode is True
    assert flt.tag == "db"

    assert flt.toggle_tag("db") is None
    assert flt.toggle_tag("ops") == "ops"
    copied = flt.copy()
    copied.clear_soft()
    assert copied.tag is None
    assert copied.sort == flt.sort


def test_filters_from_kwargs_validates() -> None:
    flt = filters_from_kwargs(tag="API", kind="nope", sort="bogus", pinned_only=True)
    assert flt.tag == "api"
    assert flt.kind is None
    assert flt.sort == "updated"
    assert flt.pinned_only is True
    assert "No advanced" in AdvancedFilters().describe()


def test_filter_presets(vault_home: Path) -> None:
    _ = vault_home
    assert "pinned" in list_filter_preset_ids()
    preset = get_filter_preset("trash")
    assert preset is not None
    flt = preset.as_filters()
    assert flt.trash_mode is True

    target = AdvancedFilters()
    assert apply_filter_preset(target, "errors") is True
    assert target.kind == "error"
    assert apply_filter_preset(target, "missing") is False
    assert len(FILTER_PRESETS) >= 5


def test_navigation_helpers() -> None:
    assert move_index(None, delta=1, size=5) == 1
    assert move_index(4, delta=1, size=5) == 4
    assert move_index(0, delta=-1, size=5) == 0
    assert move_index_wrap(4, delta=1, size=5) == 0
    assert top_index(3) == 0
    assert bottom_index(3) == 2
    assert top_index(0) is None
    assert page_down(0, size=30, page_size=10) == 10
    assert page_up(10, size=30, page_size=10) == 0
    assert half_page_down(0, size=20, viewport=10) == 5
    assert clamp_index(99, 5) == 4
    assert describe_position(2, 10) == "3/10"

    class Obj:
        def __init__(self, id: int) -> None:
            self.id = id

    items = [Obj(10), Obj(20), Obj(30)]
    assert index_of_id(items, 20) == 1
    assert select_relative(items, 20, delta=1).id == 30
    assert select_relative(items, None, delta=1).id == 10


def test_clipboard_helpers(vault_home: Path) -> None:
    entry = storage.get_entry(1)
    assert body_for_clipboard(entry) == entry.body
    auto = resolve_clipboard_payload(entry, CopyMode.AUTO)
    assert auto.label == "body"
    title = resolve_clipboard_payload(entry, CopyMode.TITLE)
    assert title.text == entry.title
    meta = resolve_clipboard_payload(entry, CopyMode.META)
    assert "id:" in meta.text
    assert "kind:" in format_entry_meta_block(entry)
    assert "chars" in format_copy_status(entry, chars=3).lower()
    assert truncate_for_preview("a" * 80, width=20).endswith("…")

    empty_body = storage.add_entry("Title only", body="   ", kind="note")
    payload = resolve_clipboard_payload(empty_body, CopyMode.AUTO)
    assert payload.label == "title"


def test_palette_filtering_and_catalog() -> None:
    assert len(PALETTE_COMMANDS) >= 15
    assert "copy-meta" in palette_command_ids()
    hits = filter_palette_commands("trash")
    assert any(cmd.id == "trash" for cmd in hits)
    multi = filter_palette_commands("focus tags")
    assert any(cmd.id == "focus-sidebar" for cmd in multi)
    assert filter_palette_commands("zzzz-nope") == []
    cmd = get_palette_command("help")
    assert cmd is not None
    assert cmd.matches("keys")
    assert "?" in cmd.display_label()
    grouped = palette_commands_by_category()
    assert grouped
    assert PART2_BINDING_ACTIONS


def test_helptext_content() -> None:
    assert "Command palette" in HELP_TEXT or "palette" in HELP_TEXT.lower()
    assert "j /" in HELP_TEXT or "j / ↓" in HELP_TEXT
    sections = format_help_sections()
    assert "Navigation" in sections
    sheet = binding_cheat_sheet()
    assert sheet["y"] == "copy_body"
    assert sheet[":"] == "command_palette"


def test_load_filtered_entries(vault_home: Path) -> None:
    _ = vault_home
    all_active = load_filtered_entries()
    assert len(all_active) == 3

    pinned = load_filtered_entries(filters=AdvancedFilters(pinned_only=True))
    assert len(pinned) == 1
    assert pinned[0].title == "Docker stuck"

    by_tag = load_filtered_entries(filters=AdvancedFilters(tag="db"))
    assert {e.title for e in by_tag} == {"Postgres auth", "Snippet cache"}

    by_kind = load_filtered_entries(filters=AdvancedFilters(kind="error"))
    assert len(by_kind) == 1

    searched = load_filtered_result(query="docker", filters=AdvancedFilters())
    assert searched.used_search is True
    assert searched.count == 1

    storage.delete_entry(1, permanent=False)
    trash = load_filtered_entries(filters=AdvancedFilters(trash_mode=True))
    assert len(trash) == 1
    assert trash[0].is_trashed

    entries, err = safe_load_filtered_entries(query="postgres")
    assert err is None
    assert len(entries) == 0  # trashed, not in active search

    tags = load_sidebar_tags()
    assert {t.name for t in tags} >= {"db", "docker"}
    stats = load_vault_stats()
    assert stats is not None
    assert stats.active_entries >= 2

    restored = restore_entry(1)
    assert restored.is_trashed is False

    sorted_title = apply_post_search_sort(list(all_active), "title")
    assert sorted_title[0].title <= sorted_title[-1].title
    assert count_pinned(all_active) >= 1

    result = load_filtered_result(filters=AdvancedFilters(pinned_only=True))
    status = format_filter_load_status(result, AdvancedFilters(pinned_only=True))
    assert "pinned" in status


def test_permanent_delete_and_messages(vault_home: Path) -> None:
    entry = storage.add_entry("Temp", body="x", kind="note")
    storage.delete_entry(entry.id, permanent=False)
    trashed = storage.get_entry(entry.id, include_trashed=True)
    msg = confirm_permanent_delete_message(trashed)
    assert "permanent" in msg.lower()
    assert trashed.is_trashed
    permanently_delete_entry(entry.id)
    with pytest.raises(Exception):
        storage.get_entry(entry.id, include_trashed=True)


@pytest.mark.asyncio
async def test_tui_sidebar_and_filter_summary(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        assert app_ui.query_one("#sidebar") is not None
        assert app_ui.query_one("#filter-summary") is not None
        assert len(app_ui._entries) == 3
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_vim_navigation(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        list_view = app_ui.query_one("#entry-list")
        list_view.index = 0
        await pilot.press("j")
        await pilot.pause()
        assert list_view.index == 1
        await pilot.press("k")
        await pilot.pause()
        assert list_view.index == 0
        await pilot.press("G")
        await pilot.pause()
        assert list_view.index == len(app_ui._entries) - 1
        await pilot.press("g")
        await pilot.pause()
        assert list_view.index == 0
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_cycle_sort_and_kind(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert app_ui.filters.sort in VALID_SORTS
        await pilot.press("K")
        await pilot.pause()
        assert app_ui.filters.kind in (None, *VALID_KINDS)
        await pilot.press("P")
        await pilot.pause()
        assert app_ui.filters.pinned_only is True
        assert all(e.pinned for e in app_ui._entries)
        await pilot.press("hash")
        await pilot.pause()
        assert app_ui.filters.active_count() == 0
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_trash_view_restore(vault_home: Path) -> None:
    _ = vault_home
    target = storage.get_entry(2)
    storage.delete_entry(target.id, permanent=False)

    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        await pilot.pause()
        assert app_ui.filters.trash_mode is True
        assert any(e.id == target.id for e in app_ui._entries)

        for index, entry in enumerate(app_ui._entries):
            if entry.id == target.id:
                app_ui.query_one("#entry-list").index = index
                app_ui.show_entry(entry)
                break
        await pilot.press("u")
        await pilot.pause()
        assert storage.get_entry(target.id).is_trashed is False
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_help_and_stats_overlays(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        app_ui.action_help()
        await pilot.pause()
        assert app_ui.screen.query_one("#help-dialog") is not None
        await pilot.press("escape")
        await pilot.pause()
        app_ui.action_show_stats()
        await pilot.pause()
        assert app_ui.screen.query_one("#stats-dialog") is not None
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_command_palette_runs_refresh(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        app_ui.run_palette_command("refresh")
        await pilot.pause()
        assert len(app_ui._entries) == 3
        app_ui.run_palette_command("toggle-pinned-only")
        await pilot.pause()
        assert app_ui.filters.pinned_only is True
        app_ui.run_palette_command("preset:trash")
        await pilot.pause()
        assert app_ui.filters.trash_mode is True
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_copy_body_status(vault_home: Path) -> None:
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
        await pilot.press("y")
        await pilot.pause()
        status = str(app_ui.query_one("#status").render())
        assert "Copied" in status or "copy" in status.lower() or "entry" in status.lower()
        await pilot.press("q")


@pytest.mark.asyncio
async def test_tui_tag_sidebar_filter(vault_home: Path) -> None:
    _ = vault_home
    app_ui = TermVaultApp()
    async with app_ui.run_test() as pilot:
        await pilot.pause()
        app_ui.filters.set_tag("docker")
        app_ui.reload_all()
        await pilot.pause()
        assert len(app_ui._entries) == 1
        assert app_ui._entries[0].title == "Docker stuck"
        assert "docker" in app_ui.filters.compact_badge()
        app_ui.filters.tag = None
        app_ui.reload_all()
        await pilot.pause()
        assert len(app_ui._entries) == 3
        await pilot.press("q")
