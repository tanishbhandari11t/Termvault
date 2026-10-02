"""Persistent embedding index stored in ``entry_embeddings``.

Each row records the backend key and a content hash, so the index refreshes
incrementally: only new or edited entries are re-embedded.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone

from termvault import storage
from termvault.db import connect, initialize_database
from termvault.intelligence.constants import EMBED_BATCH_SIZE, SEMANTIC_MIN_SCORE
from termvault.intelligence.corpus import filter_entries, load_corpus
from termvault.intelligence.embeddings import (
    EmbeddingBackend,
    backend_from_key,
    get_backend,
)
from termvault.intelligence.errors import IntelligenceError
from termvault.intelligence.vectors import pack, top_k, unpack
from termvault.models import Entry


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def entry_document_text(entry: Entry) -> str:
    """Text that gets embedded; the title is repeated to give it extra weight."""
    tags = " ".join(entry.tags)
    return f"{entry.title}\n{entry.title}\n{tags}\n{entry.kind}\n{entry.body}"


def document_hash(entry: Entry, backend_key: str) -> str:
    digest = hashlib.sha256()
    digest.update(backend_key.encode("utf-8"))
    digest.update(b"\0")
    digest.update(entry_document_text(entry).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class IndexStatus:
    active_entries: int
    indexed: int
    fresh: int
    stale: int
    missing: int
    orphaned: int
    backends: dict[str, int]
    backend_key: str | None

    @property
    def is_current(self) -> bool:
        return self.stale == 0 and self.missing == 0 and self.orphaned == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "active_entries": self.active_entries,
            "indexed": self.indexed,
            "fresh": self.fresh,
            "stale": self.stale,
            "missing": self.missing,
            "orphaned": self.orphaned,
            "backends": dict(self.backends),
            "backend": self.backend_key,
            "current": self.is_current,
        }


@dataclass
class IndexBuildReport:
    backend_key: str
    embedded: int = 0
    unchanged: int = 0
    removed: int = 0
    embedded_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "backend": self.backend_key,
            "embedded": self.embedded,
            "unchanged": self.unchanged,
            "removed": self.removed,
            "embedded_ids": list(self.embedded_ids),
        }


@dataclass(frozen=True)
class SemanticHit:
    entry: Entry
    score: float


def _index_rows() -> dict[int, tuple[str, str]]:
    initialize_database()
    with connect() as conn:
        rows = conn.execute(
            "SELECT entry_id, backend, content_hash FROM entry_embeddings"
        ).fetchall()
    return {int(row["entry_id"]): (str(row["backend"]), str(row["content_hash"])) for row in rows}


def current_backend_key() -> str | None:
    """The backend most rows were built with, or ``None`` if the index is empty."""
    counts = Counter(backend for backend, _ in _index_rows().values())
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def resolve_backend(spec: str | None = None) -> EmbeddingBackend:
    """Explicit spec wins; otherwise reuse whatever the index was built with."""
    if spec:
        return get_backend(spec)
    key = current_backend_key()
    return backend_from_key(key) if key else get_backend(None)


def index_status(backend: EmbeddingBackend | None = None) -> IndexStatus:
    rows = _index_rows()
    entries = load_corpus()
    key = backend.key if backend is not None else current_backend_key()
    active_ids = {entry.id for entry in entries}
    fresh = stale = missing = 0
    for entry in entries:
        row = rows.get(entry.id)
        if row is None:
            missing += 1
        elif key is not None and row == (key, document_hash(entry, key)):
            fresh += 1
        else:
            stale += 1
    orphaned = sum(1 for entry_id in rows if entry_id not in active_ids)
    return IndexStatus(
        active_entries=len(entries),
        indexed=len(rows),
        fresh=fresh,
        stale=stale,
        missing=missing,
        orphaned=orphaned,
        backends=dict(Counter(backend for backend, _ in rows.values())),
        backend_key=key,
    )


def build_index(
    backend: EmbeddingBackend | None = None,
    *,
    rebuild: bool = False,
    batch_size: int = EMBED_BATCH_SIZE,
) -> IndexBuildReport:
    """Embed new / changed active entries and drop rows for trashed ones."""
    if batch_size < 1:
        raise IntelligenceError("Batch size must be at least 1.")
    chosen = backend or resolve_backend()
    key = chosen.key
    entries = load_corpus()
    rows = {} if rebuild else _index_rows()
    report = IndexBuildReport(backend_key=key)

    pending: list[tuple[Entry, str]] = []
    for entry in entries:
        content_hash = document_hash(entry, key)
        if rows.get(entry.id) == (key, content_hash):
            report.unchanged += 1
        else:
            pending.append((entry, content_hash))

    now = _utc_now()
    vectors: list[tuple[Entry, str, list[float]]] = []
    for start in range(0, len(pending), batch_size):
        batch = pending[start : start + batch_size]
        embedded = chosen.embed([entry_document_text(entry) for entry, _ in batch])
        vectors.extend((entry, content_hash, vector) for (entry, content_hash), vector in zip(batch, embedded))

    initialize_database()
    with connect() as conn:
        if rebuild:
            conn.execute("DELETE FROM entry_embeddings")
        for entry, content_hash, vector in vectors:
            conn.execute(
                """
                INSERT OR REPLACE INTO entry_embeddings
                    (entry_id, backend, dim, content_hash, vector, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entry.id, key, len(vector), content_hash, pack(vector), now),
            )
            report.embedded += 1
            report.embedded_ids.append(entry.id)
        cursor = conn.execute(
            """
            DELETE FROM entry_embeddings
            WHERE entry_id NOT IN (SELECT id FROM entries WHERE trashed_at IS NULL)
            """
        )
        report.removed = max(int(cursor.rowcount), 0)
    return report


def clear_index() -> int:
    initialize_database()
    with connect() as conn:
        cursor = conn.execute("DELETE FROM entry_embeddings")
        return int(cursor.rowcount)


def load_vectors(backend_key: str) -> dict[int, list[float]]:
    initialize_database()
    with connect() as conn:
        rows = conn.execute(
            "SELECT entry_id, vector FROM entry_embeddings WHERE backend = ?",
            (backend_key,),
        ).fetchall()
    return {int(row["entry_id"]): list(unpack(bytes(row["vector"]))) for row in rows}


def semantic_search(
    query: str,
    *,
    limit: int = 10,
    tag: str | None = None,
    kind: str | None = None,
    backend: EmbeddingBackend | None = None,
    min_score: float = SEMANTIC_MIN_SCORE,
    refresh: bool = True,
) -> list[SemanticHit]:
    """Rank active entries by embedding similarity to ``query``."""
    if not query.strip():
        raise IntelligenceError("Query must not be empty.")
    chosen = backend or resolve_backend()
    if refresh:
        build_index(chosen)
    entries = filter_entries(load_corpus(), tag=tag, kind=kind)
    by_id = {entry.id: entry for entry in entries}
    vectors = load_vectors(chosen.key)
    query_vector = chosen.embed([query])[0]
    ranked = top_k(
        query_vector,
        ((entry_id, vector) for entry_id, vector in vectors.items() if entry_id in by_id),
        limit,
        min_score=min_score,
    )
    return [SemanticHit(entry=by_id[entry_id], score=score) for entry_id, score in ranked]


def related_entries(
    entry_id: int,
    *,
    limit: int = 5,
    backend: EmbeddingBackend | None = None,
    min_score: float = SEMANTIC_MIN_SCORE,
) -> tuple[Entry, list[SemanticHit]]:
    """Entries most similar to an existing one (excluding itself)."""
    source = storage.get_entry(entry_id, include_trashed=True)
    chosen = backend or resolve_backend()
    build_index(chosen)
    entries = {entry.id: entry for entry in load_corpus()}
    vectors = load_vectors(chosen.key)
    source_vector = vectors.get(entry_id)
    if source_vector is None:
        source_vector = chosen.embed([entry_document_text(source)])[0]
    ranked = top_k(
        source_vector,
        (
            (other_id, vector)
            for other_id, vector in vectors.items()
            if other_id != entry_id and other_id in entries
        ),
        limit,
        min_score=min_score,
    )
    return source, [SemanticHit(entry=entries[other_id], score=score) for other_id, score in ranked]
