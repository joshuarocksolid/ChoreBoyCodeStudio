# TN-RUN-01 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUN-01  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/run/run_manifest.py` (395 LOC), `app/run/runtime_launch.py` (41 LOC), `app/run/runner_command_builder.py` (20 LOC), `app/run/exit_status.py` (16 LOC). Cross-read: `tests/unit/run/test_run_manifest.py`, `tests/unit/run/test_runtime_launch.py`, `docs/ARCHITECTURE.md` §13.

---

## Executive verdict

**Conditionally thermo-clean for slice size, not approval-ready for contract growth.** The manifest is a real typed boundary — frozen `RunManifest`, strict path validation, deterministic `save_run_manifest` (`sort_keys=True`), and canonical `build_breakpoint` normalization on load are solid foundations. Launch helpers are small and direct; the PosixPath-in-argv regression test shows appropriate bootstrap determinism awareness. Dominant risks are **structural duplication and drift**: near-identical loopback transport types/parsers (`DebugTransportConfig` vs `ReplControlConfig`), hand-rolled JSON mapping that already diverges from runner-side breakpoint parsing (TN-RUNNER-03-6), and **mode-blind validation** that only enforces `debug_transport` for `python_debug` while silently accepting debug/REPL fields on other modes. `run_manifest.py` is one new mode-field away from needing decomposition. Would not approve further debug/REPL manifest fields without unifying transport config, adding mode-aware validation/serialization, and closing round-trip test gaps.

---

### TN-RUN-01-1 — Duplicate loopback transport models and twin parsers

- **Persona:** TN-RUN-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/debug/debug_models.py:18-26` — `DebugTransportConfig(protocol, host, port, session_token, connect_timeout_ms=8000)`. `app/run/run_manifest.py:103-111` — `ReplControlConfig` with identical fields and `connect_timeout_ms=800`. `app/run/run_manifest.py:289-311` vs `314-336` — `_parse_debug_transport` and `_parse_repl_control` are copy-paste parsers differing only in field name and default timeout. `app/run/run_manifest.py:84-99` — duplicate `to_dict` branches for the two shapes.
- **Code-judo alternative:** One frozen `LoopbackTransportConfig` in `app/debug/debug_models.py` (or `app/run/transport_config.py`) with `default_timeout_ms` per use-site or a `channel: Literal["debug", "repl"]` discriminator. Single `_parse_loopback_transport(raw, *, field_name, default_timeout_ms)` plus thin aliases. Deletes ~80 LOC and one entire type.
- **Suggested remediation:** Hard cutover: replace `ReplControlConfig` with `DebugTransportConfig` or a shared base type; update `ReplSessionManager`, `repl_control.py`, and manifest JSON keys (`repl_control` stays as the JSON field name — only the Python type unifies). No parallel parsers.
- **Tests that would prove fix:** Parametrized round-trip tests for both JSON keys through one parser; existing `test_run_manifest_round_trips_repl_control_config` and debug transport tests stay green after type unification.
- **Handoff overlap:** R-run-2

---

### TN-RUN-01-2 — Mode-blind manifest validation accepts cross-mode field pollution

- **Persona:** TN-RUN-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_manifest.py:157-162` — only cross-mode rule: `python_debug` requires `debug_transport`. No rule requiring `repl_control` for `python_repl`. No rejection of `breakpoints`, `source_maps`, or `debug_exception_policy` on `python_script` / `python_repl` manifests. `app/run/run_service.py:161-176` — script/debug manifests always embed `breakpoints`, `debug_exception_policy`, and `source_maps` regardless of mode; `repl_control` is never set on the `RunService` REPL path (only `ReplSessionManager` sets it — `app/shell/repl_session_manager.py:178-191`). `docs/ARCHITECTURE.md:820-823` documents debug-only optional fields but omits `repl_control` entirely.
- **Code-judo alternative:** Mode-scoped validation table: `{mode: required_fields, allowed_fields}`. Parse rejects unknown combinations (e.g. `breakpoints` on `python_script`) instead of silently carrying dead JSON. `to_dict()` emits mode-minimal payloads — script manifests omit empty debug arrays and default policies.
- **Suggested remediation:** Add `_validate_mode_fields(mode, ...)` after field parse in `parse_run_manifest`. Require `repl_control` when `mode == python_repl` (or document and enforce “REPL without control is completion-degraded only” as an explicit opt-out). Update ARCHITECTURE §13.1 with `repl_control` for `python_repl`. Align `RunService` REPL path with `ReplSessionManager` or delete the duplicate REPL launch path (pairs with TN-RUN-SHELL-8).
- **Tests that would prove fix:** Parse rejects `python_script` + non-empty `breakpoints`; rejects `python_debug` without `debug_transport` (currently untested); rejects or accepts-by-policy `python_repl` without `repl_control`. `to_dict` snapshot per mode shows no debug keys on script runs.
- **Handoff overlap:** R-run-2, shell-wave-1-followup

---

### TN-RUN-01-3 — Hand-rolled JSON mapping is a drift magnet across process boundaries

- **Persona:** TN-RUN-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_manifest.py:49-100` — manual `to_dict` re-serializes nested debug shapes field-by-field instead of delegating to model methods. `app/run/run_manifest.py:61-70` — serializes six breakpoint fields; omits `verified` and `verification_message` (`app/debug/debug_models.py:55-56`), so in-memory verification state cannot round-trip through manifest JSON. `app/runner/debug_runner.py:730-753` — separate `_parse_breakpoints` in runner (flagged TN-RUNNER-03-6). `app/run/run_service.py:267-293` — third breakpoint normalization path with silent `continue` on bad entries (no validation error). Three writers, one schema, no single source of truth.
- **Code-judo alternative:** Colocate `to_manifest_dict()` / `from_manifest_dict()` on `DebugBreakpoint`, `DebugTransportConfig`, `DebugSourceMap`, and `DebugExceptionPolicy` (or one `RunManifestCodec` module). `RunManifest.to_dict` becomes `{**core_fields, **codec.encode_debug_bundle(self)}`. Runner and editor both import the codec — delete runner-local `_parse_breakpoints`.
- **Suggested remediation:** Extract `app/run/manifest_codec.py` (or extend `debug_models.py` with JSON-boundary methods only). Hard cutover runner parser to codec. Decide explicitly whether verification fields belong in persisted manifest; if not, document omission in ARCHITECTURE §13.1.
- **Tests that would prove fix:** Full debug manifest round-trip (transport + breakpoints + source_maps + policy) through save/load equals input. Runner `update_breakpoints` command uses same parser as manifest load (shared test vectors).
- **Handoff overlap:** R-run-2 (pairs with TN-RUNNER-03-6)

---

### TN-RUN-01-4 — `frozen=True` RunManifest still allows shallow mutation of contract fields

- **Persona:** TN-RUN-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_manifest.py:29-47` — `@dataclass(frozen=True)` with `argv: list[str]`, `env: dict[str, str]`, `breakpoints: list[DebugBreakpoint]`, `source_maps: list[DebugSourceMap]`. Python frozen only blocks rebinding attributes, not in-place list/dict mutation. `app/runner/execution_context.py:18-26` — same pattern on `RunnerExecutionContext`. Any holder can `manifest.argv.append("injected")` or `manifest.env["PATH"] = "..."` after construction, breaking the editor→runner contract without touching `save_run_manifest`.
- **Code-judo alternative:** Store immutable containers: `argv: tuple[str, ...]`, `env: Mapping[str, str]` (or `tuple[tuple[str,str], ...]`), `breakpoints: tuple[DebugBreakpoint, ...]`. Parse and constructors coerce inputs once; no mutable aliases escape.
- **Suggested remediation:** Change container field types to tuples/`Mapping`; update `to_dict`/`parse_run_manifest` to wrap with `tuple()`/`dict()` at boundaries. Low churn — callers mostly read and pass through.
- **Tests that would prove fix:** Construct manifest, attempt `manifest.argv.append("x")` → `AttributeError` or frozen-field error; verify `parse_run_manifest` → mutate → re-serialize produces different JSON (characterization before fix, prevented after).
- **Handoff overlap:** none

---

### TN-RUN-01-5 — `run_manifest.py` is a 395-line contract monolith absorbing every new run mode concern

- **Persona:** TN-RUN-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/run_manifest.py:1-395` — single module owns `RunManifest`, `ReplControlConfig`, `to_dict`, `parse_run_manifest`, `load/save`, and nine private validators/parsers (`_require_*`, `_parse_breakpoints`, `_parse_debug_transport`, `_parse_repl_control`, `_parse_exception_policy`, `_parse_source_maps`, `_parse_optional_positive_int`). Imports reach into `app.debug` for four model types plus `build_breakpoint`. Wave baseline lists 395 LOC (`docs/code review/run-wave-1/00-manifest.md:32`); thermo rule treats growth past 1k as presumptive blocker — this file is the highest-LOC contract surface in the run slice.
- **Code-judo alternative:** Split into `run_manifest_models.py` (dataclasses only), `run_manifest_parse.py` (validation + load), `run_manifest_persist.py` (save/load file I/O). Or keep models and move parsers into `manifest_codec.py` (TN-RUN-01-3). Target: each file &lt;200 LOC, one reason to change.
- **Suggested remediation:** Decompose when implementing TN-RUN-01-1/03 (transport unification + codec extraction) in one hard-cutover PR — do not add a fourth transport field inline.
- **Tests that would prove fix:** Import paths updated; existing `tests/unit/run/test_run_manifest.py` green without behavior change.
- **Handoff overlap:** R-run-2

---

### TN-RUN-01-6 — Launch command builder does not canonicalize `manifest_path`

- **Persona:** TN-RUN-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/run/runner_command_builder.py:10-20` — passes `manifest_path` through unchanged in both AppRun (`argv=[..., manifest_path]`) and plain-Python command branches. Contrast `app/run/runtime_launch.py:33` — `build_runpy_bootstrap_payload` resolves `script_path` via `Path(...).resolve()`. `app/run/run_manifest.py:229-234` — all persisted manifest path *fields* must be absolute, but the CLI `--manifest` argument has no such guarantee at the builder API. Today callers pass resolved paths (`app/run/host_process_manager.py:46`, `repl_session_manager.py:195`), but the builder contract is implicit.
- **Code-judo alternative:** `resolved_manifest = str(Path(manifest_path).expanduser().resolve())` at top of `build_runner_command`; one line, symmetric with bootstrap and manifest field validators.
- **Suggested remediation:** Resolve in builder; add unit test with relative manifest path asserting argv/payload contain absolute string.
- **Tests that would prove fix:** `test_build_runner_command_resolves_relative_manifest_path` for both AppRun and plain-python branches.
- **Handoff overlap:** none

---

### TN-RUN-01-7 — Contract test coverage stops short of debug-mode and enforcement rules

- **Persona:** TN-RUN-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/run/test_run_manifest.py:17-124` — five tests: script round-trip, invalid mode, absolute paths, breakpoint shape, REPL control round-trip via `to_dict`. Missing: `parse_run_manifest` rejects `python_debug` without `debug_transport` (`app/run/run_manifest.py:157-162` — zero test references to this rule). Missing: debug manifest save/load round-trip with `debug_transport`, `source_maps`, and `debug_exception_policy`. No tests for `build_runner_command` or `describe_exit_code` despite both sitting in TN-RUN-01 scope (`app/run/runner_command_builder.py`, `app/run/exit_status.py`). Risk-first gate: mode validation and bootstrap argv shaping justify tests; `describe_exit_code` is lower priority.
- **Code-judo alternative:** Parametrized `test_parse_run_manifest_mode_rules` covering all cross-field rules from TN-RUN-01-2; one golden-file debug manifest round-trip test shared with runner integration.
- **Suggested remediation:** Add mode-rule and debug round-trip tests when validation tightens (TN-RUN-01-2); add `build_runner_command` tests with TN-RUN-01-6 fix.
- **Tests that would prove fix:** (Self-describing — these are the missing tests.)
- **Handoff overlap:** none

---

### TN-RUN-01-8 — `exit_status.py` is shell presentation logic living in the run contract package

- **Persona:** TN-RUN-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/run/exit_status.py:6-16` — `describe_exit_code` formats return codes for human-readable status strings. Only consumers: `app/shell/run_output_coordinator.py:83`, `app/shell/main_window.py:2890`. No use from `app/run/process_supervisor.py`, `run_service.py`, or runner code. `docs/ARCHITECTURE.md:920-928` §13.5 defines semantic exit codes (`0`, `1`, `2`, `3`, `130`); `describe_exit_code` only maps numeric/signal form, not semantic constants — thin utility with misplaced ownership (same smell as TN-RUN-02-8 for `ConsoleModel`).
- **Code-judo alternative:** Move to `app/shell/run_status_text.py` or merge into `run_output_coordinator.py`. If runner semantic codes need surfacing, add `describe_run_exit_code(code: int) -> str` next to `constants.RUN_EXIT_*` in `app/core/constants.py` or a dedicated `run_exit_codes.py` owned by the contract layer.
- **Suggested remediation:** Relocate with hard cutover shell imports; optional small mapping from `constants.RUN_EXIT_*` to user-facing strings for §13.5 alignment.
- **Tests that would prove fix:** Move/add unit test under `tests/unit/shell/`; fast shard green.
- **Handoff overlap:** shell-wave-1-followup

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| RunManifest JSON contract | Typed and validated for core fields; mode cross-rules incomplete (TN-RUN-01-2) |
| Frozen dataclass integrity | Shallow mutability on container fields (TN-RUN-01-4) |
| Field naming drift | `ReplControlConfig` vs `DebugTransportConfig`; ARCHITECTURE omits `repl_control` (TN-RUN-01-1, TN-RUN-01-2) |
| Launch/bootstrap determinism | Bootstrap resolves paths; builder should resolve `--manifest` (TN-RUN-01-6); PosixPath argv regression covered |
| Debug/REPL fields in manifest | Embedded correctly for debug; duplicated parsers and mode-blind acceptance (TN-RUN-01-1, TN-RUN-01-2, TN-RUN-01-3) |

**Prior audit staleness:** Do not treat `docs/deslop/AUDIT_app.md` as current (per `_README.md` handoff rules).
