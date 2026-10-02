"""Canonical in-memory export document models for Phase 6 Part 1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from termvault import __version__
from termvault.config import VALID_KINDS
from termvault.models import Entry
from termvault.portability.constants import (
    EXPORT_FORMAT_NAME,
    EXPORT_FORMAT_VERSION,
)
from termvault.portability.errors import ImportValidationError


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ExportEntry:
    """One entry inside an export document (ids are source-vault hints)."""

    title: str
    body: str = ""
    tags: tuple[str, ...] = ()
    kind: str = "note"
    pinned: bool = False
    trashed: bool = False
    created_at: str | None = None
    updated_at: str | None = None
    source_id: int | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "title": self.title,
            "body": self.body,
            "tags": list(self.tags),
            "kind": self.kind,
            "pinned": self.pinned,
            "trashed": self.trashed,
        }
        if self.created_at is not None:
            payload["created_at"] = self.created_at
        if self.updated_at is not None:
            payload["updated_at"] = self.updated_at
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.content_hash is not None:
            payload["content_hash"] = self.content_hash
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any], *, path: str = "entry") -> ExportEntry:
        if not isinstance(raw, dict):
            raise ImportValidationError("Entry must be an object.", path=path)
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ImportValidationError("title is required.", path=f"{path}.title")
        body = raw.get("body", "")
        if body is None:
            body = ""
        if not isinstance(body, str):
            raise ImportValidationError("body must be a string.", path=f"{path}.body")
        tags_raw = raw.get("tags", [])
        if tags_raw is None:
            tags_raw = []
        if isinstance(tags_raw, str):
            tags = tuple(
                part.strip().lower()
                for part in tags_raw.split(",")
                if part.strip()
            )
        elif isinstance(tags_raw, list):
            tags = tuple(
                str(part).strip().lower()
                for part in tags_raw
                if str(part).strip()
            )
        else:
            raise ImportValidationError(
                "tags must be a list or comma string.",
                path=f"{path}.tags",
            )
        kind = str(raw.get("kind") or "note").strip().lower()
        if kind not in VALID_KINDS:
            raise ImportValidationError(
                f"kind must be one of {VALID_KINDS}.",
                path=f"{path}.kind",
            )
        pinned = bool(raw.get("pinned", False))
        trashed = bool(raw.get("trashed", False) or raw.get("trashed_at"))
        source_id = raw.get("source_id", raw.get("id"))
        if source_id is not None:
            try:
                source_id = int(source_id)
            except (TypeError, ValueError) as exc:
                raise ImportValidationError(
                    "source_id must be an integer.",
                    path=f"{path}.source_id",
                ) from exc
        created_at = raw.get("created_at")
        updated_at = raw.get("updated_at")
        if created_at is not None and not isinstance(created_at, str):
            raise ImportValidationError(
                "created_at must be a string.",
                path=f"{path}.created_at",
            )
        if updated_at is not None and not isinstance(updated_at, str):
            raise ImportValidationError(
                "updated_at must be a string.",
                path=f"{path}.updated_at",
            )
        content_hash = raw.get("content_hash")
        if content_hash is not None and not isinstance(content_hash, str):
            raise ImportValidationError(
                "content_hash must be a string.",
                path=f"{path}.content_hash",
            )
        return cls(
            title=title.strip(),
            body=body,
            tags=tags,
            kind=kind,
            pinned=pinned,
            trashed=trashed,
            created_at=created_at,
            updated_at=updated_at,
            source_id=source_id,
            content_hash=content_hash,
        )

    @classmethod
    def from_vault_entry(cls, entry: Entry, *, content_hash: str | None = None) -> ExportEntry:
        return cls(
            title=entry.title,
            body=entry.body,
            tags=entry.tags,
            kind=entry.kind,
            pinned=entry.pinned,
            trashed=entry.is_trashed,
            created_at=entry.created_at,
            updated_at=entry.updated_at,
            source_id=entry.id,
            content_hash=content_hash,
        )


@dataclass
class ExportManifest:
    """Integrity + summary metadata for an export document."""

    entry_count: int = 0
    active_count: int = 0
    trashed_count: int = 0
    pinned_count: int = 0
    kind_counts: dict[str, int] = field(default_factory=dict)
    tag_counts: dict[str, int] = field(default_factory=dict)
    content_hash: str | None = None
    hash_algo: str = "sha256"
    filters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> ExportManifest:
        if not raw:
            return cls()
        if not isinstance(raw, dict):
            raise ImportValidationError("manifest must be an object.", path="manifest")
        kind_counts = raw.get("kind_counts") or {}
        tag_counts = raw.get("tag_counts") or {}
        if not isinstance(kind_counts, dict) or not isinstance(tag_counts, dict):
            raise ImportValidationError(
                "kind_counts/tag_counts must be objects.",
                path="manifest",
            )
        return cls(
            entry_count=int(raw.get("entry_count") or 0),
            active_count=int(raw.get("active_count") or 0),
            trashed_count=int(raw.get("trashed_count") or 0),
            pinned_count=int(raw.get("pinned_count") or 0),
            kind_counts={str(k): int(v) for k, v in kind_counts.items()},
            tag_counts={str(k): int(v) for k, v in tag_counts.items()},
            content_hash=(
                str(raw["content_hash"]) if raw.get("content_hash") else None
            ),
            hash_algo=str(raw.get("hash_algo") or "sha256"),
            filters=dict(raw.get("filters") or {}),
        )


@dataclass
class ExportDocument:
    """Top-level portable vault snapshot."""

    entries: list[ExportEntry] = field(default_factory=list)
    format: str = EXPORT_FORMAT_NAME
    version: int = EXPORT_FORMAT_VERSION
    exported_at: str = field(default_factory=utc_now_iso)
    termvault_version: str = __version__
    manifest: ExportManifest = field(default_factory=ExportManifest)
    codec_hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "version": self.version,
            "exported_at": self.exported_at,
            "termvault_version": self.termvault_version,
            "manifest": self.manifest.to_dict(),
            "entries": [entry.to_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ExportDocument:
        if not isinstance(raw, dict):
            raise ImportValidationError("Document root must be an object.")
        fmt = str(raw.get("format") or EXPORT_FORMAT_NAME)
        if fmt != EXPORT_FORMAT_NAME:
            raise ImportValidationError(
                f"Unsupported format {fmt!r}; expected {EXPORT_FORMAT_NAME!r}.",
                path="format",
            )
        version = int(raw.get("version") or EXPORT_FORMAT_VERSION)
        if version < 1 or version > EXPORT_FORMAT_VERSION:
            raise ImportValidationError(
                f"Unsupported export version {version}.",
                path="version",
            )
        entries_raw = raw.get("entries")
        if entries_raw is None:
            entries_raw = []
        if not isinstance(entries_raw, list):
            raise ImportValidationError("entries must be a list.", path="entries")
        entries = [
            ExportEntry.from_dict(item, path=f"entries[{index}]")
            for index, item in enumerate(entries_raw)
        ]
        return cls(
            entries=entries,
            format=fmt,
            version=version,
            exported_at=str(raw.get("exported_at") or utc_now_iso()),
            termvault_version=str(raw.get("termvault_version") or "unknown"),
            manifest=ExportManifest.from_dict(raw.get("manifest")),
        )
