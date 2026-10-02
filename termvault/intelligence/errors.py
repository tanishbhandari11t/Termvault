"""Errors for Phase 7 search intelligence."""

from __future__ import annotations

from termvault.errors import TermVaultError


class IntelligenceError(TermVaultError):
    """Base error for find / index / related failures."""


class BackendUnavailableError(IntelligenceError):
    """Raised when an optional embedding backend is not installed."""
