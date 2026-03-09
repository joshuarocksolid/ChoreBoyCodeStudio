# BUG_AUDIT_REPORT

Date: 2026-03-09

---

## 2026-03-09 addendum — packaging/install contract clarification

### Executive summary update

The distribution installer workflow for **Code Studio itself** was functioning in code but under-documented and easy to misread.

This audit pass clarified and documented the actual ChoreBoy contract:

- users copy the full distribution folder into `/home/default/`
- users run the installer from that copied folder
- users choose the final install location for Code Studio
- the installed `.desktop` launcher **hardcodes that chosen final location**

### Confirmed bug / implementation gap

## 11) Distribution packaging contract was under-documented and easy to misapply
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `package.py`, `packaging/install.py`, `docs/PACKAGING.md`, `docs/ARCHITECTURE.md`  
- **Evidence:** the installer already wrote a launcher hardcoded to the chosen install directory, but generated instructions and developer docs did not clearly explain:
  - required staging in `/home/default/`
  - need to keep the installer folder together
  - distinction between installer package location and final installed app location
- **Reproduction steps:**
  1. Inspect `package.py` generated installer assets and `packaging/install.py`.
  2. Observe that installed `.desktop` entries hardcode the chosen install path.
  3. Observe that prior generated instructions did not explicitly describe the ChoreBoy-specific staging/install contract.
- **Suggested fix:** document the packaging model explicitly in both generated user instructions and developer-facing docs, and reinforce it in installer UI copy.
- **Fix applied:** ✅ documented and tested on 2026-03-09

## 12) Imported `pyproject` package-callable targets silently resolved to `__init__.py`
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/project/project_service.py`, `tests/unit/project/test_project_service.py`, `tests/integration/project/test_project_import_open.py`  
- **Evidence:** for `[project.scripts] demo = "demo_pkg:main"`, project import previously inferred `default_entry = src/demo_pkg/__init__.py`; running the imported project exited `0` with no output because `main()` was never invoked.
- **Reproduction steps:**
  1. Create project with `pyproject.toml` script target `demo_pkg:main`.
  2. Put `main()` in `src/demo_pkg/__init__.py`.
  3. Import project through `open_project(...)`.
  4. Observe inferred entry file is `__init__.py`.
  5. Run imported project and observe silent success with no callable execution.
- **Why it happens:** module-reference resolution treated package `__init__.py` as though it were a directly runnable script entrypoint, but runner semantics execute files with `runpy.run_path(...)` and do not call exported callables.
- **Suggested fix:** never infer package `__init__.py` as a runnable entrypoint for console-script targets; fall back to real runnable files when available, otherwise fail with actionable validation.
- **Fix applied:** ✅ on 2026-03-09

## 13) Built-in pytest runner diverged from documented runtime contract
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/run/test_runner_service.py`, `tests/unit/run/test_test_runner_service.py`  
- **Evidence:** prior built-in command for this repo was:
  - `['/opt/freecad/AppRun', '-c', "import sys;import pytest;sys.exit(pytest.main(['-q']))"]`
  - running `run_pytest_project('/workspace')` returned `RETURN_CODE 2`
  - the repo’s documented/supported contract requires `run_tests.py` and `--import-mode=importlib`
- **Reproduction steps:**
  1. Call `run_pytest_project('/workspace')`.
  2. Inspect `result.command`.
  3. Observe missing `run_tests.py` and missing `--import-mode=importlib`.
  4. Observe return code `2` instead of the real test-result code.
- **Why it happens:** helper built raw `pytest.main(['-q'])` AppRun payloads and attempted `.venv` discovery instead of following repository/runtime rules.
- **Suggested fix:** normalize args with `--import-mode=importlib`, prefer project-local `run_tests.py` when present, and stop implicit `.venv` runtime discovery.
- **Fix applied:** ✅ on 2026-03-09

## 14) Plugin runtime failures were not persisted to plugin log diagnostics
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/plugins/runtime_manager.py`, `app/shell/plugins_panel.py`, `tests/unit/plugins/test_runtime_manager.py`  
- **Evidence:** before fix, runtime failures only updated in-memory `last_error` / registry metadata; there was no persistent plugin host log file despite `global_plugins_logs_dir()` existing and acceptance/docs expecting log diagnostics.
- **Reproduction steps:**
  1. Trigger `PluginRuntimeManager._handle_event(...)` with stderr output and host exit.
  2. Inspect plugin state directory.
  3. Observe no persistent plugin host log was written before the fix.
- **Why it happens:** runtime manager consumed stderr/exit events but did not persist them to disk or expose a stable log path in diagnostics UI.
- **Suggested fix:** persist plugin host stderr/exit diagnostics under `plugins/logs/plugin_host.log` and surface the log path / failure details in plugin diagnostics UI.
- **Fix applied:** ✅ on 2026-03-09

## 15) Default delete behavior contradicted the UI warning and depended on hidden trash semantics
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/project/file_operations.py`, `tests/unit/project/test_file_operations.py`  
- **Evidence:** project tree delete confirmations warned `This action cannot be undone.`, but `delete_path(...)` defaulted to `use_trash=True`, routing deletes through hidden `~/.local/share/Trash/files` and silently falling back to permanent deletion on `OSError`.
- **Reproduction steps:**
  1. Inspect `delete_path(...)` default parameters and `ProjectTreeActionCoordinator.handle_delete(...)`.
  2. Compare with the UI delete confirmation wording in `MainWindow`.
  3. Observe mismatch between user-facing semantics and implementation.
- **Why it happens:** filesystem helper defaulted to trash semantics, while the UI and constrained-environment behavior already treated delete as irreversible.
- **Suggested fix:** make default delete semantics permanent so code matches the existing UI contract; keep trash behavior explicit/opt-in only.
- **Fix applied:** ✅ on 2026-03-09

## Executive summary

Deep skeptical audit identified **15 confirmed bugs / implementation failures with concrete evidence**, plus **1 test-contract mismatch**.

Highest-value confirmed issues addressed in this pass:
- ChoreBoy distribution installer packaging contract was under-documented and easy to misuse
- imported `pyproject.toml` package-callable targets silently resolved to `__init__.py`
- built-in pytest runner diverged from the documented `run_tests.py` + `--import-mode=importlib` contract
- plugin runtime failures were not persisted to plugin log diagnostics
- default delete behavior contradicted the UI’s permanent-delete warning and depended on hidden trash semantics
- a stale drag/drop test failure masked a test-contract mismatch rather than a product bug

Previously confirmed audit fixes from the earlier pass remain included here:
- runner lifecycle race that could orphan active processes
- plugin install/runtime traversal vectors
- project-tree path escape and uncaught filesystem errors
- packaging entrypoint validation holes
- support-bundle log-path gaps

Final validation state:
- `python3 run_tests.py -v --import-mode=importlib` -> **passed**
- targeted suites for packaging, project import, pytest runner, plugins, and drag/drop all **passed**
- `pyright` is available but remains dominated by pre-existing PySide stub noise plus a smaller set of real type issues that were not the primary target of this audit pass

---

## Confirmed bugs

## 1) Stale process exit clobbers active runner state
- **Severity:** High  
- **Confidence:** High  
- **File(s):** `app/run/process_supervisor.py`  
- **Evidence:** stress repro showed active second PID alive while supervisor reported `is_running=False`, `state=exited`, `process_id=None`; stale events only.
- **Reproduction steps:**
  1. Start a fast process (`python -c pass`).
  2. Immediately start a second long-running process.
  3. Observe stale waiter from first process races with second process state.
- **Why it happens:** `_wait_for_exit` unconditionally reset `self._process`/state and global stream resources even when invoked for stale process.
- **Suggested fix:** isolate resources per PID and ignore stale waiter events unless process is still active.
- **Fix applied:** ✅ commit `925ec32`

---

## 2) Plugin install path traversal via manifest `id` and `version`
- **Severity:** High  
- **Confidence:** High  
- **File(s):** `app/plugins/manifest.py`, `app/bootstrap/paths.py`, `app/plugins/installer.py`  
- **Evidence:** installing plugin with `id='../../escape_plugin'` and/or `version='../../escape_version'` created install paths outside expected `plugins/installed/<id>/<version>` subtree.
- **Reproduction steps:**
  1. Create plugin manifest with traversal-like `id`/`version`.
  2. Call `install_plugin(...)`.
  3. Inspect resulting install path; it escapes install root.
- **Why it happens:** manifest only required non-empty strings; path helper joined raw values directly.
- **Suggested fix:** strict identifier/version validation + path-component safety checks.
- **Fix applied:** ✅ commit `6c89d68`

---

## 3) Runtime plugin entrypoint can escape plugin root
- **Severity:** High  
- **Confidence:** High  
- **File(s):** `app/plugins/manifest.py`, `app/plugins/host_runtime.py`  
- **Evidence:** before fix, plugin with `runtime.entrypoint="../../outside_runtime.py"` loaded and executed handler from external file:
  - `handler_found True`
  - `handler_result {'outside_loaded': True, ...}`
- **Reproduction steps:**
  1. Install plugin declaring traversal runtime entrypoint.
  2. Place executable Python file at resolved external location.
  3. Load runtime handlers and invoke command.
- **Why it happens:** no manifest/runtime loader boundary enforcement for resolved entrypoint path.
- **Suggested fix:** reject traversal/absolute entrypoints in manifest and enforce runtime loader relative-to-plugin-root check.
- **Fix applied:** ✅ commit `b2ee677`

---

## 4) Project tree creation/rename accepted path-like names and leaked exceptions
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/shell/project_tree_action_coordinator.py`  
- **Evidence:**
  - `handle_new_file(destination, "../escape.py")` created file outside intended boundary.
  - `handle_rename(..., "../bad")` raised uncaught `ValueError`.
  - folder move into child surfaced uncaught move error.
- **Reproduction steps:**
  1. Invoke tree actions with path-like user input names.
  2. Observe escape behavior or uncaught exceptions.
- **Why it happens:** no child-name validation + no exception guards around filesystem move/copy edge cases.
- **Suggested fix:** validate names as child components only; catch move/copy/rename errors and return user-facing messages.
- **Fix applied:** ✅ commit `a732058`

---

## 5) Packager reports success with missing entry file
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/packaging/packager.py`  
- **Evidence:** `package_project(..., entry_file='missing.py')` returned success and generated launcher referencing non-existent file.
- **Reproduction steps:**
  1. Create project containing `main.py` only.
  2. Package with missing entry file path.
  3. Observe success result and broken artifact.
- **Why it happens:** no preflight validation that entrypoint exists and is inside project root.
- **Suggested fix:** resolve entry path, enforce in-project boundary, require existing file.
- **Fix applied:** ✅ commit `b96d8ea`

---

## 6) Plugin export archive filename used unsanitized id/version
- **Severity:** Low-Medium  
- **Confidence:** High  
- **File(s):** `app/plugins/exporter.py`  
- **Evidence:** malformed plugin identifiers (e.g. `../evil`) produced invalid path behavior during export before fix.
- **Reproduction steps:**
  1. Insert malformed plugin id/version in registry (or call exporter with malformed values).
  2. Call `export_installed_plugin(...)`.
  3. Observe archive path misuse/error.
- **Why it happens:** archive filename used raw id/version string concatenation.
- **Suggested fix:** validate/sanitize archive filename components.
- **Fix applied:** ✅ (post-audit hardening)

---

## 7) Runtime plugin trust prompt was not enforced at runtime load
- **Severity:** Medium-High  
- **Confidence:** High  
- **File(s):** `app/plugins/host_runtime.py`, `app/plugins/trust_store.py`  
- **Evidence:** before fix, an enabled runtime plugin with no trust entry still loaded command handlers.
- **Reproduction steps:**
  1. Add runtime plugin to registry as enabled.
  2. Do not set trust (`trusted_runtime_plugins` remains false/absent).
  3. Call `load_runtime_command_handlers(...)`.
  4. Observe runtime handler present.
- **Why it happens:** loader checked enabled + compatibility but never checked trust store.
- **Suggested fix:** gate runtime module loading on `is_runtime_plugin_trusted(...)`.
- **Fix applied:** ✅ (post-audit hardening)

---

## 8) Support bundle omitted app log when logging used fallback tier
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/bootstrap/logging_setup.py`, `app/support/support_bundle.py`  
- **Evidence:** when primary state-root log path was unwritable and fallback log path was active, support bundle did not include `global_logs/app.log` before fix.
- **Reproduction steps:**
  1. Force `configure_app_logging(state_root=...)` into fallback tier.
  2. Write log line to fallback path.
  3. Build support bundle.
  4. Inspect archive entries (app log missing before fix).
- **Why it happens:** support bundle looked only at canonical primary path, not current active logging destination.
- **Suggested fix:** expose active configured log path from logging bootstrap and use that in support bundle generation.
- **Fix applied:** ✅ (post-audit hardening)

---

## 9) Active log-path lookup was not scoped by state root
- **Severity:** Low-Medium  
- **Confidence:** High  
- **File(s):** `app/bootstrap/logging_setup.py`  
- **Evidence:** active log path cache was global and returned regardless of caller-requested state root.
- **Reproduction steps:**
  1. Configure logging with `state_root=A`.
  2. Request active log path for `state_root=B`.
  3. Observe path from A returned before fix.
- **Why it happens:** `_ACTIVE_LOG_PATH` had no associated state-root context check.
- **Suggested fix:** store active state-root alongside active log path and enforce root match in getter.
- **Fix applied:** ✅ (post-audit hardening)

---

## 10) Packager allowed entrypoint paths excluded from packaged payload
- **Severity:** Medium  
- **Confidence:** High  
- **File(s):** `app/packaging/packager.py`  
- **Evidence:** packaging succeeded with `entry_file='cbcs/logs/run_entry.py'` even though `cbcs/logs` is excluded, producing artifact with missing entrypoint.
- **Reproduction steps:**
  1. Create project containing `cbcs/logs/run_entry.py`.
  2. Run `package_project(..., entry_file='cbcs/logs/run_entry.py')`.
  3. Observe success result and absent packaged entry file.
- **Why it happens:** entrypoint existence check did not verify inclusion after exclusion filters.
- **Suggested fix:** reject entrypoint when resolved path is filtered by packager exclusion rules.
- **Fix applied:** ✅ (post-audit hardening)

---

## Likely bugs / strong suspicions

- No additional high-confidence likely bugs remain after the applied fixes in this audit pass.

---

## Implementation gaps

## 1) Coverage concentration gap in high-complexity shell/runtime surfaces
- **Severity:** Medium  
- **Confidence:** Medium  
- **Evidence:** several high-complexity modules have limited direct test granularity (notably `app/shell/main_window.py`, `app/treesitter/*`, parts of plugin runtime wiring).
- **Gap:** high behavior complexity with relatively sparse focused regression tests increases change risk.
- **Suggested fix:** add focused unit/integration seams around complex orchestration paths.

## 2) Pyright remains noisy enough to hide smaller real issues
- **Severity:** Low-Medium  
- **Confidence:** High  
- **Evidence:** full `pyright` output is still dominated by PySide/PyQt stub issues and broad attribute-access noise, reducing its usefulness as a high-signal regression tool.
- **Gap:** smaller real typing regressions can be buried in the current baseline.
- **Suggested fix:** either suppress known PySide false positives more aggressively or carve out targeted typed modules with cleaner reporting.

---

## Risky areas not fully audited

- Full GUI interaction matrix in `app/shell/main_window.py` (very large orchestrator).
- Tree-sitter runtime loader/highlighter behavior under unusual vendor/runtime failures.
- End-to-end plugin host IPC under repeated crash/restart + concurrent command pressure.
- Cross-platform path semantics for plugin export/import edge cases beyond Linux.
- Optional explicit `use_trash=True` behavior on a real ChoreBoy target.

---

## Code smell / maintainability risk

## 1) One prior full-suite failure was a test-contract mismatch, not a product bug
- **Severity:** Low  
- **Confidence:** High  
- **File(s):** `tests/unit/shell/test_project_tree_action_coordinator.py`, `app/project/project_tree_widget.py`, `app/shell/project_tree_action_coordinator.py`  
- **Evidence:** failing test used nonexistent target path, but real drag/drop contract only passes existing tree-item paths from `itemAt(event.pos())`.
- **Reproduction steps:**
  1. Compare `ProjectTreeWidget.dropEvent()` target extraction with the old unit test inputs.
  2. Observe mismatch between real widget contract and test assumptions.
- **Suggested fix:** keep tests aligned with the real widget callback contract and avoid synthetic target paths that cannot arise from the UI.
- **Fix applied:** ✅ test corrected on 2026-03-09

---

## Fixes applied

1. `925ec32` — Harden supervisor against stale exit races  
2. `6c89d68` — Block plugin install path traversal inputs  
3. `a732058` — Validate project tree names and move edge cases  
4. `b96d8ea` — Fail packaging when entrypoint is invalid  
5. `b2ee677` — Constrain plugin runtime entrypoint paths  
6. `5ccdff4` — Harden plugin exporter archive path components  
7. `2ad86e8` — Enforce runtime plugin trust at handler load  
8. `4e4a9cc` — Include active fallback app log in support bundles  
9. `a5a1eba` — Scope active log lookup by state root  
10. `05b49ac` — Reject excluded packaging entrypoint paths  
11. `8e83a14` — Clarify ChoreBoy installer packaging contract  
12. `dd18bb5` — Fix pyproject package entry inference  
13. `17aa650` — Align built-in pytest runner contract  
14. `f89ced1` — Persist plugin runtime diagnostics  
15. `9700bb2` — Align drag-drop test with widget contract  
16. `TBD` — Match default delete semantics to permanent-delete UI contract

---

## Suggested next tests

1. Run plugin manager manual acceptance:
   - install/enable runtime plugin
   - safe mode toggle
   - repeated runtime failure quarantine flow
2. Run manual tree-file operations in GUI:
   - invalid names, drag-drop folder to child, bulk cut/paste edge cases
3. Exercise optional explicit `use_trash=True` behavior on a real ChoreBoy target:
   - verify whether hidden `~/.local/share/Trash/files` is reliable when explicitly requested
4. Package and launch smoke test with valid and invalid entrypoint paths.
5. Run targeted pyright review on touched modules after reducing PySide noise.

