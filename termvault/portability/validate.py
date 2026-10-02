"""Deep validation for import documents before planning."""

from __future__ import annotations

from dataclasses import dataclass, field

from termvault.portability.checksums import entry_content_hash, hash_entries
from termvault.portability.constants import (
    MAX_BODY_LENGTH,
    MAX_IMPORT_ENTRIES,
    MAX_TAG_COUNT,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
)
from termvault.portability.errors import ImportValidationError
from termvault.portability.schema import ExportDocument, ExportEntry


@dataclass
class ValidationIssue:
    level: str  # error | warning
    path: str
    message: str

    def format(self) -> str:
        return f"[{self.level}] {self.path}: {self.message}"


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]

    def add(self, level: str, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(level, path, message))

    def raise_if_errors(self) -> None:
        if self.errors:
            first = self.errors[0]
            extra = (
                f" (+{len(self.errors) - 1} more)" if len(self.errors) > 1 else ""
            )
            raise ImportValidationError(
                f"{first.message}{extra}",
                path=first.path,
            )


def validate_document(
    document: ExportDocument,
    *,
    verify_hashes: bool = True,
    strict_manifest: bool = False,
) -> ValidationReport:
    """Validate document-level and per-entry constraints."""
    report = ValidationReport()
    if len(document.entries) > MAX_IMPORT_ENTRIES:
        report.add(
            "error",
            "entries",
            f"Too many entries ({len(document.entries)} > {MAX_IMPORT_ENTRIES}).",
        )

    seen_titles: dict[str, int] = {}
    for index, entry in enumerate(document.entries):
        path = f"entries[{index}]"
        _validate_entry(
            entry,
            path=path,
            report=report,
            verify_hashes=verify_hashes,
        )
        key = entry.title.strip().lower()
        if key in seen_titles:
            report.add(
                "warning",
                path,
                f"Duplicate title in import file (also at entries[{seen_titles[key]}]).",
            )
        else:
            seen_titles[key] = index

    if document.manifest.entry_count and document.manifest.entry_count != len(
        document.entries
    ):
        level = "error" if strict_manifest else "warning"
        report.add(
            level,
            "manifest.entry_count",
            (
                f"Manifest entry_count={document.manifest.entry_count} "
                f"but document has {len(document.entries)} entries."
            ),
        )

    if verify_hashes and document.manifest.content_hash:
        actual = hash_entries(document.entries)
        if actual != document.manifest.content_hash:
            level = "error" if strict_manifest else "warning"
            report.add(
                level,
                "manifest.content_hash",
                "Aggregate content hash does not match entries.",
            )

    return report


def _validate_entry(
    entry: ExportEntry,
    *,
    path: str,
    report: ValidationReport,
    verify_hashes: bool,
) -> None:
    if not entry.title.strip():
        report.add("error", f"{path}.title", "Title is required.")
    if len(entry.title) > MAX_TITLE_LENGTH:
        report.add(
            "error",
            f"{path}.title",
            f"Title too long ({len(entry.title)} > {MAX_TITLE_LENGTH}).",
        )
    if len(entry.body) > MAX_BODY_LENGTH:
        report.add(
            "error",
            f"{path}.body",
            f"Body too long ({len(entry.body)} > {MAX_BODY_LENGTH}).",
        )
    if len(entry.tags) > MAX_TAG_COUNT:
        report.add(
            "error",
            f"{path}.tags",
            f"Too many tags ({len(entry.tags)} > {MAX_TAG_COUNT}).",
        )
    for tag in entry.tags:
        if len(tag) > MAX_TAG_LENGTH:
            report.add(
                "error",
                f"{path}.tags",
                f"Tag too long: {tag!r} ({len(tag)} > {MAX_TAG_LENGTH}).",
            )
        if not tag:
            report.add("error", f"{path}.tags", "Empty tag is not allowed.")
    if verify_hashes and entry.content_hash:
        expected = entry_content_hash(entry)
        if expected != entry.content_hash:
            report.add(
                "warning",
                f"{path}.content_hash",
                "Stored content_hash does not match title/body/tags/kind.",
            )
