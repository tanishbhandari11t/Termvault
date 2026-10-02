"""Display helpers specific to the Phase 5 Part 1 TUI."""

from __future__ import annotations

from termvault.formatting import body_snippet, format_body_for_show
from termvault.models import Entry


def list_label(entry: Entry, *, width_hint: int = 60) -> str:
    """Compact left-list label with pin + kind + truncated title."""
    pin = "★" if entry.pinned else "·"
    trash = " ⌫" if entry.is_trashed else ""
    title = entry.title.strip() or "(untitled)"
    if len(title) > width_hint:
        title = title[: width_hint - 1].rstrip() + "…"
    return f"{pin} [{entry.id}] ({entry.kind}){trash} {title}"


def detail_title(entry: Entry) -> str:
    pin = " ★" if entry.pinned else ""
    return f"[{entry.id}]{pin} {entry.title}"


def detail_meta(entry: Entry) -> str:
    """Multi-line metadata block for the detail pane."""
    lines = [
        f"Kind:     {entry.kind}",
        f"Pinned:   {'yes' if entry.pinned else 'no'}",
        f"Tags:     {entry.tags_display()}",
        f"Created:  {entry.created_at}",
        f"Updated:  {entry.updated_at}",
    ]
    if entry.is_trashed:
        lines.append(f"Trashed:  {entry.trashed_at or 'yes'}")
    if entry.body.strip():
        preview = body_snippet(entry.body, width=88)
        if preview:
            lines.append(f"Preview:  {preview}")
    return "\n".join(lines)


def detail_body(entry: Entry) -> str:
    return format_body_for_show(entry.body)


def confirm_trash_message(entry: Entry) -> str:
    tags = entry.tags_display()
    return (
        f"Move [{entry.id}] {entry.title} to trash?\n"
        f"Kind: {entry.kind}  |  Tags: {tags}\n\n"
        "This soft-deletes the entry (recoverable via CLI: tv restore)."
    )


def confirm_permanent_delete_message(entry: Entry) -> str:
    tags = entry.tags_display()
    return (
        f"Permanently delete [{entry.id}] {entry.title}?\n"
        f"Kind: {entry.kind}  |  Tags: {tags}\n\n"
        "This cannot be undone."
    )


def status_with_query(base: str, query: str) -> str:
    if not query:
        return base
    return f"{base}  ·  filter: {query!r}"
