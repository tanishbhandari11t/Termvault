"""System clipboard helpers for the CLI (``tv copy``)."""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from termvault.errors import TermVaultError
from termvault.models import Entry

CLIPBOARD_ENV = "TERMVAULT_CLIPBOARD_CMD"
COPY_FIELDS = ("body", "title", "meta", "json", "markdown")


class ClipboardUnavailableError(TermVaultError):
    """Raised when no system clipboard command is available or it fails."""


@dataclass(frozen=True)
class ClipboardBackend:
    name: str
    command: tuple[str, ...]
    encoding: str = "utf-8"


def candidate_backends(system: str | None = None) -> list[ClipboardBackend]:
    """Clipboard commands to try, in preference order, for an OS."""
    system = (system or platform.system()).lower()
    if system == "windows":
        # clip.exe treats BOM-prefixed UTF-16 input as Unicode text.
        return [ClipboardBackend("clip", ("clip",), encoding="utf-16")]
    if system == "darwin":
        return [ClipboardBackend("pbcopy", ("pbcopy",))]
    return [
        ClipboardBackend("wl-copy", ("wl-copy",)),
        ClipboardBackend("xclip", ("xclip", "-selection", "clipboard")),
        ClipboardBackend("xsel", ("xsel", "--clipboard", "--input")),
    ]


def detect_backend(
    system: str | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
) -> ClipboardBackend | None:
    override = os.environ.get(CLIPBOARD_ENV, "").strip()
    if override:
        parts = shlex.split(override, posix=os.name != "nt")
        if parts:
            return ClipboardBackend("custom", tuple(parts))
    for backend in candidate_backends(system):
        if which(backend.command[0]):
            return backend
    return None


def copy_text(text: str, *, backend: ClipboardBackend | None = None) -> ClipboardBackend:
    """Send text to the system clipboard; returns the backend used."""
    chosen = backend or detect_backend()
    if chosen is None:
        raise ClipboardUnavailableError(
            "No clipboard command found (install wl-copy, xclip, or xsel, "
            f"or set {CLIPBOARD_ENV}). Use --print to write to stdout instead."
        )
    try:
        subprocess.run(
            list(chosen.command),
            input=text.encode(chosen.encoding),
            check=True,
            timeout=10,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ClipboardUnavailableError(
            f"Clipboard command {chosen.name!r} failed: {exc}"
        ) from exc
    return chosen


def entry_clip_text(entry: Entry, field: str = "body") -> str:
    """Render the part of an entry the user wants to paste somewhere."""
    field = field.strip().lower()
    if field == "body":
        return entry.body if entry.body.strip() else entry.title
    if field == "title":
        return entry.title
    if field == "meta":
        lines = [
            f"id: {entry.id}",
            f"title: {entry.title}",
            f"kind: {entry.kind}",
            f"tags: {entry.tags_display()}",
            f"pinned: {'yes' if entry.pinned else 'no'}",
            f"updated: {entry.updated_at}",
        ]
        return "\n".join(lines)
    if field in {"json", "markdown"}:
        from termvault.portability.checksums import entry_content_hash
        from termvault.portability.markdown_format import render_entry_markdown
        from termvault.portability.schema import ExportEntry

        draft = ExportEntry.from_vault_entry(entry)
        if field == "markdown":
            return render_entry_markdown(draft)
        payload = ExportEntry.from_vault_entry(
            entry, content_hash=entry_content_hash(draft)
        ).to_dict()
        return json.dumps(payload, indent=2, ensure_ascii=False)
    raise TermVaultError(f"Unknown copy field {field!r}; choose: {', '.join(COPY_FIELDS)}")
