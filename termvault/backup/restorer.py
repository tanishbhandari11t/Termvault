"""Restore the vault from a backup archive, with safety backup and rollback."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from termvault.backup.archive import extract_member_verified, open_archive
from termvault.backup.constants import (
    CONFIG_MEMBER,
    DB_MEMBER,
    SAFETY_BACKUP_LABEL,
)
from termvault.backup.creator import create_backup
from termvault.backup.errors import InvalidBackupError, RestoreError
from termvault.backup.integrity import read_db_stats, read_schema_version
from termvault.backup.manifest import BackupManifest, BackupStats
from termvault.backup.snapshot import live_drafts_dir
from termvault.backup.store import resolve_backup_path
from termvault.backup.verifier import VerifyReport, verify_backup
from termvault.config import ensure_data_dir, get_config_path, get_db_path
from termvault.db import initialize_database
from termvault.migrations import CURRENT_SCHEMA_VERSION

_SQLITE_SIDECARS = ("-journal", "-wal", "-shm")


@dataclass
class RestorePlan:
    archive: Path
    manifest: BackupManifest
    verify: VerifyReport
    restore_config: bool
    restore_drafts: bool
    safety_backup: bool
    current_stats: BackupStats | None = None
    current_schema_version: int | None = None

    @property
    def will_migrate(self) -> bool:
        return self.manifest.schema_version < CURRENT_SCHEMA_VERSION

    @property
    def draft_count(self) -> int:
        return len(self.manifest.draft_files()) if self.restore_drafts else 0

    def to_dict(self) -> dict:
        return {
            "archive": str(self.archive),
            "restore_config": self.restore_config,
            "restore_drafts": self.restore_drafts,
            "draft_count": self.draft_count,
            "safety_backup": self.safety_backup,
            "will_migrate": self.will_migrate,
            "backup_created_at": self.manifest.created_at,
            "backup_label": self.manifest.label,
            "backup_schema_version": self.manifest.schema_version,
            "backup_stats": self.manifest.stats.to_dict(),
            "current_schema_version": self.current_schema_version,
            "current_stats": self.current_stats.to_dict() if self.current_stats else None,
            "warnings": [issue.message for issue in self.verify.warnings],
        }


@dataclass
class RestoreResult:
    plan: RestorePlan
    restored: list[str] = field(default_factory=list)
    safety_backup_path: Path | None = None
    stats_after: BackupStats | None = None
    schema_version_after: int | None = None

    def to_dict(self) -> dict:
        return {
            "plan": self.plan.to_dict(),
            "restored": self.restored,
            "safety_backup": str(self.safety_backup_path) if self.safety_backup_path else None,
            "schema_version_after": self.schema_version_after,
            "stats_after": self.stats_after.to_dict() if self.stats_after else None,
        }


def plan_restore(
    reference: str | Path,
    *,
    include_config: bool = True,
    include_drafts: bool = False,
    safety_backup: bool = True,
    backup_dir: Path | None = None,
) -> RestorePlan:
    """Resolve + verify an archive and describe what a restore would change."""
    path = resolve_backup_path(reference, backup_dir)
    report = verify_backup(path)
    if not report.ok or report.manifest is None:
        messages = [issue.message for issue in report.errors]
        raise InvalidBackupError(
            "Backup failed verification: " + (messages[0] if messages else "unknown error"),
            issues=messages,
        )
    manifest = report.manifest

    db_path = get_db_path()
    current_stats = read_db_stats(db_path) if db_path.exists() else None
    current_schema = read_schema_version(db_path) if db_path.exists() else None

    return RestorePlan(
        archive=path,
        manifest=manifest,
        verify=report,
        restore_config=include_config and manifest.has_file(CONFIG_MEMBER),
        restore_drafts=include_drafts and bool(manifest.draft_files()),
        safety_backup=safety_backup,
        current_stats=current_stats,
        current_schema_version=current_schema,
    )


def apply_restore(plan: RestorePlan, *, backup_dir: Path | None = None) -> RestoreResult:
    """Swap the live vault for the archive contents.

    Order: safety backup → stage + verify files → move live files aside →
    move staged files in → migrate. Any failure after the swap starts puts the
    original files back.
    """
    result = RestoreResult(plan=plan)
    db_path = get_db_path()
    config_path = get_config_path()

    if plan.safety_backup and db_path.exists():
        safety = create_backup(
            label=SAFETY_BACKUP_LABEL,
            include_config=True,
            include_drafts=plan.restore_drafts,
            backup_dir=backup_dir,
        )
        result.safety_backup_path = safety.path

    data_dir = ensure_data_dir()
    staged_db = data_dir / ".restore-staged.db"
    staged_config = data_dir / ".restore-staged-config.json"
    rollback_db = data_dir / ".restore-rollback.db"
    rollback_config = data_dir / ".restore-rollback-config.json"

    try:
        _stage_files(plan, staged_db, staged_config)
    except Exception:
        _cleanup(staged_db, staged_config)
        raise

    had_db = db_path.exists()
    had_config = config_path.exists()
    moved_db = False
    moved_config = False
    wrote_config = False
    try:
        if had_db:
            os.replace(db_path, rollback_db)
            moved_db = True
        _remove_sidecars(db_path)
        os.replace(staged_db, db_path)
        result.restored.append(DB_MEMBER)

        if plan.restore_config:
            if had_config:
                os.replace(config_path, rollback_config)
                moved_config = True
            os.replace(staged_config, config_path)
            wrote_config = True
            result.restored.append(CONFIG_MEMBER)

        initialize_database()
    except Exception as exc:
        rolled_back = _rollback(
            db_path=db_path,
            config_path=config_path,
            rollback_db=rollback_db,
            rollback_config=rollback_config,
            moved_db=moved_db,
            had_db=had_db,
            moved_config=moved_config,
            wrote_config=wrote_config,
        )
        raise RestoreError(f"Restore failed: {exc}", rolled_back=rolled_back) from exc
    finally:
        _cleanup(staged_db, staged_config)

    _cleanup(rollback_db, rollback_config)

    if plan.restore_drafts:
        result.restored.extend(_restore_drafts(plan))

    result.stats_after = read_db_stats(db_path)
    result.schema_version_after = read_schema_version(db_path)
    return result


def restore_backup(
    reference: str | Path,
    *,
    include_config: bool = True,
    include_drafts: bool = False,
    safety_backup: bool = True,
    backup_dir: Path | None = None,
) -> RestoreResult:
    plan = plan_restore(
        reference,
        include_config=include_config,
        include_drafts=include_drafts,
        safety_backup=safety_backup,
        backup_dir=backup_dir,
    )
    return apply_restore(plan, backup_dir=backup_dir)


def _stage_files(plan: RestorePlan, staged_db: Path, staged_config: Path) -> None:
    manifest = plan.manifest
    db_record = manifest.file(DB_MEMBER)
    if db_record is None:
        raise InvalidBackupError(f"Backup has no {DB_MEMBER}.")
    with open_archive(plan.archive) as archive:
        extract_member_verified(archive, db_record, staged_db)
        if plan.restore_config:
            config_record = manifest.file(CONFIG_MEMBER)
            if config_record is None:
                raise InvalidBackupError(f"Backup has no {CONFIG_MEMBER}.")
            extract_member_verified(archive, config_record, staged_config)


def _restore_drafts(plan: RestorePlan) -> list[str]:
    target_dir = live_drafts_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    restored: list[str] = []
    with open_archive(plan.archive) as archive:
        for record in plan.manifest.draft_files():
            name = Path(record.name).name
            destination = target_dir / name
            try:
                extract_member_verified(archive, record, destination)
                json.loads(destination.read_text(encoding="utf-8"))
            except (InvalidBackupError, ValueError, OSError):
                destination.unlink(missing_ok=True)
                continue
            restored.append(record.name)
    return restored


def _remove_sidecars(db_path: Path) -> None:
    for suffix in _SQLITE_SIDECARS:
        Path(str(db_path) + suffix).unlink(missing_ok=True)


def _rollback(
    *,
    db_path: Path,
    config_path: Path,
    rollback_db: Path,
    rollback_config: Path,
    moved_db: bool,
    had_db: bool,
    moved_config: bool,
    wrote_config: bool,
) -> bool:
    try:
        if moved_db:
            os.replace(rollback_db, db_path)
        elif not had_db:
            db_path.unlink(missing_ok=True)
        if moved_config:
            os.replace(rollback_config, config_path)
        elif wrote_config:
            config_path.unlink(missing_ok=True)
    except OSError:
        return False
    return True


def _cleanup(*paths: Path) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
