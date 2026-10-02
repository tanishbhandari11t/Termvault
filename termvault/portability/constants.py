"""Shared constants for Phase 6 Part 1 portability."""

from __future__ import annotations

from typing import Final

# On-disk format identity
EXPORT_FORMAT_NAME: Final[str] = "termvault-export"
EXPORT_FORMAT_VERSION: Final[int] = 1

# Supported codecs for Part 1
EXPORT_CODECS: Final[tuple[str, ...]] = ("json", "markdown")
DEFAULT_CODEC: Final[str] = "json"

# Conflict policies when an import entry matches an existing vault entry
CONFLICT_POLICIES: Final[tuple[str, ...]] = (
    "skip",
    "overwrite",
    "create",
    "fail",
)
DEFAULT_CONFLICT_POLICY: Final[str] = "skip"

# How to decide that two entries "match"
MATCH_STRATEGIES: Final[tuple[str, ...]] = ("title", "hash", "title+kind")
DEFAULT_MATCH_STRATEGY: Final[str] = "title"

# Safety limits
MAX_IMPORT_ENTRIES: Final[int] = 50_000
MAX_TITLE_LENGTH: Final[int] = 500
MAX_BODY_LENGTH: Final[int] = 500_000
MAX_TAG_COUNT: Final[int] = 50
MAX_TAG_LENGTH: Final[int] = 64
MAX_MARKDOWN_FILE_BYTES: Final[int] = 5_000_000

# Markdown conventions
MD_FRONTMATTER_DELIM: Final[str] = "---"
MD_ENTRY_SEPARATOR: Final[str] = "\n\n---\n\n"
MD_INDEX_FILENAME: Final[str] = "INDEX.md"
JSON_DEFAULT_FILENAME: Final[str] = "termvault-export.json"
MD_DEFAULT_FILENAME: Final[str] = "termvault-export.md"

# Manifest keys
MANIFEST_HASH_ALGO: Final[str] = "sha256"
