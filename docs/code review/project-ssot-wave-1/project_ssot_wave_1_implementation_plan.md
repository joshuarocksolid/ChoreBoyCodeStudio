# Project SSOT Wave 1 — End-to-End Implementation Plan

Status: **implementation-ready** (Phase 2 execution)  
Baseline: `042be49e5777c587391ddbb396b7ea150e296dfe`  
Source review: [`project_ssot_wave_1_thermo_review_2026-06-16.md`](project_ssot_wave_1_thermo_review_2026-06-16.md)  
Strategy doc: [`project_ssot_wave_1_remediation_plan.md`](project_ssot_wave_1_remediation_plan.md) (unchanged — this document expands it)  
Integration themes: [`_findings/TN-PROJ-INTEG.md`](_findings/TN-PROJ-INTEG.md)

This plan is the **executable** companion to the remediation plan: every CC-PROJ theme CC-PROJ-01 … CC-PROJ-23 maps to concrete steps, files, PRs, verification gates, and dependencies. Use this document to drive implementation agents and PR reviews.

---

## 1. Program scope and completion definition

### In scope

- Close all **P0** themes CC-PROJ-01 … CC-PROJ-09 (mandatory).
- Close all **P1** themes CC-PROJ-10 … CC-PROJ-20 (mandatory for program completion).
- Close **P2** themes CC-PROJ-21 … CC-PROJ-23 per disposition table below.
- Satisfy R4 (Project Inventory SSOT) and R5 (Dependency Classifier SSOT) acceptance criteria in [`docs/deslop/AUDIT_app_remaining_handoff.md`](../../deslop/AUDIT_app_remaining_handoff.md).
- Converge with Intelligence Wave 1 tracks at the shell orchestration seam (CC-15, CC-12, CC-14 partial).

### Program complete when (all must pass)

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | CC-PROJ-01 … CC-PROJ-09 closed with evidence | P0 closure checklist (§4) |
| 2 | CC-PROJ-10 … CC-PROJ-20 closed | CC matrix (§3) status = closed |
| 3 | CC-PROJ-21 risk-first tests landed; CC-PROJ-22 backlog or closed; CC-PROJ-23 closed in Wave 4 | §3 + §14 |
| 4 | One `ProjectInventorySnapshot` per project generation on hot paths | Spy test (§15) + `rg build_project_inventory_snapshot app/intelligence/` shows no fallback-only hot paths |
| 5 | Zero `app.intelligence` imports in `app/project/dependency_classifier.py` | `rg 'from app\.intelligence' app/project/` → empty |
| 6 | No new project-root `rglob`/`os.walk` outside inventory or documented artifact-only paths | `rg 'rglob\(|os\.walk\(' app/packaging app/project` → only allowed sites (§14) |
| 7 | Fast shard + targeted R4/R5 tests green | §16 |
| 8 | `npx pyright` → 0 errors | §16 |
| 9 | Four-theme manual acceptance recorded for every UI-touching PR | §17 |
| 10 | Raw finding coverage: all ~95 slice findings mapped; P0/P1 themes closed | §21 raw-finding closure checklist |

### P0-only milestone (optional early ship gate)

Ship **P0 milestone** after PROJ-R-01 … PROJ-R-16 land (CC-PROJ-01 … CC-PROJ-09). P1 themes (CC-PROJ-10 … CC-PROJ-20) remain mandatory before declaring R4/R5 complete. Do not add inventory/classifier features before P0 milestone unless product-waived per TN-PROJ-INTEG approval bar.

---

## 2. Non-negotiable rules (every PR)

1. **Hard cutover** — delete old traversal/classification paths in the same PR; no `try new / fallback old` chains.
2. **Python 3.9** syntax; no dot-prefixed storage paths (`cbcs/` not `.cbcs/`).
3. **One walk per project generation** after PROJ-R-06: shell owns snapshot; intelligence consumers receive injected snapshot.
4. **One path→module authority:** `import_layout.module_name_for_file` / `module_name_from_relative_path` only — delete naive `_module_name_from_relative_path` forks.
5. **One classifier boundary:** `dependency_classifier.py` owns classification; diagnostics/packaging adapt it — no parallel explain tree.
6. **Layer direction:** `intelligence → project`, never `project → intelligence` after PROJ-R-18.
7. **Four-theme validation** for shell/editor UI PRs (Light, Dark, HC Light, HC Dark) — record in PR summary.
8. **Tests** only when risk-first gate applies: file-set parity, classifier parity, native blocking, rewrite correctness, probe policy, orchestration call counts.

---

## 3. CC theme closure matrix

| CC | Priority | Primary PR | Wave step | Key files | Verification | Depends on |
|----|----------|------------|-----------|-----------|--------------|------------|
| CC-PROJ-01 | P0 | PROJ-R-03, R-05 | 1.1, 1.3 | `file_excludes.py`, `file_inventory.py`, `search_panel.py`, `project_service.py` | Parity test: `src/generated/*` tree/search/python agree | PROJ-R-01 |
| CC-PROJ-02 | P0 | PROJ-R-04 | 1.2 | `file_inventory.py`, `layout.py`, `import_layout.py`, `constants.py` | Matrix: vendor/cbcs/reserved names | PROJ-R-02 |
| CC-PROJ-03 | P0 | PROJ-R-06, R-07, R-09 | 2.1, 2.2, 2.4 | New orchestrator, `intelligence_cache_workflow.py`, `symbol_index.py`, `diagnostics_service.py`, `completion_providers.py` | Spy: one walk per open | PROJ-R-03, R-04 |
| CC-PROJ-04 | P0 | PROJ-R-10, R-11 | 3.1, 3.2 | `import_rewrite.py`, `import_layout.py`, `file_inventory.py`, `completion_providers.py` | `src/` move/rename rewrites `my_pkg.*` | PROJ-R-06, R-07 |
| CC-PROJ-05 | P0 | PROJ-R-19 | 5.2 | `dependency_classifier.py`, `import_diagnostics.py`, `dependency_audit.py` | Parity suite stdlib/slim inventory | PROJ-R-18 |
| CC-PROJ-06 | P0 | PROJ-R-18 | 5.1 | New `import_resolution.py`, `dependency_classifier.py`, `import_resolver.py` | `rg from app\.intelligence app/project/` empty | — |
| CC-PROJ-07 | P0 | PROJ-R-20 | 5.3 | New `native_extension_scan.py`, `dependency_ingest.py`, `plugins/auditor.py` | Wheel/tree/plugin fixture identical | PROJ-R-18 |
| CC-PROJ-08 | P0 | PROJ-R-14, R-15 | 4.1, 4.2 | `artifact_builder.py`, `file_inventory.py`, `dependency_audit.py`, `layout.py` | Copy/audit parity matrix | PROJ-R-04 |
| CC-PROJ-09 | P0 | PROJ-R-16 | 4.3 | `validator.py`, `dependency_audit.py`, native scan primitive | `vendor/orphan.so` blocks export | PROJ-R-14, R-20 partial |
| CC-PROJ-10 | P1 | PROJ-R-22 | 6.1 | `diagnostics_service.py`, new `import_explanations.py`, `dependency_classifier.py` | Explain adapts classifier; parity matrix | PROJ-R-19 |
| CC-PROJ-11 | P1 | PROJ-R-23 | 6.2 | `import_diagnostics.py`, `lint_workflow.py`, `diagnostics_service.py` | Hot lint never subprocess probe | PROJ-R-22 partial |
| CC-PROJ-12 | P1 | PROJ-R-23 | 6.2 | `code_actions.py`, `python_style_workflow.py` | Source-root fix without message parse | PROJ-R-10 |
| CC-PROJ-13 | P1 | PROJ-R-08 | 2.3 | `editor_tab_workflow.py`, `project_rescan_workflow.py`, `intelligence_cache_workflow.py` | Save-new-file: one index refresh | PROJ-R-06 |
| CC-PROJ-14 | P1 | PROJ-R-12 | 3.3 | `project_service.py`, `import_layout.py` | Excluded `vendor/run.py` not default entry | PROJ-R-06 |
| CC-PROJ-15 | P1 | PROJ-R-13 | 3.4 | `python_structure.py`, `completion_providers.py` | Duplicate AST walkers deleted | PROJ-R-11 |
| CC-PROJ-16 | P1 | PROJ-R-04, R-15 | 1.2, 4.2 | `layout.py`, integration test | `cbcs/package.json` copied-not-audited by policy | PROJ-R-04 |
| CC-PROJ-17 | P1 | PROJ-R-19, R-21 | 5.2, 5.4 | `dependency_audit.py`, `validator.py` | Manifest drift fails validation | PROJ-R-19 |
| CC-PROJ-18 | P1 | PROJ-R-24 | 6.3 | Split from `diagnostics_service.py` | No diagnostics lane file >250 LOC | PROJ-R-22 |
| CC-PROJ-19 | P1 | PROJ-R-19 | 5.2 | `dependency_classifier.py` | `RuntimeModuleInventory` tri-state explicit | PROJ-R-18 |
| CC-PROJ-20 | P1 | PROJ-R-25 | 6.4 | `completion_broker.py`, `symbol_index.py` | Cache hit keeps tier metadata | PROJ-R-07 |
| CC-PROJ-21 | P2 | PROJ-R-01, R-09, R-19 | 0.1, 2.4, 5.2 | Test helpers under `tests/unit/project/` | Risk-first tests land | — |
| CC-PROJ-22 | P2 | PROJ-R-26 (optional) | R1 sweep | `file_inventory.py`, `dependency_classifier.py`, `diagnostics_service.py` | Inline imports removed or waived in PR summary | Program end |
| CC-PROJ-23 | P2 | PROJ-R-17 | 4.4 | `validator.py`, `installer_manifest.py` | Hidden-path scan inventory-backed | PROJ-R-14 |

---

## 4. P0 blocker closure checklist

Copy-paste verification after Waves 1–5 P0 slices:

| CC | Done when | Command / test |
|----|-----------|----------------|
| **CC-PROJ-01** | Tree/search/python use same effective exclude semantics for slash patterns | `python3 run_tests.py tests/unit/project/test_inventory_parity.py -k exclude` |
| **CC-PROJ-02** | Vendor/cbcs/reserved names centralized | `python3 run_tests.py tests/unit/project/test_inventory_parity.py -k cbcs_vendor` |
| **CC-PROJ-03** | One snapshot per generation; same object to index/diagnostics/completion | `python3 run_tests.py tests/unit/project/test_inventory_orchestration.py` |
| **CC-PROJ-04** | Rewrite uses layout module names | `python3 run_tests.py tests/unit/project/test_import_rewrite.py -k src_layout` |
| **CC-PROJ-05** | Classifier/resolvability parity documented or unified | `python3 run_tests.py tests/unit/project/test_classifier_parity.py` |
| **CC-PROJ-06** | No project→intelligence imports in classifier | `rg 'from app\.intelligence' app/project/` → empty |
| **CC-PROJ-07** | Native scan primitive shared | `python3 run_tests.py tests/unit/project/test_native_extension_scan.py` |
| **CC-PROJ-08** | Payload copy inventory-backed | `rg 'rglob\("' app/packaging/artifact_builder.py` → empty on project source walk |
| **CC-PROJ-09** | Orphan vendor `.so` blocks export | `python3 run_tests.py tests/unit/packaging/test_dependency_audit.py -k orphan_native` |

---

## 5. Wave 0 — Policy foundations + parity scaffolding

**Gate:** `python3 testing/run_test_shard.py fast` + new unit tests per PR. **No production behavior changes** except test relocation.

### Step 0.1 — Inventory parity fixtures (PROJ-R-01)

**CC:** CC-PROJ-21 (partial)

**Depends on:** none — start immediately

**Create:**
- `tests/unit/project/inventory_parity_fixtures.py` — parametrized project tree builders
- `tests/unit/project/test_inventory_parity.py` — skeleton assertions (may xfail until Wave 1)

**Modify:**
- Move `tests/unit/intelligence/test_import_rewrite.py` → `tests/unit/project/test_import_rewrite.py` (preserve imports to `app.project.import_rewrite`)
- Update any pytest path references in docs only if needed

**Fixtures to scaffold:**

| Fixture | Covers |
|---------|--------|
| `flat_layout_project` | `main.py`, `pkg/module.py` |
| `src_layout_project` | `src/my_pkg/module.py`, manifest `source_roots` |
| `vendor_project` | `vendor/pkg.py`, `vendor/native.so` |
| `cbcs_metadata_project` | `cbcs/package.json`, `cbcs/runs/log`, `cbcs/cache/` |
| `slash_exclude_project` | `src/generated/foo.py` + `exclude_patterns=["src/generated/*"]` |

**Hard cutover deletes:** none (scaffolding only).

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_inventory_parity.py tests/unit/project/test_import_rewrite.py
python3 testing/run_test_shard.py fast
```

**Tests (new):**
- `test_inventory_parity_fixtures_build_expected_trees`
- Relocated rewrite tests still pass unchanged

---

### Step 0.2 — Policy vocabulary types (PROJ-R-02)

**CC:** CC-PROJ-02 (partial), CC-PROJ-21 (partial)

**Depends on:** none (parallel with PROJ-R-01)

**Modify:**
- `app/project/file_inventory.py` — add `InventoryScope` enum: `tree_entries`, `python_analysis`, `text_search`, `packaging_payload`, `packaging_audit`
- `app/project/file_inventory.py` — add `MetaDirPolicy` dataclass documenting `cbcs/` per-scope behavior
- `docs/ARCHITECTURE.md` — short subsection on vendor triple role (user dependency, project exclude default, packaging payload vs audit skip) **or** extend remediation doc if ARCHITECTURE change too broad

**Work:**
1. Types + docstrings only; iterators accept scope parameter stubs defaulting to current behavior.
2. Document vendor roles without migrating callers.

**Hard cutover deletes:** none.

**Proof:**
```bash
npx pyright app/project/file_inventory.py
python3 testing/run_test_shard.py fast
```

**Four themes:** N/A

---

## 6. Wave 1 — Exclude, `cbcs`, and vendor policy unification

**Blocks:** CC-PROJ-01, CC-PROJ-02, CC-PROJ-16 (partial)

### Step 1.1 — Effective excludes as shared contract (PROJ-R-03)

**CC:** CC-PROJ-01

**Depends on:** PROJ-R-01, PROJ-R-02

**Create:**
- `EffectiveExcludes` dataclass in `app/project/file_excludes.py` — split `name_patterns` vs `relative_path_patterns`

**Modify:**
- `app/project/file_excludes.py` — add `effective_excludes_for_project(settings, manifest)` merging global + project patterns with explicit mode split at load time
- `app/project/file_inventory.py` — `iter_project_entries` / default `iter_python_files` use relative-path semantics when patterns contain `/`; document intentional name-only fast path if any remains
- `app/project/project_service.py` — replace inline `compute_effective_excludes` orchestration (~83–87) with shared helper
- Shell call sites duplicating exclude merge:
  - `app/shell/intelligence_cache_workflow.py` (~66–69)
  - `app/shell/editor_tab_workflow.py` (poll/rescan paths)
  - `app/shell/main_window.py`, `app/shell/run_launch_workflow.py` if they gain exclude awareness

**Hard cutover deletes:** duplicated `compute_effective_excludes` call chains at shell sites; hidden `pattern_mode` footguns without named policy.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_file_excludes.py tests/unit/project/test_inventory_parity.py -k exclude
python3 run_tests.py tests/unit/project/test_file_inventory.py
```

**Tests (extend):**
- `test_slash_pattern_excluded_from_tree_and_python_analysis`
- `test_name_only_pattern_still_works_for_segment_excludes`

---

### Step 1.2 — `cbcs` and vendor policy table (PROJ-R-04)

**CC:** CC-PROJ-02, CC-PROJ-16

**Depends on:** PROJ-R-02

**Modify:**
- `app/project/file_inventory.py` — centralize `cbcs/` policy via `MetaDirPolicy`; align `iter_python_files` prune vs `iter_project_entries` include
- `app/packaging/layout.py` — fix docstring (lines 122–130) to match code; align `_EXCLUDED_RELATIVE_PREFIXES` with inventory policy table
- `app/project/import_layout.py` — replace `_RESERVED_ROOT_NAMES` duplication with `app/core/constants.py` or shared policy module
- `app/packaging/dependency_audit.py` — document `extra_top_level_skips=("vendor",)` as explicit audit policy, not accidental skip

**Hard cutover deletes:** misleading `layout.py` full-`cbcs/` exclusion doc claim.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_inventory_parity.py -k cbcs_vendor
python3 run_tests.py tests/unit/packaging/test_packager.py
```

**Tests (new/extend):**
- Matrix: `cbcs/package.json`, `cbcs/runs`, `cbcs/logs`, `cbcs/cache`, `vendor/pkg.py`, `vendor/native.so`

---

### Step 1.3 — Search UI glob integration (PROJ-R-05)

**CC:** CC-PROJ-01 (search plane)

**Depends on:** PROJ-R-03

**Modify:**
- `app/editors/search_panel.py` (~59–79, ~104) — route `exclude_globs` through `EffectiveExcludes` overlay or convert to equivalent relative-path patterns at search boundary
- `app/project/file_excludes.py` — add `merge_search_globs(effective, exclude_globs)` if needed

**Hard cutover deletes:** second untyped exclude plane in search.

**Proof:**
```bash
python3 run_tests.py tests/unit/editors/test_search_panel.py tests/unit/project/test_inventory_parity.py -k search
```

**Four themes:** search panel exclude behavior smoke in Light + HC Dark.

---

## 7. Wave 2 — Snapshot orchestration at shell boundary

**Blocks:** CC-PROJ-03, CC-PROJ-13, CC-PROJ-20 (partial)

**Aligns with:** Intelligence Wave 4 Step 4.1 (CC-15)

### Step 2.1 — Project inventory orchestrator (PROJ-R-06)

**CC:** CC-PROJ-03

**Depends on:** PROJ-R-03, PROJ-R-04

**Create:**
- `app/shell/project_inventory_orchestrator.py` (~120–180 LOC) — owns generation token, effective excludes, cached `ProjectInventorySnapshot`

**Modify:**
- `app/shell/intelligence_cache_workflow.py` — request snapshot from orchestrator instead of implicit rebuild
- `app/shell/main_window.py` or session host — wire orchestrator on project open/close
- `app/project/file_inventory.py` — optional `snapshot_generation: int` field on snapshot or wrapper type

**Work:**
1. Build snapshot once on project open, rescan, exclude-change.
2. Tree signature polling uses snapshot fingerprint for Python analysis set, not full `iter_project_entries` walk where possible.

**Hard cutover deletes:** none yet (consumers migrated in 2.2).

**Proof:**
```bash
python3 run_tests.py tests/unit/shell/test_project_inventory_orchestrator.py
```

**Four themes:** project open/rescan smoke — status bar/index kickoff in Light + Dark.

---

### Step 2.2 — Inject snapshot into intelligence consumers (PROJ-R-07)

**CC:** CC-PROJ-03, CC-PROJ-20 (partial)

**Depends on:** PROJ-R-06

**Modify:**
- `app/intelligence/symbol_index.py` — accept required `inventory_snapshot` from caller; delete internal `build_project_inventory_snapshot` at ~120 when snapshot provided
- `app/intelligence/diagnostics_service.py` — `find_unresolved_imports` (~78–82): require snapshot from caller; delete fallback rebuild with empty excludes
- `app/intelligence/completion_providers.py` — `provide_project_module_items` / `provide_project_symbol_items` (~171, ~223): require snapshot; delete fallback rebuilds
- `app/intelligence/completion_broker.py` — thread snapshot into provider calls
- `app/shell/intelligence_cache_workflow.py`, `lint_workflow.py` (~220–228) — pass orchestrator snapshot

**Hard cutover deletes:**
- Fallback `build_project_inventory_snapshot(project_root_text)` on production hot paths in the three intelligence modules
- `_PROJECT_MODULE_CACHE` global in `completion_providers.py` if still present

**Proof:**
```bash
rg 'build_project_inventory_snapshot' app/intelligence/   # only test utilities or explicit None-guard tests
python3 run_tests.py tests/unit/intelligence/test_symbol_index.py tests/unit/intelligence/test_completion_providers.py tests/unit/intelligence/test_diagnostics_service.py
```

---

### Step 2.3 — Rescan/save orchestration cleanup (PROJ-R-08)

**CC:** CC-PROJ-13

**Depends on:** PROJ-R-06, PROJ-R-07

**Modify:**
- `app/shell/project_rescan_workflow.py` (~49–68) — tier rescan: tree refresh vs plugin reload vs intelligence reindex
- `app/shell/editor_tab_workflow.py` (~767–790) — poll uses snapshot fingerprint; `cbcs/cache` churn must not trigger Python reindex
- `app/shell/intelligence_cache_workflow.py` — demote poll-triggered full reload when fingerprint unchanged

**Hard cutover deletes:** save-new-file double `update_symbol_index_cache` scheduling.

**Proof:**
```bash
python3 run_tests.py tests/unit/shell/test_project_rescan_workflow.py tests/unit/shell/test_editor_tab_workflow_inventory.py
```

**Four themes:** save new file → single index refresh observable in problems/outline.

---

### Step 2.4 — Snapshot unit tests (PROJ-R-09)

**CC:** CC-PROJ-03, CC-PROJ-21

**Depends on:** PROJ-R-06, PROJ-R-07

**Create:**
- `tests/unit/project/test_inventory_snapshot.py` — builder, module names, exclude propagation
- `tests/unit/project/test_inventory_orchestration.py` — spy: project open → one walk before symbol index + import analysis + completion fallback

**Modify:**
- Enable previously xfail parity tests from PROJ-R-01

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_inventory_snapshot.py tests/unit/project/test_inventory_orchestration.py
```

---

## 8. Wave 3 — Module identity SSOT

**Blocks:** CC-PROJ-04, CC-PROJ-14, CC-PROJ-15

**Aligns with:** Intelligence Wave 4 Step 4.3 (CC-12 partial)

### Step 3.1 — Layout-aware import rewrite (PROJ-R-10)

**CC:** CC-PROJ-04, CC-PROJ-12 (partial)

**Depends on:** PROJ-R-06 (layout load uses project context)

**Modify:**
- `app/project/import_rewrite.py` — thread `ProjectImportLayout` into `plan_import_rewrites`; delete `_module_name_from_relative_path` (62–72)
- `app/shell/project_tree_controller.py` — pass layout from manifest when planning rewrites
- `tests/unit/project/test_import_rewrite.py` — add `src/` layout move/rename cases

**Hard cutover deletes:** `_module_name_from_relative_path` in `import_rewrite.py`.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_import_rewrite.py -k src_layout
python3 run_tests.py tests/integration/project/test_tree_file_operations_integration.py
```

**Four themes:** move/rename under `src/` in project tree — verify imports updated.

---

### Step 3.2 — Collapse path-to-module helpers (PROJ-R-11)

**CC:** CC-PROJ-04

**Depends on:** PROJ-R-10, PROJ-R-07

**Modify:**
- `app/project/file_inventory.py` — `_module_name_from_python_path` (275–294): layout-only; delete naive fallback tail
- `app/intelligence/completion_providers.py` — delete `_module_name_from_path` (408–416), `_module_name_from_relative_path` (419–428); warm-cache path uses snapshot canonical `module_names` or `discover_canonical_project_modules`
- `app/project/import_layout.py` — ensure `discover_canonical_project_modules` is sole bulk naming entry

**Hard cutover deletes:** triplicate naive helpers.

**Proof:**
```bash
rg '_module_name_from_relative_path|_module_name_from_python_path' app/   # empty except import_layout internals
python3 run_tests.py tests/unit/project/test_inventory_snapshot.py tests/unit/intelligence/test_completion_providers.py
```

---

### Step 3.3 — Entry/layout helper inventory cutover (PROJ-R-12)

**CC:** CC-PROJ-14

**Depends on:** PROJ-R-03, PROJ-R-04

**Modify:**
- `app/project/project_service.py` — `_infer_default_entry_file` (370–397): replace `iterdir` with filtered inventory or layout search bases
- `app/project/project_service.py` — `_resolve_module_reference_to_entry` (442–456): use `ProjectImportLayout.import_search_bases` not hardcoded `[project_root, project_root / "src"]`
- `app/project/import_layout.py` — `suggest_missing_source_root` (306–317): replace `iterdir` with inventory point-probe helper

**Hard cutover deletes:** hardcoded `candidate_roots = [project_root, project_root / "src"]`.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_project_service.py -k entry
python3 run_tests.py tests/unit/project/test_import_layout.py
```

---

### Step 3.4 — Finish `python_structure` cutover (PROJ-R-13)

**CC:** CC-PROJ-15

**Depends on:** PROJ-R-11

**Modify:**
- `app/intelligence/completion_providers.py` — replace duplicate `_collect_top_level_symbols_from_ast` / `_extract_target_names` (372–405) with `python_structure.collect_completion_symbol_names`
- `app/intelligence/python_structure.py` — add explicit `SymbolExtractionScope` enum (top-level vs nested) if product requires nested symbols in completion
- Align index doc vs `ast.walk` behavior — pick one scope and test-lock

**Hard cutover deletes:** duplicate AST walkers in `completion_providers.py`.

**Proof:**
```bash
python3 run_tests.py tests/unit/intelligence/test_python_structure.py tests/unit/intelligence/test_completion_providers.py
```

---

## 9. Wave 4 — Packaging inventory cutover

**Blocks:** CC-PROJ-08, CC-PROJ-09, CC-PROJ-16, CC-PROJ-23

### Step 4.1 — Packaging payload iterator (PROJ-R-14)

**CC:** CC-PROJ-08

**Depends on:** PROJ-R-04

**Create:**
- `iter_packaging_payload_entries(project_root, ...)` in `app/project/file_inventory.py` or `app/packaging/payload_policy.py`

**Modify:**
- `app/packaging/artifact_builder.py` — replace `_copy_project_tree` `rglob("*")` (~334) with inventory-backed iterator
- `app/packaging/layout.py` — delegate exclusion checks to shared policy object

**Hard cutover deletes:** `source_root.rglob("*")` in project payload copy.

**Proof:**
```bash
rg 'rglob\("' app/packaging/artifact_builder.py   # empty for project source
python3 run_tests.py tests/unit/packaging/test_packager.py
```

---

### Step 4.2 — Copy vs audit policy matrix (PROJ-R-15)

**CC:** CC-PROJ-08, CC-PROJ-16

**Depends on:** PROJ-R-14

**Create:**
- `PackagingPayloadPolicy` dataclass — explicit copy set vs audited Python set vs shipped-but-not-audited rules

**Modify:**
- `app/packaging/dependency_audit.py` — name audit skip of `vendor/` as policy; remove accidental double-filter where possible
- `tests/unit/packaging/test_packaging_payload_policy.py` — matrix fixture

**Proof:**
```bash
python3 run_tests.py tests/unit/packaging/test_packaging_payload_policy.py tests/integration/packaging/test_project_packaging_workflow.py
```

---

### Step 4.3 — Orphan native payload blocking (PROJ-R-16)

**CC:** CC-PROJ-09, CC-PROJ-07 (partial)

**Depends on:** PROJ-R-14; **requires** `native_extension_scan.py` stub from PROJ-R-20a (see §13) or full PROJ-R-20 merge

**Stub contract (PROJ-R-20a):** land minimal `app/project/native_extension_scan.py` with `iter_native_artifacts_in_tree(base: Path) -> Iterator[Path]` before PROJ-R-16 if B5/B6 run in parallel. PROJ-R-16 consumes this API only; full classifier/ingest/auditor convergence completes in PROJ-R-20.

**Modify:**
- `app/packaging/validator.py` — post-policy payload scan for orphan native artifacts under `vendor/`
- `app/packaging/dependency_audit.py` — emit blocking issue for unreferenced native binaries in payload set

**Proof:**
```bash
python3 run_tests.py tests/unit/packaging/test_dependency_audit.py -k orphan_native tests/unit/packaging/test_validator.py
```

---

### Step 4.4 — Lower-risk traversal cleanup (PROJ-R-17)

**CC:** CC-PROJ-23

**Depends on:** PROJ-R-14

**Modify:**
- `app/packaging/validator.py` — `_discover_hidden_paths` (~323–334): inventory-backed walk when scanning project root
- `app/packaging/installer_manifest.py` — document artifact-root `rglob` (~245) as post-build checksum pass (keep separate)

**Hard cutover deletes:** project-source `rglob` in validator hidden-path discovery.

**Proof:**
```bash
python3 run_tests.py tests/unit/packaging/test_validator.py
```

---

## 10. Wave 5 — Classifier convergence

**Blocks:** CC-PROJ-05, CC-PROJ-06, CC-PROJ-07, CC-PROJ-17, CC-PROJ-19

### Step 5.1 — Fix dependency direction (PROJ-R-18)

**CC:** CC-PROJ-06

**Depends on:** none for module creation; PROJ-R-14 recommended for packaging alignment

**Create:**
- `app/project/import_resolution.py` — move filesystem resolution from `app/intelligence/import_resolver.py` (core `resolve_import_at_base` orchestration stays project-owned)
- `app/project/runtime_import_probe.py` — move per-import subprocess probe from `app/intelligence/runtime_import_probe.py`

**Do not relocate:** `app/bootstrap/runtime_module_probe.py` — that module probes **runtime inventory discovery** (slim stdlib / FreeCAD modules), not per-import classification. Classifier continues to consume inventory via existing bootstrap APIs.

**Modify:**
- `app/project/dependency_classifier.py` — import project-layer modules only (delete lines 33–34 intelligence imports)
- `app/intelligence/import_resolver.py` — thin adapter importing `app/project/import_resolution.py`
- `app/intelligence/runtime_import_probe.py` — hard-cutover re-export from `app/project/runtime_import_probe.py` in same PR, then delete duplicate implementation

**Hard cutover deletes:** `from app.intelligence` in `app/project/dependency_classifier.py`.

**Proof:**
```bash
rg 'from app\.intelligence' app/project/   # empty
python3 run_tests.py tests/unit/intelligence/test_import_resolver.py tests/unit/intelligence/test_runtime_import_probe.py tests/unit/project/test_dependency_classifier.py
```

---

### Step 5.2 — One classification pipeline (PROJ-R-19)

**CC:** CC-PROJ-05, CC-PROJ-19, CC-PROJ-17 (partial)

**Depends on:** PROJ-R-18

**Create:**
- `RuntimeModuleInventory` carrier in `dependency_classifier.py` — distinguish unknown, known-empty, known-populated
- `tests/unit/project/test_classifier_parity.py` — parametrized matrix

**Modify:**
- `app/project/dependency_classifier.py` — unify stdlib/inventory ordering; make `is_module_resolvable` adapter over shared `_classify` core
- `app/intelligence/import_diagnostics.py` — consume unified policy
- `app/packaging/dependency_audit.py` — thread `ProjectImportLayout`; delete parallel `_classify_relative_import` (211–254) in favor of classifier

**Hard cutover deletes:** divergent decision trees between `classify_module` and `is_module_resolvable`.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_classifier_parity.py tests/unit/project/test_dependency_classifier.py tests/unit/packaging/test_dependency_audit.py
```

---

### Step 5.3 — Native-extension scan primitive (PROJ-R-20)

**CC:** CC-PROJ-07

**Depends on:** PROJ-R-18

**Create:**
- `app/project/native_extension_scan.py` — `iter_native_artifacts_in_tree(base, scope)` and `import_resolves_to_native(...)` helpers

**Sub-step PROJ-R-20a (stub, optional early merge):** export `iter_native_artifacts_in_tree` only — unblocks PROJ-R-16 parallel with Wave 5 remainder.

**Modify:**
- `app/project/dependency_ingest.py` — replace `_classify_directory` rglob (~197–201) with shared primitive
- `app/plugins/auditor.py` — consume shared suffix policy (~48–66)
- `app/project/dependency_classifier.py` — delegate `has_compiled_extension_candidate` to primitive

**Hard cutover deletes:** three independent native scan implementations.

**Proof:**
```bash
python3 run_tests.py tests/unit/project/test_native_extension_scan.py tests/unit/project/test_dependency_ingest.py tests/unit/plugins/
```

---

### Step 5.4 — Manifest consistency in validation flow (PROJ-R-21)

**CC:** CC-PROJ-17

**Depends on:** PROJ-R-19

**Modify:**
- `app/packaging/validator.py` — `build_package_validation_report` (~79–88): call `check_manifest_consistency` from `dependency_audit.py` (458–491)
- Map manifest taxonomy (`pure_python`, `native_extension`, `runtime`) to classifier categories

**Hard cutover deletes:** dead `check_manifest_consistency` helper if validation subsumes it differently — prefer wiring over deletion.

**Proof:**
```bash
python3 run_tests.py tests/unit/packaging/test_dependency_manifest_audit.py tests/unit/packaging/test_validator.py
```

---

## 11. Wave 6 — Diagnostics adapter + shell probe policy

**Blocks:** CC-PROJ-10, CC-PROJ-11, CC-PROJ-12, CC-PROJ-18, CC-PROJ-20

**Aligns with:** Intelligence Wave 5 (CC-14)

### Step 6.1 — Explain adapter (PROJ-R-22)

**CC:** CC-PROJ-10

**Depends on:** PROJ-R-19

**Create:**
- `app/intelligence/import_explanations.py` — map `ClassifiedModule` + layout hints → explanation templates

**Modify:**
- `app/intelligence/diagnostics_service.py` — `explain_unresolved_import` (227–349): delegate to adapter; delete parallel taxonomy tree
- Delete private import of `_module_path_prefix_exists_at_base` if replaced by layout/classifier metadata

**Hard cutover deletes:** bespoke explain classifier tree in `diagnostics_service.py`.

**Proof:**
```bash
python3 run_tests.py tests/unit/intelligence/test_diagnostics_service.py -k explain tests/unit/project/test_classifier_parity.py
```

---

### Step 6.2 — Static hot paths + quick-fix ownership (PROJ-R-23)

**CC:** CC-PROJ-11, CC-PROJ-12

**Depends on:** PROJ-R-22 partial

**Modify:**
- `app/intelligence/import_diagnostics.py` — default `allow_runtime_import_probe=False` on all hot collection paths
- `app/shell/lint_workflow.py` — import analysis (~225–226): stop hardcoding `allow_runtime_import_probe=True`; manual lint (~127) keeps explicit probe
- `app/intelligence/code_actions.py` — carry module name/source-root as typed `CodeDiagnostic.detail` metadata (~247–256)
- `app/shell/python_style_workflow.py` — unified apply owner for `add_source_root` (~262–289); delete message-string parsing

**Hard cutover deletes:** `_extract_unresolved_module_name` message-prefix parsing contract.

**Proof:**
```bash
python3 run_tests.py tests/unit/intelligence/test_import_diagnostics_probe.py tests/unit/intelligence/test_code_actions.py tests/unit/shell/test_python_style_workflow.py -k source_root
```

**Four themes:** Problems panel quick-fix in HC Light + HC Dark.

---

### Step 6.3 — Diagnostics decomposition (PROJ-R-24)

**CC:** CC-PROJ-18

**Depends on:** PROJ-R-22

**Split `app/intelligence/diagnostics_service.py` (~511 LOC) into:**
- `app/intelligence/diagnostics_models.py` (extend if needed)
- `app/intelligence/builtin_lint_rules.py` — AST walkers currently at ~360–477
- `import_explanations.py` (from 6.1)
- Thin `diagnostics_service.py` facade or hard-cutover re-exports

**Hard cutover deletes:** monolithic explain + walker co-location.

**Proof:**
```bash
wc -l app/intelligence/diagnostics_service.py app/intelligence/builtin_lint_rules.py app/intelligence/import_explanations.py
find app/intelligence -name 'diagnostics*.py' -exec wc -l {} + | awk '$1>250'
python3 run_tests.py tests/unit/intelligence/test_diagnostics_service.py
```

---

### Step 6.4 — Cache truth + index atomicity (PROJ-R-25)

**CC:** CC-PROJ-20

**Depends on:** PROJ-R-07

**Modify:**
- `app/intelligence/completion_broker.py` (~416–451) — whitelist cache tier; do not blanket-tag approximate on cache hits
- `app/intelligence/completion_providers.py` — gate SQLite indexed paths on snapshot generation
- `app/intelligence/symbol_index.py` (~74–110) — atomic delta commit where practical

**Proof:**
```bash
python3 run_tests.py tests/unit/intelligence/test_completion_broker.py tests/unit/intelligence/test_symbol_index.py -k cache
```

---

## 12. PR catalog (25 PRs)

| PR | Wave | CC primary | UI / four themes | Parallel batch | Est. LOC Δ |
|----|------|------------|-------------------|----------------|------------|
| PROJ-R-01 | 0.1 | CC-PROJ-21 | No | B0 | +120 tests |
| PROJ-R-02 | 0.2 | CC-PROJ-02 | No | B0 | +40 types |
| PROJ-R-03 | 1.1 | CC-PROJ-01 | No | B1 | +80 |
| PROJ-R-04 | 1.2 | CC-PROJ-02,16 | No | B1 | +60 |
| PROJ-R-05 | 1.3 | CC-PROJ-01 | Yes | B1 | +30 |
| PROJ-R-06 | 2.1 | CC-PROJ-03 | Yes | B2 | +150 |
| PROJ-R-07 | 2.2 | CC-PROJ-03,20 | No | B2 | −40 |
| PROJ-R-08 | 2.3 | CC-PROJ-13 | Yes | B3 | −30 |
| PROJ-R-09 | 2.4 | CC-PROJ-03,21 | No | B3 | +200 tests |
| PROJ-R-10 | 3.1 | CC-PROJ-04,12 | Yes | B4 | +20 |
| PROJ-R-11 | 3.2 | CC-PROJ-04 | No | B4 | −80 |
| PROJ-R-12 | 3.3 | CC-PROJ-14 | No | B4 | +30 |
| PROJ-R-13 | 3.4 | CC-PROJ-15 | No | B4 | −120 |
| PROJ-R-14 | 4.1 | CC-PROJ-08 | No | B5 | +100 |
| PROJ-R-15 | 4.2 | CC-PROJ-08,16 | No | B5 | +80 tests |
| PROJ-R-16 | 4.3 | CC-PROJ-09 | No | B5 | +40 |
| PROJ-R-17 | 4.4 | CC-PROJ-23 | No | B5 | −20 |
| PROJ-R-18 | 5.1 | CC-PROJ-06 | No | B6 | +200 − moves |
| PROJ-R-19 | 5.2 | CC-PROJ-05,19,17 | No | B6 | +120 |
| PROJ-R-20 | 5.3 | CC-PROJ-07 | No | B6 | +90 |
| PROJ-R-21 | 5.4 | CC-PROJ-17 | No | B6 | +20 |
| PROJ-R-22 | 6.1 | CC-PROJ-10 | No | B7 | −150 |
| PROJ-R-23 | 6.2 | CC-PROJ-11,12 | Yes | B7 | +40 |
| PROJ-R-24 | 6.3 | CC-PROJ-18 | No | B7 | split |
| PROJ-R-25 | 6.4 | CC-PROJ-20 | No | B7 | +30 |
| PROJ-R-26 | optional | CC-PROJ-22 | No | after B7 | hygiene |

**Note:** PROJ-R-20 may split into **PROJ-R-20a** (stub API for R-16) + **PROJ-R-20** (full convergence) when B5/B6 parallelize.

---

## 13. Parallel execution batches (implementation agents)

Use separate git worktrees/branches per batch row. **Never parallelize** PRs that touch the same files.

| Batch | PRs | Mode | Preconditions |
|-------|-----|------|---------------|
| **B0** | PROJ-R-01, PROJ-R-02 | **2 parallel agents** | None — start immediately |
| **B1** | PROJ-R-03 → PROJ-R-04 → PROJ-R-05 | Sequential (R-05 needs R-03) | B0 complete |
| **B2** | PROJ-R-06 → PROJ-R-07 | Sequential | B1 complete |
| **B3** | PROJ-R-08, PROJ-R-09 | **2 parallel agents** after R-07 | PROJ-R-07 merged |
| **B4** | PROJ-R-10, PROJ-R-11, PROJ-R-12, PROJ-R-13 | **4 parallel agents** | PROJ-R-07 merged; R-10 before R-11 |
| **B5** | PROJ-R-14 → PROJ-R-15; PROJ-R-16 ∥ PROJ-R-17 after R-14 **and R-20a stub** | Mixed | PROJ-R-04 merged; **do not start R-16 without R-20a stub or R-20 merge** |
| **B6** | PROJ-R-18 → PROJ-R-19; PROJ-R-20a (stub) may land before R-19; PROJ-R-20 ∥ PROJ-R-21 after R-19 | Mixed | PROJ-R-14 recommended before R-18 |
| **B7** | PROJ-R-22 → PROJ-R-23 → PROJ-R-24 → PROJ-R-25 | Sequential | PROJ-R-19 merged |

**Aggressive parallelization window:** After PROJ-R-04 merges, run **B5 (packaging)** in parallel with **B2/B3 (orchestration)** — disjoint file sets (`app/packaging/` vs `app/shell/`).

**Bottleneck PRs:** PROJ-R-03 (exclude contract), PROJ-R-06 (orchestrator), PROJ-R-18 (layer inversion), PROJ-R-19 (classifier unification).

### Suggested agent parallel launch (first sprint)

| Agent | PR | Focus |
|-------|-----|-------|
| Agent A | PROJ-R-01 | Parity fixtures + test relocation |
| Agent B | PROJ-R-02 | Policy vocabulary types |
| — wait for merge — | | |
| Agent C | PROJ-R-03 | Effective excludes |
| Agent D | PROJ-R-04 | cbcs/vendor policy (parallel if C touches different files — prefer sequential) |
| — after B1 — | | |
| Agent E | PROJ-R-06 | Orchestrator |
| Agent F | PROJ-R-14 | Packaging payload iterator (parallel with E) |

---

## 14. Out of scope and boundaries

| Item | Disposition | Reference |
|------|-------------|-----------|
| `editor_tab_workflow.py` full decomposition (984 LOC) | Inventory-polling overlap only in PROJ-R-08 | TN-PROJ-SHELL |
| `product_builder.py` allowlist traversal | Keep separate — artifact staging not user project | TN-PROJ-PKG |
| `installer_manifest.py` post-build checksum `rglob` | Document as artifact-root pass; not project SSOT | CC-PROJ-23 |
| Intelligence session/broker thread safety | Owned by Intelligence Wave 1 | Out of scope |
| R6 full test audit / low-signal test deletion | After R4/R5 stabilize | CC-PROJ-21 backlog |
| CC-PROJ-22 typing/doc hygiene | PROJ-R-26 optional R1 sweep or explicit waive at program end | P2 |
| `local_history_workflow.py` rglob on delete targets | User-selected paths; not project inventory SSOT | Discovery note |
| `vendor_exclude_migration.py` os.walk | One-time migration tool; document exception | Gate 1 exception |

### Allowed post-cutover traversal sites

| Site | Reason |
|------|--------|
| `file_inventory.walk_project` | SSOT kernel |
| `product_builder._copytree_filtered` | Product artifact allowlist |
| `installer_manifest.build_artifact_checksums` | Post-build artifact checksums |
| `tree_sitter_cp39` staging | Native wheel overlay |

---

## 15. Risk-first test register

| Test file | CC | Justification |
|-----------|-----|---------------|
| `tests/unit/project/inventory_parity_fixtures.py` | CC-PROJ-01,02,21 | File-set parity matrix inputs |
| `tests/unit/project/test_inventory_parity.py` | CC-PROJ-01,02 | Tree/search/python/packaging disagree today |
| `tests/unit/project/test_inventory_snapshot.py` | CC-PROJ-03,04 | Snapshot builder + module names |
| `tests/unit/project/test_inventory_orchestration.py` | CC-PROJ-03,13 | One-walk-per-generation spy |
| `tests/unit/shell/test_project_inventory_orchestrator.py` | CC-PROJ-03 | Shell ownership boundary |
| `tests/unit/shell/test_project_rescan_workflow.py` | CC-PROJ-13 | Rescan tier separation |
| `tests/unit/shell/test_editor_tab_workflow_inventory.py` | CC-PROJ-13 | Poll fingerprint vs full reindex |
| `tests/unit/project/test_import_rewrite.py` (relocated) | CC-PROJ-04 | `src/` layout rewrite correctness |
| `tests/unit/project/test_file_inventory.py` (extend) | CC-PROJ-21 | Symlink parity (`test_symlink` pattern exists — extend to snapshot/orchestration) |
| `tests/unit/packaging/test_packaging_payload_policy.py` | CC-PROJ-08,16 | Copy vs audit matrix |
| `tests/unit/packaging/test_dependency_audit.py` (extend) | CC-PROJ-09 | Orphan native blocking |
| `tests/unit/packaging/test_dependency_manifest_audit.py` | CC-PROJ-17 | Manifest consistency wired into validator |
| `tests/unit/packaging/test_validator.py` (extend) | CC-PROJ-09,17,23 | Hidden-path + orphan native validation |
| `tests/unit/project/test_classifier_parity.py` | CC-PROJ-05,10 | Cross-consumer classification agreement |
| `tests/unit/project/test_native_extension_scan.py` | CC-PROJ-07 | Native primitive shared semantics |
| `tests/unit/project/test_dependency_ingest.py` (extend) | CC-PROJ-07 | Ingest uses shared native primitive |
| `tests/unit/intelligence/test_import_diagnostics_probe.py` (extend) | CC-PROJ-11 | Hot path never probes |
| `tests/unit/intelligence/test_diagnostics_service.py` (extend) | CC-PROJ-10 | Explain adapter parity |
| `tests/unit/shell/test_python_style_workflow.py` (extend) | CC-PROJ-12 | Source-root quick-fix E2E |
| `tests/unit/intelligence/test_completion_broker.py` (extend) | CC-PROJ-20 | Cache tier metadata |
| `tests/unit/intelligence/test_python_structure.py` | CC-PROJ-15 | Shared AST fixture |

**Do not add:** constant pinning, `to_dict` snapshots, source-text lint tests, mock-dominated inventory tests.

---

## 16. Verification gates

### Per-PR (minimum)

```bash
python3 testing/run_test_shard.py fast
npx pyright
```

### Per-wave

| Wave | Extra gates |
|------|-------------|
| 0 | `python3 run_tests.py tests/unit/project/test_inventory_parity.py tests/unit/project/test_import_rewrite.py` |
| 1 | P0 checklist §4 (CC-PROJ-01,02 partial) |
| 2 | `python3 run_tests.py tests/unit/project/test_inventory_orchestration.py tests/unit/shell/test_project_inventory_orchestrator.py` |
| 3 | `rg '_module_name_from_relative_path' app/` empty; rewrite src_layout tests green |
| 4 | `rg 'rglob\("' app/packaging/artifact_builder.py` empty; payload policy tests green |
| 5 | `rg 'from app\.intelligence' app/project/` empty; classifier parity green |
| 6 | `test_import_diagnostics_probe.py` green; diagnostics files ≤250 LOC each |

### R4-focused gate ( Waves 1–4 )

```bash
python3 run_tests.py tests/unit/project/ tests/unit/editors/test_search_panel.py tests/unit/intelligence/test_symbol_index.py tests/unit/intelligence/test_completion_providers.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/packaging/
python3 testing/run_test_shard.py fast
npx pyright
```

### R5-focused gate ( Waves 5–6 )

```bash
python3 run_tests.py tests/unit/project/test_dependency_classifier.py tests/unit/project/test_dependency_ingest.py tests/unit/project/test_classifier_parity.py tests/unit/project/test_native_extension_scan.py tests/unit/packaging/test_dependency_audit.py tests/unit/packaging/test_validator.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/intelligence/test_import_diagnostics_probe.py tests/unit/intelligence/test_import_resolver.py tests/unit/intelligence/test_runtime_import_probe.py
python3 testing/run_test_shard.py fast
npx pyright
```

### Full program (before declaring complete)

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py integration
python3 run_tests.py tests/unit/project/ tests/unit/packaging/ tests/unit/intelligence/test_symbol_index.py tests/unit/intelligence/test_completion_providers.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/intelligence/test_import_diagnostics_probe.py tests/integration/packaging/
npx pyright
rg 'from app\.intelligence' app/project/
rg 'build_project_inventory_snapshot' app/intelligence/   # no bare fallbacks on hot paths
rg 'rglob\("' app/packaging/artifact_builder.py
rg '_module_name_from_relative_path' app/
```

---

## 17. Manual acceptance register (four themes)

Record in each UI PR summary: themes verified + date.

| Scenario | PRs | AT reference |
|----------|-----|--------------|
| Project open → index/diagnostics/completion agree on modules | PROJ-R-06, R-07 | Open `src/` layout project; module completion lists `my_pkg` not `src.my_pkg` |
| Search excludes match tree | PROJ-R-05 | Search with `build/**` exclude |
| Move/rename under `src/` | PROJ-R-10 | Tree move updates imports |
| Save new file → single reindex | PROJ-R-08 | New module appears once in outline/problems |
| Package export with vendor/cbcs | PROJ-R-14, R-15, R-16 | Export blocked on orphan `.so`; metadata ships |
| Import analysis / PY200 | PROJ-R-23 | Problems panel; no UI freeze on open |
| Source-root quick fix | PROJ-R-23 | Apply fix from problems panel |

**Themes:** Light, Dark, HC Light (`#FFFFFF` surfaces), HC Dark (`#000000` surfaces) — per `.cursor/rules/ui_light_dark_mode.mdc`.

---

## 18. Intelligence Wave convergence checklist

Project SSOT remediation must not fight Intelligence Wave 1 tracks. Coordinate at these seams:

| Intelligence CC | Project PR | Convergence criterion |
|-----------------|------------|----------------------|
| CC-15 (R4 inventory) | PROJ-R-06, R-07 | Same snapshot owner; delete intelligence fallback builds |
| CC-12 (python structure) | PROJ-R-13 | Completion uses `python_structure` helpers |
| CC-14 (diagnostics god module) | PROJ-R-22, R-24 | Explain adapter + decomposition |
| CC-22 (import_rewrite move) | PROJ-R-10 | Already in project layer; finish module identity |
| CC-11 (cache-as-truth) | PROJ-R-25 | Broker tier + generation gate |

**Rule:** If Intelligence Wave 4/5 PRs land first, Project SSOT PRs must **rebase and hard-cutover** any remaining parallel paths — no long-lived dual orchestration.

---

## 19. Implementation agent playbook

1. Read §4 P0 checklist and §3 CC row for assigned PR.
2. Check **Depends on** — do not start until preconditions merged.
3. Implement with **hard cutover** — delete old path same PR.
4. Run per-PR gates (§16).
5. Record four themes if UI PR (§17).
6. Update CC matrix status in PR description (`Closes CC-PROJ-XX`).
7. Update TN-PROJ-INTEG cross-ref table with closure evidence when P0/P1 theme completes.

---

## 20. Self-review checklist (plan author)

- [x] Every CC-PROJ-01 … CC-PROJ-23 has ≥1 step with concrete file paths
- [x] Every CC has verification gate and primary PR (§3)
- [x] Every step lists Depends on (via §3 matrix + §5–11)
- [x] P0 closure table with copy-paste commands (§4)
- [x] Hard cutover deletes enumerated per wave
- [x] Program completion definition (§1)
- [x] Four-theme matrix (§17)
- [x] §15 covers all P0/P1 tests referenced in §4–§11 (including shell/packaging proof files)
- [x] 25 PRs + optional PROJ-R-26 cataloged (§12)
- [x] PROJ-R-20a stub contract for R-16 parallel safety (§9 Step 4.3, §13)
- [x] Probe relocation distinguishes `runtime_import_probe` vs `runtime_module_probe` (§10 Step 5.1)
- [x] Raw finding closure checklist (§21)
- [x] Parallel batches with conflict notes (§13)
- [x] Intelligence Wave convergence documented (§18)
- [x] Out-of-scope / allowed traversal sites (§14)
- [x] R4/R5 focused gate commands (§16)
- [x] Subagent-verified line numbers for hot spots (orchestrator gap, classifier inversion, packaging rglob, rewrite fork)

**Plan status: implementation-ready.**

---

## 21. Raw finding closure checklist (criterion #10)

Use [`_findings/TN-PROJ-INTEG.md`](_findings/TN-PROJ-INTEG.md) cross-reference table (raw ID → CC-PROJ) as the canonical map. At program end, update that table's closure column with PR evidence.

| Slice critic | Raw findings | CC owner(s) | Closure evidence |
|--------------|-------------|-------------|------------------|
| TN-PROJ-INV (15) | CC-PROJ-01,02,03,04,14,16,21,22 | PROJ-R-01…R-04, R-06…R-12, R-14…R-15 | Parity + snapshot tests green |
| TN-PROJ-CONSUMERS (13) | CC-PROJ-03,04,15,20,21 | PROJ-R-07, R-11, R-13, R-25 | Orchestration spy + completion cutover |
| TN-PROJ-REWRITE (14) | CC-PROJ-04,12,14,21,22 | PROJ-R-10, R-12, R-23 | src_layout rewrite + quick-fix tests |
| TN-PROJ-CLASS (12) | CC-PROJ-05,06,07,17,19,21,22 | PROJ-R-18…R-21 | Classifier parity + zero intelligence imports |
| TN-PROJ-DIAG (15) | CC-PROJ-06,10,11,12,18,21,22 | PROJ-R-22…R-24 | Explain adapter + probe mock + decomposition |
| TN-PROJ-PKG (14) | CC-PROJ-01,02,07,08,09,16,17,23 | PROJ-R-14…R-17, R-20 | Payload policy matrix + orphan native block |
| TN-PROJ-SHELL (12) | CC-PROJ-02,03,13,14,21 | PROJ-R-06…R-09 | Rescan tier + orchestrator tests |

**Waive without PR:** only P2 hygiene with no product impact (CC-PROJ-22) — record explicit waive in program completion summary.

---

## 22. Optional hygiene PR (PROJ-R-26)

**CC:** CC-PROJ-22

**Depends on:** all P0/P1 PRs merged

**Modify (minimal R1 sweep):**
- `app/project/file_inventory.py` — hoist inline import at ~276–277 to module top
- `app/project/dependency_classifier.py` — fix misleading re-export docstring (lines 22–24)
- `app/intelligence/diagnostics_service.py` — remove duplicate AST offset helpers if still present

**Disposition:** optional; program may complete with explicit CC-PROJ-22 waive.

---

*Derived from Project SSOT Wave 1 thermo review @ `042be49`. Update CC status columns in PRs; update this document only when scope shifts.*
