"""Per-device snapshot files in ``<folder>/termvault-sync/devices/<id>.json``.

Each device only ever writes its own file, so cloud-drive sync tools never see
two writers on the same file.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from termvault.sync.constants import MAX_SNAPSHOT_BYTES, SNAPSHOT_FORMAT, SNAPSHOT_VERSION
from termvault.sync.errors import InvalidSnapshotError
from termvault.sync.records import SyncRecord, newest


@dataclass
class DeviceSnapshot:
    device_id: str
    device_name: str
    written_at: str
    records: list[SyncRecord] = field(default_factory=list)
    app_version: str = ""

    @property
    def live_count(self) -> int:
        return sum(1 for record in self.records if not record.is_deleted)

    @property
    def tombstone_count(self) -> int:
        return sum(1 for record in self.records if record.is_deleted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": SNAPSHOT_FORMAT,
            "version": SNAPSHOT_VERSION,
            "device": {"id": self.device_id, "name": self.device_name},
            "app_version": self.app_version,
            "written_at": self.written_at,
            "records": [record.to_dict() for record in sorted(self.records, key=lambda r: r.uid)],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> DeviceSnapshot:
        if not isinstance(raw, dict) or raw.get("format") != SNAPSHOT_FORMAT:
            raise InvalidSnapshotError("Not a TermVault sync snapshot.")
        version = raw.get("version")
        if not isinstance(version, int) or version > SNAPSHOT_VERSION:
            raise InvalidSnapshotError(
                f"Snapshot version {version!r} is newer than this TermVault supports."
            )
        device = raw.get("device")
        if not isinstance(device, dict) or not device.get("id"):
            raise InvalidSnapshotError("Snapshot is missing device info.")
        records_raw = raw.get("records")
        if not isinstance(records_raw, list):
            raise InvalidSnapshotError("Snapshot records must be a list.")
        return cls(
            device_id=str(device["id"]),
            device_name=str(device.get("name") or device["id"]),
            written_at=str(raw.get("written_at") or ""),
            records=[SyncRecord.from_dict(item) for item in records_raw],
            app_version=str(raw.get("app_version") or ""),
        )


def write_snapshot(path: Path, snapshot: DeviceSnapshot) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".partial")
    temp.write_text(
        json.dumps(snapshot.to_dict(), indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temp, path)
    return path


def read_snapshot(path: Path) -> DeviceSnapshot:
    try:
        if path.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise InvalidSnapshotError(f"{path.name} is larger than the snapshot size limit.")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidSnapshotError(f"{path.name}: {exc}") from exc
    snapshot = DeviceSnapshot.from_dict(raw)
    if snapshot.device_id != path.stem:
        raise InvalidSnapshotError(
            f"{path.name}: device id {snapshot.device_id!r} does not match file name."
        )
    return snapshot


@dataclass
class RemoteView:
    snapshots: list[DeviceSnapshot]
    problems: list[str]

    def merged_records(self) -> dict[str, SyncRecord]:
        """Newest version of each uid across all other devices."""
        grouped: dict[str, list[SyncRecord]] = {}
        for snapshot in self.snapshots:
            for record in snapshot.records:
                grouped.setdefault(record.uid, []).append(record)
        return {uid: newest(versions) for uid, versions in grouped.items()}

    def device_for(self, uid: str, record: SyncRecord) -> str:
        for snapshot in self.snapshots:
            if record in snapshot.records:
                return snapshot.device_name
        return "remote"


def read_remote_snapshots(devices_dir: Path, *, exclude_device: str) -> RemoteView:
    snapshots: list[DeviceSnapshot] = []
    problems: list[str] = []
    if not devices_dir.is_dir():
        return RemoteView(snapshots, problems)
    for path in sorted(devices_dir.glob("*.json")):
        if path.stem == exclude_device:
            continue
        try:
            snapshots.append(read_snapshot(path))
        except InvalidSnapshotError as exc:
            problems.append(str(exc))
    return RemoteView(snapshots, problems)
