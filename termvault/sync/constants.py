"""Constants for opt-in folder sync."""

from __future__ import annotations

from typing import Final

SYNC_CONFIG_FILENAME: Final[str] = "sync.json"
SYNC_DIRNAME: Final[str] = "termvault-sync"
DEVICES_DIRNAME: Final[str] = "devices"
SNAPSHOT_FORMAT: Final[str] = "termvault-sync"
SNAPSHOT_VERSION: Final[int] = 1

MERGE_POLICIES: Final[tuple[str, ...]] = ("newest", "local", "remote")
DEFAULT_POLICY: Final[str] = "newest"

CONFLICT_COPY_SUFFIX: Final[str] = " (conflict copy)"
MAX_SNAPSHOT_BYTES: Final[int] = 200 * 1024 * 1024
