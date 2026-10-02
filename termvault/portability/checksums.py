"""Content hashing helpers for export integrity."""

from __future__ import annotations

import hashlib
import json
from typing import Iterable

from termvault.portability.constants import MANIFEST_HASH_ALGO
from termvault.portability.schema import ExportEntry


def normalize_for_hash(
    *,
    title: str,
    body: str,
    tags: Iterable[str],
    kind: str,
) -> str:
    """Stable canonical string used for content_hash comparisons."""
    tag_list = sorted({tag.strip().lower() for tag in tags if tag.strip()})
    payload = {
        "title": title.strip(),
        "body": body.replace("\r\n", "\n"),
        "tags": tag_list,
        "kind": kind.strip().lower(),
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def hash_text(text: str, *, algo: str = MANIFEST_HASH_ALGO) -> str:
    digest = hashlib.new(algo)
    digest.update(text.encode("utf-8"))
    return digest.hexdigest()


def entry_content_hash(entry: ExportEntry, *, algo: str = MANIFEST_HASH_ALGO) -> str:
    return hash_text(
        normalize_for_hash(
            title=entry.title,
            body=entry.body,
            tags=entry.tags,
            kind=entry.kind,
        ),
        algo=algo,
    )


def hash_entries(entries: Iterable[ExportEntry], *, algo: str = MANIFEST_HASH_ALGO) -> str:
    """Aggregate hash over ordered entry content hashes."""
    digest = hashlib.new(algo)
    for entry in entries:
        digest.update(entry_content_hash(entry, algo=algo).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def short_hash(value: str, *, length: int = 12) -> str:
    return value[:length]
