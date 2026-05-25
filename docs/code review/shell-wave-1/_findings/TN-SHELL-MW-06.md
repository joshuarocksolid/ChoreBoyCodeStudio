# TN-SHELL-MW-06 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-06  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 1997–2664 — intelligence menu actions (definition, references, rename, hover, signature), inline async hover/signature requesters, and adjacent edit/navigation handlers in the same slice.

**Context read:** `EditorIntelligenceController` (`app/shell/editor_intelligence_controller.py`), `docs/ARCHITECTURE.md` §12.3/§12.12/AD-018, `docs/deslop/AUDIT_app_remaining_handoff.md` R2 §Candidate extractions §4.

---

## Executive verdict

**Not thermo-clean.** `EditorIntelligenceController` correctly owns semantic routing and string formatting, but this slice leaves ~430 lines of menu orchestration, dialog branching, problems-panel wiring, rename preview/apply staging, and AD-018 revision guards in `MainWindow` — exactly what R2 lists as the next extraction target. The controller is a thin session façade; the shell still implements five parallel action handlers with copy-pasted preconditions, duplicated `semantic_unavailable` UX trees, paired async stale-guard blocks, and a rename flow buried in nested closures. Dominant risk: **intelligence feature logic continues to sprawl in a 5,549-line / 332-method composition root instead of a cohesive workflow module**, so the next navigation/refactor menu item will fork another handler instead of extending one place.

---

### TN-SHELL-MW-06-1 — Intelligence menu orchestration still lives in MainWindow despite a dedicated controller

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2047–2478` — five menu handlers (`_handle_find_references_action`, `_handle_rename_symbol_action`, `_handle_go_to_definition_action`, `_handle_signature_help_action`, `_handle_hover_info_action`) plus `_choose_definition_location`, four inline build/request helpers, and problems-panel / dialog / local-history side effects. `EditorIntelligenceController` only forwards to `SemanticSession` and formats tooltip text (`app/shell/editor_intelligence_controller.py:25–252`). Architecture §12.3: shell “coordinates services but should not contain deep business logic”; handoff R2 candidate §4: “inline hover/signature helpers that mostly forward to `EditorIntelligenceController`.”
- **Code-judo alternative:** Extract a `SemanticNavigationWorkflow` (or `EditorIntelligenceWorkflow`) owning the five user actions end-to-end: context validation, controller dispatch, result presentation, rename preview/apply, and problems-panel population. Pass narrow ports (`parent`, `open_file_at_line`, `problems_panel`, `save_workflow`, `local_history_workflow`, `intelligence_controller`, `metrics_settings`) — same pattern as `PythonStyleWorkflow` / `SaveWorkflow`. Wire `menu_wiring.py` callbacks to workflow methods; delete the handler block from `MainWindow`.
- **Suggested remediation:** R2 wave-4 PR scoped to semantic navigation only (references, definition, rename first; hover/signature menu actions in same module). Method count on `MainWindow` must decrease; no new one-line delegators per handoff §3.
- **Tests that would prove fix:** Move existing characterization tests from `tests/unit/shell/test_main_window_reference_rename_actions.py` and `test_main_window_semantic_navigation_actions.py` to `tests/unit/shell/test_semantic_navigation_workflow.py` targeting the extracted class; `rg "^    def " app/shell/main_window.py | wc -l` drops by ≥10.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-2 — Duplicated `semantic_unavailable` dialog branching across references and definition

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** Near-identical three-level trees at `app/shell/main_window.py:2081–2106` (Find References) and `app/shell/main_window.py:2277–2296` (Go To Definition):

  ```python
  if not result.hits:  # or not lookup.found
      if result.metadata.unsupported_reason:
          if result.metadata.source == "semantic_unavailable":
              QMessageBox.warning(..., "Semantic references/definitions are currently unavailable.\n\nReason: ...")
              return
          QMessageBox.information(..., "No semantic ... found ... dynamic or unresolved.")
      else:
          QMessageBox.information(..., "No references/definition found ...")
  ```

- **Code-judo alternative:** One typed presenter on the workflow (or a small `semantic_result_copy.py` helper) keyed by action kind + `SemanticOperationMetadata` — e.g. `present_empty_semantic_result(title, symbol_name, metadata) -> bool` returning whether UI already handled the case. Branches collapse to a single call in each handler.
- **Suggested remediation:** Implement in the R2 extraction module; reuse for any future semantic actions (e.g. rename empty-plan messaging uses a related but separate path today at `2190–2196`).
- **Tests that would prove fix:** Parametrized unit tests on the presenter for `(semantic_unavailable, unsupported_reason set)`, `(unsupported, other source)`, and `(empty, no reason)`; existing MainWindow tests repointed or deleted after cutover.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-3 — Rename action is a nested callback state machine in MainWindow

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2135–2256` — 120 lines spanning: save-all gate, `QInputDialog`, identifier validation, telemetry in `on_success`, preview truncation (`preview_patches[:3]`), confidence copy, `QMessageBox.question`, then nested `on_apply_success` / `on_apply_error` closures calling `request_apply_rename`, local-history transaction, tab refresh, project reload, and success toast.
- **Code-judo alternative:** Split into staged workflow methods with explicit types: `prompt_rename_symbol() -> str | None`, `confirm_rename_plan(plan: SemanticRenamePlan) -> bool`, `apply_confirmed_plan(plan) -> None`. Controller stays transport-only; workflow owns dialog sequencing and post-apply side effects.
- **Suggested remediation:** Same R2 PR as TN-SHELL-MW-06-1 or immediately following slice; do not add more rename branches to `MainWindow`.
- **Tests that would prove fix:** Characterization tests for plan preview truncation, confidence strings, and apply success path (already partially covered in `test_handle_rename_symbol_action_on_success_applies_plan`) moved to workflow module with typed `SemanticRenamePlan` fixtures instead of `SimpleNamespace`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-4 — Paired async stale-guard helpers and thin sync pass-throughs duplicate controller work

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** `_build_inline_signature_text` / `_build_inline_hover_text` at `app/shell/main_window.py:2376–2404` are seven-line forwards (`project_root` lookup + controller call). `_request_inline_signature_text_async` and `_request_inline_hover_text_async` at `2406–2478` duplicate the same AD-018 pattern: capture `requested_revision`, verify `active_widget is editor_widget`, compare `_editor_buffer_revision`, then format via controller. Wired from `app/shell/editor_tab_factory.py:116–132`.
- **Code-judo alternative:** Move revision-gated async presentation into `EditorIntelligenceController` (or the extracted workflow) with a single generic helper, e.g. `request_inline_tooltip(kind, ..., revision_getter, on_show)` — or colocate both sync menu and async editor entry points in the workflow so `MainWindow` exposes zero intelligence methods. Delete `_build_inline_*` pass-throughs; menu actions call workflow directly.
- **Suggested remediation:** R2 extraction §4 explicitly names these helpers. Hard cutover `editor_tab_factory` closures to workflow/controller ports in the same PR.
- **Tests that would prove fix:** Unit test that stale revision or widget swap drops callback; async and sync paths share one guard implementation (mock revision getter); remove methods from `MainWindow` method count.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-5 — Menu hover/signature use blocking sync resolution; editor uses async with revision gates

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** Menu actions at `app/shell/main_window.py:2315–2347` call `_build_inline_*` → `SemanticSession.resolve_*_blocking` inside `EditorIntelligenceController` (`editor_intelligence_controller.py:198–220`) on the UI thread. Editor-triggered hover/signature use `_request_inline_*_async` with generation + revision checks (`main_window.py:2406–2478`, AD-018). Two architectural paths for the same intelligence feature.
- **Code-judo alternative:** Menu actions should dispatch the same async request path (with generation 0 or a dedicated manual trigger) and show calltip on success — or workflow exposes one `show_hover_or_signature(manual=True)` that always async-dispatches. Eliminates blocking semantic work on the main thread and one sync code path.
- **Suggested remediation:** Part of semantic workflow extraction; verify menu latency under slow semantic backend manually (four-theme N/A — calltip text only).
- **Tests that would prove fix:** Workflow test asserting menu path calls `request_hover_info` / `request_signature_help`, not blocking resolvers; optional integration test with delayed session mock.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-6 — Definition chooser erodes typed boundaries with `list[object]`, `getattr`, and `cast(Any)`

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2349–2374` — `_choose_definition_location(self, locations: list[object])` uses `getattr(location, "file_path", "")` despite `SemanticDefinitionResult.locations: list[SemanticLocation]` (`app/intelligence/semantic_models.py:88`). Call site at `2300–2301`: `selected_location = cast(Any, location)` then `str(...)` / `int(...)`.
- **Code-judo alternative:** Type the chooser as `list[SemanticLocation] -> SemanticLocation | None`; build labels from dataclass fields directly. Delete `cast(Any)` — pyright should prove the open path.
- **Suggested remediation:** Fix in workflow extraction; add typed callback tests using real `SemanticLocation` instances.
- **Tests that would prove fix:** Extend `test_handle_go_to_definition_action_uses_target_chooser` to use `SemanticLocation` fixtures; pyright on workflow module reports 0 errors without `# type: ignore` on nested callbacks.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-7 — Repeated editor/project context boilerplate and duplicate intelligence telemetry

- **Persona:** TN-SHELL-MW-06
- **Severity:** STRUCTURAL
- **Evidence:** Each of references (`2047–2060`), rename (`2136–2166`), and definition (`2259–2274`) repeats: `_loaded_project is None` → warning, `active_tab` / `editor_widget` None checks, then identical extraction of `project_root`, `current_file_path`, `source_text`, `cursor_position`. References and rename each embed ~20 lines of `time.perf_counter()` + `_intelligence_runtime_settings.metrics_logging_enabled` + thresholded warning/info logging (`2062–2089`, `2168–2189`).
- **Code-judo alternative:** `@dataclass SemanticEditorContext(project_root, file_path, source_text, cursor_position, editor_widget, active_tab)` built by `require_semantic_editor_context(require_project: bool) -> SemanticEditorContext | None` (shows the right QMessageBox once). Telemetry wraps controller callbacks: `log_semantic_latency(operation, started_at, **fields)` in workflow or controller module.
- **Suggested remediation:** Implement as first step inside the R2 workflow module so handler bodies shrink before dialog logic moves.
- **Tests that would prove fix:** Unit tests on context builder for missing project/tab/editor; telemetry helper tested with metrics on/off and over-threshold warning once.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-06-8 — `_handle_analyze_imports_action` is unrelated orchestration in the same slice

- **Persona:** TN-SHELL-MW-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:2480–2539` — 60 lines of import diagnostics, severity mapping, problems panel, runtime center dialog, and `background_tasks.run` unrelated to semantic navigation but sitting between intelligence helpers and go-to-symbol handlers in this line range.
- **Code-judo alternative:** Move to `PythonStyleWorkflow` extension or a small `ImportAnalysisWorkflow` per R2/R5 boundaries (diagnostics SSOT lives under `app/intelligence/`).
- **Suggested remediation:** Separate R2/R5 brief; do not bundle with semantic navigation extraction unless the same PR already touches problems-panel wiring.
- **Tests that would prove fix:** Existing import-analysis tests (if any) follow the module; MainWindow method count decreases.
- **Handoff overlap:** R2, R5

---

### TN-SHELL-MW-06-9 — Unit tests prove handlers are hard to isolate without `MainWindow.__new__` harnesses

- **Persona:** TN-SHELL-MW-06
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/shell/test_main_window_reference_rename_actions.py:33–56` and `test_main_window_semantic_navigation_actions.py:24–38` construct bare `MainWindow` instances with `cast(Any, window)` and patch a dozen private attributes — a smell that the logic under test is not a testable module boundary.
- **Code-judo alternative:** After TN-SHELL-MW-06-1, tests target `SemanticNavigationWorkflow` with injected fakes; delete `MainWindow.__new__` construction patterns for these actions.
- **Suggested remediation:** Pair test migration with R2 extraction PR (hard cutover, no dual test paths).
- **Tests that would prove fix:** Workflow tests pass without importing `MainWindow`; shell integration tests keep one smoke path through menu wiring if needed.
- **Handoff overlap:** R2

---

## Cross-slice notes (for TN-SHELL-INTEG)

- **R2 semantic extraction:** This slice is the clearest single R2 target named in `AUDIT_app_remaining_handoff.md` §Candidate extractions §4. Integrate with MW-05 editing slice and completion async handlers (`main_window.py:5009+`) under one “intelligence leaves MainWindow” P1 theme.
- **AD-018 revision gating:** Hover/signature async guards here mirror completion/lint stale-drop patterns elsewhere; integration should push one revision-gated callback helper shared across intelligence UI updates.
- **Controller vs workflow boundary:** `EditorIntelligenceController` should remain routing + formatting only; dialog copy, problems panel, rename preview, and telemetry belong in the extracted workflow — do not mirror every handler as a controller method (handoff R2 implementation note).
- **Four-theme impact:** Intelligence actions use QMessageBox / problems panel only; no new hardcoded colors in this slice. HC/Light/Dark validation not required for structural extraction unless dialog copy or panel chrome changes.
