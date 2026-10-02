"""Phase 5 Part 2 overlay screens: help, stats, command palette."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView, Static

from termvault.formatting import format_stats
from termvault.models import VaultStats
from termvault.tui.helptext import HELP_TEXT, format_help_sections
from termvault.tui.palette import PaletteCommand, filter_palette_commands


class PaletteItem(ListItem):
    """Command palette row carrying a command id."""

    def __init__(self, command: PaletteCommand) -> None:
        super().__init__(Static(command.display_label()))
        self.command_id = command.id
        self.command_title = command.title


class HelpScreen(ModalScreen[None]):
    """Keyboard reference overlay."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("question_mark", "close", "Close", show=False),
    ]

    def __init__(self, *, compact: bool = False) -> None:
        super().__init__()
        self.compact = compact

    def compose(self) -> ComposeResult:
        body = format_help_sections() if self.compact else HELP_TEXT
        with Vertical(classes="modal-dialog", id="help-dialog"):
            yield Label("Help · Phase 5 Part 2")
            with VerticalScroll(id="help-body"):
                yield Static(body, id="help-text")
            with Horizontal(id="edit-actions"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)


class StatsScreen(ModalScreen[None]):
    """Vault statistics overlay."""

    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("q", "close", "Close"),
        Binding("s", "close", "Close", show=False),
    ]

    def __init__(self, stats: VaultStats) -> None:
        super().__init__()
        self.stats = stats

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-dialog", id="stats-dialog"):
            yield Label("Vault stats")
            with VerticalScroll(id="stats-body"):
                yield Static(format_stats(self.stats), id="stats-text")
            with Horizontal(id="edit-actions"):
                yield Button("Close", variant="primary", id="close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "close":
            self.action_close()

    def action_close(self) -> None:
        self.dismiss(None)


class CommandPaletteScreen(ModalScreen[str | None]):
    """Filterable command launcher."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("down", "focus_list", "List", show=False),
        Binding("ctrl+n", "focus_list", "List", show=False),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-dialog", id="palette-dialog"):
            yield Label("Command palette")
            yield Input(
                placeholder="Filter commands… (multi-word ok)",
                id="palette-filter",
            )
            yield Static("", id="palette-empty")
            yield ListView(id="palette-list")
            with Horizontal(id="edit-actions"):
                yield Button("Run", variant="primary", id="run")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self._populate("")
        self.query_one("#palette-filter", Input).focus()

    def _populate(self, needle: str) -> None:
        list_view = self.query_one("#palette-list", ListView)
        empty = self.query_one("#palette-empty", Static)
        list_view.clear()
        commands = filter_palette_commands(needle)
        for command in commands:
            list_view.append(PaletteItem(command))
        if commands:
            list_view.index = 0
            empty.update("")
            list_view.display = True
        else:
            empty.update("No commands match that filter.")
            list_view.display = False

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "palette-filter":
            self._populate(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "palette-filter":
            self.action_run()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        _ = event
        self.action_run()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run":
            self.action_run()
        elif event.button.id == "cancel":
            self.action_cancel()

    def action_focus_list(self) -> None:
        list_view = self.query_one("#palette-list", ListView)
        if list_view.display:
            list_view.focus()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_run(self) -> None:
        list_view = self.query_one("#palette-list", ListView)
        if not list_view.display or list_view.index is None or not list_view.children:
            self.dismiss(None)
            return
        item = list_view.children[list_view.index]
        if isinstance(item, PaletteItem):
            self.dismiss(item.command_id)
            return
        self.dismiss(None)
