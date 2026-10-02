"""Plain-text rendering for ``tv sync`` (ASCII only for Windows consoles)."""

from __future__ import annotations

from termvault.sync.config import SyncConfig
from termvault.sync.engine import SyncResult, SyncStatus
from termvault.sync.merge import IN_SYNC, MergePlan

ACTION_LABELS = {
    "publish": "send to other devices",
    "create": "create here",
    "update": "update here",
    "delete": "delete here",
    "tombstone": "remember deletion",
    "conflict": "conflict",
    "in_sync": "already in sync",
}
ACTION_ORDER = ("create", "update", "delete", "conflict", "tombstone", "publish", "in_sync")
MAX_DETAIL_LINES = 25


def format_plan(plan: MergePlan, *, detail: bool = True) -> str:
    counts = plan.counts
    lines = ["Plan:"]
    for name in ACTION_ORDER:
        if counts.get(name):
            lines.append(f"  {ACTION_LABELS[name]}: {counts[name]}")
    if len(lines) == 1:
        lines.append("  nothing to do")
    if detail:
        interesting = [action for action in plan.actions if action.action != IN_SYNC]
        for action in interesting[:MAX_DETAIL_LINES]:
            line = f"  - {action.action:<9} {action.title}  ({action.reason})"
            if action.copy is not None:
                line += f" -> copy: {action.copy.title}"
            lines.append(line)
        if len(interesting) > MAX_DETAIL_LINES:
            lines.append(f"  ... {len(interesting) - MAX_DETAIL_LINES} more")
    return "\n".join(lines)


def format_config(config: SyncConfig) -> str:
    return "\n".join(
        [
            f"Folder:    {config.folder}",
            f"Device:    {config.device_name} ({config.device_id[:8]})",
            f"Policy:    {config.policy}",
            f"Enabled:   {'yes' if config.enabled else 'no'}",
            f"Last sync: {config.last_sync_at or 'never'}",
        ]
    )


def format_status(status: SyncStatus) -> str:
    if status.config is None:
        return "Sync is off (opt-in). Enable it with: tv sync init <folder>"
    lines = [format_config(status.config)]
    if not status.config.enabled:
        lines.append("Sync is disabled. Re-enable with: tv sync init <folder>")
        return "\n".join(lines)
    if not status.folder_available:
        lines.append("Folder is not available right now (drive unplugged or cloud folder missing).")
        return "\n".join(lines)
    if status.devices:
        lines.append("Other devices:")
        for device in status.devices:
            lines.append(
                f"  - {device.device_name} ({device.device_id[:8]}): "
                f"{device.live} entries, {device.tombstones} deletions, written {device.written_at}"
            )
    else:
        lines.append("Other devices: none yet")
    for problem in status.problems:
        lines.append(f"  x skipped snapshot: {problem}")
    if status.plan is not None:
        lines.append(format_plan(status.plan))
    return "\n".join(lines)


def format_result(result: SyncResult) -> str:
    if result.dry_run:
        head = f"Dry run - nothing changed ({result.remote_devices} other device(s) found)."
    else:
        head = (
            f"Synced with {result.remote_devices} other device(s): "
            f"{result.created} created, {result.updated} updated, "
            f"{result.deleted} deleted, {result.conflict_copies} conflict copies."
        )
    lines = [head, format_plan(result.plan)]
    if result.backup_path:
        lines.append(f"Safety backup: {result.backup_path}")
    if result.snapshot_path:
        lines.append(f"Published: {result.snapshot_path}")
    for problem in result.problems:
        lines.append(f"x skipped snapshot: {problem}")
    return "\n".join(lines)
