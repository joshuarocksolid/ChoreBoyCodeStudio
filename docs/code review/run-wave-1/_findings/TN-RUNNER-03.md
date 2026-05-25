# TN-RUNNER-03 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUNNER-03  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/runner/debug_runner.py` (803 LOC). Cross-read: `tests/unit/runner/test_debug_runner.py`, `tests/runtime_parity/debug/test_debug_engine_runtime.py`, `app/debug/debug_transport.py`, `app/debug/debug_protocol.py`, `docs/deslop/AUDIT_app.md` §5.2 (stale — do not treat as current).

---

## Executive verdict

**Not thermo-clean.** `debug_runner.py` is an 803-line god module whose private `_RunnerDebugHost` (~610 LOC) fuses the bdb trace engine, socket transport command loop, breakpoint verification, variable serialization, and expression evaluation into one class. The process boundary is respected — debug target code and `eval`/`safe_eval` run only in the runner subprocess — and frozen-manifest breakpoint updates correctly use `dataclasses.replace`. Dominant risks are operational: a paused runner can **hang indefinitely** when the editor-side transport closes without a `disconnect` command (read loop exits silently), and **write failures during pause** are not routed through the transport-error disconnect path, so bdb callbacks can raise mid-trace. Decomposition is overdue before this module crosses the 1k-line hard stop in `_findings/_README.md`. Would not approve new debug-runner features until transport failure semantics and module splits land.

---

### TN-RUNNER-03-1 — 803 LOC god module at decomposition threshold

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py` — 803 LOC total. `_RunnerDebugHost` spans lines 71–680 (~610 LOC) and owns transport wiring (`__init__`, `connect`, `close`, `_handle_transport_message`), bdb pause orchestration (`pause_at_frame`, `_pause_loop`), command handlers (lines 250–401), payload builders (416–522), breakpoint application (524–591), variable serialization (608–661), and registries (663–676). `StructuredBdbDebugger` (29–68) and module helpers (717–803) are the only separated seams.
- **Code-judo alternative:** Hard cutover split aligned with `app/debug/` ownership: `runner_debug_engine.py` (`StructuredBdbDebugger` + trace bootstrap in `run_debug_session`), `runner_debug_command_loop.py` (`_pause_loop` + command handlers), `runner_debug_inspector.py` (frame/scope/variable serialization + registries), `runner_debug_breakpoints.py` (`_apply_breakpoints`, `_parse_breakpoints`). Host becomes a thin coordinator (~120 LOC) wiring transport callbacks to the loop.
- **Suggested remediation:** R-run-2 — decompose before adding features; net-zero LOC growth on `debug_runner.py` (re-export or delete file after cutover). Target each extracted module under 300 LOC.
- **Tests that would prove fix:** Existing `tests/unit/runner/test_debug_runner.py` passes unchanged imports via `run_debug_session`; optional import-smoke tests for new modules.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-2 — bdb engine, transport I/O, and eval share one host class

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py:71-95` — `_RunnerDebugHost.__init__` constructs `RunnerDebugTransportClient`, `StructuredBdbDebugger`, command queue, and registries in one object. `pause_at_frame` (139–152) sends transport events then blocks on `_command_queue.get()` inside the bdb trace callback. `_handle_evaluate` (306–366) calls `safe_evaluate_expression` / raw `eval` in the same class that owns `dispatch_line` stop reasons. Transport read thread (`debug_transport.py:230-241`) invokes `_handle_transport_message` on the host while bdb runs on the main traced thread — concurrency boundary is implicit.
- **Code-judo alternative:** Separate **engine** (bdb stop reasons only), **transport adapter** (enqueue/dequeue commands, send events/responses), and **inspector service** (eval + variable expansion). Host holds references; `_pause_loop` depends on an interface, not six concerns in one type.
- **Suggested remediation:** Extract alongside TN-RUNNER-03-1; document thread model (read thread produces, bdb thread consumes) in module docstring of the command loop.
- **Tests that would prove fix:** Unit test with fake transport asserting command dispatch does not import bdb; eval test unchanged.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-3 — Editor transport EOF leaves runner paused forever (zombie subprocess)

- **Persona:** TN-RUNNER-03
- **Severity:** BLOCKER
- **Evidence:** `app/debug/debug_transport.py:230-241` — `RunnerDebugTransportClient._read_loop` exits the `for line in resources.reader` loop on peer EOF **without** calling `_on_error`. `app/runner/debug_runner.py:181-182` — `_pause_loop` blocks on `self._command_queue.get()` with no timeout. `app/runner/debug_runner.py:412-414` — `_handle_transport_error` (which injects synthetic `disconnect`) runs only when the read loop raises. If the editor closes the socket or crashes while the runner is paused, the traced thread never unblocks, `run_debug_session` never returns, and `runner_main.execute_manifest` keeps the runner process alive until SIGKILL. ARCHITECTURE §13.4A: *"A broken debug transport must fail the debug session clearly."*
- **Code-judo alternative:** On read-loop exit while not `_close_event`, always invoke `_on_error("transport closed")` (or call host `on_transport_lost()`). Command loop uses `queue.get(timeout=…)` and treats timeout + dead transport as `disconnect`. `ProcessSupervisor` stop path should not rely on cooperative runner exit alone.
- **Suggested remediation:** Fix in `RunnerDebugTransportClient._read_loop` (TN-DEBUG-02 overlap) plus defensive timeout in `_pause_loop`. Hard cutover — no stdout marker fallback.
- **Tests that would prove fix:** Unit test: fake transport closes reader after `stopped` → runner exits with `RUN_EXIT_TERMINATED_BY_USER` or explicit transport-failure code within bounded time. Integration test: kill editor-side transport mid-pause → supervisor observes exit.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-4 — Transport write failures during pause bypass error handler

- **Persona:** TN-RUNNER-03
- **Severity:** BLOCKER
- **Evidence:** `app/debug/debug_transport.py:208-217` — `send_message` raises `RuntimeError("Runner debug transport is not connected.")` on write with no `_on_error` callback. `app/runner/debug_runner.py:147-148` — `pause_at_frame` calls `self._transport.send_message(build_debug_event("stopped", payload))` **outside** any try/except before entering `_pause_loop`. Same pattern on every `build_debug_response` inside `_pause_loop` (188–247). Only `_handle_transport_error` (412–414) sets `_transport_failed` and enqueues disconnect — and it is wired exclusively from the read thread's `except Exception` path, not from write failures.
- **Code-judo alternative:** Central `send_event` / `send_response` helpers that catch transport errors, log, invoke `on_transport_lost()`, and call `debugger.set_quit()`. Align runner behavior with ARCHITECTURE §13.4A clear-failure requirement.
- **Suggested remediation:** Shared transport wrapper used by runner host; write failure == read failure == session end.
- **Tests that would prove fix:** Fake transport whose `send_message` raises after first `stopped` → session terminates cleanly, traces cleared, `session_ended` best-effort sent or skipped.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-5 — `_transport_failed` is write-only dead state

- **Persona:** TN-RUNNER-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/debug_runner.py:92` — `self._transport_failed = False` in `__init__`. `app/runner/debug_runner.py:413` — set to `True` in `_handle_transport_error`. No read anywhere in `app/runner/debug_runner.py` or the repo (`rg _transport_failed` hits only these two lines).
- **Code-judo alternative:** Either consume the flag (skip further sends, force quit in pause loop) or delete it when TN-RUNNER-03-4 lands.
- **Suggested remediation:** Remove vestigial field or wire it into send helpers as idempotent "session dead" guard.
- **Tests that would prove fix:** N/A if field removed; if kept, assert no further transport sends after error.
- **Handoff overlap:** none

---

### TN-RUNNER-03-6 — Fragile `bdb.Breakpoint.bplist` access for hit conditions

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py:562-565` — after `debugger.set_break`, hit count is applied via private stdlib structure: `active_breakpoint = bdb.Breakpoint.bplist[canonical_file, breakpoint.line_number][-1]` then `active_breakpoint.ignore = breakpoint.hit_condition - 1`. This reaches into bdb internals not covered by the public `Bdb` API; Python version or bdb refactors can break silently.
- **Code-judo alternative:** Subclass `bdb.Breakpoint` or wrap `set_break` in a small adapter that sets `ignore` at creation time; or document hit-condition as editor-verified-only and push ignore logic into a dedicated helper covered by integration tests.
- **Suggested remediation:** Extract `apply_hit_condition(debugger, breakpoint)` with explicit error reporting into `verification_message`; avoid raw `bplist` access from the god host.
- **Tests that would prove fix:** Unit/integration test: breakpoint with `hit_condition=3` stops on third hit (currently untested in `test_debug_runner.py`).
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-7 — Stopped payload replays stale breakpoint verification from manifest

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py:437` — `_build_pause_payload` includes `"breakpoints": self._breakpoint_payloads(self._manifest.breakpoints)`. `_breakpoint_payloads` (593–606) reads `breakpoint.verified` and `breakpoint.verification_message` from the **manifest model**, not from the live `_apply_breakpoints` results emitted at connect (122–126) or after `update_breakpoints`. After connect, verified state lives only in transport events; manifest entries retain `verified=False` defaults (`DebugBreakpoint` in `app/debug/debug_models.py:55-56`).
- **Code-judo alternative:** Host caches last verified breakpoint payloads from `_apply_breakpoints` return value; `_build_pause_payload` uses that cache. Single SSOT for verified state during session.
- **Suggested remediation:** Store `self._verified_breakpoints: list[dict[str, object]]` updated whenever `_apply_breakpoints` runs; pause/stop events reference cache.
- **Tests that would prove fix:** Unit test: invalid breakpoint at connect → first `stopped` event lists `verified: False` with message (today would incorrectly show manifest defaults).
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUNNER-03-8 — Duplicate breakpoint parsing at runner transport boundary

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py:730-753` — module-local `_parse_breakpoints` rebuilds `DebugBreakpoint` from loose dicts. Parallel parsers exist in `app/run/run_manifest.py` (manifest load), `app/debug/debug_session.py:277`, and `app/debug/debug_breakpoints.build_breakpoint`. Runner copy uses `_parse_int(...) or None` for hit_condition (748), diverging from `run_manifest._parse_optional_positive_int` and `debug_breakpoints.build_breakpoint` normalization (`hit_condition <= 0` → None).
- **Code-judo alternative:** Import `build_breakpoint` / shared `parse_breakpoint_entry` from `app/debug/debug_breakpoints.py`; one normalization path for editor and runner.
- **Suggested remediation:** Delete `_parse_breakpoints`; call shared helper in `_handle_update_breakpoints`.
- **Tests that would prove fix:** Parametrized test shared with debug_breakpoints; hit_condition=0 rejected consistently.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-9 — Broad `except Exception` on session teardown hides close failures

- **Persona:** TN-RUNNER-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/debug_runner.py:129-136` — `close()` wraps `session_ended` send in `except Exception:` with debug-level log only. Acceptable for best-effort teardown, but indistinguishable from logic bugs without structured close reason. `_safe_repr` (796-800) and `_apply_breakpoints` (578-590) also catch broad `Exception` — latter is justified (per-breakpoint verification); former is justified (repr safety).
- **Code-judo alternative:** Catch `OSError`, `RuntimeError` (transport not connected) only; let unexpected exceptions propagate during development or re-raise after log.
- **Suggested remediation:** Narrow exception types on `close()` once transport send helper exists (TN-RUNNER-03-4).
- **Tests that would prove fix:** Fake transport raises `RuntimeError` on close → session still closes socket, no hang.
- **Handoff overlap:** none

---

### TN-RUNNER-03-10 — Private bdb `_set_stopinfo` bootstrap escape hatch

- **Persona:** TN-RUNNER-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/debug_runner.py:688-694` — `run_debug_session` calls `cast(Any, host.debugger)._set_stopinfo(None, None, -1)` with `# noqa: SLF001` to avoid stopping on the first traceable line. Depends on CPython bdb private API; no abstraction boundary if bdb internals change.
- **Code-judo alternative:** Subclass `StructuredBdbDebugger` with a supported override (e.g. custom `set_trace` / `breakpoints` timing) or document and isolate in `runner_debug_engine.py` as the sole place allowed to touch bdb privates.
- **Suggested remediation:** Move SLF001 block into engine module with comment linking to bdb version assumptions; runtime_parity test asserts first-line behavior.
- **Tests that would prove fix:** Unit test already implies no stop before user breakpoint (`test_run_debug_session_first_pause_targets_user_breakpoint`); add explicit assert no `stopped` before line 2 execution.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-03-11 — Runtime parity tests do not exercise runner debug engine

- **Persona:** TN-RUNNER-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/runtime_parity/debug/test_debug_engine_runtime.py` — covers `probe_debug_runtime`, stdlib `bdb` import, and `debug_models` import only. No AppRun invocation of `run_debug_session` or transport handshake. Unit tests (`test_debug_runner.py`) mock `RunnerDebugTransportClient` entirely; integration coverage is one slow test (`tests/integration/debug/test_breakpoint_stepping_flow.py`) at `RunService` level, not runner-isolated.
- **Code-judo alternative:** One runtime_parity test launching runner debug mode with loopback transport under AppRun (skip when no display/AppRun), or mark existing integration test with `runtime_parity` when run through AppRun shard.
- **Suggested remediation:** Add parity test only if risk-first gate satisfied (transport EOF / zombie path in TN-RUNNER-03-3 justifies integration test after fix).
- **Tests that would prove fix:** `test_debug_runner_transport_loss_exits` under `runtime_parity` marker post-fix.
- **Handoff overlap:** none

---

### TN-RUNNER-03-12 — Unrelated output-bridge tests live in debug runner test module

- **Persona:** TN-RUNNER-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/runner/test_debug_runner.py:362-401` — `test_redirect_output_to_log_mirrors_stdout_and_stderr` and `test_redirect_output_to_log_falls_back_when_log_file_open_fails` import `output_bridge`, not `debug_runner`. Obscures test ownership for TN-RUNNER-01.
- **Code-judo alternative:** Move to `tests/unit/runner/test_output_bridge.py` (or TN-RUNNER-01 scope file).
- **Suggested remediation:** Test file hygiene during runner package cleanup; no behavior change.
- **Tests that would prove fix:** pytest collection paths unchanged after move.
- **Handoff overlap:** R-run-2

---

## Positive signals

| Signal | Evidence |
|--------|----------|
| Process boundary preserved | `run_debug_session` runs under `runner_main.execute_manifest` (`app/runner/runner_main.py:82-83`); editor never imports target project code for debug eval |
| Frozen manifest respected | `app/runner/debug_runner.py:370` — `self._manifest = replace(self._manifest, breakpoints=breakpoints)`; test confirms caller manifest unchanged (`test_run_debug_session_updates_breakpoints_without_mutating_manifest`) |
| Safe eval default | `_handle_evaluate` defaults to `safe_evaluate_expression`; unsafe requires explicit flag (`333-337`) |
| Thin bdb wrapper | `StructuredBdbDebugger` delegates stop decisions to host without transport knowledge |
| Dedicated transport channel | Uses `RunnerDebugTransportClient` + `debug_protocol` envelopes; no stdout marker parsing in this module |
| Core paths tested | Breakpoint pause, invalid BP verification, safe/unsafe eval, uncaught-exception pause covered with fake transport |

---

## Stale audit note

`docs/deslop/AUDIT_app.md` §5.2 item 8 claims in-place mutation `self._manifest.breakpoints[:] = breakpoints` at line 350. At baseline `24a7cb37`, line 370 uses `dataclasses.replace` — **finding is obsolete**; do not reintroduce in-place mutation.

---

## Inspection summary

| Area | Files read | Outcome |
|------|------------|---------|
| Primary | `debug_runner.py` (803 LOC, full) | 12 findings (2 BLOCKER, 7 STRUCTURAL, 3 NICE-TO-HAVE) |
| Unit tests | `test_debug_runner.py` | Good fake-transport coverage; gaps on transport loss, stepping, hit conditions |
| Runtime parity | `test_debug_engine_runtime.py` | No runner debug session coverage |
| Transport | `debug_transport.py` | EOF silent exit drives TN-RUNNER-03-3 |
| Protocol | `debug_protocol.py` | Clean envelopes; no issues in this slice |
| Integration | `test_breakpoint_stepping_flow.py` (cross-read) | End-to-end step_over exists at RunService layer |
