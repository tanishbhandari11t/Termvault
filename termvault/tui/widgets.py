"""Reusable widgets for Phase 5 Part 1 + Part 2 sidebar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import ListItem, ListView, Static

from termvault.models import Entry, TagCount
from termvault.tui.constants import EMPTY_LIST_HINT
from termvault.tui.display import detail_body, detail_meta, detail_title, list_label
from termvault.tui.helptext import STATUS_HINTS_PART2


class EntryListItem(ListItem):
    """List row that remembers which vault entry it represents."""

    def __init__(self, entry: Entry) -> None:
        classes = "entry-row pinned" if entry.pinned else "entry-row"
        if entry.is_trashed:
            classes += " trashed"
        super().__init__(Static(list_label(entry), classes=classes))
        self.entry_id = entry.id
        self.entry_title = entry.title
        self.entry_kind = entry.kind


class TagListItem(ListItem):
    """Sidebar row for a vault tag."""

    def __init__(self, tag: TagCount, *, active: bool = False) -> None:
        classes = "tag-row active" if active else "tag-row"
        super().__init__(Static(f"{tag.name} ({tag.count})", classes=classes))
        self.tag_name = tag.name


class AllTagsItem(ListItem):
    """Sidebar row that clears the tag filter."""

    def __init__(self, *, active: bool = False) -> None:
        classes = "tag-row active" if active else "tag-row"
        super().__init__(Static("All tags", classes=classes))
        self.tag_name: str | None = None


class TagSidebar(Vertical):
    """Left sidebar listing vault tags."""

    def compose(self) -> ComposeResult:
        yield Static("Tags", id="sidebar-title")
        yield ListView(id="tag-list")

    def reload(self, tags: list[TagCount], active_tag: str | None) -> None:
        tag_list = self.query_one("#tag-list", ListView)
        tag_list.clear()
        tag_list.append(AllTagsItem(active=active_tag is None))
        for tag in tags:
            tag_list.append(TagListItem(tag, active=active_tag == tag.name))


class DetailPane(Vertical):
    """Right-hand detail view for the selected entry."""

    def compose(self) -> ComposeResult:
        yield Static("Select an entry", id="detail-title")
        yield Static("", id="detail-meta")
        with VerticalScroll(id="detail-body-scroll"):
            yield Static("", id="detail-body")

    def show_empty(self, message: str | None = None) -> None:
        """Render an empty-state message in the detail pane."""
        self.query_one("#detail-title", Static).update("No entries")
        self.query_one("#detail-meta", Static).update("")
        self.query_one("#detail-body", Static).update(message or EMPTY_LIST_HINT)

    def show_entry(self, entry: Entry) -> None:
        """Render full metadata + body for one entry."""
        self.query_one("#detail-title", Static).update(detail_title(entry))
        self.query_one("#detail-meta", Static).update(detail_meta(entry))
        self.query_one("#detail-body", Static).update(detail_body(entry))


class ShortcutHints(Static):
    """Persistent shortcut reminder under the search box."""

    def __init__(self) -> None:
        super().__init__(STATUS_HINTS_PART2, id="shortcut-hints", markup=True)


class FilterSummary(Static):
    """Shows active Part 2 filters next to search."""

    def __init__(self) -> None:
        super().__init__("", id="filter-summary", markup=False)

    def set_summary(self, text: str) -> None:
        self.update(text)
