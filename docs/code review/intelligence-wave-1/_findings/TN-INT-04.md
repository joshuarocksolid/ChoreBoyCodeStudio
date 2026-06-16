# TN-INT-04 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-04  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/symbol_index.py`, `app/intelligence/api_index.py`, `app/intelligence/import_resolver.py`, `app/intelligence/runtime_import_probe.py`, `app/intelligence/cache_controls.py` — project symbol indexing, static API index, import resolution facade, runtime import probes, and intelligence cache settings. Cross-read: `app/shell/intelligence_cache_workflow.py`, `app/intelligence/completion_providers.py`, `app/persistence/sqlite_index.py`, `app/project/file_inventory.py`.

---

## Executive verdict

**Not thermo-clean.** The slice correctly keeps AST symbol extraction off the UI thread and documents SQLite as acceleration, but it introduces a **second ad-hoc background worker** (`SymbolIndexWorker`) beside the canonical `SemanticWorker` / AD-017 scheduler model, with its own cancel/generation/commit semantics duplicated in shell code. SQLite reads on the completion hot path treat the cache as implicit truth with no degradation metadata (AD-007 / architecture gate #12). Project-tree work is centralized in R4's `iter_python_files`, yet **orchestration still schedules redundant full traversals** on open, save, lint, and module-completion fallback. AST symbol extraction is forked across `symbol_index` and `completion_providers`. `incremental_indexing` is parsed but only wired to save-triggered refresh, not open-time indexing. Dominant risk: **parallel worker + cache-as-truth drift** that will multiply as semantic navigation and rename slices attach more readers to the same SQLite file.

---

### TN-INT-04-1 — SymbolIndexWorker is ad-hoc thread orchestration beside AD-017

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:38-71` — bespoke `threading.Thread`, `threading.Event` cancel, and `should_commit` callback. `app/intelligence/semantic_worker.py:24-36` — canonical keyed queue worker already exists. `docs/ARCHITECTURE.md` AD-017 — "generic shell background work uses a reusable bounded scheduler with keyed cancellation/replacement semantics instead of ad-hoc thread spawning."
- **Code-judo alternative:** One `BackgroundTaskScheduler` (or extend `SemanticWorker` with non-Jedi task keys like `"symbol_index"`) owns symbol indexing: submit/replace keyed job, generation invalidation, main-thread `on_done`. Delete `SymbolIndexWorker`'s thread lifecycle; keep `_extract_symbols` / fingerprint diff as the task body.
- **Suggested remediation:** Hard cutover `IntelligenceCacheWorkflow.start_symbol_indexing` to scheduler API; mirror generation gating already in `intelligence_cache_workflow.py:65-80` as scheduler key generation instead of a parallel worker class.
- **Tests that would prove fix:** Unit test: second `start_symbol_indexing` cancels first job without orphan thread; stale generation never calls `on_done`; no regression in `tests/unit/intelligence/test_symbol_index.py` scenarios via scheduler adapter.
- **Handoff overlap:** AD-016, none

---

### TN-INT-04-2 — SQLite symbol cache read path lacks acceleration-not-truth contract

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/completion_providers.py:135-159` — `provide_project_symbol_items` reads `SQLiteSymbolIndex.search_by_prefix` and emits `CompletionItem` with no cache-miss signal, empty-cache handling, or in-flight indexing awareness. Contrast `provide_project_module_items` at `176-196`, which falls back to `iter_python_files` when the index is empty. `docs/ARCHITECTURE.md` AD-007 — "SQLite … remain acceleration layers, not competing truth sources."
- **Code-judo alternative:** Single `ProjectSymbolSource` port: if cache row count == 0 or index worker running → return `CompletionTierMetadata(degraded="index_warming")` and optionally synchronous AST for current file only; never silently equate empty/stale SQLite with "project has no symbols."
- **Suggested remediation:** Plumb cache readiness through `CompletionBroker` merge policy (gate #12); add explicit `confidence` / degradation field on project-symbol items parallel to `api_index`'s `confidence="static"`.
- **Tests that would prove fix:** Completion service test: empty SQLite → degraded metadata or fallback items, not empty list presented as authoritative; warm cache → indexed symbols with `source="symbol_cache"`.
- **Handoff overlap:** AD-016, AD-007

---

### TN-INT-04-3 — Incremental index update is non-atomic across symbol and fingerprint tables

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:97-133` — deletes/upserts symbols, then separately upserts fingerprints in a second step; `_can_commit()` can abort between them. `app/persistence/sqlite_index.py:255-298` — per-file symbol upsert opens its own connection/commit; `upsert_file_fingerprints` is a separate commit at `196-214`.
- **Code-judo alternative:** One `apply_index_delta(project_root, delta: IndexDelta)` transaction: tombstone deleted files, upsert changed symbols, update fingerprints, commit once. Worker calls that; readers treat partial state as "warming."
- **Suggested remediation:** Add `SQLiteSymbolIndex.apply_file_delta(...)` with single `connection` context; worker `_run` becomes one call plus `count_symbols`.
- **Tests that would prove fix:** Simulate interrupt after symbol upsert but before fingerprint upsert → either rolled back or reader detects inconsistent state; incremental test in `test_symbol_index.py` still passes.
- **Handoff overlap:** none

---

### TN-INT-04-4 — `incremental_indexing` setting is half-wired (save only, not open)

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/cache_controls.py:106-108` — `should_refresh_index_after_save` gates on `incremental_indexing`. `app/shell/project_load_surface.py:61-66` — project open always calls `start_symbol_indexing` regardless of `incremental_indexing`. Settings UI exposes "Incremental indexing" (`settings_dialog_general.py:241-243`) with no effect on open/rescan paths.
- **Code-judo alternative:** Rename setting to match behavior or wire it consistently: `incremental_indexing=False` → full rebuild path (`replace_symbols_for_project` or delete+scan all files); `True` → fingerprint diff only. Single `index_policy(settings)` consumed by open, save, and rescan workflows.
- **Suggested remediation:** Extend `cache_controls` with `should_index_on_open(settings)` and `index_mode(settings)`; teach `SymbolIndexWorker` / scheduler task to honor full vs incremental.
- **Tests that would prove fix:** `incremental_indexing=False` on open triggers full replace (all files in `changed_files` or explicit full path); save refresh respects same flag.
- **Handoff overlap:** none

---

### TN-INT-04-5 — R4 SSOT for traversal, but orchestration still multiplies full walks

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:83-84` — worker lists all Python files every run. `app/intelligence/diagnostics_service.py:106` — lint pass walks all Python files again. `app/intelligence/completion_providers.py:196-204` — module completion fallback walks tree when cache empty. `app/shell/save_workflow.py:212-216` — save triggers another index walk. R4 centralized `iter_python_files` (`app/project/file_inventory.py`) but not **inventory snapshot sharing**.
- **Code-judo alternative:** `ProjectInventorySnapshot` (paths + fingerprints + exclude hash) computed once per generation; symbol worker, diagnostics batch, and completion module list consume the same snapshot from shell/project load workflow.
- **Suggested remediation:** R4 follow-on: expose snapshot from `file_inventory` or project-load surface; pass into worker instead of re-walking; defer diagnostics walk when snapshot unchanged.
- **Tests that would prove fix:** Spy/metrics test: single project open → one `walk_project` (or one snapshot build) per generation, not N independent walks across subsystems.
- **Handoff overlap:** R4

---

### TN-INT-04-6 — Duplicated AST symbol extraction models (symbol_index vs completion_providers)

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/symbol_index.py:159-189` — `ast.walk`, functions/classes only, builds `SymbolLocation` with signature/doc. `app/intelligence/completion_providers.py:268-288` and `350-372` — separate `_collect_symbols_from_ast` / `_collect_top_level_symbols_from_ast` with assignments/imports included for completions. `SymbolLocation` vs `IndexedSymbol` manual field copy at `108-120`.
- **Code-judo alternative:** One `app/intelligence/python_symbols.py` module: `extract_file_symbols(path, *, scope="toplevel"|"all_definitions")` returning a shared frozen record; `to_indexed_symbol()` at persistence boundary only.
- **Suggested remediation:** Extract shared AST helpers; delete `_list_python_source_files` pass-through wrapper; collapse `build_python_symbol_index` to call the same extractor the worker uses.
- **Tests that would prove fix:** Parametrized AST fixture tests on shared module; symbol index + completion provider tests unchanged behavior.
- **Handoff overlap:** none

---

### TN-INT-04-7 — Weak fingerprint (mtime+size) with unused `fingerprint_version`

- **Persona:** TN-INT-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/symbol_index.py:199-201` — `_file_fingerprint` uses `(st_mtime_ns, st_size)` only. `118` — `fingerprint_version=1` hardcoded on every upsert. No content hash; equal-size edits or coarse timestamp resolution can skip re-index; version field never participates in invalidation logic.
- **Code-judo alternative:** Either document fingerprint as best-effort and bump cache on save explicitly (already triggers reindex), or add cheap content hash (e.g. `hashlib.file_digest` first N KB + size) and gate upsert on `(fingerprint_version, hash)`.
- **Suggested remediation:** Wire `fingerprint_version` into compare in worker diff, or drop the column until a migration story exists.
- **Tests that would prove fix:** Same mtime/size, changed content → file appears in `changed_files`; version bump forces full re-extract.
- **Handoff overlap:** none

---

### TN-INT-04-8 — `_can_commit()` guard spam instead of structured cancel scope

- **Persona:** TN-INT-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/symbol_index.py:79-135` — eleven separate `if not self._can_commit(): return` checks inside `_run`. Generation staleness is also enforced in shell callbacks (`intelligence_cache_workflow.py:128-129`).
- **Code-judo alternative:** Context manager or `CommitGate` passed into pure functions (`plan_delta`, `apply_delta`); cancel raises `IndexCancelled` caught once at top of `_run`. Shell generation check stays in callback only.
- **Suggested remediation:** Refactor `_run` into `plan_index_delta(...) -> Delta | None` (pure) + `apply_index_delta(..., gate)` (checks gate once per batch operation).
- **Tests that would prove fix:** Existing stale-generation tests pass; `_run` line count drops, branch count measurable down.
- **Handoff overlap:** none

---

### TN-INT-04-9 — `api_index.py` duplicates curated module trees (maintenance sprawl)

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/api_index.py:59-86` — `QtWidgets` and `PySide2.QtWidgets` duplicate identical `ApiMember` tuples; same pattern for `QtCore`/`PySide2.QtCore` (`87-110`) and `QtGui`/`PySide2.QtGui` (`111-132`). `_CURATED_API_INDEX` is a 108-line literal map.
- **Code-judo alternative:** Canonical keys only (`PySide2.QtWidgets`, etc.) plus `_alias_module_name(name) -> canonical` at lookup time; or generate curated index from `runtime_api_index.json` exclusively and delete inline tuples.
- **Suggested remediation:** Deduplicate via alias table `{ "QtWidgets": "PySide2.QtWidgets" }`; move bulk data to JSON already loaded by `_load_index_members`.
- **Tests that would prove fix:** Completion tests for both `QtWidgets.` and `PySide2.QtWidgets.` contexts still resolve same members; file shrinks ~40%.
- **Handoff overlap:** none

---

### TN-INT-04-10 — Runtime import probe is a hidden subprocess layer without shared ownership

- **Persona:** TN-INT-04
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/runtime_import_probe.py:56-79` — `@lru_cache` subprocess `[runtime_path, "-c", probe_script]` per top-level module. `app/intelligence/import_resolver.py:49-50` — opt-in probe from resolver. `app/project/dependency_classifier.py:191-196` and `244-245` — duplicate probe calls with separate policy. No `clear_runtime_import_probe_cache()` on project switch in production paths (only tests call it).
- **Code-judo alternative:** Single `RuntimeImportCatalog` service: owns probe cache, timeout budget, and invalidation; `import_resolver` and `dependency_classifier` call it. Resolver stays a thin filesystem+layout facade.
- **Suggested remediation:** Move probe behind `dependency_classifier` or new `runtime_import_catalog.py`; resolver delegates probe branch; document subprocess cost in lint/manual trigger paths (gate #9 awareness).
- **Tests that would prove fix:** One mock subprocess site; classifier + resolver tests unchanged; cache clear hooked from project-close workflow.
- **Handoff overlap:** R5, AD-016

---

### TN-INT-04-11 — `cache_controls.py` mixes unrelated highlighting policy with index settings

- **Persona:** TN-INT-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/cache_controls.py:12-24` — `IntelligenceRuntimeSettings` bundles `cache_enabled`, `incremental_indexing`, `force_full_reindex_on_open` with `highlighting_adaptive_mode` and threshold chars (`49-102`). Index slice owns parsing for editor highlighting tiers unrelated to SQLite symbol cache.
- **Code-judo alternative:** Split `IntelligenceCacheSettings` (cache/index only) from `HighlightingAdaptiveSettings`; `parse_intelligence_runtime_settings` composes both or delegates to `highlighting_policy.py`.
- **Suggested remediation:** Extract highlighting fields to adjacent module already consumed by editor shell; keep `rebuild_symbol_cache` and `should_refresh_index_after_save` in cache-focused module.
- **Tests that would prove fix:** `test_cache_controls.py` split; settings round-trip unchanged via `settings_models` facade.
- **Handoff overlap:** none

---

### TN-INT-04-12 — `build_python_symbol_index` full-scan path survives beside incremental worker

- **Persona:** TN-INT-04
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/symbol_index.py:144-156` — synchronous full-project AST scan building in-memory dict, used by unit tests (`test_symbol_index.py:17-36`) but not production completion path (SQLite-only). Two mental models for "project symbol index" in one module.
- **Code-judo alternative:** Tests drive worker + SQLite (already covered in `test_symbol_index_worker_*`); demote `build_python_symbol_index` to test helper or delete and use `SQLiteSymbolIndex.lookup` against worker-populated DB.
- **Suggested remediation:** Move full-scan helper to `tests/support/` if still needed for pure AST assertions; production API surface = worker + cache reader only.
- **Tests that would prove fix:** No production imports of `build_python_symbol_index`; test coverage unchanged via worker fixtures.
- **Handoff overlap:** none

---

## Architecture gate checklist (TN-INT-04)

| Gate | Status | Notes |
|------|--------|-------|
| 1 Single owner: Jedi/Rope on SemanticWorker | **Pass** | Symbol index does not touch Jedi/Rope |
| 9 No editor-side execution of user project code | **Pass with caveat** | Runtime probe executes imports in AppRun subprocess, not user project code |
| 10 Visible caches only | **Pass** | SQLite under global state dir, not dot-prefixed |
| 12 SQLite = acceleration, not truth | **Fail** | `provide_project_symbol_items` treats cache as sole source (TN-INT-04-2) |
| AD-017 bounded scheduler | **Fail** | Ad-hoc `SymbolIndexWorker` thread (TN-INT-04-1) |

---

## Approval bar

**Do not approve** until TN-INT-04-1 (worker model), TN-INT-04-2 (cache truth boundary), and TN-INT-04-4 (incremental setting wiring) have a coherent design. TN-INT-04-3 and TN-INT-04-5 are strong P1 follow-ups before rename/navigation slices add more cache readers. Remaining findings are P2 cleanup that reduces duplication debt (API index, AST helpers, settings split).
