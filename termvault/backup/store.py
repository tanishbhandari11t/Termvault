"""Backup directory management: locate, list, resolve ``latest``, prune."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from termvault.backup.archive import load_manifest
from termvault.backup.constants import (
    BACKUP_DIRNAME,
    BACKUP_SUFFIX,
    LATEST_ALIAS,
    SAFETY_BACKUP_LABEL,
)
from termvault.backup.errors import BackupError, BackupNotFoundError
from termvault.backup.manifest import BackupManifest
from termvault.backup.naming import parse_backup_timestamp
from termvault.config import get_data_dir


def default_backup_dir() -> Path:
    return get_data_dir() / BACKUP_DIRNAME


def ensure_backup_dir(directory: Path | None = None) -> Path:
    target = directory or default_backup_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


@dataclass
class BackupInfo:
    """Lightweight listing row for one archive on disk."""

    path: Path
    size_bytes: int
    created_at: datetime | None
    manifest: BackupManifest | None = None
    error: str | None = None
    mtime_ns: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def readable(self) -> bool:
        return self.manifest is not None

    @property
    def label(self) -> str | None:
        return self.manifest.label if self.manifest else None

    @property
    def is_safety_backup(self) -> bool:
        return self.label == SAFETY_BACKUP_LABEL

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "label": self.label,
            "readable": self.readable,
            "error": self.error,
            "schema_version": self.manifest.schema_version if self.manifest else None,
            "stats": self.manifest.stats.to_dict() if self.manifest else None,
        }


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def describe_backup(path: Path) -> BackupInfo:
    stat = path.stat()
    try:
        manifest = load_manifest(path)
    except BackupError as exc:
        return BackupInfo(
            path=path,
            size_bytes=stat.st_size,
            created_at=parse_backup_timestamp(path.name),
            error=str(exc),
            mtime_ns=stat.st_mtime_ns,
        )
    created = _parse_iso(manifest.created_at) or parse_backup_timestamp(path.name)
    return BackupInfo(
        path=path,
        size_bytes=stat.st_size,
        created_at=created,
        manifest=manifest,
        mtime_ns=stat.st_mtime_ns,
    )


def list_backups(directory: Path | None = None) -> list[BackupInfo]:
    """Newest first. Unreadable archives are listed with an error."""
    target = directory or default_backup_dir()
    if not target.is_dir():
        return []
    infos = [
        describe_backup(path)
        for path in target.iterdir()
        if path.is_file() and path.suffix == BACKUP_SUFFIX
    ]
    epoch = datetime.min.replace(tzinfo=timezone.utc)
    # created_at has one-second resolution; mtime breaks ties between fast backups.
    infos.sort(key=lambda info: (info.created_at or epoch, info.mtime_ns), reverse=True)
    return infos


def resolve_backup_path(reference: str | Path, directory: Path | None = None) -> Path:
    """Resolve a path, a bare filename in the backup dir, or ``latest``."""
    text = str(reference)
    if text == LATEST_ALIAS:
        readable = [info for info in list_backups(directory) if info.readable]
        if not readable:
            raise BackupNotFoundError(f"{LATEST_ALIAS} (no backups in {directory or default_backup_dir()})")
        return readable[0].path
    candidate = Path(text).expanduser()
    if candidate.exists():
        return candidate.resolve()
    in_dir = (directory or default_backup_dir()) / text
    if in_dir.exists():
        return in_dir.resolve()
    raise BackupNotFoundError(candidate)


@dataclass
class PrunePlan:
    keep: list[BackupInfo] = field(default_factory=list)
    remove: list[BackupInfo] = field(default_factory=list)

    @property
    def freed_bytes(self) -> int:
        return sum(info.size_bytes for info in self.remove)

    def to_dict(self) -> dict:
        return {
            "keep": [info.name for info in self.keep],
            "remove": [info.name for info in self.remove],
            "freed_bytes": self.freed_bytes,
        }


def plan_prune(
    *,
    keep_last: int | None = None,
    older_than_days: int | None = None,
    directory: Path | None = None,
    now: datetime | None = None,
) -> PrunePlan:
    """Decide which archives to delete. The newest readable backup is always kept."""
    if keep_last is None and older_than_days is None:
        raise BackupError("Pass --keep and/or --older-than to prune.")
    if keep_last is not None and keep_last < 1:
        raise BackupError("--keep must be at least 1.")
    if older_than_days is not None and older_than_days < 0:
        raise BackupError("--older-than must be >= 0.")

    infos = list_backups(directory)
    moment = now or datetime.now(timezone.utc)
    cutoff = moment - timedelta(days=older_than_days) if older_than_days is not None else None
    newest_readable = next((info for info in infos if info.readable), None)

    plan = PrunePlan()
    for index, info in enumerate(infos):
        if info is newest_readable:
            plan.keep.append(info)
            continue
        beyond_count = keep_last is not None and index >= keep_last
        too_old = cutoff is not None and info.created_at is not None and info.created_at < cutoff
        if keep_last is not None and cutoff is not None:
            should_remove = beyond_count and too_old
        else:
            should_remove = beyond_count or too_old
        (plan.remove if should_remove else plan.keep).append(info)
    return plan


def apply_prune(plan: PrunePlan) -> list[Path]:
    removed: list[Path] = []
    for info in plan.remove:
        try:
            info.path.unlink()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise BackupError(f"Unable to delete {info.path}: {exc}") from exc
        removed.append(info.path)
    return removed
