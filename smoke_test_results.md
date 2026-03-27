# ChoreBoy Code Studio UI Smoke Test Results

Date: 2026-03-27  
Environment: FreeCAD AppRun runtime on DISPLAY=:1  
Build under test: ChoreBoy Code Studio v0.2

## Phase 1: Launch & environment verification
**Status**: PARTIAL
**AT coverage**: [AT-01, AT-02]

### Findings
- [PASS] Editor launched and remained responsive. Screenshot: `/workspace/smoke_artifacts/screenshots/phase01_initial_launch.webp`
- [FAIL] Status text mismatch.
  - **Steps to reproduce**: Launch editor and inspect status bar startup text.
  - **Expected**: `Runtime ready (6/6 checks)`
  - **Actual**: `Runtime ready (7/7 checks)`
  - **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase01_final_state.webp`
- [PASS] Runtime Center opened and showed healthy/no active runtime issues. Screenshot: `/workspace/smoke_artifacts/screenshots/phase01_runtime_center.webp`

## Phase 2: Project creation workflows (all template types)
**Status**: PARTIAL
**AT coverage**: [AT-19, AT-20, AT-21, AT-33]

### Findings
- [FAIL] Welcome-screen **New Project** path created `blank_project` metadata instead of allowing explicit `utility_script` selection.
  - **Steps to reproduce**: Welcome screen -> New Project -> create `SmokeUtilityScript` -> inspect `/workspace/SmokeUtilityScript/cbcs/project.json`.
  - **Expected**: template should be `utility_script`.
  - **Actual**: template persisted as `blank_project`.
  - **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase02_utility_project.webp`
- [PASS] `qt_app` project creation succeeded with expected tree + `main.py` opened. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_qt_app_project.webp`
- [PASS] `headless_tool` project creation succeeded with expected tree + `main.py` opened. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_headless_tool_project.webp`
- [PASS] Help -> Load Example Project created and opened `SmokeCrudExample` with expected browseable files. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_example_project.webp`

## Phase 3: Editor core — edit, save, tabs, dirty tracking
**Status**: PASS
**AT coverage**: [AT-06, AT-07, AT-08, AT-09, AT-44]

### Findings
- [PASS] File open in tabs and duplicate-tab suppression behaved correctly. Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_file_open_tab.webp`
- [PASS] Dirty marker appeared on edit and cleared on save. Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_dirty_indicator.webp`
- [PASS] Save All cleared dirty state across multiple files.
- [PASS] Dirty-tab close prompt appeared with Save/Discard/Cancel.
- [PASS] Preview-tab lifecycle matched AT-44 (single-click preview replaced by next preview; double-click pinned). Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_preview_behavior.webp`

## Phase 4: Run & output (MVP critical path)
**Status**: PARTIAL
**AT coverage**: [AT-10, AT-11, AT-12, AT-13, AT-14, AT-15, AT-16]

### Findings
- [PASS] Run launched in separate process while editor stayed responsive; Qt app window appeared. Screenshot: `/workspace/smoke_artifacts/screenshots/phase04_success_run_gui_launch.webp`
- [PASS] Run log showed live run state lines (start/run-id/runner metadata).
- [PASS] Failure run produced traceback with file/line mapping in `main.py`.
  - **Evidence**: `File "/workspace/SmokeCrudExample/main.py", line 19`
  - **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase04_traceback_runlog.png`
- [PASS] Per-run logs created in `/workspace/SmokeCrudExample/cbcs/logs/` and contained traceback details.
- [WARN] Stop behavior observed (`Run terminated by user (SIGTERM signal 15)`), but full dedicated `while True` scenario could not be fully re-executed due intermittent GUI-agent failures. Screenshot: `/workspace/smoke_artifacts/screenshots/phase04_stop_terminated_state.webp`
- [PASS] Editor remained usable after run failure/termination.

## Phase 5: Debug workflow
**Status**: PARTIAL
**AT coverage**: [AT-29, AT-30, AT-31, AT-59, AT-60]

### Findings
- [PASS] Debug launch contract is wired: debug manifests were generated with `mode: python_debug`, breakpoint payloads, and transport metadata.
- [PASS] Breakpoints appeared in debug payload/UI list.
- [FAIL] Pause/stepping behavior not confirmed end-to-end.
  - **Steps to reproduce**: set breakpoint in executable line -> start Debug Project.
  - **Expected**: pause at breakpoint + step controls update current line.
  - **Actual**: no stable paused frame state observed; breakpoint remained pending/unresolved in observed runs.
  - **Screenshots**: `/workspace/smoke_artifacts/screenshots/phase05_pre_debug_state.png`, `/workspace/smoke_artifacts/screenshots/phase05_debug_unavailable_state.png`
- [FAIL] Variables/watch/threads/frames/scope population could not be validated due missing paused state.
- [FAIL] Conditional breakpoint behavior could not be conclusively validated for same reason.

## Phase 6: Intelligence & diagnostics
**Status**: PARTIAL
**AT coverage**: [AT-47, AT-48, AT-50]

### Findings
- [PASS] Python highlighting visible and readable. Screenshot: `/workspace/smoke_artifacts/screenshots/phase06_intelligence_baseline.png`
- [PASS] Completion popup appeared on trigger; suggestion metadata displayed. Screenshot: `/workspace/smoke_artifacts/screenshots/phase06_completion_attempt.png`
- [WARN] Captured completion appeared approximate/sparse; richer semantic trust not conclusively validated.
- [FAIL] Hover docs/signature, go-to-definition, references, and rename could not be fully exercised because GUI automation became unstable for precise interactions in this phase.
- [PASS] Diagnostics surfaces active (Problems panel + traceback line mapping already validated in Phase 4).

## Phase 7: Formatting & imports
**Status**: PARTIAL
**AT coverage**: [AT-52, AT-53, AT-54]

### Findings
- [FAIL] Formatting command did not produce observable Black-style transformation in tested file.
  - **Steps**: create intentionally badly formatted `app/format_test.py` -> trigger Tools format command -> save -> inspect file.
  - **Expected**: normalization to Black style.
  - **Actual**: formatting remained unchanged in repeated attempts.
- [PARTIAL] Organize Imports flow was triggered, but final import ordering/style changes were inconclusive from UI automation.
- [PASS] `pyproject.toml` with Black/isort sections was added for validation context (`/workspace/SmokeCrudExample/pyproject.toml`).
- [WARN] Due intermittent input/menu automation instability, this phase is marked partial with likely command-path regression but not fully isolated.
- [Evidence screenshot] `/workspace/smoke_artifacts/screenshots/phase07_format_imports_state.png`

## Phase 8: Find & replace, search
**Status**: PARTIAL
**AT coverage**: [AT-06 (navigation behavior support), no direct AT ID in request]

### Findings
- [PASS] In-file Find UI opened and highlighted matches. Screenshot: `/workspace/smoke_artifacts/screenshots/phase08_find_in_file.png`
- [PASS] Replace UI opened with replace controls visible. Screenshot: `/workspace/smoke_artifacts/screenshots/phase08_replace_ui.png`
- [WARN] Find-in-files attempts were partially contaminated by automation keystroke artifacts (query text included suffix tokens), leading to no-results states not clearly attributable to product behavior.
- [FAIL] Clean positive click-to-navigate verification for find-in-files result activation was not conclusively completed in this run.
- [Evidence screenshots] `/workspace/smoke_artifacts/screenshots/phase08_find_in_files.png`, `/workspace/smoke_artifacts/screenshots/phase08_find_in_files_qapplication.png`

## Phase 9: Project tree file operations
**Status**: FAIL
**AT coverage**: [AT-27, AT-28]

### Findings
- [FAIL] Could not reliably complete create/rename/delete/drag-drop validations due repeated GUI-agent execution failures during this phase.
- [WARN] Context-menu capture evidence is inconclusive (overlay/search state interfered with clean project-tree interaction capture).
- [Evidence screenshot] `/workspace/smoke_artifacts/screenshots/phase09_tree_context_menu.png`

## Phase 10: Settings & preferences
**Status**: PASS
**AT coverage**: [AT-34, AT-35, AT-36, AT-43]

### Findings
- [PASS] Settings dialog opened and displayed expected tabs/scope controls.
- [PASS] Global/Project scope selector visible.
- [PASS] Keybindings/Syntax Colors/Linter/Files tabs visible.
- [Evidence screenshot] `/workspace/smoke_artifacts/screenshots/phase10_settings_dialog.webp`

## Phase 11: Theme validation pass
**Status**: PASS
**AT coverage**: [Theme validation across AT-51/AT-57/AT-71 expectations]

### Findings
- [PASS] Dark theme: editor/tree/run log/debug/problems/search/status readable with adequate contrast. Screenshot: `/workspace/smoke_artifacts/screenshots/phase11_dark_theme.webp`
- [PASS] Light theme: same areas remained readable with no disappearing icons/borders. Screenshot: `/workspace/smoke_artifacts/screenshots/phase11_light_theme.webp`
- [PASS] No critical light/dark regressions observed in sampled surfaces.

## Phase 12: Local history & recovery
**Status**: PARTIAL
**AT coverage**: [AT-65, AT-66, AT-67, AT-68]

### Findings
- [PASS] Multiple edits+saves created local-history entries.
- [PASS] Local History dialog showed checkpoints with timestamps/labels. Screenshot: `/workspace/smoke_artifacts/screenshots/phase12_local_history_dialog.webp`
- [PASS] Restore to Buffer successfully reverted content to earlier revision. Screenshot: `/workspace/smoke_artifacts/screenshots/phase12_local_history_restore.webp`
- [WARN] Crash-recovery relaunch scenario (AT-68/AT-66 crash path) not safely testable without terminating full session context.

## Phase 13: Plugins, packaging, dependencies
**Status**: PARTIAL
**AT coverage**: [AT-37, AT-81, AT-90]

### Findings
- [PASS] Plugin Manager opened and showed installed plugin inventory/details. Screenshot: `/workspace/smoke_artifacts/screenshots/phase13_plugin_manager.webp`
- [PASS] Package Project wizard opened and initial steps were walkable without export. Screenshots: `/workspace/smoke_artifacts/screenshots/phase13_package_wizard_step1.webp`, `/workspace/smoke_artifacts/screenshots/phase13_package_wizard_step2.webp`
- [FAIL] Dependency Inspector was not discoverable from visible UI paths tested.
  - **Attempted paths**: Tools menu, Runtime Center, View menu, project-tree context menus, settings tabs.
  - **Expected**: accessible dependency inspector surface.
  - **Actual**: no discoverable entry point.

## Phase 14: Python console & test explorer
**Status**: PARTIAL
**AT coverage**: [AT-26, AT-96, AT-97]

### Findings
- [PASS] Python Console accepted/evaluated expressions (`2+3`, `print("ok")`) and displayed output (`ok`). Screenshot: `/workspace/smoke_artifacts/screenshots/phase14_python_console.webp`
- [FAIL] Test Explorer UI was not discoverable from tested menu/surface paths.
- [FAIL] Running a test from explorer could not be performed because explorer was inaccessible.

## Phase 15: Developer day-in-the-life workflow
**Status**: PARTIAL
**AT coverage**: [AT-06, AT-07, AT-08, AT-10, AT-12, AT-17, AT-29, AT-30, AT-31, AT-47, AT-50, AT-52]

### Findings
- [PASS] Created new `qt_app` project `TaskTracker` under `/workspace` and opened it. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_created.webp`
- [PASS] Implemented PySide2 app in `main.py` with `QMainWindow`, `QListWidget`, and Add Task button; run launched Qt window. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_running.webp`
- [PASS] Introduced bug and reproduced traceback with clear file/line mapping, then fixed and reran successfully. Screenshots: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_traceback.webp`, `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_fixed.webp`
- [PARTIAL] Debug step was attempted; debug manifest generated for TaskTracker but stable paused frame/variable inspect was not observed in UI (consistent with Phase 5 debug issue). Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_debug_attempt.png`
- [PARTIAL] Find-in-files for `QListWidget` attempted; navigation confirmation remained inconclusive due same search interaction instability. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_find_in_files_qlistwidget.png`
- [PARTIAL] Rename workflow surfaced UI (`Rename Symbol` prompt requiring cursor on symbol) but full rename-apply verification not completed. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_recent_projects_menu.png`
- [FAIL] Save/close/reopen-from-recent full validation loop could not be conclusively completed due repeated late-phase GUI-agent failures.

## Gap Analysis

### Severity definitions (use exactly these)
- **P0 — Blocker**: Core MVP workflow broken (can't open/edit/save/run).
  User cannot accomplish primary task.
- **P1 — Critical**: Feature exists but fails in common scenarios.
  Workaround may exist but is non-obvious.
- **P2 — Major**: Feature partially works but has significant UX issues,
  missing feedback, or edge-case failures.
- **P3 — Minor**: Cosmetic issues, minor inconsistencies, theme glitches,
  or polish gaps that don't block workflows.
- **P4 — Enhancement**: Missing feature that would improve the experience
  but isn't part of current scope.

### [P1] Debug sessions do not reliably pause at breakpoints
- **Phase**: 5
- **AT reference**: AT-30, AT-31, AT-59, AT-60
- **Steps to reproduce**: Set breakpoint on executable line in `main.py` -> start Debug Project.
- **Expected**: Execution pauses at breakpoint; step controls and frame/locals/watch data become active.
- **Actual**: Debug launch contract is emitted, but no stable paused-frame state observed; breakpoint remains pending/unresolved in UI.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase05_debug_unavailable_state.png`

### [P1] Welcome-screen project creation does not produce `utility_script` template
- **Phase**: 2
- **AT reference**: AT-19
- **Steps to reproduce**: Welcome screen -> New Project -> create project.
- **Expected**: Utility template selection path (or resulting `template: "utility_script"` metadata).
- **Actual**: Created project metadata persisted as `template: "blank_project"` with no template choice shown.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase02_utility_project.webp`

### [P1] Test Explorer is not discoverable from tested UI surfaces
- **Phase**: 14
- **AT reference**: AT-96, AT-97
- **Steps to reproduce**: Inspect View/Tools/bottom-panel/toolbar surfaces for Test Explorer entry.
- **Expected**: Discoverable explorer with test discovery + run actions.
- **Actual**: No discoverable Test Explorer entry point in tested paths; cannot execute test run from explorer.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase14_python_console.webp`

### [P2] Dependency Inspector entry point not discoverable
- **Phase**: 13
- **AT reference**: AT-90
- **Steps to reproduce**: Search Tools, Runtime Center, View, settings, and context menus.
- **Expected**: Discoverable Dependency Inspector surface.
- **Actual**: No discoverable entry point from tested UI surfaces.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase13_plugin_manager.webp`

### [P2] Format/Organize Imports behavior inconclusive and likely ineffective
- **Phase**: 7
- **AT reference**: AT-52, AT-53, AT-54
- **Steps to reproduce**: Create intentionally poorly formatted Python file -> invoke format/organize imports -> save and inspect file.
- **Expected**: Observable Black/isort transformations according to project config.
- **Actual**: Repeated attempts did not produce reliable, observable transformations in captured run.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase07_format_imports_state.png`

### [P2] Find-in-files interaction unstable in this run
- **Phase**: 8
- **AT reference**: no AT coverage
- **Steps to reproduce**: Ctrl+Shift+F search; attempt result navigation.
- **Expected**: Stable query input and click-through navigation to file/line.
- **Actual**: Query interaction suffered from unstable automation/input artifacts; positive navigation could not be conclusively validated.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase08_find_in_files_qapplication.png`

### [P3] Runtime readiness count differs from expected script text
- **Phase**: 1
- **AT reference**: AT-02
- **Steps to reproduce**: Launch app and inspect status bar startup checks count.
- **Expected**: `Runtime ready (6/6 checks)` (per requested test script).
- **Actual**: `Runtime ready (7/7 checks)`.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase01_final_state.webp`
