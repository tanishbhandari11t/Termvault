"""Markdown codec for TermVault export documents.

Supports:
- A single ``.md`` file with one or more entries separated by a blank line + ``---``
- Each entry uses YAML-like frontmatter (subset) + body
- A directory of ``.md`` files
"""

from __future__ import annotations

import re
from pathlib import Path

from termvault.portability.constants import (
    MD_ENTRY_SEPARATOR,
    MD_FRONTMATTER_DELIM,
    MD_INDEX_FILENAME,
)
from termvault.portability.errors import ImportValidationError
from termvault.portability.paths import list_markdown_files, read_text_file
from termvault.portability.schema import ExportDocument, ExportEntry, utc_now_iso

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z",
    re.DOTALL,
)
_ENTRY_SPLIT_RE = re.compile(r"\n(?:[ \t]*\n)?---\n(?=---\n|\#)", re.MULTILINE)


def dumps_export_markdown(document: ExportDocument) -> str:
    """Serialize an export document to a multi-entry markdown file."""
    header_lines = [
        f"<!-- termvault-export version={document.version} -->",
        f"<!-- exported_at: {document.exported_at} -->",
        f"<!-- termvault_version: {document.termvault_version} -->",
        f"<!-- entry_count: {len(document.entries)} -->",
        "",
    ]
    if not document.entries:
        return "\n".join(header_lines) + "_No entries._\n"
    chunks = [render_entry_markdown(entry) for entry in document.entries]
    return "\n".join(header_lines) + MD_ENTRY_SEPARATOR.join(chunks)


def render_entry_markdown(entry: ExportEntry) -> str:
    lines = [
        MD_FRONTMATTER_DELIM,
        f"title: {_yaml_quote(entry.title)}",
        f"kind: {entry.kind}",
        f"pinned: {'true' if entry.pinned else 'false'}",
        f"trashed: {'true' if entry.trashed else 'false'}",
        f"tags: [{', '.join(_yaml_quote(tag) for tag in entry.tags)}]",
    ]
    if entry.source_id is not None:
        lines.append(f"source_id: {entry.source_id}")
    if entry.created_at:
        lines.append(f"created_at: {entry.created_at}")
    if entry.updated_at:
        lines.append(f"updated_at: {entry.updated_at}")
    if entry.content_hash:
        lines.append(f"content_hash: {entry.content_hash}")
    lines.append(MD_FRONTMATTER_DELIM)
    lines.append("")
    body = entry.body.rstrip()
    lines.append(body + ("\n" if body else ""))
    return "\n".join(lines)


def loads_export_markdown(text: str) -> ExportDocument:
    """Parse a markdown export (single or multi-entry) into a document."""
    cleaned = _strip_html_comments(text).strip()
    if not cleaned or cleaned == "_No entries._":
        return ExportDocument(entries=[], exported_at=utc_now_iso())

    parts = _split_markdown_entries(cleaned)
    entries = [
        parse_entry_markdown(part, path=f"markdown[{i}]")
        for i, part in enumerate(parts)
    ]
    return ExportDocument(entries=entries, codec_hint="markdown")


def loads_export_markdown_path(path: Path) -> ExportDocument:
    """Load markdown from a file or a directory of markdown files."""
    if path.is_dir():
        files = list_markdown_files(path)
        entries: list[ExportEntry] = []
        for file_path in files:
            if file_path.name == MD_INDEX_FILENAME:
                continue
            text = read_text_file(file_path)
            doc = loads_export_markdown(text)
            entries.extend(doc.entries)
        return ExportDocument(entries=entries, codec_hint="markdown")
    return loads_export_markdown(read_text_file(path))


def parse_entry_markdown(text: str, *, path: str = "markdown") -> ExportEntry:
    text = text.strip()
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return _parse_bare_markdown(text, path=path)

    meta_raw, body = match.group(1), match.group(2)
    meta = parse_simple_frontmatter(meta_raw, path=f"{path}.frontmatter")
    title = meta.get("title")
    if not title:
        raise ImportValidationError("frontmatter title is required.", path=path)
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return ExportEntry.from_dict(
        {
            "title": title,
            "body": body.strip("\n"),
            "tags": tags,
            "kind": meta.get("kind", "note"),
            "pinned": _as_bool(meta.get("pinned", False)),
            "trashed": _as_bool(meta.get("trashed", False)),
            "source_id": meta.get("source_id"),
            "created_at": meta.get("created_at"),
            "updated_at": meta.get("updated_at"),
            "content_hash": meta.get("content_hash"),
        },
        path=path,
    )


def parse_simple_frontmatter(text: str, *, path: str) -> dict:
    """Parse a tiny YAML-like subset: ``key: value``, ``tags: [a, b]``."""
    result: dict = {}
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            raise ImportValidationError(
                f"Invalid frontmatter line: {stripped!r}",
                path=f"{path}:{line_no}",
            )
        key, raw_value = stripped.split(":", 1)
        result[key.strip()] = _parse_frontmatter_value(raw_value.strip())
    return result


def _parse_frontmatter_value(raw: str):
    if raw.lower() in {"true", "yes"}:
        return True
    if raw.lower() in {"false", "no"}:
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        parts = [
            _unquote(part.strip())
            for part in _split_csv_respecting_quotes(inner)
        ]
        return [part for part in parts if part]
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    return _unquote(raw)


def _split_csv_respecting_quotes(text: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    quote_char = ""
    for ch in text:
        if ch in {'"', "'"}:
            if not in_quote:
                in_quote = True
                quote_char = ch
                continue
            if ch == quote_char:
                in_quote = False
                quote_char = ""
                continue
        if ch == "," and not in_quote:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    parts.append("".join(current).strip())
    return parts


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1"}
    return bool(value)


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _split_markdown_entries(text: str) -> list[str]:
    """Split multi-entry markdown on ``\\n---\\n`` when the next block starts a new entry."""
    if MD_ENTRY_SEPARATOR in text:
        # Primary path used by our own serializer.
        parts = [part.strip() for part in text.split(MD_ENTRY_SEPARATOR)]
        return [part for part in parts if part]

    # Fallback: split before a new frontmatter block that follows a closed one.
    parts = _ENTRY_SPLIT_RE.split(text)
    cleaned = [part.strip() for part in parts if part.strip()]
    return cleaned or [text]


def _parse_bare_markdown(text: str, *, path: str) -> ExportEntry:
    lines = text.splitlines()
    title = "Untitled"
    body_lines = lines
    if lines and lines[0].lstrip().startswith("#"):
        title = lines[0].lstrip("#").strip() or "Untitled"
        body_lines = lines[1:]
        if body_lines and not body_lines[0].strip():
            body_lines = body_lines[1:]
    body = "\n".join(body_lines).strip("\n")
    return ExportEntry.from_dict({"title": title, "body": body}, path=path)
