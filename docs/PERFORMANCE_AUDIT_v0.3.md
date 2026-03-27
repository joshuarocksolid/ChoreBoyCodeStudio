# Performance Audit v0.3 (since `v0.2`)

Date: 2026-03-27  
Scope: `v0.2..HEAD`  
Baseline reference: commit `fb4afd4` (previous audit patterns and fixes)

## Executive summary

Since `v0.2`, the largest user-visible performance risk is now the packaging dependency-audit path: unresolved imports can trigger per-module runtime subprocess probes, pushing packaging preflight into tens of seconds on large unresolved sets. The second major risk is global-history loading, where timeline listing does N+1 SQL alias lookups and runs synchronously from the UI action path, causing near-1s delays with ~5k tracked files. Startup and interaction costs are otherwise mostly bounded, but there is avoidable repeated work in theme-token resolution (`gsettings` subprocess per call) and mandatory startup probing before first paint. Compared with the prior audit at `fb4afd4`, previously targeted hotspots (run-log scaling, routine lint probe policy, search exclude pruning, semantic warm-path bounds) remain controlled by tests and current measurements. The recommendations below prioritize high-impact, low-effort changes that can ship incrementally without public API changes.

---

## Methodology and evidence collection

### Test/validation runs used during audit

- Attempted full suite: `python3 run_tests.py -v --import-mode=importlib` (hung in integration path; known caveat in repo guidance).
- Targeted performance + semantic integration:
  - `python3 run_tests.py -v --import-mode=importlib tests/integration/performance/ tests/integration/intelligence/test_semantic_navigation_integration.py tests/integration/intelligence/test_semantic_rename_integration.py`
  - Result: 18 passed, 3 skipped (tree-sitter runtime unavailable in this environment).
- Targeted baseline-unit check:
  - `python3 run_tests.py -v --import-mode=importlib tests/unit/`
  - Pre-existing failures observed in this environment (not introduced by this audit): pyflakes/tree-sitter related unit failures.

### Profiling approach

- Used ad-hoc scripts with `time.perf_counter()` (outside production code) and `cProfile`.
- Ran measurements both in host Python and `/opt/freecad/AppRun` where runtime behavior mattered.
- Collected repeated runs (typically 3–10) and reported raw run values plus median.

### Baseline comparison against `fb4afd4`

Previous audit themes from `fb4afd4` included run-log growth, routine lint runtime probing, search traversal overhead, completion no-match cost, and reference/rename responsiveness. Current integration performance tests indicate those baseline patterns are still bounded (no new regression signal in those previously fixed areas).

---

## Findings table (sorted by impact)

| # | Area | Issue | Impact | Effort | Recommendation |
|---|---|---|---|---|---|
| 1 | Packaging / dependency audit | Per-import runtime subprocess probing in dependency audit can explode latency | High | Small | Disable runtime probing by default in package dependency audit; rely on known runtime module inventory and static classification |
| 2 | Local history + UI responsiveness | Global history list performs N+1 alias queries and is invoked synchronously from UI action path | High | Medium | Batch alias retrieval (single query per listing) and load history list off main thread |
| 3 | Theme resolution / UI hot path | `gsettings` subprocess is called repeatedly via `_resolve_theme_tokens()` | Medium | Small | Cache system dark-mode preference once per session and invalidate only on explicit theme changes |
| 4 | Startup sequencing | Startup capability probe runs before first window paint and includes subprocess checks | Medium | Medium | Defer non-critical checks until after window show; keep minimal gating checks pre-paint |
| 5 | Packaging preflight flow | Dependency audit runs even when preflight already has blocking issues | Medium | Trivial | Short-circuit: if preflight has blocking issues, skip dependency audit and return immediately |

---

## Detailed findings

## 1) Packaging dependency audit triggers expensive per-module runtime probes

### Problem

Packaging validation always enables runtime import probing:

- `app/packaging/validator.py:58-62`
- `app/packaging/dependency_audit.py:214-221`
- Probe implementation launches subprocess per top-level import:
  - `app/intelligence/runtime_import_probe.py:56-69`

When many unresolved modules are present, this turns dependency audit into repeated subprocess waits.

### Evidence

- Synthetic unresolved-import workload (60 files x 5 missing imports = 300 misses):
  - `allow_runtime_import_probe=False`: median **30.41 ms**
  - `allow_runtime_import_probe=True`: median **42,874.06 ms**
- Single cold probe cost:
  - `probe_runtime_module_importability('json')`: **196.36 ms** cold, **0.0766 ms** warm (cached)

Raw numbers (ms):

- No-probe runs: `[32.91, 30.41, 29.61]`
- Probe-on runs: `[42874.06, 42819.98, 43076.61]`

### Recommendation

Make packaging dependency audit static-first:

1. In `build_package_validation_report(...)` (`app/packaging/validator.py`), call `run_dependency_audit(... allow_runtime_import_probe=False)` by default.
2. Use `known_runtime_modules` when available for fast runtime classification.
3. Optionally expose an explicit “deep runtime verification” mode (manual/advanced), not default packaging path.

---

## 2) Global history listing has N+1 query behavior and blocks UI action

### Problem

Global history open action calls listing synchronously:

- `app/shell/main_window.py:1690-1697`

Listing does per-file alias fetch:

- `app/persistence/local_history_store.py:405-491`
- `path_aliases` call inside loop: `app/persistence/local_history_store.py:488`
- Alias lookup performs additional per-file SQL queries:
  - `app/persistence/local_history_store.py:993-1040`

### Evidence

Scaling benchmark for `list_global_history_files()`:

- 500 files: median **15.69 ms**
- 1,000 files: median **46.71 ms**
- 2,000 files: median **155.72 ms**
- 5,000 files: median **869.19 ms**

Alias sensitivity at 5,000 files:

- Current behavior: median **883.56 ms**
- With alias lookup bypassed (measurement control): median **36.11 ms**

cProfile at 1,000 files:

- `list_global_history_files`: 0.055s total
- `_path_aliases_for_file_key`: dominant cumulative cost, 1000 calls
- ~2000 SQL `execute` calls from alias path

### Recommendation

1. Replace per-file alias fetch with one batched lineage query keyed by returned `file_key` set.
2. Keep base summaries fast; lazily resolve full alias history only when user expands/inspects one timeline.
3. Move `_handle_open_global_history_action` listing call onto existing background task lane and populate dialog asynchronously.

---

## 3) Theme-token resolution repeatedly spawns `gsettings` subprocess

### Problem

Theme token resolution in system mode calls `_system_prefers_dark_theme()`, which runs:

- `app/shell/main_window.py:1022-1029`
- `app/shell/main_window.py:1085-1092`

`_resolve_theme_tokens()` is called from startup/theme application and runtime-center dialog paths (e.g. `app/shell/main_window.py:695`, `:795`, `:1659`, `:5415`, `:6276`).

### Evidence

AppRun measurement:

- `_resolve_theme_tokens()` with `theme_mode='system'`: median **2.73 ms** (runs `[3.28, 2.72, 2.71, 2.73, 2.74, 2.41, 3.79, 3.60]`)
- Forced light/dark mode: median **~0.013 ms**

`MainWindow` init profile also shows `subprocess.run` from theme detection in startup stack.

### Recommendation

1. Cache system dark-mode preference in memory (session-scoped).
2. Read once on startup; refresh only when user toggles theme mode or explicit refresh action.
3. Keep fallback behavior for environments without `gsettings`.

---

## 4) Startup capability probe is synchronous before first UI paint

### Problem

Editor startup does probe before constructing/showing main window:

- `run_editor.py:104-106` and `:119`

Probe includes subprocess import checks:

- `app/bootstrap/capability_probe.py:95-113`
- `app/bootstrap/capability_probe.py:204-232`

### Evidence

AppRun measurements:

- `run_startup_capability_probe()` median: **152.40 ms** (`[182.16, 153.47, 151.72, 152.40, 151.59]`)
- MainWindow init median: **48.92 ms** (startup cost currently dominated more by pre-window probe than window build itself)

### Recommendation

1. Keep only hard-blocking checks pre-window (minimal set).
2. Defer heavier checks (especially subprocess-backed probes) to post-show timer/background task.
3. Update status bar/runtime center incrementally as deferred checks complete.

---

## 5) Packaging still performs dependency audit when preflight already blocks

### Problem

`build_package_validation_report(...)` computes preflight issues, then always runs dependency audit regardless of preflight blockers:

- `app/packaging/validator.py:52-62`

### Evidence

10k-file project benchmark:

- Valid entry config: median **696.24 ms**
- Invalid entry config (preflight-blocking): median **689.08 ms**

This indicates near-identical cost despite already-known blocking state.

### Recommendation

If preflight has any blocking issue:

1. Skip `run_dependency_audit(...)`.
2. Return preflight-only validation report immediately.
3. Optionally allow manual “Run full dependency audit anyway” action in UI for diagnostics.

---

## Quick wins (high impact + low effort)

1. **Disable runtime subprocess probing in package dependency audit default path**  
   - Files: `app/packaging/validator.py`, `app/packaging/dependency_audit.py`  
   - Why quick: small conditional/config change; very large worst-case latency reduction.

2. **Short-circuit dependency audit when preflight already has blocking issues**  
   - File: `app/packaging/validator.py`  
   - Why quick: control-flow guard; avoids unnecessary heavy work.

3. **Cache system theme preference to avoid repeated `gsettings` subprocess calls**  
   - File: `app/shell/main_window.py`  
   - Why quick: localized caching change with no API impact.

4. **Move global-history listing off UI thread first; batch alias query second**  
   - Files: `app/shell/main_window.py`, `app/persistence/local_history_store.py`  
   - Why quick-ish: async action wiring is small; SQL batching is medium but highly impactful.

---

## Notes on non-findings / stable areas from prior audit baseline

- Prior high-impact regressions documented at `fb4afd4` (run-log scaling, routine lint probe policy, search prune behavior, semantic warm-path bounds) did not show fresh regression signals in this audit’s targeted performance/integration runs.
- Several performance integration thresholds currently pass in this environment; tree-sitter-specific performance tests were skipped due runtime availability in this VM.
