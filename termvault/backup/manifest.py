"""Backup manifest model: what is inside an archive and how to verify it."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from termvault import __version__
from termvault.backup.constants import (
    BACKUP_FORMAT_NAME,
    BACKUP_FORMAT_VERSION,
    HASH_ALGO,
)
from termvault.backup.errors import InvalidBackupError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class BackupFileRecord:
    """One file stored in the archive, with its size and content hash."""

    name: str
    size: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "size": self.size, "sha256": self.sha256}

    @classmethod
    def from_dict(cls, raw: Any) -> BackupFileRecord:
        if not isinstance(raw, dict):
            raise InvalidBackupError("manifest.files entries must be objects.")
        try:
            name = str(raw["name"])
            size = int(raw["size"])
            digest = str(raw["sha256"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidBackupError(f"Malformed file record: {raw!r}") from exc
        if size < 0 or len(digest) != 64:
            raise InvalidBackupError(f"Malformed file record for {name!r}.")
        return cls(name=name, size=size, sha256=digest)


@dataclass(frozen=True)
class BackupStats:
    """Vault counts captured from the snapshot at backup time."""

    total_entries: int = 0
    active_entries: int = 0
    trashed_entries: int = 0
    pinned_entries: int = 0
    tag_count: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "total_entries": self.total_entries,
            "active_entries": self.active_entries,
            "trashed_entries": self.trashed_entries,
            "pinned_entries": self.pinned_entries,
            "tag_count": self.tag_count,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> BackupStats:
        if not raw:
            return cls()
        if not isinstance(raw, dict):
            raise InvalidBackupError("manifest.stats must be an object.")
        try:
            return cls(**{key: int(raw.get(key, 0)) for key in cls().to_dict()})
        except (TypeError, ValueError) as exc:
            raise InvalidBackupError("manifest.stats values must be integers.") from exc


@dataclass
class BackupManifest:
    """Top-level description of a backup archive."""

    schema_version: int
    files: list[BackupFileRecord] = field(default_factory=list)
    stats: BackupStats = field(default_factory=BackupStats)
    label: str | None = None
    created_at: str = field(default_factory=utc_now_iso)
    termvault_version: str = __version__
    host: str = field(default_factory=platform.node)
    platform: str = field(default_factory=platform.system)
    hash_algo: str = HASH_ALGO
    format: str = BACKUP_FORMAT_NAME
    version: int = BACKUP_FORMAT_VERSION

    def file(self, name: str) -> BackupFileRecord | None:
        for record in self.files:
            if record.name == name:
                return record
        return None

    def has_file(self, name: str) -> bool:
        return self.file(name) is not None

    def draft_files(self) -> list[BackupFileRecord]:
        return [record for record in self.files if record.name.startswith("drafts/")]

    @property
    def total_bytes(self) -> int:
        return sum(record.size for record in self.files)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "created_at": self.created_at,
            "termvault_version": self.termvault_version,
            "schema_version": self.schema_version,
            "label": self.label,
            "host": self.host,
            "platform": self.platform,
            "hash_algo": self.hash_algo,
            "stats": self.stats.to_dict(),
            "files": [record.to_dict() for record in self.files],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, raw: Any) -> BackupManifest:
        if not isinstance(raw, dict):
            raise InvalidBackupError("Manifest root must be an object.")
        fmt = raw.get("format")
        if fmt != BACKUP_FORMAT_NAME:
            raise InvalidBackupError(
                f"Not a TermVault backup (format={fmt!r})."
            )
        try:
            version = int(raw.get("version", 0))
            schema_version = int(raw["schema_version"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidBackupError("Manifest version fields are missing or invalid.") from exc
        if version < 1 or version > BACKUP_FORMAT_VERSION:
            raise InvalidBackupError(
                f"Unsupported backup format version {version} "
                f"(this TermVault reads up to {BACKUP_FORMAT_VERSION})."
            )
        files_raw = raw.get("files")
        if not isinstance(files_raw, list):
            raise InvalidBackupError("manifest.files must be a list.")
        hash_algo = str(raw.get("hash_algo") or HASH_ALGO)
        if hash_algo != HASH_ALGO:
            raise InvalidBackupError(f"Unsupported hash algorithm {hash_algo!r}.")
        label = raw.get("label")
        return cls(
            schema_version=schema_version,
            files=[BackupFileRecord.from_dict(item) for item in files_raw],
            stats=BackupStats.from_dict(raw.get("stats")),
            label=str(label) if label else None,
            created_at=str(raw.get("created_at") or ""),
            termvault_version=str(raw.get("termvault_version") or "unknown"),
            host=str(raw.get("host") or ""),
            platform=str(raw.get("platform") or ""),
            hash_algo=hash_algo,
            format=BACKUP_FORMAT_NAME,
            version=version,
        )

    @classmethod
    def from_json(cls, text: str) -> BackupManifest:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InvalidBackupError(f"Manifest is not valid JSON: {exc}") from exc
        return cls.from_dict(raw)
