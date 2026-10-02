"""Read the local vault as sync records, and track per-uid merge bases."""

from __future__ import annotations

import sqlite3

from termvault.sync.records import SyncRecord
from termvault.tags import fetch_entry_tags


def read_local_records(conn: sqlite3.Connection) -> dict[str, SyncRecord]:
    """Every entry (including trashed) plus tombstones for deleted uids."""
    records: dict[str, SyncRecord] = {}
    rows = conn.execute(
        """
        SELECT id, uid, title, body, kind, pinned, trashed_at, created_at, updated_at
        FROM entries
        WHERE uid IS NOT NULL
        """
    ).fetchall()
    for row in rows:
        uid = str(row["uid"])
        records[uid] = SyncRecord(
            uid=uid,
            title=str(row["title"]),
            body=str(row["body"]),
            tags=fetch_entry_tags(conn, int(row["id"])),
            kind=str(row["kind"] or "note"),
            pinned=bool(int(row["pinned"] or 0)),
            trashed_at=str(row["trashed_at"]) if row["trashed_at"] is not None else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
    for row in conn.execute("SELECT uid, deleted_at FROM entry_tombstones").fetchall():
        uid = str(row["uid"])
        if uid not in records:
            records[uid] = SyncRecord.tombstone(uid, str(row["deleted_at"]))
    return records


def uid_to_entry_id(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT id, uid FROM entries WHERE uid IS NOT NULL").fetchall()
    return {str(row["uid"]): int(row["id"]) for row in rows}


def read_sync_state(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT uid, base_hash FROM sync_state").fetchall()
    return {str(row["uid"]): str(row["base_hash"]) for row in rows}


def write_sync_state(
    conn: sqlite3.Connection,
    bases: dict[str, str],
    synced_at: str,
) -> None:
    """Replace merge bases with the state everyone agreed on after this sync."""
    conn.execute("DELETE FROM sync_state")
    conn.executemany(
        "INSERT INTO sync_state(uid, base_hash, synced_at) VALUES (?, ?, ?)",
        [(uid, base_hash, synced_at) for uid, base_hash in bases.items()],
    )


def clear_sync_state(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM sync_state")
    return int(cursor.rowcount)
