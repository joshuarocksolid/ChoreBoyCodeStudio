# TN-PROJ-SHELL — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-SHELL  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/shell/intelligence_cache_workflow.py`, `app/shell/lint_workflow.py`, `app/shell/main_window.py` (entry-replacement dialog / inventory imports), `app/shell/run_launch_workflow.py`, `app/shell/editor_tab_workflow.py` (tree signature polling), `app/shell/project_rescan_workflow.py`, cross-read orchestration in `project_load_surface.py`, `save_workflow.py`, `project_tree_ui_workflow.py`. Cross-read tests: `test_main_window_lint_probe_policy.py`, `test_project_tree_refresh_state.py`, shell integration tests that stub `start_symbol_indexing`. Gates: R4 inventory snapshot orchestration, R5 classifier/runtime-probe policy, architecture gates 3/5/6/9 from `00-manifest.md`.

---

## Executive verdict

**Not thermo-clean.** Shell workflows correctly route raw `.py` discovery through `file_inventory` (`iter_python_files`, `enumerate_project_entries` via `project_service`) and gate manual lint runtime probes, but **no shell module owns or shares `ProjectInventorySnapshot`**. Project-open, poll-driven reload, save, and rescan each schedule independent full-project walks for tree enumeration, symbol indexing, and import analysis. The 1 s tree-signature poll watches a **broader file set** (all entries including `cbcs/` metadata) than intelligence indexing uses (Python-only, `cbcs/` pruned), so metadata/cache churn can trigger plugin reload and full reindex without any Python module-list change. Would not approve further Project SSOT wiring until a single per-generation snapshot is built once at the shell boundary and injected into symbol index, diagnostics, and completion paths—orchestration debt from Intelligence CC-15 remains entirely open at the shell seam.

---

### TN-PROJ-SHELL-1 — Shell has zero `ProjectInventorySnapshot` ownership; intelligence consumers re-walk independently

- **Persona:** TN-PROJ-SHELL
- **Severity:** BLOCKER
- **Evidence:** `rg "inventory_snapshot|ProjectInventorySnapshot" app/shell/` → no matches. `app/shell/intelligence_cache_workflow.py:72-78` — `update_symbol_index_cache(...)` triggers `build_project_inventory_snapshot` inside `symbol_index._list_python_source_files`. `app/shell/lint_workflow.py:220-228` — `run_import_analysis` calls `find_unresolved_imports(...)` with no `inventory_snapshot`; `diagnostics_service.py:78-82` builds a fresh snapshot when absent. `app/intelligence/completion_providers.py:171,223` — same fallback pattern (not wired from shell).
- **Code-judo alternative:** Introduce `ProjectInventoryOrchestrator` (or extend `ProjectLoadWorkflow` / `ProjectRescanWorkflow`) that builds one `ProjectInventorySnapshot` per project generation (open, rescan, exclude change) and passes it to symbol index, lint/import analysis, and session/completion bootstrap. Delete per-consumer `build_project_inventory_snapshot` calls on hot paths once injection is mandatory.
- **Suggested remediation:** Hard cutover at shell boundary: `finalize_project_open`, `rescan_from_disk(reindex=True)`, and exclude-change reload build snapshot once with `effective_excludes_for`, store on window or session host, pass through `IntelligenceCacheWorkflow.start_symbol_indexing`, `LintWorkflow.run_import_analysis`, and semantic session refresh.
- **Tests that would prove fix:** Integration test: mock walk counter on `iter_python_files` — one open + one manual import analysis ⇒ exactly one snapshot build. Unit test on orchestrator generation token invalidates stale snapshot.
- **Handoff overlap:** R4, CC-15, gate 5, gate 6

---

### TN-PROJ-SHELL-2 — Poll-driven reload performs three full traversals with no shared snapshot

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:548-550` — 1 s timer calls `poll_external_file_changes`. `app/shell/editor_tab_workflow.py:770-778` — on signature mismatch calls `reload_current_project()`. `editor_tab_workflow.py:786-789` — `scan_project_tree_signature` calls `enumerate_project_entries` (full tree walk #1). `project_tree_ui_workflow.py:468-469` — `reload_current_project` → `rescan_from_disk(reload_plugins=True, reindex=True)`. `project_rescan_workflow.py:49-68` — `open_project` re-enumerates entries (#2), then `start_symbol_indexing` builds python snapshot (#3).
- **Code-judo alternative:** Poll compares a cheap fingerprint (mtime/size hash of last snapshot module list, or incremental watcher) instead of re-walking the tree every second. On real change, rescan reuses the walk product from `open_project` entries to derive `ProjectInventorySnapshot` without a third python-only walk.
- **Suggested remediation:** Collapse poll + rescan into one orchestrated generation: rescan returns `(LoadedProject, ProjectInventorySnapshot)`; poll only triggers rescan when fingerprint differs; defer plugin reload unless manifest/plugin paths changed.
- **Tests that would prove fix:** Perf/regression test: poll with stable tree ⇒ zero `iter_project_entries` calls; simulated new `.py` file ⇒ one enumeration + one snapshot build total.
- **Handoff overlap:** R4, CC-15, gate 5

---

### TN-PROJ-SHELL-3 — Tree signature file set diverges from intelligence Python file set

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:786-790` — signature from `enumerate_project_entries` (all files/dirs; includes `cbcs/`). `app/shell/project_tree_utils.py:14-25` — `filter_tree_signature_entries` strips only `cbcs/runs/` and `cbcs/logs/`, not `cbcs/cache/`. `tests/unit/shell/test_project_tree_refresh_state.py:189-207` — asserts `cbcs/cache/index.bin` remains in filtered signature. `app/project/file_inventory.py:134-149` — `iter_python_files` prunes `cbcs/` entirely for intelligence walks.
- **Code-judo alternative:** Derive poll signature from the same `ProjectInventorySnapshot.python_file_paths` plus explicit manifest paths (`cbcs/project.json`), not from full entry enumeration. Metadata cache writes stop triggering reload cascades without hiding real source additions.
- **Suggested remediation:** Replace `scan_project_tree_signature` full walk with snapshot fingerprint comparison; extend ignore policy document in `project_tree_utils` or delete tree-signature walk in favor of snapshot generation counter.
- **Tests that would prove fix:** Extend `test_poll_external_file_changes_ignores_run_artifact_writes` to cover `cbcs/cache/` writes; assert no reload when only cache bin changes.
- **Handoff overlap:** R4, gate 3, CC-15

---

### TN-PROJ-SHELL-4 — `reload_current_project` conflates light tree refresh with heavy plugin reload and full reindex

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/project_tree_ui_workflow.py:465-469` — `refresh_project_tree_from_disk()` uses light `rescan_from_disk()` (no reindex); `reload_current_project()` always passes `reload_plugins=True, reindex=True`. `editor_tab_workflow.py:778`, `save_workflow.py:209`, `settings_apply_workflow.py:196` — all call `reload_current_project()` for disparate reasons (poll, new file save, exclude change). `project_rescan_workflow.py:54-69` — plugin reload + symbol reindex + test rediscovery bundled.
- **Code-judo alternative:** Split rescan tiers explicitly: `rescan_tree_only`, `rescan_and_reindex`, `rescan_plugins_and_reindex`. Poll and new-file save use tree + snapshot refresh; plugin reload only when `cbcs/project.json` or plugin manifest fingerprint changes.
- **Suggested remediation:** Map each caller to the minimal tier; demote poll-triggered reload to `rescan_from_disk(reindex=True)` without plugin reload unless manifest changed.
- **Tests that would prove fix:** Unit tests on `ProjectRescanWorkflow` assert plugin reload hook call count per tier; poll test asserts `reload_plugin_activation` not called for added `.py` file.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-SHELL-5 — New-file save double-schedules symbol indexing

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/save_workflow.py:208-216` — when saving a path that did not exist before, `reload_current_project()` runs (which reindexes via `project_rescan_workflow.py:63-68`), then `should_refresh_index_after_save` triggers a second `start_symbol_indexing` without `exclude_patterns`. `intelligence_cache_workflow.py:61,78` — each call bumps `_symbol_index_generation`, cancelling the prior task; two walks are scheduled, one discarded.
- **Code-judo alternative:** Save path calls either rescan-with-reindex **or** incremental `start_symbol_indexing`, never both. Rescan returns whether reindex ran; save skips duplicate when rescan already reindexed.
- **Suggested remediation:** Guard second `start_symbol_indexing` when save already invoked `reload_current_project`; or demote new-file save to light tree update + single snapshot-driven index pass.
- **Tests that would prove fix:** Save-new-file integration test: mock `update_symbol_index_cache` call count == 1; generation bump count == 1.
- **Handoff overlap:** R4, CC-15, gate 5

---

### TN-PROJ-SHELL-6 — `LintWorkflow.run_import_analysis` bypasses workflow broker and snapshot injection

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/lint_workflow.py:130-142` — per-file lint correctly uses `analyze_python_with_workflow(self._host.workflow_broker(), ...)`. `lint_workflow.py:220-228` — import analysis calls `find_unresolved_imports(...)` directly (no broker, no `inventory_snapshot`). `allow_runtime_import_probe=True` always. Contrasts with TN-INT-SHELL-SEAM-4 broker consolidation goal for diagnostics ingress.
- **Code-judo alternative:** Route import analysis through broker diagnostics provider (project-wide query kind) or a shared `DiagnosticsRunner` that accepts `inventory_snapshot` and probe policy. Shell passes snapshot from orchestrator.
- **Suggested remediation:** Add `inventory_snapshot` parameter plumbed from shell; align probe policy with manual-lint gate (explicit menu action ⇒ probe allowed).
- **Tests that would prove fix:** Shell unit test: import analysis receives same snapshot object built at open; broker invoked when plugin linters registered.
- **Handoff overlap:** R5, CC-14, TN-INT-SHELL-SEAM-4, gate 9

---

### TN-PROJ-SHELL-7 — Manual lint runtime-probe policy is correct; adjacent paths disagree

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/lint_workflow.py:127` — `allow_runtime_import_probe = trigger == "manual"`. `tests/unit/shell/test_main_window_lint_probe_policy.py:58-114` — strong coverage for manual=True, save/tab_change=False. `lint_workflow.py:225-226` — `run_import_analysis` hardcodes `allow_runtime_import_probe=True`. `main_window_composition.py:562-567` — startup `_runtime_probe_timer` calls `diagnostics_orchestrator.start_runtime_module_probe()` independently of lint triggers.
- **Code-judo alternative:** Centralize probe policy in one module (`RuntimeProbePolicy`: manual lint | import analysis menu | startup probe | packaging audit). Classifier SSOT consumes the same policy object; shell only sets tier from trigger.
- **Suggested remediation:** Document explicit product policy for import-analysis vs manual lint vs startup probe; wire `run_import_analysis` through policy helper; ensure startup probe does not race hot save/tab lint paths.
- **Tests that would prove fix:** Parametrized policy test covering all shell ingress triggers; no probe on save/tab_change/import-analysis when user disables runtime probing in settings (if added).
- **Handoff overlap:** R5, gate 7, TN-INT-SHELL-SEAM-4

---

### TN-PROJ-SHELL-8 — Project open finalizes lint before symbol index completes

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/project_load_surface.py:56-66` — `finalize_project_open` calls `lint_all_open_files()` synchronously (schedules per-file lint tasks), then `start_symbol_indexing(...)`. `lint_workflow.py:190-198` — tab_change trigger disables runtime probe but still runs import diagnostics per file via broker. Completion/navigation may read stale or empty symbol cache until indexing finishes; no handshake between index completion and relint.
- **Code-judo alternative:** `finalize_project_open` builds snapshot, starts index, registers `on_success` to relint open files (or emit `ProjectGenerationReady` event). Lint during open uses injected snapshot for import layout consistency.
- **Suggested remediation:** Reorder: snapshot → start index → lint on index success (or lint immediately with snapshot but relint after index commit). Publish generation token to lint workflow stale checks.
- **Tests that would prove fix:** Open project test: lint task starts after index `on_success`; import diagnostics use snapshot module list matching index walk.
- **Handoff overlap:** R4, CC-15, CC-14

---

### TN-PROJ-SHELL-9 — Entry-file choice enumeration duplicated with inconsistent helpers

- **Persona:** TN-PROJ-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/run_launch_workflow.py:39-49` — `_collect_project_entry_file_choices` uses `iter_python_files` + `sorted(...)`. `app/shell/main_window.py:431-435` — `_prompt_for_project_entry_replacement` duplicates list comprehension over `iter_python_files` (order relies on iterator sort, no shared helper). Neither applies `effective_excludes_for`; excluded/vendor `.py` files appear as runnable entry choices while intelligence honors excludes.
- **Code-judo alternative:** Single `collect_runnable_entry_choices(project_root, *, exclude_patterns)` in `app/project/file_inventory.py` or `project_service.py`; both run dialog and entry-replacement dialog import it with project effective excludes.
- **Suggested remediation:** Extract helper; pass excludes from loaded project metadata; use in run-with-arguments and missing-entry dialog.
- **Tests that would prove fix:** Parametrized test: vendor-excluded `.py` omitted from choices when exclude patterns active; run dialog and replacement dialog return identical sorted lists.
- **Handoff overlap:** R4, gate 4

---

### TN-PROJ-SHELL-10 — `IntelligenceCacheWorkflow` recomputes excludes on every index start instead of accepting orchestrated snapshot

- **Persona:** TN-PROJ-SHELL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/intelligence_cache_workflow.py:63-69` — when `exclude_patterns is None`, recomputes via `compute_effective_excludes(load_effective_exclude_patterns(...), metadata.exclude_patterns)`. Callers inconsistently pass excludes: `project_load_surface.py:63-66` passes them; `save_workflow.py:216` and `shell_composition.py:153-154` omit them. `settings_apply_workflow.py:171` omits excludes. Duplicate exclude resolution across shell hosts (`MainWindowIntelligenceCacheHost`, `ProjectRescanHost`, `effective_excludes_for`).
- **Code-judo alternative:** Index start accepts `(ProjectInventorySnapshot, exclude_patterns)` only from orchestrator; delete lazy exclude recompute inside cache workflow.
- **Suggested remediation:** Require explicit excludes or snapshot at all `start_symbol_indexing` call sites; add pyright/doc contract on host port.
- **Tests that would prove fix:** Call-site audit test or lint rule: `start_symbol_indexing(` must pass `exclude_patterns=` or `inventory_snapshot=`; save/settings paths verified.
- **Handoff overlap:** R4, gate 4, gate 5

---

### TN-PROJ-SHELL-11 — No dedicated tests for rescan orchestration or cache workflow behavior

- **Persona:** TN-PROJ-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `rg "project_rescan|ProjectRescan|rescan_from_disk|IntelligenceCacheWorkflow" tests/` — zero matches for rescan workflow; integration tests monkeypatch `start_symbol_indexing` to no-op (`test_main_window_session_persistence_integration.py:64`, `test_responsiveness_thresholds.py:53`, etc.). `test_project_tree_refresh_state.py:116-186` — tests poll reload trigger and run-artifact filtering only (signature mocked). `test_main_window_lint_probe_policy.py` — lint probe only; no import-analysis or snapshot tests.
- **Code-judo alternative:** Unit-test `ProjectRescanWorkflow` with fake host recording call order and tiers. Unit-test `IntelligenceCacheWorkflow` generation stale drop without MainWindow.
- **Suggested remediation:** Add `tests/unit/shell/test_project_rescan_workflow.py` and `test_intelligence_cache_workflow.py` before R4 orchestration refactor; one integration test for save-new-file single index scheduling (TN-PROJ-SHELL-5).
- **Tests that would prove fix:** New tests exist and run in fast shard; remove broad monkeypatch reliance for indexing in at least one integration path.
- **Handoff overlap:** R4, CC-15

---

### TN-PROJ-SHELL-12 — `editor_tab_workflow` tree poll reaches into `project_service` instead of inventory SSOT surface

- **Persona:** TN-PROJ-SHELL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tab_workflow.py:19,786-789` — imports `enumerate_project_entries` from `app.project.project_service` (which delegates to `iter_project_entries` in `file_inventory.py:325-328`). Works today but splits the SSOT import story: run/shell entry dialogs import `file_inventory` directly; poll imports `project_service`.
- **Code-judo alternative:** Shell modules import enumeration only from `file_inventory` public API; `project_service.enumerate_project_entries` becomes thin deprecated alias or internal to open/load.
- **Suggested remediation:** Change poll import to `iter_project_entries` + list materialization, or accept snapshot fingerprint and delete poll-time enumeration entirely (preferred with TN-PROJ-SHELL-3).
- **Tests that would prove fix:** Import-layer lint or architectural test: shell must not import `enumerate_project_entries` from `project_service` once snapshot orchestration lands.
- **Handoff overlap:** R4, gate 1

---

## Cross-cutting notes

| Theme | Status in shell orchestration slice |
|-------|-------------------------------------|
| Gate 5: one walk per generation | **Open** — poll, open, save, rescan, and index each walk independently (TN-PROJ-SHELL-1, -2, -5) |
| Gate 6: snapshot as intelligence contract | **Open** — shell never builds or passes `ProjectInventorySnapshot` (TN-PROJ-SHELL-1) |
| Gate 3: `cbcs/` policy per API | **Partial** — tree signature includes `cbcs/cache`; python inventory excludes all `cbcs/` (TN-PROJ-SHELL-3) |
| R5 classifier / runtime probe | Per-file lint gated; import analysis and startup probe unconsolidated (TN-PROJ-SHELL-6, -7) |
| Intelligence CC-15 snapshot orchestration | Unchanged at shell layer; primary debt for this slice |
| TN-INT-SHELL-SEAM lint broker split | Partially improved (`run_import_analysis` moved to `LintWorkflow`) but broker bypass remains (TN-PROJ-SHELL-6) |
| Test coverage | Lint probe strong; rescan/cache/snapshot orchestration absent (TN-PROJ-SHELL-11) |

**Approval bar:** Block on TN-PROJ-SHELL-1 (no shared snapshot) and TN-PROJ-SHELL-3 (signature/intelligence file-set mismatch causing spurious reloads). Land TN-PROJ-SHELL-4, -5, and -8 together with TN-PROJ-CONSUMERS orchestrator work before adding new shell inventory touchpoints. Entry-listing dedup (TN-PROJ-SHELL-9) can ride a later polish wave.
