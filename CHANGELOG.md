# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.8.0] - 2026-09-29

### Added

- Phase 6 Part 2 backup / restore (~6 hour+ hand-implementation scope)
- `tv backup create|list|info|verify|restore|prune`
- Zip archives with a manifest of SHA-256 hashes, schema version, and entry stats
- Consistent snapshots via SQLite's online backup API
- Restore safety backup, dry-run, confirmation, and automatic rollback on failure
- Schema compatibility checks (older upgraded, newer refused)
- `tv copy ID` cross-platform clipboard helper
- `tests/test_backup.py`

## [0.7.0] - 2026-09-18

### Added

- Phase 6 Part 1 portability (~6 hour+ hand-implementation scope)
- `tv export` / `tv import` with JSON and Markdown codecs
- Export filters (tag/kind/pinned/trash/query/ids), manifests, content hashes
- Import conflict policies (skip/overwrite/create/fail) + match strategies
- Dry-run / preview / JSON reports and `tests/test_portability.py`

## [0.6.0] - 2026-09-16

### Added

- Phase 5 Part 2 advanced TUI (~5 hour hand-implementation scope)
- Tag sidebar filtering, filter presets, sort/kind/pinned/trash-view cycles
- Command palette (`:` / `Ctrl+P`) with ranked multi-token matching
- Help + vault stats overlays
- Vim-style navigation helpers (`j`/`k`/`g`/`G`)
- Restore from trash, permanent-delete confirm in trash view
- Clipboard yank for body / title / metadata
- `tests/test_tui_part2.py` coverage for Part 2 modules + Pilot flows

## [0.5.3] - 2026-09-15

### Added

- Expanded Phase 5 Part 1 toward a ~5 hour hand-implementation scope
- TUI form validation, draft autosave, search history, display helpers
- Shortcut hints bar, richer confirm/edit/new flows, session recent-opened

## [0.5.2] - 2026-09-15

### Changed

- Split Phase 5 into Part 1 (core TUI) and Part 2 (advanced TUI)
- Kept only Phase 5 Part 1 files in the tree
- Removed Part 2 features: tag sidebar, command palette, help/stats overlays,
  vim navigation, trash-view/restore/copy, sort/kind filter cycles

## [0.5.1] - 2026-09-15

### Added

- Expanded Phase 5 TUI: tag sidebar, sort/kind/trash/pinned filters
- Help + stats overlays, command palette (`:` / `ctrl+p`)
- Vim-style navigation (`j`/`k`/`g`/`G`)
- Richer new/edit modals (kind + tags)
- Restore / copy-body actions, external `styles.tcss`
- Broader Textual pilot coverage for Phase 5

## [0.5.0] - 2026-09-15

### Added

- Interactive Textual TUI via `tv tui` / `tv ui`
- Two-pane browser with live search filter
- Keyboard actions for new/edit/pin/trash/refresh
- Phase 5 Textual pilot tests

## [0.4.1] - 2026-09-13

### Added

- Schema migrations + normalized `tags` / `entry_tags` tables
- Entry kinds (`note`, `snippet`, `command`, `link`, `error`)
- Pins (`tv pin` / `tv unpin`) with pinned-first sorting
- Soft delete trash (`tv delete`, `tv restore`, `tv purge`, `tv list --trash`)
- `tv tag rename`, `tv stats`, `tv config`
- JSON output (`--json`) across list/search/tags/stats/show
- Persisted defaults in `~/.termvault/config.json`

## [0.4.0] - 2026-09-12

### Added

- `tv tags` to list tags with usage counts
- `tv tag add` / `tv tag remove` for per-entry tag edits
- `tv list --tag`, `--sort`, and `--snippets/--no-snippets`
- `tv recent` for latest updated entries
- Snippet-friendly list/search previews and cleaner `tv show` body formatting

## [0.3.0] - 2026-09-12

### Added

- `tv search` with SQLite FTS5 full-text search
- BM25 ranking and result snippets
- Prefix matching (e.g. `post` matches `postgres`)
- Automatic FTS backfill for existing Phase 2 vaults

## [0.2.0] - 2026-09-12

### Added

- Local SQLite vault stored under `~/.termvault/`
- Entry commands: `tv add`, `tv list`, `tv show`, `tv edit`, `tv delete`
- Optional tags on entries
- `TERMVAULT_DATA_DIR` override for isolated vaults/tests
- Phase roadmap in `PHASES.md`

## [0.1.0] - 2026-09-10

### Added

- Initial project foundation and packaging (`pyproject.toml`)
- `tv` CLI entry point with `--help` and `--version`
- Basic CLI error handling
- Phase 1 test suite for the CLI foundation
