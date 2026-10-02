"""Knowledge-entry and organization CLI commands for TermVault."""

from __future__ import annotations

from typing import Optional

import typer

from termvault import storage
from termvault.config import (
    VALID_KINDS,
    VALID_OUTPUT_FORMATS,
    VALID_SORTS,
    VaultSettings,
    load_settings,
    save_settings,
)
from termvault.errors import TermVaultError
from termvault.formatting import (
    dumps_json,
    format_entry_detail,
    format_entry_summary,
    format_search_hit,
    format_stats,
    format_tag_counts,
)

tag_app = typer.Typer(help="Add, remove, or rename tags.")


def _fail(exc: TermVaultError) -> None:
    typer.echo(f"Error: {exc}", err=True)
    raise typer.Exit(code=1) from None


def _emit(text: str) -> None:
    typer.echo(text)


def _wants_json(explicit: Optional[bool]) -> bool:
    if explicit is True:
        return True
    if explicit is False:
        return False
    return load_settings().default_output == "json"


def add_command(
    title: str = typer.Argument(..., help="Short title for the knowledge entry."),
    body: str = typer.Option("", "--body", "-b", help="Entry body / notes."),
    tag: Optional[list[str]] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Tag to attach (repeatable).",
    ),
    kind: str = typer.Option(
        "note",
        "--kind",
        "-k",
        help=f"Entry kind: {', '.join(VALID_KINDS)}.",
    ),
    pin: bool = typer.Option(False, "--pin", help="Pin the entry immediately."),
) -> None:
    """Add a new knowledge entry to the local vault."""
    try:
        entry = storage.add_entry(
            title=title,
            body=body,
            tags=tag,
            kind=kind,
            pinned=pin,
        )
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Added entry {entry.id}: {entry.title}")


def list_command(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Max entries to show.",
    ),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by tag."),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Filter by kind."),
    sort: Optional[str] = typer.Option(
        None,
        "--sort",
        "-s",
        help=f"Sort by: {', '.join(VALID_SORTS)}.",
    ),
    pinned: bool = typer.Option(False, "--pinned", help="Only pinned entries."),
    trash: bool = typer.Option(False, "--trash", help="Only trashed entries."),
    snippets: Optional[bool] = typer.Option(
        None,
        "--snippets/--no-snippets",
        help="Show a short body preview for each entry.",
    ),
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """List knowledge entries with organization filters."""
    settings = load_settings()
    try:
        entries = storage.list_entries(
            limit=limit or settings.default_list_limit,
            tag=tag,
            kind=kind,
            sort=sort or settings.default_sort,
            pinned_only=pinned,
            trashed_only=trash,
        )
    except TermVaultError as exc:
        _fail(exc)

    show_snippets = settings.show_snippets if snippets is None else snippets
    if _wants_json(as_json):
        _emit(dumps_json([entry.to_dict() for entry in entries]))
        return

    if not entries:
        if tag:
            _emit(f'No entries tagged "{tag}".')
        elif trash:
            _emit("Trash is empty.")
        else:
            _emit('No entries yet. Add one with: tv add "Your title"')
        return

    blocks = [
        format_entry_summary(entry, show_snippet=show_snippets) for entry in entries
    ]
    _emit("\n".join(blocks))


def recent_command(
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Max entries to show.",
    ),
    snippets: Optional[bool] = typer.Option(
        None,
        "--snippets/--no-snippets",
        help="Show a short body preview for each entry.",
    ),
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """Show the most recently updated active entries."""
    settings = load_settings()
    try:
        entries = storage.recent_entries(limit=limit or settings.default_recent_limit)
    except TermVaultError as exc:
        _fail(exc)

    show_snippets = settings.show_snippets if snippets is None else snippets
    if _wants_json(as_json):
        _emit(dumps_json([entry.to_dict() for entry in entries]))
        return

    if not entries:
        _emit('No entries yet. Add one with: tv add "Your title"')
        return

    _emit(
        "\n".join(
            format_entry_summary(entry, show_snippet=show_snippets) for entry in entries
        )
    )


def show_command(
    entry_id: int = typer.Argument(..., help="Entry id to display."),
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """Show full details for one entry (including trashed)."""
    try:
        entry = storage.get_entry(entry_id, include_trashed=True)
    except TermVaultError as exc:
        _fail(exc)

    if _wants_json(as_json):
        _emit(dumps_json(entry.to_dict()))
        return
    _emit(format_entry_detail(entry))


def edit_command(
    entry_id: int = typer.Argument(..., help="Entry id to edit."),
    title: Optional[str] = typer.Option(None, "--title", help="New title."),
    body: Optional[str] = typer.Option(None, "--body", "-b", help="New body."),
    tag: Optional[list[str]] = typer.Option(
        None,
        "--tag",
        "-t",
        help="Replace tags (repeatable).",
    ),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="New entry kind."),
) -> None:
    """Edit an existing active knowledge entry."""
    if title is None and body is None and tag is None and kind is None:
        typer.echo(
            "Error: provide --title, --body, --tag, and/or --kind to edit.",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        entry = storage.update_entry(
            entry_id,
            title=title,
            body=body,
            tags=tag,
            kind=kind,
        )
    except TermVaultError as exc:
        _fail(exc)

    _emit(f"Updated entry {entry.id}: {entry.title}")


def delete_command(
    entry_id: int = typer.Argument(..., help="Entry id to delete."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    permanent: bool = typer.Option(
        False,
        "--permanent",
        help="Permanently delete instead of moving to trash.",
    ),
) -> None:
    """Move an entry to trash, or permanently delete it."""
    try:
        entry = storage.get_entry(entry_id, include_trashed=True)
    except TermVaultError as exc:
        _fail(exc)

    action = "permanently delete" if permanent else "trash"
    if not yes:
        confirmed = typer.confirm(f"{action.capitalize()} entry {entry.id} ({entry.title})?")
        if not confirmed:
            _emit("Cancelled.")
            raise typer.Exit(code=0)

    try:
        deleted = storage.delete_entry(entry_id, permanent=permanent)
    except TermVaultError as exc:
        _fail(exc)

    if permanent:
        _emit(f"Permanently deleted entry {deleted.id}: {deleted.title}")
    else:
        _emit(f"Trashed entry {deleted.id}: {deleted.title}")


def restore_command(
    entry_id: int = typer.Argument(..., help="Trashed entry id to restore."),
) -> None:
    """Restore an entry from the trash."""
    try:
        entry = storage.restore_entry(entry_id)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Restored entry {entry.id}: {entry.title}")


def purge_command(
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Permanently delete every trashed entry."""
    if not yes:
        confirmed = typer.confirm("Permanently delete ALL trashed entries?")
        if not confirmed:
            _emit("Cancelled.")
            raise typer.Exit(code=0)
    try:
        count = storage.purge_trashed()
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Purged {count} trashed entr{'y' if count == 1 else 'ies'}.")


def pin_command(
    entry_id: int = typer.Argument(..., help="Entry id to pin."),
) -> None:
    """Pin an entry so it sorts above others."""
    try:
        entry = storage.set_pinned(entry_id, True)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Pinned entry {entry.id}: {entry.title}")


def unpin_command(
    entry_id: int = typer.Argument(..., help="Entry id to unpin."),
) -> None:
    """Remove the pin from an entry."""
    try:
        entry = storage.set_pinned(entry_id, False)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Unpinned entry {entry.id}: {entry.title}")


def _did_you_mean(query: str, *, tag: Optional[str], kind: Optional[str]) -> str:
    from termvault.intelligence.corpus import load_corpus
    from termvault.intelligence.report import format_suggestions
    from termvault.intelligence.suggest import suggest_queries

    try:
        suggestions = suggest_queries(query, load_corpus(tag=tag, kind=kind))
    except TermVaultError:
        return ""
    if not suggestions:
        return ""
    return f'{format_suggestions(suggestions)}  (or try: tv find "{query}")'


def search_command(
    query: list[str] = typer.Argument(..., help="Search terms."),
    limit: Optional[int] = typer.Option(
        None,
        "--limit",
        "-n",
        min=1,
        help="Max results to show.",
    ),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Require this tag."),
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help="Require this kind."),
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """Search the vault with full-text matching."""
    joined = " ".join(query).strip()
    if not joined:
        typer.echo("Error: search query is required.", err=True)
        raise typer.Exit(code=1)

    settings = load_settings()
    try:
        hits = storage.search_entries(
            joined,
            limit=limit or settings.default_search_limit,
            tag=tag,
            kind=kind,
        )
    except TermVaultError as exc:
        _fail(exc)

    if _wants_json(as_json):
        _emit(dumps_json([hit.to_dict() for hit in hits]))
        return

    if not hits:
        _emit(f'No matches for "{joined}".')
        hint = _did_you_mean(joined, tag=tag, kind=kind)
        if hint:
            _emit(hint)
        return

    _emit(f'{len(hits)} match(es) for "{joined}":\n')
    _emit("\n\n".join(format_search_hit(hit) for hit in hits))


def tags_command(
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """List all tags with usage counts."""
    try:
        tags = storage.list_tags()
    except TermVaultError as exc:
        _fail(exc)

    if _wants_json(as_json):
        _emit(dumps_json([tag.to_dict() for tag in tags]))
        return
    _emit(format_tag_counts(tags))


def stats_command(
    as_json: Optional[bool] = typer.Option(
        None,
        "--json/--text",
        help="Emit JSON instead of text.",
    ),
) -> None:
    """Show vault organization statistics."""
    try:
        stats = storage.vault_stats()
    except TermVaultError as exc:
        _fail(exc)

    if _wants_json(as_json):
        _emit(dumps_json(stats.to_dict()))
        return
    _emit(format_stats(stats))


def config_command(
    list_limit: Optional[int] = typer.Option(None, "--list-limit", min=1),
    recent_limit: Optional[int] = typer.Option(None, "--recent-limit", min=1),
    search_limit: Optional[int] = typer.Option(None, "--search-limit", min=1),
    sort: Optional[str] = typer.Option(None, "--sort", help=f"One of {', '.join(VALID_SORTS)}."),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        help=f"One of {', '.join(VALID_OUTPUT_FORMATS)}.",
    ),
    snippets: Optional[bool] = typer.Option(
        None,
        "--snippets/--no-snippets",
        help="Default snippet previews on list/recent.",
    ),
    show: bool = typer.Option(False, "--show", help="Print the current settings."),
) -> None:
    """View or update local TermVault defaults."""
    settings = load_settings()
    changed = False

    if list_limit is not None:
        settings.default_list_limit = list_limit
        changed = True
    if recent_limit is not None:
        settings.default_recent_limit = recent_limit
        changed = True
    if search_limit is not None:
        settings.default_search_limit = search_limit
        changed = True
    if sort is not None:
        settings.default_sort = sort
        changed = True
    if output is not None:
        settings.default_output = output
        changed = True
    if snippets is not None:
        settings.show_snippets = snippets
        changed = True

    if changed:
        try:
            path = save_settings(settings)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=1) from None
        _emit(f"Saved settings to {path}")

    if show or not changed:
        payload = {
            "default_list_limit": settings.default_list_limit,
            "default_recent_limit": settings.default_recent_limit,
            "default_search_limit": settings.default_search_limit,
            "default_sort": settings.default_sort,
            "default_output": settings.default_output,
            "show_snippets": settings.show_snippets,
        }
        _emit(dumps_json(payload))


@tag_app.command("add")
def tag_add_command(
    entry_id: int = typer.Argument(..., help="Entry id to tag."),
    tag: str = typer.Argument(..., help="Tag name to add."),
) -> None:
    """Add a tag to an entry."""
    try:
        entry = storage.add_tag(entry_id, tag)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Tags for entry {entry.id}: {entry.tags_display()}")


@tag_app.command("remove")
def tag_remove_command(
    entry_id: int = typer.Argument(..., help="Entry id to update."),
    tag: str = typer.Argument(..., help="Tag name to remove."),
) -> None:
    """Remove a tag from an entry."""
    try:
        entry = storage.remove_tag(entry_id, tag)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Tags for entry {entry.id}: {entry.tags_display()}")


@tag_app.command("rename")
def tag_rename_command(
    old_name: str = typer.Argument(..., help="Existing tag name."),
    new_name: str = typer.Argument(..., help="New tag name."),
) -> None:
    """Rename a tag across the whole vault."""
    try:
        count = storage.rename_tag(old_name, new_name)
    except TermVaultError as exc:
        _fail(exc)
    _emit(f"Renamed tag '{old_name}' -> '{new_name}' on {count} entr{'y' if count == 1 else 'ies'}.")


def register_entry_commands(app: typer.Typer) -> None:
    """Register Phase 2-4 commands on the root app."""
    app.command("add")(add_command)
    app.command("list")(list_command)
    app.command("recent")(recent_command)
    app.command("show")(show_command)
    app.command("edit")(edit_command)
    app.command("delete")(delete_command)
    app.command("restore")(restore_command)
    app.command("purge")(purge_command)
    app.command("pin")(pin_command)
    app.command("unpin")(unpin_command)
    app.command("search")(search_command)
    app.command("tags")(tags_command)
    app.command("stats")(stats_command)
    app.command("config")(config_command)
    app.add_typer(tag_app, name="tag")
