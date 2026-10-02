"""Portability-specific errors for Phase 6 Part 1."""

from __future__ import annotations

from termvault.errors import TermVaultError, ValidationError


class PortabilityError(TermVaultError):
    """Base error for export / import failures."""


class ExportError(PortabilityError):
    """Raised when an export cannot be produced."""


class ImportError_(PortabilityError):
    """Raised when an import document cannot be read or applied.

    Named ``ImportError_`` to avoid shadowing the builtin ``ImportError``.
    """


class ImportValidationError(ValidationError, PortabilityError):
    """Raised when an import payload fails schema / field validation."""

    def __init__(self, message: str, *, path: str | None = None) -> None:
        if path:
            message = f"{path}: {message}"
        super().__init__(message)
        self.path = path


class ConflictFailError(PortabilityError):
    """Raised when conflict policy is ``fail`` and a match is found."""

    def __init__(self, title: str, existing_id: int) -> None:
        super().__init__(
            f"Conflict on title {title!r} (existing entry {existing_id})."
        )
        self.title = title
        self.existing_id = existing_id


class UnsupportedFormatError(PortabilityError):
    """Raised when a codec / version is not supported."""
