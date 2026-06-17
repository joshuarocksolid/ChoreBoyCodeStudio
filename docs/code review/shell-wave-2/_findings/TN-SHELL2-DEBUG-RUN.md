# TN-SHELL2-DEBUG-RUN — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-DEBUG-RUN  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/debug_panel/` (818 LOC), `debug_control_workflow.py` (319 LOC), `run_launch/` (414 LOC), `run_launch_workflow.py` (582 LOC), `breakpoint_store.py` (111 LOC), `run_session_controller.py` (232 LOC). Cross-read: `debug_shell_host.py`, `run_debug_presenter.py`, `main_window.py` (stop/restart), `clear_console_policy.py`, TN-RUN-INTEG, TN-RUN-SHELL. Re-validate Shell Wave 1 **CC-12**, **CC-14**.

**Delta note:** Scope files are **unchanged** between baseline `fccb611` and post-kickoff HEAD `430c567`. This critic audits the **post–Shell Wave 1 / partial Run Wave 1 remediation state** at baseline — not a line-range delta diff.

---

## Executive verdict

**REJECT for the debug/run shell seam slice.** Shell Wave 1 R2 and Run Wave 1 follow-up landed real extractions: `BreakpointStore` owned by `DebugControlWorkflow`, typed `DebugShellHost`, `RunLaunchWorkflow` + `run_launch/` subpackage with frozen `DebugTarget`, `RunSessionController` + `RunSessionStore`, and debug panel split (`debug_panel_trees.py` / `debug_panel_widget.py`). **CC-12** (breakpoint SSOT) and **CC-14** (launch graph off MainWindow) are **substantially closed**, not fully closed. Dominant remaining risks match Run Wave 1 TN-RUN-INTEG shell handoff: **restart lifecycle still on MainWindow with stop-then-immediate-relaunch race** (Run CC-17), **typed-host migration stops at `DebugControlWorkflow`** while `RunDebugPresenter` and `RunLaunchWorkflowHost` remain `Any`-heavy (Run CC-16 partial), and **dual breakpoint clear-all paths** (panel vs menu). No **REGRESSION** vs Shell Wave 1 remediation intent; several Run Wave 1 findings are **materially improved** (dict-alias bypass removed, `ALREADY_RUNNING` surfaced in UI, run-config/active-file extracted). **Do not approve** new run/debug launch surfaces or breakpoint call sites until lifecycle symmetry and presenter/host typing land.

---

## Prior-wave re-validation (CC-12, CC-14)

| CC ID | Shell Wave 1 headline | Status @ `fccb611` | Evidence |
|-------|----------------------|-------------------|----------|
| **CC-12** | Debug breakpoint state split across MainWindow + workflows | **SUBSTANTIALLY CLOSED** | `DebugControlWorkflow.__init__` owns `BreakpointStore` (`debug_control_workflow.py:28-30`); injected as `breakpoint_store=` into `EditorSessionWorkflow`, `LocalHistoryWorkflow`, `ProjectTreeActionCoordinator` (`main_window_composition.py:385,425`) — no MainWindow dict fields. Session persist/restore uses `lines_snapshot()` + `restore_session_breakpoints()` (`editor_session_workflow.py:78-137`); tree delete/move uses `clear_file` / `remap_paths` (`project_tree_controller.py:49,79`). Unit tests: `test_breakpoint_store.py`, `test_debug_control_workflow.py`. **Residual:** dual internal maps (`_breakpoints_by_file` vs `_breakpoint_specs_by_key`); panel disable semantics via `set_line_enabled(False)` drops spec; dual clear-all paths (finding 4). |
| **CC-14** | Run/debug launch graph still on MainWindow | **SUBSTANTIALLY CLOSED** | Launch menu/run-config/debug-target memory live in `RunLaunchWorkflow` (582 LOC) delegating to `run_launch/active_file_launch.py` (113), `run_launch/run_configuration_workflow.py` (213), `run_launch/debug_targets.py` (64). Typed `DebugTarget` union + `debug_target_from_mapping` for legacy dicts. **Residual:** stop/restart/clear still on `MainWindow` (`main_window.py:465-482`); `RunDebugPresenter` still `window: Any` (`run_debug_presenter.py:18-19`); restart race (finding 1). Run-config status-bar chrome correctly colocated in `RunConfigurationWorkflow`. |

### Cross-read: Run Wave 1 TN-RUN-INTEG themes touching this slice

| Run CC | Theme | Slice status @ baseline |
|--------|-------|-------------------------|
| **CC-02** | Pause authority split | **PARTIAL IMPROVED** — toolbar gating reads `DebugSession.state.execution_state` via `RunSessionController.refresh_action_states` (`run_event_workflow.py:322-328`); breakpoint sync still gated on paused (`debug_control_workflow.py:264-267`). Run-layer bool mirror may persist — out of slice. |
| **CC-09** | Triple session mirrors | **PARTIAL IMPROVED** — `RunSessionStore` in controller (`run_session_controller.py:40-50,119`); presenter still publishes bus events separately. |
| **CC-16** | `run_launch_workflow` god workflow | **PARTIAL CLOSED** — 725 → 582 LOC + `run_launch/` extraction; facade still owns tree handlers + rerun dispatch. |
| **CC-17** | Restart race + silent `ALREADY_RUNNING` | **PARTIAL** — presenter now warns on `ALREADY_RUNNING` (`run_debug_presenter.py:56-61`); restart still stop-then-immediate-relaunch on MW (`main_window.py:473-479`). |
| **CC-18** | BreakpointStore SSOT bypass via dict aliases | **SUBSTANTIALLY CLOSED** — no public mutable dict properties; collaborators use store methods only. |

---

### TN-SHELL2-DEBUG-RUN-1 — Restart lifecycle race: stop then immediate relaunch on MainWindow

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:473-479` — `_handle_restart_action` calls `stop_run()` then immediately `handle_rerun_last_debug_target_action()` / `handle_run_action()` with no exit-gated wait. `run_session_controller.py:81-86` rejects when `supervisor.is_running()`. User-initiated restart can hit `ALREADY_RUNNING` even though presenter now shows a dialog (`run_debug_presenter.py:56-61`) — race unchanged from TN-RUN-SHELL-4.
- **Code-judo alternative:** `RunDebugPresenter.restart(*, prefer_debug_target: bool)` queues relaunch on `RunProcessExitEvent` or bounded supervisor idle poll; menus wire presenter only. Delete restart orchestration from MainWindow.
- **Suggested remediation:** Hard cutover `menu_wiring.py:52` to presenter; slow integration: Stop → Restart → second session starts reliably.
- **Tests that would prove fix:** Integration/slow test after exit event; unit test presenter blocks relaunch until idle.
- **Handoff overlap:** CC-14, Run CC-17, TN-SHELL2-MW-5

---

### TN-SHELL2-DEBUG-RUN-2 — Session lifecycle asymmetry: start via presenter, stop/restart on MainWindow

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Start path: `run_launch_workflow.py:212-222` → `run_debug_presenter.py:21-90` → `run_session_controller.py:52-124`. Stop: `main_window.py:468-471` — direct `stop_session` + `set_run_status("stopping")` bypassing presenter. Restart: finding 1. `before_start` prep (`prepare_new_run`) only on start path via presenter callback (`run_debug_presenter.py:47`).
- **Code-judo alternative:** Single `RunSessionLifecycle` (or extended presenter) owns start/stop/restart/clear prep; MainWindow binds menu IDs once.
- **Suggested remediation:** Pair with TN-SHELL2-MW-5; move stop/restart into presenter in one PR.
- **Tests that would prove fix:** Menu stop/restart integration unchanged behavior; MW loses `_handle_stop_action` / `_handle_restart_action`.
- **Handoff overlap:** CC-14, Run CC-16, TN-SHELL2-MW-5

---

### TN-SHELL2-DEBUG-RUN-3 — Typed debug workflow vs `window: Any` presenter (inconsistent seam)

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL (partial closure of Run TN-RUN-SHELL-2)
- **Severity:** STRUCTURAL
- **Evidence:** `debug_control_workflow.py:28` — `DebugShellHost` protocol (not `window: Any`). Contrast `run_debug_presenter.py:18-19` — `def __init__(self, window: Any)` with 15+ private touches (`_run_session_controller`, `_event_bus`, `_debug_panel`, `_bottom_tabs_widget`, …). Same split noted in TN-RUN-SHELL-2.
- **Code-judo alternative:** `RunDebugPresenterHost` protocol mirroring launch host — inject controller, event bus, debug panel port, run-event workflow callbacks. Presenter becomes testable without `MainWindow.__new__`.
- **Suggested remediation:** Add `test_run_debug_presenter.py` with stub host when typing lands; hard cutover composition wiring.
- **Tests that would prove fix:** Presenter unit tests map all `RunSessionStartFailureReason` values without Qt main window.
- **Handoff overlap:** CC-14, Run CC-16, CC-22

---

### TN-SHELL2-DEBUG-RUN-4 — Dual breakpoint clear-all paths: atomic store clear vs N panel remove emits

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Menu Run → Remove All Breakpoints → `debug_control_workflow.handle_remove_all_breakpoints_action` (`menu_wiring.py:60`, `debug_control_workflow.py:80-87`) — single `_store.clear_all()`, gutter sweep, one sync. Debug panel Clear All button → `debug_panel_widget.py:403-405` — loops `breakpoint_remove_requested.emit` per row (N transport/sync passes if session paused). Panel path never calls `handle_remove_all_breakpoints_action`.
- **Code-judo alternative:** Panel emits `clear_all_breakpoints_requested` signal; workflow handles atomically (one code path). Or wire panel button directly to workflow method in `main_window_panels.py`.
- **Suggested remediation:** Hard cutover panel signal; delete per-item loop clear.
- **Tests that would prove fix:** Unit test: panel clear invokes store `clear_all` once; integration: gutter + panel list empty after either surface.
- **Handoff overlap:** CC-12, Run CC-18 (partial)

---

### TN-SHELL2-DEBUG-RUN-5 — `RunLaunchWorkflowHost` protocol leaks `Any` on critical debug/run ports

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `run_launch_workflow.py:117-134,144-154,162-172` — `editor_manager`, `debug_control_workflow`, `run_debug_presenter`, `settings_service`, `resolve_theme_tokens`, `test_runner_workflow`, `status_bar`, `logger` all typed `Any`. `ActiveFileLaunchHost` repeats pattern (`active_file_launch.py:14-33`). Forces `# type: ignore[attr-defined]` at call sites (`run_event_workflow.py:327-338`).
- **Code-judo alternative:** Narrow protocols per port (`DebugControlWorkflowPort` with `build_debug_breakpoints_for_launch`, `RunDebugPresenterPort` with `start_session`, …) — same move as `DebugShellHost`.
- **Suggested remediation:** Typing pass paired with TN-SHELL2-COMP composition adapters; no new `Any` host fields.
- **Tests that would prove fix:** `npx pyright` clean on `run_launch_workflow.py` with protocol stubs.
- **Handoff overlap:** CC-14, CC-22, Run CC-16

---

### TN-SHELL2-DEBUG-RUN-6 — `RunLaunchWorkflow` facade still 582 LOC; debug launch boilerplate duplicated

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL (partial closure of Run TN-RUN-SHELL-1/6)
- **Severity:** STRUCTURAL
- **Evidence:** `run_launch_workflow.py:243-262,460-493` — project debug and named-config debug both assemble breakpoints + exception policy + `start_session` + `record_debug_target(ProjectTarget())`. Active-file path correctly delegated to `ActiveFileLaunchWorkflow` (`529-536`) with transient remap. Facade still owns tree run handlers (`410-433`), rerun dispatch (`372-408`), and ad-hoc dialog orchestration (`299-364`).
- **Code-judo alternative:** Private `_start_debug_session(...)` collapses project/config/active debug wiring; facade exposes thin action methods only. Tree run → `ActiveFileLaunchWorkflow` or shared `TreeFileLaunchWorkflow`.
- **Suggested remediation:** Do not grow past ~650 LOC without split; next feature triggers extraction PR.
- **Tests that would prove fix:** Parametrize existing `test_run_command_routing.py` debug paths assert identical breakpoint/policy wiring through one helper.
- **Handoff overlap:** CC-14, Run CC-16

---

### TN-SHELL2-DEBUG-RUN-7 — CC-12 residual: disabled breakpoint drops spec; dual-store invariant burden

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `breakpoint_store.py:85-94` — `set_line_enabled(..., enabled=False)` removes spec from `_breakpoint_specs_by_key` while gutter set loses line. `handle_debug_breakpoint_toggle` calls both `set_spec(with_enabled(...))` and `set_line_enabled` (`debug_control_workflow.py:217-223`) — redundant writes. Disabled breakpoints with conditions/hit counts are discarded until re-enabled. Editor gutter uses line sets only; panel checkbox maps to enabled flag — semantics differ from remove.
- **Code-judo alternative:** Single map `DebugBreakpoint` with `enabled` flag; gutter reads enabled lines; disable is not delete spec. Or document disable-as-remove and delete dual-store `_breakpoints_by_file`.
- **Suggested remediation:** Product decision + store invariant test; align panel toggle with gutter without spec eviction.
- **Tests that would prove fix:** Unit test: disable preserves condition; re-enable restores hit threshold.
- **Handoff overlap:** CC-12, Run CC-18

---

### TN-SHELL2-DEBUG-RUN-8 — Debug panel widget 484 LOC; signal surface still monolithic

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL (partial closure of Shell CC-21 debug panel split)
- **Severity:** NICE-TO-HAVE
- **Evidence:** Shell Wave 1 flagged `debug_panel_widget.py` at 753 LOC. Baseline: trees extracted to `debug_panel_trees.py` (334 LOC); widget 484 LOC with 10 signals (`debug_panel_widget.py:50-60`) and inline refresh for threads/stack/vars/watch/breakpoints. Under 1k rule but dense.
- **Code-judo alternative:** Extract section controllers if widget grows again; keep trees module as SSOT for builders.
- **Suggested remediation:** R3 only if adding sections; current split is acceptable keeper.
- **Tests that would prove fix:** Existing debug panel unit tests stay green after further split.
- **Handoff overlap:** CC-21, none

---

### TN-SHELL2-DEBUG-RUN-9 — Duplicate debug refresh handlers (stack vs locals)

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `debug_control_workflow.py:146-164` — `handle_debug_refresh_stack` and `handle_debug_refresh_locals` are byte-identical: guard running, read `selected_frame`, `select_frame_command`, `send_debug_command`. Panel wires two signals in `main_window_panels.py` (~277-278).
- **Code-judo alternative:** Single `handle_debug_refresh_frame_context()` connected to both signals until DAP distinguishes locals refresh.
- **Suggested remediation:** Collapse in typed-host cleanup PR (zero behavior change).
- **Tests that would prove fix:** One unit test, one transport command per refresh click.
- **Handoff overlap:** Run CC-16 (partial), none

---

### TN-SHELL2-DEBUG-RUN-10 — Positive: `DebugShellHost` + stub workflow tests (Run Wave 1 pattern to replicate)

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL (closure of Run TN-RUN-SHELL-2 / Shell CC-12)
- **Severity:** NICE-TO-HAVE (positive keeper)
- **Evidence:** `debug_shell_host.py:62-124` — typed ports for run service, debug session, panel, editors, exception policy. `tests/unit/shell/test_debug_control_workflow.py` constructs `StubDebugShellHost` without `MainWindow`. `tests/unit/shell/test_breakpoint_store.py` covers encapsulation helpers.
- **Code-judo alternative:** Replicate for `RunDebugPresenterHost` and narrow `RunLaunchWorkflowHost` (finding 3, 5).
- **Suggested remediation:** Do not regress to `window: Any` on debug workflow; extend pattern to presenter.
- **Tests that would prove fix:** Manifest gate: new debug/run shell tests use stub hosts not `MainWindow.__new__`.
- **Handoff overlap:** CC-12, CC-14, Run CC-16

---

### TN-SHELL2-DEBUG-RUN-11 — Positive: `RunSessionController` + `RunSessionStore` clean run-layer boundary

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** RESIDUAL (positive keeper)
- **Severity:** NICE-TO-HAVE (positive)
- **Evidence:** `run_session_controller.py:37-124` — frozen `RunSessionStartResult`, explicit failure reasons, projectless script/debug entry (`70-74`), pause delegates to `RunService` (`137-150`). Action refresh uses `DebugExecutionState` not ad-hoc pause bool (`180-187`). Covered by `test_run_session_controller.py`.
- **Code-judo alternative:** Move session banner strings to presenter (Run TN-RUN-SHELL-9) when unifying lifecycle.
- **Suggested remediation:** Keep controller free of new UI copy; lifecycle unification absorbs stop/restart.
- **Tests that would prove fix:** Existing unit tests remain green after presenter absorbs messaging.
- **Handoff overlap:** Run CC-09, Run CC-12 (run-layer), none

---

### TN-SHELL2-DEBUG-RUN-12 — Clear-console policy named; menu vs session-start semantics documented in code

- **Persona:** TN-SHELL2-DEBUG-RUN
- **Status:** NEW (post–Wave 1 improvement @ baseline)
- **Severity:** NICE-TO-HAVE (positive)
- **Evidence:** `clear_console_policy.py:41-70` — `clear_run_output_sinks` (menu) vs `prepare_new_run` (session start) vs `clear_python_console_display` (toolbar). `main_window.py:465-466,481-482` delegates to policy helpers. Partially addresses Run TN-RUN-SHELL-7; toolbar-only clear still lives on console widget (TN-SHELL2-CONSOLE scope).
- **Code-judo alternative:** Keep policy module as SSOT; console slice wires toolbar to `clear_python_console_display` only.
- **Suggested remediation:** Cross-reference TN-SHELL2-CONSOLE for remaining toolbar/menu divergence.
- **Tests that would prove fix:** Characterization tests per policy function when touching console slice.
- **Handoff overlap:** Run CC-25, TN-SHELL2-CONSOLE

---

## Slice metrics (baseline `fccb611`)

| Metric | Value |
|--------|------:|
| Scope total LOC | 2,481 |
| Largest file | `run_launch_workflow.py` — 582 |
| Files ≥700 LOC in slice | 0 |
| `debug_panel/` LOC | 818 (widget 484 + trees 334) |
| `DebugControlWorkflow` host typing | `DebugShellHost` (not `window: Any`) |
| `RunDebugPresenter` host typing | `window: Any` |
| `RunLaunchWorkflowHost` `Any` ports | 10 |
| Dedicated unit tests | `test_debug_control_workflow.py`, `test_breakpoint_store.py`, `test_run_command_routing.py`, `test_run_session_controller.py` |
| Delta vs baseline in slice files | 0 bytes (unchanged @ kickoff) |

---

## Verdict summary

| Gate | Result |
|------|--------|
| 1k-line rule (slice) | **PASS** |
| CC-12 breakpoint SSOT | **SUBSTANTIALLY CLOSED** — P1 dual-store + clear-all path |
| CC-14 launch graph off MW | **SUBSTANTIALLY CLOSED** — P1 lifecycle + presenter typing |
| Run CC-17 restart reliability | **FAIL** — race persists |
| Typed host ports (debug/run seam) | **PARTIAL** — workflow yes, presenter/launch host no |
| REGRESSION vs Shell Wave 1 intent | **NONE** |
| Cross-wave Run TN-RUN-INTEG blockers in slice | **1 structural** (restart race); run-layer P0 transport themes out of slice |

**REJECT.** The slice achieved the Shell Wave 1 extraction intent for breakpoints and launch routing and must not revert to MainWindow-owned dicts or inline launch graphs. It is **not thermo-clean**: ship-blocking reliability debt remains on **Restart** (TN-SHELL2-DEBUG-RUN-1), and the **presenter / launch-host typing gap** (TN-SHELL2-DEBUG-RUN-3, -5) will multiply cost on the next debug mode or run-config field. **P1 before new features:** TN-SHELL2-DEBUG-RUN-1, -2, -3, -4, -5. **Keepers:** TN-SHELL2-DEBUG-RUN-10, -11, -12; CC-12/CC-14 substantial closure.

---

*Cross-reference index: Run Wave 1 integration rollup TN-RUN-INTEG; shell MainWindow residuals TN-SHELL2-MW.*
