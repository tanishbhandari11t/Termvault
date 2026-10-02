"""Modal screens for Phase 5 Part 1 (new / edit / confirm)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea

from termvault import storage
from termvault.config import VALID_KINDS
from termvault.errors import TermVaultError
from termvault.models import Entry
from termvault.tui.display import confirm_permanent_delete_message, confirm_trash_message
from termvault.tui.drafts import (
    clear_draft,
    edit_draft_path,
    load_draft,
    new_draft_path,
    save_draft,
)
from termvault.tui.validation import FormData, forms_equal, validate_entry_form


def _kind_options() -> list[tuple[str, str]]:
    return [(kind, kind) for kind in VALID_KINDS]


def _selected_kind(select: Select, fallback: str = "note") -> str:
    value = select.value
    if value in (Select.BLANK, None):
        return fallback
    return str(value)


def _read_form(
    *,
    title_id: str,
    body_id: str,
    tags_id: str,
    kind_id: str,
    kind_fallback: str,
    screen: ModalScreen[bool],
) -> tuple[str, str, str, str]:
    title = screen.query_one(f"#{title_id}", Input).value
    body = screen.query_one(f"#{body_id}", TextArea).text
    tags_raw = screen.query_one(f"#{tags_id}", Input).value
    kind = _selected_kind(screen.query_one(f"#{kind_id}", Select), fallback=kind_fallback)
    return title, body, kind, tags_raw


class EditEntryScreen(ModalScreen[bool]):
    """Edit title, kind, tags, and body for an existing entry."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+d", "save_draft_only", "Save draft", show=True),
    ]

    def __init__(self, entry: Entry) -> None:
        super().__init__()
        self.entry = entry
        self._original = FormData(
            title=entry.title,
            body=entry.body,
            kind=entry.kind,
            tags=entry.tags,
        )
        self._draft_path = edit_draft_path(entry.id)

    def compose(self) -> ComposeResult:
        draft = load_draft(self._draft_path)
        initial = draft or self._original
        with Vertical(classes="modal-dialog", id="edit-dialog"):
            yield Label(f"Edit entry [{self.entry.id}]")
            if draft is not None:
                yield Static("Restored unsaved draft from disk.", id="draft-banner")
            yield Input(value=initial.title, id="edit-title", placeholder="Title")
            yield Select(
                _kind_options(),
                value=initial.kind if initial.kind in VALID_KINDS else self.entry.kind,
                id="edit-kind",
                prompt="Kind",
            )
            yield Input(
                value=", ".join(initial.tags),
                id="edit-tags",
                placeholder="Tags (comma-separated)",
            )
            yield TextArea(initial.body, id="edit-body")
            with Horizontal(id="edit-actions"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Save draft", id="draft")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#edit-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "draft":
            self.action_save_draft_only()
        elif event.button.id == "cancel":
            self.action_cancel()

    def _current_form(self) -> FormData | None:
        title, body, kind, tags_raw = _read_form(
            title_id="edit-title",
            body_id="edit-body",
            tags_id="edit-tags",
            kind_id="edit-kind",
            kind_fallback=self.entry.kind,
            screen=self,
        )
        result = validate_entry_form(
            title=title,
            body=body,
            kind=kind,
            tags_raw=tags_raw,
        )
        return result.data if result.ok else None

    def is_dirty(self) -> bool:
        current = self._current_form()
        if current is None:
            # Invalid but changed text still counts as dirty.
            title = self.query_one("#edit-title", Input).value
            body = self.query_one("#edit-body", TextArea).text
            tags = self.query_one("#edit-tags", Input).value
            return bool(title.strip() or body or tags.strip())
        return not forms_equal(current, self._original)

    def action_cancel(self) -> None:
        if self.is_dirty():
            # Keep draft so work is not lost, then close.
            data = self._current_form()
            if data is not None:
                save_draft(self._draft_path, data, meta={"entry_id": self.entry.id})
            self.app.notify("Closed with unsaved changes — draft kept.", severity="warning")
        self.dismiss(False)

    def action_save_draft_only(self) -> None:
        title, body, kind, tags_raw = _read_form(
            title_id="edit-title",
            body_id="edit-body",
            tags_id="edit-tags",
            kind_id="edit-kind",
            kind_fallback=self.entry.kind,
            screen=self,
        )
        result = validate_entry_form(
            title=title or self.entry.title,
            body=body,
            kind=kind,
            tags_raw=tags_raw,
        )
        if not result.ok or result.data is None:
            self.app.notify(result.error or "Invalid draft.", severity="error")
            return
        save_draft(self._draft_path, result.data, meta={"entry_id": self.entry.id})
        self.app.notify("Draft saved.", severity="information")

    def action_save(self) -> None:
        title, body, kind, tags_raw = _read_form(
            title_id="edit-title",
            body_id="edit-body",
            tags_id="edit-tags",
            kind_id="edit-kind",
            kind_fallback=self.entry.kind,
            screen=self,
        )
        result = validate_entry_form(
            title=title,
            body=body,
            kind=kind,
            tags_raw=tags_raw,
        )
        if not result.ok or result.data is None:
            self.app.notify(result.error or "Invalid form.", severity="error")
            return
        data = result.data
        try:
            storage.update_entry(
                self.entry.id,
                title=data.title,
                body=data.body,
                tags=list(data.tags),
                kind=data.kind,
            )
        except TermVaultError as exc:
            self.app.notify(str(exc), severity="error")
            return
        clear_draft(self._draft_path)
        self.dismiss(True)


class NewEntryScreen(ModalScreen[bool]):
    """Create a vault entry with kind + tags from the TUI."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("ctrl+s", "save", "Save", show=True),
        Binding("ctrl+d", "save_draft_only", "Save draft", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._draft_path = new_draft_path()

    def compose(self) -> ComposeResult:
        draft = load_draft(self._draft_path)
        with Vertical(classes="modal-dialog", id="edit-dialog"):
            yield Label("New entry")
            if draft is not None:
                yield Static("Restored unsaved draft from disk.", id="draft-banner")
            yield Input(
                value=draft.title if draft else "",
                placeholder="Title",
                id="new-title",
            )
            yield Select(
                _kind_options(),
                value=(draft.kind if draft and draft.kind in VALID_KINDS else "note"),
                id="new-kind",
                prompt="Kind",
            )
            yield Input(
                value=", ".join(draft.tags) if draft else "",
                placeholder="Tags (comma-separated)",
                id="new-tags",
            )
            yield TextArea(draft.body if draft else "", id="new-body")
            with Horizontal(id="edit-actions"):
                yield Button("Create", variant="primary", id="save")
                yield Button("Save draft", id="draft")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#new-title", Input).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save":
            self.action_save()
        elif event.button.id == "draft":
            self.action_save_draft_only()
        elif event.button.id == "cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        title, body, kind, tags_raw = _read_form(
            title_id="new-title",
            body_id="new-body",
            tags_id="new-tags",
            kind_id="new-kind",
            kind_fallback="note",
            screen=self,
        )
        if title.strip() or body.strip() or tags_raw.strip():
            result = validate_entry_form(
                title=title or "untitled draft",
                body=body,
                kind=kind,
                tags_raw=tags_raw,
            )
            if result.ok and result.data is not None:
                # Preserve typed title even if we had to stub for validation.
                data = FormData(
                    title=title.strip(),
                    body=result.data.body,
                    kind=result.data.kind,
                    tags=result.data.tags,
                )
                save_draft(self._draft_path, data)
                self.app.notify("Draft saved.", severity="information")
        self.dismiss(False)

    def action_save_draft_only(self) -> None:
        title, body, kind, tags_raw = _read_form(
            title_id="new-title",
            body_id="new-body",
            tags_id="new-tags",
            kind_id="new-kind",
            kind_fallback="note",
            screen=self,
        )
        result = validate_entry_form(
            title=title or "untitled draft",
            body=body,
            kind=kind,
            tags_raw=tags_raw,
        )
        if not result.ok or result.data is None:
            self.app.notify(result.error or "Invalid draft.", severity="error")
            return
        data = FormData(
            title=title.strip(),
            body=result.data.body,
            kind=result.data.kind,
            tags=result.data.tags,
        )
        save_draft(self._draft_path, data)
        self.app.notify("Draft saved.", severity="information")

    def action_save(self) -> None:
        title, body, kind, tags_raw = _read_form(
            title_id="new-title",
            body_id="new-body",
            tags_id="new-tags",
            kind_id="new-kind",
            kind_fallback="note",
            screen=self,
        )
        result = validate_entry_form(
            title=title,
            body=body,
            kind=kind,
            tags_raw=tags_raw,
        )
        if not result.ok or result.data is None:
            self.app.notify(result.error or "Invalid form.", severity="error")
            return
        data = result.data
        try:
            storage.add_entry(
                title=data.title,
                body=data.body,
                tags=list(data.tags) or None,
                kind=data.kind,
            )
        except TermVaultError as exc:
            self.app.notify(str(exc), severity="error")
            return
        clear_draft(self._draft_path)
        self.dismiss(True)


class ConfirmScreen(ModalScreen[bool]):
    """Yes/no confirmation used before trashing an entry."""

    BINDINGS = [
        Binding("y", "yes", "Yes", show=False),
        Binding("n", "no", "No", show=False),
        Binding("escape", "no", "No", show=False),
    ]

    def __init__(self, entry: Entry, *, permanent: bool = False) -> None:
        super().__init__()
        self.entry = entry
        self.permanent = permanent
        self.message = (
            confirm_permanent_delete_message(entry)
            if permanent
            else confirm_trash_message(entry)
        )

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-dialog", id="confirm-dialog"):
            yield Static(self.message, id="confirm-message")
            with Horizontal(id="edit-actions"):
                yield Button(
                    "Yes, delete" if self.permanent else "Yes, trash",
                    variant="error",
                    id="yes",
                )
                yield Button("No", id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)
