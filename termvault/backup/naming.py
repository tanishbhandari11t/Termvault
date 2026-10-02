"""Backup filename generation and parsing."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from termvault.backup.constants import (
    BACKUP_FILE_PREFIX,
    BACKUP_SUFFIX,
    MAX_LABEL_LENGTH,
)

_SLUG_STRIP_RE = re.compile(r"[^a-z0-9]+")
_NAME_RE = re.compile(
    rf"^{re.escape(BACKUP_FILE_PREFIX)}-(\d{{8}})-(\d{{6}})(?:-([a-z0-9-]+?))?(?:-(\d+))?"
    rf"{re.escape(BACKUP_SUFFIX)}$"
)


def slugify_label(label: str | None) -> str | None:
    """Lowercase, dash-separated, length-capped label safe for filenames."""
    if not label:
        return None
    slug = _SLUG_STRIP_RE.sub("-", label.strip().lower()).strip("-")
    if not slug:
        return None
    return slug[:MAX_LABEL_LENGTH].rstrip("-")


def timestamp_token(moment: datetime | None = None) -> str:
    when = (moment or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return when.strftime("%Y%m%d-%H%M%S")


def backup_filename(label: str | None = None, *, moment: datetime | None = None) -> str:
    parts = [BACKUP_FILE_PREFIX, timestamp_token(moment)]
    slug = slugify_label(label)
    if slug:
        parts.append(slug)
    return "-".join(parts) + BACKUP_SUFFIX


def unique_backup_path(
    directory: Path,
    label: str | None = None,
    *,
    moment: datetime | None = None,
) -> Path:
    """Pick a non-existing path in directory, adding -2, -3… on collision."""
    base = backup_filename(label, moment=moment)
    candidate = directory / base
    counter = 2
    while candidate.exists():
        stem = base[: -len(BACKUP_SUFFIX)]
        candidate = directory / f"{stem}-{counter}{BACKUP_SUFFIX}"
        counter += 1
    return candidate


def parse_backup_timestamp(name: str) -> datetime | None:
    """Extract the UTC timestamp from a generated backup filename."""
    match = _NAME_RE.match(name)
    if not match:
        return None
    try:
        parsed = datetime.strptime(f"{match.group(1)}{match.group(2)}", "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def looks_like_backup_name(name: str) -> bool:
    return name.startswith(BACKUP_FILE_PREFIX) and name.endswith(BACKUP_SUFFIX)
