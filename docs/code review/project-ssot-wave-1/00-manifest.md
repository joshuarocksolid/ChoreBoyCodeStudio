# Scope manifest: project-ssot-wave-1 thermo-nuclear review

Status: Wave 1 kickoff
Baseline commit: `042be49e5777c587391ddbb396b7ea150e296dfe`
Date: 2026-06-16
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear maintainability pass over the Project SSOT work started during Intelligence Wave 1 remediation:

- R4 inventory SSOT — `app/project/file_inventory.py`, traversal consumers, snapshot orchestration, packaging enumeration overlap.
- R5 dependency/runtime classifier SSOT — `app/project/dependency_classifier.py`, diagnostics/package audit convergence, native-extension policy, runtime probe ownership.

This wave follows the backlog ordering in [`shell-wave-1`](../shell-wave-1/shell_wave_1_thermo_review_2026-05-25.md) §7 and the implementation reality after [`intelligence-wave-1`](../intelligence-wave-1/intelligence_wave_1_thermo_review_2026-06-16.md). Intelligence remediation (`65d486a`) created the core SSOT modules, but this review verifies whether the ownership boundaries are actually thermo-clean.

---

## Metric sweep (at kickoff)

| Metric | Value |
|--------|------:|
| Baseline commit | `042be49e5777c587391ddbb396b7ea150e296dfe` |
| `app/project/` Python LOC | 3,167 (19 modules) |
| SSOT quartet LOC | 946 (`file_inventory.py` 294, `import_layout.py` 318, `dependency_classifier.py` 246, `import_rewrite.py` 88) |
| Largest project modules | `project_manifest.py` 517, `project_service.py` 482, `import_layout.py` 318, `file_inventory.py` 294 |
| Direct `file_inventory` importers | 10 files under `app/` |
| Direct `dependency_classifier` importers | 5 production files under `app/` plus tests |
| Live `rglob('*.py')` in `app/` | 0 (remaining hits are docstrings) |
| Packaging modules using `rglob` | 5 (`validator.py`, `artifact_builder.py`, `product_builder.py`, `installer_manifest.py`, root `packaging/install.py`) |
| Independent inventory snapshot builders | 3 consumer paths (`symbol_index`, `completion_providers`, `diagnostics_service`) |
| `os.walk` in `app/project/` | 2 executable sites (`file_inventory.py`, `vendor_exclude_migration.py`) |
| `# type: ignore` in scoped union | 8 |
| Bare `except Exception:` in scoped union | 6 |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/project -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
wc -l app/project/file_inventory.py app/project/dependency_classifier.py app/project/import_layout.py app/project/import_rewrite.py
rg "rglob\(" app/packaging app/project packaging --type py -n
rg "build_project_inventory_snapshot|iter_python_files|iter_text_file_paths|iter_project_entries" app --type py -l
rg "from app\.project\.dependency_classifier|from app\.project\.file_inventory" app --type py -l
rg "from app\.intelligence\.import_resolver|from app\.intelligence\.runtime_import_probe" app/project --type py
```

---

## Current state summary

| Area | Status | Review target |
|------|--------|---------------|
| Eight historical `rglob('*.py') + cbcs skip` sites | **Migrated** to `iter_python_files` | Validate orchestration, not raw migration |
| Search panel | **Migrated** to `iter_text_file_paths` | Validate exclude parity |
| Project enumeration | **Migrated** to `iter_project_entries` | Validate `cbcs/` include semantics |
| Import rewrite | **Moved** to `app/project/import_rewrite.py` and uses inventory | Validate caller cutover and rewrite scan semantics |
| Packaging dependency audit | **Partial** — uses `iter_python_files` but double-filters with packaging excludes | Validate copy/audit/file-set drift |
| Packaging artifact copy/validation | **Open** — raw `rglob("*")` in multiple modules | Validate whether this blocks R4 acceptance |
| `ProjectInventorySnapshot` | **Partial** — API exists, production sharing absent | Validate one-walk-per-generation gate |
| Classifier module | **Partial** — public module exists | Validate policy convergence and boundary direction |
| Packaging private intelligence imports | **Fixed** | Verify no regression |
| Diagnostics explain path | **Open** — parallel decision tree remains | Validate R5 SSOT gap |
| Runtime probe ownership | **Open** — project classifier imports intelligence probe/resolver | Validate layer inversion |

---

## Architecture gates (all critics)

1. All project `.py` discovery routes through `app/project/file_inventory.py`; no new `rglob('*.py')` or ad-hoc `cbcs/` skip.
2. Packaging project enumeration routes through the inventory API, or the exception is documented and protected by parity tests.
3. `cbcs/` policy is explicit per API: tree enumeration may include it, intelligence/package analysis must not accidentally drift.
4. Exclude policy has one effective source per use case; avoid a third unowned plane between `file_excludes`, packaging layout, and import layout.
5. One project generation should not trigger N independent full walks; snapshot orchestration must be owned.
6. `ProjectInventorySnapshot` is the canonical module-list contract for intelligence subsystems.
7. Import classification routes through `dependency_classifier.py`; no parallel stdlib lists or native-extension scans without a clearly named lower-level primitive.
8. `classify_module` and `is_module_resolvable` must agree on representative packaging-vs-PY200 cases, or the difference must be an explicit product policy.
9. `explain_unresolved_import` should adapt classifier/layout results, not grow a second classifier.
10. Dependency direction should be `intelligence -> project`, not `project -> intelligence`.
11. Packaging must not import private intelligence symbols.
12. Native-extension detection must not fork between ingest, audit, and plugin auditor.

---

## In scope — slice critics (7)

| ID | Primary files | Cluster |
|----|---------------|---------|
| TN-PROJ-INV | `file_inventory.py`, `file_excludes.py`, `project_service.py`, `search_panel.py` | Inventory core + excludes |
| TN-PROJ-CONSUMERS | `symbol_index.py`, `completion_providers.py`, `diagnostics_service.py`, `intelligence_cache_workflow.py`, `completion_broker.py` | Snapshot orchestration + intelligence consumers |
| TN-PROJ-REWRITE | `import_rewrite.py`, `import_layout.py`, `project_tree_controller.py`, `code_actions.py` | Import layout/rewrite ownership |
| TN-PROJ-CLASS | `dependency_classifier.py`, `dependency_ingest.py`, `dependency_manifest.py`, `plugins/auditor.py` | Classifier core + native taxonomy |
| TN-PROJ-DIAG | `diagnostics_service.py`, `import_diagnostics.py`, `import_resolver.py`, `runtime_import_probe.py`, `code_actions.py` | Diagnostics/classifier convergence |
| TN-PROJ-PKG | `dependency_audit.py`, `validator.py`, `artifact_builder.py`, `product_builder.py`, `installer_manifest.py`, `layout.py` | Packaging enumeration + audit |
| TN-PROJ-SHELL | `intelligence_cache_workflow.py`, `lint_workflow.py`, `main_window.py`, `run_launch_workflow.py`, `editor_tab_workflow.py` | Shell orchestration of inventory refresh |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-PROJ-INTEG | Dedupe cross-cutting themes into `CC-PROJ-01...`; map to R4/R5 fix waves |

---

## Test coverage gaps (critics must validate)

| Module / behavior | Dedicated tests | Gap severity |
|-------------------|-----------------|--------------|
| `build_project_inventory_snapshot` / `ProjectInventorySnapshot` | None | **High** |
| One-walk-per-generation orchestration | None | **High** |
| Classifier vs packaging audit vs diagnostics parity | None | **High** |
| Packaging copy vs inventory file-set parity | None | **High** |
| `code_actions` source-root quick fix contract | Partial | **High** |
| `completion_providers` inventory snapshot pass-through | Thin | **High** |
| `dependency_classifier` unit matrix | Strong | Low, but lacks cross-consumer parity |
| `file_inventory` iterators | Strong | Medium, snapshot untested |
| `diagnostics_service` | Strong but broad | High, explain/classifier drift |

---

## Prior wave cross-read

| Theme | Current status |
|-------|----------------|
| Intelligence CC-11 parallel `SymbolIndexWorker` | Class replaced, but cache-as-acceleration and scheduler semantics still need validation |
| Intelligence CC-12 Python structure extraction fork | `python_structure.py` exists; outline and completion duplication remain candidates |
| Intelligence CC-14 diagnostics god module | Partially decomposed; `diagnostics_service.py` still owns explain tree and built-in walkers |
| Intelligence CC-15 R4 inventory partial | Snapshot API exists; shared orchestration is still open |
| Intelligence CC-22 misplaced `import_rewrite` | Moved to `app/project/`; validate importers and tests |
| Shell wave 2 backlog | R4 Project Inventory SSOT is the planned successor wave |
| Shell wave 3 backlog | R5 Dependency Classifier SSOT is the next planned wave |

---

## Out of scope

- Fix commits, new tests, pyright fixes, or code remediation.
- Full `app/project/project_manifest.py` or tree UI review unless inventory call sites are involved.
- Intelligence session/broker thread safety, which was owned by Intelligence Wave 1.
- Full shell hotspot review (`editor_tab_workflow.py` line-count risk is only in scope for inventory polling).
- R6 test audit and R7 out-of-scope audit.
- Deep bundled plugin review; only packaging/plugin classifier boundaries are in scope.

---

## Read order for fix agents

1. [`project_ssot_wave_1_thermo_review_2026-06-16.md`](project_ssot_wave_1_thermo_review_2026-06-16.md) — consolidated rollup.
2. [`_findings/TN-PROJ-INTEG.md`](_findings/TN-PROJ-INTEG.md) — deduped CC themes and fix waves.
3. Per-slice evidence in `_findings/TN-PROJ-*.md`.
4. [`project_ssot_wave_1_remediation_plan.md`](project_ssot_wave_1_remediation_plan.md) — implementation sequencing.
5. [`project_ssot_wave_1_implementation_plan.md`](project_ssot_wave_1_implementation_plan.md) — executable PR catalog (PROJ-R-01…R-26).
6. [`docs/deslop/AUDIT_app_remaining_handoff.md`](../../deslop/AUDIT_app_remaining_handoff.md) — R4/R5 briefs.
7. [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — canonical project/import/classifier ownership.

---

## Artifact layout

```text
docs/code review/project-ssot-wave-1/
├── 00-manifest.md
├── project_ssot_wave_1_thermo_review_2026-06-16.md
├── project_ssot_wave_1_remediation_plan.md
├── project_ssot_wave_1_implementation_plan.md
├── _findings/
│   ├── _README.md
│   ├── TN-PROJ-INV.md
│   ├── TN-PROJ-CONSUMERS.md
│   ├── TN-PROJ-REWRITE.md
│   ├── TN-PROJ-CLASS.md
│   ├── TN-PROJ-DIAG.md
│   ├── TN-PROJ-PKG.md
│   ├── TN-PROJ-SHELL.md
│   └── TN-PROJ-INTEG.md
```
