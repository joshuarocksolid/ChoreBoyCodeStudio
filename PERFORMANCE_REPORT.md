# Performance Report

## Executive summary

This audit found and validated multiple real performance issues, with five high-confidence fixes shipped:

1. **Confirmed bottleneck fixed:** run-log output rendering had superlinear growth from repeated full-text checks.
2. **Confirmed bottleneck fixed (routine-path):** unresolved-import runtime probing caused large UI-thread lint stalls.
3. **Confirmed bottleneck fixed for exclusion-heavy workloads:** search now prunes excluded directories before scanning files.
4. **Confirmed bottleneck fixed:** project-module completion now reuses indexed module metadata with in-process caching.
5. **Confirmed responsiveness bottleneck fixed:** find-references and rename-planning actions no longer execute project scans on the UI thread.

The highest measured gain was in run-log rendering throughput (**~27x faster at 40k lines**).  
The audit still has important remaining engine-level work to do: reference scanning, cold go-to-definition, and diagnostics remain expensive internally, but the first user-facing shell freeze in navigation/refactor actions has now been removed.

---

## Confirmed bottlenecks

## 1) Run Log append path exhibited quadratic growth (fixed)
- **Severity:** Critical  
- **Confidence:** High (measured before/after)  
- **File(s):** `app/shell/run_log_panel.py`  
- **Evidence:**  
  - Before: 40k lines -> **18,432 ms**
  - After: 40k lines -> **683 ms**
  - 10k lines: 1,058 ms -> 155 ms
- **Scenario:** Long-running scripts producing sustained output in Run Log panel.
- **Root cause:** Per-line call to `self._text.toPlainText()` inside append loop triggered increasingly expensive work as text grew.
- **Suggested fix:** O(1) newline decision using cursor position (implemented).
- **Expected impact:** Major UI responsiveness improvement during high-output runs.
- **Validation method:** Offscreen Qt benchmark + integration perf regression test.

## 2) Routine linting could block UI via runtime subprocess import probes (fixed for routine triggers)
- **Severity:** High  
- **Confidence:** High (measured + code-path verification)  
- **File(s):** `app/shell/main_window.py`, `app/intelligence/diagnostics_service.py`, `app/intelligence/runtime_import_probe.py`  
- **Evidence:**  
  - Analyzer with probe enabled (20 unresolved imports): **1,461 ms**
  - Same with probe disabled: **1.15 ms**
- **Scenario:** Save/realtime/tab-change lint on files with unresolved imports.
- **Root cause:** `allow_runtime_import_probe=True` on routine lint flows caused subprocess launch per unresolved module (cold path).
- **Suggested fix:** Disable probe on routine flows; keep probe for explicit manual linting (implemented).
- **Expected impact:** Removes large cold-stall class from normal editing workflow.
- **Validation method:** Unit tests for trigger policy + analyzer benchmarks.

## 3) Search traversal wasted time scanning excluded directory trees (fixed)
- **Severity:** High (for exclusion-heavy projects)  
- **Confidence:** High (measured before/after simulation)  
- **File(s):** `app/editors/search_panel.py`  
- **Evidence:**  
  - Excluded-directory workload:
    - Current: **1.34 ms**
    - Old behavior simulation: **607.03 ms**
- **Scenario:** Projects with large excluded folders (`generated`, `.venv`, etc.) and a focused include area.
- **Root cause:** Excludes were applied at file stage only; traversal still descended into excluded directories.
- **Suggested fix:** Prune excluded directories during traversal (implemented).
- **Expected impact:** Large improvement in first-result and total search latency for common real-world layouts.
- **Validation method:** Synthetic benchmark + added unit coverage.

---

## 4) Project module completion had poor no-match worst-case behavior (fixed)
- **Severity:** Medium-High  
- **Confidence:** High (measured before/after)  
- **File(s):** `app/intelligence/completion_providers.py`, `app/intelligence/completion_service.py`, `app/persistence/sqlite_index.py`  
- **Evidence:**  
  - Before (no indexed module cache path): no-match prefix **~251.67 ms**
  - After (indexed metadata + in-process cache): no-match prefix **~27.58 ms**
  - After matching prefix: **~24.26 ms**
- **Scenario:** Completion queries with rare/invalid prefixes in large projects.
- **Root cause:** Full recursive filesystem module scan per request in no-match paths.
- **Suggested fix:** Reuse indexed file metadata and cache derived module names by project/cache stamp (implemented).
- **Expected impact:** Lower completion p95 latency on large projects.
- **Validation method:** Completion service microbenchmarks + new unit coverage.

---

## 5) Find References / Rename planning blocked the UI thread (fixed at shell layer)
- **Severity:** High  
- **Confidence:** High (code-path change + automated validation + focused timing)  
- **File(s):** `app/shell/main_window.py`  
- **Evidence:**  
  - Planning-phase measurement showed `find_references()` scaling to roughly **952 ms at ~10k files**
  - Focused post-fix action benchmark with 250 ms injected engine delay:
    - `Find References` handler returned in **0.36 ms**
    - `Rename Symbol` handler returned in **0.30 ms**
- **Scenario:** interactive navigation/refactor actions on medium/large projects.
- **Root cause:** shell action handlers performed project-wide analysis inline on the UI thread.
- **Suggested fix:** dispatch reference search and rename planning through `BackgroundTaskRunner` while preserving current result UI (implemented).
- **Expected impact:** eliminates editor freezes when the user triggers these actions, even before deeper engine optimization lands.
- **Validation method:** new shell action unit tests + AppRun benchmark with injected slow task behavior.

---

## Scalability risks

## 6) Find-in-files remains linear for broad no-match scans
- **Severity:** Medium  
- **Confidence:** High (measured)  
- **File(s):** `app/editors/search_panel.py`  
- **Evidence (after changes):** 20k files, no-match query still ~**718 ms**.
- **Scenario:** very large projects with broad no-hit search terms.
- **Root cause:** unavoidable full scan in no-match case; regex/content checks still dominate once traversal overhead is reduced.
- **Suggested fix:** optional indexing for search, chunked incremental UI result updates, and cancellation improvements.
- **Expected impact:** Better responsiveness at very large scales.
- **Validation method:** scaling benchmark across 1k-20k files.

## 7) Reference search / rename planning engine still scales linearly
- **Severity:** Medium  
- **Confidence:** Medium-High  
- **File(s):** `app/intelligence/reference_service.py`, `app/intelligence/refactor_service.py`  
- **Evidence:**  
  - `find_references` scales to roughly **952 ms** at ~10k files in synthetic benchmarks.
- **Scenario:** interactive reference/rename commands in larger workspaces.
- **Root cause:** full-project token/AST walks plus repeated path normalization and double scanning.
- **Suggested fix:** optimize `reference_service.py` internals after the shell-layer backgrounding already landed.
- **Expected impact:** lower total wait time after the UI-thread freeze has been removed.
- **Validation method:** targeted profiling + scaling benchmark reruns.

---

## Low-priority inefficiencies

## 8) `SQLiteSymbolIndex` object recreation overhead
- **Severity:** Low  
- **Confidence:** High  
- **File(s):** `app/intelligence/completion_providers.py`, `app/intelligence/navigation_service.py`, `app/persistence/sqlite_index.py`  
- **Evidence:** constructor+query average ~**2.3 ms**, first-call ~9 ms.
- **Scenario:** repeated completion/navigation calls.
- **Root cause:** short-lived object creation and connection setup.
- **Suggested fix:** reuse index service instance per project/session.
- **Expected impact:** modest p95 improvement; lower overhead noise.
- **Validation method:** microbench constructor/query loops.

---

## Fixes applied

1. `RunLogPanel.append_live_line` O(1) newline check.
2. Routine lint triggers now disable runtime subprocess import probing.
3. `find_in_files` traversal now uses streaming `os.walk` with directory-level exclusion pruning.
4. Project module completions now use indexed module metadata cache when available.
5. `Find References` and `Rename Symbol` now dispatch expensive planning work through `BackgroundTaskRunner` instead of scanning inline on the UI thread.
5. Added/updated tests:
   - `tests/integration/performance/test_responsiveness_thresholds.py`
   - `tests/unit/shell/test_main_window_lint_probe_policy.py`
   - `tests/unit/editors/test_search_panel.py`
   - `tests/unit/intelligence/test_completion_service.py`
   - `tests/unit/persistence/test_sqlite_index.py`
   - `tests/unit/shell/test_main_window_reference_rename_actions.py`

---

## Before/after measurement table

| Area | Before | After | Delta |
|---|---:|---:|---:|
| Run log append (40k lines) | 18,432 ms | 683 ms | **~27x faster** |
| Run log append (10k lines) | 1,058 ms | 155 ms | **~6.8x faster** |
| Lint unresolved imports (20, probe on/off) | 1,461 ms / 1.15 ms | routine path now uses off | Removes routine cold stall class |
| Search with huge excluded dir | ~607 ms (old behavior simulation) | 1.34 ms | **~453x faster** |
| Completion no-match (20k modules) | ~251.67 ms | 27.58 ms | **~9.1x faster** |

---

## Highest-value next profiling steps

1. **UI-thread frame-time profiling**
   - Instrument Qt event-loop stalls during references/rename/search operations.
2. **Search indexing experiment**
   - Compare current streaming scan vs optional indexed search for >50k file projects.
3. **Runtime-parity retest in AppRun with populated vendor artifacts**
   - Re-run tree-sitter/highlighting perf gates currently skipped in this VM checkout.

