"""Phase 7 opt-in folder sync. Nothing here runs unless ``tv sync init`` was used."""

from __future__ import annotations

from termvault.sync.config import (
    SyncConfig,
    disable_sync,
    init_sync,
    load_sync_config,
)
from termvault.sync.engine import SyncResult, SyncStatus, run_sync, sync_status
from termvault.sync.errors import (
    InvalidSnapshotError,
    SyncError,
    SyncFolderMissingError,
    SyncNotConfiguredError,
)
from termvault.sync.merge import MergeAction, MergePlan, merge_one, plan_merge
from termvault.sync.records import SyncRecord

__all__ = [
    "InvalidSnapshotError",
    "MergeAction",
    "MergePlan",
    "SyncConfig",
    "SyncError",
    "SyncFolderMissingError",
    "SyncNotConfiguredError",
    "SyncRecord",
    "SyncResult",
    "SyncStatus",
    "disable_sync",
    "init_sync",
    "load_sync_config",
    "merge_one",
    "plan_merge",
    "run_sync",
    "sync_status",
]
