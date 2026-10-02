"""Human / JSON reports for export and import operations."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from termvault.portability.planner import ImportPlan, PlanOp
from termvault.portability.schema import ExportDocument


@dataclass
class ExportReport:
    path: Path | None
    codec: str
    entry_count: int
    filters_summary: str
    content_hash: str | None = None
    dry_run: bool = False
    preview_titles: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path) if self.path else None,
            "codec": self.codec,
            "entry_count": self.entry_count,
            "filters": self.filters_summary,
            "content_hash": self.content_hash,
            "dry_run": self.dry_run,
            "preview_titles": self.preview_titles,
        }

    def format_text(self) -> str:
        lines = [
            "Export " + ("preview (dry-run)" if self.dry_run else "complete"),
            f"  codec:   {self.codec}",
            f"  entries: {self.entry_count}",
            f"  filters: {self.filters_summary}",
        ]
        if self.path:
            lines.append(f"  path:    {self.path}")
        if self.content_hash:
            lines.append(f"  hash:    {self.content_hash[:16]}…")
        if self.preview_titles:
            lines.append("  preview:")
            for title in self.preview_titles[:10]:
                lines.append(f"    - {title}")
            if len(self.preview_titles) > 10:
                lines.append(f"    … +{len(self.preview_titles) - 10} more")
        return "\n".join(lines)


@dataclass
class ImportApplyReport:
    plan: ImportPlan
    created_ids: list[int] = field(default_factory=list)
    overwritten_ids: list[int] = field(default_factory=list)
    dry_run: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = self.plan.to_dict()
        payload["dry_run"] = self.dry_run
        payload["created_ids"] = self.created_ids
        payload["overwritten_ids"] = self.overwritten_ids
        return payload

    def format_text(self, *, verbose: bool = False) -> str:
        label = "Import plan (dry-run)" if self.dry_run else "Import applied"
        lines = [
            label,
            f"  policy:  {self.plan.policy}",
            f"  match:   {self.plan.strategy}",
            f"  {self.plan.summary()}",
        ]
        if self.plan.validation.warnings:
            lines.append(f"  warnings: {len(self.plan.validation.warnings)}")
        if not self.dry_run:
            if self.created_ids:
                lines.append(
                    f"  created ids: {', '.join(map(str, self.created_ids))}"
                )
            if self.overwritten_ids:
                lines.append(
                    "  overwritten ids: "
                    + ", ".join(map(str, self.overwritten_ids))
                )
        if verbose:
            lines.append("  steps:")
            for item in self.plan.items:
                extra = f" → #{item.existing_id}" if item.existing_id else ""
                lines.append(f"    [{item.op.value}] {item.incoming.title}{extra}")
        return "\n".join(lines)


def format_document_preview(document: ExportDocument, *, limit: int = 10) -> str:
    lines = [
        f"Document: {document.format} v{document.version}",
        f"Entries:  {len(document.entries)}",
        f"Exported: {document.exported_at}",
    ]
    for entry in document.entries[:limit]:
        pin = "★" if entry.pinned else "·"
        lines.append(f"  {pin} ({entry.kind}) {entry.title}")
    if len(document.entries) > limit:
        lines.append(f"  … +{len(document.entries) - limit} more")
    return "\n".join(lines)


def dumps_report_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def count_ops(plan: ImportPlan) -> dict[str, int]:
    counts = {op.value: 0 for op in PlanOp}
    for item in plan.items:
        counts[item.op.value] += 1
    return counts
