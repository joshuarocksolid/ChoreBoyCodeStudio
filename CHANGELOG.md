# Changelog

All notable user-facing changes to ChoreBoy Code Studio are documented here.

Release tags: `v0.1`, `v0.2`, `v0.4.5`, `v0.4.9`, `v0.4.10`, `v0.4.11`.

LibrePy list mail-outs: v0.4.5 on 2026-06-27, v0.4.7 on 2026-06-30, v0.4.8 on 2026-08-24, v0.4.9 on 2026-08-31. Next list mail-out is v0.4.12.

## [Unreleased]

## [0.4.12] - 2026-09-03

Follow-up to the v0.4.11 shop-LAN state default. A probed state-root default per parent directory, and a visible icon fallback for packaged-app shortcuts.

### Changed

- Code Studio probes each candidate parent directory before it chooses where to keep its state, instead of always using a hard-coded hidden path. Where a hidden file or hidden directory is denied, or the parent is unknown, it falls back to a safe visible name. Machines that already have a root from the env var, a pointer, or a legacy state directory keep the root they have (PR #69).

### Fixed

- Desktop shortcuts for packaged apps no longer fail the install when the hidden icon name is denied. The shortcut copies a visible sidecar icon instead and points `Icon=` at whichever copy succeeded (PR #69).

## [0.4.11] - 2026-09-01

Follow-up to the v0.4.10 ELF hotfix. Desktop icons for packaged apps, and a shop-LAN default for Code Studio state.

### Fixed

- Desktop shortcuts for packaged apps that install under `~/.local` now copy the icon next to the shortcut as a hidden sibling and rewrite `Icon=` on the published copy so the ChoreBoy file manager can show it (Ervin Newswanger, PR #66 / ops thread 27258, `email:48687`). Apps stay in `$HOME/.local/share/FreeCAD/Macro/Apps/`; they are not moved to Desktop.

### Changed

- New machines default Code Studio state to `/home/default/FreeCAD/choreboy_code_studio_state` instead of `$HOME/choreboy_code_studio_state`. Boxes that already have the home directory keep it. Shared shop state is opt-in via env or pointer, never implied by installing onto the share (PR #67). Clair's home→share symlink stays the logical identity.

## [0.4.10] - 2026-08-31

Hotfix for the v0.4.9 zip mailed to the list. Clair Nolt reported `invalid ELF header` loading `tree_sitter_python` (`email:27237`).

### Fixed

- Product packaging now rejects tree-sitter `_binding*.so` files that are not little-endian ELF64 x86-64. The mailed 0.4.9 zip shipped Darwin grammar wheels under the same `_binding.abi3.so` name, which made syntax highlighting fail on ChoreBoy.
- Opening a `.sql` file no longer raises when the vendored SQL grammar ABI does not match tree-sitter 0.23. That file falls back to plain text instead of breaking the highlighter.

## [0.4.9] - 2026-08-29

Shop-tested by Ervin Newswanger on 2026-08-31 (`email:27192`). Mailed to `librepy-users@timtech.io` on 2026-08-31 (`email:27237`). Clair Nolt reported syntax highlighting off the same day; fixed in 0.4.10.

### Added

- Packaged apps install to `$HOME/.local/share/FreeCAD/Macro/Apps/<app name>` by default. The installer creates a Desktop shortcut and does not ask for a folder. A different package already in that slot is refused by name. Check **Ask the installer for an install folder** in Package Project to pick a path (request #46, Ervin Newswanger).

### Fixed

- Package Project no longer crashes on relative imports with `resolve_name() takes 2 positional arguments but 3 were given` (request #44, Ervin Newswanger).
- Unused missing imports can warn instead of blocking export when **Allow export with missing imports** is checked. Native extensions and unsafe subprocess calls still block (request #45, Ervin Newswanger).

## [0.4.8] - 2026-08-17

Mailed to `librepy-users@timtech.io` on 2026-08-24 (`email:26851`).

### Fixed

- Red error indicators now clear when the underlying error is fixed, without requiring Save. Realtime lint was bound to a stale editor manager after project open (request #40, Reuben Shirk).
- Dot-attribute completion lists public members first, highlights the typed prefix, and shows inline help after the name (request #40).
- Outside file changes are detected again, including restored drafts with no recorded mtime. Auto-save and Run no longer overwrite a newer disk file without a prompt. Opening a project no longer leaves the reload prompt bound to an empty editor manager, and choosing Reload now updates the open buffer (request #42, Ervin Newswanger).
- Test Explorer discovers tests in projects that do not ship `run_tests.py`. The AppRun `-c` pytest payload now actually runs collect.

### Changed

- New markdown tabs open in Split so the source is editable and the preview stays visible. Preview-only was the default and felt read-only (request #41, Reuben Shirk).

### Added

- Drop a file onto the main window to open it in an editor tab (request #43, Ervin Newswanger).

## [0.4.7] - 2026-06-30

Mailed to `librepy-users@timtech.io` on 2026-06-30 (`email:24999`). No git tag.

### Fixed

- Completion suggestion list no longer crashes with `RecursionError` when keyboard navigation hits the first or last row (request #39, Clair Nolt). Reported on v0.4.5.

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
