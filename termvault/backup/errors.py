"""Backup / restore errors for Phase 6 Part 2."""

from __future__ import annotations

from pathlib import Path

from termvault.errors import TermVaultError


class BackupError(TermVaultError):
    """Base error for backup / restore failures."""


class BackupNotFoundError(BackupError):
    def __init__(self, path: Path | str) -> None:
        super().__init__(f"Backup not found: {path}")
        self.path = Path(path)


class InvalidBackupError(BackupError):
    """Raised when an archive is corrupt, tampered with, or incompatible."""

    def __init__(self, message: str, *, issues: list[str] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


class UnsafeArchiveError(InvalidBackupError):
    """Raised when an archive member would escape the extraction directory."""


class RestoreError(BackupError):
    """Raised when a restore fails (the vault is rolled back when possible)."""

    def __init__(self, message: str, *, rolled_back: bool = False) -> None:
        if rolled_back:
            message = f"{message} (previous vault was restored)"
        super().__init__(message)
        self.rolled_back = rolled_back
