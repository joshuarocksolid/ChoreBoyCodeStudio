# AUDIT_LOG

Date: 2026-03-08  
Auditor mode: deep skeptical audit (evidence-first)

## Current final status (2026-03-09)
- Branch: `cursor/adversarial-code-audit-9904`
- Full automated validation:
  - `python3 run_tests.py -v --import-mode=importlib` -> **passed**
- High-value fixes landed for:
  - ChoreBoy installer packaging contract documentation/behavior
  - imported `pyproject` package-callable inference
  - built-in pytest runner contract drift
  - plugin runtime log diagnostics persistence
  - drag/drop unit-test contract mismatch
- Remaining non-fixed finding explicitly carried in the report:
  - none currently at the same confidence level; remaining risk areas are called out in the report

---

## 2026-03-09 addendum — ChoreBoy installer packaging contract

### User clarification incorporated
- The relevant "packaging" workflow for this review is the **Code Studio distribution installer**:
  - `package.py`
  - `packaging/install.py`
- Intended contract on ChoreBoy:
  - user copies the entire distribution folder into `/home/default/`
  - user runs the bundled installer from that copied folder
  - installer prompts for the final location where Code Studio should live
  - installed `.desktop` launcher hardcodes that chosen final location

### Evidence of prior ambiguity
- The repo previously had:
  - installer implementation already hardcoding the chosen final install path
  - generated install instructions that only said "copy to your ChoreBoy Home Folder"
  - no dedicated developer doc explaining the distinction between:
    - installer package staging location
    - final installed application location
- This created a documentation/mental-model gap for future developers and reviewers.

### Commands run

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/packaging/test_distribution_installer.py`
- Result: **passed**
- Coverage added for:
  - install instructions explicitly requiring `/home/default/` staging
  - bundled installer launcher continuing to resolve from installer folder
  - installed launcher hardcoding chosen install directory
  - warning when installer package is not staged under `/home/default/`

#### `"/opt/freecad/AppRun" -c "<installer contract evidence snippet>"`
- Result: **passed**
- Key output:
  - install instructions now begin with:
    - `Copy this entire folder into /home/default/ on the ChoreBoy.`
    - `Keep the entire folder together.`
  - non-home staging warning now explains:
    - installer package should be copied into `/home/default/`
  - installed launcher `Exec=` now shows a hardcoded final install path:
    - `root='/home/default/tools/code_studio'`

### Fixes implemented
- `package.py`
  - extracted helper builders for installer desktop entry and install instructions
  - updated generated `INSTALL.txt` to explicitly require `/home/default/` staging
  - documented that the installer folder must stay together
  - documented that installed launchers hardcode the chosen install directory
- `packaging/install.py`
  - added explicit helper for installed desktop-entry generation
  - added staging-location warning helper for packages not copied under `/home/default/`
  - updated wizard copy to explain:
    - staging in `/home/default/`
    - final install directory choice
    - hardcoded launcher target semantics
    - rerun-installer requirement after moving installed files
- `docs/PACKAGING.md`
  - added developer-facing source-of-truth documentation for the ChoreBoy-specific packaging/install workflow
- `docs/ARCHITECTURE.md`
  - registered `PACKAGING.md` in canonical file ownership

---

## 2026-03-09 addendum — imported `pyproject` package-callable inference

### Confirmed behavior before fix
- Reproduction project:
  - `pyproject.toml` with:
    - `[project.scripts]`
    - `demo = "demo_pkg:main"`
  - package file:
    - `src/demo_pkg/__init__.py` defining `main()`
- Prior result:
  - imported project metadata inferred `default_entry = src/demo_pkg/__init__.py`
  - running the imported project exited `0`
  - no user output was produced because `runpy.run_path(__init__.py)` never called `main()`

### Commands run after fix

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/project/test_project_service.py tests/integration/project/test_project_import_open.py`
- Result: **passed**
- Coverage added for:
  - package-callable `pyproject` targets no longer mapping silently to `__init__.py`
  - fallback to runnable file (`run.py`) when available
  - clear validation failure when only non-runnable `__init__.py` exists

#### `python3 - <<'PY' ...` (package-callable pyproject repro)
- Result: **passed**
- Key output:
  - `DEFAULT_ENTRY run.py`
  - runner output included `RUN_FALLBACK_OK`
  - runner output did **not** include package callable side effects from `__init__.py`

### Fixes implemented
- `app/project/project_service.py`
  - stopped treating package `__init__.py` as a valid inferred runnable entrypoint for `pyproject` script targets
  - excluded `__init__.py` from generic top-level/recursive runnable-file fallback
  - added clearer error message when Python files exist but no runnable entry file can be inferred
- tests added/updated:
  - `tests/unit/project/test_project_service.py`
  - `tests/integration/project/test_project_import_open.py`

---

## 2026-03-09 addendum — built-in pytest runner contract drift

### Confirmed behavior before fix
- `app/run/test_runner_service.py` previously:
  - built direct AppRun payloads using `pytest.main(['-q'])`
  - omitted required `--import-mode=importlib`
  - preferred `.venv` runtimes despite repo/runtime guidance saying no virtualenv
  - ignored repository-local `run_tests.py`
- Reproduction:
  - `run_pytest_project('/workspace')` returned:
    - `RETURN_CODE 2`
    - `FAILURE_COUNT 0`
  - built command was:
    - `['/opt/freecad/AppRun', '-c', "import sys;import pytest;sys.exit(pytest.main(['-q']))"]`

### Commands run after fix

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/run/test_test_runner_service.py`
- Result: **passed**
- Coverage now verifies:
  - `--import-mode=importlib` is always included
  - `run_tests.py` is preferred when present in the project root
  - runtime selection no longer walks `.venv` paths by default
  - `CBCS_PYTEST_EXECUTABLE` still works as an explicit override

#### `python3 -c "from app.run.test_runner_service import run_pytest_project; ..."`
- Result: **passed**
- Key output after fix:
  - `RETURN_CODE 1`
  - command:
    - `['/opt/freecad/AppRun', '-c', "import runpy, sys; ... runpy.run_path('/workspace/run_tests.py', run_name='__main__')"]`
- This changed the repo repro from an immediate collection/bootstrap failure (`2`) to the real failing-test result (`1`).

### Fixes implemented
- `app/run/test_runner_service.py`
  - now injects `--import-mode=importlib` into pytest args
  - prefers project-local `run_tests.py` when present
  - removes implicit `.venv` runtime discovery
  - keeps `CBCS_PYTEST_EXECUTABLE` as the explicit override path
- tests updated:
  - `tests/unit/run/test_test_runner_service.py`

---

## 2026-03-09 addendum — plugin runtime diagnostics persistence

### Audit question
- Docs and acceptance expectations claimed runtime plugin failures should be visible in plugin status/log diagnostics.
- Before this pass, code search showed:
  - in-memory `PluginRuntimeManager.last_error`
  - registry `last_error` / `failure_count`
  - no persistent plugin host log writing despite `global_plugins_logs_dir()` helper existing

### Commands run

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/plugins/test_runtime_manager.py`
- Result: **passed**
- Coverage now verifies:
  - stderr is still captured as `last_error`
  - plugin host stderr is persisted to a log file
  - plugin host exit events are persisted to a log file

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/plugins`
- Result: **passed**

#### `python3 - <<'PY' ...` (plugin runtime log persistence repro)
- Result: **passed**
- Key output:
  - `LOG_PATH /tmp/.../state/plugins/logs/plugin_host.log`
  - log contents:
    - `stderr: boom`
    - `host exited return_code=3 terminated_by_user=False`

### Fixes implemented
- `app/plugins/runtime_manager.py`
  - now writes plugin host diagnostics to `plugins/logs/plugin_host.log`
  - logs stderr lines, command timeouts/failures, host reload/start/stop, and host exits
  - exposes `log_file_path` for diagnostics/UI use
- `app/shell/plugins_panel.py`
  - now includes failure-count/last-error details in displayed compatibility text when present
  - adds per-row tooltip details including plugin host log path
- tests updated:
  - `tests/unit/plugins/test_runtime_manager.py`

---

## 2026-03-09 addendum — drag/drop failing test mismatch and final suite status

### Failing baseline test analysis
- Baseline full-suite run originally failed only:
  - `tests/unit/shell/test_project_tree_action_coordinator.py::test_handle_drop_move_returns_oserror_message`
- Static/behavioral analysis:
  - `ProjectTreeWidget.dropEvent()` only passes an existing target item path from `itemAt(event.pos())`
  - the failing test passed a nonexistent target path (`/tmp/project/target`)
  - `handle_drop_move(...)` therefore correctly normalized destination back to the source parent and returned:
    - `Cannot move item onto itself.`
- Conclusion:
  - this was a **test-contract mismatch**, not a confirmed product bug

### Fix implemented
- Updated the unit test to use an actual existing target directory, matching the real tree-widget drag/drop contract.

### Validation commands

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_project_tree_action_coordinator.py`
- Result: **passed**

#### `python3 run_tests.py -v --import-mode=importlib`
- Result: **passed**
- Full suite now completes successfully in this environment after the audit fixes and the drag/drop test correction.

---

## 2026-03-09 addendum — delete semantics now match UI contract

### Confirmed behavior before fix
- `delete_path(...)` defaulted to `use_trash=True`
- project tree delete flows called `delete_path(target_path)` with that default
- UI confirmation text in `MainWindow` said:
  - `This action cannot be undone.`
- implementation therefore mismatched the user-facing contract and depended on hidden `~/.local/share/Trash/files`
- any `OSError` in trash handling silently fell back to permanent deletion

### Commands run

#### `python3 run_tests.py -v --import-mode=importlib tests/unit/project/test_file_operations.py tests/unit/project/test_bulk_file_operations.py`
- Result: **passed**
- Coverage now verifies:
  - default delete is permanent
  - explicit `use_trash=True` still moves to trash when requested
  - bulk delete callers using `use_trash=False` remain green

#### `python3 run_tests.py -v --import-mode=importlib`
- Result: **passed**

### Fix implemented
- `app/project/file_operations.py`
  - changed `delete_path(..., use_trash=False)` default to permanent delete
- `tests/unit/project/test_file_operations.py`
  - now asserts default delete matches permanent-delete semantics
  - keeps explicit trash behavior under `use_trash=True` covered

## 1) Baseline validation and environment reality

### Command: `python3 run_tests.py -q`
- Result: **failed**
- Output:
  - `ModuleNotFoundError: No module named 'pytest'`

### Command: `python3 -m pytest -q`
- Result: **failed**
- Output:
  - `/usr/bin/python3: No module named pytest`

### Command: `pyright --version`
- Result: **failed**
- Output:
  - `pyright: command not found`

### Command: `python3 -m compileall -q app run_editor.py run_runner.py run_plugin_host.py dev_launch_editor.py launcher.py`
- Result: **passed**

---

## 2) High-risk investigation trail

## 2.1 Runner/process lifecycle

### Target files
- `app/run/process_supervisor.py`
- `tests/integration/run/test_process_supervisor.py`

### Repro script (before fix)
- Stress-started a fast process followed by a second running process.
- Observed stale waiter clobbering active state.
- Evidence captured:
  - `pid2 alive True`
  - `supervisor_running False`
  - `state exited`
  - `process_id_prop None`
  - events: `running`, `running`, `exited`, `exit(0)` for stale process only

### Static proof
- `_wait_for_exit` unconditionally executed:
  - `self._process = None`
  - `self._state = "exited"`
- cleanup storage for reader threads/streams was process-global, allowing stale exit cleanup to touch active process resources.

### Fix implemented
- Per-process resource tracking keyed by PID.
- `_wait_for_exit` now ignores stale processes unless they are still active `self._process`.
- Stream/thread cleanup isolated per process.
- Added regression unit tests:
  - `tests/unit/run/test_process_supervisor.py`

### Post-fix verification
- Re-ran stress script (900 attempts): `race_detected False`

---

## 2.2 Plugin install/runtime safety (path traversal)

### Target files
- `app/plugins/manifest.py`
- `app/bootstrap/paths.py`
- `app/plugins/installer.py`

### Repro script (before fix)
- Created plugin manifest with:
  - `id: "../../escape_plugin"`
  - `version: "../../escape_version"`
- Installed plugin via `install_plugin(...)`.
- Observed install path escaped expected `plugins/installed/` subtree.

### Static proof
- `parse_plugin_manifest` only required non-empty string for `id` and `version`.
- `plugin_install_dir` directly joined `installed_root / plugin_id / version` with no path-component safety.

### Fix implemented
- Added strict manifest validation:
  - `id` allowed chars: letters/numbers/dot/underscore/hyphen
  - `version` allowed chars: letters/numbers/dot/underscore/plus/hyphen
- Added safe path-component guard in `plugin_install_dir`.
- Added tests:
  - `tests/unit/plugins/test_manifest.py`
  - `tests/unit/plugins/test_installer.py`
  - `tests/unit/bootstrap/test_paths.py`

### Post-fix verification
- Re-ran malicious manifest install:
  - `blocked id must use only letters, numbers, dots, underscores, or hyphens...`
- Re-ran malicious version install:
  - `blocked version must use only letters, numbers, dots, underscores, plus, or hyphens...`

---

## 2.3 Project tree filesystem action hardening

### Target files
- `app/shell/project_tree_action_coordinator.py`

### Repro script (before fix)
1. `handle_new_file(destination, "../escape.py")`
   - created file outside intended directory boundary.
2. `handle_rename(source, "../bad")`
   - raised `ValueError`, bubbled up.
3. `handle_drop_move(folder, folder/child)`
   - `shutil.Error` bubbled up.

### Fix implemented
- Added strict child-name validation for new file/folder/rename.
- Added graceful error handling for rename/move/copy filesystem exceptions.
- Added explicit guard: cannot move folder into itself.
- Added regression tests in:
  - `tests/unit/shell/test_project_tree_action_coordinator.py`

### Post-fix verification
- Re-ran repro script:
  - `err_new File name cannot include path separators.`
  - `escaped_exists False`
  - `err_rename New name cannot include path separators.`
  - `err_drop Cannot move a folder into itself.`

---

## 2.4 Packaging contract integrity

### Target files
- `app/packaging/packager.py`
- `tests/unit/packaging/test_packager.py`

### Repro script (before fix)
- Called `package_project(..., entry_file='missing.py')`
- Returned `success=True` and generated desktop launcher referencing nonexistent entrypoint.

### Fix implemented
- Added entrypoint validation in `package_project`:
  - entry must be non-empty
  - entry must resolve **inside project root**
  - entry must exist and be a file
- Normalized entry path passed to desktop launcher generation.
- Added tests:
  - missing entry fails
  - outside-project absolute entry fails

### Post-fix verification
- `success False`
- `error Entry file not found in project: missing.py`
- Valid entry still succeeds.

---

## 2.5 Runtime plugin entrypoint escape

### Target files
- `app/plugins/manifest.py`
- `app/plugins/host_runtime.py`
- `tests/unit/plugins/test_host_runtime.py`

### Repro script (before fix)
- Installed plugin with:
  - `runtime.entrypoint: "../../outside_runtime.py"`
- Created `outside_runtime.py` outside plugin folder.
- Called `load_runtime_command_handlers(...)`.
- Observed command handler loaded and executed external file.

### Evidence snippet
- `handler_found True`
- `handler_result {'outside_loaded': True, 'payload': {'k': 1}}`

### Static proof
- Manifest parser accepted arbitrary runtime entrypoint strings.
- Host runtime loader resolved `install_path / runtime_entrypoint` but did not enforce that resolved path stayed under plugin install root.

### Fix implemented
- Manifest validation now rejects runtime entrypoints with:
  - absolute paths
  - `.` / `..` segments
  - backslashes
- Runtime loader now enforces `resolved_entrypoint.relative_to(resolved_install_path)`.
- Added tests:
  - `tests/unit/plugins/test_manifest.py` (invalid runtime entrypoint cases)
  - `tests/unit/plugins/test_host_runtime.py`

### Post-fix verification
- Re-ran malicious install:
  - `blocked runtime.entrypoint cannot contain '.' or '..' path segments...`

---

## 2.6 Plugin export archive-name traversal hardening

### Target files
- `app/plugins/exporter.py`
- `tests/unit/plugins/test_exporter.py`

### Repro script (before fix)
- With malformed plugin id/version values in registry or caller input, export composed archive filename directly from raw values.
- Example path-like id (`../evil`) produced invalid path behavior and non-actionable export failure.

### Static proof
- `archive_name = f"{plugin_id}-{version}{...}"` with no component sanitation.

### Fix implemented
- Added `_safe_archive_component(...)` guard for both plugin id and version.
- Rejects empty values, `.`/`..`, and path separators.
- Added unit tests for:
  - normal archive generation
  - path-like plugin id rejection.

### Post-fix verification
- Repro now blocked with explicit error:
  - `blocked plugin_id cannot contain path separators.`

---

## 2.7 Runtime trust flag not enforced when loading runtime handlers

### Target files
- `app/plugins/host_runtime.py`
- `app/plugins/trust_store.py`
- `tests/unit/plugins/test_host_runtime.py`

### Repro script (before fix)
- Created enabled runtime plugin in registry with no trust entry.
- Called `load_runtime_command_handlers(state_root=...)`.
- Observed runtime command handler loaded despite trust never granted.

### Static proof
- `load_runtime_command_handlers(...)` filtered only by:
  - registry enabled flag
  - manifest compatibility
  - runtime entrypoint presence
- No trust-store check existed before loading runtime module.

### Fix implemented
- Added trust gate:
  - `is_runtime_plugin_trusted(plugin_id, version, state_root=...)`
- Runtime handlers are now skipped unless trust is explicitly true.
- Added tests in `tests/unit/plugins/test_host_runtime.py`:
  - untrusted plugin skipped
  - trusted plugin loaded and callable.

### Post-fix verification
- Repro output after fix:
  - `untrusted_handler_count 0`
  - `trusted_handler_count 1`

---

## 2.8 Support bundle missed active fallback app log

### Target files
- `app/bootstrap/logging_setup.py`
- `app/support/support_bundle.py`
- `tests/unit/bootstrap/test_logging_setup.py`
- `tests/integration/support/test_support_bundle.py`

### Repro script (before fix)
- Forced primary log path failure to trigger fallback tier.
- `configure_app_logging(...)` selected fallback `/tmp/choreboy_code_studio/logs/app.log`.
- `build_support_bundle(...)` checked only canonical primary `global_app_log_path(state_root)`, so app log was omitted.

### Static proof
- `support_bundle.py` used `global_app_log_path(state_root)` directly.
- Logging setup can route to fallback path while primary path remains nonexistent.

### Fix implemented
- Added `get_active_log_path(state_root=...)` in logging bootstrap to expose configured active log destination.
- Support bundle now includes this active log path (fallback or primary).
- Added regression tests for:
  - active fallback path resolution
  - support bundle inclusion of fallback app log.

### Post-fix verification
- Repro output after fix:
  - `tier fallback`
  - `has_app_log True`

---

## 2.9 Active log lookup leaked across state roots

### Target files
- `app/bootstrap/logging_setup.py`
- `tests/unit/bootstrap/test_logging_setup.py`

### Repro analysis (before fix)
- Logging setup stored a single global active log path.
- `get_active_log_path(state_root=...)` returned that active path regardless of requested state root.
- In multi-state-root workflows/tests, support bundle or diagnostics could include a log from the wrong state root.

### Static proof
- `get_active_log_path` had no state-root match check for `_ACTIVE_LOG_PATH`.

### Fix implemented
- Added `_ACTIVE_STATE_ROOT` tracking.
- `get_active_log_path(state_root=...)` now returns active path only when it matches requested state root.
- Added unit test:
  - `test_get_active_log_path_ignores_active_log_from_different_state_root`.

### Post-fix verification
- Repro script output:
  - `active_for_state_two .../state_two/logs/app.log`
  - `expected_state_two .../state_two/logs/app.log`

---

## 2.10 Packager accepted entrypoint paths that are excluded from package payload

### Target files
- `app/packaging/packager.py`
- `tests/unit/packaging/test_packager.py`

### Repro script (before fix)
- Project contained `cbcs/logs/run_entry.py`.
- Called `package_project(..., entry_file='cbcs/logs/run_entry.py')`.
- Result:
  - `success True`
  - packaged entry file missing (`entry_in_pkg_exists False`).

### Static proof
- Packager validated entry existence but did not enforce that entry path survived `_should_exclude(...)` filters.
- `cbcs/logs` is explicitly excluded from copy.

### Fix implemented
- Added preflight check: reject entrypoint when resolved relative path is excluded.
- Added regression test:
  - `test_returns_failure_when_entry_file_is_excluded_path`.

### Post-fix verification
- Repro output after fix:
  - `success False`
  - `error Entry file resolves to an excluded path and would not be packaged: cbcs/logs/run_entry.py`

---

## 3) Commits produced during audit

1. `925ec32` — Harden supervisor against stale exit races  
2. `6c89d68` — Block plugin install path traversal inputs  
3. `a732058` — Validate project tree names and move edge cases  
4. `b96d8ea` — Fail packaging when entrypoint is invalid  
5. `b2ee677` — Constrain plugin runtime entrypoint paths  
6. `5ccdff4` — Harden plugin exporter archive path components  
7. `7ef2fc4` — Record exporter hardening commit in bug report  
8. `2ad86e8` — Enforce runtime-plugin trust gate at load time  
9. `4e4a9cc` — Include active fallback app log in support bundles  
10. `a5a1eba` — Scope active-log lookup by state root  
11. `05b49ac` — Reject excluded packaging entrypoint paths

---

## 4) Remaining constraints and limits

- Could not run pytest suites due missing pytest in runtime/system Python.
- Could not run type checker due missing pyright binary.
- Used deterministic repro scripts + static code-path validation + syntax compilation instead.

