# TN-SHELL-MW-08 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-08  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 2937–3483 — active-file run/debug launch, transient entry files, project entry repair, debug-target rerun routing, named run configurations (dialogs, status-bar indicator, persistence), session start/stop/restart. Cross-read: `run_session_controller.py`, `run_config_controller.py`, `debug_control_workflow.py`, `run_debug_presenter.py`, `run_output_coordinator.py`, `support/preflight.py`.

---

## Executive verdict

**Not thermo-clean.** Controllers and presenters exist (`RunSessionController`, `RunConfigController`, `RunDebugPresenter`, `DebugControlWorkflow`) but this slice is still **~550 lines of launch orchestration** on `MainWindow`: entry resolution, transient dirty-buffer files, debug-target memory, configuration dialogs, status-bar menu wiring, and stop/restart branching. Extraction is **partial** — the service layer moved out; the user-action graph and UI glue did not. Dominant risks: (1) **dual entry-resolution paths** (preflight vs modal repair) with one path dead on the Run Project main line; (2) **`_last_debug_target` as an untyped dict** driving a four-way rerun router; (3) **asymmetric lifecycle** (start via presenter, stop/restart inline on `MainWindow`) with a plausible restart race into silent `ALREADY_RUNNING`. Four-theme impact is indirect: run-configuration dialogs already receive `ShellThemeTokens` via `_current_theme_tokens()` — any extraction must preserve token plumbing and re-validate HC Light/HC Dark dialog chrome.

---

### TN-SHELL-MW-08-1 — Run launch orchestration is half-extracted; MainWindow still owns the action graph

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2937-3483` — 22 methods spanning active-file launch, entry-point repair, rerun routing, run-config dialogs/menu, session prep, stop, and restart. `RunSessionController.start_session` (`run_session_controller.py:47-118`) handles service calls; `RunDebugPresenter.start_session` (`run_debug_presenter.py:22-88`) maps results to UI — but every **caller decision** (which entry, which breakpoints, which dialog, which debug target) remains on `MainWindow`.
- **Code-judo alternative:** One `RunLaunchWorkflow` (or split `ActiveFileRunWorkflow` + `RunConfigurationWorkflow`) owns the user-action graph: preflight → entry resolution → breakpoint assembly → `RunDebugPresenter.start_session`. `MainWindow` connects menu IDs to workflow public methods and deletes the 22 private handlers in this slice.
- **Suggested remediation:** R2 wave-4 extraction per `docs/deslop/AUDIT_app_remaining_handoff.md` § R2 — net **method count down** on `MainWindow`; no new one-line delegators. Wire menus directly to workflow methods where practical.
- **Tests that would prove fix:** Construct `RunLaunchWorkflow` with stub host (no `MainWindow` import); port `tests/unit/shell/test_run_command_routing.py` and `test_entrypoint_resolution.py` to workflow public API; integration test: F5 → active config → session started event published.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-2 — `_last_debug_target` untyped dict drives a four-way rerun router

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:3090-3123` — `_handle_rerun_last_debug_target_action` branches on `target.get("kind")` values `"project"`, `"active_file"`, `"current_test"`, `"test_node"` with inconsistent payload keys (`file_path` vs `target_path` vs `node_id`). Targets are set in four places in/near this slice (`2974`, `2934`, `3294`) plus via `TestRunnerWorkflow` init callback (`main_window.py:703`: `record_debug_target=lambda target: setattr(self, "_last_debug_target", dict(target))`).
- **Code-judo alternative:** Frozen dataclass union `DebugTarget` (`ProjectTarget | ActiveFileTarget | CurrentTestTarget | TestNodeTarget`) owned by `DebugControlWorkflow` or `RunLaunchWorkflow`; single `record_target()` / `rerun_last()` API; menu enablement reads `workflow.has_rerun_target`.
- **Suggested remediation:** Move target memory into `DebugControlWorkflow` (R2 candidate #2 in handoff); replace dict literals with typed targets; collapse rerun routing to one workflow method that delegates test cases to `TestRunnerWorkflow`.
- **Tests that would prove fix:** Parametrized unit test: each target kind reruns the correct collaborator; regression on dirty-buffer debug rerun (`test_run_command_routing.py` transient remap cases).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-3 — Dual entry-resolution strategies; modal repair path is dead on Run Project

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:3001-3017` — `_resolve_project_entry_for_project_run` prompts for replacement when default entry is missing. **Not called** from `_handle_run_project_action` (`2911-2914`), which uses raw `default_entry` + `_ensure_run_preflight_ready` → Runtime Center. Grep shows production callers: **zero** (only tests in `tests/unit/shell/test_entrypoint_resolution.py` and an assertion in `test_run_command_routing.py:122-124` that run path must **not** invoke modal resolution). `_set_project_entry_point` (`3049-3087`) is still used from project tree (`project_tree_presenter.py:332`).
- **Code-judo alternative:** Single SSOT: either extend `build_run_preflight` (`support/preflight.py:15-174`) with an optional “repair entry” action that returns a chosen replacement, or delete `_resolve_project_entry_for_project_run` and document that entry repair is tree/settings-only. No parallel modal + preflight paths.
- **Suggested remediation:** Hard cutover — delete dead `_resolve_project_entry_for_project_run` / `_prompt_for_project_entry_replacement` **or** wire Run Project through one resolution API; update/delete orphan tests accordingly.
- **Tests that would prove fix:** One characterization test for “missing default entry → user-visible outcome” on the **actual** Run Project path (Runtime Center today); no test-only methods without production callers.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-4 — Debug launch boilerplate triplicated across three entry paths

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** Breakpoint assembly + exception policy + `_start_session` + `_last_debug_target` assignment repeated:
  - Active file: `main_window.py:2959-2974`
  - Named config: `main_window.py:3279-3294`
  - Default project debug (just above slice): `main_window.py:2927-2934`
  All call `self._debug_control_workflow.build_debug_breakpoints_for_launch(...)` with slightly different kwargs (`active_file_path`/`remapped_active_path` only on active-file path).
- **Code-judo alternative:** `DebugControlWorkflow.launch_session(*, mode, entry_file, source_maps, remapped_paths)` or `RunLaunchWorkflow.start_debug(...)` — one method builds breakpoints, applies policy, calls presenter, records target.
- **Suggested remediation:** Extract shared `start_debug_session(...)` into `DebugControlWorkflow` or `RunLaunchWorkflow`; delete duplicated blocks from `MainWindow`.
- **Tests that would prove fix:** Existing `test_start_active_file_session_debug_remaps_active_file_breakpoints_to_transient_path` plus one test per config/project path asserting identical breakpoint/policy wiring.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-5 — Run-configuration UX (~200 LOC) outgrew `RunConfigController`

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `RunConfigController` (`run_config_controller.py:41-108`) owns parse/persist only. `MainWindow` owns dialog orchestration and chrome: `_handle_run_with_configuration_action` (`3125-3160`), `_open_save_invocation_as_configuration_dialog` (`3219-3252`), `_persist_run_configurations_result` (`3297-3336`), status-bar indicator (`3338-3423`), and duplicated `RunConfigurationsInitial` construction. `_persist_run_configurations_result` also mutates `default_argv` via `set_project_default_argv` — persistence split across controller (run_configs) and `MainWindow` (default_argv).
- **Code-judo alternative:** `RunConfigurationWorkflow` with `edit_configurations()`, `save_from_invocation()`, `launch_active()`, `populate_status_menu()`; controller remains I/O; workflow owns active-name state and manifest argv/default_entry side effects in one transaction.
- **Suggested remediation:** R2/R3 — extract workflow; pass `parent`, `tokens`, and `loaded_project` snapshot; connect status-bar menu `aboutToShow` directly to workflow. Validate run-config dialogs in all four theme modes after move.
- **Tests that would prove fix:** Unit tests on workflow without Qt widgets where possible; existing `tests/unit/shell/test_run_config_controller.py` stays for I/O; add workflow test for persist+active-name+indicator refresh.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-08-6 — Delegator layers violate R2 “no new one-line pass-throughs”

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:3425-3426` — `_current_theme_tokens` returns `self._resolve_theme_tokens()`. `main_window.py:3442-3468` — `_start_session` lazily constructs `RunDebugPresenter(self)` then forwards all kwargs. Two indirection hops for every run/debug start; presenter also uses `window: Any` (`run_debug_presenter.py:19-20`).
- **Code-judo alternative:** Construct `RunDebugPresenter` in composition root (`__init__` or shell wiring module); menus call `presenter.start_session` directly. Theme tokens passed into run-config workflow at construction, not via MainWindow method.
- **Suggested remediation:** Eager-init presenter alongside `_run_session_controller`; delete `_start_session` and `_current_theme_tokens` from `MainWindow` when run-config workflow absorbs dialog token needs.
- **Tests that would prove fix:** Presenter unit tests with fake window host; no tests should need to patch `MainWindow._start_session` — patch presenter instead.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-7 — Asymmetric session lifecycle: start via presenter, stop/restart inline

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** Start: `main_window.py:3442-3468` → `RunDebugPresenter.start_session`. Stop: `main_window.py:3471-3474` — `_run_session_controller.stop_session(...)` + `_set_run_status("stopping")` + `_refresh_run_action_states()` with no presenter involvement. Restart: `main_window.py:3476-3482` — `stop_run()` then immediate branch on `active_session_mode` (cleared asynchronously by `RunOutputCoordinator` at exit, `run_output_coordinator.py:110`). Session mode and UI status are owned across three types.
- **Code-judo alternative:** `RunDebugPresenter` (or `RunSessionLifecycle`) owns start **and** stop/restart: `stop()`, `restart(last_target_or_active)`. Coordinator callbacks update presenter-owned state; `MainWindow` does not touch `_set_run_status` on stop.
- **Suggested remediation:** Extend presenter with stop/restart; route `_handle_stop_action` / `_handle_restart_action` through it; align with `RunOutputCoordinator` exit handling.
- **Tests that would prove fix:** Integration test: stop → exit event → idle status; restart after stop completes starts new session (not `ALREADY_RUNNING`).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-8 — Restart may race stop and fail silently on `ALREADY_RUNNING`

- **Persona:** TN-SHELL-MW-08
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:3476-3482` — `_handle_restart_action` calls `self._run_service.stop_run()` then immediately `_handle_rerun_last_debug_target_action()` or `_handle_run_action()` without awaiting supervisor idle. `RunSessionController.start_session` rejects when `supervisor.is_running()` (`run_session_controller.py:76-80`). `RunDebugPresenter` swallows that case with no UI (`run_debug_presenter.py:57-58`: `elif result.failure_reason == RunSessionStartFailureReason.ALREADY_RUNNING: pass`).
- **Code-judo alternative:** Restart queues on process exit (subscribe to `RunProcessExitEvent`) or polls supervisor with bounded wait before re-launch; surface “still stopping” if timeout.
- **Suggested remediation:** Move restart into presenter/coordinator with exit-gated relaunch; never silently ignore `ALREADY_RUNNING` on user-initiated restart.
- **Tests that would prove fix:** Integration/slow test: start run → Restart → assert second session starts or user sees blocking message; unit test that presenter shows feedback on `ALREADY_RUNNING` when intent is restart.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-08-9 — Transient dirty-buffer entry files: correct lifecycle, wrong owner

- **Persona:** TN-SHELL-MW-08
- **Severity:** NICE-TO-HAVE
- **Evidence:** `main_window.py:2947-2999` — `_write_transient_entry_file`, `_delete_transient_entry_file`, `_active_transient_entry_file_path` tracking on `MainWindow`. Cleanup on run exit lives outside slice (`main_window.py:4174-4177`). Logic is cohesive but embedded in the shell god object; well-tested (`test_run_command_routing.py` transient cases).
- **Code-judo alternative:** `TransientEntryFileStore` or method bundle inside `RunLaunchWorkflow` with `create_for_dirty_tab()` / `cleanup_after_exit()`; `MainWindow` holds no temp-path state.
- **Suggested remediation:** Move with `RunLaunchWorkflow` extraction (finding 1); keep public behavior identical.
- **Tests that would prove fix:** Existing transient tests pass unchanged against new owner.
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `RunSessionController` — typed `RunSessionStartResult` / failure reasons; clean run-service boundary (`run_session_controller.py:17-118`).
- `RunConfigController` — focused CRUD/persistence with explicit validation errors (`run_config_controller.py:41-108`).
- `DebugControlWorkflow.build_debug_breakpoints_for_launch` — handles transient path remap (`debug_control_workflow.py:140-163`).
- Preflight integration via `_ensure_run_preflight_ready` → Runtime Center is the **canonical** Run Project gate (`main_window.py:2878-2895`, `support/preflight.py:15-174`).
- Characterization tests exist for routing and transient files (`tests/unit/shell/test_run_command_routing.py`, `test_main_window_run_with_arguments.py`).

---

## Approval bar (this slice)

**Would not approve** a change that adds more run/debug handlers or `_last_debug_target` call sites on `MainWindow` without extracting `RunLaunchWorkflow` / `RunConfigurationWorkflow` and **net-reducing** method count. Any run-config UI move must include four-theme dialog validation (Light, Dark, HC Light, HC Dark).
