# TN-PROJ-CONSUMERS — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-CONSUMERS  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/intelligence/symbol_index.py`, `app/intelligence/completion_providers.py`, `app/intelligence/diagnostics_service.py` (inventory/snapshot paths), `app/intelligence/completion_broker.py` (provider calls), `app/intelligence/python_structure.py`, `app/shell/intelligence_cache_workflow.py`. Cross-read: `app/project/file_inventory.py`, `tests/unit/intelligence/test_symbol_index.py`, `tests/unit/intelligence/test_completion_providers.py`, `tests/unit/intelligence/test_diagnostics_service.py`.

---

## Executive verdict

**Not thermo-clean.** R4 migrated traversal into `file_inventory.py` and introduced `ProjectInventorySnapshot`, but this slice proves the SSOT stop at the API boundary: **no production caller shares one snapshot per project generation**. Symbol indexing, completion fallbacks, and batch import analysis each call `build_project_inventory_snapshot` independently; the optional `inventory_snapshot` parameters on completion and diagnostics are dead wiring — `CompletionBroker` never passes them, and `LintWorkflow.run_import_analysis` never passes them either. Worse, **exclude policy diverges**: symbol indexing honors effective project excludes from the shell, while diagnostics and completion rebuild snapshots with default (empty) excludes, so the indexed/analyzed file set can disagree with what the user configured. Module-name derivation forks between layout-aware snapshot builders and cache-path string heuristics. `python_structure.py` partially centralizes AST work, but completion still carries duplicate collectors and ignores the exported helper. SQLite is positioned as acceleration in architecture docs, yet the broker re-tags cache hits as approximate and module completion prefers stale indexed paths over the snapshot contract. Dominant risk: **N walks + N module derivations + exclude drift** on every project open/save/completion cycle — exactly what R4 gate #5 and #6 were meant to prevent.

---

### TN-PROJ-CONSUMERS-1 — `ProjectInventorySnapshot` exists but is never orchestrated in production

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:234-267` — snapshot type and builder. `app/intelligence/completion_providers.py:145,201` — optional `inventory_snapshot` params. `app/intelligence/diagnostics_service.py:62,78-82` — optional param with fallback `build_project_inventory_snapshot(root)`. `rg inventory_snapshot app/` — **only intelligence modules define/use the param; zero shell callers pass it.** `app/intelligence/completion_broker.py:222-233` — calls `provide_project_symbol_items` / `provide_project_module_items` without `inventory_snapshot`. `app/shell/lint_workflow.py:221-228` — `find_unresolved_imports(...)` with no snapshot.
- **Code-judo alternative:** One `ProjectInventoryGeneration` owned by project-load / rescan workflow: build snapshot once (paths + module names + exclude hash + generation id), store on `LoadedProject` or a small `ProjectInventoryService`, pass the same frozen snapshot into symbol worker, completion broker, and import analysis. Delete per-consumer `or build_project_inventory_snapshot(...)` fallbacks except tests.
- **Suggested remediation:** R4 follow-on in shell layer (`project_load_surface`, `project_rescan_workflow`, `intelligence_cache_workflow`): expose `build_shared_inventory_snapshot(project, excludes) -> ProjectInventorySnapshot`; thread through all three consumers in the same generation bump.
- **Tests that would prove fix:** `tests/unit/project/test_inventory_snapshot.py` (planned in intelligence-wave-1 plan, still absent): spy asserts one `walk_project` per generation on project open; completion + diagnostics + index consume identical `python_file_paths` tuple reference.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-CONSUMERS-2 — Exclude parity broken: symbol index respects excludes; diagnostics/completion do not

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** BLOCKER
- **Evidence:** `app/shell/intelligence_cache_workflow.py:63-69,73-76` — loads `compute_effective_excludes(...)` and passes `exclude_patterns` into `update_symbol_index_cache`. `app/intelligence/symbol_index.py:120` — `build_project_inventory_snapshot(project_root, exclude_patterns=exclude_patterns)`. `app/intelligence/diagnostics_service.py:81` — `build_project_inventory_snapshot(root)` **with no exclude_patterns**. `app/intelligence/completion_providers.py:171,223` — same default-empty excludes on fallback paths. `app/intelligence/completion_providers.py` — no `exclude_patterns` parameter anywhere.
- **Code-judo alternative:** Snapshot builder always receives the same effective exclude list computed once at project generation; consumers never call `build_project_inventory_snapshot` without it. If a consumer needs a different file set (e.g. tree enumeration including `cbcs/`), that is a **named API** on `file_inventory`, not a silent default drift.
- **Suggested remediation:** Extend shared snapshot to carry `exclude_fingerprint`; shell passes excludes into diagnostics/completion; add `exclude_patterns` to `find_unresolved_imports` only as a deprecated escape hatch until orchestration lands.
- **Tests that would prove fix:** Project with `build/**` excluded: symbol index skips `build/foo.py`, import analysis does not flag imports inside excluded tree, completion module list omits excluded modules — all from one snapshot.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-CONSUMERS-3 — Three independent full walks per project generation (gate #5 violation)

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:60,120-121` — every index run lists all Python files via snapshot + stats every path for fingerprints. `app/intelligence/diagnostics_service.py:81-82` — `find_unresolved_imports` rebuilds snapshot when param omitted. `app/intelligence/completion_providers.py:171-174,223-224` — lazy snapshot on cache miss / empty module cache. Manifest metric: "Independent inventory snapshot builders | 3 consumer paths."
- **Code-judo alternative:** Single walk produces snapshot; symbol worker consumes `snapshot.python_file_paths` and only `stat()`s those paths for fingerprint diff; diagnostics iterates the same tuple; completion never walks. Save-triggered incremental index diffs against prior snapshot + changed path only.
- **Suggested remediation:** Couple symbol indexing to shared snapshot generation event; defer `find_unresolved_imports` full-project pass until snapshot generation completes or pass prebuilt snapshot from shell.
- **Tests that would prove fix:** Metrics/spy test: project open → exactly one `build_project_inventory_snapshot` (or one `walk_project`) before first completion keystroke and before import analysis.
- **Handoff overlap:** R4, CC-15, CC-11

---

### TN-PROJ-CONSUMERS-4 — Module-name derivation fork: layout-aware snapshot vs cache string heuristic

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/file_inventory.py:254-261,275-294` — `_module_name_from_python_path` uses `resolve_project_import_layout` / `module_name_for_file` then relative-path fallback. `app/intelligence/completion_providers.py:210-221` — warm SQLite path uses `_module_names_from_indexed_paths` → `_module_name_from_relative_path` (`:419-428`) with **no import layout**. `app/intelligence/completion_providers.py:223-225` — cold path uses `module_names_from_snapshot(snapshot)` (layout-aware). `app/intelligence/completion_providers.py:408-416` — `_module_name_from_path` duplicates layout logic but is **never called** (dead fork).
- **Code-judo alternative:** Module names are a field on `ProjectInventorySnapshot` only; completion reads `snapshot.module_names` or SQLite cache rows keyed by canonical module name — never re-derives from path strings. Delete `_module_name_from_relative_path`, `_module_names_from_indexed_paths`, and dead `_module_name_from_path`.
- **Suggested remediation:** Persist canonical module name in SQLite indexed_files metadata at index time using `file_inventory` helper; module completion reads names from snapshot or cache column, not path parsing.
- **Tests that would prove fix:** Source-root layout fixture: cache-warm and cache-cold module completion return identical module lists; no test relies on string-only derivation.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-CONSUMERS-5 — `CompletionBroker` downgrades SQLite cache hits to approximate tier

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_providers.py:154-165` — cache hit returns `source="cache"`, `confidence="exact"`. `app/intelligence/completion_broker.py:215-237` — wraps all fast-tier providers in `_tag_approximate_items(...)`. `app/intelligence/completion_broker.py:416-451` — rewrites every non-`static_api_index` item to `source="approximate"`, `confidence="approximate"`, `engine="heuristic"`, including cache hits.
- **Code-judo alternative:** `_tag_approximate_items` skips items with `source in ("cache", "exact")` or only tags providers that are genuinely heuristic (current-file AST, keyword, builtin). Broker merge policy reads provider metadata instead of blanket downgrade.
- **Suggested remediation:** Whitelist exact sources in `_tag_approximate_items`; plumb `CompletionTierMetadata` degradation only when fallback AST scan runs (`provide_project_symbol_items` approximate branch).
- **Tests that would prove fix:** Broker fast-tier test: populated SQLite → items retain `source="cache"` and rank above approximate AST fallback; envelope confidence reflects indexed tier.
- **Handoff overlap:** AD-007, CC-11

---

### TN-PROJ-CONSUMERS-6 — SQLite module list can disagree with snapshot file set (stale indexed paths)

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_providers.py:210-221` — if cache DB exists and `list_indexed_python_files` non-empty, module completion uses indexed paths **without** verifying they match current snapshot or excludes. `app/persistence/sqlite_index.py:240-253` — returns all `.py` rows for project. Symbol index removes deleted files on next run (`symbol_index.py:67-78`), but module completion can read **stale** indexed paths until worker completes — and uses different module-name derivation (TN-PROJ-CONSUMERS-4).
- **Code-judo alternative:** Module completion uses `snapshot.module_names` when generation matches; SQLite is a prefix-search accelerator keyed by snapshot generation, not an alternate module catalog.
- **Suggested remediation:** Gate `list_indexed_python_files` path on snapshot generation / exclude hash equality; otherwise fall through to snapshot module names.
- **Tests that would prove fix:** Delete project file, before reindex completes, module completion does not offer deleted module; after reindex, list matches snapshot.
- **Handoff overlap:** R4, AD-007, CC-11

---

### TN-PROJ-CONSUMERS-7 — `python_structure` dedup incomplete: completion duplicates AST collectors; exported helper unused

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/python_structure.py:65-104` — `collect_completion_symbol_names` + `_collect_top_level_symbols_from_ast` (canonical). `rg collect_completion_symbol_names app/` — **only defined, never imported**. `app/intelligence/completion_providers.py:290-310,372-405` — duplicate `_collect_symbols_from_ast` (full `ast.walk` including nested defs/imports) and `_collect_top_level_symbols_from_ast` (copy of python_structure). `app/intelligence/completion_providers.py:125` — `provide_current_file_symbol_items` uses local `_collect_symbols_from_ast`, not `collect_completion_symbol_names`.
- **Code-judo alternative:** Completion imports `collect_completion_symbol_names` for current-file and module-member paths; delete duplicated private functions in `completion_providers.py`. Keep `_collect_symbols_from_ast` only if product policy requires nested/import names — then move to `python_structure` with an explicit `scope=` parameter shared with indexing.
- **Suggested remediation:** Hard cutover completion providers to `python_structure` helpers; one parametrized collector for "index symbols" vs "completion names".
- **Tests that would prove fix:** Parametrized fixture tests on shared module; delete duplicate functions; completion + symbol index tests unchanged.
- **Handoff overlap:** CC-12

---

### TN-PROJ-CONSUMERS-8 — Symbol extraction semantics diverge: index walks entire tree; doc claims top-level

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/python_structure.py:31-32,44-45` — docstring "Extract top-level function and class symbols" but `for node in ast.walk(tree)` collects **nested** functions/classes. `app/intelligence/completion_providers.py:372-394` — `_collect_top_level_symbols_from_ast` iterates `syntax_tree.body` only (true top-level). Approximate symbol fallback (`completion_providers.py:174`) uses `extract_symbol_locations` (all nested); current-file completion uses broader `_collect_symbols_from_ast`.
- **Code-judo alternative:** Explicit `SymbolExtractionScope` enum in `python_structure`: `TOP_LEVEL`, `ALL_DEFINITIONS`, `COMPLETION_NAMES`; index, cache fallback, and editor completion each declare scope — no accidental nested-symbol inflation in completion or deflation in outline.
- **Suggested remediation:** Align doc + implementation; index worker and approximate fallback share one scope; completion uses narrower scope by policy.
- **Tests that would prove fix:** Fixture with nested `def inner` inside function: index includes/excludes per chosen scope consistently across consumers.
- **Handoff overlap:** CC-12

---

### TN-PROJ-CONSUMERS-9 — Symbol cache update remains non-atomic across symbols and fingerprints

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:74-110` — separate `remove_symbols_for_files`, `upsert_symbols_for_files`, `upsert_file_fingerprints` guarded by `_can_commit()` between steps. `app/persistence/sqlite_index.py` — per-operation commits (per TN-INT-04-3). Cancel/stale generation can leave symbols updated without matching fingerprints.
- **Code-judo alternative:** Single `apply_index_delta(project_root, delta, gate)` transaction on SQLite connection; readers treat partial state as warming.
- **Suggested remediation:** Add batched apply API on `SQLiteSymbolIndex`; worker `_run` becomes plan + single commit.
- **Tests that would prove fix:** Interrupt simulation after symbol upsert → rolled back or reader detects inconsistent state; existing incremental tests in `test_symbol_index.py` stay green.
- **Handoff overlap:** CC-11

---

### TN-PROJ-CONSUMERS-10 — `intelligence_cache_workflow` schedules indexing but does not own inventory generation

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/intelligence_cache_workflow.py:58-111` — bumps generation, passes excludes to `update_symbol_index_cache`, uses shared background scheduler (AD-017 improvement). No snapshot build, no handoff to completion/diagnostics, no `ProjectInventorySnapshot` on host protocol (`:17-49`). Index task internally rebuilds snapshot (`symbol_index.py:120`).
- **Code-judo alternative:** Rename workflow to `ProjectIntelligenceRefreshWorkflow`: first task builds shared snapshot, second task (or same task) updates SQLite from snapshot paths — single orchestration entry for open/save/rescan.
- **Suggested remediation:** Extend host with `inventory_snapshot_for_generation()`; build snapshot on main thread or first background task before symbol extract loop.
- **Tests that would prove fix:** Workflow unit test with fake host: one snapshot built, passed to index updater and exposed to completion broker mock.
- **Handoff overlap:** R4, CC-15, TN-PROJ-SHELL

---

### TN-PROJ-CONSUMERS-11 — Approximate symbol fallback on completion hot path re-scans project AST

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_providers.py:168-192` — when SQLite empty, loops **all** `snapshot.python_file_paths`, calls `extract_symbol_locations` per file until limit. `app/intelligence/completion_broker.py:222-227` — invoked on every fast completion request while cache warming. No in-flight index awareness or "warming" degradation metadata on envelope (contrast approximate `source` on items only).
- **Code-judo alternative:** While index worker running or cache empty, return explicit degradation (`index_warming`) and optionally current-file symbols only — never synchronous multi-file AST scan on UI-driven fast tier.
- **Suggested remediation:** Broker checks index generation / worker key; providers return empty + reason instead of full-project AST fallback during warm-up.
- **Tests that would prove fix:** Empty cache + indexing in flight → fast completion completes without O(n_files) AST parse; items show warming metadata.
- **Handoff overlap:** AD-007, CC-11

---

### TN-PROJ-CONSUMERS-12 — Test coverage gap: snapshot contract and orchestration untested

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `docs/code review/project-ssot-wave-1/00-manifest.md:111-112` — "`build_project_inventory_snapshot` / `ProjectInventorySnapshot` | None | **High**". `rg inventory_snapshot tests/` — **no matches**. `tests/unit/intelligence/test_completion_providers.py:14-37` — only approximate fallback when cache empty; no snapshot pass-through, exclude parity, or module-name fork. `tests/unit/intelligence/test_symbol_index.py` — worker/cache tests, no snapshot sharing. `tests/unit/intelligence/test_diagnostics_service.py` — no `inventory_snapshot` param coverage.
- **Code-judo alternative:** Dedicated `test_inventory_snapshot.py` for builder + module names; consumer tests inject shared snapshot and assert zero builder calls.
- **Suggested remediation:** Add tests listed in manifest before fix-agent wave; parametrized exclude + source-root layout cases.
- **Tests that would prove fix:** New tests pass; regression catches reintroduction of independent walks.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-CONSUMERS-13 — Save-triggered reindex omits explicit excludes (relies on implicit reload)

- **Persona:** TN-PROJ-CONSUMERS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/save_workflow.py:216` — `start_symbol_indexing(window._loaded_project.project_root)` without `exclude_patterns=`. `app/shell/intelligence_cache_workflow.py:63-69` — reloads excludes from host when param is None. Works today but duplicates exclude resolution logic and is fragile if save path bypasses loaded project metadata sync.
- **Code-judo alternative:** Shared snapshot already carries excludes; save triggers `refresh_index(snapshot)` — no second exclude resolution path.
- **Suggested remediation:** Part of TN-PROJ-CONSUMERS-1 orchestration; until then pass `effective_excludes_for(...)` explicitly from save workflow for symmetry with project open.
- **Tests that would prove fix:** Save after exclude change uses same file set as open-time index.
- **Handoff overlap:** R4, TN-PROJ-SHELL

---

## Architecture gate checklist (TN-PROJ-CONSUMERS)

| Gate | Status | Notes |
|------|--------|-------|
| 5 One walk per generation | **Fail** | Three independent snapshot builds (TN-PROJ-CONSUMERS-3) |
| 6 `ProjectInventorySnapshot` canonical for intelligence | **Fail** | API exists; orchestration absent (TN-PROJ-CONSUMERS-1) |
| 3 `cbcs/` policy explicit per API | **Pass with caveat** | All three use `iter_python_files` default (cbcs pruned); tree enumeration differs elsewhere |
| 4 Exclude policy one source per use case | **Fail** | Symbol index vs diagnostics/completion exclude drift (TN-PROJ-CONSUMERS-2) |
| AD-007 SQLite = acceleration, not truth | **Fail** | Broker downgrades cache (TN-PROJ-CONSUMERS-5); stale module list path (TN-PROJ-CONSUMERS-6) |
| AD-017 bounded scheduler for index | **Pass** | `intelligence_cache_workflow` uses `background_tasks().run` (TN-INT-04-1 remediated) |

---

## Approval bar

**Do not approve** R4 consumer cutover as complete until TN-PROJ-CONSUMERS-1 (shared orchestration) and TN-PROJ-CONSUMERS-2 (exclude parity) have a design — these are presumptive blockers for file-set SSOT. TN-PROJ-CONSUMERS-3 through TN-PROJ-CONSUMERS-8 are strong P1 follow-ups that prevent completion/diagnostics/index from drifting module lists and AST semantics. TN-PROJ-CONSUMERS-5 and TN-PROJ-CONSUMERS-11 affect user-visible completion quality during cache warm-up. Remaining items are P2 test and wiring hygiene. Positive note: ad-hoc `SymbolIndexWorker` thread is gone; scheduler-based indexing and approximate fallback metadata on empty cache (`test_completion_providers.py`) show partial intelligence-wave-1 remediation — but the project snapshot orchestration gap remains the dominant debt in this slice.
