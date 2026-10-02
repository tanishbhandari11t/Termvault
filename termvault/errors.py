"""Application-level exceptions for TermVault."""

from __future__ import annotations


class TermVaultError(Exception):
    """Base class for expected TermVault errors."""


class EntryNotFoundError(TermVaultError):
    """Raised when an entry id does not exist."""

    def __init__(self, entry_id: int, *, trashed: bool = False) -> None:
        if trashed:
            message = f"Entry {entry_id} is in the trash."
        else:
            message = f"Entry {entry_id} not found."
        super().__init__(message)
        self.entry_id = entry_id


class TagNotFoundError(TermVaultError):
    """Raised when a tag name does not exist."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Tag '{name}' not found.")
        self.name = name


class ValidationError(TermVaultError):
    """Raised when user input fails validation."""
