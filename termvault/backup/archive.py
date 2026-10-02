"""Zip archive read / write with path-safety checks."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path, PurePosixPath

from termvault.backup.constants import (
    MANIFEST_MEMBER,
    MAX_MEMBER_BYTES,
    MAX_MEMBER_COUNT,
)
from termvault.backup.errors import (
    BackupError,
    BackupNotFoundError,
    InvalidBackupError,
    UnsafeArchiveError,
)
from termvault.backup.integrity import sha256_bytes, sha256_file, sha256_stream
from termvault.backup.manifest import BackupFileRecord, BackupManifest


def is_safe_member_name(name: str) -> bool:
    """Reject absolute paths, drive letters, backslashes, and ``..`` segments."""
    if not name or name.startswith(("/", "\\")) or "\\" in name:
        return False
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        return False
    return ":" not in posix.parts[0]


def record_for_file(name: str, path: Path) -> BackupFileRecord:
    digest, size = sha256_file(path)
    return BackupFileRecord(name=name, size=size, sha256=digest)


def write_archive(
    destination: Path,
    members: dict[str, Path],
    manifest: BackupManifest,
    *,
    extra_bytes: dict[str, bytes] | None = None,
) -> Path:
    """Write members + manifest atomically (temp file, then rename)."""
    for name in [*members, *(extra_bytes or {})]:
        if not is_safe_member_name(name):
            raise BackupError(f"Refusing to archive unsafe member name {name!r}.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(destination.name + ".partial")
    try:
        with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(MANIFEST_MEMBER, manifest.to_json())
            for name, path in members.items():
                archive.write(path, arcname=name)
            for name, data in (extra_bytes or {}).items():
                archive.writestr(name, data)
        os.replace(temp_path, destination)
    except OSError as exc:
        raise BackupError(f"Unable to write backup {destination}: {exc}") from exc
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return destination


def open_archive(path: Path) -> zipfile.ZipFile:
    if not path.exists():
        raise BackupNotFoundError(path)
    if not path.is_file():
        raise InvalidBackupError(f"Backup path is not a file: {path}")
    try:
        return zipfile.ZipFile(path, "r")
    except zipfile.BadZipFile as exc:
        raise InvalidBackupError(f"Not a valid zip archive: {path}") from exc


def check_member_names(archive: zipfile.ZipFile) -> None:
    infos = archive.infolist()
    if len(infos) > MAX_MEMBER_COUNT:
        raise InvalidBackupError(f"Archive has too many members ({len(infos)}).")
    for info in infos:
        if not is_safe_member_name(info.filename):
            raise UnsafeArchiveError(f"Unsafe path in archive: {info.filename!r}")
        if info.file_size > MAX_MEMBER_BYTES:
            raise InvalidBackupError(f"Archive member too large: {info.filename!r}")


def read_manifest(archive: zipfile.ZipFile) -> BackupManifest:
    try:
        raw = archive.read(MANIFEST_MEMBER)
    except KeyError as exc:
        raise InvalidBackupError("Archive has no manifest.json.") from exc
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidBackupError("manifest.json is not UTF-8.") from exc
    return BackupManifest.from_json(text)


def load_manifest(path: Path) -> BackupManifest:
    """Read just the manifest from an archive on disk."""
    with open_archive(path) as archive:
        check_member_names(archive)
        return read_manifest(archive)


def member_digest(archive: zipfile.ZipFile, name: str) -> tuple[str, int]:
    with archive.open(name) as handle:
        return sha256_stream(handle)


def extract_member(archive: zipfile.ZipFile, name: str, destination: Path) -> Path:
    """Extract one member to an explicit destination path (never archive paths)."""
    if not is_safe_member_name(name):
        raise UnsafeArchiveError(f"Unsafe path in archive: {name!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(name) as source, destination.open("wb") as target:
        while True:
            chunk = source.read(1024 * 1024)
            if not chunk:
                break
            target.write(chunk)
    return destination


def extract_member_verified(
    archive: zipfile.ZipFile,
    record: BackupFileRecord,
    destination: Path,
) -> Path:
    """Extract a member and confirm it matches its manifest hash."""
    extract_member(archive, record.name, destination)
    digest, size = sha256_file(destination)
    if digest != record.sha256 or size != record.size:
        destination.unlink(missing_ok=True)
        raise InvalidBackupError(f"Checksum mismatch for {record.name!r}.")
    return destination


def bytes_record(name: str, data: bytes) -> BackupFileRecord:
    return BackupFileRecord(name=name, size=len(data), sha256=sha256_bytes(data))
