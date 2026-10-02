"""Human-readable output for backup / restore commands."""

from __future__ import annotations

from termvault.backup.creator import BackupResult
from termvault.backup.manifest import BackupManifest, BackupStats
from termvault.backup.restorer import RestorePlan, RestoreResult
from termvault.backup.store import BackupInfo, PrunePlan
from termvault.backup.verifier import VerifyReport


def format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def format_stats(stats: BackupStats) -> str:
    return (
        f"{stats.active_entries} active, {stats.trashed_entries} trashed, "
        f"{stats.pinned_entries} pinned, {stats.tag_count} tags"
    )


def format_backup_result(result: BackupResult) -> str:
    manifest = result.manifest
    lines = [
        "Backup created",
        f"  path:    {result.path}",
        f"  size:    {format_bytes(result.size_bytes)}",
        f"  entries: {format_stats(manifest.stats)}",
        f"  schema:  v{manifest.schema_version}",
        f"  files:   {', '.join(record.name for record in manifest.files)}",
    ]
    if manifest.label:
        lines.insert(2, f"  label:   {manifest.label}")
    return "\n".join(lines)


def format_manifest(manifest: BackupManifest, *, path: str | None = None) -> str:
    lines = ["Backup info"]
    if path:
        lines.append(f"  path:       {path}")
    lines.extend(
        [
            f"  created:    {manifest.created_at}",
            f"  label:      {manifest.label or '-'}",
            f"  termvault:  {manifest.termvault_version}",
            f"  schema:     v{manifest.schema_version}",
            f"  host:       {manifest.host or '-'} ({manifest.platform or '-'})",
            f"  entries:    {format_stats(manifest.stats)}",
            "  files:",
        ]
    )
    for record in manifest.files:
        lines.append(
            f"    {record.name:<28} {format_bytes(record.size):>10}  {record.sha256[:12]}..."
        )
    return "\n".join(lines)


def format_backup_list(infos: list[BackupInfo]) -> str:
    if not infos:
        return "No backups found. Create one with: tv backup create"
    lines = [f"{len(infos)} backup(s), newest first:"]
    for info in infos:
        when = info.created_at.strftime("%Y-%m-%d %H:%M:%S") if info.created_at else "unknown time"
        if not info.readable:
            lines.append(f"  x {info.name}  ({when})  unreadable: {info.error}")
            continue
        assert info.manifest is not None
        label = f"  [{info.label}]" if info.label else ""
        lines.append(
            f"  - {info.name}  {when}  {format_bytes(info.size_bytes)}  "
            f"{info.manifest.stats.active_entries} entries{label}"
        )
    return "\n".join(lines)


def format_verify_report(report: VerifyReport) -> str:
    status = "OK" if report.ok else "FAILED"
    lines = [f"Verify {status}: {report.path}"]
    if report.manifest is not None:
        lines.append(f"  files checked: {report.checked_files}/{len(report.manifest.files)}")
    if report.db_schema_version is not None:
        lines.append(f"  schema:        v{report.db_schema_version}")
    if report.db_stats is not None:
        lines.append(f"  entries:       {format_stats(report.db_stats)}")
    for issue in report.issues:
        lines.append(f"  {issue.format()}")
    return "\n".join(lines)


def format_restore_plan(plan: RestorePlan) -> str:
    current = format_stats(plan.current_stats) if plan.current_stats else "no vault yet"
    lines = [
        "Restore plan",
        f"  from:          {plan.archive}",
        f"  backup made:   {plan.manifest.created_at}"
        + (f"  [{plan.manifest.label}]" if plan.manifest.label else ""),
        f"  backup has:    {format_stats(plan.manifest.stats)}",
        f"  current vault: {current}",
        f"  database:      will be replaced",
        f"  config:        {'will be replaced' if plan.restore_config else 'kept as is'}",
        f"  drafts:        {plan.draft_count} to restore" if plan.restore_drafts else "  drafts:        kept as is",
        f"  safety backup: {'yes' if plan.safety_backup else 'NO (--no-safety-backup)'}",
    ]
    if plan.will_migrate:
        lines.append(f"  schema:        v{plan.manifest.schema_version} -> upgraded after restore")
    for issue in plan.verify.warnings:
        lines.append(f"  {issue.format()}")
    return "\n".join(lines)


def format_restore_result(result: RestoreResult) -> str:
    lines = ["Restore complete", f"  restored: {', '.join(result.restored)}"]
    if result.stats_after is not None:
        lines.append(f"  vault now: {format_stats(result.stats_after)}")
    if result.schema_version_after is not None:
        lines.append(f"  schema:    v{result.schema_version_after}")
    if result.safety_backup_path is not None:
        lines.append(f"  undo with: tv backup restore \"{result.safety_backup_path}\"")
    return "\n".join(lines)


def format_prune_plan(plan: PrunePlan, *, applied: bool) -> str:
    if not plan.remove:
        return f"Nothing to prune ({len(plan.keep)} backup(s) kept)."
    verb = "Deleted" if applied else "Would delete"
    lines = [
        f"{verb} {len(plan.remove)} backup(s), freeing {format_bytes(plan.freed_bytes)}:"
    ]
    lines.extend(f"  - {info.name}" for info in plan.remove)
    lines.append(f"Keeping {len(plan.keep)} backup(s).")
    if not applied:
        lines.append("Re-run with --yes to delete.")
    return "\n".join(lines)
