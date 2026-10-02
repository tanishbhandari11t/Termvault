# TermVault Phases

Work through these in order. Each phase should leave `tv` installable and tested.

## Phase 1 — CLI foundation ✅

**Goal:** Installable package with a working `tv` command.

- [x] Package layout + `pyproject.toml`
- [x] `tv --help` / `tv --version`
- [x] Basic error handling + Phase 1 tests

## Phase 2 — Local knowledge vault ✅

**Goal:** Store and manage notes locally with SQLite.

- [x] Local data directory + SQLite database
- [x] `tv add` / `tv list` / `tv show` / `tv edit` / `tv delete`
- [x] Optional tags on entries
- [x] Tests using an isolated temp database

**Try it:**

```bash
tv add "Fix postgres auth" --body "Reset role password, then reload pg_hba.conf" --tag db
tv list
tv show 1
tv edit 1 --title "Fix Postgres auth"
tv delete 1 --yes
```

## Phase 3 — Search ✅

**Goal:** Find notes fast from the terminal.

- [x] `tv search <query>`
- [x] SQLite FTS5 full-text search
- [x] Simple ranking + readable results

**Try it:**

```bash
tv search postgres
tv search docker cache --limit 5
```

## Phase 4 — Organization ✅ (expanded)

**Goal:** Keep a growing vault usable — enough depth that building this phase by hand is multi-hour work.

- [x] First-class tags (`tv tags`, `tv tag add|remove|rename`, `tv list --tag`)
- [x] Normalized tag tables + schema migrations
- [x] Entry kinds + pins + trash/restore/purge
- [x] Snippet-friendly formatting + JSON output
- [x] `tv recent` / filters / sorting polish
- [x] `tv stats` + `tv config` defaults

**Try it:**

```bash
tv add "API timeout" -b "raise read timeout to 30s" -t backend -k error --pin
tv tags
tv list --tag backend --kind error
tv recent --limit 5
tv tag rename backend api
tv stats --json
tv delete 1 --yes
tv restore 1
tv config --list-limit 15 --show
```

## Phase 5 Part 1 — Core TUI ✅ (~5hr hand-build)

**Goal:** Ship a usable two-pane Textual browser with enough depth that typing Part 1 from scratch takes **at least ~5 hours**.

**In the repo:**

- `termvault/tui/__init__.py`
- `termvault/tui/app.py`
- `termvault/tui/browser.py`
- `termvault/tui/constants.py`
- `termvault/tui/validation.py`
- `termvault/tui/drafts.py`
- `termvault/tui/search.py`
- `termvault/tui/display.py`
- `termvault/tui/widgets.py`
- `termvault/tui/screens.py`
- `termvault/tui/styles.tcss`
- `termvault/commands/tui.py`
- `tests/test_tui.py`

**Checklist:**

- [x] `tv tui` / `tv ui`
- [x] Two-pane list + detail + shortcut hints + CSS
- [x] Live search with history tracking
- [x] New / edit modals (validation, kind/tags, dirty cancel, draft autosave)
- [x] Pin + trash-with-confirm
- [x] Session selection memory / recent opened
- [x] Refresh / quit / search+list focus helpers
- [x] Broad Part 1 unit + Textual pilot tests
- [x] CLI remains the stable API

**Try it:**

```bash
tv tui
```

Keys: `/` search · `n` new · `e` edit · `p` pin · `d` trash · `r` refresh · `Ctrl+S` save · `Ctrl+D` draft · `q` quit

## Phase 5 Part 2 — Advanced TUI ✅ (~5hr hand-build)

**Goal:** Power-user chrome on top of Part 1 — enough depth that typing Part 2 from scratch takes **at least ~5 hours**.

**In the repo now (new vs Part 1):**

- `termvault/tui/filters.py`
- `termvault/tui/filter_presets.py`
- `termvault/tui/actions_advanced.py`
- `termvault/tui/palette.py`
- `termvault/tui/helptext.py`
- `termvault/tui/clipboard_util.py`
- `termvault/tui/navigation.py`
- `termvault/tui/screens_advanced.py`
- Expanded `app.py` / `widgets.py` / `styles.tcss` / `display.py` / `constants.py`
- `tests/test_tui_part2.py`

**Checklist:**

- [x] Tag sidebar filtering
- [x] Command palette (`:` / `Ctrl+P`) with ranked multi-token filter
- [x] Help + stats overlays
- [x] Vim navigation (`j`/`k`/`g`/`G`) + nav helpers
- [x] Sort / kind / pinned-only / trash-view cycles + filter presets
- [x] Restore + copy body/title/meta to clipboard
- [x] Permanent delete confirm while in trash view
- [x] Broad Part 2 unit + Textual pilot tests
- [x] CLI remains the stable API

**Try it:**

```bash
tv tui
```

Keys: `?` help · `:` palette · `t` trash view · `o` sort · `K` kind · `P` pinned · `u` restore · `y` copy · `j`/`k` move · `#` clear filters

## Phase 6 Part 1 — Export / Import ✅ (~6hr+ hand-build)

**Goal:** Move knowledge between machines via portable files — deep enough that typing Part 1 from scratch takes **more than 6 hours**.

**In the repo now:**

- `termvault/portability/` package:
  - `schema.py` — export document + entry + manifest models
  - `checksums.py` — stable content hashes
  - `filters.py` / `selection.py` — what to export
  - `json_format.py` / `markdown_format.py` — codecs
  - `detect.py` / `paths.py` / `validate.py`
  - `conflicts.py` / `planner.py` — match + dry-run plan
  - `exporter.py` / `importer.py` / `report.py`
- `termvault/commands/portability.py` — `tv export` / `tv import`
- `tests/test_portability.py`

**Checklist:**

- [x] JSON export/import with format version + manifest
- [x] Markdown export/import (frontmatter, multi-entry, dir of files)
- [x] Filters: tag / kind / pinned / trash / query / ids / limit
- [x] Conflict policies: skip / overwrite / create / fail
- [x] Match strategies: title / hash / title+kind
- [x] Dry-run + preview + JSON reports
- [x] Validation + content hashes
- [x] Broad unit + CLI tests
- [x] CLI remains the stable API

**Try it:**

```bash
tv export ./vault.json -f json --force
tv export ./vault.md -f markdown --force
tv import ./vault.json --dry-run -v
tv import ./vault.json --conflict overwrite
```

## Phase 6 Part 2 — Backup / Restore ✅ (current, ~6hr+ hand-build)

**Goal:** Whole-vault safety net: exact copies of the database and settings that can be verified and restored without losing data.

**In the repo now:**

- `termvault/backup/` package:
  - `manifest.py` — archive manifest (files, hashes, schema version, stats)
  - `integrity.py` — SHA-256 hashing, SQLite integrity / schema / stats checks
  - `snapshot.py` — consistent live-database copy via SQLite's backup API
  - `archive.py` — atomic zip writing, path-safety checks, verified extraction
  - `naming.py` / `store.py` — backup filenames, listing, `latest`, pruning
  - `creator.py` / `verifier.py` / `restorer.py` / `report.py`
- `termvault/clipboard.py` — cross-platform clipboard (`clip` / `pbcopy` / `wl-copy` / `xclip` / `xsel`)
- `termvault/commands/backup.py` — `tv backup …` / `tv copy`
- `tests/test_backup.py`

**Checklist:**

- [x] `tv backup create` (label, custom path, optional drafts + readable export.json)
- [x] `tv backup list` / `info` / `verify` (checksums, SQLite health, schema compatibility)
- [x] `tv backup restore` with dry-run, confirmation, automatic safety backup
- [x] Rollback to the previous vault if a restore fails mid-way
- [x] Older-schema backups upgraded on restore; newer-schema backups refused
- [x] `tv backup prune` (keep N / older than N days; newest always kept)
- [x] `tv copy ID` clipboard helper (body / title / meta / json / markdown)
- [x] Broad unit + CLI tests

**Try it:**

```bash
tv backup create --label before-cleanup
tv backup list
tv backup verify latest
tv backup restore latest --dry-run
tv backup restore latest
tv backup prune --keep 5 --yes
tv copy 1 --field json
```

## Phase 7 — Intelligence (optional)

**Goal:** Smarter retrieval without leaving local-first defaults.

- [ ] Fuzzy matching refinements
- [ ] Optional embeddings / semantic search
- [ ] Optional sync (explicit opt-in only)

---

**Rule:** Finish the current phase’s checklist and tests before starting the next one.
