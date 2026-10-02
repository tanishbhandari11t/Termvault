"""Schema migrations for TermVault."""

from __future__ import annotations

import sqlite3
import uuid

CURRENT_SCHEMA_VERSION = 3

# Phase 7: stable cross-device ids, deletion tombstones, search vectors, sync bases.
# Triggers keep storage.py unaware of uids: inserts get one automatically and
# permanent deletes leave a tombstone that sync can propagate.
INTELLIGENCE_SCHEMA = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_entries_uid ON entries(uid);

CREATE TABLE IF NOT EXISTS entry_tombstones (
    uid TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entry_embeddings (
    entry_id INTEGER PRIMARY KEY,
    backend TEXT NOT NULL,
    dim INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    vector BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS sync_state (
    uid TEXT PRIMARY KEY,
    base_hash TEXT NOT NULL,
    synced_at TEXT NOT NULL
);

DROP TRIGGER IF EXISTS entries_uid_ai;
CREATE TRIGGER entries_uid_ai AFTER INSERT ON entries
WHEN new.uid IS NULL BEGIN
    UPDATE entries SET uid = lower(hex(randomblob(16))) WHERE id = new.id;
END;

DROP TRIGGER IF EXISTS entries_tombstone_ad;
CREATE TRIGGER entries_tombstone_ad AFTER DELETE ON entries
WHEN old.uid IS NOT NULL BEGIN
    INSERT OR REPLACE INTO entry_tombstones(uid, deleted_at)
    VALUES (old.uid, strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'));
END;
"""

BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL DEFAULT '',
    tags TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_updated_at ON entries(updated_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5(
    title,
    body,
    tags,
    tokenize = 'porter unicode61'
);
"""

FTS_TRIGGERS = """
DROP TRIGGER IF EXISTS entries_ai;
DROP TRIGGER IF EXISTS entries_ad;
DROP TRIGGER IF EXISTS entries_au;

CREATE TRIGGER entries_ai AFTER INSERT ON entries BEGIN
    INSERT INTO entries_fts(rowid, title, body, tags)
    VALUES (new.id, new.title, new.body, new.tags);
END;

CREATE TRIGGER entries_ad AFTER DELETE ON entries BEGIN
    DELETE FROM entries_fts WHERE rowid = old.id;
END;

CREATE TRIGGER entries_au AFTER UPDATE OF title, body, tags ON entries BEGIN
    DELETE FROM entries_fts WHERE rowid = old.id;
    INSERT INTO entries_fts(rowid, title, body, tags)
    VALUES (new.id, new.title, new.body, new.tags);
END;
"""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _current_version(conn: sqlite3.Connection) -> int:
    if not _has_table(conn, "schema_migrations"):
        return 0
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    return int(row[0])


def _mark_version(conn: sqlite3.Connection, version: int, applied_at: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
        (version, applied_at),
    )


def _backfill_fts(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "entries_fts"):
        return
    entry_count = int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
    fts_count = int(conn.execute("SELECT COUNT(*) FROM entries_fts").fetchone()[0])
    if entry_count > 0 and fts_count == 0:
        conn.execute(
            """
            INSERT INTO entries_fts(rowid, title, body, tags)
            SELECT id, title, body, tags FROM entries
            """
        )


def _migrate_to_v1(conn: sqlite3.Connection, applied_at: str) -> None:
    """Baseline Phase 2/3 schema."""
    conn.executescript(BASE_SCHEMA)
    conn.executescript(FTS_TRIGGERS)
    _backfill_fts(conn)
    _mark_version(conn, 1, applied_at)


def _migrate_to_v2(conn: sqlite3.Connection, applied_at: str) -> None:
    """Phase 4 organization: kinds, pins, trash, normalized tags."""
    columns = _table_columns(conn, "entries")
    if "kind" not in columns:
        conn.execute(
            "ALTER TABLE entries ADD COLUMN kind TEXT NOT NULL DEFAULT 'note'"
        )
    if "pinned" not in columns:
        conn.execute(
            "ALTER TABLE entries ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0"
        )
    if "trashed_at" not in columns:
        conn.execute("ALTER TABLE entries ADD COLUMN trashed_at TEXT")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE COLLATE NOCASE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS entry_tags (
            entry_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            PRIMARY KEY (entry_id, tag_id),
            FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_entries_pinned
            ON entries(pinned DESC, updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_entries_kind ON entries(kind);
        CREATE INDEX IF NOT EXISTS idx_entries_trashed_at ON entries(trashed_at);
        CREATE INDEX IF NOT EXISTS idx_entry_tags_tag_id ON entry_tags(tag_id);
        """
    )

    _migrate_csv_tags_into_tables(conn, applied_at)
    conn.executescript(FTS_TRIGGERS)
    _backfill_fts(conn)
    _mark_version(conn, 2, applied_at)


def _migrate_to_v3(conn: sqlite3.Connection, applied_at: str) -> None:
    """Phase 7 intelligence + sync: uids, tombstones, embeddings, sync state."""
    conn.executescript(FTS_TRIGGERS)
    if "uid" not in _table_columns(conn, "entries"):
        conn.execute("ALTER TABLE entries ADD COLUMN uid TEXT")
    missing = conn.execute(
        "SELECT id FROM entries WHERE uid IS NULL OR uid = ''"
    ).fetchall()
    for row in missing:
        conn.execute(
            "UPDATE entries SET uid = ? WHERE id = ?",
            (uuid.uuid4().hex, int(row[0])),
        )
    conn.executescript(INTELLIGENCE_SCHEMA)
    _mark_version(conn, 3, applied_at)


def _migrate_csv_tags_into_tables(conn: sqlite3.Connection, applied_at: str) -> None:
    rows = conn.execute("SELECT id, tags FROM entries").fetchall()
    for row in rows:
        entry_id = int(row["id"])
        raw = str(row["tags"] or "")
        if not raw.strip():
            continue
        for part in raw.split(","):
            name = part.strip().lower()
            if not name:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO tags(name, created_at) VALUES (?, ?)",
                (name, applied_at),
            )
            tag_row = conn.execute(
                "SELECT id FROM tags WHERE name = ?",
                (name,),
            ).fetchone()
            if tag_row is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO entry_tags(entry_id, tag_id) VALUES (?, ?)",
                (entry_id, int(tag_row[0])),
            )


def apply_migrations(conn: sqlite3.Connection, applied_at: str) -> None:
    """Bring the database schema up to CURRENT_SCHEMA_VERSION."""
    # Always ensure baseline objects exist for brand-new DBs.
    conn.executescript(BASE_SCHEMA)

    version = _current_version(conn)
    if version < 1:
        _migrate_to_v1(conn, applied_at)
        version = 1
    if version < 2:
        _migrate_to_v2(conn, applied_at)
        version = 2
    if version < 3:
        _migrate_to_v3(conn, applied_at)
