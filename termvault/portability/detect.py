"""Detect export codec from path / content sniffing."""

from __future__ import annotations

from pathlib import Path

from termvault.portability.constants import EXPORT_CODECS
from termvault.portability.errors import UnsupportedFormatError


def detect_codec_from_path(path: Path) -> str | None:
    """Return ``json`` / ``markdown`` from a file or directory path."""
    if path.is_dir():
        return "markdown"
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".md", ".markdown"}:
        return "markdown"
    return None


def detect_codec_from_text(text: str) -> str:
    """Sniff codec from leading content."""
    sample = text.lstrip()[:2000]
    if not sample:
        raise UnsupportedFormatError("Empty import content.")
    if sample.startswith("{") or sample.startswith("["):
        return "json"
    if sample.startswith("---") or sample.startswith("#") or sample.startswith("<!--"):
        return "markdown"
    # Heuristic: JSON-looking vs markdown prose
    if '"title"' in sample and ("{" in sample):
        return "json"
    return "markdown"


def resolve_codec(
    *,
    path: Path | None = None,
    text: str | None = None,
    explicit: str | None = None,
) -> str:
    """Resolve codec with explicit > path > sniff precedence."""
    if explicit:
        codec = explicit.strip().lower()
        if codec in {"md", "markdown"}:
            codec = "markdown"
        if codec not in EXPORT_CODECS:
            raise UnsupportedFormatError(
                f"Unsupported codec {explicit!r}; choose: {', '.join(EXPORT_CODECS)}"
            )
        return codec
    if path is not None:
        detected = detect_codec_from_path(path)
        if detected:
            return detected
    if text is not None:
        return detect_codec_from_text(text)
    raise UnsupportedFormatError(
        "Unable to detect format; pass --format json|markdown."
    )
