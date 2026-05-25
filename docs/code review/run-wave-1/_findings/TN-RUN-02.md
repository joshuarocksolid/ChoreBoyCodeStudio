# TN-RUN-02 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUN-02  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/run/process_supervisor.py` (317 LOC), `app/run/host_process_manager.py` (62 LOC), `app/run/run_service.py` (330 LOC), `app/run/console_model.py` (45 LOC), `app/run/output_tail_buffer.py` (43 LOC). Cross-read: `app/shell/run_session_controller.py`, `tests/integration/run/test_run_service_integration.py`, `tests/unit/run/test_run_service.py`, `tests/unit/run/test_process_supervisor.py`, `tests/integration/run/test_process_supervisor_integration.py`, `app/shell/run_output_coordinator.py`, `app/shell/run_debug_presenter.py`, `docs/ARCHITECTURE.md` §4.1/§6.

---

## Executive verdict

**Not thermo-clean.** The subprocess boundary is mostly sound — `ProcessSupervisor` has real stale-exit hardening and integration tests cover stop/input/state ordering — but **RunService orchestration is not atomic or thread-safe**. A second `start_run` attempt can tear down an active debug transport before the supervisor rejects the launch; session and pause flags mutate on supervisor/transport threads while the shell reads them on the Qt thread without synchronization; and `start_run` persists manifests (and sometimes opens debug sockets) before process exclusivity is proven, leaving orphan artifacts and leaked listeners on failure paths. `HostProcessManager` is a pass-through wrapper that buys no boundary, and `ConsoleModel` / `OutputTailBuffer` are shell output buffers living in the lifecycle package despite zero use by `RunService` or `ProcessSupervisor`. **Would not approve** further run-mode growth in `run_service.py` without extracting artifact planning, making session state single-owner + thread-safe, and collapsing stop/wait ownership into one lifecycle coordinator.

---

### TN-RUN-02-1 — Re-entrant `start_run` destroys active debug transport before supervisor exclusivity check

- **Persona:** TN-RUN-02
- **Severity:** BLOCKER
- **Evidence:** `app/run/run_service.py:150-156` — every debug start calls `self._close_debug_transport_server()` then `DebugTransportServer(...).start()` **before** `save_run_manifest` or `start_manifest`. `app/run/run_service.py:179-186` — `start_manifest` is the first point that can raise `"Runner process is already active."` (`app/run/process_supervisor.py:67-68`). `app/run/run_service.py:184-186` — on failure, only the **new** transport is closed; the first run's transport is already gone.
- **Code-judo alternative:** Make `RunService.start_run` a single atomic gate: (1) acquire run lock / verify `not supervisor.is_running()`, (2) only then start debug transport and write artifacts, (3) launch process, (4) commit `RunSession`. Never call `_close_debug_transport_server()` until the prior run's process has exited (or fold transport lifecycle into the same state machine as the subprocess).
- **Suggested remediation:** Add an internal `_assert_idle()` at the top of `start_run` (raise `RunLifecycleError` before side effects). Move debug-transport open to after successful `supervisor.start`, or bind transport lifetime to `ProcessSupervisor` exit events so re-entrant calls cannot close a peer run's socket.
- **Tests that would prove fix:** Integration test: start debug run, call `start_run` again without stopping (bypassing shell guard), assert first run's debug transport still accepts commands and `send_debug_command("continue")` succeeds; assert no orphan manifest from the rejected attempt (pairs with TN-RUN-02-3).
- **Handoff overlap:** R-run-2

---

### TN-RUN-02-2 — RunService session and debug-pause flags mutate on supervisor threads without synchronization

- **Persona:** TN-RUN-02
- **Severity:** BLOCKER
- **Evidence:** `app/run/run_service.py:225-229` — `_forward_event` clears `_current_session` and `_is_debug_paused` from the supervisor waiter/reader callback path. `app/run/run_service.py:234-241` — `_forward_debug_message` sets `_is_debug_paused` from the debug transport thread. `app/shell/run_session_controller.py:175-177` and `app/shell/debug_control_workflow.py:288-312` — shell reads `is_debug_mode` / `is_debug_paused` on the Qt thread with no lock or queue barrier. `app/shell/main_window.py:2843-2846` — run events are queued to the main thread, but **RunService's own fields are updated before enqueue** in `_forward_event`.
- **Code-judo alternative:** RunService exposes an immutable snapshot (`RunLifecycleSnapshot`) updated only on the main thread — supervisor callbacks enqueue raw `ProcessEvent`s; a single `RunLifecycleReducer` applies them on the Qt timer thread alongside shell UI updates. Debug pause becomes part of that snapshot, not a separate bool.
- **Suggested remediation:** Introduce `threading.Lock` around `_current_session` / `_is_debug_paused` **or** stop mutating RunService from supervisor callbacks entirely (forward-only, let shell/controller own session truth). Prefer the reducer pattern to align with `_run_event_queue` already in `main_window.py`.
- **Tests that would prove fix:** Stress test: spawn run that emits rapid debug stop/continue events while main thread polls `is_debug_paused` in a loop; assert no `True`/`False` torn reads (or assert all reads happen after queued apply). Characterization test that `current_session` and shell `_active_run_session_info` remain consistent through exit.
- **Handoff overlap:** R-run-2, shell-wave-1-followup

---

### TN-RUN-02-3 — Non-atomic `start_run`: artifacts and debug sockets commit before process launch succeeds

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_service.py:157-177` — `ensure_directory`, `RunManifest` construction, and `save_run_manifest(manifest_path, manifest)` run **before** `self._host_manager.start_manifest(...)`. `app/run/run_service.py:150-156` — debug mode opens `DebugTransportServer` before persist. If `ensure_directory` / `save_run_manifest` raises after transport start, nothing closes the listener (`except` at 184-186 only wraps `start_manifest`). If `start_manifest` raises because a process is already active, manifest JSON for the new `run_id` remains on disk with no matching process.
- **Code-judo alternative:** Split `RunArtifactPlanner` (pure: paths, manifest payload) from `RunProcessLauncher` (side effects). Launcher sequence: verify idle → write manifest to temp → start process → atomic rename / commit session. Debug transport starts only after manifest commit succeeds **and** supervisor accepts launch.
- **Suggested remediation:** Wrap pre-start side effects in `try/finally` that closes debug transport on any failure after line 150. Add `RunService._assert_idle()` before artifact writes. Consider deleting orphan manifest on failed launch.
- **Tests that would prove fix:** Unit test with monkeypatched `save_run_manifest` raising after debug transport start — assert transport port is closed (no leaked listener). Unit test: supervisor `start` raises `RunLifecycleError` — assert manifest file removed or marked invalid; `current_session` unchanged.
- **Handoff overlap:** R-run-2

---

### TN-RUN-02-4 — `start_run` monolith with triplicated projectless/project path resolution

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_service.py:81-196` — single 115-line method owns run-id generation, three branch variants (projectless REPL, projectless script, loaded project), debug transport wiring, manifest persistence, and process launch. `app/run/run_service.py:107-113` vs `123-128` vs `137-138` — copy-pasted working-directory normalization (`expanduser`, absolute vs relative join, `.resolve()`). `app/run/run_service.py:304-329` — path helpers already extracted for manifest/log paths but not launch context.
- **Code-judo alternative:** Introduce `LaunchContext` dataclass built by `plan_launch(loaded_project, entry_file, mode, ...)` returning `(manifest, launch_cwd, log_path)` as a pure plan. `start_run` becomes ~15 lines: plan → optional debug attach → persist → start → session. Deletes nested if-ladder.
- **Suggested remediation:** Extract `app/run/launch_plan.py` (or extend `run_manifest.py` with planner) in R-run-2 wave; keep `RunService` as coordinator only. Hard cutover callers/tests to planner — no parallel path resolution.
- **Tests that would prove fix:** Port existing unit tests (`test_start_run_supports_projectless_repl_with_home_working_directory`, `test_start_run_supports_projectless_script_with_explicit_entry`, `test_start_run_applies_explicit_run_overrides`) to target planner directly; `start_run` tests become thin integration smoke.
- **Handoff overlap:** R-run-2

---

### TN-RUN-02-5 — `stop()` and waiter thread dual-own process reap; fragile join window

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/process_supervisor.py:97-154` — `stop()` sends signals, calls `process.wait(timeout=...)`, runs `_cleanup_process_resources`, `_join_waiter_thread()`. `app/run/process_supervisor.py:235-252` — `_wait_for_exit` also calls `process.wait()`, cleanup, state transition to `"exited"`, and emits exit events. `app/run/process_supervisor.py:285-292` — waiter join capped at `0.5` seconds; timeout leaves waiter running. `stop()` never sets `_state = "exited"` itself — callers returning from `stop_run()` can observe `state == "stopping"` until waiter finishes. Prior review flag: subprocess stop/kill races.
- **Code-judo alternative:** One owner thread for reap: `stop()` only signals and sets `_terminated_by_user`; a single `_reap_process(process)` path (called from waiter or stop waiter) performs wait-once, cleanup, state=`exited`, emit exit. `stop()` blocks on an `threading.Event` signalled by reap, not on a second `wait()`.
- **Suggested remediation:** Remove duplicate `process.wait()` from `stop()` — delegate to waiter with a "stop requested" flag, or use `threading.Event` per process for synchronous stop API. Increase join timeout or loop until waiter clears `_waiter_thread` in tests. Emit exit from one code path only.
- **Tests that would prove fix:** Integration test: call `stop()` and assert exactly one `exit` event (already partially covered); add test where `on_event` sleeps briefly — `stop()` still completes and state ends at `exited` within bounded time. Concurrent natural exit + `stop()` test (prior race flag).
- **Handoff overlap:** R-run-2

---

### TN-RUN-02-6 — Bare `except Exception` in supervisor observer path hides shell regressions

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/process_supervisor.py:297-301` — `_emit_event` catches `Exception` and returns silently (`# Event callbacks are observer side-effects; never crash supervisor threads.`). `tests/integration/run/test_process_supervisor_integration.py:124-138` — `test_process_supervisor_ignores_callback_exceptions` codifies swallow behavior. Prior review flag: bare except Exception in shutdown paths (R1 handoff). Related: `app/run/run_service.py:184-186` — broad `except Exception` on launch failure (acceptable if re-raised after cleanup, but pairs with non-atomic start).
- **Code-judo alternative:** Replace bare swallow with narrow `(RuntimeError, OSError)` for known observer failures, or route to injected `on_observer_error: Callable[[Exception], None]` that logs via `app.core.logging` without killing supervisor threads. Never silent pass in production builds.
- **Suggested remediation:** Align with R1 handoff item 1 (`docs/deslop/AUDIT_app_remaining_handoff.md` R1 §Concrete work §1): log at warning/debug with event type context; keep supervisor thread alive. Update test to assert log emission, not just survival.
- **Tests that would prove fix:** Unit test: observer raises `ValueError` — assert logger received structured warning and next output events still flow. Count of bare `except Exception:` in `app/run/` does not increase (R1 acceptance criterion).
- **Handoff overlap:** R1

---

### TN-RUN-02-7 — `HostProcessManager` is an identity wrapper with no earned boundary

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/host_process_manager.py:13-61` — class forwards `is_running`, `stop`, `pause`, `send_input` directly to `ProcessSupervisor`; `start_manifest` only calls `build_runner_command` + `supervisor.start`. No tests under `tests/**/test_host_process*`. `app/run/run_service.py:56-60` — `RunService` holds `_host_manager` solely to reach the same supervisor API.
- **Code-judo alternative:** Delete `HostProcessManager`; inject `ProcessSupervisor` into `RunService` and call `build_runner_command` + `supervisor.start` inline (2 lines). If a boundary is needed, make it `RunnerProcessLauncher` that owns command construction **and** exclusivity guard — not a pass-through.
- **Suggested remediation:** Hard cutover: merge into `RunService` or collapse into `ProcessSupervisor.start_manifest(command_builder=...)`. Remove module in same PR as `LaunchContext` extraction (TN-RUN-02-4).
- **Tests that would prove fix:** Existing `RunService` unit/integration tests remain green after import cutover; no new tests required unless launcher gains exclusivity logic.
- **Handoff overlap:** R-run-2

---

### TN-RUN-02-8 — `ConsoleModel` and `OutputTailBuffer` are shell output concerns misplaced in lifecycle package

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/console_model.py:18-44` and `app/run/output_tail_buffer.py:8-42` — bounded in-memory buffers with no imports from `process_supervisor`, `run_service`, or runner subprocess code. `app/shell/main_window.py:497-499` — only consumer: `self._console_model = ConsoleModel()` and `self._active_run_output_tail = OutputTailBuffer(...)`. `docs/ARCHITECTURE.md:163-176` — editor displays console output; subprocess package should supervise processes, not UI buffer policy.
- **Code-judo alternative:** Move to `app/shell/run_output_buffers.py` (or merge into `run_output_coordinator.py` as private helpers). Single bounded-buffer primitive if both line- and chunk-trim are needed — one deque-based type with `max_lines` **or** `max_chars`, not two parallel implementations in `app/run/`.
- **Suggested remediation:** Relocate modules with hard cutover imports in `main_window.py`; leave re-export shim for one release only if external plugins import them (grep shows no non-shell usage). Keeps `app/run/` focused on manifest + subprocess blast radius per `00-manifest.md` hotspot list.
- **Tests that would prove fix:** Move `tests/unit/run/test_console_model.py` and `test_output_tail_buffer.py` to `tests/unit/shell/`; green fast shard.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUN-02-9 — Three session records diverge across layers and threads

- **Persona:** TN-RUN-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_service.py:61-71` — `_current_session` / `current_session`. `app/shell/run_session_controller.py:41-45` — `_active_session_mode`. `app/shell/run_debug_presenter.py:65-71` — sets `window._active_run_session_info` and `_active_run_session_log_path` on successful start. `app/run/run_service.py:227-228` — exit clears `_current_session` on supervisor thread. `app/shell/run_output_coordinator.py:110` — exit clears `_active_session_mode` on main thread via queued event. `app/shell/main_window.py:2961-2962` — `_apply_run_event` reads `_active_run_session_info` for event bus payloads, not `RunService.current_session`. Prior flag: non-atomic run state.
- **Code-judo alternative:** One `RunSessionHandle` (run_id, mode, paths) owned by `RunSessionController` or a dedicated `RunSessionStore` updated atomically on start/exit. `RunService` returns session metadata once at start and emits events — shell does not mirror fields. Event bus payloads derive from the single store.
- **Suggested remediation:** Collapse shell mirrors into controller store; `RunService.current_session` becomes read-through or is removed from shell API. Apply exit cleanup in one main-thread reducer (pairs with TN-RUN-02-2).
- **Tests that would prove fix:** Integration test: full start → output → exit → assert all three prior fields cleared in same event-handler pass; debug restart (`main_window.py:2357-2363`) leaves consistent state between stop and relaunch.
- **Handoff overlap:** shell-wave-1-followup, R-run-2

---

### TN-RUN-02-10 — pid-keyed resource table over-engineered for strictly single-process supervision

- **Persona:** TN-RUN-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/run/process_supervisor.py:46-47` — `_process_resources: dict[int, _ProcessResources]`. `app/run/process_supervisor.py:67-68` — exclusivity enforced: only one active child. `tests/unit/run/test_process_supervisor.py:27-46` — stale-exit tests manipulate dict entries for old/new PIDs. `_ProcessResources` + pid dict exists solely to handle stale waiter races that a single `_active_resources: _ProcessResources | None` paired with generation counter could handle.
- **Code-judo alternative:** Replace dict with `_resources: _ProcessResources | None` and monotonic `_run_generation: int` incremented on each `start()`; waiter captures generation at spawn and bails if stale. Deletes pid-keyed map and `pop(process.pid)`.
- **Suggested remediation:** Refactor during TN-RUN-02-5 stop/waiter unification; keep stale-exit unit tests green with generation guard.
- **Tests that would prove fix:** Existing `test_wait_for_exit_ignores_stale_process_when_new_process_is_active` adapted to generation counter; no behavior change.
- **Handoff overlap:** R-run-2

---

## Prior-flag reconciliation

| Prior flag | Disposition in this slice |
|------------|---------------------------|
| Bare `except Exception` in shutdown paths | **Confirmed** — `ProcessSupervisor._emit_event` (`process_supervisor.py:299`); codified by integration test. TN-RUN-02-6 → **R1**. Launch cleanup at `run_service.py:184` re-raises after transport close — lower priority. |
| Subprocess stop/kill races | **Partially mitigated, structurally debt** — stale-exit guard in `_wait_for_exit` (`process_supervisor.py:239-240`) and unit tests help; dual `wait()` + 0.5s waiter join in `stop()` remains a race surface. TN-RUN-02-5 → **R-run-2**. |
| Non-atomic run state | **Confirmed and widened** — manifest-before-launch (TN-RUN-02-3), thread-unsafe session fields (TN-RUN-02-2), triple shell mirrors (TN-RUN-02-9). Not thermo-clean. |

## Positive signals (replicate, do not rewrite)

- `ProcessSupervisor` stale-exit guard and dedicated unit tests (`tests/unit/run/test_process_supervisor.py`) — keep this pattern when unifying stop/wait.
- Integration coverage for stop/input/state ordering (`tests/integration/run/test_process_supervisor_integration.py`, `tests/integration/run/test_run_service_integration.py`) — extend for atomic start and debug re-entrancy, do not replace with mock-heavy unit tests.
- `RunSession` frozen dataclass and path helpers at bottom of `run_service.py` — good contracts; extract planner without changing on-disk layout.
- `OutputTailBuffer` / `ConsoleModel` implementations are small and tested — worth keeping, wrong package (move, don't rewrite).
