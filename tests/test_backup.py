"""Tests for Phase 6 Part 2 (backup / restore + clipboard helpers)."""

from __future__ import annotations

import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.backup.archive import (
    is_safe_member_name,
    load_manifest,
    record_for_file,
    write_archive,
)
from termvault.backup.constants import (
    CONFIG_MEMBER,
    DB_MEMBER,
    EXPORT_MEMBER,
    LIVE_DRAFTS_DIRNAME,
    MANIFEST_MEMBER,
    SAFETY_BACKUP_LABEL,
)
from termvault.backup.creator import create_backup
from termvault.backup.errors import (
    BackupError,
    BackupNotFoundError,
    InvalidBackupError,
    RestoreError,
)
from termvault.backup.manifest import BackupFileRecord, BackupManifest
from termvault.backup.naming import (
    backup_filename,
    parse_backup_timestamp,
    slugify_label,
    unique_backup_path,
)
from termvault.backup.report import format_bytes
from termvault.backup.restorer import plan_restore, restore_backup
from termvault.backup.store import (
    apply_prune,
    list_backups,
    plan_prune,
    resolve_backup_path,
)
from termvault.backup.verifier import verify_backup
from termvault.cli import app
from termvault.clipboard import (
    CLIPBOARD_ENV,
    ClipboardBackend,
    ClipboardUnavailableError,
    candidate_backends,
    copy_text,
    detect_backend,
    entry_clip_text,
)
from termvault.config import (
    DATA_DIR_ENV,
    VaultSettings,
    get_data_dir,
    load_settings,
    save_settings,
)
from termvault.errors import TermVaultError
from termvault.migrations import CURRENT_SCHEMA_VERSION

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    monkeypatch.delenv(CLIPBOARD_ENV, raising=False)
    storage.add_entry("Postgres auth", body="Reset role password", tags=["db"], kind="command", pinned=True)
    storage.add_entry("Docker stuck", body="Restart WSL", tags=["docker"], kind="error")
    storage.add_entry("Redis flush", body="redis-cli FLUSHDB", tags=["db", "cache"], kind="snippet")
    save_settings(VaultSettings(default_list_limit=7))
    return data_dir


def _titles() -> set[str]:
    return {entry.title for entry in storage.list_entries(limit=100, include_trashed=True)}


def _rewrite_archive(
    source: Path,
    destination: Path,
    *,
    replace: dict[str, bytes] | None = None,
    drop: set[str] | None = None,
    add: dict[str, bytes] | None = None,
) -> Path:
    replace = replace or {}
    drop = drop or set()
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(destination, "w") as dst:
        for info in src.infolist():
            if info.filename in drop:
                continue
            data = replace.get(info.filename, src.read(info.filename))
            dst.writestr(info.filename, data)
        for name, data in (add or {}).items():
            dst.writestr(name, data)
    return destination


# ── naming ────────────────────────────────────────────────────────────────


def test_slugify_and_filenames(tmp_path: Path) -> None:
    assert slugify_label("  Before Big Cleanup!! ") == "before-big-cleanup"
    assert slugify_label("!!!") is None
    assert slugify_label(None) is None
    moment = datetime(2026, 9, 29, 12, 30, 5, tzinfo=timezone.utc)
    name = backup_filename("nightly", moment=moment)
    assert name == "termvault-backup-20260929-123005-nightly.zip"
    assert parse_backup_timestamp(name) == moment
    assert parse_backup_timestamp("random.zip") is None

    first = unique_backup_path(tmp_path, "x", moment=moment)
    first.write_bytes(b"")
    second = unique_backup_path(tmp_path, "x", moment=moment)
    assert second != first
    assert second.name.endswith("-2.zip")


def test_drafts_dirname_matches_tui() -> None:
    from termvault.tui.constants import DRAFT_DIRNAME

    assert LIVE_DRAFTS_DIRNAME == DRAFT_DIRNAME


def test_format_bytes() -> None:
    assert format_bytes(512) == "512 B"
    assert format_bytes(2048) == "2.0 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"


# ── manifest + archive safety ─────────────────────────────────────────────


def test_manifest_roundtrip_and_rejections() -> None:
    record = BackupFileRecord(name=DB_MEMBER, size=10, sha256="a" * 64)
    manifest = BackupManifest(schema_version=2, files=[record], label="x")
    loaded = BackupManifest.from_json(manifest.to_json())
    assert loaded.schema_version == 2
    assert loaded.file(DB_MEMBER) == record
    assert loaded.label == "x"

    raw = manifest.to_dict()
    with pytest.raises(InvalidBackupError):
        BackupManifest.from_dict({**raw, "format": "something-else"})
    with pytest.raises(InvalidBackupError):
        BackupManifest.from_dict({**raw, "version": 99})
    with pytest.raises(InvalidBackupError):
        BackupManifest.from_dict({**raw, "files": [{"name": "x", "size": 1, "sha256": "short"}]})
    with pytest.raises(InvalidBackupError):
        BackupManifest.from_json("{not json")


@pytest.mark.parametrize(
    ("name", "safe"),
    [
        ("termvault.db", True),
        ("drafts/new-entry.json", True),
        ("../evil.txt", False),
        ("drafts/../../evil", False),
        ("/etc/passwd", False),
        ("C:/Windows/evil", False),
        ("a\\b", False),
        ("", False),
    ],
)
def test_is_safe_member_name(name: str, safe: bool) -> None:
    assert is_safe_member_name(name) is safe


# ── create ────────────────────────────────────────────────────────────────


def test_create_backup_default_location(vault_home: Path) -> None:
    result = create_backup(label="first")
    assert result.path.parent == get_data_dir() / "backups"
    assert result.path.name.endswith("-first.zip")
    manifest = result.manifest
    assert manifest.schema_version == CURRENT_SCHEMA_VERSION
    assert manifest.stats.active_entries == 3
    assert manifest.stats.pinned_entries == 1
    assert manifest.has_file(DB_MEMBER)
    assert manifest.has_file(CONFIG_MEMBER)
    assert not manifest.has_file(EXPORT_MEMBER)

    with zipfile.ZipFile(result.path) as archive:
        assert set(archive.namelist()) == {MANIFEST_MEMBER, DB_MEMBER, CONFIG_MEMBER}
    assert load_manifest(result.path).to_dict() == manifest.to_dict()


def test_create_backup_options(vault_home: Path, tmp_path: Path) -> None:
    drafts = get_data_dir() / LIVE_DRAFTS_DIRNAME
    drafts.mkdir(parents=True, exist_ok=True)
    (drafts / "new-entry.json").write_text('{"title": "wip"}', encoding="utf-8")

    result = create_backup(
        tmp_path / "custom",
        include_config=False,
        include_drafts=True,
        include_export=True,
    )
    assert result.path.name == "custom.zip"
    manifest = result.manifest
    assert not manifest.has_file(CONFIG_MEMBER)
    assert manifest.has_file("drafts/new-entry.json")
    assert manifest.has_file(EXPORT_MEMBER)
    with zipfile.ZipFile(result.path) as archive:
        exported = json.loads(archive.read(EXPORT_MEMBER))
    assert len(exported["entries"]) == 3

    with pytest.raises(BackupError):
        create_backup(tmp_path / "custom.zip")
    assert create_backup(tmp_path / "custom.zip", overwrite=True).path.exists()


def test_create_backup_into_directory(vault_home: Path, tmp_path: Path) -> None:
    target_dir = tmp_path / "usb"
    target_dir.mkdir()
    result = create_backup(target_dir, label="usb")
    assert result.path.parent == target_dir.resolve()


def test_backup_excludes_backup_folder_itself(vault_home: Path) -> None:
    create_backup()
    second = create_backup()
    with zipfile.ZipFile(second.path) as archive:
        assert not any(name.startswith("backups") for name in archive.namelist())


# ── verify ────────────────────────────────────────────────────────────────


def test_verify_good_backup(vault_home: Path) -> None:
    result = create_backup()
    report = verify_backup(result.path)
    assert report.ok, report.issues
    assert report.checked_files == len(result.manifest.files)
    assert report.db_schema_version == CURRENT_SCHEMA_VERSION
    assert report.db_stats == result.manifest.stats


def test_verify_detects_tampering(vault_home: Path, tmp_path: Path) -> None:
    result = create_backup()
    with zipfile.ZipFile(result.path) as archive:
        db_bytes = bytearray(archive.read(DB_MEMBER))
    db_bytes[-1] ^= 0xFF
    tampered = _rewrite_archive(result.path, tmp_path / "tampered.zip", replace={DB_MEMBER: bytes(db_bytes)})
    report = verify_backup(tampered)
    assert not report.ok
    assert any("Checksum mismatch" in issue.message for issue in report.errors)


def test_verify_missing_manifest_and_member(vault_home: Path, tmp_path: Path) -> None:
    result = create_backup()
    no_manifest = _rewrite_archive(result.path, tmp_path / "a.zip", drop={MANIFEST_MEMBER})
    assert not verify_backup(no_manifest).ok

    no_db = _rewrite_archive(result.path, tmp_path / "b.zip", drop={DB_MEMBER})
    report = verify_backup(no_db)
    assert any("Missing file" in issue.message for issue in report.errors)

    extra = _rewrite_archive(result.path, tmp_path / "c.zip", add={"notes.txt": b"hi"})
    report = verify_backup(extra)
    assert report.ok
    assert any("unlisted" in issue.message for issue in report.warnings)


def test_verify_rejects_non_zip_and_unsafe_paths(vault_home: Path, tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"definitely not a zip")
    assert not verify_backup(junk).ok

    result = create_backup()
    unsafe = _rewrite_archive(result.path, tmp_path / "unsafe.zip", add={"../evil.txt": b"x"})
    report = verify_backup(unsafe)
    assert not report.ok
    assert any("Unsafe" in issue.message for issue in report.errors)

    missing = verify_backup(tmp_path / "nope.zip")
    assert not missing.ok


def test_verify_rejects_newer_schema(vault_home: Path, tmp_path: Path) -> None:
    result = create_backup()
    work = tmp_path / "work"
    work.mkdir()
    with zipfile.ZipFile(result.path) as archive:
        archive.extract(DB_MEMBER, work)
    db_copy = work / DB_MEMBER
    with closing(sqlite3.connect(db_copy)) as conn:
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (99, 'future')")
        conn.commit()
    manifest = BackupManifest(
        schema_version=99,
        files=[record_for_file(DB_MEMBER, db_copy)],
        stats=result.manifest.stats,
    )
    future = write_archive(tmp_path / "future.zip", {DB_MEMBER: db_copy}, manifest)
    report = verify_backup(future)
    assert not report.ok
    assert any("newer" in issue.message for issue in report.errors)


def test_verify_rejects_corrupt_database(vault_home: Path, tmp_path: Path) -> None:
    fake_db = tmp_path / "fake.db"
    fake_db.write_bytes(b"this is not sqlite" * 100)
    manifest = BackupManifest(schema_version=2, files=[record_for_file(DB_MEMBER, fake_db)])
    archive = write_archive(tmp_path / "corrupt.zip", {DB_MEMBER: fake_db}, manifest)
    report = verify_backup(archive)
    assert not report.ok
    assert any("integrity" in issue.message.lower() for issue in report.errors)


# ── list / resolve / prune ────────────────────────────────────────────────


def test_list_and_resolve_latest(vault_home: Path) -> None:
    create_backup(label="one")
    create_backup(label="two")
    newest = create_backup(label="three")
    junk = get_data_dir() / "backups" / "broken.zip"
    junk.write_bytes(b"nope")

    infos = list_backups()
    assert len(infos) == 4
    readable = [info for info in infos if info.readable]
    assert readable[0].label == "three"
    assert any(not info.readable for info in infos)

    assert resolve_backup_path("latest") == newest.path
    assert resolve_backup_path(newest.path.name) == newest.path
    with pytest.raises(BackupNotFoundError):
        resolve_backup_path("does-not-exist.zip")


def test_resolve_latest_with_no_backups(vault_home: Path) -> None:
    with pytest.raises(BackupNotFoundError):
        resolve_backup_path("latest")


def test_prune_keep_last(vault_home: Path) -> None:
    for label in ("a", "b", "c"):
        create_backup(label=label)
    plan = plan_prune(keep_last=1)
    assert [info.label for info in plan.keep] == ["c"]
    assert len(plan.remove) == 2
    assert plan.freed_bytes > 0
    apply_prune(plan)
    remaining = list_backups()
    assert [info.label for info in remaining] == ["c"]


def test_prune_older_than_always_keeps_newest(vault_home: Path) -> None:
    for label in ("a", "b", "c"):
        create_backup(label=label)
    future = datetime.now(timezone.utc) + timedelta(days=30)
    plan = plan_prune(older_than_days=7, now=future)
    assert [info.label for info in plan.keep] == ["c"]
    assert len(plan.remove) == 2

    combined = plan_prune(keep_last=2, older_than_days=7, now=future)
    assert len(combined.remove) == 1

    nothing_old = plan_prune(older_than_days=7)
    assert nothing_old.remove == []

    with pytest.raises(BackupError):
        plan_prune()


# ── restore ───────────────────────────────────────────────────────────────


def test_restore_round_trip_with_safety_backup(vault_home: Path) -> None:
    base = create_backup(label="base")
    storage.delete_entry(1, permanent=True)
    storage.add_entry("After backup", body="new")
    save_settings(VaultSettings(default_list_limit=33))

    result = restore_backup(base.path)
    assert _titles() == {"Postgres auth", "Docker stuck", "Redis flush"}
    assert load_settings().default_list_limit == 7
    assert result.restored == [DB_MEMBER, CONFIG_MEMBER]
    assert result.stats_after is not None and result.stats_after.active_entries == 3
    assert result.safety_backup_path is not None

    safety = load_manifest(result.safety_backup_path)
    assert safety.label == SAFETY_BACKUP_LABEL

    restore_backup(result.safety_backup_path, safety_backup=False)
    assert "After backup" in _titles()
    assert load_settings().default_list_limit == 33


def test_restore_keeps_config_when_asked(vault_home: Path) -> None:
    base = create_backup()
    save_settings(VaultSettings(default_list_limit=44))
    result = restore_backup(base.path, include_config=False, safety_backup=False)
    assert result.restored == [DB_MEMBER]
    assert load_settings().default_list_limit == 44


def test_restore_drafts(vault_home: Path) -> None:
    drafts = get_data_dir() / LIVE_DRAFTS_DIRNAME
    drafts.mkdir(parents=True, exist_ok=True)
    draft = drafts / "new-entry.json"
    draft.write_text('{"title": "wip"}', encoding="utf-8")
    base = create_backup(include_drafts=True)
    draft.unlink()

    plan = plan_restore(base.path, include_drafts=True, safety_backup=False)
    assert plan.draft_count == 1
    result = restore_backup(base.path, include_drafts=True, safety_backup=False)
    assert "drafts/new-entry.json" in result.restored
    assert json.loads(draft.read_text(encoding="utf-8")) == {"title": "wip"}


def test_restore_rolls_back_on_failure(vault_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = create_backup()
    storage.add_entry("After backup", body="new")

    def boom() -> None:
        raise RuntimeError("simulated migration crash")

    monkeypatch.setattr("termvault.backup.restorer.initialize_database", boom)
    with pytest.raises(RestoreError) as excinfo:
        restore_backup(base.path, safety_backup=False)
    assert excinfo.value.rolled_back is True
    monkeypatch.undo()
    monkeypatch.setenv(DATA_DIR_ENV, str(vault_home))

    assert "After backup" in _titles()
    leftovers = [p.name for p in get_data_dir().iterdir() if p.name.startswith(".restore-")]
    assert leftovers == []


def test_restore_refuses_bad_backup(vault_home: Path, tmp_path: Path) -> None:
    result = create_backup()
    broken = _rewrite_archive(result.path, tmp_path / "broken.zip", replace={DB_MEMBER: b"garbage"})
    with pytest.raises(InvalidBackupError):
        plan_restore(broken)
    assert len(_titles()) == 3


def test_restore_into_empty_vault(vault_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    base = create_backup(tmp_path / "portable.zip")
    monkeypatch.setenv(DATA_DIR_ENV, str(tmp_path / "fresh-machine"))
    plan = plan_restore(base.path)
    assert plan.current_stats is None
    result = restore_backup(base.path)
    assert result.safety_backup_path is None
    assert _titles() == {"Postgres auth", "Docker stuck", "Redis flush"}


# ── CLI ───────────────────────────────────────────────────────────────────


def test_cli_backup_help() -> None:
    result = runner.invoke(app, ["backup", "--help"])
    assert result.exit_code == 0
    for command in ("create", "list", "info", "verify", "restore", "prune"):
        assert command in result.output


def test_cli_create_list_info_verify(vault_home: Path) -> None:
    created = runner.invoke(app, ["backup", "create", "--label", "cli", "--json"])
    assert created.exit_code == 0, created.output
    payload = json.loads(created.output)
    assert payload["manifest"]["label"] == "cli"

    listed = runner.invoke(app, ["backup", "list"])
    assert listed.exit_code == 0
    assert "1 backup(s)" in listed.output

    info = runner.invoke(app, ["backup", "info", "latest"])
    assert info.exit_code == 0
    assert "termvault.db" in info.output

    verified = runner.invoke(app, ["backup", "verify", "latest"])
    assert verified.exit_code == 0
    assert "Verify OK" in verified.output


def test_cli_verify_failure_exit_code(vault_home: Path, tmp_path: Path) -> None:
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"nope")
    result = runner.invoke(app, ["backup", "verify", str(junk)])
    assert result.exit_code == 1
    assert "FAILED" in result.output


def test_cli_restore_dry_run_confirm_and_yes(vault_home: Path) -> None:
    runner.invoke(app, ["backup", "create"])
    storage.add_entry("After backup", body="new")

    dry = runner.invoke(app, ["backup", "restore", "latest", "--dry-run"])
    assert dry.exit_code == 0
    assert "Restore plan" in dry.output
    assert "After backup" in _titles()

    declined = runner.invoke(app, ["backup", "restore", "latest"], input="n\n")
    assert declined.exit_code == 0
    assert "Cancelled" in declined.output
    assert "After backup" in _titles()

    applied = runner.invoke(app, ["backup", "restore", "latest", "--yes"])
    assert applied.exit_code == 0, applied.output
    assert "Restore complete" in applied.output
    assert "After backup" not in _titles()


def test_cli_restore_missing_backup(vault_home: Path) -> None:
    result = runner.invoke(app, ["backup", "restore", "latest", "--yes"])
    assert result.exit_code == 1
    assert "Error" in result.output


def test_cli_prune_preview_then_apply(vault_home: Path) -> None:
    for label in ("a", "b", "c"):
        create_backup(label=label)
    preview = runner.invoke(app, ["backup", "prune", "--keep", "1"])
    assert preview.exit_code == 0
    assert "Would delete 2" in preview.output
    assert len(list_backups()) == 3

    applied = runner.invoke(app, ["backup", "prune", "--keep", "1", "--yes"])
    assert applied.exit_code == 0
    assert "Deleted 2" in applied.output
    assert len(list_backups()) == 1


# ── clipboard ─────────────────────────────────────────────────────────────


def test_candidate_backends_per_os() -> None:
    assert candidate_backends("Windows")[0].name == "clip"
    assert candidate_backends("Darwin")[0].name == "pbcopy"
    assert [b.name for b in candidate_backends("Linux")] == ["wl-copy", "xclip", "xsel"]


def test_detect_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CLIPBOARD_ENV, raising=False)
    assert detect_backend("Linux", which=lambda _name: None) is None
    found = detect_backend("Linux", which=lambda name: "/usr/bin/xclip" if name == "xclip" else None)
    assert found is not None and found.name == "xclip"

    monkeypatch.setenv(CLIPBOARD_ENV, "mycopy --flag")
    custom = detect_backend("Linux", which=lambda _name: None)
    assert custom is not None
    assert custom.name == "custom"
    assert custom.command == ("mycopy", "--flag")


def test_copy_text_runs_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["input"] = kwargs["input"]

    monkeypatch.setattr("termvault.clipboard.subprocess.run", fake_run)
    backend = ClipboardBackend("fake", ("fakecopy",))
    assert copy_text("héllo", backend=backend) is backend
    assert captured["command"] == ["fakecopy"]
    assert captured["input"].decode("utf-8") == "héllo"

    monkeypatch.setattr("termvault.clipboard.detect_backend", lambda: None)
    with pytest.raises(ClipboardUnavailableError):
        copy_text("x")


def test_entry_clip_text_fields(vault_home: Path) -> None:
    entry = storage.get_entry(1)
    assert entry_clip_text(entry, "body") == "Reset role password"
    assert entry_clip_text(entry, "title") == "Postgres auth"
    assert "kind: command" in entry_clip_text(entry, "meta")
    assert json.loads(entry_clip_text(entry, "json"))["title"] == "Postgres auth"
    assert 'title: "Postgres auth"' in entry_clip_text(entry, "markdown")
    with pytest.raises(TermVaultError):
        entry_clip_text(entry, "nope")


def test_cli_copy(vault_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    printed = runner.invoke(app, ["copy", "2", "--print"])
    assert printed.exit_code == 0
    assert printed.output.strip() == "Restart WSL"

    as_json = runner.invoke(app, ["copy", "2", "--field", "json", "--print"])
    assert json.loads(as_json.output)["kind"] == "error"

    sent: list[str] = []

    def fake_copy(text: str) -> ClipboardBackend:
        sent.append(text)
        return ClipboardBackend("fake", ("fake",))

    monkeypatch.setattr("termvault.commands.backup.copy_text", fake_copy)
    copied = runner.invoke(app, ["copy", "3"])
    assert copied.exit_code == 0
    assert "via fake" in copied.output
    assert sent == ["redis-cli FLUSHDB"]

    missing = runner.invoke(app, ["copy", "99", "--print"])
    assert missing.exit_code == 1
