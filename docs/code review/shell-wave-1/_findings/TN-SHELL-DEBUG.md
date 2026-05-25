# TN-SHELL-DEBUG — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-DEBUG  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/debug_panel_widget.py` (753 LOC), `app/shell/debug_control_workflow.py` (343 LOC). Cross-read: `main_window_panels.py` (signal wiring), `main_window.py` (`_apply_debug_inspector_event`, breakpoint dicts), `style_sheet_sections_panels.py` (`shell_section_debug_panel`), `app/debug/debug_breakpoints.py`, `tests/unit/shell/test_debug_panel_widget.py`, `tests/unit/shell/test_main_window_debug_routing.py`.

---

## Executive verdict

**Not thermo-clean.** The debug UI split is directionally right — `DebugPanelWidget` is a signal-driven view with solid unit coverage, and `DebugControlWorkflow` owns transport commands and breakpoint assembly — but R2 extraction stopped halfway. Breakpoint **state still lives on `MainWindow`** (`_breakpoints_by_file`, `_breakpoint_specs_by_key`) while the workflow mutates it through `window: Any`, and the panel toggle path does not reconcile gutter presence with `enabled` on the spec. `debug_panel_widget.py` sits at **753 LOC** with five near-copy tree builders; R3 split is justified now that public-behavior tests exist. Four-theme styling is mostly token-driven via `shell_section_debug_panel`, but `threadsTree` is omitted from the QSS block (falls back to platform defaults). Would not approve further debug features until breakpoint SSOT moves fully into `DebugControlWorkflow` (or a `BreakpointStore`) and panel/workflow duplication is collapsed.

---

### TN-SHELL-DEBUG-1 — Breakpoint state is split; panel disable does not sync editor gutter

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:437-438` — `_breakpoints_by_file: dict[str, set[int]]` (gutter presence) and `_breakpoint_specs_by_key` (full `DebugBreakpoint` including `enabled`) are separate stores. `app/shell/debug_control_workflow.py:242-257` — `handle_debug_breakpoint_toggle` updates only `_breakpoint_specs_by_key` with `enabled=enabled`; it never touches `_breakpoints_by_file` or `editor_widget.set_breakpoints(...)`. Contrast `handle_editor_breakpoint_toggled` (`78-91`), which updates both dict and gutter set. Editor gutter is a line-number set only (`code_editor_chrome_mixin.py:86-88`).
- **Code-judo alternative:** One `BreakpointStore` (owned by `DebugControlWorkflow`) with a single model: presence + enabled + condition/hit. Gutter reads `store.lines_for_file(path)`; panel reads `store.all_for_display()`. Toggle updates one record and pushes gutter + panel + transport in one transaction.
- **Suggested remediation:** R2 — move both dicts into `DebugControlWorkflow` or `app/shell/breakpoint_store.py`; `handle_debug_breakpoint_toggle` mirrors `handle_editor_breakpoint_toggled` semantics (or maps disable → keep line in gutter with distinct visual — but pick one model and enforce it everywhere). Remove breakpoint dict injection from `LocalHistoryWorkflow` / `ProjectTreeActionCoordinator` in favor of store methods (`remap_paths`, `clear_for_file`, `restore_snapshot`).
- **Tests that would prove fix:** Unit test: panel checkbox uncheck → gutter marker removed or visually distinct per chosen model; editor toggle ↔ panel checkbox stay in sync; `sync_breakpoints_to_active_debug_session` payload matches store.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-2 — `DebugControlWorkflow` is a ceremonial extraction (`window: Any`)

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/debug_control_workflow.py:25-26` — `def __init__(self, window: Any)`. Every handler rebinds `window = self._window` and reaches into `window._run_service`, `window._debug_session`, `window._breakpoints_by_file`, `window._editor_widgets_by_path`, `window._loaded_project`, etc. (40+ private field touches in 343 LOC). Wired from `main_window.py:551` with `DebugControlWorkflow(self)`.
- **Code-judo alternative:** Typed host bundle (`DebugShellHost` protocol): `run_service`, `debug_session`, `debug_panel`, `editor_for_path`, `loaded_project_root`, `append_debug_output`, `refresh_run_actions`. Breakpoint store owned by workflow, not injected from outside.
- **Suggested remediation:** R2 candidate #2 per `docs/deslop/AUDIT_app_remaining_handoff.md` — complete extraction: state in, `window: Any` out. Connect menus/panel signals directly to workflow public methods (already partially done in `menu_wiring.py` / `main_window_panels.py`); delete MainWindow pass-throughs as store absorbs breakpoint dicts.
- **Tests that would prove fix:** `tests/unit/shell/test_debug_control_workflow.py` constructing workflow from stub host (no `MainWindow` import); port navigation tests from `test_main_window_debug_routing.py`.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-3 — `handle_debug_refresh_stack` and `handle_debug_refresh_locals` are byte-identical

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/debug_control_workflow.py:165-183` — both methods: guard `supervisor.is_running()`, read `selected_frame`, bail if `None`, call `select_frame_command(selected_frame.frame_id)`, `send_debug_command`. Panel exposes two signals (`refresh_stack_requested`, `refresh_locals_requested`) wired separately in `main_window_panels.py:276-277`.
- **Code-judo alternative:** Single `handle_debug_refresh_frame_context()` (or `handle_debug_resync_inspector()`) connected to both panel signals and both status-header buttons. If locals truly need a distinct transport command later, add it when the protocol exists — not two public methods today.
- **Suggested remediation:** Collapse to one workflow method; update panel/status wiring. Drop duplicate menu/tooltip copy if behavior is identical.
- **Tests that would prove fix:** One unit test asserting one `select_frame` command per refresh action; remove redundant test doubles if any.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-4 — Manual `DebugBreakpoint` reconstruction instead of frozen-dataclass helpers

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_breakpoints.py:53-70` already provides `update_breakpoint_verification`. Yet `debug_control_workflow.py:126-137`, `245-254`, and `283-292` each hand-assemble full `DebugBreakpoint(...)` with seven fields copied from `spec`. `display_breakpoints` merges verified state with another 11-line constructor block.
- **Code-judo alternative:** Add `replace_breakpoint_fields(breakpoint, **changes)` or use `dataclasses.replace` at call sites; merge verified overlay via `update_breakpoint_verification` + `replace(..., enabled=..., condition=...)`.
- **Suggested remediation:** Extend `app/debug/debug_breakpoints.py` with small copy helpers; workflow methods become one-liners. Reduces field-add churn when `DebugBreakpoint` grows.
- **Tests that would prove fix:** Unit tests on new helpers; existing `test_debug_panel_widget.py` breakpoint label tests stay green.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-5 — Clear-all breakpoints emits N remove signals (sequential orchestration)

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/debug_panel_widget.py:672-674` — `_handle_clear_all_breakpoints` loops `self._breakpoints` and emits `breakpoint_remove_requested` per entry. Workflow handles each via `handle_debug_breakpoint_remove` (`228-240`), which mutates dicts, syncs one editor, calls `refresh_breakpoints_list`, and `sync_breakpoints_to_active_debug_session` **per removal**.
- **Code-judo alternative:** Panel emits one `breakpoints_clear_all_requested` signal (or workflow exposes `handle_remove_all_breakpoints_action` already used from menu — panel “Clear All” should call the same path). Single store clear → one editor sweep → one transport sync.
- **Suggested remediation:** Wire panel “Clear All” to `DebugControlWorkflow.handle_remove_all_breakpoints_action` (or shared store method) instead of N panel remove signals. Menu and panel share one code path.
- **Tests that would prove fix:** Assert one `update_breakpoints_command` after clear-all during paused session; `test_clear_all_breakpoints_emits_remove_for_each_breakpoint` rewritten to assert single workflow call or single transport command.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-6 — `debug_panel_widget.py` at 753 LOC; five copy-paste tree builders

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/debug_panel_widget.py:267-328` — `_build_threads_tree`, `_build_stack_tree`, `_build_variables_tree`, `_build_breakpoints_tree` repeat header labels, selection mode, alternating rows, mono font, header resize. File total 753 LOC (handoff smell threshold 700+; R3 lists this module explicitly).
- **Code-judo alternative:** Extract `debug_panel_trees.py` with `_make_debug_tree(**profile)` factory (columns, decoration, handlers) and keep `DebugPanelWidget` as layout + signal surface (~250 LOC). `_SectionHeader` / `_StatusHeader` can move to `debug_panel_chrome.py`.
- **Suggested remediation:** R3 split per handoff § R3 item 4 — **after** tightening tests to public signals/API (`watch_expressions`, `update_from_state`, signal emissions) rather than `_threads_tree` private probes where feasible.
- **Tests that would prove fix:** Existing `test_debug_panel_widget.py` passes unchanged object names and behavior; optional refactor reduces private attribute assertions.
- **Handoff overlap:** R3

---

### TN-SHELL-DEBUG-7 — Debug pause orchestration split across workflow and `MainWindow`

- **Persona:** TN-SHELL-DEBUG
- **Severity:** STRUCTURAL
- **Evidence:** Panel navigation goes to workflow (`handle_debug_navigate_preview/permanent`, `is_debug_navigation_target_allowed`). Auto pause-at-frame behavior lives on `MainWindow._apply_debug_inspector_event` (`main_window.py:3919-3939`): updates panel, opens file, sets/clears debug execution line on editor. Command input enablement split between `run_debug_presenter.py:80-83` and `main_window.py:4110-4111`, `4387-4388`.
- **Code-judo alternative:** `DebugInspectorPresenter` (or extend `DebugControlWorkflow`) owns pause side effects: panel refresh, allowed-path gate, execution-line indicator, command-input enabled — fed explicit editor/editor-map ports.
- **Suggested remediation:** R2 — move `_apply_debug_inspector_event` body into workflow/presenter; MainWindow subscribes to debug session events with one callback. Aligns with MW-08 run/debug presenter extraction theme.
- **Tests that would prove fix:** Port `test_main_window_debug_routing.py` pause/indicator cases to presenter/workflow tests; integration test: paused session highlights current frame line in editor.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-8 — Command eval reuses watch-evaluate path without distinction

- **Persona:** TN-SHELL-DEBUG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/debug_control_workflow.py:218-226` — `handle_debug_command_submit` strips text and delegates to `handle_debug_watch_evaluate`. Panel separates “Evaluate in selected frame…” command input from watch expressions (`debug_panel_widget.py:396-407` vs `342-346`), but transport is identical `evaluate_command`.
- **Code-judo alternative:** If intentional, rename workflow method to `handle_debug_evaluate_expression` and connect both signals to it — delete misleading `handle_debug_command_submit` / `handle_debug_watch_evaluate` pair. If command input should support REPL-like statements vs watch subset, split at command service boundary explicitly.
- **Suggested remediation:** Document single evaluate path in workflow docstring; collapse to one public method + two signal connections.
- **Tests that would prove fix:** One parametrized test: watch signal and command signal both produce same transport for same expression in debug mode.
- **Handoff overlap:** R2

---

### TN-SHELL-DEBUG-9 — `threadsTree` missing from debug panel QSS section

- **Persona:** TN-SHELL-DEBUG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/debug_panel_widget.py:269` — `shell.debug.threadsTree` object name set. `app/shell/style_sheet_sections_panels.py:270-273` — QSS targets `stackTree`, `variablesTree`, `watchTree`, `breakpointsTree` only; no `threadsTree` rules (hover/selected/alternate row styling).
- **Code-judo alternative:** Add `QTreeWidget#shell\\.debug\\.threadsTree` to the same rule blocks as other debug trees, or fold threads into a shared `#shell\\.debug\\.dataTree` class.
- **Suggested remediation:** Extend `shell_section_debug_panel`; validate **all four theme modes** (Light, Dark, HC Light, HC Dark) for thread row hover/selection contrast.
- **Tests that would prove fix:** Manual four-theme checklist; optional stylesheet substring test mirroring other panel sections.
- **Handoff overlap:** R3

---

### TN-SHELL-DEBUG-10 — Unit tests overfit private widget graph

- **Persona:** TN-SHELL-DEBUG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/shell/test_debug_panel_widget.py:100-101`, `106-107`, etc. — assertions on `panel._watch_input`, `panel._threads_tree`, `panel._stack_tree`, `panel._bp_tree`. Handoff R3: “Do not overfit tests to private child widget names.”
- **Code-judo alternative:** Test through public API: signals, `watch_expressions()`, `findChildren(QTreeWidget)` counts, header count labels via accessible names, or small test hooks like `debug_panel_widget.top_level_item_text(tree_id, row, col)` if needed.
- **Suggested remediation:** During R3 module split, rewrite tests to survive tree builder extraction without coupling to `_bp_tree` field names.
- **Tests that would prove fix:** Refactored tests pass after `_build_*` moves to submodule without importing private attrs.
- **Handoff overlap:** R3

---

## Positive signals (not findings)

- `DebugPanelWidget` exposes a clean signal surface (11 signals) wired in one block in `main_window_panels.py:268-278` — good AD-015 boundary for the view.
- Auto watch evaluate dedup (`_last_auto_eval_key`, `debug_panel_widget.py:430-435`) avoids transport spam on repeated paused state updates; covered by `test_auto_evaluate_watches_only_once_for_same_stop`.
- `_syncing_breakpoint_tree` guard (`579-605`) prevents feedback loops on checkbox refresh — correct Qt pattern.
- `is_debug_navigation_target_allowed` (`debug_control_workflow.py:195-205`) enforces project-root containment for debug navigation; unit tested in `test_main_window_debug_routing.py`.
- Debug panel QSS uses `ShellThemeTokens` throughout `shell_section_debug_panel` including `focus_border_width` on watch/command inputs — HC-aware focus rings.

---

## Approval bar (this slice)

**Would not approve** new debug panel sections or breakpoint features until TN-SHELL-DEBUG-1 (breakpoint SSOT) and TN-SHELL-DEBUG-2 (workflow ownership) are addressed. R3 file split (TN-SHELL-DEBUG-6) should follow immediately after R2 store move so the 753 LOC widget does not grow past 1k. Any UI touch must record four-theme validation (gap today: TN-SHELL-DEBUG-9 threads styling unverified).
