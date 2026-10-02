"""SQLite connection helpers and schema setup."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from termvault.config import ensure_data_dir, get_db_path
from termvault.migrations import apply_migrations


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def initialize_database() -> None:
    """Ensure the data directory and latest schema exist."""
    ensure_data_dir()
    with connect() as conn:
        apply_migrations(conn, _utc_now())


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with sensible defaults."""
    ensure_data_dir()
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
