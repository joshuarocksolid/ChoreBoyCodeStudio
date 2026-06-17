# Project SSOT Wave 1 — Remediation Plan (Phase 2)

Status: ready for implementation approval  
Implementation plan: [`project_ssot_wave_1_implementation_plan.md`](project_ssot_wave_1_implementation_plan.md)
Baseline: `042be49e5777c587391ddbb396b7ea150e296dfe`
Source review: [`project_ssot_wave_1_thermo_review_2026-06-16.md`](project_ssot_wave_1_thermo_review_2026-06-16.md)
Integration themes: [`_findings/TN-PROJ-INTEG.md`](_findings/TN-PROJ-INTEG.md)

**Do not start implementation until this plan is approved.** Phase 1 (document-only review) is complete.

---

## Goals

1. Close all **P0** themes CC-PROJ-01 … CC-PROJ-09 before declaring R4/R5 complete.
2. Establish one owned project inventory policy: excludes, `cbcs`, vendor, payload, and module identity.
3. Enforce **one `ProjectInventorySnapshot` per project generation** at the shell/project boundary.
4. Cut packaging export over to an explicit inventory-backed payload policy.
5. Make `dependency_classifier.py` the real classifier boundary: no intelligence imports, no parallel explain tree, no native detector fork.
6. Add risk-first parity tests for file sets, classifier outcomes, native-extension blocking, and snapshot orchestration.

---

## Non-negotiable rules (every PR)

- Hard cutover importers; no long-lived compatibility wrapper for old traversal/classification paths.
- Python 3.9 syntax; no dot-prefixed runtime paths.
- No new project-root `rglob`/`os.walk` outside `file_inventory` or explicit artifact-only code.
- No new import classification outside `dependency_classifier` or a clearly named lower-level primitive it owns.
- No diagnostic message-string parsing as a contract when explicit metadata can carry the value.
- Tests only when risk-first gate applies: file-set parity, import classification parity, native-extension blocking, data rewrite correctness, subprocess probe policy, and orchestration call counts.
- UI-touching shell remediation must record four-theme validation or explain the gap.

---

## Wave 0 — Policy foundations + parity scaffolding

**Blocks:** CC-PROJ-21 (partial), CC-PROJ-02 (partial)

**Goal:** Add test scaffolding and named policy types before changing behavior.

### Step 0.1 — Inventory parity fixtures

**Files:**
- New test helper under `tests/unit/project/`
- Update relevant project/packaging tests only

**Work:**
1. Add fixtures for common project trees: `src/` layout, `vendor/`, `cbcs/package.json`, `cbcs/runs`, slash-pattern excludes, orphan `.so`.
2. Add helper assertions that compare tree/search/python/package file sets without changing production code.
3. Move import rewrite tests from intelligence package to project package if needed, preserving test names/coverage.

**Gate:** Existing tests still pass; new helper is inert until waves consume it.

### Step 0.2 — Policy vocabulary

**Files:**
- `app/project/file_inventory.py`
- `docs/ARCHITECTURE.md` or this remediation doc if architecture update is too broad

**Work:**
1. Introduce explicit names for inventory scopes and metadata policy (`tree_entries`, `python_analysis`, `text_search`, `packaging_payload`, `packaging_audit`).
2. Document vendor's roles: user dependency, project exclude default, packaging payload, audit skip.
3. Do not migrate callers yet.

**Gate:** Types/docs only; no behavior changes.

---

## Wave 1 — Exclude, `cbcs`, and vendor policy unification

**Blocks:** CC-PROJ-01, CC-PROJ-02, CC-PROJ-16

**Goal:** Make the effective file-set policy explicit before centralizing snapshots.

### Step 1.1 — Effective excludes as a shared contract

**Files:**
- `app/project/file_excludes.py`
- `app/project/file_inventory.py`
- `app/project/project_service.py`
- `app/editors/search_panel.py`
- shell call sites that currently compute excludes

**Work:**
1. Create one helper for effective project excludes.
2. Preserve historical behavior where required, but name the policy rather than hiding it behind `pattern_mode`.
3. Make slash-pattern behavior consistent for tree/search/python analysis or document/test an intentional difference.

**Gate:** A project with `exclude_patterns=["src/generated/*"]` yields consistent tree/search/python-analysis results.

### Step 1.2 — `cbcs` and vendor policy table

**Files:**
- `app/project/file_inventory.py`
- `app/packaging/layout.py`
- `app/project/import_layout.py`
- tests under `tests/unit/project/` and `tests/unit/packaging/`

**Work:**
1. Centralize `cbcs` policy: metadata included in tree/payload, analysis prunes it, `runs/logs/cache` pruned from packaging payload.
2. Align `is_packaging_excluded_path` docs with implementation.
3. Replace hardcoded reserved-name lists where they duplicate constants/policy.

**Gate:** Matrix test covers `cbcs/package.json`, `cbcs/runs`, `cbcs/logs`, `cbcs/cache`, `vendor/pkg.py`, `vendor/native.so`.

### Step 1.3 — Search UI glob integration

**Files:**
- `app/editors/search_panel.py`
- `app/project/file_excludes.py`

**Work:**
1. Route UI `exclude_globs` through the shared effective-exclude representation, or keep them as a named overlay with tests.
2. Avoid a second untyped exclude plane in search.

**Gate:** Search and tree behavior for `build/**` and `src/*.gen.py` is characterized.

---

## Wave 2 — Snapshot orchestration at the shell boundary

**Blocks:** CC-PROJ-03, CC-PROJ-13, CC-PROJ-20 (partial)

**Goal:** Share one inventory snapshot per project generation across symbol index, diagnostics, and completion.

### Step 2.1 — Project inventory orchestrator

**Files:**
- New focused shell/project module for inventory generation ownership
- `app/shell/intelligence_cache_workflow.py`
- `app/shell/lint_workflow.py`
- `app/shell/editor_tab_workflow.py`

**Work:**
1. Build `ProjectInventorySnapshot` once on project open/rescan/exclude-change.
2. Attach a generation token and effective excludes to the snapshot.
3. Make tree signature polling distinguish metadata churn from Python analysis changes.

**Gate:** Spy test: project open builds one snapshot before first symbol index/import analysis/completion fallback.

### Step 2.2 — Inject snapshot into consumers

**Files:**
- `app/intelligence/symbol_index.py`
- `app/intelligence/diagnostics_service.py`
- `app/intelligence/completion_providers.py`
- `app/intelligence/completion_broker.py`
- shell callers

**Work:**
1. Pass the shared snapshot into symbol indexing, unresolved import analysis, and completion providers.
2. Delete fallback snapshot builders on production hot paths; keep a clear test/utility path if needed.
3. Ensure all consumers use the same `python_file_paths` and `module_names`.

**Gate:** Same snapshot object/value is observed by symbol index, diagnostics, and completion in a project-open scenario.

### Step 2.3 — Rescan/save orchestration cleanup

**Files:**
- `app/shell/project_rescan_workflow.py`
- `app/shell/editor_tab_workflow.py`
- `app/shell/intelligence_cache_workflow.py`

**Work:**
1. Split rescan tiers: file tree refresh, plugin reload, and intelligence reindex should not always happen together.
2. Prevent save-new-file double scheduling.
3. Use snapshot fingerprint/generation for intelligence, not broad project tree signature.

**Gate:** Save-new-file triggers one index refresh; `cbcs/cache` churn does not trigger Python reindex.

### Step 2.4 — Snapshot unit tests

**Files:**
- `tests/unit/project/test_inventory_snapshot.py` (new)
- `tests/unit/project/test_inventory_orchestration.py` (new)
- `tests/unit/shell/test_project_inventory_orchestrator.py` (new)

**Work:**
1. Add builder, module-name, and exclude-propagation tests for `ProjectInventorySnapshot`.
2. Add spy test: project open builds one walk before symbol index, import analysis, and completion.
3. Enable parity fixture tests scaffolded in Wave 0.

**Gate:** Manifest high-gap rows for snapshot/orchestration addressed; `build_project_inventory_snapshot` has dedicated coverage.

---

## Wave 3 — Module identity SSOT

**Blocks:** CC-PROJ-04, CC-PROJ-14, CC-PROJ-15

**Goal:** Make `import_layout` the only path-to-module authority.

### Step 3.1 — Layout-aware import rewrite

**Files:**
- `app/project/import_rewrite.py`
- `app/project/import_layout.py`
- `app/shell/project_tree_controller.py`

**Work:**
1. Thread `ProjectImportLayout` through import rewrite planning.
2. Delete naive relative-path module derivation in rewrite.
3. Add `src/` layout move/rename tests.

**Gate:** Moving `src/my_pkg/module.py` rewrites imports to `my_pkg.*`, not `src.my_pkg.*`.

### Step 3.2 — Collapse path-to-module helpers

**Files:**
- `app/project/file_inventory.py`
- `app/intelligence/completion_providers.py`
- `app/project/import_layout.py`

**Work:**
1. Route inventory snapshot module names through canonical layout helpers.
2. Delete completion provider module-name forks.
3. Make fallback behavior explicit for files outside source roots.

**Gate:** `rg "_module_name_from_relative_path|_module_name_from_python_path" app/` shows only intentional canonical helpers.

### Step 3.3 — Entry/layout helper inventory cutover

**Files:**
- `app/project/project_service.py`
- `app/project/import_layout.py`

**Work:**
1. Replace entry inference `iterdir` and layout source-root suggestion scans with inventory primitives or explicit point-probe helpers.
2. Keep point lookups distinct from project tree walks.

**Gate:** Excluded `vendor/run.py` is not inferred as the default entry.

### Step 3.4 — Finish `python_structure` cutover

**Files:**
- `app/intelligence/python_structure.py`
- `app/intelligence/completion_providers.py`
- related tests

**Work:**
1. Replace duplicate completion AST collectors with shared structure helpers.
2. Decide and type the symbol extraction scope (top-level vs nested).

**Gate:** Duplicate AST collectors are deleted; tests cover top-level and nested symbol behavior.

---

## Wave 4 — Packaging inventory cutover

**Blocks:** CC-PROJ-08, CC-PROJ-09, CC-PROJ-16, CC-PROJ-23

**Goal:** Make packaging copy/audit file-set differences explicit and tested.

### Step 4.1 — Packaging payload iterator

**Files:**
- `app/project/file_inventory.py` or a focused packaging/project bridge module
- `app/packaging/artifact_builder.py`
- `app/packaging/layout.py`

**Work:**
1. Add `iter_packaging_payload_entries` or equivalent policy-backed iterator.
2. Replace source project `rglob("*")` in payload copy.
3. Keep product-builder artifact traversal separate unless the policy truly matches.

**Gate:** Payload copy order and excludes are deterministic and inventory-backed.

### Step 4.2 — Copy vs audit policy matrix

**Files:**
- `app/packaging/dependency_audit.py`
- `app/packaging/layout.py`
- tests under `tests/unit/packaging/`

**Work:**
1. Name and test the distinction between payload files and audited Python files.
2. Preserve intended behavior: metadata can ship, runtime logs/cache cannot, top-level vendor Python may be skipped by static first-party audit.
3. Remove accidental double-filtering where possible.

**Gate:** Fixture with `vendor`, `cbcs`, `.git`, `__pycache__`, and Python/non-Python files passes a copy/audit matrix.

### Step 4.3 — Orphan native payload blocking

**Files:**
- `app/packaging/validator.py`
- `app/packaging/dependency_audit.py`
- classifier/native scan primitive from Wave 5 if available

**Work:**
1. Detect native artifacts in payload even if unreferenced by imports.
2. Block export or report an explicit validation issue before copy.

**Gate:** `vendor/orphan.so` with no Python import blocks package validation.

### Step 4.4 — Lower-risk traversal cleanup

**Files:**
- `app/packaging/validator.py`
- `app/packaging/installer_manifest.py`

**Work:**
1. Replace hidden-path source traversal with policy-backed inventory if it scans a project root.
2. Leave artifact checksum traversal separate, but document why it is artifact-root traversal.

**Gate:** Hidden-path advisory matches inventory-derived scan.

---

## Wave 5 — Classifier convergence

**Blocks:** CC-PROJ-05, CC-PROJ-06, CC-PROJ-07, CC-PROJ-17, CC-PROJ-19

**Goal:** Make classification a real project-layer contract.

### Step 5.1 — Fix dependency direction

**Files:**
- New `app/project/import_resolution.py` or equivalent
- `app/project/dependency_classifier.py`
- `app/intelligence/import_resolver.py`
- `app/intelligence/runtime_import_probe.py`

**Work:**
1. Move filesystem import resolution into project layer.
2. Move or wrap runtime import probing in a neutral/project-owned module.
3. Leave intelligence as a consumer, not an owner.

**Gate:** `rg "from app\.intelligence" app/project/dependency_classifier.py` is empty.

### Step 5.2 — One classification pipeline

**Files:**
- `app/project/dependency_classifier.py`
- `app/intelligence/import_diagnostics.py`
- `app/packaging/dependency_audit.py`

**Work:**
1. Introduce an explicit `RuntimeModuleInventory` carrier to distinguish unknown, known-empty, and known-populated inventories.
2. Make `is_module_resolvable` an adapter over the same classification path, or document/test the policy difference.
3. Thread `ProjectImportLayout`/metadata into packaging audit.

**Gate:** Parametrized parity suite covers stdlib, slim runtime inventory, first-party `src/`, vendored pure Python, vendored native, runtime-only, and missing imports across classifier/audit/diagnostics.

### Step 5.3 — Native-extension scan primitive

**Files:**
- `app/project/dependency_classifier.py` or new focused native scan module
- `app/project/dependency_ingest.py`
- `app/plugins/auditor.py`
- `app/packaging/dependency_audit.py`

**Work:**
1. Define separate helpers for "tree contains native artifact" and "import name resolves to native artifact".
2. Migrate ingest, audit, and plugin auditor to the shared primitives.

**Gate:** Same wheel/tree/plugin fixture produces expected classification in all three paths.

### Step 5.4 — Manifest consistency in validation flow

**Files:**
- `app/packaging/dependency_audit.py`
- `app/packaging/validator.py`
- tests under `tests/unit/packaging/`

**Work:**
1. Wire `check_manifest_consistency` into validation or delete it if obsolete.
2. Map manifest taxonomy (`pure_python`, `native_extension`, `runtime`) to audit categories.

**Gate:** Package validation fails on manifest/vendor drift.

---

## Wave 6 — Diagnostics adapter + shell probe policy

**Blocks:** CC-PROJ-10, CC-PROJ-11, CC-PROJ-12, CC-PROJ-18, CC-PROJ-20

**Goal:** Make diagnostics consume project-layer contracts instead of duplicating them.

### Step 6.1 — Explain adapter

**Files:**
- `app/intelligence/diagnostics_service.py`
- new `app/intelligence/import_explanations.py` or project-layer equivalent
- `app/project/dependency_classifier.py`

**Work:**
1. Build explanations from `ClassifiedModule` plus layout hints.
2. Delete private `_module_path_prefix_exists_at_base` import.
3. Remove the parallel classifier tree.

**Gate:** Existing explanation tests pass through classifier-backed path; parity matrix green.

### Step 6.2 — Static hot paths, explicit probes

**Files:**
- `app/intelligence/import_diagnostics.py`
- `app/shell/lint_workflow.py`
- runtime explainer paths

**Work:**
1. Default lint/import collection remains static-only.
2. Runtime probe only happens on explicit explain/manual audit paths.
3. Ensure manual lint does not spawn a subprocess per unresolved import.

**Gate:** Test spies prove hot lint/import analysis never calls AppRun probe by default.

### Step 6.3 — Quick-fix ownership

**Files:**
- `app/intelligence/code_actions.py`
- `app/shell/python_style_workflow.py`
- diagnostics models

**Work:**
1. Carry module name/source-root intent as typed diagnostic metadata.
2. Choose one apply owner for `add_source_root`; do not parse user-facing message strings.

**Gate:** Source-root quick fix end-to-end test applies without message parsing.

### Step 6.4 — Diagnostics decomposition and cache truth

**Files:**
- `app/intelligence/diagnostics_service.py`
- `app/intelligence/completion_broker.py`
- `app/intelligence/symbol_index.py`

**Work:**
1. Split diagnostics into focused modules after classifier adapter lands.
2. Preserve cache tier/degradation metadata; cache hits should not be blanket-tagged approximate.
3. Make symbol index delta commit atomic where practical.

**Gate:** No diagnostics lane file grows past a healthy size cap; cache hit keeps explicit cache tier.

---

## Validation commands

### Per-PR minimum

```bash
python3 testing/run_test_shard.py fast
npx pyright
```

### R4-focused gate

```bash
python3 run_tests.py tests/unit/project/ tests/unit/editors/test_search_panel.py tests/unit/intelligence/test_symbol_index.py tests/unit/intelligence/test_completion_providers.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/packaging/
python3 testing/run_test_shard.py fast
npx pyright
```

### R5-focused gate

```bash
python3 run_tests.py tests/unit/project/test_dependency_classifier.py tests/unit/project/test_dependency_ingest.py tests/unit/project/test_dependency_manifest.py tests/unit/packaging/test_dependency_audit.py tests/unit/packaging/test_validator.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/intelligence/test_import_diagnostics_probe.py tests/unit/intelligence/test_import_resolver.py tests/unit/intelligence/test_runtime_import_probe.py
python3 testing/run_test_shard.py fast
npx pyright
```

### Completion criteria

- All P0 themes CC-PROJ-01 … CC-PROJ-09 are closed or explicitly product-waived.
- `TN-PROJ-INTEG` cross-reference table can be updated with evidence for each closure.
- No new traversal/classification bypasses appear under `app/`.
- Fast shard and pyright pass.

---

## Deferred work

- R6 full test audit: low-signal test cleanup belongs after R4/R5 ownership stabilizes.
- R7 out-of-scope audit: scripts, root launchers, bundled plugins, and templates remain separate.
- Full shell hotspot split: `editor_tab_workflow.py` line-count risk is real but only inventory-polling overlap belongs in this wave.

*Remediation plan derived from Project SSOT Wave 1 thermo review @ `042be49`. Update this document when CC-PROJ themes close or scope shifts.*
