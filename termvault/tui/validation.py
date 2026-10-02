"""Form validation for Phase 5 Part 1 new/edit screens."""

from __future__ import annotations

from dataclasses import dataclass

from termvault.config import VALID_KINDS
from termvault.tui.constants import (
    MAX_BODY_LENGTH,
    MAX_TAG_COUNT,
    MAX_TAG_LENGTH,
    MAX_TITLE_LENGTH,
)


@dataclass(frozen=True)
class FormData:
    """Normalized values collected from a new/edit modal."""

    title: str
    body: str
    kind: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a TUI form."""

    ok: bool
    data: FormData | None = None
    error: str | None = None


def parse_tags(raw: str) -> tuple[str, ...]:
    """Split a comma-separated tag string into normalized unique tags."""
    seen: set[str] = set()
    tags: list[str] = []
    for part in raw.split(","):
        tag = part.strip().lower()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
    return tuple(sorted(tags))


def validate_entry_form(
    *,
    title: str,
    body: str,
    kind: str,
    tags_raw: str,
) -> ValidationResult:
    """Validate user input from the new/edit modals."""
    cleaned_title = " ".join(title.split()).strip()
    if not cleaned_title:
        return ValidationResult(ok=False, error="Title is required.")
    if len(cleaned_title) > MAX_TITLE_LENGTH:
        return ValidationResult(
            ok=False,
            error=f"Title must be {MAX_TITLE_LENGTH} characters or fewer.",
        )

    cleaned_body = body.replace("\r\n", "\n").replace("\r", "\n")
    if len(cleaned_body) > MAX_BODY_LENGTH:
        return ValidationResult(
            ok=False,
            error=f"Body must be {MAX_BODY_LENGTH} characters or fewer.",
        )

    cleaned_kind = (kind or "note").strip().lower()
    if cleaned_kind not in VALID_KINDS:
        return ValidationResult(
            ok=False,
            error="Kind must be one of: " + ", ".join(VALID_KINDS),
        )

    tags = parse_tags(tags_raw)
    if len(tags) > MAX_TAG_COUNT:
        return ValidationResult(
            ok=False,
            error=f"At most {MAX_TAG_COUNT} tags are allowed.",
        )
    for tag in tags:
        if len(tag) > MAX_TAG_LENGTH:
            return ValidationResult(
                ok=False,
                error=f"Tag '{tag}' is longer than {MAX_TAG_LENGTH} characters.",
            )
        if any(ch.isspace() for ch in tag):
            return ValidationResult(
                ok=False,
                error=f"Tag '{tag}' cannot contain spaces.",
            )

    return ValidationResult(
        ok=True,
        data=FormData(
            title=cleaned_title,
            body=cleaned_body,
            kind=cleaned_kind,
            tags=tags,
        ),
    )


def forms_equal(left: FormData, right: FormData) -> bool:
    """Return True when two form payloads are identical."""
    return (
        left.title == right.title
        and left.body == right.body
        and left.kind == right.kind
        and left.tags == right.tags
    )
