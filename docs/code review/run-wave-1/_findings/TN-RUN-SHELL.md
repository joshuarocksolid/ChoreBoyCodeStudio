# TN-RUN-SHELL — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUN-SHELL  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/shell/run_launch_workflow.py` (725 LOC), `run_session_controller.py` (222), `run_output_coordinator.py` (147), `repl_session_manager.py` (261), `debug_control_workflow.py` (337). Cross-read: `run_debug_presenter.py`, `breakpoint_store.py`, `shell_composition.py` (`MainWindowRunLaunchHost`), `docs/code review/shell-wave-1/_findings/TN-SHELL-MW-08.md`, `TN-SHELL-MW-09.md`, `TN-SHELL-DEBUG.md`, `tests/unit/shell/test_run_session_controller.py`, `test_run_output_coordinator.py`, `test_run_command_routing.py`.

---

## Executive verdict

**Not thermo-clean.** Shell Wave 1 R2 partially landed: `RunLaunchWorkflow` absorbed the MW-08 launch graph with typed `DebugTarget`, `BreakpointStore` replaced MainWindow breakpoint dicts, and `RunSessionController` / `RunOutputCoordinator` are clean callback-driven seams. Extraction stopped halfway — **`run_launch_workflow.py` is 725 LOC** (run launch + run-config dialogs + status-bar chrome + debug-target memory), **`DebugControlWorkflow` and `RunDebugPresenter` still use `window: Any`**, and **stop/restart lifecycle remains on `MainWindow`** with a documented restart race. Dominant risks: (1) **restart → silent `ALREADY_RUNNING`** when stop has not completed; (2) **breakpoint SSOT leaked** via mutable dict aliases into session/tree workflows; (3) **three incompatible “clear console” behaviors** on the run/output path. Positive: `RunOutputCoordinator` and `RunSessionController` are textbook orchestration; `ReplSessionManager` correctly isolates REPL from script lifecycle.

---

### TN-RUN-SHELL-1 — `RunLaunchWorkflow` is a 725 LOC god workflow at the 1k threshold

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/run_launch_workflow.py:176-726` — single class owns active-file launch, project/config launch, run-with-arguments dialogs, run-configuration persistence, status-bar `QToolButton` menu (`install_active_run_config_indicator`, `_populate_active_run_config_menu`), debug-target memory (`record_debug_target`, `handle_rerun_last_debug_target_action`), and transient dirty-buffer files (`_write_transient_entry_file`, `delete_transient_entry_file`). Manifest baseline flags this module as a high-risk hotspot (`docs/code review/run-wave-1/00-manifest.md:95`).
- **Code-judo alternative:** Split into `ActiveFileRunWorkflow`, `RunConfigurationWorkflow` (dialogs + status indicator), and `DebugTargetMemory` — or keep one facade that delegates to three ~200 LOC modules. Status-bar Qt wiring moves with run-config workflow; launch paths call a shared `start_debug_session(...)` helper (see TN-RUN-SHELL-6).
- **Suggested remediation:** Hard cutover — no parallel MainWindow handlers. Net LOC down on `run_launch_workflow.py` before adding features. Preserve `RunLaunchWorkflowHost` protocol and four-theme token plumbing through host ports.
- **Tests that would prove fix:** Existing `tests/unit/shell/test_run_command_routing.py` stays green against refactored public API; add workflow-level test for status-bar active-config selection without `MainWindow` import.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-2 — Typed host on launch path; `window: Any` on debug path (inconsistent seam)

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/run_launch_workflow.py:100-174` — `RunLaunchWorkflowHost` protocol with explicit ports. Contrast `app/shell/debug_control_workflow.py:26-27` — `def __init__(self, window: Any)` with 40+ private field touches (`window._run_service`, `window._debug_session`, `window._editor_widgets_by_path`, …). Same pattern in `app/shell/run_debug_presenter.py:19-20`. `shell_composition.py:270-346` — `MainWindowRunLaunchHost` is typed adapter, but returns `Any` for `editor_manager`, `debug_control_workflow`, `run_debug_presenter`, etc.
- **Code-judo alternative:** `DebugShellHost` / `RunDebugPresenterHost` protocols mirroring `PythonConsoleWorkflowHost` (`python_console_workflow.py:38-48`) and `ShellThemeWorkflowHost` — inject `run_service`, `debug_session`, `debug_panel`, `append_debug_output`, `refresh_run_actions`, `breakpoint_store` as ports. Breakpoint store owned by workflow, not reached through window.
- **Suggested remediation:** Complete R2 extraction per TN-SHELL-DEBUG-2; delete `window: Any` from presenter and debug workflow in one cutover. Wire menus/panel signals directly to typed workflow methods (already partially done in `menu_wiring.py`, `main_window_panels.py`).
- **Tests that would prove fix:** New `tests/unit/shell/test_debug_control_workflow.py` with stub host (no `MainWindow` import); port pause/navigation cases from `test_main_window_debug_routing.py`.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-3 — Asymmetric session lifecycle: start via presenter, stop/restart on MainWindow

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** Start path: `run_launch_workflow.py:212` → `run_debug_presenter.py:22-88` → `run_session_controller.py:47-118`. Stop: `main_window.py:2352-2355` — `_handle_stop_action` calls `_run_session_controller.stop_session` + `_set_run_status("stopping")` with no presenter. Restart: `main_window.py:2357-2363` — inline `stop_run()` then `_run_launch_workflow.handle_rerun_last_debug_target_action()` or `handle_run_action()`. Exit cleanup: `run_output_coordinator.py:110-111` clears `active_session_mode`; presenter never involved in stop/restart/exit symmetry.
- **Code-judo alternative:** `RunDebugPresenter` (or `RunSessionLifecycle`) owns `start`, `stop`, `restart` — coordinates with `RunOutputCoordinator` exit events. `MainWindow` connects menu IDs once; no direct `_set_run_status` on stop.
- **Suggested remediation:** Extend presenter with `stop()` and `restart(*, prefer_debug_target: bool)`; route `menu_wiring.py:51-52` through presenter. Align transient entry cleanup (`main_window.py:2992-2995`) with lifecycle owner.
- **Tests that would prove fix:** Integration/slow test: Stop → exit → idle status; Restart after exit completes starts second session (not `ALREADY_RUNNING`).
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-4 — Restart races stop and fails silently on `ALREADY_RUNNING`

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:2357-2363` — `_handle_restart_action` calls `self._run_service.stop_run()` then immediately relaunches without awaiting supervisor idle. `run_session_controller.py:76-80` rejects start when `supervisor.is_running()`. `run_debug_presenter.py:57-58` — `elif result.failure_reason == RunSessionStartFailureReason.ALREADY_RUNNING: pass` (no UI feedback). `RunOutputCoordinator` clears mode only on exit event (`run_output_coordinator.py:110`), which may arrive after the restart attempt.
- **Code-judo alternative:** Restart queues on `RunProcessExitEvent` or polls supervisor with bounded wait; presenter surfaces “still stopping” or disables Restart until idle. Never silently ignore `ALREADY_RUNNING` on user-initiated restart.
- **Suggested remediation:** Move restart into presenter with exit-gated relaunch; at minimum show status/message on `ALREADY_RUNNING` when intent is restart.
- **Tests that would prove fix:** Slow integration: start → Restart → assert second session starts or user-visible blocking message; unit test that presenter warns on `ALREADY_RUNNING` for restart intent.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-5 — Breakpoint SSOT exists but is bypassed via mutable dict aliases

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/breakpoint_store.py:16-22` — docstring claims SSOT, but `breakpoints_by_file` and `breakpoint_specs_by_key` properties return **live mutable dicts**. `main_window.py:585-586,631` injects these into `LocalHistoryWorkflow` / `EditorSessionWorkflow` / `ProjectTreeActionCoordinator`. `editor_session_workflow.py:98-113` clears and repopulates dicts directly; `project_tree_controller.py:47,77-79` mutates `breakpoints_by_file` on file delete/move without going through store methods. Dual internal stores (`_breakpoints_by_file` vs `_breakpoint_specs_by_key`) remain (`breakpoint_store.py:13-14`); `set_line_enabled(..., enabled=False)` removes spec but gutter set semantics differ from panel toggle paths.
- **Code-judo alternative:** `BreakpointStore` exposes methods only (`clear_file`, `remap_paths`, `restore_snapshot`, `lines_for_file`, `all_specs`) — no mutable dict exports. Collaborators call store API; workflow owns single store instance.
- **Suggested remediation:** R2 hard cutover — replace dict injection with `BreakpointStorePort` protocol; migrate `EditorSessionWorkflow` / tree coordinator to store methods. Panel toggle fix (`debug_control_workflow.py:240-241` calls `set_line_enabled`) is correct; lock down alias leaks next.
- **Tests that would prove fix:** Unit tests on store invariants (gutter set ↔ spec enabled); session-restore integration test uses store API not dict mutation; existing `test_main_window_session_persistence_integration.py` rewritten against public store methods.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-6 — Debug launch boilerplate triplicated inside `RunLaunchWorkflow`

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** Breakpoint assembly + exception policy + `start_session` + `record_debug_target` repeated:
  - Project default debug: `run_launch_workflow.py:254-261`
  - Named config debug: `run_launch_workflow.py:511-526`
  - Active file debug: `run_launch_workflow.py:681-697` (only path passing `active_file_path` / `remapped_active_path` to `build_debug_breakpoints_for_launch`)
  Same pattern noted in TN-SHELL-MW-08-4 on MainWindow; moved but not collapsed.
- **Code-judo alternative:** Single `RunLaunchWorkflow.start_debug_session(*, entry_file, argv=..., source_maps=..., remapped_paths=...)` builds breakpoints via `debug_control_workflow`, applies policy, calls presenter, records target kind.
- **Suggested remediation:** Extract private `_start_debug_session(...)`; three public handlers become one-liners.
- **Tests that would prove fix:** Parametrize `test_run_command_routing.py` debug paths asserting identical breakpoint/policy wiring; transient remap test already covers active-file kwargs.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-7 — Three incompatible “clear console” behaviors on the run/output path

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** Run menu → `menu_wiring.py:63` → `main_window.py:2365-2372` — `_handle_clear_console_action` clears `_console_model`, run log panel, python console widget, **and** debug panel output. In-tab toolbar → `main_window_panels.py:262` — `clear_btn` → `python_console_widget.clear_console` (display only). Context menu → `python_console_widget.py:393` — same widget-only clear. Session start prep → `main_window.py:2344-2350` — `_prepare_for_session_start` clears output tail and problems and calls `run_log_panel.begin_run()` but **does not** clear `_console_model`; `run_session_controller.py:90-91` appends separator + “Starting run…” on every start (append semantics). Cross-ref TN-SHELL-MW-09-2.
- **Code-judo alternative:** Explicit policy: `clear_run_output_sinks()` (menu) vs `clear_python_console_display()` (toolbar) vs `prepare_new_run()` (session start — document whether prior console lines persist). Rename menu item if it clears debug + run log, not “console” alone.
- **Suggested remediation:** Product decision in PRD, then route all surfaces through named workflow methods; avoid widening `_handle_clear_console_action` without label change.
- **Tests that would prove fix:** Characterization tests with mocked sinks: menu clear vs toolbar clear vs `before_start` hook assert which models/panels are touched (risk-first gate).
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-8 — `ReplSessionManager` duplicates run-layer manifest launch logic

- **Persona:** TN-RUN-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `repl_session_manager.py:161-197` — `_launch` builds `RunManifest`, `ReplControlConfig`, `save_run_manifest`, `HostProcessManager.start_manifest` with REPL-specific paths. Parallel logic in `app/run/run_service.py:95-177` for projectless/REPL modes (`build_repl_manifest_path`, `build_repl_log_path`, `RunManifest` construction). Both import from `app/run/run_manifest.py` and `generate_run_id` — business rules duplicated at shell vs run package boundary.
- **Code-judo alternative:** `RunService.start_repl_sidecar(...)` or shared `build_and_launch_repl_manifest(...)` in `app/run/` consumed by `ReplSessionManager`; shell manager owns auto-restart policy and completion socket only.
- **Suggested remediation:** R-run-2 — extract shared REPL manifest builder; hard cutover ReplSessionManager to call run-layer API; delete duplicated manifest field assembly.
- **Tests that would prove fix:** Existing REPL unit/integration tests unchanged behavior; one test asserting manifest schema parity between paths.
- **Handoff overlap:** R-run-2

---

### TN-RUN-SHELL-9 — `RunSessionController` embeds console presentation strings

- **Persona:** TN-RUN-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `run_session_controller.py:89-91,114-116` — `before_start()` hook then unconditional `append_console_line("────────────────────\n", "system")` and `"Starting run...\n"`, plus debug-mode python-console system line. Orchestration layer owns UX copy and formatting; presenter/`MainWindow._prepare_for_session_start` also mutates run-log state (`begin_run`).
- **Code-judo alternative:** Controller returns `RunSessionStartResult` only; presenter or a thin `RunConsolePresenter` appends session banners after successful start (or `before_start` callback owns all prep messaging).
- **Suggested remediation:** Move banner lines to presenter when touching TN-RUN-SHELL-3 lifecycle unification.
- **Tests that would prove fix:** Adjust `test_run_session_controller.py` to assert result fields only; move line assertions to presenter tests.
- **Handoff overlap:** none

---

### TN-RUN-SHELL-10 — `sync_breakpoints_to_active_debug_session` only when debug paused

- **Persona:** TN-RUN-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `debug_control_workflow.py:286-291` — `sync_breakpoints_to_active_debug_session` returns early unless `is_debug_mode and is_debug_paused`. Breakpoint edits while running (not paused) update store and gutter but do not push `update_breakpoints_command` until next pause. Launch-time breakpoints go through manifest (`run_launch_workflow` → presenter → `RunService`); runtime edits during `RUNNING` may desync until pause.
- **Code-judo alternative:** Document intentional model, or extend guard to allow sync when debug session is active and transport connected (not only paused). Align with runner capability in `app/runner/debug_runner.py`.
- **Suggested remediation:** Confirm runner supports mid-run breakpoint updates; if yes, widen guard; if no, document in workflow docstring and debug panel UX.
- **Tests that would prove fix:** Integration test: toggle breakpoint while debug running → runner reflects on next stop or immediately per product spec.
- **Handoff overlap:** R-run-2

---

### TN-RUN-SHELL-11 — Debug refresh stack/locals are byte-identical workflow methods

- **Persona:** TN-RUN-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `debug_control_workflow.py:154-172` — `handle_debug_refresh_stack` and `handle_debug_refresh_locals` identical: guard running, read `selected_frame`, `select_frame_command`, `send_debug_command`. Panel wires two signals (`main_window_panels.py:277-278`) to duplicate methods. Noted in TN-SHELL-DEBUG-3.
- **Code-judo alternative:** Single `handle_debug_refresh_frame_context()` connected to both signals until protocol distinguishes locals refresh.
- **Suggested remediation:** Collapse when touching TN-RUN-SHELL-2 typed host refactor.
- **Tests that would prove fix:** One unit test asserting one transport command per refresh action.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-SHELL-12 — Seam modules lack direct unit tests except launch routing and session controller

- **Persona:** TN-RUN-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** Tests exist for `RunSessionController` (`test_run_session_controller.py`), `RunOutputCoordinator` (`test_run_output_coordinator.py`), and `RunLaunchWorkflow` via `test_run_command_routing.py`. **No** `test_debug_control_workflow.py`, `test_breakpoint_store.py`, `test_run_debug_presenter.py`, or `test_repl_session_manager.py` under `tests/unit/shell/` (grep). Breakpoint store behavior validated only indirectly through MainWindow integration tests mutating private dicts (`test_main_window_session_persistence_integration.py:71-85`).
- **Code-judo alternative:** After TN-RUN-SHELL-2/5, add stub-host tests for debug workflow and store invariants per risk-first gate (breakpoint persistence and transport commands justify tests).
- **Suggested remediation:** Do not add tests in this review round; note gap for fix agent after typed host + store encapsulation.
- **Tests that would prove fix:** See above; prioritize store invariant and presenter failure-reason mapping (`ALREADY_RUNNING` on restart).
- **Handoff overlap:** none

---

## Positive signals (not findings)

- **`RunSessionController`** — typed `RunSessionStartResult` / `RunSessionStartFailureReason`; clean `RunService` boundary; projectless script entry allowed (`run_session_controller.py:65-75`). Well covered by unit tests.
- **`RunOutputCoordinator`** — pure event router with injected callbacks; no `window: Any`; debug vs output vs exit paths are testable in isolation (`test_run_output_coordinator.py`).
- **`RunLaunchWorkflow` extraction** — addresses TN-SHELL-MW-08-1/2 themes: typed `DebugTarget` union (`run_launch_workflow.py:29-84`), `RunLaunchWorkflowHost` protocol, characterization tests without MainWindow.
- **`ReplSessionManager`** — correctly uses private `HostProcessManager`; auto-restart backoff (`repl_session_manager.py:213-228`); completion over control socket with degradation envelope — appropriate shell-side orchestration.
- **`BreakpointStore` introduction** — panel toggle now syncs gutter (`debug_control_workflow.py:240-241`); partial fix for TN-SHELL-DEBUG-1.

---

## Approval bar (this slice)

**Would not approve** new run/debug launch paths on `MainWindow` or further growth of `run_launch_workflow.py` past ~800 LOC without splitting run-config UX and collapsing debug launch helpers (TN-RUN-SHELL-1, TN-RUN-SHELL-6). **Would not approve** new breakpoint call sites through raw dict aliases (TN-RUN-SHELL-5). Fix TN-RUN-SHELL-4 (restart race + silent `ALREADY_RUNNING`) before treating Restart as reliable. Any run-config or debug dialog move must record four-theme validation (Light, Dark, HC Light, HC Dark).
