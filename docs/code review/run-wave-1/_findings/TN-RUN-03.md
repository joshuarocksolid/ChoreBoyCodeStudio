# TN-RUN-03 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUN-03  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/run/pytest_discovery_service.py` (219 LOC), `app/run/pytest_runner_service.py` (327 LOC), `app/run/problem_parser.py` (61 LOC). Cross-read: `app/shell/test_runner_workflow.py`, `app/plugins/builtin_workflows.py`, `app/plugins/workflow_adapters.py`, `app/plugins/runtime_serializers.py`, `docs/code review/shell-wave-1/_findings/TN-SHELL-TEST-UI.md` (outcome string soup), `tests/unit/run/test_pytest_discovery_service.py`, `tests/unit/run/test_pytest_runner_service.py`, `tests/unit/run/test_problem_parser.py`, `tests/unit/shell/test_test_runner_workflow.py`, `docs/ARCHITECTURE.md` §12.6 / §25b.

---

## Executive verdict

**Not thermo-clean.** Pytest discovery, execution, and output parsing are bolted onto the `app/run/` subprocess-lifecycle package as three parallel subprocess stacks that never share a command builder, environment contract, or cancellation hook with `RunService` / `ProcessSupervisor`. Discovery and runner disagree on runtime selection (`run_tests.py`, `CBCS_PYTEST_EXECUTABLE`, vendor bootstrap), quiet-mode runs cannot feed the explorer outcome model, and pytest failure parsing lives outside `problem_parser.py` beside traceback parsing. Outcome and node-kind vocabulary remain raw strings end-to-end (TN-SHELL-TEST-UI-8 overlap). Unit tests cover payload vendor injection and command shapes well, but the workflow outcome test masks the `-q`/`-v` mismatch by injecting verbose stdout manually. **Would not approve** further Test Explorer features until pytest subprocess contracts unify, outcomes are typed, and parsers consolidate under one module boundary.

---

### TN-RUN-03-1 — Pytest services belong in a dedicated package, not `app/run/` lifecycle

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `docs/ARCHITECTURE.md:724-732` — §12.6 defines `app/run/` as manifest creation, runner launch, output read, run state, stop/terminate. `app/run/pytest_discovery_service.py:64-92` and `app/run/pytest_runner_service.py:259-281` spawn **synchronous** `subprocess.run` pytest invocations with no manifest, no `ProcessSupervisor`, and no shared lifecycle with `RunService`. `docs/code review/run-wave-1/00-manifest.md:96` — manifest lists "pytest services mixed into `app/run/` lifecycle package" as a high-risk hotspot.
- **Code-judo alternative:** Extract `app/pytest/` (or `app/testing/pytest/`) owning discovery, runner command planning, output parsers, and typed models. `app/run/` keeps runner-process supervision only; shell and plugins import from the pytest package. Hard cutover — no re-export shims in `app/run/`.
- **Suggested remediation:** Move the three primary modules plus tests; update `builtin_workflows`, `test_runner_workflow`, bundled plugin, and serializers in one PR. Leave `ProblemEntry` in a shared `app/run/problem_parser.py` or colocate with pytest if traceback parsing also moves.
- **Tests that would prove fix:** Import graph grep shows no `app/run/pytest_*` paths; existing unit tests pass from new package paths only.
- **Handoff overlap:** R-run-2

---

### TN-RUN-03-2 — Discovery and runner subprocess contracts diverge on runtime, bootstrap, and env

- **Persona:** TN-RUN-03
- **Severity:** BLOCKER
- **Evidence:** `app/run/pytest_discovery_service.py:118-125` — discovery calls `resolve_runtime_executable(None)` directly; AppRun path uses inline `_build_apprun_pytest_payload`, never `run_tests.py`. `app/run/pytest_runner_service.py:109-125,252-256` — runner prefers project `run_tests.py` via `build_runpy_bootstrap_payload`, then falls back to AppRun `-c pytest.main(...)`. `app/run/pytest_runner_service.py:128-156` — runner honors `CBCS_PYTEST_EXECUTABLE` with probe subprocess; discovery ignores it. `app/run/pytest_discovery_service.py:214-218` — discovery sets `QT_QPA_PLATFORM=offscreen`; `app/run/pytest_runner_service.py:262-268` — runner passes no custom env. `app/run/pytest_discovery_service.py:10` — imports `build_runpy_bootstrap_payload` but never uses it (dead signal of incomplete alignment).
- **Code-judo alternative:** Single `PytestLaunchPlan` module: `plan_collect(project_root) -> list[str]` and `plan_run(project_root, args) -> list[str]` sharing runtime selection, vendor injection, `run_tests.py` preference, env defaults, and missing-pytest marker handling. Discovery and runner become thin wrappers over one planner.
- **Suggested remediation:** Unify runtime selection first (highest user-visible risk); add integration test that discovery and run-all use the same executable and bootstrap path for a fixture project with `run_tests.py`.
- **Tests that would prove fix:** Parametrized test: given project with `run_tests.py`, both `discover_tests` and `run_pytest_project` build commands whose resolved runtime and bootstrap payload match; discovery respects `CBCS_PYTEST_EXECUTABLE` when set.
- **Handoff overlap:** R-run-2, shell-wave-1-followup

---

### TN-RUN-03-3 — Triplicated AppRun `-c` pytest payload builders

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/pytest_discovery_service.py:128-141` — `_build_apprun_pytest_payload(pytest_args)`. `app/run/pytest_runner_service.py:196-223` — `_build_apprun_pytest_probe_payload()` and `_build_apprun_pytest_payload(*, pytest_args)` with identical vendor insert + `ModuleNotFoundError` marker blocks. Tests duplicate vendor-order assertions in both `tests/unit/run/test_pytest_discovery_service.py:145-167` and `tests/unit/run/test_pytest_runner_service.py:31-61`.
- **Code-judo alternative:** One `app/pytest/apprun_payload.py` (or under unified launch plan) exporting `build_pytest_main_payload(args)`, `build_pytest_probe_payload()`, and `PYTEST_MISSING_MARKER`. Discovery and runner import; tests assert once.
- **Suggested remediation:** Extract shared module as part of TN-RUN-03-2 planner work; delete duplicate private functions in same diff.
- **Tests that would prove fix:** Single parametrized payload contract test; discovery/runner service tests mock planner instead of re-validating payload string shape.
- **Handoff overlap:** R-run-2

---

### TN-RUN-03-4 — Quiet-mode runs cannot populate explorer outcomes (`-q` vs `-v` mismatch)

- **Persona:** TN-RUN-03
- **Severity:** BLOCKER
- **Evidence:** `app/run/pytest_runner_service.py:46-47,98` — `run_pytest_project` and `run_pytest_target` inject `-q`. `app/run/pytest_discovery_service.py:95-115` — `parse_test_results` expects verbose lines containing `" PASSED"`, `" FAILED"`, `" SKIPPED"`, `" ERROR"`. `app/shell/test_runner_workflow.py:346-358` — `_update_test_outcomes_from_pytest` calls `parse_test_results(result.stdout)` after every run; returns empty for `-q` output, so outcomes never update for Run All / Run File. `tests/unit/shell/test_test_runner_workflow.py:203-225` — masks bug by fabricating verbose stdout (`"::test_alpha FAILED\n"`) while production `run_all_tests` path uses `-q` via `builtin_workflows.py:177`.
- **Code-judo alternative:** Either (a) standardize explorer-updating runs on `-v` (or `--tb=no -v`) across project/file/node scopes, or (b) parse pytest's structured output (`--reportlog`, JUnit, or `-rA` summary) in one function that does not depend on verbose per-line tokens. Prefer (b) if console noise matters — but pick one contract and enforce it in command builder.
- **Suggested remediation:** Align command args with parser; add failing characterization test that runs `run_pytest_project` fake stdout `"1 passed"` and asserts outcomes update (will fail today). Fix workflow test to use realistic `-q` stdout.
- **Tests that would prove fix:** Integration-style unit test: `-q` mixed pass/fail fixture output → `parse_test_results` or replacement returns per-node outcomes; `test_handle_pytest_result_updates_outcomes` uses production command shape.
- **Handoff overlap:** shell-wave-1-followup, R3

---

### TN-RUN-03-5 — Outcome and node-kind vocabulary are untyped raw strings

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/pytest_discovery_service.py:28,58` — `kind: str` and `outcome: str  # "passed", "failed", "skipped", "error"`. `app/run/pytest_discovery_service.py:103-114` — literals assigned in `parse_test_results`. `app/shell/test_runner_workflow.py:100,352-356,427` — `dict[str, str]` and `outcome == "failed"`. Cross-read: `docs/code review/shell-wave-1/_findings/TN-SHELL-TEST-UI.md` TN-SHELL-TEST-UI-8 documents panel-side string soup; run layer is the authoritative source but provides no shared type.
- **Code-judo alternative:** `TestOutcome = Literal["passed", "failed", "skipped", "error", "not_run"]` and `TestNodeKind = Literal["file", "class", "function"]` in pytest models module; `DiscoveredTestResult.outcome: TestOutcome`; panel and workflow import the alias. Filter/count helpers operate on `OutcomeCounts` dataclass.
- **Suggested remediation:** Add types in pytest package (TN-RUN-03-1); pyright strict on workflow + discovery modules; ship with R3 panel work to avoid half-migrated string compares.
- **Tests that would prove fix:** Type checker enforces outcome keys; one helper test for `count_outcomes(mapping) -> OutcomeCounts` shared by shell and run layers.
- **Handoff overlap:** R3, shell-wave-1-followup

---

### TN-RUN-03-6 — Pytest failure parsing split from `problem_parser.py` duplicates `ProblemEntry` production

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/problem_parser.py:24-61` — `parse_traceback_problems` only. `app/run/pytest_runner_service.py:284-327` — `parse_pytest_failures` and `_parse_pytest_failure_line` live in runner service, also producing `ProblemEntry` with `context="pytest"`. `tests/unit/run/test_problem_parser.py` — covers traceback only; pytest failure tests sit in `test_pytest_runner_service.py:64-74`. Consumers (`main_window.py:3021-3023` traceback vs `test_runner_workflow.py:333-334` pytest failures) use different parsers for the same Problems pane type.
- **Code-judo alternative:** Extend `problem_parser.py` with `parse_pytest_problems(output, project_root) -> list[ProblemEntry]` (move existing functions). Runner service imports and calls; single module owns all navigable problem extraction from process output.
- **Suggested remediation:** Move functions + tests in hard cutover; runner re-exports nothing. Optional: unified `parse_run_output(text, *, project_root, flavor="auto")` if auto-detection stays simple — avoid if it becomes a fallback chain.
- **Tests that would prove fix:** `test_problem_parser.py` gains pytest failure cases; `rg parse_pytest_failures app/run/pytest_runner_service.py` returns no definitions.
- **Handoff overlap:** R-run-2

---

### TN-RUN-03-7 — Runner subprocess path lacks discovery-grade error handling; timeouts escape to shell

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/pytest_discovery_service.py:78-81` — catches `subprocess.TimeoutExpired` and `OSError`, returns `DiscoveryResult(error_message=...)`. `app/run/pytest_runner_service.py:259-281` — `_run_pytest_command` calls bare `subprocess.run(..., timeout=timeout_seconds)` with no try/except; timeout/OSError propagate to `GeneralTaskScheduler` worker (`app/shell/background_tasks.py:52-54`) as generic exceptions. `app/shell/test_runner_workflow.py:311-315` — user sees `"Pytest run failed: {exc}"` without structured `PytestRunResult` or partial stdout. Discovery maps `PYTEST_MISSING_MARKER`; runner probe emits marker but `_run_pytest_command` never translates it to a friendly error on run failure.
- **Code-judo alternative:** `_run_pytest_command` always returns `PytestRunResult` — on timeout/OSError, populate `stderr` with actionable message, set `return_code=-1`, preserve elapsed time. Mirror discovery's marker → message mapping for run path.
- **Suggested remediation:** Wrap subprocess call; add unit test for timeout returning result object (not raise). Align with TN-RUN-03-2 env/marker handling.
- **Tests that would prove fix:** `test_run_pytest_project_timeout_returns_result` asserts no exception, `return_code != 0`, message in stderr; workflow test asserts console line on timeout without crashing callback chain.
- **Handoff overlap:** R-run-2

---

### TN-RUN-03-8 — Pytest subprocesses ignore workflow cancellation hooks

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_runner_workflow.py:257-258,295-296` — background tasks receive `_cancel_event` but pass it unused. `app/plugins/builtin_workflows.py:153-155` — `_run_builtin_pytest_job` receives `is_cancelled` and discards with `_ = is_cancelled`. `app/run/pytest_runner_service.py:262-268` — blocking `subprocess.run` with no process handle for kill. `app/shell/background_tasks.py:44-47` — superseded keyed tasks set cancellation event, but pytest child keeps running until natural exit.
- **Code-judo alternative:** Pass `cancel_event` / `is_cancelled` into pytest services; use `subprocess.Popen` + poll loop (or shared small helper with `ProcessSupervisor`-compatible kill semantics) so replacement discovery/run tasks terminate prior pytest children. At minimum, document non-cancellable contract and disable key replacement for pytest keys — prefer termination.
- **Suggested remediation:** Short term: poll `is_cancelled` during long runs and kill child; long term: optional alignment with `ProcessSupervisor` for consistent stop semantics across run modes.
- **Tests that would prove fix:** Unit test with fake Popen: set cancel flag mid-run → subprocess receives terminate/kill; second discovery request does not deliver stale results from first child.
- **Handoff overlap:** R-run-2, shell-wave-1-followup

---

### TN-RUN-03-9 — Line-based output parsers are brittle and incomplete for real pytest trees

- **Persona:** TN-RUN-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/run/pytest_discovery_service.py:150-209` — `_parse_collect_output` skips lines without `::`, always sets `line_number=0`, supports only two- and three-segment node IDs (no parametrized `[...]` segments, no deeper nesting). `app/run/pytest_discovery_service.py:103-114` — `parse_test_results` uses substring `" PASSED"` etc., vulnerable to false positives in node IDs or messages. `app/run/pytest_runner_service.py:304-327` — `_parse_pytest_failure_line` requires `.py` suffix and exactly two colon splits, misses many pytest failure formats (windows paths, `E   assert` blocks, multi-line tracebacks already handled elsewhere).
- **Code-judo alternative:** Prefer pytest-native machine output for collection (`--collect-only --quiet` JSON via plugin, or `--fixtures` avoidance) and results (JUnit XML or reportlog) with a single deserializer to `DiscoveredTestNode` / `DiscoveredTestResult`. Keep line parsers only as fallback with explicit format flag — not silent default.
- **Suggested remediation:** Phase 1: document supported pytest output shapes in ARCHITECTURE §25b; Phase 2: add structured reporter behind feature flag; delete substring parsers when structured path covers explorer needs.
- **Tests that would prove fix:** Fixture files for parametrized tests and `[slow]` markers parse to stable node IDs; regression test where node name contains `" ERROR"` substring does not mis-classify outcome.
- **Handoff overlap:** R3

---

### TN-RUN-03-10 — Duplicate workflow serialization for `PytestRunResult` / `ProblemEntry`

- **Persona:** TN-RUN-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/plugins/builtin_workflows.py:222-244` — `_pytest_run_result_to_dict` and `_problem_entry_to_dict`. `app/plugins/runtime_serializers.py:57-75` — `serialize_pytest_run_result` and `serialize_problem_entry` with identical field shapes. `app/plugins/builtin_workflows.py:186` — job handler returns local dict serializer, not `serialize_pytest_run_result`.
- **Code-judo alternative:** Builtin pytest job returns via `serialize_pytest_run_result`; delete private `_pytest_run_result_to_dict` / `_problem_entry_to_dict`. Single serialization SSOT for workflow broker boundary.
- **Suggested remediation:** One-line import swap in `builtin_workflows.py`; grep confirms no duplicate dict builders.
- **Tests that would prove fix:** Existing plugin tests green; optional assert serialized keys match `runtime_serializers` golden dict.
- **Handoff overlap:** none

---

### TN-RUN-03-11 — `identify_test_at_cursor` is editor intelligence embedded in runner service

- **Persona:** TN-RUN-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/run/pytest_runner_service.py:64-89` — AST walk for test function at cursor; no subprocess dependency. Only caller: `app/shell/test_runner_workflow.py:158`. Module docstring: "Project-level pytest runner helpers."
- **Code-judo alternative:** Move to `app/intelligence/` or `app/shell/test_targeting.py` beside cursor/run-at-line helpers; runner service stays subprocess + parse only.
- **Suggested remediation:** Extract on next touch of either module; trivial import update in workflow.
- **Tests that would prove fix:** Move existing cursor tests to new module path; runner service tests shrink to subprocess contracts.
- **Handoff overlap:** R3

---

### TN-RUN-03-12 — Dead surface: `run_pytest_failed`, unused imports, optional typing drift

- **Persona:** TN-RUN-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/run/pytest_runner_service.py:57-61` — `run_pytest_failed` exported but shell reroutes via explicit `pytest_args` (`app/shell/test_runner_workflow.py:174-181` → `run_pytest_args`). `app/run/pytest_discovery_service.py:7,10` — unused `Optional` import and unused `build_runpy_bootstrap_payload` import. `app/run/pytest_runner_service.py:142-143,177` — `_candidate_pytest_runtimes` / `_runtime_supports_pytest` accept `project_root` then `_ = project_root` (API pretends project context matters).
- **Code-judo alternative:** Delete `run_pytest_failed` or make workflow call it; remove dead imports; drop unused `project_root` parameters from runtime probe helpers.
- **Suggested remediation:** Hygiene pass bundled with TN-RUN-03-2 planner extraction.
- **Tests that would prove fix:** `rg run_pytest_failed` shows single definition or real caller; pyright/ruff clean on discovery module imports.
- **Handoff overlap:** none

---

## Positive signals (replicate, do not rewrite)

- **Vendor-before-pytest AppRun contract** — Both services and tests enforce `sys.path.insert(vendor)` before `import pytest` (`test_pytest_discovery_service.py:145-167`, `test_pytest_runner_service.py:31-61`); keep this invariant in any unified payload builder.
- **`PYTEST_MISSING_MARKER` UX** — Discovery maps marker to friendly message (`pytest_discovery_service.py:84-85`); extend same pattern to run path (TN-RUN-03-7).
- **Project `run_tests.py` preference on run path** — Runner correctly routes through `build_runpy_bootstrap_payload` when script exists (`pytest_runner_service.py:113-121`); extend to discovery (TN-RUN-03-2).
- **Arg normalization** — `_normalized_pytest_args` injects `--import-mode=importlib` and `-p no:cacheprovider` consistently (`pytest_runner_service.py:226-242`); good default for ChoreBoy; should be shared with discovery collect args.
- **ProblemEntry as cross-pane contract** — Single dataclass feeds Problems panel, workflow, and plugins; consolidation target is parser location, not the model (TN-RUN-03-6).
- **Workflow test harness** — `test_test_runner_workflow.py` exercises orchestration without `MainWindow`; extend with realistic stdout fixtures after TN-RUN-03-4 fix.

---

## Slice metrics (baseline commit)

| Metric | Value |
|--------|------:|
| `pytest_discovery_service.py` LOC | 219 |
| `pytest_runner_service.py` LOC | 327 |
| `problem_parser.py` LOC | 61 |
| Combined slice LOC | 607 |
| `_build_apprun_pytest_payload` implementations | 2 |
| Runtime selection paths (discovery vs runner) | 2 |
| Production callers of `run_pytest_failed` | 0 |
| `parse_test_results` compatible with `run_pytest_project` (`-q`) | No |

## Cross-slice notes

- **Outcome string soup:** TN-SHELL-TEST-UI-8 — run layer should own `TestOutcome` type; panel/workflow import it in R3 tranche.
- **Dual outcome SSOT:** TN-SHELL-TEST-UI-2 — fixing `-q`/`-v` (TN-RUN-03-4) is prerequisite for trustworthy explorer state; otherwise panel mirrors stale `"not_run"`.
- **Subprocess exclusivity:** TN-RUN-02 — pytest uses parallel subprocess stack; overlapping long pytest run + debug run + `RunService` child is uncoordinated (no global process gate).
- **ARCHITECTURE §25b.4 result persistence** — Not implemented in these modules; any persistence layer should consume typed outcomes post TN-RUN-03-4/5, not raw stdout parsing.

## Approval bar (this slice)

**Blocked for thermo-clean approval** until: (1) unified pytest launch plan across discovery and runner (TN-RUN-03-2, TN-RUN-03-3), (2) `-q`/outcome pipeline fixed or replaced with structured results (TN-RUN-03-4), (3) pytest failure parsing consolidated in `problem_parser.py` (TN-RUN-03-6). Typed outcomes (TN-RUN-03-5) and package extraction (TN-RUN-03-1) should land in the same fix wave as shell R3 to prevent new explorer features from extending the duplicated subprocess stack.
