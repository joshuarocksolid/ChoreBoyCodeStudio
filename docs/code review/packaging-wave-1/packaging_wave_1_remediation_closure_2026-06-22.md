# Packaging Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Packaging Wave 1 remediation (PKG-R-01 … PKG-R-12)  
**Baseline review:** [packaging_wave_1_thermo_review_2026-06-22.md](packaging_wave_1_thermo_review_2026-06-22.md) @ `6eb9e4fc8885aab4452efc83da10cf28c9f4fe60`  
**Remediation commit:** `a9645c193439404138b96e7496adbfaa9ca0e66c`  
**Verified commit:** `44eae74` (+ this closure doc)  
**Verdict:** **ACCEPT (Packaging Wave 1 P0 + P1 milestones)** — P2 residuals documented below

---

## 1. CC-PKG theme closure matrix

| CC | Priority | PR(s) | Status | Evidence |
|----|----------|-------|--------|----------|
| CC-PKG-01 | P0 | R-01 | **closed** | `PackageValidationReport.is_ready` gates on `issue_report` blocking issues; `test_build_package_validation_report_blocks_when_manifest_vendor_missing`; `test_build_project_package_artifact_refuses_export_when_manifest_vendor_missing` |
| CC-PKG-02 | P1 | R-02 | **closed** | `dependency_audit.py` **363** LOC; extracted `manifest_consistency_audit.py` (95), `subprocess_packaging_rules.py` (155), `vendor_native_validation.py` (80); zero `app/packaging/` files ≥600 |
| CC-PKG-03 | P1 | R-03 | **closed** | `run_dependency_audit` uses `DEFAULT_PACKAGING_PAYLOAD_POLICY.iter_audit_python_files`; no direct `iter_python_files` + manual exclude in audit loop |
| CC-PKG-04 | P1 | R-04 | **closed** | SSOT `validate_packaged_entry_relative_path` in `launcher_bootstrap.py`; `layout.py` + `installer_manifest.py` import it; `test_entry_path_validation.py` alignment test |
| CC-PKG-05 | P1 | R-05 | **closed** | Public `collect_imported_top_levels_from_tree` / `orphan_vendor_native_issues` in `vendor_native_validation.py`; validator imports only public `dependency_audit` API |
| CC-PKG-06 | P1 | R-06 | **closed** | `_PACKAGE_ID_RE` / `_PACKAGE_VERSION_RE` only in `config.py`; `validator.py` trusts parsed `ProjectPackageConfig` for format rules |
| CC-PKG-07 | P1 | R-07 | **closed** | Single AST parse per audited file in `run_dependency_audit`; `imported_top_levels` reused for orphan-native scan; no second full-project parse in validator |
| CC-PKG-08 | P1 | R-08 | **closed** | `prune_rules.py` `PackagingPruneRules` consumed by `payload_policy.py` and `product_builder.py` |
| CC-PKG-09 | P1 | R-09 | **closed** | `_discover_user_excluded_python_that_ships` emits degraded preflight advisory (`package.project.user_excluded_python_will_ship`) |
| CC-PKG-10 | P2 | R-10 | **closed** | `manifest_consistency_audit.py` top-level imports; no function-body imports |
| CC-PKG-11 | P2 | R-11 | **partial** | `tree_sitter_core_binding_name()` SSOT restored in `tree_sitter_cp39.py`; thin `_expected_tree_sitter_binding_name` wrapper remains in `product_builder.py` (test-only seam) |
| CC-PKG-12 | P2 | R-12 | **closed** | `PRUNE_DIR_NAMES` removed; `.pyc` handled via `PackagingPruneRules.prune_file_suffixes` |
| CC-PKG-13 | P2 | — | **deferred** | Broad `except Exception` on artifact write path (`artifact_builder.py:139`) — Wave 5 hygiene |
| CC-PKG-14 | P2 | — | **deferred** | Artifact checksum `rglob("*")` in `installer_manifest.py:245` — acceptable post-staging; optional future file-list feed |

**Project SSOT overlap (acknowledged, not re-litigated):** CC-PROJ-08/09/16/23 closed @ baseline; CC-PROJ-17 manifest wiring gap **closed** via CC-PKG-01 export gate.

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff (2026-06-22 @ `6eb9e4f`) | Closure @ `44eae74` |
|--------|----------------------------------|---------------------|
| `dependency_audit.py` LOC | **647** (≥700 smell) | **363** |
| Largest `app/packaging/` module | `dependency_audit.py` 647 | `product_builder.py` **474** |
| `app/packaging/` files ≥700 LOC | 0 | **0** |
| `app/packaging/` files ≥600 LOC | 1 (smell) | **0** |
| Bare `: Any` in `app/packaging/` | 0 | **0** |
| JSON boundary `dict[str, Any]` | 13 | **13** (serialization only) |
| Total `app/packaging/` LOC | 3,251 | **3,317** (+66 net; split modules) |

---

## 3. Grep preservation gates

```text
rg '_collect_imported_top_levels|_orphan_vendor_native_issues' app/packaging/     → empty
rg '_PACKAGE_ID_RE|_PACKAGE_VERSION_RE' app/packaging/validator.py               → empty
rg 'PRUNE_DIR_NAMES' app/packaging/                                              → empty
rg 'from app\.packaging\.dependency_audit import _' app/packaging/               → empty
find app/packaging -name '*.py' -exec wc -l {} + | awk '$1>=700'                   → empty
find app/packaging -name '*.py' -exec wc -l {} + | awk '$1>=600'                   → empty
```

---

## 4. Architecture gate scorecard (packaging-specific)

| Gate | Kickoff | Closure |
|------|---------|---------|
| AD-019 shared installable writer | Pass | **Pass** |
| Installable-only profile hard cutover | Pass | **Pass** |
| Project payload inventory-backed copy | Pass | **Pass** |
| Explicit copy vs audit policy object | Pass | **Pass** |
| Audit uses policy iterator | Fail (CC-PKG-03) | **Pass** |
| Export gate = full blocking issue set | Fail (CC-PKG-01) | **Pass** |
| cp39 tree-sitter product contract | Pass | **Pass** |
| No dot-prefixed storage paths in packaging | Pass | **Pass** |
| Python 3.9 syntax compliance | Pass | **Pass** |
| Private cross-module imports | Fail (CC-PKG-05) | **Pass** |

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/packaging/` | **PASS** | 79 selected @ remediation commit; all green @ `44eae74` |
| `test_validator.py` manifest export gate | **PASS** | `is_ready is False` + artifact refusal when manifest vendor missing |
| `test_entry_path_validation.py` | **PASS** | layout + launcher_bootstrap entry-path SSOT |
| `test_dependency_manifest_audit.py` | **PASS** | manifest consistency audit module |
| `npx pyright app/packaging/` | **PASS** | 0 errors, 0 warnings |

---

## 6. Residual debt (non-blockers for P1 ACCEPT)

1. **CC-PKG-13** — Narrow `except Exception` on `artifact_builder.write_project_package_artifact` write path.
2. **CC-PKG-14** — Optional checksum builder fed from written artifact file list instead of post-staging `rglob`.
3. **CC-PKG-11 tail** — Delete `_expected_tree_sitter_binding_name` wrapper; tests call `tree_sitter_core_binding_name` directly.

---

## 7. Sign-off

Packaging Wave 1 **P0 + P1 remediation milestones are met**: export refuses blocking manifest/vendor drift, audit file-set routes through `PackagingPayloadPolicy.iter_audit_python_files`, `dependency_audit.py` split below 600 LOC, validation seams deduplicated, and prune/user-exclude policy SSOT landed. Residual P2 hygiene (CC-PKG-11 tail, CC-PKG-13, CC-PKG-14) is documented for Wave 5.

**Next program item:** Update `PROGRAM_STATUS` for packaging-wave-1 ACCEPT; route P2 tail to hygiene backlog.
