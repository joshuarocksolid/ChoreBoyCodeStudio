# ChoreBoy Code Studio UI Smoke Test Results

Date: 2026-03-27  
Environment: FreeCAD AppRun runtime on DISPLAY=:1  
Build under test: ChoreBoy Code Studio v0.2

## Phase 1: Launch & environment verification
**Status**: PARTIAL
**AT coverage**: [AT-01, AT-02]

### Findings
- [PASS] Editor launched and stayed responsive. Screenshot: `/workspace/smoke_artifacts/screenshots/phase01_initial_launch.webp`
- [FAIL] Status text mismatch.
  - **Steps to reproduce**: Launch editor and inspect startup status bar text.
  - **Expected**: `Runtime ready (6/6 checks)`
  - **Actual**: `Runtime ready (7/7 checks)`
  - **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase01_final_state.webp`
- [PASS] Runtime Center opened and reported healthy runtime/no active issues. Screenshot: `/workspace/smoke_artifacts/screenshots/phase01_runtime_center.webp`

## Phase 2: Project creation workflows (all template types)
**Status**: PARTIAL
**AT coverage**: [AT-19, AT-20, AT-21, AT-33]

### Findings
- [FAIL] Welcome-screen New Project path produced `blank_project` instead of explicit `utility_script`.
  - **Steps to reproduce**: Welcome screen -> New Project -> create `SmokeUtilityScript` -> inspect `cbcs/project.json`.
  - **Expected**: `template: "utility_script"` for AT-19 flow.
  - **Actual**: `template: "blank_project"`.
  - **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase02_utility_project.webp`
- [PASS] `qt_app` creation succeeded with expected tree and `main.py` open. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_qt_app_project.webp`
- [PASS] `headless_tool` creation succeeded with expected tree and `main.py` open. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_headless_tool_project.webp`
- [PASS] Help -> Load Example Project succeeded for `SmokeCrudExample`. Screenshot: `/workspace/smoke_artifacts/screenshots/phase02_example_project.webp`

## Phase 3: Editor core — edit, save, tabs, dirty tracking
**Status**: PASS
**AT coverage**: [AT-06, AT-07, AT-08, AT-09, AT-44]

### Findings
- [PASS] File opening and tab dedupe worked. Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_file_open_tab.webp`
- [PASS] Dirty marker appeared on edit and cleared on save. Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_dirty_indicator.webp`
- [PASS] Save All cleared dirty state on multiple files.
- [PASS] Dirty-tab close prompt showed Save/Discard/Cancel.
- [PASS] Preview tab semantics matched AT-44. Screenshot: `/workspace/smoke_artifacts/screenshots/phase03_preview_behavior.webp`

## Phase 4: Run & output (MVP critical path)
**Status**: PARTIAL
**AT coverage**: [AT-10, AT-11, AT-12, AT-13, AT-14, AT-15, AT-16]

### Findings
- [PASS] Run launched in separate process while editor stayed usable. Screenshot: `/workspace/smoke_artifacts/screenshots/phase04_success_run_gui_launch.webp`
- [PASS] Run Log showed live run metadata lines.
- [PASS] Failure run included traceback mapping to file/line in `main.py`. Screenshot: `/workspace/smoke_artifacts/screenshots/phase04_traceback_runlog.png`
- [PASS] Per-run logs were created under `cbcs/logs` and contained full traceback text.
- [WARN] Stop behavior was observed (`SIGTERM`) but fully isolated long-running-loop scenario could not be repeatedly re-executed due intermittent GUI-agent instability. Screenshot: `/workspace/smoke_artifacts/screenshots/phase04_stop_terminated_state.webp`
- [PASS] Editor stayed functional after run failures/stops.

## Phase 5: Debug workflow
**Status**: PARTIAL
**AT coverage**: [AT-29, AT-30, AT-31, AT-59, AT-60]

### Findings
- [PASS] Debug launch contract wiring exists (`python_debug` manifests with breakpoint and transport payloads).
- [PASS] Breakpoints appear in debug payloads/UI.
- [FAIL] Paused-breakpoint stepping flow was not confirmed.
  - **Steps to reproduce**: Set breakpoint -> start Debug Project.
  - **Expected**: Pause at breakpoint with step over/into/out and live frame/locals.
  - **Actual**: No stable paused-frame state observed; breakpoint remained pending/unresolved in observed sessions.
  - **Screenshots**: `/workspace/smoke_artifacts/screenshots/phase05_pre_debug_state.png`, `/workspace/smoke_artifacts/screenshots/phase05_debug_unavailable_state.png`
- [FAIL] Variables/watch/threads/frames/scopes remained unvalidated because paused state was not achieved.

## Phase 6: Intelligence & diagnostics
**Status**: PARTIAL
**AT coverage**: [AT-47, AT-48, AT-50]

### Findings
- [PASS] Python syntax highlighting visible and readable. Screenshot: `/workspace/smoke_artifacts/screenshots/phase06_intelligence_baseline.png`
- [PASS] Completion popup could be triggered and showed suggestion metadata. Screenshot: `/workspace/smoke_artifacts/screenshots/phase06_completion_attempt.png`
- [WARN] Completion quality in sample looked approximate/sparse; richer semantic trust not proven.
- [FAIL] Hover docs, go-to-definition, references, and rename were not fully validated due repeated precision-interaction instability in this phase.
- [PASS] Diagnostics surfaces remained active; traceback line mapping was validated in Phase 4.

## Phase 7: Formatting & imports
**Status**: PARTIAL
**AT coverage**: [AT-52, AT-53, AT-54]

### Findings
- [FAIL] Format command did not produce observable Black-style transformations in repeated attempts on intentionally malformed test file.
- [PARTIAL] Organize Imports command path was triggered, but result quality remained inconclusive in this run.
- [PASS] `pyproject.toml` with Black/isort sections was added in test project for config-respect checks.
- [WARN] Menu/input instability impacted repeatability of this phase. Screenshot: `/workspace/smoke_artifacts/screenshots/phase07_format_imports_state.png`

## Phase 8: Find & replace, search
**Status**: PARTIAL
**AT coverage**: [no direct AT coverage]

### Findings
- [PASS] In-file Find worked with highlighted matches. Screenshot: `/workspace/smoke_artifacts/screenshots/phase08_find_in_file.png`
- [PASS] Replace UI surfaced expected controls. Screenshot: `/workspace/smoke_artifacts/screenshots/phase08_replace_ui.png`
- [WARN] Find-in-files input/navigation remained unstable in this run; positive click-through navigation could not be conclusively demonstrated.
- [Evidence] `/workspace/smoke_artifacts/screenshots/phase08_find_in_files.png`, `/workspace/smoke_artifacts/screenshots/phase08_find_in_files_qapplication.png`

## Phase 9: Project tree file operations
**Status**: PARTIAL
**AT coverage**: [AT-27, AT-28]

### Findings
- [PASS] Project-tree context actions are reachable; additional targeted retry produced an explicit tree-action modal (`New Folder`) from context flow, confirming at least part of file-operation UI path is functioning. Screenshot: `/workspace/smoke_artifacts/screenshots/phase_extra_new_file_prompt_attempt.png`
- [WARN] Full create/rename/delete/drag-drop sequence still could not be completed end-to-end in one stable pass due recurring UI-state interference (search/rename overlays and agent instability), so AT-27/AT-28 remain only partially verified.
- [WARN] Additional recovery attempts confirmed an unstable coupling between tree selection and active editor tab state during delete prompts (delete intent repeatedly targeted `project.json` despite explicit attempts to select generated file entries), preventing safe drag-drop/delete verification in-session without risking project metadata loss.
- [Evidence] `/workspace/smoke_artifacts/screenshots/phase09_tree_context_menu.png`, `/workspace/smoke_artifacts/screenshots/phase09_context_menu_retry.png`, `/workspace/smoke_artifacts/screenshots/phase_extra_new_file_prompt_attempt.png`, `/workspace/smoke_artifacts/screenshots/phase_extra_tree_selection_before_delete.png`, `/workspace/smoke_artifacts/screenshots/phase_extra_delete_prompt.png`

## Phase 10: Settings & preferences
**Status**: PASS
**AT coverage**: [AT-34, AT-35, AT-36, AT-43]

### Findings
- [PASS] Settings dialog opened successfully.
- [PASS] Global/Project scope controls visible.
- [PASS] Keybindings/Syntax Colors/Linter/Files tabs visible.
- [Evidence] `/workspace/smoke_artifacts/screenshots/phase10_settings_dialog.webp`

## Phase 11: Theme validation pass
**Status**: PASS
**AT coverage**: [AT-51, AT-57, AT-71 (readability expectations)]

### Findings
- [PASS] Dark theme remained readable across editor/tree/run log/debug/problems/search/status surfaces. Screenshot: `/workspace/smoke_artifacts/screenshots/phase11_dark_theme.webp`
- [PASS] Light theme remained readable for same surfaces. Screenshot: `/workspace/smoke_artifacts/screenshots/phase11_light_theme.webp`
- [PASS] No critical theme-contrast regressions observed in sampled surfaces.

## Phase 12: Local history & recovery
**Status**: PARTIAL
**AT coverage**: [AT-65, AT-66, AT-67, AT-68]

### Findings
- [PASS] Multiple edits+saves created local history entries.
- [PASS] Local History dialog displayed checkpoints with timestamp/label metadata. Screenshot: `/workspace/smoke_artifacts/screenshots/phase12_local_history_dialog.webp`
- [PASS] Restore to Buffer reverted file content to earlier snapshot. Screenshot: `/workspace/smoke_artifacts/screenshots/phase12_local_history_restore.webp`
- [WARN] Crash-recovery relaunch flow was not safely testable without terminating current long-running session context.

## Phase 13: Plugins, packaging, dependencies
**Status**: PARTIAL
**AT coverage**: [AT-37, AT-81, AT-90]

### Findings
- [PASS] Plugin Manager opened and displayed installed plugin inventory/details. Screenshot: `/workspace/smoke_artifacts/screenshots/phase13_plugin_manager.webp`
- [PASS] Package Project wizard opened and initial steps were walkable without export. Screenshots: `/workspace/smoke_artifacts/screenshots/phase13_package_wizard_step1.webp`, `/workspace/smoke_artifacts/screenshots/phase13_package_wizard_step2.webp`
- [FAIL] Dependency Inspector entry point was not discoverable.
  - **Attempted paths**: Tools menu, Runtime Center, View menu, context menus, settings tabs.
  - **Expected**: discoverable Dependency Inspector surface.
  - **Actual**: no visible entry point found in tested UI.

## Phase 14: Python console & test explorer
**Status**: PARTIAL
**AT coverage**: [AT-26, AT-96, AT-97]

### Findings
- [PASS] Python Console executed expressions and printed output (`ok`). Screenshot: `/workspace/smoke_artifacts/screenshots/phase14_python_console.webp`
- [FAIL] Test Explorer was not discoverable from tested UI paths.
- [FAIL] Test run from explorer could not be executed because explorer entry point was inaccessible.

## Phase 15: Developer day-in-the-life workflow
**Status**: PARTIAL
**AT coverage**: [AT-06, AT-07, AT-08, AT-10, AT-12, AT-17, AT-29, AT-30, AT-31, AT-47, AT-50, AT-52]

### Findings
- [PASS] New `qt_app` project `TaskTracker` created under `/workspace`. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_created.webp`
- [PASS] Implemented PySide2 `QMainWindow` + `QListWidget` + Add Task button app; run launched Qt window. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_running.webp`
- [PASS] Introduced bug, reproduced traceback, fixed via traceback location, and reran successfully. Screenshots: `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_traceback.webp`, `/workspace/smoke_artifacts/screenshots/phase15_tasktracker_fixed.webp`
- [PARTIAL] Debug attempt generated TaskTracker debug manifests but stable paused-variable inspection remained unconfirmed (same blocker as Phase 5). Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_debug_attempt.png`
- [PARTIAL] Find-in-files for `QListWidget` executed but clean result-navigation confirmation remained inconclusive. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_find_in_files_qlistwidget.png`
- [PARTIAL] Rename UI surfaced (`Rename Symbol` prompt), but full rename-apply validation remained incomplete. Screenshot: `/workspace/smoke_artifacts/screenshots/phase15_recent_projects_menu.png`
- [FAIL] Full close/reopen-from-recent state-restore loop was not conclusively completed due repeated late-phase GUI-agent failures.

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
- **AT reference**: AT-30
- **Steps to reproduce**: Set breakpoint on executable line -> start Debug Project.
- **Expected**: Execution pauses at breakpoint; step controls and frame/locals/watch data become active.
- **Actual**: Debug launch contract is emitted, but no stable paused-frame state observed; breakpoints remain pending in observed sessions.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase05_debug_unavailable_state.png`

### [P1] Welcome-screen project creation does not produce `utility_script` template
- **Phase**: 2
- **AT reference**: AT-19
- **Steps to reproduce**: Welcome screen -> New Project -> create project.
- **Expected**: Utility template selection path (or resulting `template: "utility_script"` metadata).
- **Actual**: Created project metadata persisted as `template: "blank_project"` without template choice UI.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase02_utility_project.webp`

### [P1] Test Explorer is not discoverable from tested UI surfaces
- **Phase**: 14
- **AT reference**: AT-96
- **Steps to reproduce**: Inspect View/Tools/bottom-panel/toolbar surfaces for Test Explorer entry.
- **Expected**: Discoverable Test Explorer with discovery/run controls.
- **Actual**: No discoverable Test Explorer entry point in tested surfaces.
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
- **AT reference**: AT-52
- **Steps to reproduce**: Create intentionally poorly formatted Python file -> invoke format/organize imports -> save and inspect file.
- **Expected**: Observable Black/isort transformations per project config.
- **Actual**: Repeated attempts did not produce reliable, observable transformations in captured run.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase07_format_imports_state.png`

### [P2] Find-in-files interaction unstable in this run
- **Phase**: 8
- **AT reference**: no AT coverage
- **Steps to reproduce**: Ctrl+Shift+F search; attempt result navigation.
- **Expected**: Stable query input and click-through navigation to file/line.
- **Actual**: Query interaction was unstable in this session; positive navigation not conclusively validated.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase08_find_in_files_qapplication.png`

### [P2] Project tree file-operations only partially verified
- **Phase**: 9
- **AT reference**: AT-27
- **Steps to reproduce**: Attempt context-menu create/rename/delete/drag-drop operations in project tree.
- **Expected**: Deterministic file operation flow with confirmations.
- **Actual**: Context-action entry is present (e.g., New Folder prompt reached), but full create/rename/delete/drag-drop coverage was not completed in one stable sequence.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase09_context_menu_retry.png`

### [P3] Runtime readiness count differs from expected script text
- **Phase**: 1
- **AT reference**: AT-02
- **Steps to reproduce**: Launch app and inspect status bar startup check count.
- **Expected**: `Runtime ready (6/6 checks)` (per requested script text).
- **Actual**: `Runtime ready (7/7 checks)`.
- **Screenshot**: `/workspace/smoke_artifacts/screenshots/phase01_final_state.webp`
