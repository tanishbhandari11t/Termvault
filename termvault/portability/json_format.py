"""JSON codec for TermVault export documents."""

from __future__ import annotations

import json
from typing import Any

from termvault.portability.errors import ImportValidationError
from termvault.portability.schema import ExportDocument


def dumps_export_json(document: ExportDocument, *, pretty: bool = True) -> str:
    """Serialize an export document to JSON text."""
    if pretty:
        return json.dumps(
            document.to_dict(),
            indent=2,
            ensure_ascii=False,
            sort_keys=False,
        ) + "\n"
    return json.dumps(document.to_dict(), ensure_ascii=False, separators=(",", ":"))


def loads_export_json(text: str) -> ExportDocument:
    """Parse JSON text into an ExportDocument."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f"Invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ImportValidationError("JSON root must be an object.")
    # Allow a bare list of entries as a convenience.
    if "entries" not in raw and _looks_like_entry_list_wrapper(raw):
        raise ImportValidationError("JSON root must include an entries array.")
    return ExportDocument.from_dict(raw)


def loads_export_json_flexible(text: str) -> ExportDocument:
    """Parse JSON, also accepting a bare list of entry objects."""
    try:
        raw: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ImportValidationError(f"Invalid JSON: {exc}") from exc
    if isinstance(raw, list):
        return ExportDocument.from_dict({"entries": raw})
    if isinstance(raw, dict):
        if "entries" in raw or raw.get("format") == "termvault-export":
            return ExportDocument.from_dict(raw)
        # Single entry object
        if "title" in raw:
            return ExportDocument.from_dict({"entries": [raw]})
    raise ImportValidationError(
        "JSON must be an export document, an entry object, or a list of entries."
    )


def _looks_like_entry_list_wrapper(raw: dict[str, Any]) -> bool:
    return False
