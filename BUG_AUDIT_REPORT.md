# BUG_AUDIT_REPORT

Date: 2026-03-08

## Executive summary

Deep skeptical audit identified **10 confirmed bugs** with concrete evidence and reproductions.  
All 10 were fixed with minimal scoped changes and pushed as separate commits.

Highest-impact issues were:
- runner lifecycle race that could orphan active processes
- plugin path traversal vectors during install/runtime loading
- project-tree operations permitting path escapes and uncaught move/rename exceptions
- packager producing successful artifacts with broken entrypoints

Tooling limitations in this environment:
- `pytest` unavailable in both AppRun and system Python
- `pyright` unavailable

Validation therefore used:
- deterministic repro scripts
- static code-path proof
- syntax compilation (`compileall`)

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

- No additional high-confidence likely bugs remain after applied hardening in this audit pass.

---

## Implementation gaps

## 1) Validation toolchain unavailable in environment
- **Severity:** Medium (process/testing risk)  
- **Confidence:** High  
- **Evidence:**
  - `python3 run_tests.py -q` -> missing pytest
  - `python3 -m pytest -q` -> missing pytest
  - `pyright --version` -> command not found
- **Gap:** unable to run full automated regression suite in this environment.
- **Suggested fix:** restore test/type tooling in CI/dev image and run targeted suites for changed modules.

## 2) Coverage concentration gap in high-complexity shell/runtime surfaces
- **Severity:** Medium  
- **Confidence:** Medium  
- **Evidence:** several high-complexity modules have limited direct test granularity (notably `app/shell/main_window.py`, `app/treesitter/*`, parts of plugin runtime wiring).
- **Gap:** high behavior complexity with relatively sparse focused regression tests increases change risk.
- **Suggested fix:** add focused unit/integration seams around complex orchestration paths.

---

## Risky areas not fully audited

- Full GUI interaction matrix in `app/shell/main_window.py` (very large orchestrator).
- Tree-sitter runtime loader/highlighter behavior under unusual vendor/runtime failures.
- End-to-end plugin host IPC under repeated crash/restart + concurrent command pressure.
- Cross-platform path semantics for plugin export/import edge cases beyond Linux.

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

---

## Suggested next tests

1. Restore pytest and run:
   - `python3 run_tests.py -v tests/unit/run/test_process_supervisor.py`
   - `python3 run_tests.py -v tests/unit/plugins/`
   - `python3 run_tests.py -v tests/unit/shell/test_project_tree_action_coordinator.py`
   - `python3 run_tests.py -v tests/unit/packaging/test_packager.py`
2. Run plugin manager manual acceptance:
   - install/enable runtime plugin
   - safe mode toggle
   - repeated runtime failure quarantine flow
3. Run manual tree-file operations in GUI:
   - invalid names, drag-drop folder to child, bulk cut/paste edge cases
4. Package and launch smoke test with valid and invalid entrypoint paths.

