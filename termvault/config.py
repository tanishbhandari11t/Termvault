"""Paths, env overrides, and user-facing vault preferences."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

# Tests and advanced users can redirect all vault files with this env var.
DATA_DIR_ENV = "TERMVAULT_DATA_DIR"

VALID_SORTS = ("updated", "created", "title")
VALID_OUTPUT_FORMATS = ("text", "json")
VALID_KINDS = ("note", "snippet", "command", "link", "error")


@dataclass
class VaultSettings:
    """Persisted defaults for list/search/recent behavior."""

    default_list_limit: int = 20
    default_recent_limit: int = 10
    default_search_limit: int = 10
    default_sort: str = "updated"
    default_output: str = "text"
    show_snippets: bool = True

    def validate(self) -> None:
        if self.default_list_limit < 1:
            raise ValueError("default_list_limit must be >= 1")
        if self.default_recent_limit < 1:
            raise ValueError("default_recent_limit must be >= 1")
        if self.default_search_limit < 1:
            raise ValueError("default_search_limit must be >= 1")
        if self.default_sort not in VALID_SORTS:
            raise ValueError(f"default_sort must be one of {VALID_SORTS}")
        if self.default_output not in VALID_OUTPUT_FORMATS:
            raise ValueError(f"default_output must be one of {VALID_OUTPUT_FORMATS}")


def get_data_dir() -> Path:
    """Return the directory where TermVault stores local data."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".termvault").resolve()


def get_db_path() -> Path:
    """Return the SQLite database path."""
    return get_data_dir() / "termvault.db"


def get_config_path() -> Path:
    """Return the JSON settings file path."""
    return get_data_dir() / "config.json"


def ensure_data_dir() -> Path:
    """Create the data directory if needed and return it."""
    data_dir = get_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_settings() -> VaultSettings:
    """Load vault settings, falling back to defaults when missing/invalid."""
    ensure_data_dir()
    path = get_config_path()
    if not path.exists():
        return VaultSettings()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return VaultSettings()
    if not isinstance(raw, dict):
        return VaultSettings()

    settings = VaultSettings(
        default_list_limit=int(raw.get("default_list_limit", 20)),
        default_recent_limit=int(raw.get("default_recent_limit", 10)),
        default_search_limit=int(raw.get("default_search_limit", 10)),
        default_sort=str(raw.get("default_sort", "updated")),
        default_output=str(raw.get("default_output", "text")),
        show_snippets=bool(raw.get("show_snippets", True)),
    )
    try:
        settings.validate()
    except ValueError:
        return VaultSettings()
    return settings


def save_settings(settings: VaultSettings) -> Path:
    """Persist vault settings to disk."""
    settings.validate()
    ensure_data_dir()
    path = get_config_path()
    path.write_text(json.dumps(asdict(settings), indent=2) + "\n", encoding="utf-8")
    return path
