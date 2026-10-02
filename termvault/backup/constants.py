"""Shared constants for Phase 6 Part 2 backup / restore."""

from __future__ import annotations

from typing import Final

BACKUP_FORMAT_NAME: Final[str] = "termvault-backup"
BACKUP_FORMAT_VERSION: Final[int] = 1

BACKUP_DIRNAME: Final[str] = "backups"
LIVE_DRAFTS_DIRNAME: Final[str] = "tui-drafts"
BACKUP_FILE_PREFIX: Final[str] = "termvault-backup"
BACKUP_SUFFIX: Final[str] = ".zip"
SAFETY_BACKUP_LABEL: Final[str] = "pre-restore"
LATEST_ALIAS: Final[str] = "latest"

# Archive member names
MANIFEST_MEMBER: Final[str] = "manifest.json"
DB_MEMBER: Final[str] = "termvault.db"
CONFIG_MEMBER: Final[str] = "config.json"
EXPORT_MEMBER: Final[str] = "export.json"
DRAFTS_PREFIX: Final[str] = "drafts/"

REQUIRED_TABLES: Final[tuple[str, ...]] = ("entries", "schema_migrations")
HASH_ALGO: Final[str] = "sha256"
HASH_CHUNK_BYTES: Final[int] = 1024 * 1024

# Safety limits for reading untrusted archives
MAX_MEMBER_BYTES: Final[int] = 2 * 1024 * 1024 * 1024
MAX_MEMBER_COUNT: Final[int] = 10_000
MAX_LABEL_LENGTH: Final[int] = 40

DEFAULT_PRUNE_KEEP: Final[int] = 10
