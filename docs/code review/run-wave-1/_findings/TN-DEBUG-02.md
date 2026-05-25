# TN-DEBUG-02 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-DEBUG-02
**Date:** 2026-05-25
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`
**Scope:** `app/debug/debug_session.py` (315 LOC), `app/debug/debug_transport.py` (241 LOC). Cross-read: `tests/unit/debug/test_debug_session.py`, `tests/integration/debug/test_debug_session_integration.py`, `app/run/run_service.py` (debug server startup, `_forward_debug_message`, `_forward_debug_transport_error`), `app/shell/run_output_coordinator.py`, `app/runner/debug_runner.py` (transport error → `disconnect` command).

---

## Executive verdict

**Not thermo-clean.** The split between `DebugSession` (pure state reducer) and `DebugTransportServer`/`RunnerDebugTransportClient` (socket I/O) is the right boundary, but pause/run authority is duplicated across three places — `RunService._is_debug_paused` (mutated on the transport read thread), `DebugSession.execution_state` (mutated on the UI thread after a 50 ms queue batch), and shell action gating that reads the former while the inspector reads the latter. Socket teardown races with in-flight `send_command`, transport read failures synthesize `session_ended` without closing the editor-side server, and `continued` leaves a full paused inspector snapshot attached to a running session. There are **zero** unit or integration tests for `debug_transport.py`. Dominant risk: debug desync on the main path (toolbar vs panel vs transport connectivity), not parser edge cases.

---

### TN-DEBUG-02-1 — Pause authority split across transport thread, UI queue, and two state stores

- **Persona:** TN-DEBUG-02
- **Severity:** BLOCKER
- **Evidence:** `app/run/run_service.py:234-244` — `_forward_debug_message` sets `_is_debug_paused` synchronously on the transport read thread before enqueueing the `ProcessEvent`. `app/shell/main_window.py:2843-2846` — events drain on a 50 ms `QTimer` into `RunOutputCoordinator.apply`, which calls `DebugSession.apply_protocol_message` (`app/shell/run_output_coordinator.py:63-71`). Toolbar gating reads `RunService.is_debug_paused` (`app/shell/actions.py:51-55`, `app/shell/run_session_controller.py:177`); inspector/panel reads `DebugSession.state.execution_state` (`app/shell/main_window.py:2739-2756`, `app/shell/debug_panel/debug_panel_widget.py:160-170`). Breakpoint sync gates on `is_debug_paused` (`app/shell/debug_control_workflow.py:288-289`).
- **Code-judo alternative:** Collapse pause/run into one reducer: transport callbacks enqueue raw payloads only; `DebugSession` (or a thin `DebugSessionController` beside it) is the sole authority for `execution_state` and derived `is_paused`; `RunService` exposes `debug_session.state` (or a snapshot) instead of a parallel bool. Action refresh reads the same snapshot the panel uses — no cross-thread flag.
- **Suggested remediation:** Remove `_is_debug_paused` from `RunService`; derive pause from `DebugSession.state.execution_state == PAUSED` after the same queue drain that updates the panel. If a synchronous pre-queue hint is ever needed, pass it inside the enqueued event payload, not a side-channel bool on another thread.
- **Tests that would prove fix:** Integration test: after `stopped`, assert toolbar step/continue enablement and panel `execution_state` flip in the same UI tick; no window where `is_debug_paused` and `execution_state` disagree. Characterization test on `RunService` forwarding: no direct mutation before enqueue.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-02-2 — `send_command` races read-loop teardown on unguarded `_client_resources`

- **Persona:** TN-DEBUG-02
- **Severity:** BLOCKER
- **Evidence:** `app/debug/debug_transport.py:76-87` — `send_command` loads `resources = self._client_resources` outside `_write_lock`, then writes. `app/debug/debug_transport.py:145-146` — `_read_loop` `finally` sets `self._client_resources = None` and closes sockets without acquiring `_write_lock`. `app/debug/debug_transport.py:89-94` — `close()` nulls `_client_resources` on the caller thread while the read thread may still be in `finally`. Only writes are serialized; the connection pointer itself is unprotected.
- **Code-judo alternative:** Hold one `_connection_lock` (or reuse `_write_lock`) for the full `{get resources → encode → write}` span **and** for `{null resources → shutdown}`. Alternatively, an `_AtomicConnection` handle whose `send` returns `ConnectionClosed` instead of raising mid-write.
- **Suggested remediation:** Extend the lock scope in `send_command`/`close`/`_read_loop` so `_client_resources` cannot be cleared while a send is in flight. `RunService.send_debug_command` should map transport-closed to a typed `RunLifecycleError` the shell can surface once, not intermittent `RuntimeError`.
- **Tests that would prove fix:** Unit test with a fake socket: read thread closes connection while main thread calls `send_command`; assert no write after close and a single deterministic error. Threaded stress: N concurrent sends + forced disconnect.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-02-3 — Transport read failure emits synthetic `session_ended` but editor server stays open

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_transport.py:141-146` — read failure clears client resources and emits error via `_emit_error`. `app/run/run_service.py:246-259` — `_forward_debug_transport_error` sets `_is_debug_paused = False` and forwards synthetic `session_ended` + stderr output; it does **not** call `_close_debug_transport_server()`. Runner side sets `_transport_failed` and injects `disconnect` (`app/runner/debug_runner.py:412-414`), but editor-side listener remains until process `exit` (`app/run/run_service.py:226-229`). Subsequent `send_debug_command` hits `RuntimeError("Debug transport is not connected.")` (`app/debug/debug_transport.py:80-81`).
- **Code-judo alternative:** Treat transport error as a terminal session transition: close server, clear debug mode flags, and let `RunOutputCoordinator` apply `mark_exited()` through the same path as a real `session_ended` event — one lifecycle funnel.
- **Suggested remediation:** `_forward_debug_transport_error` should invoke `_close_debug_transport_server()` after enqueueing the synthetic event (or fold close into the coordinator's handling of `session_ended`). Document whether the subprocess is expected to keep running after transport loss; if not, escalate to `stop_run()`.
- **Tests that would prove fix:** Unit test: simulate read-loop exception → assert server socket closed, `send_debug_command` raises `RunLifecycleError`, session state reaches `EXITED` after coordinator apply. Integration: kill runner socket mid-pause → shell recovers without zombie listener on port.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-02-4 — `continued` clears execution flags but retains full paused inspector snapshot

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_session.py:71-75` — `continued` sets `execution_state = RUNNING` and clears `stop_reason` only; threads, frames, scopes, variables, and `variables_by_reference` from the last `stopped` event remain. Contrast `mark_exited()` (`app/debug/debug_session.py:51-61`), which clears inspector collections. Panel still renders stack/locals from stale data until the next stop (`app/shell/debug_panel/debug_panel_widget.py:160-170` keys off `execution_state` for auto-eval but not tree clearing).
- **Code-judo alternative:** Model two explicit snapshots — `running_snapshot` (empty inspector) and `paused_snapshot` (full payload) — swapped atomically on `stopped`/`continued`/`mark_exited`. Or a single `apply_running()` helper that `continued`, `session_ready`, and post-exit paths all call.
- **Suggested remediation:** On `continued` (and optionally `session_ready`), clear or reset inspector fields the same way `mark_exited` does (except breakpoints/policy/watch cache policy — decide explicitly). Ensure `_apply_debug_inspector_event` does not reopen the last frame file when state is `RUNNING`.
- **Tests that would prove fix:** Unit test: `stopped` → assert frames populated → `continued` → assert `frames == []`, `variables == []`, `variables_by_reference == {}`. Integration: after continue, panel trees empty or show running placeholder.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-DEBUG-02-5 — No tests for socket lifecycle, hello validation, or reconnect policy

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_transport.py` — 241 LOC, two public classes, two daemon threads each, token/protocol validation (`:135-139`), and close/join semantics (`:89-107`). Repository search: no `test_debug_transport*.py`; runner tests monkeypatch `RunnerDebugTransportClient` (`tests/unit/runner/test_debug_runner.py`). Session tests mock at the protocol payload layer only (`tests/unit/debug/test_debug_session.py`).
- **Code-judo alternative:** Thin `DebugTransportServer` / `RunnerDebugTransportClient` integration over loopback with a `FakeBlockingReader` for unit layer; one `@pytest.mark.integration` happy-path connect → hello → event → command → close.
- **Suggested remediation:** Add `tests/unit/debug/test_debug_transport.py` covering: reject wrong protocol/token, idempotent `close`, `send_command` when disconnected, read-thread error invokes `on_error` once. Risk-first gate satisfied: subprocess/socket boundary + threading + irreversible close.
- **Tests that would prove fix:** (This finding *is* the test gap — list cases above as the initial suite scope.)
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-02-6 — `apply_protocol_message` silently drops unknown kinds and events

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_session.py:33-49` — only `event`, `response`, and `hello` are handled; any other `kind` is a no-op with no `last_message` or error surface. `_apply_event_payload` (`:64-98`) and `_apply_response_payload` (`:100-146`) use early-return chains with no default branch — unknown `event`/`command` names leave prior state untouched.
- **Code-judo alternative:** Typed dispatch table (`kind → handler`) with an explicit `_record_protocol_skew(kind, name)` that sets `last_message` to a visible warning. Fail closed in debug builds/tests when an unrecognized `kind` arrives.
- **Suggested remediation:** Add `else` branches that log and set a diagnostic `last_message`; optionally increment a session counter the shell can show in the debug output panel. Coordinate with protocol version bumps in TN-DEBUG-01.
- **Tests that would prove fix:** Unit test: unknown `kind` and unknown `event` leave `execution_state` unchanged **and** set a non-empty diagnostic message (once implemented).
- **Handoff overlap:** none

---

### TN-DEBUG-02-7 — Mutable `DebugSession.state` bypasses the reducer boundary

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_session.py:29-31` — `@property def state` returns the live `DebugSessionState` object. Tests mutate directly: `tests/unit/debug/test_debug_session.py:174-176` assigns `session.state.frames`, `variables_by_reference`, `scopes` before `mark_exited()`. Any shell code can desync transport-driven state by writing fields without going through `apply_protocol_message`.
- **Code-judo alternative:** Expose `state` as a read-only snapshot (`dataclasses.replace` or frozen view) and keep `_state` private; mutations only via `apply_protocol_message`, `mark_exited`, and explicit test helpers (`DebugSession._testing_reset()` if needed).
- **Suggested remediation:** Return a copy or frozen snapshot from `state`; or document and enforce (via pyright protocol) that only the coordinator may touch `_state`. Prefer mechanical enforcement over convention.
- **Tests that would prove fix:** Unit test: external assignment to a returned snapshot does not alter the next `apply_protocol_message` outcome (once snapshotting is in place).
- **Handoff overlap:** shell-wave-1-followup

---

### TN-DEBUG-02-8 — `select_frame` merges scope variables without evicting stale references

- **Persona:** TN-DEBUG-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_session.py:118-122` — successful `select_frame` response calls `variables_by_reference.update(...)` without removing references from the previous frame. `_sync_selected_scope_variables` (`:148-156`) displays the first scope in list order that has cached variables, not necessarily the scope matching `selected_frame_id`.
- **Code-judo alternative:** On frame change, replace `variables_by_reference` with the response payload only (same as `stopped` does for a full snapshot), or track `active_references: frozenset[int]` and prune on selection change.
- **Suggested remediation:** Align `select_frame` with `stopped` semantics: clear then populate, or use assignment instead of `update`. Scope sync should prefer the first **locals** scope or match runner's `selected_frame_id` contract.
- **Tests that would prove fix:** Unit test: frame A locals ref 7 → select frame B locals ref 9 → assert ref 7 absent from `variables_by_reference` and `variables` shows frame B locals only.
- **Handoff overlap:** none

---

### TN-DEBUG-02-9 — `mark_exited` partial reset leaves selection IDs and watch cache

- **Persona:** TN-DEBUG-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/debug/debug_session.py:51-61` — clears threads/frames/scopes/variables/`variables_by_reference`/`exception_info` but retains `selected_thread_id`, `selected_frame_id`, `watch_results`, `breakpoints`, and `exception_policy`. `DebugSessionState.apply_event` for `exited` (`app/debug/debug_models.py:174-176`) does not reset selection fields.
- **Code-judo alternative:** Single `_reset_inspector_fields(*, keep_breakpoints: bool, keep_watches: bool)` shared by `mark_exited`, `continued`, and `session_ended` paths with explicit policy per field group.
- **Suggested remediation:** Zero selection IDs on exit; decide whether watch results and breakpoints should survive session end (document in `DebugSessionState` docstring) and test that policy.
- **Tests that would prove fix:** Extend `test_debug_session_mark_exited_clears_inspector_state` to assert `selected_frame_id == 0` and document expected `watch_results` behavior.
- **Handoff overlap:** none

---

### TN-DEBUG-02-10 — Integration test applies session updates off the UI-thread contract

- **Persona:** TN-DEBUG-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/integration/debug/test_debug_session_integration.py:71-74` — `_feed_events()` calls `session.apply_protocol_message` from the test thread while `RunService` delivers debug payloads via `on_event=events.append` synchronously from the transport read thread (`app/run/run_service.py:234-244` with no queue in this test harness). Production marshals through `MainWindow._run_event_queue` (`app/shell/main_window.py:2843-2964`).
- **Code-judo alternative:** Integration test enqueues through the same coordinator path (or a test double queue + drain function) the shell uses, so threading assumptions match production.
- **Suggested remediation:** Refactor test helper to drain events on one thread only, or mark test as exercising reducer logic only (not concurrency) in a docstring and add a separate threaded transport integration test (see TN-DEBUG-02-5).
- **Tests that would prove fix:** (Meta — fix is to align harness with production queue semantics.)
- **Handoff overlap:** none
