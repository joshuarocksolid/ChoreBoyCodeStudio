# Stability Audit v0.3 (since v0.2)

## Executive summary

This audit reviewed all `v0.2..HEAD` stability-relevant areas and validated behavior with baseline and targeted runtime tests. The full-suite baseline (`python3 run_tests.py -v --import-mode=importlib`) did **not** reach green status: semantic integration failures appeared immediately, then the run-preflight lane stalled. The highest-impact regression is semantic runtime bootstrap failure (Jedi/Rope import contract), which cascades into incorrect fallback behavior for navigation/references and hard failures for rename/performance/runtime-parity tests. A second high-impact reliability issue is run-project missing-entry behavior bypassing preflight and entering a modal prompt path that can hang non-interactive flows. Relative to the prior performance audit (`fb4afd4`), responsiveness work landed, but several correctness/error-path regressions remain and should be fixed before release hardening.

## Findings (sorted by severity)

| # | Area | Issue | Severity | Effort | Recommendation |
|---|---|---|---|---|---|
| 1 | Semantic runtime bootstrap | Jedi/Rope runtime probes accept broken imports and semantic runtime becomes unusable | **High** | Small | Validate required module attributes/submodules during runtime init, not just top-level import |
| 2 | Navigation/reference correctness | Semantic failures are swallowed and silently downgraded to approximate results | **High** | Small | Stop blanket-swallow fallback for runtime failures; surface explicit semantic-unavailable diagnostics |
| 3 | Run preflight / UX reliability | Missing project entrypoint path bypasses preflight and opens blocking modal selection flow | **High** | Small | Route project run/debug through preflight-first error reporting (Runtime Center), avoid mandatory modal prompt |
| 4 | Test/runtime resource cleanup | Test shutdown helper skips run/repl/plugin stop path, leaving long-lived child processes | **Medium** | Trivial | Mirror full close teardown in helper by invoking active-run/repl/plugin shutdown |
| 5 | Plugin runtime diagnostics | Job event handler exceptions are swallowed without logging/error surfacing | **Medium** | Small | Log handler failures and expose a failure signal/metric instead of silent success |

---

## Detailed findings

### 1) Semantic runtime bootstrap regression breaks semantic stack

- **Location**
  - `app/intelligence/jedi_runtime.py:32-55`
  - `app/intelligence/refactor_runtime.py:27-43`
  - `app/intelligence/refactor_engine.py:35-40`
  - `app/intelligence/jedi_engine.py:251-253`
- **What the problem is**
  - `initialize_jedi_runtime()` only does `import jedi` then accesses `jedi.settings` (`jedi_runtime.py:44`). In current runtime this import resolves to a namespace package (no `settings`), causing `AttributeError`, so runtime status is set unavailable.
  - `initialize_refactor_runtime()` only checks `import rope` (`refactor_runtime.py:35`), but `RopeRefactorEngine.plan_rename()` later imports `rope.base.project` (`refactor_engine.py:39`) and fails at runtime.
- **Failure scenario (reproducible)**
  1. Run:
     ```bash
     /opt/freecad/AppRun -c "import sys;sys.path.insert(0,'/workspace');from app.intelligence.jedi_runtime import initialize_jedi_runtime;print(initialize_jedi_runtime())"
     ```
     Output shows `is_available=False` with `AttributeError: module 'jedi' has no attribute 'settings'`.
  2. Run:
     ```bash
     python3 run_tests.py --import-mode=importlib tests/integration/intelligence/test_semantic_rename_integration.py::test_plan_rename_symbol_builds_patch_style_preview
     ```
     Fails with `RuntimeError: AttributeError: module 'jedi' has no attribute 'settings'` (also seen in unit/runtime-parity tests).
  3. Run:
     ```bash
     python3 run_tests.py --import-mode=importlib tests/runtime_parity/intelligence/test_semantic_engine_runtime.py::test_semantic_runtimes_use_visible_cache_paths_and_no_hidden_project_dirs
     ```
     Fails with `ModuleNotFoundError: No module named 'rope.base.project'`.
- **Blast radius**
  - Semantic navigation, references, rename, and semantic perf/runtime-parity lanes fail or degrade.
  - User-visible features return incorrect precision or hard-fail depending on caller.
- **Proposed fix**
  - In runtime probes, validate required APIs explicitly:
    - Jedi: verify `jedi.Script` and optional `jedi.settings` contract; fail with structured reason.
    - Rope: verify `import rope.base.project` and `import rope.refactor.rename`.
  - Treat probe failure as first-class unsupported mode and gate semantic features consistently.

---

### 2) Navigation/reference silently hide semantic failures and return incorrect results

- **Location**
  - `app/intelligence/navigation_service.py:53-54, 75`
  - `app/intelligence/reference_service.py:61-62, 81`
- **What the problem is**
  - Both services wrap semantic calls in broad `except Exception` and silently switch to heuristic fallback.
  - This masks runtime failures and reports approximate metadata as if operation succeeded.
- **Failure scenario (reproducible)**
  1. Run:
     ```bash
     python3 run_tests.py --import-mode=importlib tests/integration/intelligence/test_semantic_navigation_integration.py::test_lookup_definition_with_cache_resolves_imported_symbol_from_source_context
     ```
  2. Failure assertion from junit:
     - expected `result.metadata.source == "semantic"`
     - actual `result.metadata.source == "approximate"`
  3. Same pattern reproduces for references:
     ```bash
     python3 run_tests.py --import-mode=importlib tests/integration/intelligence/test_semantic_navigation_integration.py::test_find_references_uses_semantic_binding_identity
     ```
- **Blast radius**
  - Incorrect go-to-definition/reference targeting under unresolved/shadowing cases.
  - Silent degradation makes root-cause diagnosis hard for users and maintainers.
- **Proposed fix**
  - Catch only expected semantic “unsupported” states; do **not** blanket-catch runtime failures.
  - When runtime init fails, return explicit metadata (`source="semantic_unavailable"` + reason) and surface diagnostic warning in UI.
  - Add tests asserting runtime failure is visible and not silently converted to approximate success.

---

### 3) Run-project missing-entry flow bypasses preflight and blocks in modal prompt

- **Location**
  - `app/shell/main_window.py:3185-3191, 3273-3315`
  - `app/support/preflight.py:59, 308`
  - `tests/integration/shell/test_run_preflight_integration.py:101-135`
- **What the problem is**
  - `_handle_run_project_action()` resolves/repairs entrypoint first (`_resolve_project_entry_for_project_run`), which may open `QInputDialog.getItem` (`main_window.py:3310`) before preflight.
  - Preflight already has explicit `run.entry_not_found` reporting (`preflight.py:308`), but this path is bypassed.
- **Failure scenario (reproducible)**
  1. Run:
     ```bash
     python3 run_tests.py -vv --import-mode=importlib tests/integration/shell/test_run_preflight_integration.py::test_run_project_preflight_opens_runtime_center_for_missing_entry
     ```
  2. Test stalls waiting on modal path (command exceeded timeout and remained running with spawned child processes).
  3. Expected behavior in test (`...:135`) is Runtime Center issue `run.entry_not_found`, but modal replacement prompt path prevents that.
- **Blast radius**
  - Non-interactive/headless flows can hang.
  - User error handling is inconsistent (modal prompt vs Runtime Center preflight issue).
- **Proposed fix**
  - Make run/debug project actions preflight-first:
    - pass current configured entry directly to preflight
    - if missing, show Runtime Center issue (`run.entry_not_found`) and stop
  - Keep entry-repair prompt in explicit “Set Entry Point” workflow, not automatic run path.

---

### 4) Test shutdown helper leaks run/repl/plugin processes

- **Location**
  - `testing/main_window_shutdown.py:8-15`
  - `app/shell/main_window.py:5354-5362`
  - `app/shell/main_window.py:720-723, 5042`
- **What the problem is**
  - Test helper calls only `_begin_shutdown_teardown()` and does not invoke `_stop_active_run_before_close()`.
  - Real close path stops REPL and plugin runtime (`main_window.py:5361-5362`); helper does not.
- **Failure scenario (reproducible)**
  1. Run long/interactive shell integration tests repeatedly (or the preflight test above).
  2. Observe lingering processes (`run_plugin_host.py`, `run_runner.py`, `run_tests.py`) via `ps`.
  3. Subsequent test runs stall/hang with orphan processes still alive.
- **Blast radius**
  - CI/dev reliability degradation and flaky hangs.
  - Harder diagnosis because leaked subprocesses are outside test assertion surface.
- **Proposed fix**
  - Update helper to mirror close-event shutdown sequence:
    - `_begin_shutdown_teardown()`
    - `_stop_active_run_before_close()`
  - Add unit/integration assertion that no REPL/plugin host remains after helper teardown.

---

### 5) Plugin job event handler exceptions are swallowed silently

- **Location**
  - `app/plugins/runtime_manager.py:304-309`
- **What the problem is**
  - If a workflow job event handler raises, exception is caught and ignored (`except Exception: return True`) with no log/error propagation.
- **Failure scenario (reproducible)**
  1. Start a workflow job with an event callback that raises.
  2. Manager still returns successful job result and no runtime error is surfaced.
  3. Reproduction script output: `result {'done': True}` despite handler failure.
- **Blast radius**
  - Plugin integration errors disappear from diagnostics.
  - UI state can diverge from backend job reality without operator visibility.
- **Proposed fix**
  - Log handler exception with provider/job context.
  - Track handler failure state on job and surface as warning/error event to caller.
  - Add tests validating exception logging and surfaced failure signal.

---

## Quick wins (high severity, low effort)

1. **Harden semantic runtime probe contracts** (Issue #1)  
   Add explicit capability checks for Jedi/Rope submodules during initialization and return structured unsupported reasons.

2. **Remove silent semantic fallback on runtime exceptions** (Issue #2)  
   Replace blanket `except Exception` in navigation/reference with explicit semantic-unavailable result metadata and UI warning hook.

3. **Preflight-first run-project path** (Issue #3)  
   Ensure missing entrypoint is reported as `run.entry_not_found` in Runtime Center without requiring modal prompt in run action.

4. **Fix teardown helper leakage** (Issue #4)  
   Include `_stop_active_run_before_close()` in `shutdown_main_window_for_test` to prevent orphan REPL/plugin processes.

---

## Test gaps and recommended additions

1. **Semantic runtime contract tests are incomplete**
   - Gap: no focused unit test asserting runtime probe validates required Jedi/Rope APIs (not just top-level import).
   - Add:
     - `tests/unit/intelligence/test_jedi_runtime.py::test_initialize_jedi_runtime_requires_script_api`
     - `tests/unit/intelligence/test_refactor_runtime.py::test_initialize_refactor_runtime_requires_rope_project_modules`

2. **No explicit coverage that semantic runtime failure is surfaced (not silently downgraded)**
   - Gap: integration tests catch metadata mismatch indirectly, but no contract test for error visibility path.
   - Add:
     - navigation/reference unit tests with injected semantic runtime failure asserting explicit metadata + warning path.

3. **Run-preflight missing-entry non-interactive behavior not guarded**
   - Gap: existing integration test asserts expected Runtime Center issue but currently hangs; no guard against modal prompt in run action.
   - Add:
     - unit test asserting `_handle_run_project_action` does not call prompt path when entry is missing.
     - integration test with monkeypatched `QInputDialog.getItem` fail-fast to guarantee no modal path.

4. **Shutdown helper process cleanup has no direct assertion**
   - Gap: helper currently does partial teardown and no test asserts subprocess/repl/plugin stop semantics.
   - Add:
     - unit test for `shutdown_main_window_for_test` verifying `_repl_manager.shutdown` and `_plugin_runtime_manager.stop` are called.

5. **Plugin job-event handler exception observability missing**
   - Gap: tests cover success/timeouts but not callback exception reporting.
   - Add:
     - unit test injecting failing `on_event` callback and asserting log/warning event emitted.

---

## Baseline and targeted verification evidence

- Baseline command executed:
  ```bash
  python3 run_tests.py -v --import-mode=importlib
  ```
  Result: semantic integration tests failed early; later run-preflight lane stalled.

- Targeted failing evidence:
  - semantic navigation metadata mismatch (`approximate` vs expected `semantic`)
  - semantic rename/perf failures from `RuntimeError: AttributeError: module 'jedi' has no attribute 'settings'`
  - runtime-parity failure from `ModuleNotFoundError: No module named 'rope.base.project'`

- Targeted passing evidence (non-affected areas):
  - `tests/unit/persistence/test_local_history_store.py` → all passed
  - `tests/unit/plugins/test_runtime_manager.py` → all passed
