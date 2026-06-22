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
| 31 | Auto-save does not trim trailing whitespace | PASS | Re-validated with auto-save *effective* (had to enable at Project scope — project file pinned `auto_save:false`). With trim-on-save ON, auto-save fired (status -> saved), the fresh auto-indented line was not trimmed, and typed chars landed at the indented column (no jump to col 0). |

## Group B — Syntax coloring & diagnostics

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 24 | `.fcmacro` syntax coloring (no identifier flood) | PASS | `.fcmacro` attaches Python highlighting; generic identifiers render default text color (no cyan flood), keywords/strings/numbers/comments/defs/`self`/calls still colored. Verified on `smoke_macro.fcmacro`. |
| 27 | Undefined identifier PY301 squiggle | PASS | Full-width squiggle + Problems "PY301 undefined name 'nothing'" + gutter error marker. NOTE: only fires under the **Pyflakes** linter provider; the default built-in provider does no name resolution. Project `cbcs/settings.json` pinned `selected_linter: default`, so the provider had to be set at **Project** scope (incidentally confirms request #5 project-override layering). |
| 25 | Settings syntax token names not clipped | PASS | Syntax Colors token column shows full labels (e.g. "Lexical / Keyword Operator", "Lexical / Escape Sequence", "Lexical / String Prefix"); no truncation/elision. Light theme verified. |

## Group C — Completion

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 34 | Dot-attribute completion (editor + console) | PASS | Editor: `os.` popped member completions with detail. Console: `data.` listed the live dict's methods (keys/values/items/get/...) with provenance `jedi_interpreter · runtime · semantic` and a side-effect-risk pill, reflecting the actual runtime object. |

## Group D — Navigation

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 29 | Outline panel + Ctrl+R Go to Symbol | PASS (.py) / WARN (.fcmacro) | On `.py`: hierarchical outline (class>methods), click-to-navigate, cursor-follow highlight, and Ctrl+R "Go to Symbol in File" all work. GAP: `.fcmacro` files show "No outline available" — outline/symbol-nav gate on `{.py,.pyw,.pyi}` and exclude `.fcmacro` even though #24 gives it highlighting. |

## Group E — File open

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 28 | Open File starts in active file's directory | PASS | With `cbcs/project.json` as the active tab, File > Open File opened with "Look in:" = `…/RunArgsSmokeTest/cbcs` (active file's dir, tier 1), distinct from project root. |

## Group F — Run arguments

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 36 | Run With Arguments / Run Configurations / quoting / status-bar indicator | WARN | **Committed HEAD crashes on every run** (`TypeError: append_console_line() takes 2 positional arguments but 3 were given`; see Issues). After restarting the editor against the **working tree** (which has the uncommitted `bind_append_console_line()` fix), all #36 behavior works: ad-hoc `--foo bar baz` -> `sys.argv[1:]==['--foo','bar','baz']` and did NOT persist (run_configs stayed `[]`); `Dev` config (argv `--profile dev`, `DEBUG=1`) persisted to `cbcs/project.json` and ran with `sys.argv[1:]==['--profile','dev']` + `DEBUG=1`; quoting preview showed 3 tokens with embedded space preserved; unbalanced quote showed "No closing quotation" and blocked Run; status-bar active-config indicator + popup present. **Action required: commit the run-path fix (and finish the Stop-path wiring) before release.** |

## Group G — Themes

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 37 | High Contrast Light/Dark themes | PASS | View > Theme lists 5 entries; HC Dark = pure black, HC Light = pure white, focus rings visibly thicker; panels stayed HC (no fallback); Settings > Syntax Colors shows 4 scopes. `settings.json` persists `theme.mode` and all four `syntax_colors` scopes (`light`/`dark`/`high_contrast_light`/`high_contrast_dark`). (User did a quick visual check.) |
| 38 | Neutral dark-gray chrome palette | PASS | Settings > General > Appearance offers Standard vs Neutral gray dark; Neutral renders chrome neutral gray (~#303030) while blue accent survives; switching to Standard shows the blue tint; distinct. Persists as `theme.dark_chrome_palette: "neutral_gray"` in settings.json. |

## Group H — Packaging

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 35 | Installable packaging export + launcher | PASS | Run > Package Project (installable) exported to `/home/joshua/runargssmoketest_installer_v0.1.0`. Contains installer/ (bootstrap.py, install.py, launcher_bootstrap.py), payload/app_files/ (project files correctly rooted), package_manifest.json (sha256 per file, entry `app_files/main.py`, launcher_mode `absolute_install_root`, default_install_base `/home/default`), package_report.json (`success: true`, dependency audit clear, 2 non-blocking advisories: generic description + no custom icon), README.txt, INSTALL.txt, and install_*.desktop with `Path=` set to package root and Exec → AppRun + installer/bootstrap.py. Packaging Report UI surfaced the 2 advisories correctly. Drove the installer headlessly (InstallWorker._do_install against a temp target): checksum verify + payload copy + atomic stage→swap + launcher write all succeeded, and the installed main.py executed via the launcher Exec form with correct runtime cwd/argv/env. **Minor defect found:** install marker `cbcs_installed_package.json` records `install_dir` as the transient `*_installing` staging path instead of the final dir (marker is written into stage_dir before the rename in `_do_install`). Launcher Exec is correct (built from `self.install_dir`); upgrade detection unaffected (reads dir path, not marker field). Low impact. |

## Group I — By-design confirm

| # | Request | Result | Notes |
|---|---------|--------|-------|
| 26 | Run/Debug Active File gated to Python | | |

## Issues found

- **#30 — Flat-Python paste right-click context menu not wired.** `CodeEditorWidget._show_context_menu` (which augments the menu with "Paste and Re-indent (Flat Python)" / "Re-indent Selection (Flat Python)") is never invoked: there is no `contextMenuEvent` override and no `customContextMenuRequested` connection in `app/editors/code_editor_widget.py` or its mixin bases, so the default `QPlainTextEdit` context menu is shown. The Edit-menu action and `Ctrl+Alt+V` shortcut work, so the feature is reachable; only the documented context-menu surface (AT-EDIT-FLAT-PYTHON-PASTE steps 3-4) is missing. Existing unit tests only call `_augment_context_menu_with_flat_python_actions` directly and therefore do not catch the wiring gap.
- **#29 — `.fcmacro` files have no outline / Go to Symbol.** `app/shell/editor_tab_outline_workflow.py` (`refresh_for_active_tab`, line ~57), `app/intelligence/outline_service.py` (`build_file_outline`), and the symbol-navigation workflows all gate on `{.py,.pyw,.pyi}` and call `set_unsupported_language("fcmacro")` for `.fcmacro`. Request #24 added `.fcmacro` to the Python language spec (highlighting) and the python_tools/diagnostics plugins include it, so this is an inconsistency that hurts the FreeCAD-macro audience #24/#26 target. Suggest adding `.fcmacro` to the outline/symbol suffix set.
- **#36 / ALL RUN+DEBUG — hard crash on run start (HEAD).** `app/shell/run_session_controller.py` calls `append_console_line(text, "system")` (positional stream) at lines 96, 97, 112, 120, 128 (and `stop_session` line 128), but the wired callback `app/shell/run_event_workflow.py:281 append_console_line(self, text, *, stream="stdout")` makes `stream` keyword-only. HEAD `run_debug_presenter.py:48` passes that method directly, so every run raises `TypeError: append_console_line() takes 2 positional arguments but 3 were given`. Tests miss it because they inject permissive fakes for `append_console_line`. **Workspace caveat:** `run_debug_presenter.py` and `run_event_workflow.py` have a large uncommitted WIP refactor (adds `bind_append_console_line()` wrapper) that partially fixes the run path but not the Stop path — the tree is mid-edit, so run-path smoke results are not against a clean committed state.
