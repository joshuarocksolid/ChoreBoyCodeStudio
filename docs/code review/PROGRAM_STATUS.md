```yaml
overall: IN_PROGRESS
current_phase: P1
current_item: P1-3
last_verified_commit: 5db7a69
last_session_ended: 2026-06-23T22:00:00Z
metrics:
  app_files_gte_1000: 0
  main_window_methods: 28
  shell_window_any_count: 66
  files_gte_700: 5
  diagnostics_service_loc: 225
  dependency_classifier_loc: 293
  project_intelligence_imports: 0
phases:
  P0: done
  P1: in_progress
  P2: pending
  P3: pending
  P4: pending
blockers: []
next_actions:
  - "P1-3 CC-PROJ-14 tail (PROJ-R-12): replace import_layout.py iterdir/glob entry probes with inventory-backed paths; then write project_ssot_wave_1_remediation_closure doc and advance P1-4 Run W1 baseline"
sessions_completed: 17
```

## Session 17 summary (2026-06-23) — PROJ-R-24 CC-PROJ-18 + P1 audit

### Baseline @ HEAD (5db7a69)

| Gate | Result |
|------|--------|
| `rg 'from app\.intelligence' app/project/` | **0** |
| Diagnostics lane split (`builtin_lint_rules`, `import_explanations`, `diagnostics_models`) | **present** |
| `diagnostics_service.py` LOC (pre-fix) | **259** (>250 gate) |
| app files ≥1k | **0** |

### Landed this session

**PROJ-R-24 / CC-PROJ-18 (ACCEPT):** Moved `apply_lint_rule_profile` + severity mapping to `lint_profile.py`; removed dead imports from `diagnostics_service.py`. Facade now **225 LOC** (all diagnostics lane files ≤250). Fixed test import to `pyflakes_adapter`.

**P1 CC-PROJ matrix audit @ HEAD:**

| CC | Status | Evidence |
|----|--------|----------|
| CC-PROJ-10 | **ACCEPT** | `import_explanations.py`; `explain_unresolved_import` delegates |
| CC-PROJ-11 | **ACCEPT** | Hot lint `allow_runtime_import_probe=False`; `test_import_diagnostics_probe.py` |
| CC-PROJ-12 | **ACCEPT** | `code_actions.py` typed `add_source_root`; `test_code_actions.py` |
| CC-PROJ-13 | **ACCEPT** | `ProjectInventoryOrchestrator`; `test_inventory_orchestration.py` |
| CC-PROJ-14 | **PARTIAL** | Vendor entry skip landed (session 16); `import_layout.py` `iterdir`/`glob` remain |
| CC-PROJ-15 | **ACCEPT** | `python_structure.py` consumed by symbol_index/completion_providers |
| CC-PROJ-16 | **ACCEPT** | `test_inventory_parity.py -k cbcs_vendor` |
| CC-PROJ-17 | **ACCEPT** | `test_dependency_manifest_audit.py` |
| CC-PROJ-18 | **ACCEPT** | Lane LOC gate: `diagnostics_service.py` **225**, `builtin_lint_rules` **138**, `import_explanations` **211** |
| CC-PROJ-19 | **ACCEPT** | `RuntimeModuleInventory` tri-state in `dependency_classifier.py` |
| CC-PROJ-20 | **ACCEPT** | Broker `_reuse_cached_envelope` preserves tier/`source_phase` metadata |
| CC-PROJ-21…23 | **deferred** | P2 backlog |

### Verification @ session end

| Gate | Result |
|------|--------|
| `test_diagnostics_service.py` + probe + code_actions + manifest audit | **PASS** (56) |
| pyright | **0 errors** |
| fast shard | **FLaky** — `test_main_window_background_teardown` intermittent F in shard; **PASS** in isolation (pre-existing) |

### Wave status

| Wave | Status |
|------|--------|
| editors-wave-1 | ACCEPT |
| shell-wave-2 | ACCEPT (P1 milestones) |
| intelligence-wave-1 | ACCEPT (P1 milestones) |
| project-ssot-wave-1 | **in_progress** — P0+P1 audit done; CC-PROJ-14 tail blocks formal closure |
| run-wave-1 | open (P1-4) |

### Uncommitted working tree (ready for parent commit)

```
 M app/intelligence/diagnostics_service.py
 M app/intelligence/lint_profile.py
 M tests/unit/intelligence/test_diagnostics_service.py
 M docs/code review/PROGRAM_STATUS.md
```

### Verification commands (re-run before CC-PROJ-14 tail)

```bash
find app/intelligence -name 'diagnostics*.py' -exec wc -l {} + | awk '$1>250'
python3 run_tests.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/project/
python3 testing/preflight_test_env.py
python3 testing/run_test_shard.py fast
npx pyright
```
