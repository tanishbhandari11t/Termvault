"""Per-vault sync settings in ``<data dir>/sync.json``.

No file means sync is off. Nothing in TermVault touches the sync folder unless
the user has run ``tv sync init``.
"""

from __future__ import annotations

import json
import os
import platform
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from termvault.config import ensure_data_dir, get_data_dir
from termvault.errors import ValidationError
from termvault.sync.constants import (
    DEFAULT_POLICY,
    DEVICES_DIRNAME,
    MERGE_POLICIES,
    SYNC_CONFIG_FILENAME,
    SYNC_DIRNAME,
)
from termvault.sync.errors import SyncError, SyncFolderMissingError, SyncNotConfiguredError


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_policy(policy: str | None) -> str:
    value = (policy or DEFAULT_POLICY).strip().lower()
    if value not in MERGE_POLICIES:
        raise ValidationError("Policy must be one of: " + ", ".join(MERGE_POLICIES))
    return value


@dataclass(frozen=True)
class SyncConfig:
    folder: str
    device_id: str
    device_name: str
    enabled: bool = True
    policy: str = DEFAULT_POLICY
    created_at: str = ""
    last_sync_at: str | None = None

    @property
    def folder_path(self) -> Path:
        return Path(self.folder)

    @property
    def root(self) -> Path:
        return self.folder_path / SYNC_DIRNAME

    @property
    def devices_dir(self) -> Path:
        return self.root / DEVICES_DIRNAME

    @property
    def snapshot_path(self) -> Path:
        return self.devices_dir / f"{self.device_id}.json"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def config_path() -> Path:
    return get_data_dir() / SYNC_CONFIG_FILENAME


def load_sync_config() -> SyncConfig | None:
    path = config_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SyncError(f"Could not read {path}: {exc}") from exc
    if not isinstance(raw, dict) or not raw.get("folder") or not raw.get("device_id"):
        raise SyncError(f"{path} is missing required keys (folder, device_id).")
    return SyncConfig(
        folder=str(raw["folder"]),
        device_id=str(raw["device_id"]),
        device_name=str(raw.get("device_name") or raw["device_id"][:8]),
        enabled=bool(raw.get("enabled", True)),
        policy=normalize_policy(raw.get("policy")),
        created_at=str(raw.get("created_at") or ""),
        last_sync_at=raw.get("last_sync_at"),
    )


def save_sync_config(config: SyncConfig) -> Path:
    ensure_data_dir()
    path = config_path()
    temp = path.with_suffix(".json.partial")
    temp.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    return path


def require_sync_config() -> SyncConfig:
    config = load_sync_config()
    if config is None or not config.enabled:
        raise SyncNotConfiguredError()
    return config


def ensure_folder_available(config: SyncConfig) -> None:
    """The user's folder must exist; only our own subfolder is ever created."""
    if not config.folder_path.is_dir():
        raise SyncFolderMissingError(config.folder)
    config.devices_dir.mkdir(parents=True, exist_ok=True)


def default_device_name() -> str:
    return platform.node() or "device"


def init_sync(
    folder: str | Path,
    *,
    device_name: str | None = None,
    policy: str | None = None,
    create_folder: bool = False,
) -> SyncConfig:
    """Opt in to sync. Re-running keeps the same device id."""
    target = Path(folder).expanduser().resolve()
    if create_folder:
        target.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        raise SyncFolderMissingError(str(target))
    if target == get_data_dir() or get_data_dir() in target.parents:
        raise ValidationError("The sync folder must be outside the vault data directory.")

    existing = load_sync_config()
    config = SyncConfig(
        folder=str(target),
        device_id=existing.device_id if existing else uuid.uuid4().hex,
        device_name=(device_name or (existing.device_name if existing else default_device_name())).strip(),
        enabled=True,
        policy=normalize_policy(policy or (existing.policy if existing else None)),
        created_at=existing.created_at if existing and existing.created_at else _utc_now(),
        last_sync_at=existing.last_sync_at if existing and existing.folder == str(target) else None,
    )
    if not config.device_name:
        raise ValidationError("Device name must not be empty.")
    ensure_folder_available(config)
    save_sync_config(config)
    return config


def disable_sync(*, forget: bool = False) -> SyncConfig | None:
    """Turn sync off. ``forget`` also deletes the local sync config."""
    config = load_sync_config()
    if config is None:
        return None
    if forget:
        config_path().unlink(missing_ok=True)
        return replace(config, enabled=False)
    updated = replace(config, enabled=False)
    save_sync_config(updated)
    return updated


def mark_synced(config: SyncConfig, synced_at: str) -> SyncConfig:
    updated = replace(config, last_sync_at=synced_at)
    save_sync_config(updated)
    return updated
