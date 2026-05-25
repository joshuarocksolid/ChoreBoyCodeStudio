# TN-DEBUG-01 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-DEBUG-01
**Date:** 2026-05-25
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`
**Scope:** `app/debug/debug_models.py` (184 LOC), `app/debug/debug_breakpoints.py` (91 LOC), `app/debug/debug_protocol.py` (80 LOC), `app/debug/debug_command_service.py` (74 LOC), `app/debug/safe_eval.py` (80 LOC), `app/debug/debug_runtime_probe.py` (68 LOC). Cross-read: `tests/unit/debug/test_debug_models.py`, `tests/unit/debug/test_debug_command_service.py`, `tests/unit/debug/test_safe_eval.py`, `app/debug/debug_session.py`, `app/run/run_manifest.py`, `app/runner/debug_runner.py`, `docs/deslop/AUDIT_app_remaining_handoff.md` R1, `docs/code review/shell-wave-1/_findings/TN-SHELL-DEBUG.md` (breakpoint helper underuse).

---

## Executive verdict

**Not thermo-clean.** The slice is modest in size (577 LOC) and the layering intent is sound — frozen models, breakpoint helpers, JSON-line protocol builders, command factories, safe eval, runtime probe — but the **shared contract is fragmented**. Breakpoint wire shapes are hand-built in at least four places while `breakpoint_to_manifest_payload` sits unused; inbound breakpoint parsing is triplicated outside `debug_breakpoints.py` with divergent hit-condition rules; and `DebugEvent`/`apply_event()` form a legacy reducer parallel to `DebugSession.apply_protocol_message` with stale comments and wrong `stop_reason` semantics. `debug_protocol.py` correctly reuses `rpc_protocol` for JSON framing but does not own envelope validation beyond a single `kind` check. Dominant risk: the next breakpoint or protocol field will land in the wrong serializer/parser and desync manifest, transport command, runner response, and session state — not a single-file LOC problem.

---

### TN-DEBUG-01-1 — Breakpoint wire format is duplicated four ways with skewed omission rules

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_manifest.py:61-70` — `RunManifest.to_dict()` inlines breakpoint dicts, always emitting `condition` and `hit_condition` (including `None`). `app/debug/debug_command_service.py:52-64` — `update_breakpoints_command` inlines a second shape with the same always-present fields. `app/debug/debug_breakpoints.py:73-91` — `breakpoint_to_manifest_payload` omits empty `condition` and `None`/`<=0` `hit_condition`, supports `runtime_file_path` remapping — **never imported anywhere in the repo**. `app/runner/debug_runner.py:593-606` — `_breakpoint_payloads` adds `verified` and `verification_message` for transport events, again hand-built.
- **Code-judo alternative:** One module owns both directions: `breakpoint_to_wire_dict(breakpoint, *, include_verification: bool, runtime_file_path: str | None)` and `parse_breakpoint_entry(entry) -> DebugBreakpoint | None`. Manifest, command service, runner pause payloads, and session parsers all call the same helpers.
- **Suggested remediation:** Collapse the four serializers into `debug_breakpoints.py`; wire `RunManifest.to_dict()` and `update_breakpoints_command()` through the shared outbound helper; delete inline list comprehensions. Decide one omission policy (prefer omit-empty for transport bandwidth; document in helper docstring).
- **Tests that would prove fix:** Parametrized round-trip: `build_breakpoint` → wire dict → parse → equal model; cases for empty condition, `hit_condition=0`, verified fields on/off.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-2 — `breakpoint_to_manifest_payload` is dead code on the canonical path

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_breakpoints.py:73-91` defines `breakpoint_to_manifest_payload`. Repository search shows **zero call sites** outside the definition. Launch manifest serialization uses `RunManifest.to_dict()` (`app/run/run_manifest.py:61-70`); runtime sync uses `update_breakpoints_command()` (`app/debug/debug_command_service.py:52-64`).
- **Code-judo alternative:** Either wire the helper into both outbound paths (TN-DEBUG-01-1) or delete it in the same hard cutover — dead helpers are worse than no helper because they imply a contract that production does not honor.
- **Suggested remediation:** Hard cutover per repo rules: adopt the helper as SSOT or remove it; do not leave a third dormant shape.
- **Tests that would prove fix:** Import/call coverage from `test_run_manifest.py` and `test_debug_command_service.py` through the shared helper only.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-3 — Inbound breakpoint parsing is triplicated with divergent normalization

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_session.py:259-282` — `_parse_breakpoints` delegates to `build_breakpoint` with `_parse_optional_int` for hit counts (`>0` only). `app/run/run_manifest.py:246-286` — separate `_parse_breakpoints` with strict manifest errors and `_parse_optional_positive_int`. `app/runner/debug_runner.py:730-753` — module-local `_parse_breakpoints` constructs raw `DebugBreakpoint(...)`, uses `_parse_int(...) or None` for hit counts (0 becomes `None`, but negative ints are kept as truthy `or None` failures), skips path normalization, and synthesizes fallback IDs as `"%s:%s" % (file_path, line_number)` instead of `make_breakpoint_id`. All three sit outside `debug_breakpoints.py`.
- **Code-judo alternative:** Export `parse_breakpoint_entry(entry: Mapping[str, object]) -> DebugBreakpoint | None` and `parse_breakpoint_list(raw: object) -> list[DebugBreakpoint]` from `debug_breakpoints.py`; manifest layer wraps parse errors into `_raise_manifest_error`; runner and session call the same entry parser.
- **Suggested remediation:** Move parsing into `debug_breakpoints.py`; delete runner and session private copies (pairs with TN-RUNNER-03-8). Single hit-condition rule: `build_breakpoint` normalization (`<=0` → `None`).
- **Tests that would prove fix:** Shared parametrized parser tests consumed by manifest, session, and runner test modules; assert `hit_condition=0` and missing fields behave identically at all boundaries.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-4 — Breakpoint copy helpers stop at verification; shell/store hand-rebuild frozen models

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_breakpoints.py:53-70` — `update_breakpoint_verification` returns a copy with verification fields changed. `app/shell/debug_control_workflow.py:115-125`, `140-150`, `228-238`, `270-280` — each hand-assembles full `DebugBreakpoint(...)` copying seven fields from `spec`. `app/shell/breakpoint_store.py:86-95` — `remap_paths` rebuilds specs with another seven-field constructor. Shell-wave review already flagged this (`TN-SHELL-DEBUG-4`).
- **Code-judo alternative:** Add `replace_breakpoint(breakpoint, **changes) -> DebugBreakpoint` using `dataclasses.replace`, or small focused helpers (`with_enabled`, `with_condition`, `with_file_path`). Workflow/store methods become one-liners; field additions touch one helper.
- **Suggested remediation:** Extend `debug_breakpoints.py` with immutable update helpers; refactor shell call sites in the R2 sweep. `update_breakpoint_verification` becomes a thin wrapper over `replace_breakpoint`.
- **Tests that would prove fix:** Unit tests on new helpers; existing `test_debug_panel_widget.py` and breakpoint store tests stay green.
- **Handoff overlap:** R1 | shell-wave-1-followup

---

### TN-DEBUG-01-5 — Legacy `DebugEvent` reducer parallels the protocol reducer with stale contract comments

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_models.py:122-127` — `DebugEvent` docstring says editor code aggregates transport updates, but production path is `DebugSession.apply_protocol_message` (`app/debug/debug_session.py:33-49`). Only `mark_exited()` still calls `apply_event()` (`app/debug/debug_session.py:51-55`). Tests name the path explicitly legacy: `test_debug_session_state_applies_legacy_events` (`tests/unit/debug/test_debug_models.py:12`). Handoff R1 item 3 calls out stale comments tied to the deleted stdout-marker parser.
- **Code-judo alternative:** Delete `DebugEvent` and `DebugSessionState.apply_event()` after moving `mark_exited` to set `_state` fields directly (or via a private `_apply_exited()` beside the protocol handlers). One reducer, one comment story.
- **Suggested remediation:** R1 — reword or remove legacy API; if kept for tests only, rename to `_LegacyDebugEvent` / `@pytest.fixture` helper and mark module docstring as test-only shim with removal date.
- **Tests that would prove fix:** `test_debug_session.py` covers exited path through protocol; delete or migrate `test_debug_models.py` legacy tests when API is removed.
- **Handoff overlap:** R1

---

### TN-DEBUG-01-6 — `apply_event()` hardcodes `stop_reason="breakpoint"` for every paused event

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_models.py:168-170` — `if event.event_type == "paused": self.stop_reason = "breakpoint"`. Contrast `DebugSession._apply_event_payload` for `stopped` (`app/debug/debug_session.py:83-85`), which reads `body.get("reason")` (`"exception"`, `"step"`, `"pause"`, etc. from `app/runner/debug_runner.py:41-54`). Legacy reducer loses stop-reason fidelity if any caller revives `DebugEvent(event_type="paused", ...)`.
- **Code-judo alternative:** Fold into TN-DEBUG-01-5 — delete legacy path. If retained briefly, add `stop_reason: str = ""` field on `DebugEvent` and pass through instead of hardcoding.
- **Suggested remediation:** Align or delete legacy reducer; do not maintain two pause models with different reason semantics.
- **Tests that would prove fix:** If legacy kept: paused event with `stop_reason="exception"` round-trips; prefer deletion over patching.
- **Handoff overlap:** R1

---

### TN-DEBUG-01-7 — Command factory tuple layer duplicates protocol envelope assembly

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_command_service.py:8-74` — every helper returns `tuple[str, dict[str, object]]` (command name + arguments). `app/debug/debug_transport.py:82-83` — `send_command` wraps with `build_debug_command()` then `encode_debug_message()`. Breakpoint commands serialize inside the factory (`:52-64`) instead of calling breakpoint wire helpers. `RunService.send_debug_command` (`app/run/run_service.py:213-221`) accepts raw name + dict, bypassing factories for `"pause"`.
- **Code-judo alternative:** Either (a) command factories return fully built protocol dicts via `build_debug_command`, making transport a thin encode/send layer, or (b) keep name+args but move **all** argument shaping (including breakpoints) into typed payload builders in `debug_breakpoints.py` / `debug_protocol.py`. Pick one assembly stage, not two with duplicated dict literals.
- **Suggested remediation:** After TN-DEBUG-01-1, `update_breakpoints_command` becomes `("update_breakpoints", {"breakpoints": breakpoint_list_to_wire(...)}`. Consider typed `DebugCommand` frozen dataclass if the tuple pattern keeps growing.
- **Tests that would prove fix:** Existing `test_debug_command_service.py` stays; add assertion that outbound breakpoint dicts match manifest wire helper byte-for-byte.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-8 — Protocol builders vs `rpc_protocol`: shared codec only, no shared envelope discipline

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_protocol.py:8,13-16` — imports `encode_message`/`decode_message` from `app/plugins/rpc_protocol.py` (JSON line codec). Debug envelopes use `kind`/`command`/`event`/`command_id` (`:29-80`); plugin RPC uses `type`/`request_id`/`command_id`/`payload` (`app/plugins/rpc_protocol.py:18-89`). `decode_debug_message` validates `kind` only (`:23-25`); no schema check for required `command`/`event` fields, protocol version beyond hello, or cross-reference to `DEBUG_PROTOCOL_NAME` on every message. `encode_debug_message` is a one-line alias (`:13-16`).
- **Code-judo alternative:** Keep JSON codec sharing (good), but add debug-specific `validate_debug_envelope(payload) -> DebugEnvelope` typed union, or minimal per-`kind` validators co-located with builders. Unknown fields / missing required keys surface as explicit decode errors (pairs with TN-DEBUG-02-6 silent drops on the session side).
- **Suggested remediation:** Extend `decode_debug_message` with per-kind required keys; document in module docstring that `rpc_protocol` is **codec-only**, not envelope-compatible with plugins. Re-export codec without `encode_debug_message` wrapper if it adds no behavior.
- **Tests that would prove fix:** Unit tests: decode rejects missing `command` on `kind=command`, missing `event` on `kind=event`, empty `kind`; valid envelopes pass.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-9 — `safe_eval` boundary stops at AST shape; command layer exposes unchecked `unsafe` escape hatch

- **Persona:** TN-DEBUG-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/safe_eval.py:9-46,73-80` — allowlist omits `ast.Call`, blocking direct calls; still permits `ast.Attribute`/`ast.Subscript`, so user properties/`__getattr__` may run while evaluating “read-only” watches. `app/debug/debug_command_service.py:36-48` — `evaluate_command(..., unsafe: bool = False)` forwards `unsafe` in arguments with no policy gate. `app/runner/debug_runner.py:333-337` — runner switches to raw `eval(...)` when `unsafe=True`; shell never passes `unsafe=True` today (`app/shell/debug_control_workflow.py:204`), but any transport client could.
- **Code-judo alternative:** Treat `unsafe` as a runner-internal diagnostic flag, not a command argument — or require a session capability token set at hello. Document safe-eval limits (property side effects) in `safe_eval.py` module docstring; optionally block `@property` access via AST parent walk if watch fidelity allows.
- **Suggested remediation:** Remove `unsafe` from the public command schema unless product requires it; if retained, validate in `decode_debug_message` / runner command dispatch that only debug engine self-tests may set it. Expand `test_safe_eval.py` with max-length and dunder rejection as explicit cases (some covered parametrically).
- **Tests that would prove fix:** Unit test: `evaluate_command(unsafe=True)` rejected at protocol validation or runner policy layer; safe eval documents and tests property-access behavior.
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-10 — `debug_runtime_probe` advertises QThread support without probing

- **Persona:** TN-DEBUG-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/debug/debug_runtime_probe.py:17-18,34-35,58-59,66-67` — `supports_qthread_breakpoints` is `False` only on the bdb fallback path; set to `True` whenever `debugpy` passes the `in_process_debug_adapter` signature check, with no Qt/thread probe. Field name implies runtime capability evidence; value is inferred from engine choice.
- **Code-judo alternative:** Rename to `engine_supports_qthread_breakpoints` with docstring “expected when debugpy in-process adapter present”, or perform a lightweight PySide2/thread probe when DISPLAY/runtime parity allows.
- **Suggested remediation:** Clarify semantics in docstring and `DebugRuntimeDecision` field name during R-run-2 engine selection work; avoid UI/feature gating on an unprobed bool.
- **Tests that would prove fix:** Runtime parity test asserts decision fields match documented semantics, not aspirational names.
- **Handoff overlap:** none

---

### TN-DEBUG-01-11 — No direct unit tests for `debug_breakpoints.py` normalization helpers

- **Persona:** TN-DEBUG-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/debug/debug_breakpoints.py` — path normalization (`breakpoint_key`), ID generation (`make_breakpoint_id`), hit-condition clamping (`build_breakpoint`, `:40`), and verification copy (`update_breakpoint_verification`) are exercised only indirectly via `test_debug_command_service.py`, `test_run_manifest.py`, and shell tests. No `tests/unit/debug/test_debug_breakpoints.py`.
- **Code-judo alternative:** Once TN-DEBUG-01-1/03 land, one focused unit module tests parse/serialize round-trips and edge cases — the risk-first gate is satisfied (non-trivial branching, external wire contract).
- **Suggested remediation:** Add `test_debug_breakpoints.py` when consolidating parsers/serializers; do not add tests before the SSOT exists (avoid locking duplicate behavior).
- **Tests that would prove fix:** (This finding defines the suite scope post-consolidation.)
- **Handoff overlap:** R-run-2

---

### TN-DEBUG-01-12 — `DebugSessionState` mutable aggregate lacks field-group reset helpers shared with session reducer

- **Persona:** TN-DEBUG-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/debug/debug_models.py:136-184` — mutable `DebugSessionState` holds inspector, breakpoint, watch, and policy fields. `apply_event()` partially updates execution flags only (`:166-184`). `DebugSession.mark_exited()` (`app/debug/debug_session.py:51-61`) clears inspector subsets manually; `continued` clears even less (TN-DEBUG-02-4). No shared `_reset_inspector_fields()` on the model despite repeated partial-reset patterns.
- **Code-judo alternative:** Add explicit methods on `DebugSessionState`: `clear_inspector()`, `clear_on_continue()`, `clear_on_exit(keep_breakpoints=True)` so session reducer and legacy path share one policy.
- **Suggested remediation:** Implement when TN-DEBUG-02-4 / TN-DEBUG-02-9 are addressed; keeps reset policy in the model layer this critic owns.
- **Tests that would prove fix:** Unit tests on reset helpers; session tests assert `continued` and `mark_exited` call the same primitives with documented differences.
- **Handoff overlap:** shell-wave-1-followup
