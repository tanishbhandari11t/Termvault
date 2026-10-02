# TermVault

A local-first terminal knowledge base for developers.

## Problem

Developers repeatedly search for commands, debugging solutions, code snippets, and notes across browsers, documentation, and scattered files.

## Vision

TermVault aims to become a developer's searchable second brain directly inside the terminal.

## Current status

**Phase 6** is complete: portable export/import (Part 1) and full-vault backup/restore (Part 2).

- `tv export` / `tv import` move entries between vaults as JSON or Markdown
- `tv backup create|list|verify|restore|prune` keep exact, verified copies of the whole vault
- `tv copy ID` puts an entry on the system clipboard
- Phase 5 TUI remains available via `tv tui`
- Next (optional): Phase 7 — smarter search

See [PHASES.md](PHASES.md).

## Installation

```bash
git clone <repository-url>
cd termvault
pip install -e .
```

## Quick start

```bash
tv add "Fix postgres auth" -b "Reset role password" -t db -k command --pin
tv export ./vault.json -f json --force
tv import ./vault.json --dry-run -v
tv backup create --label first
tv tui
```

| Command | What it does |
|---------|----------------|
| `tv export PATH` | Write vault entries to JSON or Markdown |
| `tv import PATH` | Import from an export file (with conflict policy) |
| `tv backup create` | Zip up the whole vault (database + settings) |
| `tv backup restore latest` | Put a backup back (takes a safety backup first) |
| `tv copy ID` | Copy an entry to the clipboard |
| `tv tui` | Interactive browser |

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).
