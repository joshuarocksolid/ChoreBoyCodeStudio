# TN-PROJ-DIAG — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-DIAG  
**Date:** 2026-06-16  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/intelligence/diagnostics_service.py` (510 LOC), `app/intelligence/import_diagnostics.py` (162 LOC), `app/intelligence/import_resolver.py` (75 LOC), `app/intelligence/runtime_import_probe.py` (84 LOC), `app/intelligence/code_actions.py` (394 LOC), `app/shell/lint_workflow.py` (357 LOC), `app/shell/python_style_workflow.py` (351 LOC). Cross-read: `app/project/dependency_classifier.py`, `app/project/import_layout.py`, `app/support/runtime_explainer.py`. Tests: `tests/unit/intelligence/test_diagnostics_service.py`, `test_diagnostics_py200_pyflakes.py`, `test_import_diagnostics_probe.py`, `test_import_resolver.py`, `test_runtime_import_probe.py`, `test_code_actions.py`, `tests/unit/shell/test_main_window_lint_probe_policy.py`.

---

## Executive verdict

**Not thermo-clean for R5 convergence.** Intelligence Wave 1 remediation moved PY200 collection onto `dependency_classifier.is_module_resolvable`, extracted shared models and Pyflakes, and fixed the Pyflakes-vs-default fork for unresolved imports — real progress. The Project SSOT gates are still open: `explain_unresolved_import` maintains a **second parallel classification tree** instead of adapting `classify_module` results; the project-layer classifier **depends upward** on `app/intelligence.import_resolver` and `runtime_import_probe`; manual lint and full-project import analysis still thread `allow_runtime_import_probe=True` into the per-node resolution hot path; and quick-fix/source-root behavior is **split across intelligence planning and shell application** with message-string parsing as the only contract. Dominant risk: packaging audit, lint PY200, explain UI, and quick fixes can disagree on the same import because four layers each own a slice of the decision — the SSOT modules exist but diagnostics has not finished the cutover.

---

### TN-PROJ-DIAG-1 — Manual lint still enables AppRun subprocess probes on the per-import hot path

- **Persona:** TN-PROJ-DIAG
- **Severity:** BLOCKER
- **Evidence:** `app/shell/lint_workflow.py:127-138` — `allow_runtime_import_probe = trigger == "manual"` passed into `analyze_python_with_workflow`. `app/intelligence/import_diagnostics.py:41-47,82-87` — each unresolved candidate calls `is_module_resolvable(..., allow_runtime_import_probe=...)`. `app/project/dependency_classifier.py:244-245` — probe invokes `is_runtime_module_importable(top_level)`. `app/intelligence/runtime_import_probe.py:63-68` — `subprocess.run([runtime_path, "-c", probe_script], timeout=5)`. `tests/unit/shell/test_main_window_lint_probe_policy.py:58-73` — asserts manual lint passes `True`; `tests/unit/intelligence/test_import_diagnostics_probe.py` only guards the **default** (`False`) path.
- **Code-judo alternative:** Delete probe from lint resolution entirely. Lint and realtime paths always use static filesystem + `known_runtime_modules` / stdlib fallback. Reserve `probe_runtime_module_importability` for `explain_unresolved_import`, `run_import_analysis`, and explicit audit actions only — split `is_module_resolvable` into static (lint) and probe-enriched (explain) entry points so the flag cannot leak into hot paths.
- **Suggested remediation:** Hard cutover: `lint_workflow` always passes `allow_runtime_import_probe=False`; extend probe-policy tests to assert manual trigger also disables subprocess on PY200 collection; keep probe only on `run_import_analysis` / explainer APIs.
- **Tests that would prove fix:** Parametrized test: manual lint with monkeypatched `subprocess.run` that raises on call; `run_import_analysis` path still probes when explicitly requested.
- **Handoff overlap:** R5, CC-14, architecture gate 9

---

### TN-PROJ-DIAG-2 — `explain_unresolved_import` is a parallel classifier, not an adapter over `classify_module`

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:227-348` — bespoke decision tree (`missing_source_root` → `project_module_missing` → `compiled_extension_unknown` → `runtime_module_unavailable` → `vendored_dependency_missing`) built from layout probes and heuristics. `app/project/dependency_classifier.py:123-209` — `classify_module` already emits `stdlib | first_party | vendored | vendored_native | runtime | missing` with shared primitives. Explain never calls `classify_module`. Architecture gate 9: *"`explain_unresolved_import` should adapt classifier/layout results, not grow a second classifier."*
- **Code-judo alternative:** `explain_unresolved_import(module) = map_category_to_explanation(classify_module(...))` plus layout-only `suggest_missing_source_root` pre-check (or fold source-root detection into classifier as a first-class category). Delete `_looks_like_runtime_specific_module` heuristic; derive runtime-unavailable copy from probe result + `CATEGORY_RUNTIME` / `CATEGORY_MISSING` mismatch.
- **Suggested remediation:** New `app/project/import_explanation.py` (or extend `dependency_classifier`) owns category → `ImportExplanation` templates; `diagnostics_service.explain_unresolved_import` becomes a thin formatter.
- **Tests that would prove fix:** Parity matrix: representative imports classified by `classify_module` produce explain `kind` values that match documented mapping; existing `test_explain_unresolved_import_*` green against adapter.
- **Handoff overlap:** R5, CC-14, architecture gate 7/9

---

### TN-PROJ-DIAG-3 — Explain path imports private layout helper despite public API existing

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:245-247` — inline `from app.project.import_layout import _module_path_prefix_exists_at_base` and call on `vendor_root`. `app/project/import_layout.py:267-279` — public `module_path_prefix_exists_at_base` exists; `_module_path_prefix_exists_at_base` is a one-line alias. Only production importer of the private symbol outside `import_layout.py` is `diagnostics_service`.
- **Code-judo alternative:** Use `module_path_prefix_exists_at_base(vendor_root, module_name)` or delete the need entirely once explain routes through `classify_module` (vendor hits come from classifier resolution).
- **Suggested remediation:** Replace private import in same PR as TN-PROJ-DIAG-2; add grep CI guard: no `_module_path_prefix_exists_at_base` imports outside `import_layout.py`.
- **Tests that would prove fix:** Existing explain tests unchanged; `rg '_module_path_prefix_exists_at_base' app --type py` → only `import_layout.py`.
- **Handoff overlap:** R5, CC-22

---

### TN-PROJ-DIAG-4 — Layer inversion: project SSOT classifier depends on intelligence probe and resolver

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:33-34` — `from app.intelligence.import_resolver import resolve_project_import` and `from app.intelligence.runtime_import_probe import is_runtime_module_importable`. Module docstring `:22-24` documents resolver as re-exported from intelligence. Architecture gate 10: *"Dependency direction should be `intelligence -> project`, not `project -> intelligence`."*
- **Code-judo alternative:** Move `resolve_project_import` filesystem probe into `app/project/import_layout.py` (alongside `resolve_import_at_base`) or a new `app/project/import_resolution.py`. Move `runtime_import_probe` to `app/project/` or `app/bootstrap/` (probe is runtime/platform concern). Classifier imports only project-layer modules; intelligence diagnostics import classifier.
- **Suggested remediation:** Hard cutover: relocate resolver + probe, update `dependency_classifier` imports, delete `app/intelligence/import_resolver.py` or reduce to a deprecated re-export shim removed in same wave.
- **Tests that would prove fix:** `rg 'from app\.intelligence\.(import_resolver|runtime_import_probe)' app/project --type py` → empty; `test_dependency_classifier.py` and import diagnostics tests green.
- **Handoff overlap:** R5, architecture gate 10

---

### TN-PROJ-DIAG-5 — `import_resolver` duplicates project filesystem resolution outside classifier ownership

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/import_resolver.py:39-51` — iterates `layout.import_search_bases`, calls `resolve_import_at_base`, optionally probes runtime. `app/project/dependency_classifier.py:159-166,234-241` — same loop via `resolve_project_import` with probe flag variations. `completion_providers.py` still imports `resolve_module_binding` from intelligence resolver. Two resolution stacks for the same invariant.
- **Code-judo alternative:** One canonical `project.import_layout.resolve_module(project_root, module_name, layout)` used by classifier, completion, and diagnostics. Delete intelligence resolver module after importers cut over.
- **Suggested remediation:** Extract shared resolution to project layer; wire `classify_module`, `is_module_resolvable`, and completion through it.
- **Tests that would prove fix:** `test_import_resolver.py` behaviors covered by project-layer tests; grep shows no `app.intelligence.import_resolver` production imports.
- **Handoff overlap:** R5, CC-15

---

### TN-PROJ-DIAG-6 — `classify_module` vs `is_module_resolvable` semantic fork is undocumented at explain/quick-fix boundary

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/project/dependency_classifier.py:152-157` — `classify_module` treats `STDLIB_TOP_LEVELS` as stdlib when no inventory. `:229-232` — `is_module_resolvable` uses `known_runtime_modules if provided else STDLIB_TOP_LEVELS` but docstring `:223-227` states diagnostics is **stricter** when inventory provided (stdlib bypass). `classify_module` passes `known_runtime_modules=frozenset()` into `resolve_project_import` (`:162`) even when caller supplied inventory. Packaging audit uses `classify_module`; lint uses `is_module_resolvable` — same import can be `stdlib` in audit and PY200 in editor when runtime inventory omits a stdlib name. Architecture gate 8.
- **Code-judo alternative:** Single resolution function with explicit `ResolutionPolicy.LINT | PACKAGING | EXPLAIN` enum, or unify semantics and document the one intentional difference (if any) in product terms. Explain and quick-fix should consume the same policy as lint for PY200.
- **Suggested remediation:** Add cross-consumer parity tests (manifest gap table); align `classify_module` stdlib handling with lint policy or expose explicit `category` on PY200 diagnostics.
- **Tests that would prove fix:** Parametrized parity: `tomllib` / slim-runtime cases — audit category vs lint PY200 vs explain kind agree or test documents explicit divergence.
- **Handoff overlap:** R5, architecture gate 8

---

### TN-PROJ-DIAG-7 — `ImportDiagnostic` strips `CodeDiagnostic`; shell re-builds rich model on import analysis

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_models.py:10-16` — `ImportDiagnostic` (file, line, message only). `app/intelligence/diagnostics_service.py:207-213` — `_diagnostics_for_file` drops code, severity, columns converting `CodeDiagnostic` → `ImportDiagnostic`. `app/shell/lint_workflow.py:241-250` — `run_import_analysis` maps back to `CodeDiagnostic`, re-derives severity via `resolve_lint_rule_settings("PY200", ...)`. `app/support/runtime_explainer.py:72-73` — parses module name from message string again.
- **Code-judo alternative:** Deprecate `ImportDiagnostic`; `find_unresolved_imports` returns `list[CodeDiagnostic]` filtered to `code=="PY200"`. Shell and explainer consume one model; optional `detail: Mapping[str, str]` carries `unresolved_module` without message parsing.
- **Suggested remediation:** Hard cutover bundled plugins + `runtime_explainer`; keep thin compatibility wrapper if external API requires old shape.
- **Tests that would prove fix:** `test_find_unresolved_imports_*` assert code/severity/columns; lint_workflow import analysis stops manual severity reconstruction.
- **Handoff overlap:** R5, CC-14

---

### TN-PROJ-DIAG-8 — Quick-fix `add_source_root` split-brain: planned in intelligence, applied in shell

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/code_actions.py:247-256` — emits `QuickFix(action_kind="add_source_root", ...)`. `:101-113` — `apply_quick_fixes` handles only `remove_line`, `replace_import_module`, `create_module_file`; no `add_source_root`. `app/shell/python_style_workflow.py:237-240,262-289` — shell filters source-root fixes and applies via `_apply_source_root_fixes` (manifest mutation via `append_project_source_root`). No test in `test_code_actions.py` covers source-root planning or end-to-end apply.
- **Code-judo alternative:** Either implement `add_source_root` inside `apply_quick_fixes` with injected manifest writer dependency, or stop emitting from `code_actions` and let shell plan source-root fixes exclusively — not both. Prefer project-service callable from intelligence apply path.
- **Suggested remediation:** Unify apply ownership; add `test_plan_safe_fixes_for_file` + shell integration test for source-root fix without string parsing.
- **Tests that would prove fix:** Unit test: PY200 under `src/` layout plans `add_source_root`; apply path (intelligence or shell, pick one) updates manifest; grep shows single owner for manifest mutation.
- **Handoff overlap:** R5, shell-wave-1-followup, manifest test gap (High)

---

### TN-PROJ-DIAG-9 — PY200 quick-fix and explainer rely on fragile message-string contract

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/import_diagnostics.py:56,76,97` — `message=f"Unresolved import: {name}"`. `app/intelligence/code_actions.py:280-287` — `_extract_unresolved_module_name` parses `"Unresolved import:"` prefix. `app/support/runtime_explainer.py:73` — `diagnostic.message.removeprefix("Unresolved import: ")`. Typo or localization in message breaks quick-fix planning and runtime reports independently.
- **Code-judo alternative:** Add optional `detail: dict[str, str]` on `CodeDiagnostic` (e.g. `{"module": "foo.bar"}`) set at diagnostic emission; planners read `detail["module"]`, delete string parsers.
- **Suggested remediation:** Extend `CodeDiagnostic` in `diagnostics_models.py`; set detail in `collect_unresolved_import_diagnostics`; migrate parsers in one cutover PR.
- **Tests that would prove fix:** Quick-fix test uses diagnostic with alternate message text but same `detail`; still plans correct fix.
- **Handoff overlap:** R5, CC-14

---

### TN-PROJ-DIAG-10 — `diagnostics_service.py` remains a god module: orchestration + explain tree + four AST walkers

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py` — 510 LOC. `:100-171` orchestrates syntax, provider fork, PY200, profile filter. `:360-477` — four private AST rule functions (`_duplicate_definition_diagnostics`, `_unused_import_diagnostics`, `_duplicate_import_diagnostics`, `_unreachable_statement_diagnostics`). `:227-348` — full explain taxonomy. Models and Pyflakes were extracted (`diagnostics_models.py`, `pyflakes_adapter.py`) but walkers and explain remain co-located. Intelligence CC-14 partial decomposition.
- **Code-judo alternative:** Finish TN-INT-05 split: `builtin_lint_rules.py` (visitors), `import_explanations.py` (adapter over classifier), thin `diagnostics_service.py` facade. Target no file >250 LOC in diagnostics lane.
- **Suggested remediation:** Block new diagnostic rules in god module until decomposition lands; move explain in same PR as TN-PROJ-DIAG-2.
- **Tests that would prove fix:** Existing `test_diagnostics_service.py` green with import path updates only.
- **Handoff overlap:** R5, CC-14, CC-15

---

### TN-PROJ-DIAG-11 — Multiple full-tree `ast.walk` passes per lint (built-in + imports)

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:148-151` — four built-in walkers each scanning tree (`_unused_import_diagnostics` `:388` — `ast.walk`; `_unreachable_statement_diagnostics` `:458` — second full walk). `app/intelligence/import_diagnostics.py:38` — third full `ast.walk` for PY200. Default-provider lint on large files = O(n) × 3+ traversals before profile merge.
- **Code-judo alternative:** Single `DiagnosticVisitor(ast.NodeVisitor)` or shared import collector invoked once; built-in rules register on same pass. Orchestrator: parse once → visit once → merge streams.
- **Suggested remediation:** Introduce visitor during god-module split (TN-PROJ-DIAG-10); no behavior change required beyond ordering tests.
- **Tests that would prove fix:** Existing diagnostic count/ordering tests unchanged.
- **Handoff overlap:** CC-14

---

### TN-PROJ-DIAG-12 — `find_unresolved_imports` performs independent inventory walk (snapshot orchestration gap)

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:78-82` — accepts `inventory_snapshot` but defaults to `build_project_inventory_snapshot(root)` when None. `run_import_analysis` (`lint_workflow.py:221-228`) does not pass snapshot. Manifest notes three independent snapshot builders including diagnostics. Architecture gates 5–6: one walk per project generation.
- **Code-judo alternative:** Shell/intelligence cache workflow owns one `ProjectInventorySnapshot` per generation; `find_unresolved_imports` requires snapshot or receives it from orchestrator — no silent full walk fallback in production paths.
- **Suggested remediation:** Thread shared snapshot from `intelligence_cache_workflow` (TN-PROJ-CONSUMERS); delete inline `build_project_inventory_snapshot` default after cutover.
- **Tests that would prove fix:** Orchestration test: one `iter_python_files` invocation per refresh generation across symbol index + diagnostics + completion.
- **Handoff overlap:** R4, CC-15, architecture gates 5–6

---

### TN-PROJ-DIAG-13 — Full-project import analysis probes every unresolved top-level import

- **Persona:** TN-PROJ-DIAG
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/lint_workflow.py:221-225,254-258` — `find_unresolved_imports(..., allow_runtime_import_probe=True)` then `build_import_issue_report(..., allow_runtime_import_probe=True)`. Walks all Python files (`diagnostics_service.py:83-96`), and for each PY200 candidate calls probe-eligible resolution. `@lru_cache(maxsize=1024)` on probe (`runtime_import_probe.py:56`) limits repeat cost but first analysis of N distinct top-level imports can still spawn up to N AppRun subprocesses (5s timeout each).
- **Code-judo alternative:** Import analysis: static classify first; batch probe only for modules still `missing` after static pass, or probe once per unique top-level in a dedicated audit phase with progress UI — not inline inside per-node lint collection.
- **Suggested remediation:** Separate "Analyze imports" into static scan + optional explicit "Probe runtime" step; never pass probe flag into `collect_unresolved_import_diagnostics` loop.
- **Tests that would prove fix:** Integration test: project with 20 unresolved imports triggers ≤1 probe batch or bounded subprocess count; explainer still enriches when probe enabled at report build time only.
- **Handoff overlap:** R5, AD-016

---

### TN-PROJ-DIAG-14 — Duplicated AST offset and severity helpers between diagnostics modules

- **Persona:** TN-PROJ-DIAG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/diagnostics_service.py:217-224,499-504` — `_col_offset`, `_end_col_offset`, `_severity_from_profile_value`. `app/intelligence/import_diagnostics.py:145-162` — duplicate trio (`_severity_from_profile_value` uses inline lint_profile import). Models were extracted to `diagnostics_models.py` but offset/severity helpers were not centralized.
- **Code-judo alternative:** Move helpers to `diagnostics_models.py` or `lint_types.py`; single import site for both modules.
- **Suggested remediation:** Trivial dedupe in same PR as TN-PROJ-DIAG-10 decomposition.
- **Tests that would prove fix:** Grep single definition; no behavior change.
- **Handoff overlap:** CC-14

---

### TN-PROJ-DIAG-15 — Built-in vs Pyflakes provider fork still drops non-PY200 overlap (partial fix only)

- **Persona:** TN-PROJ-DIAG
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/intelligence/diagnostics_service.py:145-151` — Pyflakes branch skips four built-in AST walkers; else branch runs them. `test_diagnostics_py200_pyflakes.py` confirms PY200 runs under both providers (fixed since TN-INT-05). Built-in PY210/PY220/PY221/PY230 still duplicate Pyflakes when vendor Pyflakes is always bundled (`AGENTS.md`). Mutually exclusive fork remains for hygiene rules.
- **Code-judo alternative:** Default provider = Pyflakes + always-on PY200; delete built-in duplicate walkers (~120 LOC) or document Pyflakes as mandatory on ChoreBoy and remove built-in provider from settings.
- **Suggested remediation:** Product decision: if Pyflakes is always present, hard cutover built-in hygiene rules to Pyflakes-only path.
- **Tests that would prove fix:** Retarget redundant built-in-only tests to Pyflakes path; settings copy reflects composition not fork.
- **Handoff overlap:** R5, AD-016

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| R5 classifier SSOT | **Partial** — lint PY200 uses `is_module_resolvable`; explain/quick-fix do not use `classify_module` (TN-PROJ-DIAG-2, -6) |
| Layer direction | **Inverted** — `dependency_classifier` imports intelligence (TN-PROJ-DIAG-4) |
| Runtime probe policy | **Inconsistent** — static default guarded by tests; manual lint + import analysis still probe (TN-PROJ-DIAG-1, -13) |
| Private layout helper | **Open** — explain imports `_module_path_prefix_exists_at_base` (TN-PROJ-DIAG-3) |
| Diagnostic model | **Dual** — `ImportDiagnostic` strip/rebuild cycle (TN-PROJ-DIAG-7) |
| Quick-fix ownership | **Split** — source-root plan vs shell apply (TN-PROJ-DIAG-8, -9) |
| God module | **510 LOC** — walkers + explain remain (TN-PROJ-DIAG-10, -11) |
| Snapshot orchestration | **Absent** — diagnostics builds own walk (TN-PROJ-DIAG-12) |
| Intelligence Wave 1 deltas | Models + Pyflakes extracted; PY200 under Pyflakes fixed; probe static default tested |

**Approval bar:** Would not approve new explain kinds, classifier branches, or quick-fix action kinds until TN-PROJ-DIAG-2/4/8 land (explain adapts classifier, project-layer owns resolution/probe, unified quick-fix apply). TN-PROJ-DIAG-1 (manual lint probe) is the highest behavioral-risk item for ChoreBoy UI responsiveness.
