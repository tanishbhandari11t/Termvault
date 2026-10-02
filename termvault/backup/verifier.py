"""Verify backup archives: structure, checksums, SQLite health, compatibility."""

from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from termvault.backup.archive import (
    check_member_names,
    extract_member,
    member_digest,
    open_archive,
    read_manifest,
)
from termvault.backup.constants import CONFIG_MEMBER, DB_MEMBER, MANIFEST_MEMBER
from termvault.backup.errors import BackupError
from termvault.backup.integrity import (
    missing_tables,
    read_db_stats,
    read_schema_version,
    sqlite_integrity_errors,
)
from termvault.backup.manifest import BackupManifest, BackupStats
from termvault.migrations import CURRENT_SCHEMA_VERSION


@dataclass(frozen=True)
class VerifyIssue:
    level: str  # "error" | "warning"
    message: str

    def format(self) -> str:
        return f"[{self.level}] {self.message}"


@dataclass
class VerifyReport:
    path: Path
    manifest: BackupManifest | None = None
    issues: list[VerifyIssue] = field(default_factory=list)
    db_schema_version: int | None = None
    db_stats: BackupStats | None = None
    checked_files: int = 0

    @property
    def errors(self) -> list[VerifyIssue]:
        return [issue for issue in self.issues if issue.level == "error"]

    @property
    def warnings(self) -> list[VerifyIssue]:
        return [issue for issue in self.issues if issue.level == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, message: str) -> None:
        self.issues.append(VerifyIssue("error", message))

    def warn(self, message: str) -> None:
        self.issues.append(VerifyIssue("warning", message))

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "ok": self.ok,
            "checked_files": self.checked_files,
            "db_schema_version": self.db_schema_version,
            "db_stats": self.db_stats.to_dict() if self.db_stats else None,
            "errors": [issue.message for issue in self.errors],
            "warnings": [issue.message for issue in self.warnings],
            "manifest": self.manifest.to_dict() if self.manifest else None,
        }


def verify_backup(path: Path, *, deep: bool = True) -> VerifyReport:
    """Check an archive end to end. Never raises for bad archives; see report.ok."""
    report = VerifyReport(path=path)
    try:
        archive = open_archive(path)
    except BackupError as exc:
        report.error(str(exc))
        return report

    with archive:
        try:
            check_member_names(archive)
            manifest = read_manifest(archive)
        except BackupError as exc:
            report.error(str(exc))
            return report
        report.manifest = manifest
        _check_members(archive, manifest, report)
        if deep and report.ok:
            _check_database(archive, manifest, report)
            _check_json_members(archive, manifest, report)
    return report


def _check_members(
    archive: zipfile.ZipFile,
    manifest: BackupManifest,
    report: VerifyReport,
) -> None:
    present = {info.filename for info in archive.infolist()}
    if not manifest.has_file(DB_MEMBER):
        report.error(f"Manifest does not list {DB_MEMBER}.")

    listed = {record.name for record in manifest.files}
    for extra in sorted(present - listed - {MANIFEST_MEMBER}):
        report.warn(f"Archive contains unlisted file {extra!r}.")

    for record in manifest.files:
        if record.name not in present:
            report.error(f"Missing file listed in manifest: {record.name!r}.")
            continue
        digest, size = member_digest(archive, record.name)
        report.checked_files += 1
        if size != record.size:
            report.error(
                f"Size mismatch for {record.name!r}: "
                f"manifest {record.size}, archive {size}."
            )
        elif digest != record.sha256:
            report.error(f"Checksum mismatch for {record.name!r} (file was modified).")


def _check_database(
    archive: zipfile.ZipFile,
    manifest: BackupManifest,
    report: VerifyReport,
) -> None:
    with tempfile.TemporaryDirectory(prefix="termvault-verify-") as tmp:
        db_copy = extract_member(archive, DB_MEMBER, Path(tmp) / DB_MEMBER)
        problems = sqlite_integrity_errors(db_copy)
        if problems:
            report.error("Database integrity check failed: " + "; ".join(problems[:3]))
            return
        missing = missing_tables(db_copy)
        if missing:
            report.error("Database is missing tables: " + ", ".join(missing))
            return

        version = read_schema_version(db_copy)
        report.db_schema_version = version
        report.db_stats = read_db_stats(db_copy)

    if version != manifest.schema_version:
        report.error(
            f"Schema version mismatch: manifest {manifest.schema_version}, database {version}."
        )
    if version > CURRENT_SCHEMA_VERSION:
        report.error(
            f"Backup uses schema v{version}, newer than this TermVault "
            f"(v{CURRENT_SCHEMA_VERSION}). Upgrade TermVault to restore it."
        )
    elif version < CURRENT_SCHEMA_VERSION:
        report.warn(
            f"Backup uses schema v{version}; it will be upgraded to "
            f"v{CURRENT_SCHEMA_VERSION} on restore."
        )
    if report.db_stats is not None and report.db_stats != manifest.stats:
        report.warn("Manifest stats differ from the database contents.")


def _check_json_members(
    archive: zipfile.ZipFile,
    manifest: BackupManifest,
    report: VerifyReport,
) -> None:
    if manifest.has_file(CONFIG_MEMBER):
        parsed = _load_json_member(archive, CONFIG_MEMBER)
        if not isinstance(parsed, dict):
            report.error(f"{CONFIG_MEMBER} is not a JSON object.")
    for record in manifest.draft_files():
        if _load_json_member(archive, record.name) is None:
            report.warn(f"Draft {record.name!r} is not valid JSON and will be skipped.")


def _load_json_member(archive: zipfile.ZipFile, name: str) -> object | None:
    try:
        return json.loads(archive.read(name).decode("utf-8"))
    except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
        return None
