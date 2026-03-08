# Performance Audit Log

Date: 2026-03-08  
Auditor: Cursor performance audit agent  
Scope: end-to-end responsiveness + high-impact throughput bottlenecks in editor/search/lint/output paths.

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

