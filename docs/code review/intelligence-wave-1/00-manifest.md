# Scope manifest: intelligence-wave-1 thermo-nuclear review

Status: Wave 1 kickoff  
Baseline commit: `ce176983f3d3434b390718692047583c9b38c4ed`  
Date: 2026-06-16  
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear maintainability pass over the intelligence subsystem:

- [`app/intelligence/`](../../app/intelligence/) — semantic session, completion broker, Jedi/Rope engines, diagnostics, outline, symbol index, import resolution
- Shell/editor seam — orchestration outside the package that calls intelligence directly

Sequenced as **Shell Wave 5** in [`shell_wave_1_thermo_review_2026-05-25.md`](../shell-wave-1/shell_wave_1_thermo_review_2026-05-25.md) §7 and [`run_wave_1_thermo_review_2026-05-25.md`](../run-wave-1/run_wave_1_thermo_review_2026-05-25.md) §8.

**Prior context:** MainWindow refactor landed (`main_window.py` 542 LOC); intelligence wiring lives in [`main_window_composition.py`](../../app/shell/main_window_composition.py). Phase 2+3 thermo remediation added [`import_diagnostics.py`](../../app/intelligence/import_diagnostics.py) and R4 [`file_inventory.py`](../../app/project/file_inventory.py) (partial migration).

---

## Metric sweep (at kickoff)

| Metric | Value |
|--------|------:|
| Baseline commit | `ce176983f3d3434b390718692047583c9b38c4ed` |
| `app/intelligence/` Python LOC | 6,395 (32 modules) |
| Largest intelligence modules | `diagnostics_service.py` 614, `outline_service.py` 510, `jedi_engine.py` 502, `completion_broker.py` 453, `completion_providers.py` 433 |
| Intelligence files ≥ 700 LOC | 0 |
| Shell seam LOC | `semantic_navigation_workflow.py` **1,103** (only `app/` file **>1k**), `editor_intelligence_controller.py` 252, `main_window_composition.py` 595 |
| Editor intelligence imports | 9 files under `app/editors/` |
| Shell intelligence imports | 22 files under `app/shell/` |
| Total importing files (shell + editors) | 31 |
| Bare `except Exception:` in `app/intelligence/` | 7 |
| `# type: ignore` in `app/intelligence/` | 2 |
| `window: Any` in shell + intelligence (sample) | 73 |
| Intelligence unit tests | 25 files under `tests/unit/intelligence/` |
| Intelligence integration tests | 1 file |
| Intelligence runtime_parity tests | 2 files |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/intelligence -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
wc -l app/shell/semantic_navigation_workflow.py app/intelligence/diagnostics_service.py
rg "from app\.intelligence|import app\.intelligence" app/shell app/editors --type py -l | wc -l
rg "^\s*except\s+Exception\s*:\s*$" app/intelligence --type py | wc -l
```

---

## In scope — slice critics (10)

| ID | Primary files | ~LOC | Cluster |
|----|---------------|-----:|---------|
| TN-INT-01 | `semantic_session.py`, `semantic_worker.py`, `semantic_facade.py`, `completion_service.py`, `semantic_models.py` | 1,187 | AD-016 session ownership |
| TN-INT-02 | `completion_broker.py`, `completion_context.py`, `completion_providers.py`, `completion_resolver.py`, `completion_models.py`, `completion_metrics.py` | 1,456 | Tier merge / broker policy |
| TN-INT-03 | `jedi_engine.py`, `jedi_runtime.py`, `semantic_utils.py` | 652 | Jedi engine adapter |
| TN-INT-04 | `symbol_index.py`, `api_index.py`, `import_resolver.py`, `runtime_import_probe.py`, `cache_controls.py` | 708 | Index + import resolution |
| TN-INT-05 | `diagnostics_service.py`, `lint_profile.py`, `code_actions.py`, `import_diagnostics.py` | 1,371 | Diagnostics god module |
| TN-INT-06 | `outline_service.py` | 510 | Outline dual path |
| TN-INT-07 | `refactor_engine.py`, `refactor_runtime.py`, `import_rewrite.py`, `latency_tracker.py` | 341 | Rename / import rewrite |
| TN-INT-SHELL-NAV | `semantic_navigation_workflow.py` | 1,103 | Shell navigation monolith |
| TN-INT-SHELL-SEAM | `main_window_composition.py`, `editor_intelligence_controller.py`, `lint_workflow.py`, `intelligence_cache_workflow.py`, `python_style_workflow.py`, `python_console_workflow.py` | ~1,400 | Composition + parallel workflows |
| TN-INT-SHELL-EDITORS | `code_editor_semantics.py`, `code_editor_widget.py`, `editor_tab_factory.py`, `editor_tab_workflow.py`, completion popup | ~1,500 | Editor boundary leaks |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-INT-INTEG | Dedupe cross-cutting themes → CC-01… IDs; map to R2/R3/R4/R5 fix waves |

---

## Prior wave cross-read (what changed since 2026-05-25 reviews)

| Theme | Status |
|-------|--------|
| shell-wave-1 CC-15 intelligence on MainWindow | **Moved** — logic now in `semantic_navigation_workflow.py` (1,103 LOC) |
| shell-wave-1 CC-01 agent debug logging | **Fixed** — grep gate empty under `app/` |
| Phase 2+3 import diagnostics | **Partial** — `import_diagnostics.py` extracted; `diagnostics_service.py` still god module |
| Phase 2+3 R4 inventory | **Partial** — `file_inventory.iter_python_files` exists; symbol index / diagnostics still re-walk |
| Run wave 1 remediation | **Done** — unrelated to intelligence slice |
| MainWindow under 1k | **Done** — 542 LOC; **`semantic_navigation_workflow.py` is new 1k+ violation** |

---

## Test coverage gaps (critics must validate)

| Module | Dedicated tests | Gap severity |
|--------|-----------------|--------------|
| `jedi_engine.py` | None (facade indirect only) | **High** |
| `runtime_introspection.py` | Import smoke only | **Critical** |
| `completion_providers.py` | Partial via service/broker | Moderate–High |
| `diagnostics_service.py` | 37 tests | Low |
| `outline_service.py` | 22 tests + runtime parity | Low |

---

## Shell seam summary (prep-C)

**Top boundary leaks:**
1. `semantic_navigation_workflow.py` second orchestrator — 7 direct intelligence imports + runtime merge beside controller
2. Duplicate outline paths — `editor_tab_workflow` + navigation both call `build_outline_from_source`
3. Lint via `workflow_broker` — never touches `SemanticSession`
4. `SymbolIndexWorker` + `RuntimeIntrospectionCoordinator` outside session
5. Split completion stacks — editor (controller + nav) vs REPL (`ReplSessionManager`)

**Revision gating:** Shared helpers in `semantic_navigation_workflow`; ad-hoc duplicate in `lint_workflow`; none in controller; menu blocking paths skip gate entirely.

---

## Out of scope

- Fix commits, test additions, pyright fixes in this round
- Full `main_window.py` review (shell-wave-1 except intelligence callbacks)
- Deep `app/runner/repl_completion.py` (note boundary only in TN-INT-SHELL-SEAM)
- R4/R5 **implementation** (note duplication only)

---

## Read order for fix agents

1. [`intelligence_wave_1_thermo_review_2026-06-16.md`](intelligence_wave_1_thermo_review_2026-06-16.md) — rollup (P0/P1/P2, fix waves)
2. [`_findings/TN-INT-INTEG.md`](_findings/TN-INT-INTEG.md) — deduped CC themes
3. Per-slice evidence in `_findings/TN-INT-*.md`
4. [`docs/deslop/AUDIT_app_remaining_handoff.md`](../deslop/AUDIT_app_remaining_handoff.md) — R2/R3/R4/R5 briefs
5. [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md) — AD-016, AD-017, AD-018, §17.4

---

## Artifact layout

```
docs/code review/intelligence-wave-1/
├── 00-manifest.md                    (this file)
├── intelligence_wave_1_thermo_review_2026-06-16.md
├── intelligence_wave_1_remediation_plan.md
├── _findings/
│   ├── _README.md
│   ├── TN-INT-01.md … TN-INT-07.md
│   ├── TN-INT-SHELL-NAV.md, TN-INT-SHELL-SEAM.md, TN-INT-SHELL-EDITORS.md
│   └── TN-INT-INTEG.md
```
