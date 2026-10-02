"""Consistent point-in-time copies of the live vault files."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path

from termvault.backup.constants import LIVE_DRAFTS_DIRNAME
from termvault.config import get_config_path, get_data_dir, get_db_path
from termvault.db import initialize_database


@dataclass
class VaultSnapshot:
    """Files staged in a temp directory, ready to be archived."""

    db_path: Path
    config_path: Path | None = None
    draft_paths: list[Path] = field(default_factory=list)


def snapshot_database(destination: Path) -> Path:
    """Copy the live database with SQLite's online backup API.

    Unlike a raw file copy, this is safe even if another process is writing.
    """
    initialize_database()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with closing(sqlite3.connect(get_db_path())) as source:
        with closing(sqlite3.connect(destination)) as target:
            source.backup(target)
    return destination


def snapshot_config(destination: Path) -> Path | None:
    source = get_config_path()
    if not source.is_file():
        return None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    return destination


def live_drafts_dir() -> Path:
    return get_data_dir() / LIVE_DRAFTS_DIRNAME


def list_live_drafts() -> list[Path]:
    directory = live_drafts_dir()
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix == ".json")


def take_snapshot(
    staging_dir: Path,
    *,
    include_config: bool = True,
    include_drafts: bool = False,
) -> VaultSnapshot:
    """Stage the database (and optional config / drafts) into staging_dir."""
    db_copy = snapshot_database(staging_dir / "termvault.db")
    config_copy = (
        snapshot_config(staging_dir / "config.json") if include_config else None
    )
    drafts: list[Path] = []
    if include_drafts:
        drafts_dir = staging_dir / "drafts"
        drafts_dir.mkdir(parents=True, exist_ok=True)
        for draft in list_live_drafts():
            target = drafts_dir / draft.name
            target.write_bytes(draft.read_bytes())
            drafts.append(target)
    return VaultSnapshot(db_path=db_copy, config_path=config_copy, draft_paths=drafts)
