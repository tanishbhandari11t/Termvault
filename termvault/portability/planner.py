"""Import planning: turn a document + policy into concrete steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from termvault import storage
from termvault.models import Entry
from termvault.portability.conflicts import (
    ConflictAction,
    ConflictMatch,
    build_conflict_index,
    normalize_conflict_policy,
    normalize_match_strategy,
    resolve_action,
    same_content,
)
from termvault.portability.schema import ExportDocument, ExportEntry
from termvault.portability.validate import ValidationReport, validate_document


class PlanOp(str, Enum):
    CREATE = "create"
    SKIP = "skip"
    OVERWRITE = "overwrite"
    SKIP_IDENTICAL = "skip_identical"


@dataclass
class PlanItem:
    op: PlanOp
    incoming: ExportEntry
    index: int
    existing_id: int | None = None
    existing_title: str | None = None
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "op": self.op.value,
            "index": self.index,
            "title": self.incoming.title,
            "kind": self.incoming.kind,
            "existing_id": self.existing_id,
            "existing_title": self.existing_title,
            "note": self.note,
        }


@dataclass
class ImportPlan:
    items: list[PlanItem] = field(default_factory=list)
    validation: ValidationReport = field(default_factory=ValidationReport)
    policy: str = "skip"
    strategy: str = "title"
    include_trashed_imports: bool = False

    @property
    def create_count(self) -> int:
        return sum(1 for item in self.items if item.op is PlanOp.CREATE)

    @property
    def overwrite_count(self) -> int:
        return sum(1 for item in self.items if item.op is PlanOp.OVERWRITE)

    @property
    def skip_count(self) -> int:
        return sum(
            1
            for item in self.items
            if item.op in {PlanOp.SKIP, PlanOp.SKIP_IDENTICAL}
        )

    def summary(self) -> str:
        return (
            f"create={self.create_count}  overwrite={self.overwrite_count}  "
            f"skip={self.skip_count}  total={len(self.items)}"
        )

    def to_dict(self) -> dict:
        return {
            "policy": self.policy,
            "strategy": self.strategy,
            "summary": {
                "create": self.create_count,
                "overwrite": self.overwrite_count,
                "skip": self.skip_count,
                "total": len(self.items),
            },
            "items": [item.to_dict() for item in self.items],
            "validation": {
                "ok": self.validation.ok,
                "errors": [i.format() for i in self.validation.errors],
                "warnings": [i.format() for i in self.validation.warnings],
            },
        }


def load_active_vault_entries(*, limit: int = 100_000) -> list[Entry]:
    return storage.list_entries(limit=limit, include_trashed=False)


def build_import_plan(
    document: ExportDocument,
    *,
    policy: str = "skip",
    strategy: str = "title",
    include_trashed_imports: bool = False,
    skip_identical: bool = True,
    verify_hashes: bool = True,
    vault_entries: list[Entry] | None = None,
) -> ImportPlan:
    """Build a dry-runable import plan against the current vault."""
    policy = normalize_conflict_policy(policy)
    strategy = normalize_match_strategy(strategy)
    validation = validate_document(document, verify_hashes=verify_hashes)
    validation.raise_if_errors()

    existing = vault_entries if vault_entries is not None else load_active_vault_entries()
    index = build_conflict_index(existing, strategy=strategy)

    plan = ImportPlan(
        validation=validation,
        policy=policy,
        strategy=strategy,
        include_trashed_imports=include_trashed_imports,
    )

    for i, incoming in enumerate(document.entries):
        if incoming.trashed and not include_trashed_imports:
            plan.items.append(
                PlanItem(
                    op=PlanOp.SKIP,
                    incoming=incoming,
                    index=i,
                    note="Skipping trashed import entry (pass --include-trashed).",
                )
            )
            continue

        action, match = resolve_action(
            incoming,
            index=index,
            strategy=strategy,
            policy=policy,
        )
        plan.items.append(
            _to_plan_item(
                action,
                incoming,
                index=i,
                match=match,
                skip_identical=skip_identical,
            )
        )
    return plan


def _to_plan_item(
    action: ConflictAction,
    incoming: ExportEntry,
    *,
    index: int,
    match: ConflictMatch | None,
    skip_identical: bool,
) -> PlanItem:
    if action is ConflictAction.CREATE:
        return PlanItem(op=PlanOp.CREATE, incoming=incoming, index=index)
    assert match is not None
    if action is ConflictAction.SKIP:
        if skip_identical and same_content(incoming, match.existing):
            return PlanItem(
                op=PlanOp.SKIP_IDENTICAL,
                incoming=incoming,
                index=index,
                existing_id=match.existing.id,
                existing_title=match.existing.title,
                note="Identical content; skipped.",
            )
        return PlanItem(
            op=PlanOp.SKIP,
            incoming=incoming,
            index=index,
            existing_id=match.existing.id,
            existing_title=match.existing.title,
            note=f"Conflict ({match.strategy}); skipped by policy.",
        )
    if action is ConflictAction.OVERWRITE:
        if skip_identical and same_content(incoming, match.existing):
            return PlanItem(
                op=PlanOp.SKIP_IDENTICAL,
                incoming=incoming,
                index=index,
                existing_id=match.existing.id,
                existing_title=match.existing.title,
                note="Identical content; overwrite not needed.",
            )
        return PlanItem(
            op=PlanOp.OVERWRITE,
            incoming=incoming,
            index=index,
            existing_id=match.existing.id,
            existing_title=match.existing.title,
            note="Will overwrite existing entry.",
        )
    # FAIL already raised in resolve_action
    return PlanItem(op=PlanOp.SKIP, incoming=incoming, index=index, note="unreachable")
