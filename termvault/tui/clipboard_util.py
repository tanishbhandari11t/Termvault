"""Clipboard helpers for Phase 5 Part 2.

Textual's App.copy_to_clipboard handles the OS write. These helpers decide
*what* to copy and how to describe the result in the status bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from termvault.models import Entry


class CopyMode(str, Enum):
    """What payload the user asked to yank."""

    BODY = "body"
    TITLE = "title"
    ID = "id"
    META = "meta"
    AUTO = "auto"


@dataclass(frozen=True)
class ClipboardPayload:
    """Resolved clipboard text plus a short label for status feedback."""

    text: str
    label: str
    mode: CopyMode

    @property
    def chars(self) -> int:
        return len(self.text)


def body_for_clipboard(entry: Entry) -> str:
    """Choose the best clipboard payload for an entry (auto mode)."""
    return resolve_clipboard_payload(entry, CopyMode.AUTO).text


def resolve_clipboard_payload(entry: Entry, mode: CopyMode = CopyMode.AUTO) -> ClipboardPayload:
    """Build a clipboard payload for the requested mode."""
    if mode is CopyMode.TITLE:
        return ClipboardPayload(entry.title, "title", CopyMode.TITLE)
    if mode is CopyMode.ID:
        return ClipboardPayload(str(entry.id), "id", CopyMode.ID)
    if mode is CopyMode.META:
        text = format_entry_meta_block(entry)
        return ClipboardPayload(text, "meta", CopyMode.META)
    if mode is CopyMode.BODY:
        body = entry.body if entry.body.strip() else entry.title
        label = "body" if entry.body.strip() else "title"
        return ClipboardPayload(body, label, CopyMode.BODY)

    # AUTO: prefer body, fall back to title.
    if entry.body.strip():
        return ClipboardPayload(entry.body, "body", CopyMode.AUTO)
    return ClipboardPayload(entry.title, "title", CopyMode.AUTO)


def format_entry_meta_block(entry: Entry) -> str:
    """Plain-text metadata block suitable for pasting into chat / tickets."""
    lines = [
        f"id: {entry.id}",
        f"title: {entry.title}",
        f"kind: {entry.kind}",
        f"pinned: {'yes' if entry.pinned else 'no'}",
        f"tags: {entry.tags_display()}",
        f"created: {entry.created_at}",
        f"updated: {entry.updated_at}",
    ]
    if entry.is_trashed:
        lines.append(f"trashed: {entry.trashed_at}")
    return "\n".join(lines)


def format_copy_status(entry: Entry, *, chars: int, label: str | None = None) -> str:
    resolved = label or ("body" if entry.body.strip() else "title")
    return f"Copied {resolved} of entry {entry.id} ({chars} chars)."


def format_copy_status_from_payload(entry: Entry, payload: ClipboardPayload) -> str:
    return format_copy_status(entry, chars=payload.chars, label=payload.label)


def truncate_for_preview(text: str, *, width: int = 48) -> str:
    """Single-line preview used when confirming a yank in the status bar."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= width:
        return cleaned
    return cleaned[: width - 1].rstrip() + "…"
