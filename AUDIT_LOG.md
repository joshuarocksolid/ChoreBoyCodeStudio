# AUDIT_LOG

Date: 2026-03-08  
Auditor mode: deep skeptical audit (evidence-first)

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

## 3) Commits produced during audit

1. `925ec32` — Harden supervisor against stale exit races  
2. `6c89d68` — Block plugin install path traversal inputs  
3. `a732058` — Validate project tree names and move edge cases  
4. `b96d8ea` — Fail packaging when entrypoint is invalid  
5. `b2ee677` — Constrain plugin runtime entrypoint paths  
6. `5ccdff4` — Harden plugin exporter archive path components  
7. `7ef2fc4` — Record exporter hardening commit in bug report  
8. *(pending this changeset)* enforce runtime-plugin trust gate at load time

---

## 4) Remaining constraints and limits

- Could not run pytest suites due missing pytest in runtime/system Python.
- Could not run type checker due missing pyright binary.
- Used deterministic repro scripts + static code-path validation + syntax compilation instead.

