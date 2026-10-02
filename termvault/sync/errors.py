"""Errors for opt-in folder sync."""

from __future__ import annotations

from termvault.errors import TermVaultError


class SyncError(TermVaultError):
    """Base error for sync failures."""


class SyncNotConfiguredError(SyncError):
    def __init__(self) -> None:
        super().__init__(
            "Sync is not enabled. It is opt-in: run 'tv sync init <folder>' first."
        )


class SyncFolderMissingError(SyncError):
    def __init__(self, folder: str) -> None:
        super().__init__(
            f"Sync folder not found: {folder}. Is the drive mounted / cloud folder available?"
        )
        self.folder = folder


class InvalidSnapshotError(SyncError):
    """A device snapshot file could not be parsed or validated."""
