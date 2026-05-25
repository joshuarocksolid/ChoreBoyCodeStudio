# TN-RUNNER-02 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUNNER-02  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/runner/repl_control.py` (90 LOC), `app/runner/repl_protocol.py` (99 LOC), `app/runner/repl_completion.py` (288 LOC). Cross-read: `app/shell/repl_session_manager.py`, `app/runner/runner_main.py` (`_run_interactive_repl`), `docs/code review/shell-wave-1/_findings/TN-SHELL-MW-09.md`, `docs/code review/shell-wave-1/_findings/TN-SHELL-INTEG.md` (CC-01), `tests/unit/runner/test_repl_completion.py`, `tests/unit/shell/test_repl_session_manager.py`.

---

## Executive verdict

**Not thermo-clean.** The REPL sidecar is small (~477 LOC across three modules) and correctly keeps live namespace inspection in the runner process, but the **process-boundary contract is half-formed**: wire messages are loose dicts with no protocol-version handshake, `ReplControlConfig.protocol` is stored in the manifest and never enforced, and **completion degradation metadata does not flow** when Jedi fails or runtime `eval`/`getattr` fallback runs — contradicting ARCHITECTURE §14.1A and the editor completion broker pattern. **CC-01 agent-debug slop is cleared** in `repl_completion.py` (no `#region agent log`, no hardcoded `.cursor` paths at baseline). Dominant risks: (1) **unsynchronized shared-namespace access** between `console.interact()` and `ThreadingTCPServer` completion threads; (2) **silent fallback** that presents runtime-inspection results without envelope-level degradation; (3) **zero tests** on `repl_control.py` / `repl_protocol.py` transport boundary. Would not extend the sidecar (resolve, signature help) until typed envelopes and degradation honesty land.

---

### TN-RUNNER-02-1 — Shared REPL namespace accessed concurrently without a lock

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/runner_main.py:106-125` — `_run_interactive_repl` builds one `namespace` dict, passes it to `_QuietConsole(locals=namespace)` on the **main thread**, and to `ReplControlServer(..., namespace=namespace)` which starts `socketserver.ThreadingTCPServer` (`repl_control.py:45-48`). `ReplCompletionService.complete` reads/evaluates against `self._namespace` (`repl_completion.py:68,117-118,152`) while the REPL main thread may be executing user statements that mutate the same dict. No lock, snapshot, or queue serializes metadata work behind REPL execution.
- **Code-judo alternative:** Single-threaded completion queue drained on the REPL thread (bdb-style), or a `threading.RLock` around namespace reads in completion plus documented invariant that completion is best-effort during execution. Simplest v1 move: reject or degrade completions while the console is mid-`runsource` instead of overlapping `eval`/`dir`.
- **Suggested remediation:** R-run-2 — pick one concurrency model and document it in `repl_control.py` module docstring; align with ARCHITECTURE §14.1A health/timeout semantics.
- **Tests that would prove fix:** Unit test with a namespace mutator thread + completion thread asserting no `RuntimeError: dictionary changed size during iteration` (or explicit `degradation_reason="repl_busy"` when serialized).
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-2 — Manifest `protocol` field is write-only; wire contract never validated

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** `ReplControlConfig.protocol` is required at manifest parse (`app/run/run_manifest.py:319-328`) and set to `REPL_CONTROL_PROTOCOL` in `repl_session_manager.py:166-167`. `ReplControlServer` and `_handle_request` (`repl_control.py:64-89`) never read `config.protocol` or compare against `repl_protocol.REPL_CONTROL_PROTOCOL`. Client requests carry `session_token` and `method` only (`repl_session_manager.py:125-133`) — no protocol/version field on the wire. Contrast `debug_protocol.build_hello_message` which includes `"protocol": DEBUG_PROTOCOL_NAME`.
- **Code-judo alternative:** First message on connect is a typed `hello`/`complete` envelope with mandatory `protocol` field; server rejects mismatch before touching namespace. One constant, one validation site — delete duplicate string in manifest-only storage or derive server expectation from config with assert at startup.
- **Suggested remediation:** Add `build_repl_request` / `parse_repl_request` in `repl_protocol.py`; server validates `payload["protocol"] == config.protocol` before token check.
- **Tests that would prove fix:** Unit test: wrong protocol → `{"ok": false, "error": ...}` without invoking completion; manifest round-trip unchanged.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-3 — Ad-hoc dict protocol at the runner/shell boundary

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** Shell client builds a raw dict (`repl_session_manager.py:125-133`); runner parses with `payload.get("method")`, `payload.get("line_buffer")`, etc. (`repl_control.py:73-82`). `ReplCompletionRequest` exists server-side only (`repl_completion.py:24-32`) — not used on the wire. Response shape is `{"ok": bool, "result"|"error"}` without `kind`/`command_id` discipline. `repl_protocol.py` serializes `CompletionEnvelope` items but not requests/responses. Parallel typed pattern: `app/debug/debug_protocol.py` (`build_debug_command`, `build_debug_response`, decode validation).
- **Code-judo alternative:** `repl_protocol.py` owns all envelopes: `build_complete_request(...)`, `build_complete_response(...)`, `parse_repl_control_message(line) -> ReplControlMessage` union. Shell and runner import the same builders — delete duplicated field names and magic `"complete"` / `"ping"` strings from orchestrators.
- **Suggested remediation:** Hard cutover — no compatibility shim for old dict shape (loopback-only channel).
- **Tests that would prove fix:** Round-trip tests in `tests/unit/runner/test_repl_protocol.py` for request/response builders; fake-socket test through `_handle_request`.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-4 — Completion fallback never sets `degradation_reason` (honesty gap)

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** `ReplCompletionService.complete` (`repl_completion.py:41-61`) catches Jedi failure with debug log only (`47-49`), then returns fallback items with **empty** `degradation_reason`. Fallback path uses `runtime_inspection` confidence (`57-61`) but no envelope-level reason. ARCHITECTURE §14.1A: *"any fallback that uses `dir()`, descriptors, or `__getattr__` must surface its side-effect risk instead of presenting the result as purely static analysis."* Editor analogue sets `degradation_reason=COMPLETION_DEGRADATION_SEMANTIC_ENGINE_ERROR` on semantic failure (`app/intelligence/completion_broker.py:129-132`). Shell surfaces reasons via status bar (`python_console_workflow.py:95-98`); empty reason → **silent degradation** when Jedi fails or only fallback items return.
- **Code-judo alternative:** Central degradation constants (e.g. `repl_jedi_unavailable`, `repl_runtime_inspection`) set on envelope whenever Jedi is skipped or `_complete_with_fallback` / `_complete_dotted_expression` supplies items; propagate through `envelope_to_dict` (already has field at `repl_protocol.py:55`).
- **Suggested remediation:** Tag envelope in `complete()` when `jedi_items` is empty after exception or when fallback path used; optionally when any item has `side_effect_risk != "none"`.
- **Tests that would prove fix:** Unit test: force Jedi import/raise → envelope has non-empty `degradation_reason`; workflow test asserts status-bar message (existing pattern in `test_python_console_workflow.py:153`).
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUNNER-02-5 — ARCHITECTURE §14.1A surface area partially implemented

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** Implemented methods in `_handle_request` (`repl_control.py:74-87`): `complete`, `ping` only. ARCHITECTURE §14.1A lists completion-item **resolve**, **signature help**, and explicit **health/timeout/shutdown** handling. No resolve/signature handlers; shutdown is implicit via `ReplControlServer.stop()` in `runner_main.py:124-125` when REPL exits — editor cannot drain in-flight completion before stop. `ping` returns `{"status": "ready"}` but shell never calls it (`repl_session_manager.py` has no health probe).
- **Code-judo alternative:** Either narrow ARCHITECTURE to v1 scope explicitly, or add typed stubs that return `degradation_reason="not_implemented"` so clients do not assume parity with editor intelligence. If v1 is completion-only, delete ping from protocol doc and document health as TCP connect failure only.
- **Suggested remediation:** Product/architecture alignment pass before adding features; implement resolve/signature on shared protocol module, not as a third ad-hoc method string.
- **Tests that would prove fix:** Contract test listing supported methods; unsupported method returns stable error code (today: `Unsupported REPL control method` string at `repl_control.py:89`).
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-6 — Broad `except Exception` returns raw exception text to the editor client

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** `repl_control.py:41-42` — handler wraps entire read/parse/dispatch in `except Exception as exc: response_payload = {"ok": False, "error": str(exc)}`. Internal failures (JSON parse, unexpected bugs) become user-visible strings on the shell side (`repl_session_manager.py:144` passes through as `degradation_reason`). Contrast debug transport which routes failures through structured error handling (see TN-RUNNER-03-3/04 on debug path).
- **Code-judo alternative:** Catch expected validation errors → stable error codes; log unexpected with `_logger.exception` and return generic `"repl_internal_error"`. Never forward `str(exc)` for non-validation failures.
- **Suggested remediation:** Split `_handle_request` validation from dispatch; narrow handler `except` to transport parse errors only.
- **Tests that would prove fix:** Unit test: raise inside `completion_service.complete` → client receives stable code, not traceback substring.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-7 — Dotted fallback uses `eval()` with per-item risk tags only

- **Persona:** TN-RUNNER-02
- **Severity:** STRUCTURAL
- **Evidence:** `repl_completion.py:151-177` — `_complete_dotted_expression` calls `eval(expression, {"__builtins__": builtins}, self._namespace)` then `getattr` per member. Items tag `side_effect_risk="possible_descriptor_or_getattr"` (`176`) but successful Jedi path returns `side_effect_risk="low"` (`94`) even though Jedi Interpreter also executes in live namespace. Envelope never sets degradation when eval/getattr path used (`57-61`). User cannot distinguish semantic Jedi vs runtime inspection at request level — only per-item metadata if UI reads it (console popup may not).
- **Code-judo alternative:** Set envelope `degradation_reason` and/or `confidence` downgrade whenever fallback path runs; unify Jedi and fallback under one "live runtime" policy object that decides labeling. Avoid `eval` where `jedi.Interpreter` already failed — return empty with explicit reason.
- **Suggested remediation:** Pair with TN-RUNNER-02-4; document that console completion is always live-runtime, not static analysis.
- **Tests that would prove fix:** Unit test: dotted expr with failing Jedi → items from eval path carry envelope degradation; item-level risk preserved.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUNNER-02-8 — Transport boundary untested; TASKS integration path missing

- **Persona:** TN-RUNNER-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/runner/test_repl_completion.py` exercises `ReplCompletionService` in-process only (2 tests). `tests/unit/shell/test_repl_session_manager.py` mocks `_launch` / supervisor — **no** `complete()` socket test. No `tests/unit/runner/test_repl_control.py` or `test_repl_protocol.py`. `docs/TASKS.md:1555-1558` references `tests/integration/run/test_repl_completion_integration.py` — **file absent** at baseline.
- **Code-judo alternative:** One unit module tests JSON-line framing, token rejection, and envelope round-trip without threading; one slow integration test optional under risk-first gate after TN-RUNNER-02-1 concurrency fix.
- **Suggested remediation:** Add protocol/control tests when fixing TN-RUNNER-02-2/03; create or remove TASKS reference to missing integration file.
- **Tests that would prove fix:** `test_repl_control_rejects_bad_token`; `test_envelope_round_trip_preserves_replacement_range`.
- **Handoff overlap:** none

---

### TN-RUNNER-02-9 — `CompletionEnvelope` wire subset drops request-level metadata fields

- **Persona:** TN-RUNNER-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `envelope_to_dict` (`repl_protocol.py:50-58`) serializes `items`, `degradation_reason`, `source`, `confidence` only. `envelope_from_dict` (`61-75`) ignores `source_phase`, `request_id`, `buffer_revision`, `is_incomplete`, `latency_breakdown` present on `CompletionItem` model (`app/intelligence/completion_models.py:55-70`). `completion_item_to_dict` uses `asdict(item)` but `completion_item_from_dict` manually maps a subset — fields like `item_id`, `resolve_provider` are lost on round-trip.
- **Code-judo alternative:** Explicit REPL wire DTO (frozen dataclass) decoupled from editor `CompletionEnvelope` — map once at boundary instead of partial asdict/from_dict mirroring.
- **Suggested remediation:** When adding resolve (TN-RUNNER-02-5), define v1 wire schema rather than extending ad-hoc dict.
- **Tests that would prove fix:** Round-trip test documents intentional field loss or asserts full parity for REPL-needed fields.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-02-10 — `except BaseException` on Jedi path swallows non-Exception signals

- **Persona:** TN-RUNNER-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `repl_completion.py:47` — `except BaseException as exc` around `_complete_with_jedi`. Catches `KeyboardInterrupt` / `SystemExit` in completion worker threads, converting them into empty Jedi results instead of propagating. Unlikely on hot path but violates usual "catch Exception" guard for service code.
- **Code-judo alternative:** `except Exception` only; let base exceptions propagate to thread boundary and fail the request with stable error.
- **Suggested remediation:** Narrow except when touching TN-RUNNER-02-4 degradation work.
- **Tests that would prove fix:** Optional unit test with mocked Jedi raising `RuntimeError` vs ensuring `KeyboardInterrupt` is not swallowed (mock).
- **Handoff overlap:** none

---

## CC-01 cross-read (agent logging)

**Verified at baseline:** `app/runner/repl_completion.py` contains **no** `#region agent log`, `_agent_log_*`, or hardcoded `.cursor/debug-0b96d3.log` paths. TN-SHELL-INTEG **CC-01** cited this file historically; shell-wave-1 fix handoff marks CC-01 removed from `repl_completion.py`. Remaining CC-01 scope is shell-only (`python_console_widget.py`, `main_window.py`) — **not a TN-RUNNER-02 finding**.

---

## Positive signals

| Signal | Evidence |
|--------|----------|
| Process boundary respected | Live namespace stays in runner; shell uses TCP loopback + session token (`repl_session_manager.py:136-148`) |
| Small, scannable modules | 90 + 99 + 288 LOC — well under 1k decomposition threshold |
| Session token gate | `_handle_request` rejects bad token before completion (`repl_control.py:70-71`) |
| Loopback-only bind | `ReplControlConfig.host` defaults to `127.0.0.1` (`repl_session_manager.py:168`) |
| REPL lifecycle pairing | `control_server.start()` / `stop()` paired with `console.interact()` in `finally` (`runner_main.py:114-125`) |
| Shared completion vocabulary | Reuses `CompletionItem` / `CompletionEnvelope` from intelligence models |
| CC-01 cleared on runner path | No agent-debug slop in primary slice files |

---

## Inspection summary

| Area | Files read | Outcome |
|------|------------|---------|
| Primary | `repl_control.py`, `repl_protocol.py`, `repl_completion.py` | 10 findings (0 BLOCKER, 7 STRUCTURAL, 3 NICE-TO-HAVE) |
| Shell seam | `repl_session_manager.py` | Cross-read for client protocol + degradation surfacing |
| Bootstrap | `runner_main.py` | Concurrency + lifecycle context |
| Tests | `test_repl_completion.py`, `test_repl_session_manager.py` | Service-only coverage; no transport tests |
| Shell wave 1 | TN-SHELL-MW-09, TN-SHELL-INTEG CC-01 | CC-01 cleared here; completion threading/degradation UX overlap MW-09-4 |
