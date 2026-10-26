# Changelog

All notable user-facing changes to ChoreBoy Code Studio are documented here.

Release tags: `v0.1`, `v0.2`, `v0.4.5`, `v0.4.9`, `v0.4.10`, `v0.4.11`, `v0.4.12`, `v0.4.13`, `v0.4.14`.

LibrePy list mail-outs: v0.4.5 on 2026-06-27, v0.4.7 on 2026-06-30, v0.4.8 on 2026-08-24, v0.4.9 on 2026-08-31, v0.4.13 on 2026-10-21, v0.4.14 on 2026-10-26.

## [0.4.14] - 2026-10-26

Shop settings sharing is now set up from inside Code Studio (Clair Nolt). No pointer file, link or text editing.

### Added

- Settings > General > Shop sharing. Turn on "Share my settings with the other ChoreBoys in this shop" on the server first. It creates `share/Code Studio Settings` with this computer's settings, recent projects and Python Console history. History, logs, caches and SQLite stay on each computer.
- The other ChoreBoys find that folder by themselves and ask once, in a bar across the top of the window: Use shop settings, or Keep this computer's. Using the shop settings keeps a backup of this computer's settings in `before_shop`. The choice can be changed later in Settings.
- A status bar chip shows `Settings: shop · <server>`, or `Settings: shop offline · copy from <time>` when the server is off. Clicking it opens Settings at Shop sharing.

### Fixed

- A client ChoreBoy no longer falls back to its own settings with a startup dialog because the server's pointer file held the server's path. Each computer stores its own path to the shop folder.
- Saving settings on one computer no longer undoes changes made on another. Save writes only the settings you changed, and merges them into the current shared file.
- A client launch no longer empties the shared recent projects list. A project on the shop share opens from every computer. A project on one computer's own disk shows greyed out as "on <computer>" elsewhere and is never removed by another computer.
- When the server is off or the share disappears mid-session, Code Studio keeps working on its last synced copy, says so in the status bar, and sends the changes when the share comes back. It no longer saves silently to the local file.

### Changed

- A v0.4.13 pointer file (`share/Chore_Boy/CBCS/cbcs_state_root`) or a `~/choreboy_code_studio_state` link is read once and turned into the new setting. A relative path in the pointer file now works. Reading these old setups will be removed in v0.4.16.
- `CBCS_STATE_ROOT` still works for advanced use. Its startup message now says to check that the folder exists on this computer.

## [0.4.13] - 2026-10-21

Fixes what the LibrePy group reported since v0.4.12, and runs on FreeCAD 1.1 as well as FreeCAD 1.0 from one build. Builds tagged 0.4.13 (21 Sep) and 0.4.14 (24 Sep) were never sent to the list. Their tags are deleted and their changes are in this release, reworked where noted below.

### Fixed

- Code Studio no longer closes silently at launch with "database is locked" (Kevin Hoover, Joel Lamar Nolt). Startup now checks that the state folder accepts a file lock and a SQLite write, not only a plain file write. If local history or the symbol index can't open, the editor still opens with that feature off and a dialog that names the folder and the error. If the window can't be built at all, a "CBCS could not start" dialog shows the error and the log path.
- On FreeCAD 0.21 the editor opens with plugins off and one dialog that says plugins need FreeCAD 1.0 (Arlyn Martin). Run shows the same explanation instead of a traceback.
- Moving, renaming or cutting and pasting an open file in the Explorer no longer loses later edits (Reuben Shirk). The tab follows the file and Save writes to the new path.
- Choosing No when a file changed on disk keeps the tab marked as changed on disk, and Save asks again before it overwrites the other version (Ervin Newswanger). A file deleted or renamed outside Code Studio gets a missing marker with Keep Editing, Close and Save As.
- Package Project no longer rejects apps that start `/opt/freecad/AppRun` (Clair Nolt). The check now uses programs measured on FreeCAD 1.0 on 20 Oct 2026. AppRun and `/bin/sh` are allowed. `pdftoppm`, `python3`, `bash`, `xdg-open`, `okular`, `env` and `pcmanfm` are blocked, because ChoreBoy denies them. An untested program is a warning. FreeCAD 1.1 denies `/bin/sh`, so it is a warning when you package on FreeCAD 1.0 and blocked when you package on FreeCAD 1.1.
- A missing import stops the export only when the entry file reaches it and it is not inside `try`/`except ImportError`. Other missing imports are warnings. The "skip missing dependency" checkbox is gone.
- Programs your app starts no longer die when Code Studio closes (Clair Nolt). Closing with a run active asks whether to stop the program or keep it running. The Run Log dims FreeCAD's `LD_LIBRARY_PATH` echo and the `connect failed` line, with a tooltip that says they are harmless.
- Every packaged-app install failure shows the full error text with Copy Details. A shortcut problem no longer reports a failed install after the files are in place (Joel Lamar Nolt).
- Zips built on a Mac get the Linux tree-sitter grammars, so syntax highlighting works on ChoreBoy.
- Bold syntax colors render bold on Qt 6.

### Changed

- Completion has one setting in Settings > General > Intelligence: Off, Manual or While typing. Manual is the default and never opens a popup by itself, including after `.`. Ctrl+Space opens it. The list has every member, with no 100 or 500 cap. It matches by prefix, by capitals (`sT` finds `setText`) and loosely, puts names you picked before first, and closes when nothing matches. It never opens inside numbers like `1.5`, strings or comments. The docs pane shows the signature and the first paragraph of the docstring. The editor and the Python Console share the setting. It replaces Enable completion, Auto-trigger and Auto-trigger on period (Reuben Shirk, Clair Nolt).
- Editor tabs can be dragged to reorder, and the order survives a restart. Ctrl+\ splits the editor into two groups, and tabs can be dragged between them. A file open in both groups is one buffer (Reuben Shirk, Clair Nolt).
- Packaged apps install to `/home/default/FreeCAD/Apps/<package id>`, a folder the ChoreBoy file manager can open, so their icons show (Ervin Newswanger). An app without its own icon gets the Python icon. The launcher goes in `/home/default`, and in `~/Desktop` when that folder exists. Installing an app that is already there offers Replace, which keeps the app's data, or Uninstall. A file the app changed after install, such as its own database, counts as data, so Replace and Uninstall keep it. Replace moves apps out of the old `~/.local/share/FreeCAD/Macro/Apps` folder.
- Code Studio keeps its state in `/home/default/FreeCAD/CBCS/state`. Sharing settings between machines is opt-in through `CBCS_STATE_ROOT` or the pointer file `/home/default/share/Chore_Boy/CBCS/cbcs_state_root`, or the same path under `~/share/<server>/` on a client. Only `settings.json`, `recent_projects.json` and `python_console_history.json` go to the shared folder. History, logs and caches stay on each machine. If the shared folder can't be reached, Code Studio uses this computer's settings and says so (Clair Nolt, Jason Rissler, Kevin Hoover). On first launch, settings from an old state folder are copied once. History is not copied.
- Code Studio runs on the FreeCAD 1.1 image (Python 3.11, PySide6, no PySide2) as well as today's image (Python 3.9, PySide2). It uses the Qt binding FreeCAD provides. `CBCS_QT_API=pyside2` or `pyside6` forces one. The startup check reports the binding and the Qt version and checks `QtUiTools`, so it now counts nine checks.
- On FreeCAD 1.1, highlighting and the outline use the tree-sitter that ships in the image, because that image can't load native libraries from the Code Studio folder.
- New Qt projects, the example projects and the installer import Qt through FreeCAD's `PySide` package (`from PySide.QtWidgets import ...`, with `QAction`, `QActionGroup` and `QShortcut` from `PySide.QtGui`), so the same code runs on both images. Completion knows `PySide` and `PySide6` as well as `PySide2`.
- Launchers and the installer start on FreeCAD 1.1, which aborts with "File name too long" when an `AppRun -c` command has more than 255 characters without a `/`. Launchers made by older versions still have that problem on FreeCAD 1.1. Reinstall Code Studio, and re-package and reinstall apps, to replace them.

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
