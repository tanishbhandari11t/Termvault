"""Normalized tag helpers kept in sync with denormalized FTS tag text."""

from __future__ import annotations

import sqlite3

from termvault.errors import TagNotFoundError, ValidationError


def normalize_tag_name(raw: str) -> str:
    """Normalize a single tag name."""
    tag = raw.strip().lower()
    if not tag:
        raise ValidationError("Tag is required.")
    if any(ch in tag for ch in {",", "\n", "\t"}):
        raise ValidationError("Tags cannot contain commas or whitespace control chars.")
    if len(tag) > 64:
        raise ValidationError("Tags must be 64 characters or fewer.")
    return tag


def normalize_tags(tags: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Normalize tag input into a de-duplicated, sorted tuple."""
    if not tags:
        return ()
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            tag = normalize_tag_name(part)
            if tag in seen:
                continue
            seen.add(tag)
            cleaned.append(tag)
    return tuple(sorted(cleaned))


def tags_to_csv(tags: tuple[str, ...]) -> str:
    return ",".join(tags)


def ensure_tag(conn: sqlite3.Connection, name: str, created_at: str) -> int:
    """Insert tag if needed and return its id."""
    normalized = normalize_tag_name(name)
    conn.execute(
        "INSERT OR IGNORE INTO tags(name, created_at) VALUES (?, ?)",
        (normalized, created_at),
    )
    row = conn.execute("SELECT id FROM tags WHERE name = ?", (normalized,)).fetchone()
    if row is None:
        raise TagNotFoundError(normalized)
    return int(row[0])


def set_entry_tags(
    conn: sqlite3.Connection,
    entry_id: int,
    tags: tuple[str, ...],
    *,
    updated_at: str,
) -> None:
    """Replace an entry's normalized tags and refresh the CSV cache column."""
    conn.execute("DELETE FROM entry_tags WHERE entry_id = ?", (entry_id,))
    for name in tags:
        tag_id = ensure_tag(conn, name, updated_at)
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags(entry_id, tag_id) VALUES (?, ?)",
            (entry_id, tag_id),
        )
    conn.execute(
        "UPDATE entries SET tags = ?, updated_at = ? WHERE id = ?",
        (tags_to_csv(tags), updated_at, entry_id),
    )


def fetch_entry_tags(conn: sqlite3.Connection, entry_id: int) -> tuple[str, ...]:
    rows = conn.execute(
        """
        SELECT t.name
        FROM tags AS t
        JOIN entry_tags AS et ON et.tag_id = t.id
        WHERE et.entry_id = ?
        ORDER BY t.name COLLATE NOCASE
        """,
        (entry_id,),
    ).fetchall()
    return tuple(str(row[0]) for row in rows)


def rename_tag(
    conn: sqlite3.Connection,
    old_name: str,
    new_name: str,
    *,
    updated_at: str,
) -> int:
    """Rename a tag across the vault. Returns number of entries updated."""
    old = normalize_tag_name(old_name)
    new = normalize_tag_name(new_name)
    if old == new:
        return 0

    old_row = conn.execute("SELECT id FROM tags WHERE name = ?", (old,)).fetchone()
    if old_row is None:
        raise TagNotFoundError(old)
    old_id = int(old_row[0])

    new_id = ensure_tag(conn, new, updated_at)
    entry_ids = [
        int(row[0])
        for row in conn.execute(
            "SELECT entry_id FROM entry_tags WHERE tag_id = ?",
            (old_id,),
        ).fetchall()
    ]

    for entry_id in entry_ids:
        conn.execute(
            "INSERT OR IGNORE INTO entry_tags(entry_id, tag_id) VALUES (?, ?)",
            (entry_id, new_id),
        )
        conn.execute(
            "DELETE FROM entry_tags WHERE entry_id = ? AND tag_id = ?",
            (entry_id, old_id),
        )
        tags = fetch_entry_tags(conn, entry_id)
        conn.execute(
            "UPDATE entries SET tags = ?, updated_at = ? WHERE id = ?",
            (tags_to_csv(tags), updated_at, entry_id),
        )

    # Remove old tag if unused.
    remaining = conn.execute(
        "SELECT COUNT(*) FROM entry_tags WHERE tag_id = ?",
        (old_id,),
    ).fetchone()
    if int(remaining[0]) == 0 and old_id != new_id:
        conn.execute("DELETE FROM tags WHERE id = ?", (old_id,))

    return len(entry_ids)
