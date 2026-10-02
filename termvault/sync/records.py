"""The unit of sync: one entry (or tombstone) keyed by its stable uid."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any

from termvault.config import VALID_KINDS
from termvault.sync.errors import InvalidSnapshotError
from termvault.tags import normalize_tags


@dataclass(frozen=True)
class SyncRecord:
    uid: str
    title: str = ""
    body: str = ""
    tags: tuple[str, ...] = ()
    kind: str = "note"
    pinned: bool = False
    trashed_at: str | None = None
    created_at: str = ""
    updated_at: str = ""
    deleted_at: str | None = None

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def change_time(self) -> str:
        """When this version was produced; ISO-8601 UTC strings sort correctly."""
        return self.deleted_at if self.deleted_at is not None else self.updated_at

    @property
    def content_hash(self) -> str:
        """Hash of user-visible state; timestamps are excluded on purpose so that
        identical edits made on two devices are not reported as conflicts."""
        if self.is_deleted:
            payload: dict[str, Any] = {"deleted": True}
        else:
            payload = {
                "title": self.title,
                "body": self.body,
                "tags": list(self.tags),
                "kind": self.kind,
                "pinned": self.pinned,
                "trashed": self.trashed_at is not None,
            }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def as_conflict_copy(self, new_uid: str, suffix: str) -> SyncRecord:
        return replace(self, uid=new_uid, title=f"{self.title}{suffix}", deleted_at=None)

    def to_dict(self) -> dict[str, Any]:
        if self.is_deleted:
            return {"uid": self.uid, "deleted_at": self.deleted_at}
        return {
            "uid": self.uid,
            "title": self.title,
            "body": self.body,
            "tags": list(self.tags),
            "kind": self.kind,
            "pinned": self.pinned,
            "trashed_at": self.trashed_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def tombstone(cls, uid: str, deleted_at: str) -> SyncRecord:
        return cls(uid=uid, deleted_at=deleted_at)

    @classmethod
    def from_dict(cls, raw: Any) -> SyncRecord:
        if not isinstance(raw, dict):
            raise InvalidSnapshotError("Record must be an object.")
        uid = raw.get("uid")
        if not isinstance(uid, str) or not uid.strip():
            raise InvalidSnapshotError("Record is missing a uid.")
        if raw.get("deleted_at"):
            return cls.tombstone(uid, str(raw["deleted_at"]))
        title = raw.get("title")
        if not isinstance(title, str) or not title.strip():
            raise InvalidSnapshotError(f"Record {uid} has no title.")
        kind = str(raw.get("kind") or "note")
        if kind not in VALID_KINDS:
            raise InvalidSnapshotError(f"Record {uid} has invalid kind {kind!r}.")
        updated_at = raw.get("updated_at")
        if not isinstance(updated_at, str) or not updated_at:
            raise InvalidSnapshotError(f"Record {uid} has no updated_at.")
        try:
            tags = normalize_tags(list(raw.get("tags") or []))
        except Exception as exc:  # ValidationError from bad tag text
            raise InvalidSnapshotError(f"Record {uid} has invalid tags: {exc}") from exc
        trashed_at = raw.get("trashed_at")
        return cls(
            uid=uid,
            title=title,
            body=str(raw.get("body") or ""),
            tags=tags,
            kind=kind,
            pinned=bool(raw.get("pinned", False)),
            trashed_at=str(trashed_at) if trashed_at else None,
            created_at=str(raw.get("created_at") or updated_at),
            updated_at=updated_at,
        )


def newest(records: list[SyncRecord]) -> SyncRecord:
    """Pick the most recent version; ties break deterministically on hash."""
    return max(records, key=lambda record: (record.change_time, record.content_hash))
