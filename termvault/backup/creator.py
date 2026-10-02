"""Create backup archives from the live vault."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from termvault.backup.archive import bytes_record, record_for_file, write_archive
from termvault.backup.constants import (
    BACKUP_SUFFIX,
    CONFIG_MEMBER,
    DB_MEMBER,
    DRAFTS_PREFIX,
    EXPORT_MEMBER,
    MAX_LABEL_LENGTH,
)
from termvault.backup.errors import BackupError
from termvault.backup.integrity import read_db_stats, read_schema_version
from termvault.backup.manifest import BackupManifest
from termvault.backup.naming import unique_backup_path
from termvault.backup.snapshot import take_snapshot
from termvault.backup.store import ensure_backup_dir


@dataclass
class BackupResult:
    path: Path
    manifest: BackupManifest

    @property
    def size_bytes(self) -> int:
        return self.path.stat().st_size

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size_bytes": self.size_bytes,
            "manifest": self.manifest.to_dict(),
        }


def clean_label(label: str | None) -> str | None:
    if label is None:
        return None
    cleaned = " ".join(label.split())
    return cleaned[:MAX_LABEL_LENGTH] or None


def resolve_backup_target(
    destination: str | Path | None,
    *,
    label: str | None,
    backup_dir: Path | None,
    overwrite: bool,
) -> Path:
    """Default dir → generated name; directory → generated name inside; file → as given."""
    if destination is None:
        return unique_backup_path(ensure_backup_dir(backup_dir), label)
    raw = str(destination)
    path = Path(raw).expanduser()
    if raw.endswith(("/", "\\")) or path.is_dir():
        path.mkdir(parents=True, exist_ok=True)
        return unique_backup_path(path.resolve(), label)
    if path.suffix.lower() != BACKUP_SUFFIX:
        path = path.with_name(path.name + BACKUP_SUFFIX)
    path = path.resolve()
    if path.exists() and not overwrite:
        raise BackupError(f"Refusing to overwrite existing file: {path} (pass --force)")
    return path


def create_backup(
    destination: str | Path | None = None,
    *,
    label: str | None = None,
    include_config: bool = True,
    include_drafts: bool = False,
    include_export: bool = False,
    backup_dir: Path | None = None,
    overwrite: bool = False,
) -> BackupResult:
    """Snapshot the vault into a verified zip archive."""
    label = clean_label(label)
    target = resolve_backup_target(
        destination,
        label=label,
        backup_dir=backup_dir,
        overwrite=overwrite,
    )

    with tempfile.TemporaryDirectory(prefix="termvault-backup-") as staging:
        snapshot = take_snapshot(
            Path(staging),
            include_config=include_config,
            include_drafts=include_drafts,
        )
        members: dict[str, Path] = {DB_MEMBER: snapshot.db_path}
        if snapshot.config_path is not None:
            members[CONFIG_MEMBER] = snapshot.config_path
        for draft in snapshot.draft_paths:
            members[DRAFTS_PREFIX + draft.name] = draft

        extra: dict[str, bytes] = {}
        if include_export:
            extra[EXPORT_MEMBER] = _export_json_bytes()

        records = [record_for_file(name, path) for name, path in members.items()]
        records.extend(bytes_record(name, data) for name, data in extra.items())

        manifest = BackupManifest(
            schema_version=read_schema_version(snapshot.db_path),
            files=records,
            stats=read_db_stats(snapshot.db_path),
            label=label,
        )
        write_archive(target, members, manifest, extra_bytes=extra)

    return BackupResult(path=target, manifest=manifest)


def _export_json_bytes() -> bytes:
    """Human-readable copy of every entry, for recovery without TermVault."""
    from termvault.portability.exporter import export_vault, serialize_document
    from termvault.portability.filters import ExportFilters

    document = export_vault(ExportFilters(include_trashed=True))
    return serialize_document(document, codec="json").encode("utf-8")
