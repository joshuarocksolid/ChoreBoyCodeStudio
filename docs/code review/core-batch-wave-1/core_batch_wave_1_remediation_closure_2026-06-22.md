# Core Batch Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Core Batch Wave 1 remediation (P2-6 @ session 21–22)  
**Baseline review:** [core_batch_wave_1_thermo_review_2026-06-22.md](core_batch_wave_1_thermo_review_2026-06-22.md) @ `c4aed0a`  
**Remediation commits:** `c34dc1e`, `2a1f611`, `be4e8f8`  
**Verified commit:** `313dbf3` (+ this closure doc)  
**Verdict:** **ACCEPT (Core Batch Wave 1 P1 boundary milestones)** — bootstrap/core P1 residuals documented below

---

## 1. CC-CORE theme closure matrix

| CC | Priority | Commit(s) | Status | Evidence |
|----|----------|-----------|--------|----------|
| CC-CORE-01 | P1 | — | **deferred** | `constants.py` still **297** LOC; Wave 4 split backlog |
| CC-CORE-02 | P1 | `c34dc1e` | **partial** | `runtime_severity_rank()` SSOT in `support/contracts.py`; `DiagnosticItem` retained for health reports; probe → diagnostic adapter typed |
| CC-CORE-03 | P1 | `c34dc1e`, `2a1f611` | **closed** | Zero upward imports in `app/support/` and `app/ui/`; project/plugin/persistence/intelligence seams moved to `app/shell/` |
| CC-CORE-04 | P1 | `2a1f611` | **closed** | `support_bundle.py` **85** LOC (zip-only); collectors in `shell/support_bundle_collectors.py`; shell passes injected snapshots |
| CC-CORE-05 | P1 | `2a1f611` | **partial** | `ImportExplanationResolver` protocol + `shell/import_issue_adapter.py`; `runtime_explainer.py` **370** LOC monolith not domain-split |
| CC-CORE-06 | P1 | — | **deferred** | `startup_facade.py` still imports `run_editor` (Wave 3 bootstrap) |
| CC-CORE-07 | P1 | — | **deferred** | `capability_probe.py` still imports `python_tools.vendor_runtime`; lazy `treesitter.loader` (Wave 3 registry) |
| CC-CORE-08 | P1 | `be4e8f8` | **closed** | `HelpThemeTokens` protocol in `app/ui/theme_tokens.py`; `help_dialog.py` no longer imports `shell.theme_tokens` |
| CC-CORE-09 | P1 | — | **deferred** | `run_startup_capability_probe` / `run_minimal_startup_capability_probe` still duplicate runner loops |
| CC-CORE-10 | P1 | `c34dc1e` | **closed** | `capability_checks_from_probe(capability_report: CapabilityProbeReport)`; zero `: Any` in `app/support/` |
| CC-CORE-11 … 16 | P2 | — | **backlog** | Unchanged from thermo review §5 |

**Session 21–22 adjacent (Run Wave 1, not CC-CORE):** `674b55c` — `app/core/clear_console_contract.py` SSOT for REPL hint + toolbar tooltip; `test_clear_console_policy.py` characterization tests green @ HEAD.

---

## 2. Sub-package verdict flip @ verified baseline

| Sub-package | Thermo @ `c4aed0a` | Closure @ `313dbf3` | Rationale |
|-------------|--------------------|---------------------|-----------|
| `app/core/` | **ACCEPT** | **ACCEPT** | SSOT, size, purity unchanged |
| `app/bootstrap/` | **ACCEPT** *(conditional)* | **ACCEPT** *(conditional)* | CC-CORE-06/07/09 carry; largest file `capability_probe.py` **379** LOC |
| `app/support/` | **REJECT** | **ACCEPT** | Layer inversion removed; downward contracts + merge-only diagnostics |
| `app/ui/` | **REJECT** | **ACCEPT** | Theme token protocol breaks shell dependency |
| `app/filesystem/` | **ACCEPT** | **ACCEPT** | Unchanged |
| **Overall** | **REJECT** | **ACCEPT** | 5/5 pass size + storage-path gates; 4/5 thermo-clean; bootstrap conditional P1 carry only |

---

## 3. Metric gates @ verified baseline

| Metric | Kickoff @ `c4aed0a` | Closure @ `313dbf3` |
|--------|----------------------|---------------------|
| Foundation modules (scoped) | 26 | **30** (+`contracts.py`, `preflight_paths.py`, `ui/theme_tokens.py`, `core/clear_console_contract.py`) |
| Total scoped LOC | 3,492 | **3,443** |
| Files ≥700 LOC | 0 | **0** |
| Files ≥1,000 LOC | 0 | **0** |
| Largest file | `capability_probe.py` 379 | **`capability_probe.py` 379** |
| `support_bundle.py` LOC | 219 | **85** |
| `diagnostics.py` LOC | 219 | **74** |
| `runtime_explainer.py` LOC | 368 | **370** |
| Upward imports (`support` + `ui`) | 6 modules / 8 lines | **0** |
| `: Any` in scoped packages | 3 | **2** (`segmented_control`, `runtime_module_probe` — P2) |
| Dot-prefixed app storage paths | 0 | **0** (`GLOBAL_STATE_DIRNAME`, `PROJECT_META_DIRNAME` SSOT intact) |

---

## 4. Grep preservation gates

```text
rg 'from app\.(shell|plugins|project|persistence|intelligence|packaging)' app/support app/ui/
  → empty @ 313dbf3

rg 'shell\.theme_tokens|ShellThemeTokens' app/ui/
  → empty @ 313dbf3

find app/core app/bootstrap app/support app/ui app/filesystem -name '*.py' -exec wc -l {} + | awk '$1>=1000'
  → empty @ 313dbf3

rg ': Any' app/support/
  → empty @ 313dbf3
```

**Shell-owned collector wiring (healthy upward direction):**

- `app/shell/support_bundle_collectors.py` — plugin/local-history/settings snapshots
- `app/shell/project_health_checks.py` — project structure/manifest checks
- `app/shell/import_issue_adapter.py` — intelligence → support DTO bridge

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/support/` | **PASS** | diagnostics, preflight, runtime_explainer, child reaper |
| `tests/integration/support/test_support_bundle.py` | **PASS** | 6 tests; collectors injected from shell |
| `tests/integration/plugins/test_support_bundle_plugins_integration.py` | **PASS** | plugin diagnostics via shell collector |
| `tests/unit/shell/test_help_dialog.py` | **PASS** | markdown + HelpThemeTokens smoke (light/dark) |
| `tests/unit/shell/test_clear_console_policy.py` | **PASS** | 3 characterization tests (`674b55c` adjacent) |
| Targeted sweep (above paths) | **PASS** | **43** tests, exit 0 @ `313dbf3` |
| `npx pyright` (support/ui/shell collectors/core contract) | **PASS** | 0 errors, 0 warnings |
| fast shard | **not rerun** | closure scoped to foundation-targeted tests |
| Four-theme manual (help dialog) | **DOCUMENTED GAP** | token-path automated; full HC Light/Dark manual deferred to release QA |

---

## 6. Residual debt (non-blockers for P1 ACCEPT)

1. **CC-CORE-01** — Split `constants.py` by domain (paths/settings/plugins/run) without value drift.
2. **CC-CORE-02 tail** — Unify `DiagnosticItem` / `CapabilityCheckResult` or formalize adapter-only boundary in `core/models.py`.
3. **CC-CORE-05 tail** — Domain-split `runtime_explainer.py` (`startup_issues`, `project_issues`, `import_issues`).
4. **CC-CORE-06** — Move `run_editor` callback registration to entry layer; inject probe runner into facade.
5. **CC-CORE-07 / CC-CORE-09** — Probe check registry + shared `_run_check_list` runner; register treesitter/tooling from owning packages.
6. **CC-CORE-12 … 16** — P2 hygiene (Signal `Any`, `test_runtime_flags` location, `paths.py` style harmonization).

---

## 7. Sign-off

Core Batch Wave 1 **P1 boundary blockers are closed**: `app/support/` and `app/ui/` no longer invert the dependency graph; support bundle orchestration lives in shell workflows with injectable snapshots; help rendering consumes a downward-facing theme protocol. Size and visible-path storage gates pass unchanged. Bootstrap upward seams (CC-CORE-06/07/09) and core constants/diagnostic unification (CC-CORE-01/02/05) remain documented Wave 3–5 backlog.

**Next program item:** Update `PROGRAM_STATUS` for `core-batch-wave-1` ACCEPT; continue remaining P2 parallel closures (pytest/templates).
