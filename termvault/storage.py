"""CRUD, organization, and search operations for TermVault entries."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from termvault.config import VALID_KINDS, VALID_SORTS
from termvault.db import connect, initialize_database
from termvault.errors import EntryNotFoundError, ValidationError
from termvault.models import Entry, SearchHit, TagCount, VaultStats
from termvault.tags import (
    fetch_entry_tags,
    normalize_tags,
    rename_tag as rename_tag_in_db,
    set_entry_tags,
    tags_to_csv,
)

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_kind(kind: str | None) -> str:
    value = (kind or "note").strip().lower()
    if value not in VALID_KINDS:
        raise ValidationError(
            "Kind must be one of: " + ", ".join(VALID_KINDS)
        )
    return value


def build_fts_query(raw_query: str) -> str:
    """Turn user text into a safe FTS5 MATCH expression."""
    tokens = _TOKEN_RE.findall(raw_query.lower())
    if not tokens:
        raise ValidationError("Search query must contain letters or numbers.")
    return " AND ".join(f"{token}*" for token in tokens)


def _row_to_entry(row: object, tags: tuple[str, ...] | None = None) -> Entry:
    mapping = dict(row)  # type: ignore[arg-type]
    tag_values = tags
    if tag_values is None:
        tag_values = normalize_tags(str(mapping.get("tags") or "").split(","))
    return Entry(
        id=int(mapping["id"]),
        title=str(mapping["title"]),
        body=str(mapping["body"]),
        tags=tag_values,
        created_at=str(mapping["created_at"]),
        updated_at=str(mapping["updated_at"]),
        kind=str(mapping.get("kind") or "note"),
        pinned=bool(int(mapping.get("pinned") or 0)),
        trashed_at=(
            str(mapping["trashed_at"])
            if mapping.get("trashed_at") is not None
            else None
        ),
    )


def _load_entry(
    conn: object,
    entry_id: int,
    *,
    include_trashed: bool = False,
) -> Entry:
    row = conn.execute(  # type: ignore[attr-defined]
        """
        SELECT id, title, body, tags, created_at, updated_at, kind, pinned, trashed_at
        FROM entries
        WHERE id = ?
        """,
        (entry_id,),
    ).fetchone()
    if row is None:
        raise EntryNotFoundError(entry_id)
    entry = _row_to_entry(row, tags=fetch_entry_tags(conn, entry_id))  # type: ignore[arg-type]
    if entry.is_trashed and not include_trashed:
        raise EntryNotFoundError(entry_id, trashed=True)
    return entry


def add_entry(
    title: str,
    body: str = "",
    tags: list[str] | None = None,
    *,
    kind: str = "note",
    pinned: bool = False,
) -> Entry:
    """Create a new vault entry and return it."""
    cleaned_title = title.strip()
    if not cleaned_title:
        raise ValidationError("Title is required.")

    normalized = normalize_tags(tags)
    entry_kind = normalize_kind(kind)
    initialize_database()
    now = _utc_now()

    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO entries (
                title, body, tags, created_at, updated_at, kind, pinned, trashed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                cleaned_title,
                body,
                tags_to_csv(normalized),
                now,
                now,
                entry_kind,
                1 if pinned else 0,
            ),
        )
        entry_id = int(cursor.lastrowid)
        set_entry_tags(conn, entry_id, normalized, updated_at=now)
        return _load_entry(conn, entry_id)


def list_entries(
    limit: int = 20,
    *,
    tag: str | None = None,
    kind: str | None = None,
    sort: str = "updated",
    pinned_only: bool = False,
    include_trashed: bool = False,
    trashed_only: bool = False,
) -> list[Entry]:
    """Return entries with organization filters."""
    if limit < 1:
        raise ValidationError("Limit must be at least 1.")

    sort_key = sort.strip().lower()
    if sort_key not in VALID_SORTS:
        raise ValidationError("Sort must be one of: " + ", ".join(VALID_SORTS))

    order_by = {
        "updated": "e.pinned DESC, e.updated_at DESC, e.id DESC",
        "created": "e.pinned DESC, e.created_at DESC, e.id DESC",
        "title": "e.pinned DESC, e.title COLLATE NOCASE ASC, e.id ASC",
    }[sort_key]

    initialize_database()
    clauses: list[str] = []
    params: list[object] = []

    if trashed_only:
        clauses.append("e.trashed_at IS NOT NULL")
    elif not include_trashed:
        clauses.append("e.trashed_at IS NULL")

    if pinned_only:
        clauses.append("e.pinned = 1")

    if kind is not None:
        clauses.append("e.kind = ?")
        params.append(normalize_kind(kind))

    if tag is not None:
        normalized = normalize_tags([tag])
        if not normalized:
            raise ValidationError("Tag is required.")
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM entry_tags AS et
                JOIN tags AS t ON t.id = et.tag_id
                WHERE et.entry_id = e.id AND t.name = ?
            )
            """
        )
        params.append(normalized[0])

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(limit)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT e.id, e.title, e.body, e.tags, e.created_at, e.updated_at,
                   e.kind, e.pinned, e.trashed_at
            FROM entries AS e
            {where}
            ORDER BY {order_by}
            LIMIT ?
            """,
            params,
        ).fetchall()
        return [
            _row_to_entry(row, tags=fetch_entry_tags(conn, int(row["id"])))
            for row in rows
        ]


def recent_entries(limit: int = 10) -> list[Entry]:
    """Return the most recently updated active entries."""
    return list_entries(limit=limit, sort="updated")


def get_entry(entry_id: int, *, include_trashed: bool = False) -> Entry:
    """Fetch a single entry by id."""
    initialize_database()
    with connect() as conn:
        return _load_entry(conn, entry_id, include_trashed=include_trashed)


def update_entry(
    entry_id: int,
    *,
    title: str | None = None,
    body: str | None = None,
    tags: list[str] | None = None,
    kind: str | None = None,
) -> Entry:
    """Update fields on an existing active entry."""
    initialize_database()
    now = _utc_now()
    with connect() as conn:
        current = _load_entry(conn, entry_id)

        new_title = current.title if title is None else title.strip()
        if not new_title:
            raise ValidationError("Title is required.")

        new_body = current.body if body is None else body
        new_kind = current.kind if kind is None else normalize_kind(kind)
        new_tags = current.tags if tags is None else normalize_tags(tags)

        conn.execute(
            """
            UPDATE entries
            SET title = ?, body = ?, kind = ?, updated_at = ?
            WHERE id = ?
            """,
            (new_title, new_body, new_kind, now, entry_id),
        )
        if tags is not None:
            set_entry_tags(conn, entry_id, new_tags, updated_at=now)
        else:
            conn.execute(
                "UPDATE entries SET updated_at = ? WHERE id = ?",
                (now, entry_id),
            )
        return _load_entry(conn, entry_id)


def delete_entry(entry_id: int, *, permanent: bool = False) -> Entry:
    """Soft-delete an entry, or permanently delete when requested."""
    initialize_database()
    now = _utc_now()
    with connect() as conn:
        entry = _load_entry(conn, entry_id, include_trashed=True)
        if permanent:
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            return entry
        if entry.is_trashed:
            return entry
        conn.execute(
            "UPDATE entries SET trashed_at = ?, updated_at = ?, pinned = 0 WHERE id = ?",
            (now, now, entry_id),
        )
        return _load_entry(conn, entry_id, include_trashed=True)


def restore_entry(entry_id: int) -> Entry:
    """Restore an entry from the trash."""
    initialize_database()
    now = _utc_now()
    with connect() as conn:
        entry = _load_entry(conn, entry_id, include_trashed=True)
        if not entry.is_trashed:
            raise ValidationError(f"Entry {entry_id} is not in the trash.")
        conn.execute(
            "UPDATE entries SET trashed_at = NULL, updated_at = ? WHERE id = ?",
            (now, entry_id),
        )
        return _load_entry(conn, entry_id)


def purge_trashed() -> int:
    """Permanently delete all trashed entries. Returns deleted count."""
    initialize_database()
    with connect() as conn:
        cur = conn.execute("DELETE FROM entries WHERE trashed_at IS NOT NULL")
        return int(cur.rowcount)


def set_pinned(entry_id: int, pinned: bool) -> Entry:
    """Pin or unpin an active entry."""
    initialize_database()
    now = _utc_now()
    with connect() as conn:
        _load_entry(conn, entry_id)
        conn.execute(
            "UPDATE entries SET pinned = ?, updated_at = ? WHERE id = ?",
            (1 if pinned else 0, now, entry_id),
        )
        return _load_entry(conn, entry_id)


def list_tags() -> list[TagCount]:
    """Return tags with active (non-trashed) usage counts."""
    initialize_database()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT t.name AS name, COUNT(et.entry_id) AS count
            FROM tags AS t
            JOIN entry_tags AS et ON et.tag_id = t.id
            JOIN entries AS e ON e.id = et.entry_id
            WHERE e.trashed_at IS NULL
            GROUP BY t.id, t.name
            ORDER BY count DESC, t.name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [TagCount(name=str(row["name"]), count=int(row["count"])) for row in rows]


def add_tag(entry_id: int, tag: str) -> Entry:
    """Add a tag to an active entry."""
    normalized = normalize_tags([tag])
    entry = get_entry(entry_id)
    if normalized[0] in entry.tags:
        return entry
    merged = normalize_tags([*entry.tags, *normalized])
    return update_entry(entry_id, tags=list(merged))


def remove_tag(entry_id: int, tag: str) -> Entry:
    """Remove a tag from an active entry."""
    normalized = normalize_tags([tag])
    entry = get_entry(entry_id)
    if normalized[0] not in entry.tags:
        raise ValidationError(f"Entry {entry_id} does not have tag '{normalized[0]}'.")
    remaining = tuple(t for t in entry.tags if t != normalized[0])
    return update_entry(entry_id, tags=list(remaining))


def rename_tag(old_name: str, new_name: str) -> int:
    """Rename a tag across all entries."""
    initialize_database()
    now = _utc_now()
    with connect() as conn:
        return rename_tag_in_db(conn, old_name, new_name, updated_at=now)


def vault_stats() -> VaultStats:
    """Collect organization stats for the local vault."""
    initialize_database()
    with connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        trashed = int(
            conn.execute(
                "SELECT COUNT(*) FROM entries WHERE trashed_at IS NOT NULL"
            ).fetchone()[0]
        )
        active = total - trashed
        pinned = int(
            conn.execute(
                """
                SELECT COUNT(*) FROM entries
                WHERE pinned = 1 AND trashed_at IS NULL
                """
            ).fetchone()[0]
        )
        tag_count = int(conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0])
        kind_rows = conn.execute(
            """
            SELECT kind, COUNT(*) AS count
            FROM entries
            WHERE trashed_at IS NULL
            GROUP BY kind
            """
        ).fetchall()
        kind_counts = {str(row["kind"]): int(row["count"]) for row in kind_rows}

    top_tags = tuple(list_tags()[:5])
    return VaultStats(
        total_entries=total,
        active_entries=active,
        trashed_entries=trashed,
        pinned_entries=pinned,
        tag_count=tag_count,
        kind_counts=kind_counts,
        top_tags=top_tags,
    )


def search_entries(
    query: str,
    limit: int = 10,
    *,
    tag: str | None = None,
    kind: str | None = None,
) -> list[SearchHit]:
    """Full-text search active entries, best matches first."""
    if limit < 1:
        raise ValidationError("Limit must be at least 1.")

    fts_query = build_fts_query(query)
    initialize_database()

    clauses = ["entries_fts MATCH ?", "e.trashed_at IS NULL"]
    params: list[object] = [fts_query]

    if kind is not None:
        clauses.append("e.kind = ?")
        params.append(normalize_kind(kind))

    if tag is not None:
        normalized = normalize_tags([tag])
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM entry_tags AS et
                JOIN tags AS t ON t.id = et.tag_id
                WHERE et.entry_id = e.id AND t.name = ?
            )
            """
        )
        params.append(normalized[0])

    params.append(limit)
    where = " AND ".join(clauses)

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                e.id,
                e.title,
                e.body,
                e.tags,
                e.created_at,
                e.updated_at,
                e.kind,
                e.pinned,
                e.trashed_at,
                bm25(entries_fts) AS rank,
                snippet(entries_fts, 1, '', '', '…', 12) AS snippet
            FROM entries_fts
            JOIN entries AS e ON e.id = entries_fts.rowid
            WHERE {where}
            ORDER BY e.pinned DESC, rank
            LIMIT ?
            """,
            params,
        ).fetchall()

        hits: list[SearchHit] = []
        for row in rows:
            entry = _row_to_entry(
                row,
                tags=fetch_entry_tags(conn, int(row["id"])),
            )
            snippet = str(row["snippet"] or "").strip()
            if not snippet:
                snippet = entry.body.strip().replace("\n", " ")
                if len(snippet) > 80:
                    snippet = snippet[:77] + "..."
            hits.append(
                SearchHit(
                    entry=entry,
                    rank=float(row["rank"]),
                    snippet=snippet,
                )
            )
        return hits
