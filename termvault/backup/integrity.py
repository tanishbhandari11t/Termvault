"""Hashing and SQLite health checks used by backup and verify."""

from __future__ import annotations

import hashlib
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import BinaryIO

from termvault.backup.constants import HASH_ALGO, HASH_CHUNK_BYTES, REQUIRED_TABLES
from termvault.backup.manifest import BackupStats


def sha256_stream(stream: BinaryIO) -> tuple[str, int]:
    """Hash a binary stream; returns (hex digest, byte count)."""
    digest = hashlib.new(HASH_ALGO)
    total = 0
    while True:
        chunk = stream.read(HASH_CHUNK_BYTES)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
    return digest.hexdigest(), total


def sha256_file(path: Path) -> tuple[str, int]:
    with path.open("rb") as handle:
        return sha256_stream(handle)


def sha256_bytes(data: bytes) -> str:
    return hashlib.new(HASH_ALGO, data).hexdigest()


def _open_readonly(path: Path) -> sqlite3.Connection:
    uri = f"{path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def sqlite_integrity_errors(path: Path) -> list[str]:
    """Run ``PRAGMA integrity_check``; empty list means healthy."""
    try:
        with closing(_open_readonly(path)) as conn:
            rows = conn.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as exc:
        return [f"Not a readable SQLite database: {exc}"]
    messages = [str(row[0]) for row in rows]
    if messages == ["ok"]:
        return []
    return messages


def missing_tables(path: Path) -> list[str]:
    with closing(_open_readonly(path)) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
    present = {str(row[0]) for row in rows}
    return [table for table in REQUIRED_TABLES if table not in present]


def read_schema_version(path: Path) -> int:
    """Return the highest applied migration in a vault database file."""
    with closing(_open_readonly(path)) as conn:
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
            ).fetchone()
        except sqlite3.OperationalError:
            return 0
    return int(row[0]) if row else 0


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(str(row[1]) == column for row in rows)


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def read_db_stats(path: Path) -> BackupStats:
    """Count entries directly from a database file (works on older schemas)."""
    with closing(_open_readonly(path)) as conn:
        if not _has_table(conn, "entries"):
            return BackupStats()
        total = int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        trashed = 0
        pinned = 0
        if _has_column(conn, "entries", "trashed_at"):
            trashed = int(
                conn.execute(
                    "SELECT COUNT(*) FROM entries WHERE trashed_at IS NOT NULL"
                ).fetchone()[0]
            )
        if _has_column(conn, "entries", "pinned"):
            pinned_sql = "SELECT COUNT(*) FROM entries WHERE pinned = 1"
            if _has_column(conn, "entries", "trashed_at"):
                pinned_sql += " AND trashed_at IS NULL"
            pinned = int(conn.execute(pinned_sql).fetchone()[0])
        tag_count = 0
        if _has_table(conn, "tags"):
            tag_count = int(conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
    return BackupStats(
        total_entries=total,
        active_entries=total - trashed,
        trashed_entries=trashed,
        pinned_entries=pinned,
        tag_count=tag_count,
    )
