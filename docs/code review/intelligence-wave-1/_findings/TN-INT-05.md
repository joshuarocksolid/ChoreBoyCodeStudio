# TN-INT-05 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-05  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/intelligence/diagnostics_service.py` (614 LOC), `app/intelligence/lint_profile.py` (176 LOC), `app/intelligence/code_actions.py` (394 LOC), `app/intelligence/import_diagnostics.py` (167 LOC). Cross-read: `app/intelligence/runtime_import_probe.py`, `app/project/dependency_classifier.py`, `app/shell/lint_workflow.py`, `app/shell/python_style_workflow.py`, `tests/unit/intelligence/test_diagnostics_service.py` (674 LOC).

---

## Executive verdict

**Not thermo-clean — behavior works, structure does not.** Phase 2+3 correctly extracted PY200 import resolution into `import_diagnostics.py`, but the extraction stopped halfway: `diagnostics_service.py` remains a 614-line god module that still owns four bespoke AST walkers, Pyflakes integration, lint-profile post-processing, explanation taxonomy, and two parallel diagnostic datamodels. The default-vs-Pyflakes fork creates two incompatible lint universes (built-in reimplements a subset of Pyflakes; Pyflakes mode skips project import resolution entirely). Runtime import probing can spawn AppRun subprocesses from the lint hot path when callers pass `allow_runtime_import_probe=True`. Dominant risk: every new rule, quick fix, or import-layout tweak will land in the same file or duplicate helpers across modules — the next intelligence wave will pay compound interest unless diagnostics is decomposed into orchestration + rule engines + shared AST utilities now.

---

### TN-INT-05-1 — `diagnostics_service.py` is a god module absorbing orchestration, models, walkers, and Pyflakes

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:41-80` — three public datamodels (`ImportDiagnostic`, `ImportExplanation`, `CodeDiagnostic`). `:123-192` — `analyze_python_file` orchestrates syntax, provider fork, five diagnostic sources, profile filter, sort. `:381-498` — four private AST rule functions (`_duplicate_definition_diagnostics`, `_unused_import_diagnostics`, `_duplicate_import_diagnostics`, `_unreachable_statement_diagnostics`). `:534-614` — Pyflakes loader, vendor `sys.path` mutation, message adapter. `:248-370` — `explain_unresolved_import` classification tree. Single file: 614 LOC at baseline HEAD.
- **Code-judo alternative:** Split into `diagnostics_models.py` (types only), `python_lint_orchestrator.py` (parse once, dispatch), `builtin_lint_rules.py` (AST visitors), `pyflakes_adapter.py`, `import_explanations.py`. Keep `diagnostics_service.py` as a thin re-export facade or delete it after hard cutover imports. Target: no file >250 LOC in this lane.
- **Suggested remediation:** One hard-cutover PR: extract modules, update shell/plugin imports, delete in-file walkers from god module. Do not add PY2xx rules inline until split lands.
- **Tests that would prove fix:** Existing `tests/unit/intelligence/test_diagnostics_service.py` green with import path updates only; optional smoke import of public API from facade module.
- **Handoff overlap:** R5

---

### TN-INT-05-2 — Phase 2+3 extraction is incomplete: circular imports and duplicated helpers remain

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/import_diagnostics.py:18-19,34,160-161` — runtime inline imports of `CodeDiagnostic` / `DiagnosticSeverity` from `diagnostics_service` to break cycles. `app/intelligence/import_diagnostics.py:149-167` duplicates `_col_offset`, `_end_col_offset`, `_severity_from_profile_value` already at `app/intelligence/diagnostics_service.py:238-246,520-525`. `app/intelligence/diagnostics_service.py:28` imports `collect_unresolved_import_diagnostics` while `import_diagnostics` imports back from `diagnostics_service`.
- **Code-judo alternative:** Move shared types + AST offset helpers + severity mapping into `app/intelligence/diagnostics_models.py` (or `lint_types.py`). Both `import_diagnostics` and builtin walkers import from there — zero circular imports, zero inline imports, one `_severity_from_profile_value`.
- **Suggested remediation:** Extract models first (breaks cycle), then dedupe helpers in same PR as TN-INT-05-1 decomposition.
- **Tests that would prove fix:** `python3 run_tests.py tests/unit/intelligence/test_diagnostics_service.py tests/unit/project/test_import_layout.py` — no import cycles at module load; grep shows single definition of each helper.
- **Handoff overlap:** R5

---

### TN-INT-05-3 — Default vs Pyflakes provider fork creates two incompatible lint semantics

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/diagnostics_service.py:167-189` — when `selected_linter == pyflakes`, only `_pyflakes_diagnostics` runs; built-in walkers and `collect_unresolved_import_diagnostics` are skipped entirely. Else branch runs built-in rules + PY200. `app/shell/settings_dialog_sections.py:141-142` exposes this as a user-facing choice. ChoreBoy's core value prop includes project import resolution (PY200); Pyflakes mode silently drops it.
- **Code-judo alternative:** Pyflakes as an *additional* engine that feeds a unified diagnostic stream, not a mutually exclusive fork. Always run PY200 (import layout) regardless of provider; map Pyflakes messages into shared `CodeDiagnostic` codes; delete duplicate built-in PY220/PY221/PY210 when Pyflakes is present, or delete built-in duplicates entirely and require Pyflakes for those rules.
- **Suggested remediation:** Reframe `analyze_python_file` as `syntax + imports + provider_rules` composable pipeline. Document in settings that Pyflakes augments (or replaces) name/import hygiene but never disables project import analysis.
- **Tests that would prove fix:** Parametrized test: unresolved `import missing.mod` emits PY200 under both `LINTER_PROVIDER_DEFAULT` and `LINTER_PROVIDER_PYFLAKES`. Settings UI copy updated.
- **Handoff overlap:** R5, AD-016

---

### TN-INT-05-4 — Built-in AST walkers reimplement Pyflakes rules the profile already maps

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `lint_profile.py:54-70` defines PY220/PY221/PY210/PY230 for built-in engine; `:72-106` defines PY301–PY305/PY399 for Pyflakes mapping to overlapping concerns (e.g. PY220 unused import in both). `diagnostics_service.py:406-443` `_unused_import_diagnostics` — naive `ast.walk` Name-load scan misses re-exports, `__all__`, type-checking blocks, star-import semantics that Pyflakes handles. `:446-474` duplicate import detection duplicates Pyflakes behavior when vendor Pyflakes is always bundled per `AGENTS.md`.
- **Code-judo alternative:** Delete built-in PY210/PY220/PY221/PY230 walkers; default provider = Pyflakes when vendored (always on ChoreBoy) + always-on PY200 import module. Removes ~120 LOC and one entire semantic fork.
- **Suggested remediation:** Hard cutover: built-in provider becomes "Pyflakes + project imports + syntax" or rename default to reflect composition. Keep only rules Pyflakes cannot express (PY200, maybe ChoreBoy-specific unreachable heuristics if justified).
- **Tests that would prove fix:** Retain behavioral tests via Pyflakes path; delete redundant built-in-only tests or retarget them; assert PY200 still fires on default provider.
- **Handoff overlap:** R5

---

### TN-INT-05-5 — Multiple full-tree `ast.walk` passes instead of one visitor

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `diagnostics_service.py:171-174` calls four functions each walking or scanning the tree. `_unused_import_diagnostics` `:409` — `for node in ast.walk(syntax_tree)`. `_unreachable_statement_diagnostics` `:479` — second full `ast.walk`. `import_diagnostics.py:42` — third full `ast.walk` for imports. Per-file lint on large modules repeats O(n) traversals × 3+.
- **Code-judo alternative:** Single `DiagnosticVisitor(ast.NodeVisitor)` accumulating all built-in findings in one pass; import collection can share the same visitor or a dedicated `ImportVisitor` invoked once. Orchestrator calls `visitor.visit(tree)` once.
- **Suggested remediation:** Introduce visitor during TN-INT-05-1 split; benchmark not required — structural win is readability and predictable extension point.
- **Tests that would prove fix:** Existing diagnostic ordering/count tests unchanged; optional perf test under `tests/integration/performance/` if lint latency is tracked.
- **Handoff overlap:** none

---

### TN-INT-05-6 — Redundant `ast.parse` on the Pyflakes path

- **Persona:** TN-INT-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `diagnostics_service.py:148-149` — `syntax_tree = ast.parse(source, ...)`. `:167-169` Pyflakes branch skips `syntax_tree` and calls `_pyflakes_diagnostics`. `:560-563` `_create_pyflakes_checker` parses again: `syntax_tree = ast.parse(source, filename=str(file_path))`.
- **Code-judo alternative:** Pass the already-parsed tree into `_create_pyflakes_checker(syntax_tree, file_path)`; Pyflakes `Checker` accepts AST directly (already used at `:563`).
- **Suggested remediation:** One-line signature change when refactoring orchestrator; delete duplicate parse.
- **Tests that would prove fix:** Pyflakes tests in `test_diagnostics_service.py` remain green; syntax-error path still returns before Pyflakes (no double parse on error).
- **Handoff overlap:** none

---

### TN-INT-05-7 — Runtime import probe subprocess can run from lint hot path

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `import_diagnostics.py:45-51,86-91` — each unresolved candidate calls `is_module_resolvable(..., allow_runtime_import_probe=...)`. `dependency_classifier.py:244-245` — probe calls `is_runtime_module_importable(top_level)`. `runtime_import_probe.py:63-68` — `subprocess.run([runtime_path, "-c", probe_script], timeout=5)`. `semantic_navigation_workflow.py:309,342` and `python_style_workflow.py:149` pass `allow_runtime_import_probe=True`. `lint_workflow.py:106` enables probe only on manual trigger — good — but other callers bypass that policy.
- **Code-judo alternative:** Probe only in `explain_unresolved_import` and explicit "Analyze imports" actions, never inside per-node `collect_unresolved_import_diagnostics`. Lint classifies via filesystem + `known_runtime_modules` only; probe enriches explanations on demand.
- **Suggested remediation:** Split `is_module_resolvable` into `is_module_resolvable_static` (lint) and probe-backed helper (explain/manual audit). Thread probe flag only through explanation APIs.
- **Tests that would prove fix:** Unit test asserts `collect_unresolved_import_diagnostics` never calls `subprocess.run` when probe flag true (mock subprocess); integration test for explain path still probes.
- **Handoff overlap:** R4, AD-016

---

### TN-INT-05-8 — Parallel diagnostic models: `ImportDiagnostic` strips what `CodeDiagnostic` already carries

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `diagnostics_service.py:41-47` — `ImportDiagnostic` (file, line, message only). `:70-80` — `CodeDiagnostic` (code, severity, columns). `:218-234` — `_diagnostics_for_file` converts `CodeDiagnostic` → `ImportDiagnostic`, dropping code/severity/columns. `find_unresolved_imports` and `analyze_python_file` are two entry points for overlapping PY200 semantics.
- **Code-judo alternative:** Deprecate `ImportDiagnostic`; `find_unresolved_imports` returns `list[CodeDiagnostic]` filtered to `code=="PY200"` (or a thin alias type). Plugins/runtime explainers consume the rich model.
- **Suggested remediation:** Hard cutover bundled plugin + `runtime_explainer` imports; keep `find_unresolved_imports` as compatibility wrapper returning filtered `CodeDiagnostic` if needed.
- **Tests that would prove fix:** `test_find_unresolved_imports_*` assert code/severity present; plugin serializers updated.
- **Handoff overlap:** R5

---

### TN-INT-05-9 — `explain_unresolved_import` duplicates classifier logic and imports a private layout helper

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `diagnostics_service.py:266-268` — inline import `from app.project.import_layout import _module_path_prefix_exists_at_base` (private API). `:257-370` — parallel decision tree (source root missing, project module, compiled extension, runtime probe, vendored missing) overlapping `dependency_classifier.classify_module` and `suggest_missing_source_root` already used elsewhere. `:373-378` — `_looks_like_runtime_specific_module` magic heuristic (`isupper()` or `PySide` prefix).
- **Code-judo alternative:** `explain_unresolved_import` = thin adapter: `classified = classify_module(...)` → map `ClassifiedModule.category` to `ImportExplanation` templates. Delete private import; delete heuristic in favor of probe result + category.
- **Suggested remediation:** Move explanations next to `dependency_classifier` or new `import_explanation.py` owned by project layer; intelligence only formats strings.
- **Tests that would prove fix:** Existing explain tests in `test_diagnostics_service.py` green; grep shows no `_module_path_prefix_exists_at_base` imports outside `import_layout.py`.
- **Handoff overlap:** R3, R5

---

### TN-INT-05-10 — Pyflakes adapter uses fragile message-type string dispatch and `Any` boundaries

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `diagnostics_service.py:566-607` — `_diagnostic_from_pyflakes_message(message: Any, ...)` branches on `type(message).__name__` strings (`"UndefinedName"`, `"UnusedImport"`, …). `:539-542` iterates `getattr(checker, "messages", [])` untyped. `:546-563` `_create_pyflakes_checker` returns `Any | None`; inline `# type: ignore[import-not-found]` for pyflakes import.
- **Code-judo alternative:** Typed protocol or small registry `PYFLAKES_MESSAGE_MAP: dict[type, Callable[..., CodeDiagnostic]]` populated once at import; use `isinstance` checks. Optional: stable pyflakes message API wrapper in `pyflakes_adapter.py` with documented upstream coupling.
- **Suggested remediation:** Encapsulate all Pyflakes coupling in one adapter module; add characterization tests per message class (already partially present `:607-653`).
- **Tests that would prove fix:** Extend parametrized tests for each mapped Pyflakes message type; adapter unit tests do not import `diagnostics_service` god module.
- **Handoff overlap:** none

---

### TN-INT-05-11 — Global `sys.path` mutation for vendor Pyflakes

- **Persona:** TN-INT-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `diagnostics_service.py:610-614` — `_ensure_vendor_path_on_sys_path` inserts `vendor/` at position 0 on every Pyflakes lint invocation path (`:548`). Mutates process-global import state from intelligence layer.
- **Code-judo alternative:** Rely on existing bootstrap/vendor injection used by tests and AppRun (`run_tests.py` / `dev_launch_editor.py` already wire vendor). Delete runtime mutation; if import fails, degradation path already logs once (`:552-557`).
- **Suggested remediation:** Remove `_ensure_vendor_path_on_sys_path`; verify editor launch path pre-injects vendor (canonical bootstrap owns path policy).
- **Tests that would prove fix:** Pyflakes tests pass without helper; no duplicate vendor entries in `sys.path` after repeated lints.
- **Handoff overlap:** R4

---

### TN-INT-05-12 — Quick-fix planning split across intelligence and shell for `add_source_root`

- **Persona:** TN-INT-05
- **Severity:** STRUCTURAL
- **Evidence:** `code_actions.py:247-256` — plans `QuickFix(action_kind="add_source_root", ...)`. `:101-113` — `apply_quick_fixes` handles only `remove_line`, `replace_import_module`, `create_module_file`; no `add_source_root`. `python_style_workflow.py:182-185` — shell filters source-root fixes and applies via `_apply_source_root_fixes` (manifest mutation). `:243-287` — `_extract_unresolved_module_name` parses `"Unresolved import: {name}"` string contract from diagnostics.
- **Code-judo alternative:** Either implement `add_source_root` inside `apply_quick_fixes` (inject manifest writer dependency) or stop emitting that action from `code_actions` and let shell plan it — not both. Prefer typed diagnostic field `unresolved_module: str` on PY200 instead of message parsing.
- **Suggested remediation:** Add optional metadata to `CodeDiagnostic` (e.g. `detail: Mapping[str, str]`) for machine-readable fix keys; move manifest write into project service callable from `apply_quick_fixes` or dedicated shell planner.
- **Tests that would prove fix:** `test_code_actions.py` covers apply paths; new test for source-root fix end-to-end without string parsing.
- **Handoff overlap:** R5, shell-wave-1-followup

---

### TN-INT-05-13 — `lint_profile` unknown codes silently default to enabled warning

- **Persona:** TN-INT-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `lint_profile.py:158-160` — `resolve_lint_rule_settings`: if `code not in _DEFINITIONS_BY_CODE`, return `(True, LINT_SEVERITY_WARNING)`. Pyflakes emits PY399 bucket for unmapped messages (`diagnostics_service.py:568`). Future pyflakes classes could bypass user disable settings in UI.
- **Code-judo alternative:** Unknown codes: either register dynamically into profile on adapter mapping, or default to `(False, warning)` / explicit `PY399` only path with logging. Fail closed for settings contract.
- **Suggested remediation:** Assert adapter maps all emitted codes; `resolve_lint_rule_settings` logs once on unknown code in dev builds.
- **Tests that would prove fix:** Test unknown code respects explicit policy; settings dialog only lists `_DEFINITIONS_BY_CODE`.
- **Handoff overlap:** none

---

### TN-INT-05-14 — Dead import and stale audit doc signal ongoing drift

- **Persona:** TN-INT-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `diagnostics_service.py:24-27` imports `is_module_resolvable` but grep shows zero use in module (resolution delegated to `import_diagnostics`). `docs/deslop/AUDIT_app.md:178` still cites `diagnostics_service.py — 717 lines` (stale vs 614 LOC baseline).
- **Code-judo alternative:** Remove dead import; update audit doc line counts when decomposition lands.
- **Suggested remediation:** Trivial cleanup in same PR as TN-INT-05-2 model extraction.
- **Tests that would prove fix:** Ruff F401 clean on module; no behavior change.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| God module / 1k-line rule | 614 LOC today; four concerns still co-located — next rules likely push past 700+ without split (TN-INT-05-1) |
| Phase 2+3 import extraction | PY200 moved to `import_diagnostics.py` but helpers/models still duplicated (TN-INT-05-2) |
| Pyflakes vs built-in | Mutually exclusive fork drops PY200 in Pyflakes mode; duplicate rule implementations (TN-INT-05-3, TN-INT-05-4) |
| AST walker sprawl | 3+ full-tree walks + redundant parse on Pyflakes path (TN-INT-05-5, TN-INT-05-6) |
| Runtime subprocess probe | Callable from lint via `allow_runtime_import_probe` — policy inconsistent across shell callers (TN-INT-05-7) |
| Quick fixes | File mutations in intelligence; manifest/source-root in shell; message-string parsing contract (TN-INT-05-12) |
| SSOT with project layer | `classify_module` exists; explain path reimplements classification (TN-INT-05-9) |

**Approval bar:** Would not approve new diagnostic rules or quick-fix kinds in `diagnostics_service.py` until TN-INT-05-1/02/03 land (decompose, dedupe, unify provider pipeline). Runtime probe in per-node lint (TN-INT-05-7) is the highest behavioral-risk structural issue for UI responsiveness on ChoreBoy.
