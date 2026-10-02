"""Display helpers for compact, snippet-friendly CLI output."""

from __future__ import annotations

import json
from typing import Any

from termvault.models import Entry, SearchHit, TagCount, VaultStats


def body_snippet(body: str, width: int = 72) -> str:
    """Collapse whitespace and truncate a body for list/search previews."""
    text = " ".join(body.strip().split())
    if not text:
        return ""
    if len(text) <= width:
        return text
    return text[: width - 1].rstrip() + "…"


def format_body_for_show(body: str) -> str:
    """Render an entry body for ``tv show``, preserving code-like indentation."""
    if not body or not body.strip():
        return "(empty body)"

    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def kind_badge(kind: str) -> str:
    return kind.strip().lower() or "note"


def format_entry_summary(entry: Entry, *, show_snippet: bool = True) -> str:
    """Multi-line text summary used by list/recent."""
    pin = " ★" if entry.pinned else ""
    trash = " [trash]" if entry.is_trashed else ""
    lines = [
        f"[{entry.id}]{pin} ({kind_badge(entry.kind)}) {entry.title}{trash}",
        f"  tags: {entry.tags_display()}",
    ]
    if show_snippet:
        preview = body_snippet(entry.body)
        if preview:
            lines.append(f"  {preview}")
    lines.append(f"  updated: {entry.updated_at}")
    return "\n".join(lines)


def format_entry_detail(entry: Entry) -> str:
    """Full text details used by show."""
    pin = "yes" if entry.pinned else "no"
    trash = entry.trashed_at or "-"
    lines = [
        f"ID:      {entry.id}",
        f"Title:   {entry.title}",
        f"Kind:    {entry.kind}",
        f"Pinned:  {pin}",
        f"Tags:    {entry.tags_display()}",
        f"Created: {entry.created_at}",
        f"Updated: {entry.updated_at}",
        f"Trashed: {trash}",
        "",
        format_body_for_show(entry.body),
    ]
    return "\n".join(lines)


def format_search_hit(hit: SearchHit) -> str:
    entry = hit.entry
    pin = " ★" if entry.pinned else ""
    lines = [
        f"[{entry.id}]{pin} ({kind_badge(entry.kind)}) {entry.title}",
        f"  tags: {entry.tags_display()}",
    ]
    snippet = hit.snippet.strip() or body_snippet(entry.body)
    if snippet:
        lines.append(f"  {snippet}")
    return "\n".join(lines)


def format_tag_counts(tags: list[TagCount]) -> str:
    if not tags:
        return 'No tags yet. Add one with: tv add "Title" -t mytag'
    lines: list[str] = []
    for item in tags:
        label = "entry" if item.count == 1 else "entries"
        lines.append(f"{item.name}\t{item.count} {label}")
    return "\n".join(lines)


def format_stats(stats: VaultStats) -> str:
    lines = [
        f"Active:   {stats.active_entries}",
        f"Pinned:   {stats.pinned_entries}",
        f"Trashed:  {stats.trashed_entries}",
        f"Total:    {stats.total_entries}",
        f"Tags:     {stats.tag_count}",
        "Kinds:",
    ]
    if stats.kind_counts:
        for kind, count in sorted(stats.kind_counts.items()):
            lines.append(f"  {kind}: {count}")
    else:
        lines.append("  (none)")
    lines.append("Top tags:")
    if stats.top_tags:
        for tag in stats.top_tags:
            lines.append(f"  {tag.name}: {tag.count}")
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def dumps_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)
