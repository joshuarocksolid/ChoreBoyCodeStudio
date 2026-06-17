# Smoke Test Results — Post-v0.2 User Requests (#24–#38)

**Branch / version:** main (app reports v0.3.1)
**Tester / environment:** Joshua — local DISPLAY, project `/home/joshua/Downloads/RunArgsSmokeTest`
**Date:** 2026-06-17
**Scope:** Requests implemented since the `v0.2` tag (2026-03-09). Shallow "does it work" pass. `#22`/`#23` are WON'T DO (skipped); `#26` is a by-design confirm.

## Result legend

PASS = behaves as specified · FAIL = broken · WARN = works with caveat · SKIP = not run

## Group A — Editor text behaviors

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 32 | Tab/Shift+Tab preserves multi-line selection | PASS | Repeated Tab kept the block selected and added indent levels; Shift+Tab outdented and kept selection. |
| 33 | Multi-line paste lands selected (single-line does not) | PASS | Multi-line paste landed highlighted; single-line paste landed unselected. |
| 30 | Flat-Python paste re-indent | WARN | Hint overlay + Re-indent, auto-mode ON silent path, **Always** (persisted `auto_reindent_flat_python_paste=true`), Edit menu, and Ctrl+Alt+V all work. **BUG:** right-click context-menu entries (Paste and Re-indent / Re-indent Selection) never appear — `_show_context_menu` in `app/editors/code_editor_widget.py` is defined but never wired to a `contextMenuEvent` override/signal, so Qt's default menu shows. Unit tests call `_augment_context_menu_with_flat_python_actions` directly and miss the gap. |
| 31 | Auto-save does not trim trailing whitespace | PASS | With Auto Save + trim-on-save ON, the auto-save timer left the fresh auto-indented line intact; caret held its indented column. |

## Group B — Syntax coloring & diagnostics

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 24 | `.fcmacro` syntax coloring (no identifier flood) | PASS | `.fcmacro` attaches Python highlighting; generic identifiers render default text color (no cyan flood), keywords/strings/numbers/comments/defs/`self`/calls still colored. Verified on `smoke_macro.fcmacro`. |
| 27 | Undefined identifier PY301 squiggle | PASS | Full-width squiggle + Problems "PY301 undefined name 'nothing'" + gutter error marker. NOTE: only fires under the **Pyflakes** linter provider; the default built-in provider does no name resolution. Project `cbcs/settings.json` pinned `selected_linter: default`, so the provider had to be set at **Project** scope (incidentally confirms request #5 project-override layering). |
| 25 | Settings syntax token names not clipped | | |

## Group C — Completion

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 34 | Dot-attribute completion (editor + console) | | |

## Group D — Navigation

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 29 | Outline panel + Ctrl+R Go to Symbol | | |

## Group E — File open

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 28 | Open File starts in active file's directory | | |

## Group F — Run arguments

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 36 | Run With Arguments / Run Configurations / quoting / status-bar indicator | | |

## Group G — Themes

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 37 | High Contrast Light/Dark themes | | |
| 38 | Neutral dark-gray chrome palette | | |

## Group H — Packaging

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 35 | Installable packaging export + launcher | | |

## Group I — By-design confirm

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 26 | Run/Debug Active File gated to Python | | |

## Issues found

- **#30 — Flat-Python paste right-click context menu not wired.** `CodeEditorWidget._show_context_menu` (which augments the menu with "Paste and Re-indent (Flat Python)" / "Re-indent Selection (Flat Python)") is never invoked: there is no `contextMenuEvent` override and no `customContextMenuRequested` connection in `app/editors/code_editor_widget.py` or its mixin bases, so the default `QPlainTextEdit` context menu is shown. The Edit-menu action and `Ctrl+Alt+V` shortcut work, so the feature is reachable; only the documented context-menu surface (AT-EDIT-FLAT-PYTHON-PASTE steps 3-4) is missing. Existing unit tests only call `_augment_context_menu_with_flat_python_actions` directly and therefore do not catch the wiring gap.
