# Changelog

All notable user-facing changes to ChoreBoy Code Studio are documented here.

Release tags: `v0.1`, `v0.2`, `v0.4.5`.

## [0.4.5] - 2026-06-27

Tag: `v0.4.5`

Consolidates the untagged `0.3.2`-`0.4.4` development line into a single release.

### Added

- Run With Arguments dialog (`Ctrl+Shift+A`): live command preview, shell-style quoted argv, recent-runs history, working-directory and environment-variable editor, and Save as Configuration.
- Run Configurations two-pane editor for named configs in `cbcs/project.json`, with a status-bar active-config indicator driving Run/Debug Project.
- Project source roots (mark/unmark in the tree) for consistent import, completion, and test resolution.
- Rich autocomplete popup (kind icons, inline documentation, signature/return type, side-effect-risk indicator) shared by the editor and Python Console.
- Runner-backed dot completion for FreeCAD/PySide attribute paths, with curated API fallback when the REPL is unavailable.
- Markdown preview for `.md` files (source, preview, and split view; `Ctrl+Shift+V` toggle, `Ctrl+K V` split).
- High Contrast Light and High Contrast Dark theme modes (WCAG AAA), plus UI font-weight and neutral-gray dark-chrome preferences.
- Recovery Center, themed unsaved-changes dialog ("Keep for Next Launch"), and polished Recovery Draft / Local History dialogs with inline and side-by-side diff.
- Test Explorer: Run Test at Cursor and Debug Failed Test workflows, with discovery for nested classes and parametrized tests.
- Installable-only project packaging with an export validation gate, restyled Package Project wizard, and `vendor_py39` product pipeline.
- Flat-Python paste repair: auto re-indent for code pasted without indentation (for example, from PDFs), plus Paste and Re-indent / Re-indent Selection actions (`Ctrl+Alt+V`).

### Changed

- Background, non-blocking project open with progressive tree population and session-restored explorer state.
- Unified Clear Console policy (Python Console output, Run Log, and debug output) distinct from display-only panel clear.
- Argv parsing via `shlex` quoting; run dialogs restyled and scrollable across all four theme modes.
- Multi-line Tab/Shift+Tab now preserves the selection for repeated indent/outdent, and multi-line pastes land pre-selected.
- MainWindow decomposed into focused workflows; run launch split with exit-gated stop/restart.

### Fixed

- Stale autocomplete, navigation, and search results after cursor or buffer changes (generation-gated delivery).
- Auto-save no longer trims trailing whitespace on the line being typed; on-save transforms now run only on explicit Save.
- Installed project launchers run from `app_files/` without hand-editing `Exec=`.
- Run/debug session start-stop races, debug transport EOF/pause hangs, and breakpoint-sync drift.
- Theme-refresh gaps after layout rebuild, external-file-change polling crashes, and packaging failures now surfaced in the UI.

### Documentation

- Consistency remediation: unified test checkpoints, PRD shortcuts, four-theme manual coverage, runtime pitfalls/discovery docs, and missing doc index files.

## [0.2] - 2026-03-09

Tag: `v0.2`

### Added

- Test Explorer activity with discovery, run one/all, rerun failed, and navigate-to-test.
- Run configurations UI with named configs, default argv, and status-bar active-config indicator.
- Welcome / runtime onboarding flows and Runtime Center.
- High Contrast Light and High Contrast Dark theme modes with per-scope syntax color overrides.
- Markdown preview, split view, and toggle shortcuts for `.md` files.
- Local history and draft recovery workflows.

### Changed

- Shell/runner integration hardening for preflight, stop/restart, and theme-safe panels.
- Fast test shard (~30 s agent loop) with `slow` marker for subprocess/debug tests.

## [0.1] - Initial MVP

Tag: `v0.1`

### Added

- Editor + separate runner process architecture.
- Project open/edit/save, run log, problems panel, and basic debug support.
- Project templates (Qt app, headless tool, utility script).
- Plugin platform foundation and bundled workflow plugins.
- Visible project metadata (`cbcs/`) and global state (`choreboy_code_studio_state/`).
