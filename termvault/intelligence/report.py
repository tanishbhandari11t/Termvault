"""Plain-text rendering for find / related / index commands (ASCII only)."""

from __future__ import annotations

from termvault.formatting import body_snippet, kind_badge
from termvault.intelligence.hybrid import FindHit, FindResult
from termvault.intelligence.index import IndexBuildReport, IndexStatus, SemanticHit
from termvault.models import Entry

SOURCE_ORDER = ("fts", "fuzzy", "semantic")


def _entry_line(entry: Entry, score: float) -> str:
    pin = " *" if entry.pinned else ""
    return f"[{entry.id}]{pin} ({kind_badge(entry.kind)}) {entry.title}  score {score:.2f}"


def explain_hit(hit: FindHit) -> str:
    parts: list[str] = []
    for name in SOURCE_ORDER:
        source = hit.sources.get(name)
        if source is None:
            continue
        text = f"{name} #{source.rank}"
        if name == "semantic":
            text += f" ({source.score:.2f})"
        if source.detail:
            text += f" [{source.detail}]"
        parts.append(text)
    return "  via: " + (" | ".join(parts) if parts else "-")


def format_find_hit(hit: FindHit, *, explain: bool = False) -> str:
    entry = hit.entry
    lines = [_entry_line(entry, hit.score), f"  tags: {entry.tags_display()}"]
    preview = body_snippet(entry.body)
    if preview:
        lines.append(f"  {preview}")
    if explain:
        lines.append(explain_hit(hit))
    return "\n".join(lines)


def format_suggestions(suggestions: list[str]) -> str:
    return "Did you mean: " + ", ".join(f'"{item}"' for item in suggestions) + "?"


def format_find_result(result: FindResult, *, explain: bool = False) -> str:
    blocks: list[str] = []
    if not result.hits:
        blocks.append(f'No matches for "{result.query}" (mode: {result.mode}).')
    else:
        header = f'{len(result.hits)} result(s) for "{result.query}" (mode: {result.mode}'
        if result.backend_key:
            header += f", embeddings: {result.backend_key}"
        blocks.append(header + ")")
        blocks.extend(format_find_hit(hit, explain=explain) for hit in result.hits)
    if result.suggestions:
        blocks.append(format_suggestions(result.suggestions))
    return "\n\n".join(blocks)


def format_related(source: Entry, hits: list[SemanticHit]) -> str:
    header = f"Related to [{source.id}] {source.title}:"
    if not hits:
        return header + "\n  (nothing similar yet)"
    lines = [header]
    for hit in hits:
        lines.append(f"  {_entry_line(hit.entry, hit.score)}")
    return "\n".join(lines)


def format_index_status(status: IndexStatus) -> str:
    state = "up to date" if status.is_current else "needs refresh (run: tv index build)"
    lines = [
        f"Backend:  {status.backend_key or '(none - index is empty)'}",
        f"Active:   {status.active_entries}",
        f"Indexed:  {status.indexed}",
        f"Fresh:    {status.fresh}",
        f"Stale:    {status.stale}",
        f"Missing:  {status.missing}",
        f"Orphaned: {status.orphaned}",
        f"State:    {state}",
    ]
    if len(status.backends) > 1:
        mix = ", ".join(f"{key}={count}" for key, count in sorted(status.backends.items()))
        lines.append(f"Mixed backends: {mix}")
    return "\n".join(lines)


def format_build_report(report: IndexBuildReport) -> str:
    return (
        f"Index built with {report.backend_key}: "
        f"{report.embedded} embedded, {report.unchanged} unchanged, {report.removed} removed."
    )
