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
| **Status** | TODO |
| **Requested by** | Marcus Zimmerman |
| **Request** | Build the IDE with a modular plugin system so technically-inclined users can create and share their own extensions, rather than merging niche features into the core product. |
| **Rationale** | Keeps the core product focused on what benefits the majority (≥ 50%) of users. Minority-interest features ship as optional plugins instead of cluttering the mainline. User cites Classic Accounting as an example where a plugin model from the start would have let businesses build custom flows without bloating the base product. |
| **Trade-offs noted by requester** | Requires exposing stable internal APIs/hooks for plugin authors; maintaining backward compatibility with those APIs is ongoing work. |
| **Notes** | Large architectural decision — would need a formal design pass (plugin lifecycle, hook points, sandboxing, distribution mechanism) before implementation. Worth revisiting once the core MVP feature set is solid. |

---

### 5. VS Code-style JSON configuration files

| Field | Value |
|-------|-------|
| **Status** | TODO |
| **Request** | Add JSON configuration files (similar to VS Code's `settings.json` / `keybindings.json`) to allow user-configurable keyboard shortcuts and other settings. Consider using the same file format as VS Code to enable importing/exporting settings between the two editors. |
| **Notes** | Partial progress: a `settings.json` file exists at `~/choreboy_code_studio_state/settings.json` with a custom nested schema covering editor, theme, keybindings, syntax colors, linter, and more. However, the format is **not** VS Code-compatible — keybindings use `action_id -> shortcut` objects rather than VS Code's `[{ "key", "command", "when" }]` array, and there is no separate `keybindings.json`. The remaining work is VS Code format compatibility for import/export. |

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
| **Status** | TODO |
| **Requested by** | Clair Nolt (Ozark Timbers LLC) |
| **Request** | Syntax highlighting colors "run out" around line 630 in dark mode when editing a large Python file (650+ lines). Switching to light mode appeared to fix the issue. |
| **Root cause** | Two contributing factors identified. **(1)** `MAX_SEMANTIC_SELECTIONS_PER_REFRESH = 1800` in `app/editors/code_editor_widget.py` (line 42) caps how many semantic token overlays (`ExtraSelection`) are applied. The semantic analyzer (`app/intelligence/semantic_tokens.py`) generates a span for every variable reference, function/method call, attribute access, import, parameter, etc. — large files easily exceed 1800 spans, causing tokens beyond the budget to lose semantic coloring. **(2)** `_rebuild_semantic_selections()` (lines 344-368) runs on file open, text change, and theme change but NOT on scroll. The viewport-based prioritization in `_prioritized_semantic_spans()` (lines 385-401) becomes stale when the user scrolls to a different region. |
| **Why dark mode only** | The issue exists in both themes but is only perceptible in dark mode. Dark mode semantic colors (bright `#79C0FF`, `#7EE787`) contrast starkly with the default text color (`#E9ECEF`) on the dark background (`#1B1F23`). In light mode, semantic colors (dark `#1C7ED6`, `#2F9E44`) are visually close to the default text (`#212529`) on white, masking the loss. Switching themes triggers `_rebuild_semantic_selections()` with the current viewport, re-prioritizing spans for the visible region. |
| **Affected code** | `app/editors/code_editor_widget.py` — `MAX_SEMANTIC_SELECTIONS_PER_REFRESH`, `_prioritized_semantic_spans()`, `_rebuild_semantic_selections()`. `app/intelligence/semantic_tokens.py` — `_SemanticTokenCollector` (span generation). |
| **Potential fixes** | (a) Re-prioritize semantic selections on scroll (debounced) so the visible viewport always has full semantic coloring. (b) Increase or dynamically scale the cap based on file size / span count. (c) Hybrid: maintain a viewport-window of semantic selections that updates lazily on scroll. |

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

## Cross-cutting

- UI changes must validate in both light and dark themes (see `.cursor/rules/ui_light_dark_mode.mdc`).
- Prefer settings persistence via `app/persistence/settings_store.py` where applicable.
