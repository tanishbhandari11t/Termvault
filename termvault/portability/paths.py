"""Path helpers for safe export / import file IO."""

from __future__ import annotations

from pathlib import Path

from termvault.portability.constants import (
    JSON_DEFAULT_FILENAME,
    MD_DEFAULT_FILENAME,
)
from termvault.portability.errors import ExportError, ImportError_


def resolve_export_path(
    destination: str | Path,
    *,
    codec: str,
    force_directory: bool = False,
) -> Path:
    """Resolve where an export should be written.

    - If destination is an existing directory (or ends with sep / force_directory),
      write a default filename inside it.
    - Otherwise treat destination as a file path.
    """
    path = Path(destination).expanduser()
    if force_directory or str(destination).endswith(("/", "\\")) or (
        path.exists() and path.is_dir()
    ):
        path.mkdir(parents=True, exist_ok=True)
        filename = (
            JSON_DEFAULT_FILENAME if codec == "json" else MD_DEFAULT_FILENAME
        )
        return (path / filename).resolve()

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_text_file(path: Path, *, max_bytes: int | None = None) -> str:
    if not path.exists():
        raise ImportError_(f"Import path not found: {path}")
    if not path.is_file():
        raise ImportError_(f"Import path is not a file: {path}")
    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        raise ImportError_(
            f"Import file too large ({size} bytes; max {max_bytes})."
        )
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ImportError_(f"Unable to read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ImportError_(f"Import file is not valid UTF-8: {path}") from exc


def write_text_file(path: Path, text: str, *, overwrite: bool = False) -> Path:
    target = path.resolve()
    if target.exists() and not overwrite:
        raise ExportError(
            f"Refusing to overwrite existing file: {target} (pass --force)"
        )
    ensure_parent_dir(target)
    try:
        target.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        raise ExportError(f"Unable to write {target}: {exc}") from exc
    return target


def list_markdown_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        raise ImportError_(f"Not a directory: {directory}")
    files = sorted(
        p
        for p in directory.iterdir()
        if p.is_file() and p.suffix.lower() in {".md", ".markdown"}
    )
    if not files:
        raise ImportError_(f"No markdown files found in {directory}")
    return files
