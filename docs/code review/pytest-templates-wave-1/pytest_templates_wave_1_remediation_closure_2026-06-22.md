# Pytest / Templates / Examples Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Pytest / Templates / Examples Wave 1 (`TN-PYTMPL-INTEG`)  
**Baseline review:** [pytest_templates_wave_1_thermo_review_2026-06-22.md](pytest_templates_wave_1_thermo_review_2026-06-22.md) @ `c4aed0a48dabd0663c2a666711dee85614f7fb7d`  
**Remediation commits:** `ce5d221`, `508d207`, `edccb8d` (sessions 21–22; also `57aac8d` CC-05 outcome parser tests in ancestry)  
**Verified commit:** `313dbf3d36b12a01ca431f814aafd8c38a801566` (+ this closure doc)  
**Verdict:** **ACCEPT (Pytest / Templates / Examples Wave 1 P1 milestones)**

---

## 1. CC-PYTMPL theme closure matrix

Kickoff verdict was **REJECT** (pytest P1 seams). All four P1 themes from the thermo review are **closed or partial-closed** @ verified commit; templates/examples kickoff **ACCEPT** stands.

| CC | Priority | Package | Status @ `313dbf3` | Remediation | Evidence |
|----|----------|---------|-------------------|-------------|----------|
| CC-PYTEST-01 | P1 | pytest | **closed** | `ce5d221` | `build_pytest_subprocess_env()` in `launch_plan.py:220-224`; discovery (`discovery_service.py:85`) and runner (`runner_service.py:116`) both pass `env=build_pytest_subprocess_env()`; `test_discover_tests_uses_offscreen_qt_platform`, `test_run_pytest_project_invokes_subprocess_and_parses_failures` assert `QT_QPA_PLATFORM=offscreen` |
| CC-PYTEST-02 | P1 | pytest | **partial closed** | `ce5d221` | Collect parser handles nested classes + parametrized node IDs; AST-backed function line numbers via `_apply_line_numbers`; `-rA` summary handles parametrized IDs. **Residual:** stdout/text remains discovery SSOT (no structured `--json` collect path); acceptable @ Wave 1 with 6 new parser tests |
| CC-PYTEST-03 | P1 | pytest | **closed** | `ce5d221` | `runner_service.py` imports `build_pytest_launch_plan` from `launch_plan` only — no façade redefinition; grep gate (`test_run_wave_grep_gates.py`) still passes (24/24) |
| CC-TMPL-01 | P1 | templates | **closed** | `508d207` | `default_entry` on `TemplateMetadata`; `_load_template_metadata` reads optional field (default `main.py`); all three `templates/*/template.json` updated; `test_materialize_template_reads_default_entry_from_template_json` |
| CC-PYTEST-04 | P2 | pytest | **closed** | `ce5d221` | Dead `_select_pytest_runtime` removed from runner; canonical impl remains in `launch_plan.py:119-130` |
| CC-PYTEST-05 | P2 | pytest | **deferred** | — | Inline `import ast` in `identify_test_at_cursor` (`runner_service.py:61`); `import subprocess` in `_runtime_supports_pytest` (`launch_plan.py:168`) |
| CC-PYTEST-06 | P2 | pytest | **deferred** | — | Broad `except Exception` on manifest load in launch plan |
| CC-PYTEST-07 | P2 | pytest | **deferred** | — | Cursor identification returns bare name; shell resolves node_id |
| CC-TMPL-02 | P2 | templates | **deferred** | — | Minimal `template.json` schema; no README validation at load |
| CC-EXAMPLE-01 | P2 | examples | **deferred** | — | Magic `SHOWCASE_TEMPLATE_ID` string coupling |
| CC-EXAMPLE-02 | P2 | examples | **deferred** | — | Empty package `__init__.py` |

**Cross-wave typing (Run W1 CC-24):** `edccb8d` lands typed `TestOutcome` end-to-end — `outcome_types.py` exports `SUMMARY_OUTCOME_PREFIXES` / `VERBOSE_OUTCOME_SUFFIXES`; discovery outcomes typed; explorer icons/panel consume `TestOutcome` without cast; `test_parse_test_results_outcomes_are_test_outcome_literals`, `test_discovered_test_result_outcome_field_is_test_outcome`.

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff @ `c4aed0a` | Closure @ `313dbf3` |
|--------|---------------------|---------------------|
| Python files (`pytest` + `templates` + `examples`) | 8 | **8** |
| Total LOC (scoped packages) | **862** | **985** (+123; discovery hardening + outcome vocab + template metadata) |
| Largest file | `discovery_service.py` / `launch_plan.py` — **217** | `discovery_service.py` — **307** |
| Files ≥700 LOC | **0** | **0** |
| Files ≥1000 LOC | **0** | **0** |
| Explicit `: Any` (`rg ': Any\b'`) | **0** | **0** |
| `dict[str, Any]` JSON boundary | **2** (templates) | **2** (unchanged) |

**Per-file LOC (sorted):**

| File | Kickoff | Closure |
|------|--------:|--------:|
| `app/examples/__init__.py` | 0 | 0 |
| `app/templates/__init__.py` | 5 | 5 |
| `app/pytest/outcome_types.py` | 8 | **22** |
| `app/examples/example_project_service.py` | 40 | 40 |
| `app/pytest/__init__.py` | 54 | 54 |
| `app/pytest/runner_service.py` | 182 | **175** |
| `app/templates/template_service.py` | 139 | **158** |
| `app/pytest/launch_plan.py` | 217 | **224** |
| `app/pytest/discovery_service.py` | 217 | **307** |

---

## 3. Architecture gate scorecard

| Gate | Kickoff | Closure @ `313dbf3` |
|------|---------|---------------------|
| 1k-line rule | Pass | **Pass** |
| 700 LOC smell | Pass | **Pass** (watch: `discovery_service.py` 307) |
| Python 3.9 | Pass | **Pass** |
| No dot-prefixed storage paths | Pass | **Pass** |
| Hard cutover — no `app/run/pytest_*` | Pass | **Pass** (grep gates 24/24) |
| Shared launch plan SSOT | Partial (CC-PYTEST-03) | **Pass** |
| Subprocess env parity (discovery ↔ runner) | Fail (CC-PYTEST-01) | **Pass** |
| Template manifest entry SSOT | Partial (CC-TMPL-01) | **Pass** |
| Examples delegate pattern (Help-only) | Pass | **Pass** (unchanged) |
| Typed TestOutcome vocabulary | — | **Pass** (`edccb8d`) |

---

## 4. Grep preservation gates

Automated in `tests/unit/run/test_run_wave_grep_gates.py` — **24 tests PASS** @ closure.

```text
rg 'app/run/pytest_' app/ tests/                    → empty (no legacy pytest under app/run)
rg 'build_pytest_launch_plan' app/pytest/runner_service.py  → import + call only (no def)
find app/pytest app/templates app/examples -name '*.py' -exec wc -l {} + | awk '$1>=700'  → empty
```

---

## 5. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `tests/unit/run/test_pytest_discovery_service.py` | **PASS** | 20 selected |
| `tests/unit/run/test_pytest_runner_service.py` | **PASS** | 16 selected |
| `tests/unit/templates/test_template_service.py` | **PASS** | 5 selected |
| Combined scoped sweep | **PASS** | **41/41** @ `313dbf3` |
| `tests/unit/run/test_run_wave_grep_gates.py` | **PASS** | 24/24 |
| `npx pyright app/pytest/ app/templates/ app/examples/` | **PASS** | 0 errors, 0 warnings |
| fast shard | **not rerun** | Targeted sweep only (closure scope) |
| Four-theme manual | **N/A** | No user-facing UI markup changes in remediation commits (explorer typing is internal) |

**New / extended tests since baseline:**

| Test | Commit | CC |
|------|--------|-----|
| `test_parse_collect_output_handles_nested_classes_and_parametrized_tests` | `ce5d221` | CC-PYTEST-02 |
| `test_parse_collect_output_populates_function_line_numbers` | `ce5d221` | CC-PYTEST-02 |
| `test_parse_test_results_handles_parametrized_node_ids_in_summary_output` | `ce5d221` | CC-PYTEST-02 |
| `test_discover_tests_uses_offscreen_qt_platform` | `ce5d221` | CC-PYTEST-01 |
| `test_materialize_template_reads_default_entry_from_template_json` | `508d207` | CC-TMPL-01 |
| `test_parse_test_results_outcomes_are_test_outcome_literals` | `edccb8d` | CC-24 cross-ref |
| `test_discovered_test_result_outcome_field_is_test_outcome` | `edccb8d` | CC-24 cross-ref |

---

## 6. Sub-package verdicts (re-accept)

| Sub-package | Kickoff | Closure @ `313dbf3` |
|-------------|---------|---------------------|
| `app/pytest/` | **REJECT** | **ACCEPT** — P1 env SSOT + launch-plan import cutover closed; parser hardening + typed outcomes; CC-PYTEST-02 structured-collect tail deferred |
| `app/templates/` | **ACCEPT** | **ACCEPT** — CC-TMPL-01 closed; P2 schema polish deferred |
| `app/examples/` | **ACCEPT** | **ACCEPT** — unchanged; P2 magic-string deferred |
| **Overall** | **REJECT** | **ACCEPT** |

---

## 7. Residual debt (non-blockers for Wave 1 ACCEPT)

1. **CC-PYTEST-02 tail** — Optional structured collection (`pytest --collect-only` JSON/report plugin) if stdout edge cases surface in production Test Explorer workflows.
2. **CC-PYTEST-05 … CC-PYTEST-07** — Inline imports, manifest error narrowing, cursor node_id qualification (Wave 2 hygiene).
3. **CC-TMPL-02** — Extend `template.json` validation (`source_roots`, README presence) when New Project schema grows.
4. **CC-EXAMPLE-01/02** — Showcase ID fail-fast and package re-exports (optional).
5. **`discovery_service.py` growth** — 307 LOC; split collect parser to sibling module if it crosses 400 LOC on next feature.

---

## 8. Sign-off

Pytest / Templates / Examples Wave 1 **P1 remediation milestones are met** @ `313dbf3`: subprocess environment SSOT unifies discovery and runner; launch-plan import cutover removes façade drift; collect/run parsers hardened for nested classes, parametrized nodes, and AST line numbers; template manifests own `default_entry`; typed `TestOutcome` flows through discovery and shell consumers. Thermo kickoff **REJECT** is lifted to **ACCEPT**.

**Next program item:** Update `PROGRAM_STATUS` for `pytest-templates-wave-1` ACCEPT; route CC-PYTEST-02 structured-collect tail and P2 themes to hygiene backlog.
