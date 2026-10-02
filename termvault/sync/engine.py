"""Run a sync: read snapshots, merge, apply locally, publish our snapshot.

Remote versions are written with direct SQL so their original ``created_at`` /
``updated_at`` survive; going through ``storage.update_entry`` would stamp
"now" and make every device think the entry changed again.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from termvault import __version__
from termvault.db import connect, initialize_database
from termvault.sync.config import (
    SyncConfig,
    ensure_folder_available,
    load_sync_config,
    mark_synced,
    normalize_policy,
    require_sync_config,
)
from termvault.sync.merge import MergePlan, plan_merge
from termvault.sync.records import SyncRecord
from termvault.sync.snapshot import (
    DeviceSnapshot,
    RemoteView,
    read_remote_snapshots,
    write_snapshot,
)
from termvault.sync.state import (
    read_local_records,
    read_sync_state,
    uid_to_entry_id,
    write_sync_state,
)
from termvault.tags import set_entry_tags, tags_to_csv


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    device_name: str
    written_at: str
    live: int
    tombstones: int

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.device_id,
            "name": self.device_name,
            "written_at": self.written_at,
            "entries": self.live,
            "tombstones": self.tombstones,
        }


@dataclass
class SyncStatus:
    config: SyncConfig | None
    devices: list[DeviceInfo] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    plan: MergePlan | None = None
    folder_available: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": bool(self.config and self.config.enabled),
            "config": self.config.to_dict() if self.config else None,
            "folder_available": self.folder_available,
            "devices": [device.to_dict() for device in self.devices],
            "problems": list(self.problems),
            "pending": self.plan.to_dict() if self.plan else None,
        }


@dataclass
class SyncResult:
    config: SyncConfig
    plan: MergePlan
    dry_run: bool
    synced_at: str
    snapshot_path: Path | None = None
    remote_devices: int = 0
    problems: list[str] = field(default_factory=list)
    created: int = 0
    updated: int = 0
    deleted: int = 0
    conflict_copies: int = 0
    backup_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "dry_run": self.dry_run,
            "synced_at": self.synced_at,
            "device": {"id": self.config.device_id, "name": self.config.device_name},
            "folder": self.config.folder,
            "snapshot": str(self.snapshot_path) if self.snapshot_path else None,
            "remote_devices": self.remote_devices,
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "conflict_copies": self.conflict_copies,
            "backup": str(self.backup_path) if self.backup_path else None,
            "problems": list(self.problems),
            "plan": self.plan.to_dict(),
        }


def _device_infos(view: RemoteView) -> list[DeviceInfo]:
    return [
        DeviceInfo(
            device_id=snapshot.device_id,
            device_name=snapshot.device_name,
            written_at=snapshot.written_at,
            live=snapshot.live_count,
            tombstones=snapshot.tombstone_count,
        )
        for snapshot in view.snapshots
    ]


def _build_plan(
    conn: sqlite3.Connection,
    view: RemoteView,
    *,
    policy: str,
    conflict_copies: bool,
) -> MergePlan:
    return plan_merge(
        read_local_records(conn),
        view.merged_records(),
        read_sync_state(conn),
        policy=policy,
        conflict_copies=conflict_copies,
    )


def sync_status(*, policy: str | None = None) -> SyncStatus:
    """Describe sync config and what a run would do, without changing anything."""
    config = load_sync_config()
    status = SyncStatus(config=config)
    if config is None or not config.enabled:
        return status
    status.folder_available = config.folder_path.is_dir()
    if not status.folder_available:
        return status
    view = read_remote_snapshots(config.devices_dir, exclude_device=config.device_id)
    status.devices = _device_infos(view)
    status.problems = view.problems
    initialize_database()
    with connect() as conn:
        status.plan = _build_plan(
            conn,
            view,
            policy=normalize_policy(policy or config.policy),
            conflict_copies=True,
        )
    return status


def _write_entry(conn: sqlite3.Connection, record: SyncRecord, uid_map: dict[str, int]) -> str:
    """Create or overwrite the local entry for ``record``; returns create/update."""
    conn.execute("DELETE FROM entry_tombstones WHERE uid = ?", (record.uid,))
    entry_id = uid_map.get(record.uid)
    values = (
        record.title,
        record.body,
        tags_to_csv(record.tags),
        record.kind,
        1 if record.pinned else 0,
        record.trashed_at,
        record.created_at or record.updated_at,
        record.updated_at,
    )
    if entry_id is None:
        cursor = conn.execute(
            """
            INSERT INTO entries
                (title, body, tags, kind, pinned, trashed_at, created_at, updated_at, uid)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*values, record.uid),
        )
        entry_id = int(cursor.lastrowid)
        uid_map[record.uid] = entry_id
        outcome = "create"
    else:
        conn.execute(
            """
            UPDATE entries
            SET title = ?, body = ?, tags = ?, kind = ?, pinned = ?, trashed_at = ?,
                created_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (*values, entry_id),
        )
        outcome = "update"
    set_entry_tags(conn, entry_id, record.tags, updated_at=record.updated_at)
    return outcome


def _write_tombstone(conn: sqlite3.Connection, record: SyncRecord, uid_map: dict[str, int]) -> bool:
    """Delete the local entry (if any) and keep the remote deletion time."""
    entry_id = uid_map.pop(record.uid, None)
    if entry_id is not None:
        conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.execute(
        "INSERT OR REPLACE INTO entry_tombstones(uid, deleted_at) VALUES (?, ?)",
        (record.uid, record.deleted_at),
    )
    return entry_id is not None


def apply_plan(conn: sqlite3.Connection, plan: MergePlan, result: SyncResult) -> None:
    uid_map = uid_to_entry_id(conn)
    for action in plan.local_changes:
        if action.copy is not None:
            _write_entry(conn, action.copy, uid_map)
            result.conflict_copies += 1
        record = action.apply
        if record is None:
            continue
        if record.is_deleted:
            if _write_tombstone(conn, record, uid_map):
                result.deleted += 1
        elif _write_entry(conn, record, uid_map) == "create":
            result.created += 1
        else:
            result.updated += 1


def _safety_backup() -> Path:
    from termvault.backup import create_backup

    return create_backup(label="pre-sync").path


def run_sync(
    *,
    dry_run: bool = False,
    policy: str | None = None,
    conflict_copies: bool = True,
    backup: bool = False,
) -> SyncResult:
    """Merge with other devices' snapshots and publish this device's snapshot."""
    config = require_sync_config()
    ensure_folder_available(config)
    chosen_policy = normalize_policy(policy or config.policy)
    view = read_remote_snapshots(config.devices_dir, exclude_device=config.device_id)
    synced_at = _utc_now()
    initialize_database()

    with connect() as conn:
        plan = _build_plan(conn, view, policy=chosen_policy, conflict_copies=conflict_copies)
    result = SyncResult(
        config=config,
        plan=plan,
        dry_run=dry_run,
        synced_at=synced_at,
        remote_devices=len(view.snapshots),
        problems=list(view.problems),
    )
    if dry_run:
        return result

    if backup and plan.local_changes:
        result.backup_path = _safety_backup()

    with connect() as conn:
        apply_plan(conn, plan, result)
        records = read_local_records(conn)
        write_sync_state(
            conn,
            {uid: record.content_hash for uid, record in records.items()},
            synced_at,
        )

    snapshot = DeviceSnapshot(
        device_id=config.device_id,
        device_name=config.device_name,
        written_at=synced_at,
        records=list(records.values()),
        app_version=__version__,
    )
    result.snapshot_path = write_snapshot(config.snapshot_path, snapshot)
    result.config = mark_synced(config, synced_at)
    return result
