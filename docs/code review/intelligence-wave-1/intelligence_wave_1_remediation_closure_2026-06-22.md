# Intelligence Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Intelligence Wave 1 remediation (INT-R-01 … INT-R-13)  
**Baseline review:** [intelligence_wave_1_thermo_review_2026-06-16.md](intelligence_wave_1_thermo_review_2026-06-16.md)  
**Verified commit:** `1134412` (+ session 15 local: outline AD-018 gate tests, this closure doc)  
**Verdict:** **ACCEPT (Intelligence Wave 1 P1 milestones)** — Wave 4/5 residuals documented below

---

## 1. CC theme closure matrix (Waves 0–3)

| CC | Priority | PR(s) | Status | Evidence |
|----|----------|-------|--------|----------|
| CC-01 | P0 | R-03 | **closed** | Worker-only broker; `rg complete_fast app/shell/` empty |
| CC-02 | P0 | R-07 | **closed** | Tiered merge via `completion_merge_policy.py`; contract tests |
| CC-03 | P0 | R-08 | **closed** | Revision-safe cache reuse in broker |
| CC-04 | P0 | R-04 | **closed** | Async menu hover/signature; no `resolve_*_blocking` in `app/` |
| CC-05 | P0 | R-05 | **closed** | `build_completion_context` SSOT in editors |
| CC-06 | P0 | R-11, R-12 | **closed** | Nav monolith split: coordinator **130** LOC (was 1,103); zero `app/` files ≥1000 |
| CC-07 | P0 | R-03 | **closed** | Completion acceptance via workflow/controller worker lane |
| CC-08 | P1 | R-09, R-13 | **partial** | `semantic_session.py` **473** LOC (target ~320); composition extracted |
| CC-09 | P1 | R-06 | **closed** | Per-file nav worker keys + concurrent callback test |
| CC-10 | P1 | R-13 | **closed** | `rg '^from app\.intelligence' app/shell/semantic_*` empty; `intelligence_types.py` types-only seam |
| CC-13 | P1 | R-13 | **closed** | Outline parse off UI thread in `editor_tab_outline_workflow.py`; AD-018 gate |
| CC-14 | P1 | R-13 (shell) | **partial** | Import analysis routed via `LintWorkflow.run_import_analysis`; menu `menu_wiring.py:116`; diagnostics fork deferred INT-R-18 |
| CC-18 | P1 | R-01, R-10, R-13 | **closed** | `deliver_revision_gated_editor_result` on completion, resolve, inline, outline, lint paths |
| CC-11 | P1 | R-15 | **deferred** | Wave 4 — symbol index worker (Project SSOT / Intelligence Wave 4) |
| CC-12 | P1 | R-16 | **deferred** | Wave 4 — `python_structure.py` SSOT |
| CC-15 | P1 | R-14 | **deferred** | Wave 4 — inventory snapshot orchestration (Project SSOT P1-3) |
| CC-16 | P1 | R-17 | **deferred** | Wave 4 — Jedi engine split |
| CC-17 | P1 | R-18 | **deferred** | Wave 5 — refactor buffer≠disk fail-closed |
| CC-19 … CC-23 | P2 | R-02, R-18+ | **deferred** | P2 backlog per implementation plan |

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff (2026-06-16) | Closure |
|--------|----------------------|---------|
| `semantic_navigation_workflow.py` LOC | 1,103 | **130** |
| `app/` files ≥1000 LOC | 1 | **0** |
| `app.intelligence` imports in `app/shell/semantic_*` | 7+ | **0** |
| `complete_fast` in `app/shell/` | present | **0** |
| `resolve_*_blocking` in `app/` | present | **0** |
| `semantic_session.py` LOC | ~620 | **473** |
| MainWindow methods | 45 (cross-wave) | **28** |
| `window: Any` in `app/shell/` | 73 (sample) | **66** |

---

## 3. Grep preservation gates

```text
rg '^from app\.intelligence' app/shell/semantic_*     → empty
rg 'complete_fast' app/shell/                           → empty
rg 'resolve_.*_blocking|complete_blocking' app/         → empty
rg 'build_completion_context' app/editors/              → SSOT (editors own prefix)
rg 'hover_provider' app/                                → empty
find app -name '*.py' -exec wc -l {} + | awk '$1>=1000' → empty
```

---

## 4. Verification results

| Gate | Result | Notes |
|------|--------|-------|
| `test_editor_tab_outline_workflow.py` (new) | **PASS** | INT-R-13 CC-13/18 outline stale gate |
| `test_editor_completion_workflow.py` | **PASS** | INT-R-10 generation stale gate |
| `test_semantic_navigation_workflow.py` | **PASS** | INT-R-04/10 hover stale gate |
| `test_main_window_lint_probe_policy.py` | **PASS** | CC-14 shell lint stale + probe policy |
| fast shard | **PASS** | exit 0 @ session 15 |
| pyright | **PASS** | 0 errors |
| Four-theme manual | **DOCUMENTED GAP** | Outline/lint/import-analysis UI paths not manually verified in HC modes |

---

## 5. Residual debt (non-blockers for P1 ACCEPT)

1. **`semantic_session.py` 473 LOC** — CC-08 session shrink partial; target ~320 after further extraction (INT-R-09 tail).
2. **`editor_completion_workflow.py`** — still imports `build_completion_context` / `CompletionRequest` from intelligence (outside `semantic_*` grep gate; controller factory port optional P2).
3. **Coordinator 130 vs 120 LOC target** — INT-R-12 proof margin; functionally thin delegate pattern met.
4. **CC-14 intelligence lane** — PY200 Pyflakes fork, probe mock test, diagnostics decomposition → INT-R-18 (Wave 5).
5. **Wave 4 tracks CC-11…CC-17** — coordinate with Project SSOT Wave 1 (P1-3) at inventory orchestration seam.

---

## 6. Sign-off

Intelligence Wave 1 **P1 remediation milestones are met**: P0 blockers CC-01…CC-07 closed, navigation monolith eliminated, zero intelligence imports in `semantic_*` shell modules, async outline/lint/import paths with AD-018 gates, worker-serialized completion/nav lanes. Wave 4/5 and CC-08 session shrink remain documented for cross-program tracks.

**Next program item:** P1-3 Project SSOT Wave 1 — formalize P0 closure, verify CC-PROJ-01…09 @ HEAD, begin PROJ-R-01…
