"""TermVault TUI app — Phase 5 Part 1 core + Part 2 advanced chrome."""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, ListView, Static

from termvault import __version__, storage
from termvault.errors import TermVaultError
from termvault.tui.actions_advanced import (
    load_sidebar_tags,
    load_vault_stats,
    permanently_delete_entry,
    restore_entry,
    safe_load_filtered_entries,
)
from termvault.tui.browser import (
    BrowseSession,
    find_entry,
    format_status_count,
    next_index_after_reload,
)
from termvault.tui.clipboard_util import (
    CopyMode,
    format_copy_status_from_payload,
    resolve_clipboard_payload,
)
from termvault.tui.constants import SEARCH_PLACEHOLDER, STATUS_READY
from termvault.tui.display import status_with_query
from termvault.tui.filter_presets import apply_filter_preset
from termvault.tui.filters import AdvancedFilters
from termvault.tui.navigation import bottom_index, move_index, top_index
from termvault.tui.screens import ConfirmScreen, EditEntryScreen, NewEntryScreen
from termvault.tui.screens_advanced import (
    CommandPaletteScreen,
    HelpScreen,
    StatsScreen,
)
from termvault.tui.search import SearchController
from termvault.tui.widgets import (
    AllTagsItem,
    DetailPane,
    EntryListItem,
    FilterSummary,
    ShortcutHints,
    TagListItem,
    TagSidebar,
)

_STYLE_PATH = Path(__file__).with_name("styles.tcss")


class TermVaultApp(App[None]):
    """TermVault browser with Part 1 core + Part 2 advanced features.

    Part 2 (~5 hours of manual implementation work):
    - tag sidebar filtering
    - command palette
    - help + stats overlays
    - vim navigation
    - sort / kind / pinned / trash-view cycles
    - restore + copy-to-clipboard
    """

    TITLE = "TermVault"
    SUB_TITLE = f"v{__version__} · Phase 5 Part 1+2"
    CSS_PATH = _STYLE_PATH

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("n", "new_entry", "New"),
        Binding("e", "edit_entry", "Edit"),
        Binding("p", "toggle_pin", "Pin"),
        Binding("d", "trash_or_delete", "Trash"),
        Binding("u", "restore_entry", "Restore"),
        Binding("y", "copy_body", "Copy"),
        Binding("s", "show_stats", "Stats"),
        Binding("o", "cycle_sort", "Sort"),
        Binding("K", "cycle_kind", "Kind"),
        Binding("t", "toggle_trash", "Trash view"),
        Binding("P", "toggle_pinned_only", "Pinned"),
        Binding("hash", "clear_filters", "Clear", key_display="#"),
        Binding("question_mark", "help", "Help"),
        Binding("colon", "command_palette", "Palette", key_display=":"),
        Binding("ctrl+p", "command_palette", "Palette", show=False),
        Binding("/", "focus_search", "Search"),
        Binding("escape", "escape", "Esc", show=False),
        Binding("l", "focus_list", "List", show=False),
        Binding("b", "focus_sidebar", "Tags", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.session = BrowseSession()
        self.search = SearchController()
        self.filters = AdvancedFilters()

    @property
    def _entries(self):
        return self.session.entries

    @_entries.setter
    def _entries(self, value) -> None:
        self.session.entries = value

    @property
    def _query(self) -> str:
        return self.search.query

    @_query.setter
    def _query(self, value: str) -> None:
        self.search.set_query(value)

    @property
    def _selected_id(self) -> int | None:
        return self.session.selected_id

    @_selected_id.setter
    def _selected_id(self, value: int | None) -> None:
        self.session.selected_id = value

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical(id="top-bar"):
            with Horizontal(id="search-row"):
                yield Input(placeholder=SEARCH_PLACEHOLDER, id="search")
                yield FilterSummary()
            yield ShortcutHints()
        with Horizontal(id="body-row"):
            yield TagSidebar(id="sidebar")
            with Horizontal(id="main"):
                yield ListView(id="entry-list")
                yield DetailPane(id="detail-pane")
        yield Static(STATUS_READY, id="status")
        yield Footer()

    def on_mount(self) -> None:
        self.reload_all()
        self.query_one("#entry-list", ListView).focus()

    def set_status(self, message: str) -> None:
        base = status_with_query(message, self.search.query)
        if self.filters.active_count():
            base = f"{base}  ·  {self.filters.summary()}"
        self.query_one("#status", Static).update(base)
        self.query_one("#filter-summary", FilterSummary).set_summary(
            self.filters.compact_badge()
        )

    def reload_tags(self) -> None:
        tags = load_sidebar_tags()
        self.query_one("#sidebar", TagSidebar).reload(tags, self.filters.tag)

    def reload_entries(self) -> None:
        entries, error = safe_load_filtered_entries(
            query=self.search.query,
            filters=self.filters,
        )
        self.session.entries = entries
        self.session.last_error = error

        list_view = self.query_one("#entry-list", ListView)
        list_view.clear()
        for entry in entries:
            list_view.append(EntryListItem(entry))

        detail = self.query_one("#detail-pane", DetailPane)
        if error:
            detail.show_empty(f"Error loading vault:\n{error}")
            self.set_status(f"Error: {error}")
            return

        if not entries:
            self.session.selected_id = None
            tip = "Trash is empty." if self.filters.trash_mode else None
            detail.show_empty(tip)
            self.set_status(format_status_count(0))
            return

        index = next_index_after_reload(entries, self.session.selected_id)
        list_view.index = index
        self.show_entry(entries[index])
        self.set_status(format_status_count(len(entries)))

    def reload_all(self) -> None:
        self.reload_tags()
        self.reload_entries()

    def show_entry(self, entry) -> None:
        self.session.selected_id = entry.id
        self.session.remember_opened(entry.id)
        self.query_one("#detail-pane", DetailPane).show_entry(entry)

    def selected_entry(self):
        list_view = self.query_one("#entry-list", ListView)
        if list_view.index is None or not self.session.entries:
            return None
        if list_view.index < 0 or list_view.index >= len(self.session.entries):
            return None
        return self.session.entries[list_view.index]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if event.list_view.id != "entry-list":
            return
        item = event.item
        if isinstance(item, EntryListItem):
            found = find_entry(self.session.entries, item.entry_id)
            if found is not None:
                self.show_entry(found)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id == "tag-list":
            item = event.item
            if isinstance(item, AllTagsItem):
                self.filters.tag = None
            elif isinstance(item, TagListItem):
                self.filters.tag = item.tag_name
            self.reload_all()
            self.action_focus_list()
            self.set_status(
                f"Tag filter: {self.filters.tag}"
                if self.filters.tag
                else "Tag filter cleared"
            )
            return

        item = event.item
        if isinstance(item, EntryListItem):
            found = find_entry(self.session.entries, item.entry_id)
            if found is not None:
                self.show_entry(found)
                self.set_status(f"Opened entry {found.id}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search":
            self.search.set_query(event.value)
            self.reload_entries()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search":
            self.search.commit_pending()
            self.reload_entries()
            self.action_focus_list()
            if self.search.query:
                self.set_status(
                    f"Search committed ({len(self.search.history)} in history)"
                )

    def action_refresh(self) -> None:
        self.reload_all()
        self.set_status("Refreshed.")

    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_focus_list(self) -> None:
        self.query_one("#entry-list", ListView).focus()

    def action_focus_sidebar(self) -> None:
        self.query_one("#tag-list", ListView).focus()

    def action_escape(self) -> None:
        search = self.query_one("#search", Input)
        if search.has_focus and search.value:
            search.value = ""
            self.search.clear()
            self.reload_entries()
            self.set_status("Search cleared.")
            return
        self.action_focus_list()

    def action_clear_search(self) -> None:
        self.action_escape()

    def action_clear_filters(self) -> None:
        self.filters.clear()
        self.query_one("#search", Input).value = ""
        self.search.clear()
        self.reload_all()
        self.set_status("Filters cleared.")

    def action_cycle_sort(self) -> None:
        sort = self.filters.cycle_sort()
        self.reload_entries()
        self.set_status(f"Sort: {sort}")

    def action_cycle_kind(self) -> None:
        kind = self.filters.cycle_kind()
        self.reload_entries()
        self.set_status(f"Kind filter: {kind or 'all'}")

    def action_toggle_trash(self) -> None:
        mode = "trash" if self.filters.toggle_trash() else "active"
        self.reload_entries()
        self.set_status(f"Viewing {mode} entries.")

    def action_toggle_pinned_only(self) -> None:
        only = self.filters.toggle_pinned_only()
        self.reload_entries()
        self.set_status("Pinned only." if only else "Showing all pins.")

    def action_cursor_down(self) -> None:
        list_view = self.query_one("#entry-list", ListView)
        list_view.index = move_index(
            list_view.index,
            delta=1,
            size=len(self.session.entries),
        )

    def action_cursor_up(self) -> None:
        list_view = self.query_one("#entry-list", ListView)
        list_view.index = move_index(
            list_view.index,
            delta=-1,
            size=len(self.session.entries),
        )

    def action_cursor_top(self) -> None:
        list_view = self.query_one("#entry-list", ListView)
        list_view.index = top_index(len(self.session.entries))

    def action_cursor_bottom(self) -> None:
        list_view = self.query_one("#entry-list", ListView)
        list_view.index = bottom_index(len(self.session.entries))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_show_stats(self) -> None:
        stats = load_vault_stats()
        if stats is None:
            self.set_status("Unable to load stats.")
            return
        self.push_screen(StatsScreen(stats))

    def action_command_palette(self) -> None:
        def _done(command: str | None) -> None:
            if command:
                self.run_palette_command(command)

        self.push_screen(CommandPaletteScreen(), _done)

    def run_palette_command(self, command: str) -> None:
        mapping = {
            "refresh": self.action_refresh,
            "new": self.action_new_entry,
            "edit": self.action_edit_entry,
            "pin": self.action_toggle_pin,
            "trash": self.action_trash_or_delete,
            "restore": self.action_restore_entry,
            "copy": self.action_copy_body,
            "copy-title": self.action_copy_title,
            "copy-meta": self.action_copy_meta,
            "toggle-trash-view": self.action_toggle_trash,
            "toggle-pinned-only": self.action_toggle_pinned_only,
            "cycle-sort": self.action_cycle_sort,
            "cycle-kind": self.action_cycle_kind,
            "clear-filters": self.action_clear_filters,
            "stats": self.action_show_stats,
            "help": self.action_help,
            "focus-search": self.action_focus_search,
            "focus-list": self.action_focus_list,
            "focus-sidebar": self.action_focus_sidebar,
            "quit": self.action_quit,
        }
        if command.startswith("preset:"):
            preset_id = command.removeprefix("preset:")
            if apply_filter_preset(self.filters, preset_id):
                self.reload_all()
                self.set_status(f"Preset: {preset_id}")
            else:
                self.set_status(f"Unknown preset: {preset_id}")
            return
        action = mapping.get(command)
        if action is None:
            self.set_status(f"Unknown command: {command}")
            return
        action()

    def _copy_selected(self, mode: CopyMode) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.set_status("No entry selected.")
            return
        payload = resolve_clipboard_payload(entry, mode)
        self.copy_to_clipboard(payload.text)
        self.set_status(format_copy_status_from_payload(entry, payload))

    def action_copy_body(self) -> None:
        self._copy_selected(CopyMode.AUTO)

    def action_copy_title(self) -> None:
        self._copy_selected(CopyMode.TITLE)

    def action_copy_meta(self) -> None:
        self._copy_selected(CopyMode.META)

    def action_new_entry(self) -> None:
        def _done(saved: bool | None) -> None:
            if saved:
                self.reload_all()
                self.set_status("Created entry.")

        self.push_screen(NewEntryScreen(), _done)

    def action_edit_entry(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.set_status("No entry selected.")
            return
        if entry.is_trashed:
            self.set_status("Restore the entry before editing.")
            return

        def _done(saved: bool | None) -> None:
            if saved:
                self.reload_all()
                self.set_status(f"Updated entry {entry.id}.")

        self.push_screen(EditEntryScreen(entry), _done)

    def action_toggle_pin(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.set_status("No entry selected.")
            return
        if entry.is_trashed:
            self.set_status("Cannot pin a trashed entry.")
            return
        try:
            updated = storage.set_pinned(entry.id, not entry.pinned)
        except TermVaultError as exc:
            self.set_status(f"Error: {exc}")
            return
        self.reload_all()
        state = "Pinned" if updated.pinned else "Unpinned"
        self.set_status(f"{state} entry {updated.id}.")

    def action_trash_or_delete(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.set_status("No entry selected.")
            return

        permanent = self.filters.trash_mode or entry.is_trashed

        def _done(confirmed: bool | None) -> None:
            if not confirmed:
                self.set_status("Cancelled.")
                return
            try:
                if permanent:
                    permanently_delete_entry(entry.id)
                else:
                    storage.delete_entry(entry.id, permanent=False)
            except TermVaultError as exc:
                self.set_status(f"Error: {exc}")
                return
            self.reload_all()
            verb = "Deleted" if permanent else "Trashed"
            self.set_status(f"{verb} entry {entry.id}.")

        self.push_screen(ConfirmScreen(entry, permanent=permanent), _done)

    # Back-compat alias used by Part 1 tests / muscle memory.
    def action_trash_entry(self) -> None:
        self.action_trash_or_delete()

    def action_restore_entry(self) -> None:
        entry = self.selected_entry()
        if entry is None:
            self.set_status("No entry selected.")
            return
        if not entry.is_trashed and not self.filters.trash_mode:
            self.set_status("Switch to trash view (t) to restore.")
            return
        try:
            restored = restore_entry(entry.id)
        except TermVaultError as exc:
            self.set_status(f"Error: {exc}")
            return
        self.reload_all()
        self.set_status(f"Restored entry {restored.id}.")


def run_tui() -> None:
    """Launch the TermVault Textual application (Part 1 + Part 2)."""
    TermVaultApp().run()
