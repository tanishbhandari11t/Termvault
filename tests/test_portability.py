"""Tests for Phase 6 Part 1 (export / import portability)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from termvault import storage
from termvault.cli import app
from termvault.config import DATA_DIR_ENV
from termvault.portability.checksums import entry_content_hash, hash_entries
from termvault.portability.conflicts import (
    build_conflict_index,
    match_key,
    normalize_conflict_policy,
    resolve_action,
)
from termvault.portability.detect import detect_codec_from_text, resolve_codec
from termvault.portability.errors import ConflictFailError, ImportValidationError
from termvault.portability.exporter import export_vault, serialize_document, write_export
from termvault.portability.filters import ExportFilters
from termvault.portability.importer import apply_import_plan, import_vault, plan_import, read_import
from termvault.portability.json_format import dumps_export_json, loads_export_json_flexible
from termvault.portability.markdown_format import (
    dumps_export_markdown,
    loads_export_markdown,
    parse_entry_markdown,
)
from termvault.portability.planner import PlanOp, build_import_plan
from termvault.portability.schema import ExportDocument, ExportEntry
from termvault.portability.validate import validate_document

runner = CliRunner()


@pytest.fixture()
def vault_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "vault"
    monkeypatch.setenv(DATA_DIR_ENV, str(data_dir))
    storage.add_entry(
        "Postgres auth",
        body="Reset role password",
        tags=["db"],
        kind="command",
        pinned=True,
    )
    storage.add_entry(
        "Docker stuck",
        body="Restart WSL",
        tags=["docker"],
        kind="error",
    )
    storage.add_entry(
        "Redis flush",
        body="redis-cli FLUSHDB",
        tags=["db", "cache"],
        kind="snippet",
    )
    return data_dir


def test_export_import_commands_listed() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "export" in result.output
    assert "import" in result.output


def test_export_help() -> None:
    result = runner.invoke(app, ["export", "--help"])
    assert result.exit_code == 0
    assert "--format" in result.output
    assert "--dry-run" in result.output


def test_import_help() -> None:
    result = runner.invoke(app, ["import", "--help"])
    assert result.exit_code == 0
    assert "--conflict" in result.output
    assert "--dry-run" in result.output


def test_checksums_stable(vault_home: Path) -> None:
    _ = vault_home
    entry = ExportEntry(title="A", body="b", tags=("x", "y"), kind="note")
    h1 = entry_content_hash(entry)
    h2 = entry_content_hash(
        ExportEntry(title="A", body="b", tags=("y", "x"), kind="note")
    )
    assert h1 == h2
    assert len(hash_entries([entry])) == 64


def test_json_roundtrip(vault_home: Path) -> None:
    _ = vault_home
    document = export_vault(ExportFilters(), codec="json")
    assert len(document.entries) == 3
    assert document.manifest.entry_count == 3
    text = dumps_export_json(document)
    loaded = loads_export_json_flexible(text)
    assert len(loaded.entries) == 3
    titles = {e.title for e in loaded.entries}
    assert titles == {"Postgres auth", "Docker stuck", "Redis flush"}


def test_json_accepts_bare_list() -> None:
    text = json.dumps([{"title": "Solo", "body": "x", "kind": "note"}])
    doc = loads_export_json_flexible(text)
    assert len(doc.entries) == 1
    assert doc.entries[0].title == "Solo"


def test_markdown_roundtrip(vault_home: Path) -> None:
    _ = vault_home
    document = export_vault(ExportFilters(), codec="markdown")
    text = dumps_export_markdown(document)
    assert "title:" in text
    loaded = loads_export_markdown(text)
    assert len(loaded.entries) == 3
    assert {e.title for e in loaded.entries} == {
        "Postgres auth",
        "Docker stuck",
        "Redis flush",
    }


def test_markdown_bare_heading_parse() -> None:
    entry = parse_entry_markdown("# Hello\n\nBody here\n")
    assert entry.title == "Hello"
    assert "Body here" in entry.body


def test_export_filters_tag_and_kind(vault_home: Path) -> None:
    _ = vault_home
    by_tag = export_vault(ExportFilters(tag="db"))
    assert {e.title for e in by_tag.entries} == {"Postgres auth", "Redis flush"}
    by_kind = export_vault(ExportFilters(kind="error"))
    assert len(by_kind.entries) == 1
    pinned = export_vault(ExportFilters(pinned_only=True))
    assert len(pinned.entries) == 1
    assert pinned.entries[0].pinned is True


def test_write_export_json_file(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "out.json"
    report = write_export(out, codec="json", force=True)
    assert report.entry_count == 3
    assert out.exists()
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["format"] == "termvault-export"
    assert len(raw["entries"]) == 3


def test_write_export_refuses_overwrite(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "out.json"
    write_export(out, codec="json", force=True)
    with pytest.raises(Exception):
        write_export(out, codec="json", force=False)


def test_write_export_dry_run(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "nope.json"
    report = write_export(out, codec="json", dry_run=True)
    assert report.dry_run is True
    assert not out.exists()
    assert report.entry_count == 3


def test_detect_codec() -> None:
    assert detect_codec_from_text('{"entries":[]}') == "json"
    assert detect_codec_from_text("---\ntitle: x\n---\n") == "markdown"
    assert resolve_codec(explicit="md") == "markdown"


def test_validate_rejects_blank_title() -> None:
    doc = ExportDocument(
        entries=[ExportEntry(title="ok"), ExportEntry(title="   ")]
    )
    report = validate_document(doc)
    assert report.ok is False


def test_conflict_policy_fail(vault_home: Path) -> None:
    _ = vault_home
    document = export_vault()
    with pytest.raises(ConflictFailError):
        build_import_plan(document, policy="fail")


def test_import_skip_identical(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "bundle.json"
    write_export(out, force=True)
    plan = plan_import(out, policy="skip")
    assert plan.skip_count == 3
    assert plan.create_count == 0
    report = apply_import_plan(plan, dry_run=False)
    assert report.created_ids == []


def test_import_create_new_titles(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    payload = {
        "format": "termvault-export",
        "version": 1,
        "entries": [
            {
                "title": "Brand new idea",
                "body": "fresh",
                "kind": "note",
                "tags": ["idea"],
            }
        ],
    }
    path = tmp_path / "new.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = import_vault(path, policy="skip")
    assert report.created_ids
    assert storage.get_entry(report.created_ids[0]).title == "Brand new idea"


def test_import_overwrite(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    payload = {
        "format": "termvault-export",
        "version": 1,
        "entries": [
            {
                "title": "Docker stuck",
                "body": "UPDATED BODY",
                "kind": "error",
                "tags": ["docker"],
            }
        ],
    }
    path = tmp_path / "ow.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    report = import_vault(path, policy="overwrite")
    assert report.overwritten_ids
    updated = storage.get_entry(report.overwritten_ids[0])
    assert updated.body == "UPDATED BODY"


def test_import_markdown_cli(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    md_path = tmp_path / "vault.md"
    write_export(md_path, codec="markdown", force=True)
    text = md_path.read_text(encoding="utf-8").replace(
        "Postgres auth", "Postgres auth COPY"
    )
    copy_path = tmp_path / "copy.md"
    copy_path.write_text(text, encoding="utf-8")
    result = runner.invoke(
        app,
        ["import", str(copy_path), "--conflict", "skip", "--dry-run", "-v"],
    )
    assert result.exit_code == 0
    assert "create=" in result.output


def test_cli_export_json(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "cli.json"
    result = runner.invoke(app, ["export", str(out), "-f", "json", "--force"])
    assert result.exit_code == 0
    assert out.exists()
    assert "Export complete" in result.output


def test_cli_export_dry_run_json_report(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    result = runner.invoke(
        app,
        ["export", str(tmp_path / "x.json"), "--dry-run", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["dry_run"] is True
    assert payload["entry_count"] == 3


def test_cli_import_preview(vault_home: Path, tmp_path: Path) -> None:
    _ = vault_home
    out = tmp_path / "p.json"
    write_export(out, force=True)
    result = runner.invoke(app, ["import", str(out), "--preview"])
    assert result.exit_code == 0
    assert "Entries:" in result.output


def test_match_strategies(vault_home: Path) -> None:
    entries = storage.list_entries(limit=50)
    index = build_conflict_index(entries, strategy="title+kind")
    assert index
    incoming = ExportEntry(title="Docker stuck", body="x", kind="error")
    action, match = resolve_action(
        incoming, index=index, strategy="title+kind", policy="skip"
    )
    assert action.value == "skip"
    assert match is not None
    assert normalize_conflict_policy("overwrite") == "overwrite"
    assert match_key(incoming, "title") == "docker stuck"


def test_trashed_export_import_skip_by_default(
    vault_home: Path, tmp_path: Path
) -> None:
    storage.delete_entry(2, permanent=False)
    out = tmp_path / "with-trash.json"
    write_export(
        out,
        filters=ExportFilters(include_trashed=True),
        force=True,
    )
    doc = read_import(out)
    assert any(e.trashed for e in doc.entries)
    plan = plan_import(out, include_trashed_imports=False)
    trashed_items = [i for i in plan.items if i.incoming.trashed]
    assert trashed_items
    assert all(i.op is PlanOp.SKIP for i in trashed_items)


def test_invalid_json_import(tmp_path: Path, vault_home: Path) -> None:
    _ = vault_home
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(ImportValidationError):
        read_import(bad)


def test_serialize_codec_switch(vault_home: Path) -> None:
    doc = export_vault()
    js = serialize_document(doc, codec="json")
    md = serialize_document(doc, codec="markdown")
    assert '"entries"' in js
    assert "title:" in md
