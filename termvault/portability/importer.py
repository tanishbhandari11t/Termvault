"""High-level import orchestration for Phase 6 Part 1."""

from __future__ import annotations

from pathlib import Path

from termvault import storage
from termvault.errors import TermVaultError
from termvault.portability.detect import resolve_codec
from termvault.portability.errors import ImportError_
from termvault.portability.json_format import loads_export_json_flexible
from termvault.portability.markdown_format import loads_export_markdown_path
from termvault.portability.paths import read_text_file
from termvault.portability.planner import ImportPlan, PlanOp, build_import_plan
from termvault.portability.report import ImportApplyReport
from termvault.portability.schema import ExportDocument, ExportEntry


def read_import(
    source: str | Path,
    *,
    codec: str | None = None,
) -> ExportDocument:
    """Read an export document from a file or markdown directory."""
    path = Path(source).expanduser().resolve()
    if not path.exists():
        raise ImportError_(f"Import path not found: {path}")

    resolved = resolve_codec(path=path, explicit=codec)
    try:
        if resolved == "json":
            text = read_text_file(path)
            document = loads_export_json_flexible(text)
        elif resolved == "markdown":
            document = loads_export_markdown_path(path)
        else:
            raise ImportError_(f"Unsupported codec: {resolved}")
    except TermVaultError:
        raise
    except OSError as exc:
        raise ImportError_(f"Unable to read import: {exc}") from exc

    document.codec_hint = resolved
    return document


def plan_import(
    source: str | Path | ExportDocument,
    *,
    codec: str | None = None,
    policy: str = "skip",
    strategy: str = "title",
    include_trashed_imports: bool = False,
    skip_identical: bool = True,
    verify_hashes: bool = True,
) -> ImportPlan:
    """Build an import plan from a path or in-memory document."""
    if isinstance(source, ExportDocument):
        document = source
    else:
        document = read_import(source, codec=codec)
    return build_import_plan(
        document,
        policy=policy,
        strategy=strategy,
        include_trashed_imports=include_trashed_imports,
        skip_identical=skip_identical,
        verify_hashes=verify_hashes,
    )


def apply_import_plan(plan: ImportPlan, *, dry_run: bool = False) -> ImportApplyReport:
    """Execute a previously built import plan (or return it as dry-run)."""
    if dry_run:
        return ImportApplyReport(plan=plan, dry_run=True)

    created: list[int] = []
    overwritten: list[int] = []
    for item in plan.items:
        if item.op is PlanOp.CREATE:
            entry = _create_from_incoming(item.incoming)
            created.append(entry.id)
        elif item.op is PlanOp.OVERWRITE:
            assert item.existing_id is not None
            entry = _overwrite_existing(item.existing_id, item.incoming)
            overwritten.append(entry.id)
        # SKIP / SKIP_IDENTICAL: no-op

    return ImportApplyReport(
        plan=plan,
        created_ids=created,
        overwritten_ids=overwritten,
        dry_run=False,
    )


def import_vault(
    source: str | Path,
    *,
    codec: str | None = None,
    policy: str = "skip",
    strategy: str = "title",
    include_trashed_imports: bool = False,
    skip_identical: bool = True,
    verify_hashes: bool = True,
    dry_run: bool = False,
) -> ImportApplyReport:
    """Read → plan → apply (or dry-run) in one call."""
    plan = plan_import(
        source,
        codec=codec,
        policy=policy,
        strategy=strategy,
        include_trashed_imports=include_trashed_imports,
        skip_identical=skip_identical,
        verify_hashes=verify_hashes,
    )
    return apply_import_plan(plan, dry_run=dry_run)


def _create_from_incoming(incoming: ExportEntry):
    entry = storage.add_entry(
        title=incoming.title,
        body=incoming.body,
        tags=list(incoming.tags),
        kind=incoming.kind,
        pinned=incoming.pinned,
    )
    return entry


def _overwrite_existing(entry_id: int, incoming: ExportEntry):
    updated = storage.update_entry(
        entry_id,
        title=incoming.title,
        body=incoming.body,
        tags=list(incoming.tags),
        kind=incoming.kind,
    )
    # Pin state is separate from update_entry fields.
    if updated.pinned != incoming.pinned:
        updated = storage.set_pinned(entry_id, incoming.pinned)
    return updated
