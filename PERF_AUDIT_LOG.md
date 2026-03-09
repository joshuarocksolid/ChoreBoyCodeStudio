# Performance Audit Log

Date: 2026-03-09  
Auditor: Cursor performance audit agent  
Scope: end-to-end responsiveness + high-impact throughput bottlenecks in editor/search/lint/output paths.

## 0) Current branch continuation note

- Repository branch: `cursor/performance-audit-report-d9b6`
- This log continues prior performance-audit work already present in the repo.
- Earlier sections below describe previously landed fixes that remain relevant baseline context.

## 0.1) Slice 1 — UI-thread unblocking for reference / rename actions

### Why this slice

Planning-phase profiling and measurement confirmed that:
- `find_references()` scales to roughly **952 ms at ~10k files**
- rename planning reuses the same scan path
- both actions were executed synchronously from `MainWindow`

This slice focuses on **responsiveness first**: moving those actions off the UI thread before deeper engine optimization.

### Changed files

- `app/shell/main_window.py`
- `tests/unit/shell/test_main_window_reference_rename_actions.py` (new)

### Change summary

- `MainWindow._handle_find_references_action()` now schedules reference search through `BackgroundTaskRunner` instead of executing the scan inline.
- `MainWindow._handle_rename_symbol_action()` now schedules rename planning through `BackgroundTaskRunner` instead of planning inline on the UI thread.
- Existing result behavior is preserved:
  - find references still populates the Problems panel
  - rename still shows preview, applies the plan, refreshes open tabs, reloads project state, and reports final counts

### Validation

Targeted correctness suites:

```bash
python3 run_tests.py -v --import-mode=importlib \
  tests/unit/shell/test_main_window_reference_rename_actions.py \
  tests/unit/intelligence/test_reference_service.py \
  tests/unit/intelligence/test_refactor_service.py \
  tests/unit/intelligence/test_navigation_service.py \
  tests/unit/intelligence/test_symbol_index.py
```

Result:
- **18 passed**

Performance regression suites:

```bash
python3 run_tests.py -v --import-mode=importlib \
  tests/integration/performance/test_responsiveness_thresholds.py \
  tests/integration/performance/test_editor_highlighting_performance.py
```

Result:
- **11 passed**

### Focused responsiveness measurement

A targeted AppRun benchmark monkeypatched `find_references()` and `plan_rename_symbol()` to each sleep for 250 ms, then measured the action handler return time after backgrounding.

Observed:
- `Find References` handler return time: **0.36 ms**
- `Rename Symbol` handler return time: **0.30 ms**
- Both background tasks still completed successfully afterward.

Conclusion:
- This slice does not make the underlying analysis faster yet.
- It **does** remove the expensive scan/planning work from the UI-thread action path, which is the highest-confidence responsiveness win for these commands.

## 0.2) Slice 3/4 — reference scan + cold go-to-definition engine optimization

### Why this slice

After shell-level backgrounding, the next highest-value work was reducing the underlying engine cost for:
- `find_references()`
- rename planning (which reuses `find_references()`)
- cache-cold `lookup_definition_with_cache()`

### Changed files

- `app/intelligence/reference_service.py`
- `app/intelligence/symbol_index.py`
- `tests/unit/intelligence/test_reference_service.py`

### Change summary

#### Reference engine
- Removed the double full-project scan in `find_references()`.
- Each Python file is now:
  - read once
  - definitions collected from the in-memory source
  - token references collected from the same source payload
- Avoided repeated per-file `resolve()`/string normalization in the hot path.

#### Cold definition lookup path
- Removed unnecessary per-file `resolve()` calls during symbol-index construction.
- Preserved existing cache contract and warm-lookup behavior.

### TDD / regression coverage

Added focused unit coverage:

- `tests/unit/intelligence/test_reference_service.py::test_find_references_reads_each_python_file_once`

This test failed before the implementation because each file was read twice by the old reference path.

### Validation

Targeted suites:

```bash
python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/test_reference_service.py
python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/test_symbol_index.py tests/unit/intelligence/test_navigation_service.py
```

Results:
- reference-service suite: **5 passed**
- symbol-index/navigation suites: **7 passed**

### Before / after measurements

#### `find_references()` scaling

Before:
- ~1,002 files: **113.60 ms**
- ~2,502 files: **241.01 ms**
- ~5,002 files: **482.18 ms**
- ~10,002 files: **951.66 ms**

After:
- ~1,002 files: **49.44 ms**
- ~2,502 files: **122.03 ms**
- ~5,002 files: **248.75 ms**
- ~10,002 files: **499.21 ms**

Improvement:
- roughly **2.3x faster** at ~1k files
- roughly **2.0x faster** at ~10k files

#### `plan_rename_symbol()` scaling

After:
- ~1,002 files: **47.82 ms**
- ~2,502 files: **118.39 ms**
- ~5,002 files: **239.10 ms**
- ~10,002 files: **492.00 ms**

Conclusion:
- rename planning inherits the same engine win because it delegates to `find_references()`

#### Cold `lookup_definition_with_cache()` scaling

Before:
- ~1,002 files: **76.87 ms**
- ~2,502 files: **173.75 ms**
- ~5,002 files: **330.99 ms**
- ~10,002 files: **652.93 ms**

After:
- ~1,002 files: **52.94 ms**
- ~2,502 files: **95.27 ms**
- ~5,002 files: **181.38 ms**
- ~10,002 files: **343.64 ms**

Warm path after change:
- still ~**1.56–4.80 ms**

Improvement:
- roughly **1.45x faster** at ~1k files
- roughly **1.9x faster** at ~10k files

## 1) Environment and validation notes

- Repository branch: `cursor/performance-audit-report-4d51`
- Runtime note: `python3 run_tests.py ...` failed in this VM (`ModuleNotFoundError: pytest` inside AppRun payload).
- Measurement/test fallback used for this audit: `/workspace/.venv/bin/python`.

## 2) Baseline test run (before code changes)

Command:

```bash
/workspace/.venv/bin/python -m pytest tests/integration/performance/test_responsiveness_thresholds.py tests/integration/performance/test_editor_highlighting_performance.py -vv --durations=0
```

Result:
- `7 passed, 3 skipped`
- Tree-sitter perf tests skipped due missing vendor runtime artifacts in this checkout.

## 3) Baseline exploratory measurements (before fixes)

### 3.1 Run log append scaling

Command (offscreen Qt benchmark) measured `RunLogPanel.append_live_line`.

Observed:
- 2,000 lines: **65.13 ms**
- 5,000 lines: **297.49 ms**
- 10,000 lines: **1,058.37 ms**
- 20,000 lines: **4,367.77 ms**
- 40,000 lines: **18,432.25 ms**

Conclusion: strong superlinear/quadratic growth.

### 3.2 Lint runtime-probe overhead

Command benchmarked `analyze_python_file(... allow_runtime_import_probe=...)` on unresolved imports.

Observed:
- 20 unresolved imports, `allow_runtime_import_probe=True`: **1,461.21 ms**
- Same input, `allow_runtime_import_probe=False`: **1.15 ms**

Conclusion: subprocess import probing dominates cold lint latency.

### 3.3 Search traversal behavior

`find_in_files` scaling (single-level large directory):
- 20k files, query `needle`: **751.27 ms** (before)
- 20k files, query `zzzz`: **770.08 ms** (before)

Conclusion: linear full-tree scan cost remains significant.

### 3.4 Completion worst-case module scan

`provide_project_module_items`:
- 20k files, no-match prefix: **371.31 ms**
- 20k files, matching prefix: **10.84 ms**

Conclusion: no-match case has poor worst-case behavior.

## 4) Implemented fixes

### Fix A — Run log append path optimization

Changed:
- `app/shell/run_log_panel.py`

Change summary:
- Removed per-line `self._text.toPlainText()` emptiness check.
- Replaced with O(1) `cursor.position() > 0` newline check.

Validation:
- `tests/unit/shell/test_run_log_panel.py` pass.
- Added perf-regression coverage:
  - `tests/integration/performance/test_responsiveness_thresholds.py::test_run_log_panel_append_scales_near_linearly`

### Fix B — Disable runtime import probing for routine lint flows

Changed:
- `app/shell/main_window.py`
- `tests/unit/shell/test_main_window_lint_probe_policy.py` (new)

Change summary:
- `manual` lint trigger keeps `allow_runtime_import_probe=True`.
- Routine triggers (`save`, `tab_change`, realtime, bulk relint path) now pass `allow_runtime_import_probe=False`.

Validation:
- New unit policy tests pass:
  - manual trigger uses probe
  - save trigger does not
  - bulk relint does not

### Fix C — Search traversal prunes excluded directories early

Changed:
- `app/editors/search_panel.py`
- `tests/unit/editors/test_search_panel.py`

Change summary:
- Replaced `sorted(root.rglob("*"))` loop with streaming `os.walk`.
- Added directory pruning with `should_exclude_relative_path(..., is_directory=True)` before descending.

Validation:
- Added unit test:
  - `test_find_in_files_exclude_patterns_skip_directory_tree`

### Fix D — Completion module suggestions now reuse indexed module cache

Changed:
- `app/intelligence/completion_providers.py`
- `app/intelligence/completion_service.py`
- `app/persistence/sqlite_index.py`
- `tests/unit/intelligence/test_completion_service.py`
- `tests/unit/persistence/test_sqlite_index.py`

Change summary:
- Added `SQLiteSymbolIndex.list_indexed_python_files(...)`.
- `provide_project_module_items(...)` now accepts `cache_db_path` and prefers indexed file metadata when available.
- Added in-process module-name cache keyed by `(project_root, cache_db_path, cache mtime)` to avoid repeated DB/path conversion overhead.
- Completion service now passes its cache DB path into module provider.

Validation:
- New tests:
  - `test_project_module_items_uses_indexed_file_cache_when_available`
  - `test_sqlite_symbol_index_lists_indexed_python_files`

## 5) Post-fix measurements

### 5.1 Run log append scaling (after Fix A)

Observed:
- 2,000 lines: **27.88 ms**
- 5,000 lines: **72.59 ms**
- 10,000 lines: **154.92 ms**
- 20,000 lines: **322.26 ms**
- 40,000 lines: **682.76 ms**

Improvement vs baseline:
- 40k lines: **18,432 ms -> 683 ms (~27x faster)**.

### 5.2 Search excluded-directory workload (after Fix C)

Synthetic workload:
- 20k files under excluded `generated/`
- 20 files under visible `src/`
- query `needle`, exclude pattern `generated`

Measured:
- Current implementation: **1.34 ms**
- Old behavior simulation (file-level exclude only): **607.03 ms**

Improvement:
- **~453x faster** in exclusion-heavy projects.

### 5.3 Routine lint probe policy impact (Fix B rationale)

Measured analyzer cost difference on unresolved imports:
- probe enabled: **1,461.21 ms**
- probe disabled: **1.15 ms**

Routine lint now follows disabled-probe path, removing this cold-start stall class from normal typing/save flows.

### 5.4 Completion no-match latency (after Fix D with indexed cache)

Measured on 20k Python files with indexed fingerprint cache:
- no-match completion query (`zzzz`): **27.58 ms avg**
- matching query (`m0`): **24.26 ms avg**

Reference before Fix D (same audit baseline class, no indexed module cache path):
- no-match completion query: **~251.67 ms**

Improvement:
- no-match completion latency reduced by roughly **9x** in indexed-cache scenario.

## 6) Final targeted regression suite run

Command:

```bash
/workspace/.venv/bin/python -m pytest \
  tests/unit/shell/test_run_log_panel.py \
  tests/unit/shell/test_main_window_lint_probe_policy.py \
  tests/unit/editors/test_search_panel.py \
  tests/integration/performance/test_responsiveness_thresholds.py -vv
```

Result:
- **32 passed**

Additional comprehensive targeted suite (including optional completion optimization):

```bash
/workspace/.venv/bin/python -m pytest \
  tests/unit/shell/test_run_log_panel.py \
  tests/unit/shell/test_main_window_lint_probe_policy.py \
  tests/unit/editors/test_search_panel.py \
  tests/unit/intelligence/test_completion_service.py \
  tests/unit/persistence/test_sqlite_index.py \
  tests/integration/performance/test_responsiveness_thresholds.py -vv
```

Result:
- **50 passed**

