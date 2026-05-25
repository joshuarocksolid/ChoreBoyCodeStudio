# TN-SHELL-MW-16 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-16  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 5523–EOF — realtime lint delegators, module-level flat-Python helpers at file tail. Cross-read (lifecycle cluster): tab close/save guards (`5184–5286`), `closeEvent` / shutdown teardown (`4333–4409`), external file change + project-tree poll (`5416–5504`), realtime lint wiring (`513–517`, `621–645`, `4969`, `5518–5526`). Full read: `save_workflow.py`, `document_safety.py`, `unsaved_changes_dialog.py`, `diagnostics_search_coordinator.py`.

**Scope note:** Strict slice manifest ends at **28 lines** (`5518–5549`). Close/save guards and shutdown live **above** line 5523 but belong to the same lifecycle band; this critic treats them as in-scope because `SaveWorkflow` extraction left teardown, external-change prompts, and lint scheduling on `MainWindow`.

---

## Executive verdict

**Not thermo-clean.** `SaveWorkflow` is a solid R2 extraction for save, autosave-to-file, style-on-save, and the themed unsaved-changes contract — tab close and app exit correctly route through it. The tail slice and its lifecycle neighbors still expose **asymmetric document safety**: external disk reload uses a raw `QMessageBox.Yes | No` with no Save path while `DocumentScope.EXTERNAL_RELOAD` sits unused in `document_safety.py`. Tab close runs the save gate then leaves **~15 lines of editor teardown** on `MainWindow`; `_reset_editor_tabs` duplicates timer/editor resets. Realtime lint is two one-line delegators plus duplicated `_is_shutting_down` guards while `DiagnosticsOrchestrator` already owns scheduling logic. The file ends with **flat-Python helpers used from line ~1995**, making EOF a junk drawer on a **5,549-line** class. Dominant risk: the next lifecycle action (reload, project switch, tab close variant) will add another ad-hoc dialog or teardown branch instead of extending the document-safety model. Four-theme impact: unsaved-changes uses themed chrome (`unsaved_changes_dialog.py`); external reload and save-formatting warnings still use stock `QMessageBox` — any consolidation must re-validate Light, Dark, HC Light, and HC Dark.

---

### TN-SHELL-MW-16-1 — External file reload bypasses SaveWorkflow; dirty buffers cannot Save

- **Persona:** TN-SHELL-MW-16
- **Severity:** BLOCKER
- **Evidence:** `_check_for_external_file_change` (`main_window.py:5416-5481`) prompts with `QMessageBox.question(..., QMessageBox.Yes | QMessageBox.No)` — Reload vs keep editor buffer. Dirty case message: "Reloading will discard editor changes." (`5437-5441`). No Save / Save All option. `DocumentScope.EXTERNAL_RELOAD` is defined (`document_safety.py:26`) but **never referenced** in the repo. Tab close and app exit use `SaveWorkflow.request_unsaved_changes_decision` + themed `_UnsavedChangesDialog` (`5232-5240`, `4334-4339`, `unsaved_changes_dialog.py:181-238`).
- **Code-judo alternative:** `ExternalFileChangeWorkflow` (or extend `SaveWorkflow`) calls `request_unsaved_changes_decision("reloading from disk", scope=DocumentScope.EXTERNAL_RELOAD, dirty_buffers=(tab_state,) if dirty else ())` with dialog buttons Save / Reload / Cancel (and Discard when dirty). On SAVE, persist then reload; on PROCEED/reload, run existing local-history checkpoint path (`5454-5476`).
- **Suggested remediation:** Wire external reload through the same document-safety pipeline as tab close; implement EXTERNAL_RELOAD scope in `prompt_for_unsaved_changes` (button labels scoped to reload). Hard cutover — delete raw Yes/No branch.
- **Tests that would prove fix:** Unit test: dirty tab + external mtime change → themed dialog with Save option; Cancel leaves buffer; Save persists then reloads disk content. Characterization for clean-tab reload unchanged.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-16-2 — Tab close uses SaveWorkflow gate but teardown stays on MainWindow

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_tab_close_requested` (`5223-5254`): save decision via `SaveWorkflow` (`5232-5240`), then `MainWindow` owns `removeTab`, `pop_editor`, `close_file`, breakpoint/lint map pops, problems panel, debug refresh, action state refresh. `_close_active_tab` (`5256-5261`) and tab context menu close (`5220-5221`) delegate to the same handler. `_reset_editor_tabs` (`5263-5286`) repeats timer stops and editor-manager reset without save prompts (intentional for project switch, but duplicates teardown steps with `_begin_shutdown_teardown` at `4352-4358`).
- **Code-judo alternative:** `EditorTabLifecycleWorkflow(window_ports)` with `close_tab(index)`, `close_active_tab()`, `reset_all_tabs(*, prompt: bool)` — owns save gate delegation to `SaveWorkflow` and the post-decision teardown transaction. `MainWindow` deletes `_handle_tab_close_requested`, `_close_active_tab`, `_reset_editor_tabs`.
- **Suggested remediation:** Extract in same PR as any new close-path work; pass narrow ports (editor_manager, workspace_controller, breakpoints maps, refresh callbacks). Net **method count down** on `MainWindow`.
- **Tests that would prove fix:** Workflow unit tests with stub save workflow: Cancel → tab remains; Discard → tab removed, breakpoints cleared; Save failure → tab remains.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-16-3 — Flat-Python helpers stranded at EOF; handlers 3,500 lines away

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** Module-level `_enable_auto_reindent_flat_python_paste_in_payload` and `_flat_python_repair_status_message` live at `main_window.py:5528-5549`. Callers: paste/reindent handlers at `1995-2015`, settings update at `2015`, `editor_tab_factory.py:168` references `window._enable_auto_reindent_flat_python_paste_from_hint`. Status message is pure string formatting with no Qt dependency — belongs beside `FlatPythonIndentRepairResult` or `python_style_workflow.py`.
- **Code-judo alternative:** Move payload merger to `save_workflow.py`-style settings helper module or `python_style_workflow.py`; move status message to `app/editors/flat_python_indent.py` (or existing repair module). Delete EOF definitions; import at call sites.
- **Suggested remediation:** One-file move when touching PythonStyle band; no new symbols on `MainWindow`.
- **Tests that would prove fix:** Existing flat-Python unit tests import new module path; grep confirms `main_window.py` ends with class methods only (or ≤1 re-export).
- **Handoff overlap:** R2, R3 (`python_style_workflow.py`)

---

### TN-SHELL-MW-16-4 — Realtime lint: two delegators + triple shutdown guards

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `_schedule_realtime_lint` / `_run_scheduled_realtime_lint` (`5518-5526`) only check `_is_shutting_down` and forward to `DiagnosticsOrchestrator`. Timer wired at init (`515-517`) to `_run_scheduled_realtime_lint`; orchestrator constructed with six lambdas into `MainWindow` privates (`621-645`). Shutdown stops timer in `_begin_shutdown_teardown` (`4355-4358`) and `_reset_editor_tabs` (`5272-5274`); schedule path also guards (`5519-5520`, `5524-5525`).
- **Code-judo alternative:** At composition root, connect `_realtime_lint_timer.timeout` to a bound method on `DiagnosticsOrchestrator.run_scheduled_realtime_lint` wrapped once with `is_shutting_down` check; delete `_schedule_realtime_lint` / `_run_scheduled_realtime_lint`. Text-change hook calls `orchestrator.schedule_realtime_lint` directly (`4969` today → orchestrator).
- **Suggested remediation:** Hard cutover when touching diagnostics wiring; no new `MainWindow` lint methods.
- **Tests that would prove fix:** Unit test on orchestrator: schedule during shutdown no-op; timer fires only for active tab (existing behavior at `diagnostics_search_coordinator.py:62-64`).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-16-5 — SaveWorkflow is untyped host soup; save_tab fans out to shell subsystems

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `SaveWorkflow.__init__(self, window: Any)` (`save_workflow.py:38-39`) reaches into `window._editor_manager`, `_local_history_workflow`, `_workflow_broker`, `_intelligence_runtime_settings`, `_test_runner_workflow`, `_render_lint_diagnostics_for_file`, `_start_symbol_indexing`, etc. (`save_workflow.py:148-195`). Save success triggers lint render, test discovery refresh, symbol re-index, project reload on new file (`180-181`) — orchestration that belongs at workflow boundary or event bus, not embedded in save primitive.
- **Code-judo alternative:** `SaveWorkflowPorts` dataclass (editor save, tab presentation, local history, optional post-save hooks registry). Register `on_python_saved` / `on_any_saved` callbacks at init instead of inline getattr chains. Keeps `save_tab` focused on persist + checkpoint.
- **Suggested remediation:** Introduce ports when next extending save path; avoid widening `window: Any` surface.
- **Tests that would prove fix:** `SaveWorkflow` unit tests construct with stub ports only (no `MainWindow` import); post-save hooks invoked once per saved `.py` file.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-16-6 — External change poll only prompts for the active tab

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `_poll_external_file_changes` (`5486-5504`) calls `stale_open_paths()` then **only** runs `_check_for_external_file_change` when `active_tab.file_path in stale_paths` (`5489-5491`). Other open tabs with changed disk mtime stay stale until the user switches to them — silent divergence between buffer and disk for background tabs.
- **Code-judo alternative:** Queue stale paths and prompt per tab (or batch via document-safety multi-file dialog), or mark background tabs visually and defer prompt to tab activation with a "stale on disk" badge. Minimum fix: iterate all `stale_paths`, not just active.
- **Suggested remediation:** Pair with finding 1 when external reload joins SaveWorkflow; consider tab chrome indicator for stale-non-active files.
- **Tests that would prove fix:** Unit test: two open tabs, both stale, active tab is B → tab A still gets prompt or stale flag before switch.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-16-7 — Project tree signature poll triggers full reload without dirty-project guard

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `_poll_external_file_changes` (`5493-5504`) compares tree signatures; on change calls `_reload_current_project()` with no `SaveWorkflow` consult. `_reload_current_project` (`4809-4833`) repopulates tree, reindexes symbols, refreshes test discovery — does not close tabs, but couples filesystem churn to heavy shell refresh while dirty buffers may exist. Same reload entry used from save-new-file (`save_workflow.py:180-181`) and explorer refresh (`main_window_panels.py:133`).
- **Code-judo alternative:** Split **tree structure refresh** (cheap repopulate) from **project metadata reload**; gate full reload on `confirm_proceed_with_unsaved_changes` when dirty tabs exist and signature change implies destructive tree state. Align with `TN-SHELL-MW-11-1` preserve_state / reveal policy.
- **Suggested remediation:** Document whether auto-poll reload is safe with dirty tabs; if not, gate or downgrade to tree-only refresh.
- **Tests that would prove fix:** Characterization: dirty project + unrelated tree signature change → no silent heavy reload or user prompted first.
- **Handoff overlap:** R2, R3 (project tree presenter)

---

### TN-SHELL-MW-16-8 — Window shutdown teardown remains a 60-line MainWindow concern

- **Persona:** TN-SHELL-MW-16
- **Severity:** STRUCTURAL
- **Evidence:** `closeEvent` (`4333-4350`) sequences save decision, `_is_shutting_down`, `_begin_shutdown_teardown`, `_stop_active_run_before_close`, layout/history persistence. `_begin_shutdown_teardown` (`4352-4388`) stops **nine** timers via `hasattr` guards, cancels workers, shuts down background tasks and intelligence controller. Overlaps `TN-SHELL-MW-10-2` (search sidebar worker not torn down). Realtime lint timer stopped here but delegators remain (`4355-4358`).
- **Code-judo alternative:** `ShutdownWorkflow` owns ordered teardown phases (timers → workers → run/debug → persist). `closeEvent` becomes: save gate → `shutdown_workflow.run()`. Register child widgets (search sidebar, diagnostics) for cooperative cancel.
- **Suggested remediation:** Consolidate when fixing search-worker teardown; do not add more `hasattr` timer stops to `MainWindow`.
- **Tests that would prove fix:** Integration: close during run, during search, during lint timer pending → no post-close callbacks; all timers stopped.
- **Handoff overlap:** R2 (cross-ref TN-SHELL-MW-10)

---

### TN-SHELL-MW-16-9 — Redundant CANCEL branch in tab close handler

- **Persona:** TN-SHELL-MW-16
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_handle_tab_close_requested` returns early on `decision.intent is DocumentCloseIntent.CANCEL` (`5238-5239`) then calls `apply_unsaved_changes_decision`, which returns `False` for CANCEL anyway (`save_workflow.py:87-88`).
- **Code-judo alternative:** Single `if not self._save_workflow.apply_unsaved_changes_decision(decision): return` after request — same behavior, fewer branches.
- **Suggested remediation:** Fold into `EditorTabLifecycleWorkflow` extraction (finding 2).
- **Tests that would prove fix:** Existing tab-close tests stay green.
- **Handoff overlap:** none

---

### TN-SHELL-MW-16-10 — Auto-save-to-file swallows all exceptions

- **Persona:** TN-SHELL-MW-16
- **Severity:** NICE-TO-HAVE
- **Evidence:** `flush_auto_save_to_file` (`save_workflow.py:131-146`) wraps `save_tab` in bare `except Exception` with log only — permission errors, transform failures, and logic bugs are indistinguishable; user gets no surfaced feedback (by design for autosave, but hides systemic failures).
- **Code-judo alternative:** Catch `(OSError, ValueError)` like `save_tab`; let unexpected exceptions propagate or hit a metrics counter. Optional: status-bar hint after N consecutive failures.
- **Suggested remediation:** Tighten exception tuple when touching autosave; not a standalone PR.
- **Tests that would prove fix:** Unit test: OSError on autosave logged, timer continues; unexpected Exception not swallowed (or re-raised in dev).
- **Handoff overlap:** none

---

## Positive signals (not findings)

- `SaveWorkflow` centralizes save, save-all, autosave toggle, style-on-save transforms, and unsaved-changes decision/application — the right R2 shape (`save_workflow.py:35-290`).
- Tab close and app exit **do** use the themed unsaved dialog and `DocumentSafetyDecision` model (`5232-5240`, `4334-4339`).
- `document_safety.py` provides clean frozen snapshots and intent enum without importing editor classes.
- `unsaved_changes_dialog.py` resolves `ShellThemeTokens` from parent for four-theme-aware chrome (`55-65`, `200-212`).
- `DiagnosticsOrchestrator` owns realtime lint debounce semantics (active-tab check, pending path) (`diagnostics_search_coordinator.py:49-64`).
- External reload records local-history checkpoints before discarding dirty buffers (`5454-5475`) — recoverability intent is present even though Save is missing from the prompt.
- Menu save wiring goes directly to workflow methods, not `MainWindow` delegators (`menu_wiring.py:35-37`).

---

## Approval bar (this slice)

**Would not approve** changes that add lifecycle handlers, lint delegators, or EOF module helpers on `MainWindow` without (1) routing external reload through `SaveWorkflow` / `DocumentScope.EXTERNAL_RELOAD`, (2) extracting `EditorTabLifecycleWorkflow` with **net-reduced** method count, and (3) deleting realtime lint pass-through methods in favor of orchestrator-direct wiring. Any dialog consolidation must note four-theme validation status for external-reload and save-formatting surfaces (themed unsaved dialog vs stock `QMessageBox`).
