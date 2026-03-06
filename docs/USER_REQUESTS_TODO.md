# User-Requested Updates (TODO)

Backlog of feature requests from users. Tracked separately from the main `docs/TASKS.md` backlog.

---

## Status legend

- `DONE` — implemented and validated
- `IN PROGRESS` — currently being worked on
- `TODO` — not started

---

## Requests

### 1. Main window starts maximized

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Request** | Main window should maximize on startup (e.g. `window.showMaximized()` instead of `window.show()`). |
| **Location** | `run_editor.py` line 23 |
| **Notes** | Implemented: `window.showMaximized()` in `_start_editor()`. |

---

### 2. Syntax highlighting color customization

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Request** | Allow users to pick/customize the colors used by the syntax highlighter. |
| **Notes** | Implemented: 23 configurable tokens with independent light/dark overrides. "Syntax Colors" tab in Settings dialog (`app/shell/settings_dialog.py`) with per-token color picker, hex validation, and reset. Token definitions in `app/shell/syntax_color_preferences.py`; theme application via `app/shell/theme_tokens.py` and `app/editors/syntax_registry.py`. Persisted in `settings.json` under `syntax_colors.light` / `syntax_colors.dark`. |

---

### 3. Keyboard shortcut customization

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Request** | Allow users to customize keyboard shortcuts. |
| **Key examples (LibrePy-like)** | |
| | Ctrl+D — duplicate line |
| | Ctrl+B — delete line |
| | Ctrl+/ — toggle comment |
| | Tab — indent (user could learn to use instead of Ctrl+I) |
| **Notes** | Implemented: "Keybindings" tab in Settings dialog (`app/shell/settings_dialog.py`) with search, per-shortcut editing, conflict detection, and "Reset All". Shortcut model and defaults in `app/shell/shortcut_preferences.py`; runtime application via `_load_shortcut_overrides()` and `_apply_shortcut_overrides_runtime()` in `app/shell/main_window.py`. Persisted in `settings.json` under `keybindings.overrides`. |

---

### 4. Plugin / modular extension architecture

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Requested by** | Marcus Zimmerman |
| **Request** | Build the IDE with a modular plugin system so technically-inclined users can create and share their own extensions, rather than merging niche features into the core product. |
| **Rationale** | Keeps the core product focused on what benefits the majority (≥ 50%) of users. Minority-interest features ship as optional plugins instead of cluttering the mainline. User cites Classic Accounting as an example where a plugin model from the start would have let businesses build custom flows without bloating the base product. |
| **Trade-offs noted by requester** | Requires exposing stable internal APIs/hooks for plugin authors; maintaining backward compatibility with those APIs is ongoing work. |
| **Notes** | Implemented plugin platform with runtime code plugins in isolated host process, offline installer/uninstaller/registry, declarative command/menu/event-hook contributions, Plugin Manager UI (install/enable/disable/export), safe mode toggle, runtime trust prompt, and failure quarantine auto-disable. Per-project plugin pinning remains intentionally deferred to phase 2. |

---

### 5. Global + per-project JSON settings

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Add a two-layer settings model: a **global** `settings.json` (user-wide defaults) and a **per-project** `settings.json` (project-specific overrides that travel with the project folder). The Settings dialog should clearly show which scope the user is editing. The per-project file enables sharing editor conventions between users by copying or versioning the project folder. |
| **File locations** | Global: `~/choreboy_code_studio_state/settings.json` (already exists). Project: `<project>/cbcs/settings.json` (new). Both use the same JSON schema. |
| **Layering** | `hardcoded defaults → global settings.json → project cbcs/settings.json → effective settings`. Merge is per-key within each section (not whole-section replacement), so a project file with `{"editor": {"tab_width": 2}}` overrides only `tab_width` while all other editor keys inherit from global. |
| **Project-overridable settings** | `editor.*` (tab_width, indent_style, indent_size, font_size, font_family, format_on_save, detect_indentation_from_file, trim_trailing_whitespace_on_save, insert_final_newline_on_save), `intelligence.*` (completion, diagnostics, highlighting thresholds), `linter.*` (rule_overrides), `file_excludes.*` (patterns), `output.*` (auto_open_console_on_run_output, auto_open_problems_on_run_failure). |
| **Global-only settings** | `theme.*` (mode), `syntax_colors.*`, `keybindings.*`, `ui_layout.*`, `last_project_path`, `python_import_update_policy` — these are personal/machine-specific and not shareable per-project. |
| **Settings dialog UX** | Scope selector (Global / Project) at the top. Global scope edits the global file (current behavior). Project scope shows only project-overridable settings; inherited values shown as placeholder/dimmed; each override gets a "Reset to Global" action. Banner explaining: "Project settings override global settings for this project. Other users who open this project will inherit these settings." Project scope disabled when no project is open. |
| **Project tree visibility** | The `cbcs/` directory should be visible in the project tree so users can browse and hand-edit `cbcs/settings.json`, `cbcs/project.json`, etc. directly. Currently `cbcs/` is excluded from the tree — that exclusion will be removed. |
| **Status bar** | When project settings are active, the status bar shows an indicator to make it clear the effective settings differ from global defaults. |
| **Affected code** | `app/core/constants.py` (new constant + overridable key set), `app/bootstrap/paths.py` (new path helper), `app/persistence/settings_store.py` (load/save/merge for project settings), `app/shell/settings_models.py` (scope-aware merge helpers), `app/shell/settings_dialog.py` (scope selector, inheritance indicators, reset-to-global), `app/shell/main_window.py` (load project settings on open, recompute effective settings), `app/project/project_service.py` (stop excluding `cbcs/` from tree). |
| **Notes** | Partial progress: global `settings.json` already exists with the full schema. `file_excludes` already has a merge pattern (`compute_effective_excludes()` in `app/project/file_excludes.py`) that combines global + project patterns — this validates the layering approach. The remaining work is the per-project file, the merge layer, and the Settings dialog scope UI. |

---

### 6. FreeCAD-style column-0 comment toggle

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Change comment toggle (`Ctrl+/` or equivalent) to use FreeCAD macro editor-style column-0 commenting: toggling ON places `#` at column 0 regardless of indentation (e.g. `    code()` becomes `#    code()`); toggling OFF only removes `#` from column 0, leaving indented comments untouched (e.g. `    # note` is preserved). Any line even partially selected is included in the toggle. |
| **Rationale** | Lets users distinguish "commented-out code" (column-0 `#`) from "reminder/note comments" (indented `#`). Selecting a mixed block and toggling will only affect the commented-out code lines, leaving notes intact. |
| **Affected code** | `app/editors/text_editing.py` `toggle_comment_lines()` currently adds `#` at the indentation level and uncomments all `#`-prefixed lines indiscriminately. Called from `app/editors/code_editor_widget.py` `toggle_comment_selection()`. |
| **Notes** | Cross-references request #3 (keyboard shortcut customization) — the toggle comment shortcut is one of the listed shortcuts there. |

---

### 7. Console drag-and-drop support

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Requested by** | Ervin N. Newswanger |
| **Request** | Enable drag-and-drop onto the Python console widget. Currently dragging a file into the console only pastes the file path as text rather than executing or inserting the file contents. |
| **Affected code** | `app/shell/python_console_widget.py` — `PythonConsoleWidget` (subclass of `QTextEdit`) has no `dragEnterEvent` / `dropEvent` overrides and does not call `setAcceptDrops(True)`. |
| **Notes** | Need to decide on drop behavior: insert file contents, execute file, or offer a choice. The project tree (`app/project/project_tree_widget.py`) already has drag-and-drop for file moves and can serve as a reference for MIME handling patterns. |

---

### 8. Run unsaved code via tempfile

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Requested by** | Ervin N. Newswanger |
| **Request** | Allow running unsaved code from an editor tab without requiring a saved file or project setup. Use Python's `tempfile` module to write the editor buffer to a temporary file and execute it through the runner. Handy for testing code snippets quickly without creating a full project. |
| **Affected code** | The run flow currently requires a saved file path end-to-end: `run_session_controller.py` blocks on save failures, `RunManifest` only accepts `entry_file` as a path string, `execution_context.py` checks that the entry path exists on disk, and `runner_main.py` uses `runpy.run_path()`. Linting already reads unsaved buffer content via `buffer_source` in `main_window.py` — a similar pattern could feed the runner through a temp file. |

---

### 9. Relocatable installation (relative paths)

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Requested by** | (anonymous), Reuben Shirk (relayed by Kevin Hoover) |
| **Request** | All internal paths should be relative so the application can be moved out of the home directory into any user-chosen location. Only the `.desktop` launcher file should need updating when the install folder changes. |
| **Rationale** | Users with busy home directories want to keep the app in a dedicated programming folder without path breakage. Currently some paths are anchored to `~/`, forcing a home-directory install. |
| **Affected code** | `app/core/constants.py` defines `GLOBAL_STATE_DIRNAME` and path helpers; `run_editor.py` and `dev_launch_editor.py` resolve the app root; `.desktop` file references an absolute install path. Any code that expands `~` or assumes a home-directory base needs auditing. |
| **Notes** | Related to the existing hidden-folder constraint (`.cursor/rules/no_hidden_folders.mdc`). A full audit of path resolution across the codebase would be the first step. |

---

### 10. Semantic highlighting colors stop rendering in large files (dark mode)

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Requested by** | Clair Nolt (Ozark Timbers LLC) |
| **Request** | Syntax highlighting colors "run out" around line 630 in dark mode when editing a large Python file (650+ lines). Switching to light mode appeared to fix the issue. |
| **Resolution** | Resolved by the tree-sitter hard cutover. Highlighting is now applied directly through `QSyntaxHighlighter.setFormat()` from tree-sitter query captures, not semantic `ExtraSelection` overlays. |
| **Why this fixes it** | The old failure mode was an overlay-cap issue (`MAX_SEMANTIC_SELECTIONS_PER_REFRESH`) combined with stale viewport prioritization. The new pipeline has no semantic overlay cap and updates visible-window captures through the tree-sitter highlighter policy. |
| **Implemented in** | `app/treesitter/highlighter.py`, `app/editors/code_editor_widget.py`, `app/editors/syntax_registry.py`, `run_editor.py` |

---

### 11. "Run" option in file tree right-click context menu

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Add a "Run" option to the existing right-click context menu on the project file tree. When a file is right-clicked, the context menu (which already has New File, Rename, Delete, Duplicate, Copy, Cut, Paste, Copy Path, etc.) should also include a "Run" action that executes the selected file through the runner. |
| **Affected code** | `app/shell/main_window.py` — `_show_single_item_context_menu()` (line 3374) builds the existing `QMenu`. Add a "Run" action to this menu (for non-directory files, ideally `.py` only). When chosen, call `self._start_session(mode=constants.RUN_MODE_PYTHON_SCRIPT, entry_file=absolute_path)` which already accepts an `entry_file` parameter (line 1991). |
| **Notes** | The context menu and run infrastructure both already exist. The wiring is straightforward: add the menu action, gate it to files (not directories), and invoke the existing `_start_session` with the file path. Could optionally restrict to `.py` files only and disable/hide the action when a run is already in progress. |

---

### 12. Run/Debug active file and explicit project entry point management

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Three related changes: **(A)** Run (F5) and Debug (Ctrl+F5) should execute the file currently open and focused in the editor, not the project's `default_entry`. Currently `default_entry` is inferred at project-open time (often the alphabetically first `.py` file), so editing `probe6` and clicking Debug runs `probe1`. **(B)** Add separate "Run Project" (Shift+F5) and "Debug Project" (Ctrl+Shift+F5) actions that always run from the project entry point. **(C)** Let users explicitly set the project entry point via a "Set as Entry Point" right-click option in the file tree. The entry point file should be visually distinguished with bold text and a play-icon badge. |
| **Affected code** | `app/shell/main_window.py` — `_handle_run_action`, `_handle_debug_action`, `_build_tree_item`, `_show_single_item_context_menu`. `app/shell/menus.py` — new Run Project / Debug Project menu actions. `app/shell/toolbar.py` — new toolbar buttons. `app/shell/toolbar_icons.py` — new icons. `app/shell/actions.py` — new enabled-state fields. `app/shell/icon_provider.py` — entry-point file icon. `app/run/run_service.py` — entry resolution (no changes needed, already supports `entry_file` override). |
| **Notes** | Packaging (`app/packaging/packager.py`) already uses `metadata.default_entry` for the `.desktop` Exec line, so the explicit entry point set by the user carries through to packaging automatically. |

---

### 13. Auto-indent on Enter (FreeCAD-style)

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Requested by** | Clair Nolt (Ozark Timbers LLC) |
| **Request** | When pressing Enter to create a new line, the cursor should land at the correct indentation level instead of column 0. FreeCAD's macro editor does this — the new line inherits the indentation of the previous line, and ideally increases indent after block-opening statements (`if …:`, `def …:`, `for …:`, `class …:`, etc.). |
| **Affected code** | `app/editors/code_editor_widget.py` — `keyPressEvent()` (lines 531–565) currently does not intercept Enter/Return (except when the completion popup is open); Enter falls through to `QPlainTextEdit`'s default plain-newline behavior. A new auto-indent handler would go here. `app/editors/text_editing.py` — may need a new helper to compute the correct indentation for the new line. Existing helpers (`indent_lines`, `outdent_lines`, `smart_backspace_columns`) cover related indent operations but nothing for newline auto-indent. |

---

### 14. Gracefully handle deleted entry file

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | When the configured entry file (e.g. `default_entry` in `cbcs/project.json`) is deleted or missing from disk, the editor should detect this gracefully and prompt the user to select a new entry file rather than failing silently or crashing. |
| **Affected code** | `app/shell/main_window.py` (entry file resolution and run invocation), `app/run/run_service.py` / `app/run/execution_context.py` (entry path existence check), `app/project/project_service.py` (project metadata loading). |
| **Notes** | Related to request #12 (explicit entry point management). The detection could happen at run time (when the user clicks Run/Debug) and/or proactively via filesystem watching. A dialog or inline prompt should let the user pick a replacement `.py` file from the project tree. |

---

### 15. "New Window" action in File menu

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Add a "New Window" action to the File menu (like VS Code's `Ctrl+Shift+N`) that launches a fresh, independent editor instance so the user can quickly open a separate project in a new window. |
| **Affected code** | `app/shell/menus.py` — add a `shell.action.file.newWindow` action to the File menu (between "New Project from Template" and "Open Project", or after "Open Recent" — matching VS Code's placement). Add an `on_new_window` callback to `MenuCallbacks`. `app/shell/main_window.py` — implement the callback that spawns a new editor process. The mechanism should mirror `dev_launch_editor.py`'s `build_apprun_command()` + `subprocess.Popen(..., start_new_session=True)` pattern, launching a detached AppRun child running `run_editor.py`. `app/shell/shortcut_preferences.py` — register a default shortcut (e.g. `Ctrl+Shift+N`). |
| **Notes** | No shared state between windows — each is a fully independent process, consistent with the filesystem-first, separate-process architecture. |

---

### 16. Preview tabs (VS Code-style single-click preview mode)

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Implement VS Code-style "preview mode" for editor tabs. **Single-clicking** a file in the project tree opens it in a **preview tab** whose title renders in *italics*. Only one preview tab exists at a time — single-clicking a different file replaces the preview tab's content instead of opening a new tab. **Double-clicking** a file in the tree opens it as a **permanent tab** (non-italic title, must be explicitly closed). A preview tab **promotes to permanent** when the user: (a) double-clicks the tab header, (b) edits the file (any content-modifying keystroke), or (c) uses an explicit "keep open" shortcut (VS Code uses `Ctrl+K Enter`). An optional setting (`editor.enable_preview`) should allow disabling preview mode entirely, in which case all opens behave as permanent. |
| **Affected code** | `app/shell/main_window.py` — `itemClicked` and `itemActivated` signals (lines 3104–3105) both connect to `_handle_project_tree_item_activation` with no single/double-click distinction; this handler needs to differentiate click type and route to preview-open vs permanent-open. `_open_file_in_editor` (line 3666) creates all tabs identically and needs a `preview` parameter to control tab style and replacement logic. `_MiddleClickTabBar` (line 174) needs a `mouseDoubleClickEvent` override to promote preview tabs on double-click. `app/editors/editor_manager.py` — `EditorManager` tracks tabs in `_tabs_by_path`; needs preview-tab tracking (at most one preview tab, replacement on next preview-open). `app/editors/editor_tab.py` — `EditorTabState` needs an `is_preview` flag and a `promote()` method. Other open-file entry points (Quick Open dialog, Search sidebar, Problems panel, Debug panel, Run log panel) each need a decision on whether they open as preview or permanent (VS Code opens Quick Open results as preview by default, but navigation from errors/search opens permanent). |
| **Notes** | Italic rendering: `QTabBar` does not natively support per-tab font styles — likely requires a custom `paintEvent` or `tabButton` overlay that applies `QFont.setItalic(True)` for preview tabs. The italic indicator must coexist with the existing dirty-tab `" *"` suffix. The `editor.enable_preview` setting should integrate with the existing settings model (`app/persistence/settings_store.py`, `app/shell/settings_models.py`). |

---

### 17. Automatic file tree refresh on filesystem changes

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | The project file tree should update automatically when files or directories are added, removed, or renamed outside the editor (e.g. from a terminal, file manager, or the runner creating output files). Currently the tree only refreshes when the user manually clicks the "Refresh Explorer" button or after an internal operation (rename, delete, new file, etc.). External changes should be detected and reflected without user intervention. |
| **Affected code** | `app/shell/main_window.py` — `_reload_current_project()` (line 3656) already re-enumerates and rebuilds the tree; the watcher would call this (debounced) when changes are detected. The "Refresh Explorer" button (line 3085) and its `clicked` signal (line 3088) remain as a manual fallback. The existing 1-second `QTimer` poll (`_external_change_poll_timer`, line 464) only checks open editor tabs for content staleness via `stale_open_paths()` — it does not monitor the project directory for structural changes. `app/project/project_service.py` — `enumerate_project_entries()` (line 236) walks the project folder; no watcher is set up after enumeration. `app/project/project_tree_widget.py` — display-only; no change needed unless tree-diff (incremental update) is preferred over full rebuild. |
| **Implementation options** | **(A) `QFileSystemWatcher`** — Qt's built-in watcher; add the project root and all subdirectories. Pros: no extra dependency, integrates with Qt event loop. Cons: does not recursively watch by default (must manually add subdirs), has a per-directory file-descriptor cost, and `QFileSystemWatcher` on Linux can silently stop watching after certain inode changes. **(B) Debounced periodic poll** — extend the existing `QTimer` poll to also compare the project entry list (or a hash of directory mtimes) against the last-known state and trigger `_reload_current_project()` on diff. Pros: simple, no platform edge cases. Cons: up to one polling interval of latency. **(C) Hybrid** — use `QFileSystemWatcher` for immediate notification with a periodic poll as a safety net. |
| **Notes** | Whichever approach is chosen, the refresh must be debounced (e.g. 300–500 ms) to avoid thrashing when many files change in quick succession (bulk copy, git checkout, runner output). The refresh should preserve the tree's expansion state and current selection. If the currently-open file is deleted externally, the existing external-change poll already handles tab staleness — but the tree refresh should also remove the deleted entry visually. |

---

### 18. JRXML editor support (syntax highlighting and validation)

| Field | Value |
|-------|-------|
| **Status** | DONE |
| **Request** | Add syntax highlighting and validation for `.jrxml` (JasperReports XML) files opened in ChoreBoy Code Studio. JRXML files are XML-based report definitions used by the `jasper_bridge` library (see `docs/JASPER_BRIDGE_PLAN.md`). Syntax highlighting should treat them as XML with awareness of JasperReports-specific elements and attributes. Validation could check well-formedness and flag common JRXML authoring mistakes. |
| **Resolution** | `.jrxml` is now registered in the tree-sitter language registry under the XML path. Files open with tree-sitter syntax highlighting through the shared highlighter pipeline. |
| **Implemented in** | `app/treesitter/language_registry.py` (`.jrxml` extension mapping), `app/treesitter/queries/xml.scm`, `app/editors/syntax_registry.py` |
| **Notes** | Syntax support is complete in-editor. JRXML domain validation rules remain a separate optional enhancement. |

---

### 19. Bottom tab auto-switching on Run is disruptive

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | When the user clicks Run, the active bottom-panel tab is force-switched to Run Log (on start and on every output chunk) and potentially to Problems (on failure). If the user is watching content on another tab (e.g. Python Console or Debug), this is disruptive — the tab they were monitoring gets yanked away. The per-chunk tab stealing is the most aggressive behavior: switching on every output event means the tab keeps jumping back even if the user manually navigates away mid-run. |
| **Existing settings** | `auto_open_console_on_run_output` (default True) switches to Run Log at run start and on each output event. `auto_open_problems_on_run_failure` (default True) switches to Problems on non-zero exit with parsed problems. These provide an off-switch but are all-or-nothing. |
| **Affected code** | `app/shell/main_window.py` — `_start_session()` (line ~2037) switches to Run Log on run start; `_handle_pytest_run_result()` (line ~1960) switches on pytest completion. `app/shell/run_output_coordinator.py` — `apply()` switches to Run Log on every `output` event (line ~75) and to Problems on `exit` failure (line ~110). |
| **Notes** | A possible refinement: only auto-switch once at run start, not on every output chunk. A third setting value like "only on first output" would let users keep the initial convenience without repeated tab stealing. Alternatively, make the existing settings more discoverable in the UI. |

---

### 20. Python console command history persistence across sessions

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | The Python Console's command history is purely in-memory and lost when the app closes. History should persist across sessions so users can recall previous commands after restarting. Additionally, provide an easy way to browse, search, and re-run previous commands beyond sequential Up/Down arrow recall. |
| **Current state** | History stored in `app/shell/python_console_widget.py` line 60 as `list[str]` (max 200 entries), navigated via Up/Down arrows (lines 228–234, 335–349). No persistence — not saved in `session_persistence.py`, `layout_persistence.py`, or `settings_store.py`. No history search or popup — only sequential Up/Down recall. |
| **Affected code** | `app/shell/python_console_widget.py` — needs save/load methods for the history list. `app/shell/session_persistence.py` or `app/persistence/settings_store.py` — needs a storage location for console history (e.g. a JSON file in the global state directory). `app/shell/main_window.py` — needs to call save on shutdown and load on startup. |
| **Notes** | Two sub-features: (A) persist history to disk and reload on next launch, (B) add an easy way to browse/search/run previous commands (e.g. Ctrl+R incremental search, or a history popup/dropdown). |

---

### 21. Refresh Explorer resets folder expansion state

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Clicking the "Refresh Explorer" button (or any action that triggers a project tree reload) expands all top-level folders, discarding the user's current collapse/expand state. The user has to manually re-collapse folders every time. |
| **Root cause** | `_populate_project_tree()` in `app/shell/main_window.py` (line 3309) calls `self._project_tree_widget.clear()` then rebuilds every node from scratch. Line 3320 unconditionally calls `root_item.setExpanded(True)` on all top-level directory items. No expansion state is captured before the clear or restored afterward. |
| **Affected code** | `app/shell/main_window.py` — `_populate_project_tree()` (lines 3309–3321), called by `_reload_current_project()` (line 3656), the Refresh Explorer button (line 3088), and `project_tree_action_coordinator.py` (all tree-mutating operations). |
| **Potential fix** | Before clearing the tree, walk all `QTreeWidgetItem` nodes and record which relative paths are expanded. After rebuilding, walk the new tree and restore expansion state from the saved set. Only expand top-level directories by default on the initial project open (not on refresh). |

---

## Cross-cutting

- UI changes must validate in both light and dark themes (see `.cursor/rules/ui_light_dark_mode.mdc`).
- Prefer settings persistence via `app/persistence/settings_store.py` where applicable.
