"""Draft autosave for Phase 5 Part 1 new/edit modals."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from termvault.config import ensure_data_dir
from termvault.tui.constants import DRAFT_DIRNAME, DRAFT_EDIT_PREFIX, DRAFT_NEW_NAME
from termvault.tui.validation import FormData


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def draft_dir() -> Path:
    path = ensure_data_dir() / DRAFT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_draft_path() -> Path:
    return draft_dir() / DRAFT_NEW_NAME


def edit_draft_path(entry_id: int) -> Path:
    return draft_dir() / f"{DRAFT_EDIT_PREFIX}{entry_id}.json"


def save_draft(path: Path, data: FormData, *, meta: dict[str, Any] | None = None) -> Path:
    """Persist a form draft as JSON."""
    payload = {
        "saved_at": _utc_now(),
        "form": asdict(data),
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def load_draft(path: Path) -> FormData | None:
    """Load a draft if present and valid."""
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    form = raw.get("form")
    if not isinstance(form, dict):
        return None
    title = str(form.get("title", "")).strip()
    body = str(form.get("body", ""))
    kind = str(form.get("kind", "note")).strip().lower() or "note"
    tags_value = form.get("tags", [])
    if isinstance(tags_value, list):
        tags = tuple(str(tag) for tag in tags_value)
    else:
        tags = ()
    if not title and not body and not tags:
        return None
    return FormData(title=title, body=body, kind=kind, tags=tags)


def clear_draft(path: Path) -> None:
    """Delete a draft file if it exists."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


def list_drafts() -> list[Path]:
    """Return all draft files currently on disk."""
    folder = draft_dir()
    return sorted(folder.glob("*.json"))
