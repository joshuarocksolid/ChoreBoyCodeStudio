# TN-INT-SHELL-SEAM — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-SHELL-SEAM  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/shell/main_window_composition.py` (595 LOC), `app/shell/editor_intelligence_controller.py` (252 LOC), `app/shell/lint_workflow.py` (246 LOC), `app/shell/intelligence_cache_workflow.py` (200 LOC), `app/shell/python_style_workflow.py` (232 LOC), `app/shell/python_console_workflow.py` (116 LOC). Cross-read: `app/shell/shell_composition.py` (`build_python_console_workflow`), `app/shell/semantic_navigation_workflow.py` (revision helpers, completion orchestration), `app/editors/code_editor_semantics.py`, `app/shell/python_console_widget.py`. Gates: AD-016, AD-017, AD-018, `docs/ARCHITECTURE.md` §17.4.7–§17.4.8.

---

## Executive verdict

**Not thermo-clean — the lint-vs-session split is directionally right, but the shell seam adds indirection without buying clarity.** Composition correctly constructs `SemanticSession` for Jedi/Rope/completion and routes lint/format/fix tooling through `WorkflowBroker`, preserving AD-016 lane separation. Dominant risks: **(1) `EditorIntelligenceController` is a 252-line identity wrapper between composition and session**, doubling the surface area TN-INT-01 already flagged as copy-paste orchestration; **(2) AD-018 revision gating is implemented three different ways** (`semantic_navigation_workflow` helpers, `lint_workflow` inline checks, editor-widget `request_generation`), with `PythonStyleWorkflow` running diagnostics synchronously on the UI thread with no gate at all; **(3) editor vs REPL completion stay on separate stacks per §17.4.8, but `RuntimeIntrospectionCoordinator` re-merges REPL runtime items into editor completion inside `semantic_navigation_workflow`**, blurring the seam composition was meant to keep clean. Would not approve further shell intelligence wiring until the passthrough controller is collapsed or justified, revision applicability is one canonical helper, and all diagnostics ingress paths share `LintWorkflow` (or a single runner) with consistent async + gate semantics.

---

### TN-INT-SHELL-SEAM-1 — Composition builds `SemanticSession` then immediately wraps it in a no-op controller

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:337-344` — `SemanticSession(...)` constructed with `dispatch_to_main_thread`, `cache_db_path`, `state_root`; immediately passed to `EditorIntelligenceController(semantic_session=window._semantic_session)`. `app/shell/editor_intelligence_controller.py:28-188` — every public method (`request_completion`, `request_hover_info`, `request_lookup_definition`, …) is a one-line forward to `self._semantic_session.*`. Only non-trivial code is static formatters (`format_inline_hover_text`, `format_inline_signature_text`) at `:222-252`.
- **Code-judo alternative:** Delete the controller layer for routing; shell workflows hold a typed `SemanticSessionPort` (or the session directly) and a small `EditorIntelligenceFormatting` module for inline text. Composition exposes `_semantic_session` + formatter, not two objects that must stay in sync. Saves ~200 LOC and removes the illusion of a boundary that does not enforce anything.
- **Suggested remediation:** Hard cutover: replace `intelligence_controller()` host ports with `semantic_session()` + formatter helpers; migrate `semantic_navigation_workflow` and `editor_tab_factory` call sites; delete passthrough methods. Keep controller name only if it grows real shell-side policy (debounce, telemetry aggregation, preference gates).
- **Tests that would prove fix:** `rg "EditorIntelligenceController"` shows zero production construction or passthrough-only usage; existing semantic session tests unchanged; shell host tests inject session stub directly.
- **Handoff overlap:** AD-016, TN-INT-01-3

---

### TN-INT-SHELL-SEAM-2 — `complete_fast` is wired through composition onto the UI thread

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** BLOCKER
- **Evidence:** `app/shell/main_window_composition.py:342-344` — composition creates controller exposing `complete_fast`. `app/shell/editor_intelligence_controller.py:43-44` — passthrough to `semantic_session.complete_fast`. `app/intelligence/semantic_session.py:71-74` — `complete_fast` calls `CompletionService.complete_fast` on the **caller thread**. `app/shell/semantic_navigation_workflow.py:535-536` — `request_editor_completions_async` invokes `intelligence_controller.complete_fast(request=request)` synchronously during completion orchestration on the UI path. `docs/ARCHITECTURE.md:1271-1274` — semantic/completion broker state is session-owned and should serialize on `SemanticWorker`.
- **Code-judo alternative:** Composition should not expose a UI-callable fast tier that mutates broker caches. Either route fast tier through worker at priority 0 (same lane as semantic) or make fast tier read-only/immutable from UI and apply results only after revision gate on main thread. Delete `complete_fast` from shell-facing API until thread ownership is fixed (pairs with TN-INT-01-2).
- **Suggested remediation:** Block shell seam growth until session enforces single-lane broker access; composition wires only async completion entry points to workflows.
- **Tests that would prove fix:** Contract test: no `app/shell/` module calls `complete_fast` or `record_completion_acceptance` off-worker; stress test under TN-INT-01-2.
- **Handoff overlap:** AD-016, TN-INT-01-2

---

### TN-INT-SHELL-SEAM-3 — Intelligence bootstrap is scattered across composition with no seam module

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:256-266,337-344,417,444-477,479` — intelligence prefs, `SemanticSession`, controller, `IntelligenceCacheWorkflow`, `LintWorkflow`, `DiagnosticsOrchestrator`, `PythonConsoleWorkflow`, and `SemanticNavigationWorkflow` are wired in four separate init phases separated by unrelated workflows (local history, project tree, layout). `register_builtin_workflow_providers` at `:331-334` sits between REPL manager and session construction. No `wire_intelligence_shell(window)` or documented init-order comment tying AD-016 objects together.
- **Code-judo alternative:** Extract `app/shell/intelligence_composition.py` with one function returning a dataclass `IntelligenceShellPorts(session, lint_workflow, cache_workflow, console_workflow, nav_workflow, diagnostics_orchestrator)` called from a single block in `main_window_composition.py`. Init order becomes auditable: broker providers → session → background scheduler → lint/cache/console/nav.
- **Suggested remediation:** Extract bootstrap module in hard cutover; add init-order docstring referencing AD-016/AD-017/AD-018. Do not add more `window._*` intelligence fields inline in composition.
- **Tests that would prove fix:** Unit test constructing `IntelligenceShellPorts` with fake window satisfies host protocols; composition test asserts single bootstrap call.
- **Handoff overlap:** AD-016, R4

---

### TN-INT-SHELL-SEAM-4 — Lint correctly uses `workflow_broker`, but `PythonStyleWorkflow` bypasses `LintWorkflow` with a sync UI path

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/lint_workflow.py:111-122` — async lint via `analyze_python_with_workflow(self._host.workflow_broker(), ...)` with buffer revision capture and stale drop at `:128-133`. `app/shell/python_style_workflow.py:144-153` — `apply_safe_fixes_for_file` calls `analyze_python_with_workflow(window._workflow_broker, ...)` **synchronously on the UI thread** with no revision gate, no background scheduler, no shared telemetry. `app/shell/python_style_workflow.py:115-124` — manual lint action correctly delegates to `window._lint_workflow.render_diagnostics_for_file`. Three diagnostics ingress paths exist: `LintWorkflow`, sync safe-fixes, and `semantic_navigation_workflow.handle_analyze_imports` (`find_unresolved_imports` direct at `semantic_navigation_workflow.py:305-312`).
- **Code-judo alternative:** One `DiagnosticsRunner` (or `LintWorkflow.run_sync_for_file` / `schedule_for_file`) owns all `analyze_python_with_workflow` calls. Safe fixes schedule lint through the same runner and await/consume results with identical stale policy—or run fix planning on worker thread entirely.
- **Suggested remediation:** Route safe-fix diagnostics through `LintWorkflow` or shared runner; delete direct broker call from `PythonStyleWorkflow`. Align analyze-imports with broker adapter if plugin linters must apply.
- **Tests that would prove fix:** `rg "analyze_python_with_workflow" app/shell/` shows single module (lint runner) besides tests; safe-fix test asserts background execution or revision gate on apply.
- **Handoff overlap:** AD-018, TN-INT-05

---

### TN-INT-SHELL-SEAM-5 — AD-018 revision gate duplicated: shared helpers vs lint inline vs widget generation

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/semantic_navigation_workflow.py:33-66` — canonical `is_stale_revision_gated_editor_request` / `deliver_revision_gated_editor_result` (widget identity + `buffer_revision` equality). `app/shell/lint_workflow.py:125-133` — reimplements the same two checks inline (`active_widget is not editor_widget`, `buffer_revision != captured`). `app/editors/code_editor_semantics.py:183-184,222-223,238-239,251-252` — separate **`request_generation`** gate in editor widget apply methods. `app/shell/lint_workflow.py` never imports the shared helpers. `docs/ARCHITECTURE.md:1977-1982` (AD-018) — one rule, multiple implementations.
- **Code-judo alternative:** Move `is_stale_revision_gated_editor_request` to `app/shell/editor_stale_result_policy.py` (or `app/editors/stale_result_gate.py`). Lint, nav, and any future workflows import it. Document dual gate: `buffer_revision` for content staleness, `request_generation` for superseded completion/hover requests—both checked in one `apply_editor_intelligence_result(...)` helper.
- **Suggested remediation:** Lint hard cutover to shared helper; add helper that composes revision + generation checks for completion apply paths.
- **Tests that would prove fix:** Parametrized test on shared helper covers lint + nav scenarios; delete duplicated inline checks in lint.
- **Handoff overlap:** AD-018, R4

---

### TN-INT-SHELL-SEAM-6 — Editor completion applies revision gate in nav workflow but generation gate only in editor widget

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/semantic_navigation_workflow.py:538-557` — fast tier checks `is_stale_revision_gated_editor_request` then calls `editor_widget.show_completion_items_for_request(request_generation=...)`. `app/editors/code_editor_semantics.py:183-184` — widget drops if `request_generation != self._completion_request_generation`. Async semantic callback at `semantic_navigation_workflow.py:641-648` uses `deliver_revision_gated_editor_result` with `result.buffer_revision` but relies on widget for generation. Runtime introspection repaints at `:570-586` check revision only, not generation, before calling `show_completion_items_for_request`—a superseding completion request could still paint if revision unchanged.
- **Code-judo alternative:** Single apply function: `deliver_editor_completion(file_path, editor_widget, requested_revision, request_generation, items, prefix)` that checks both invariants before touching popup state. Nav workflow stops open-coding partial gates.
- **Suggested remediation:** Extend `deliver_revision_gated_editor_result` (rename to `deliver_gated_editor_result`) to accept optional `request_generation` and delegate to widget only after both pass.
- **Tests that would prove fix:** Test: bump `request_generation` without buffer edit → runtime introspection callback does not repaint; existing completion tests green.
- **Handoff overlap:** AD-018

---

### TN-INT-SHELL-SEAM-7 — REPL vs editor completion split is correct at composition, but editor path re-merges REPL runtime items

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `docs/ARCHITECTURE.md:1332-1341` — editor and Python Console are different semantic problems; console uses live runtime introspection. `app/shell/main_window_composition.py:321-328,477` — REPL via `ReplSessionManager`; console completion via `PythonConsoleWorkflow(repl_manager=window._repl_manager)` — **no `SemanticSession`**. `app/shell/python_console_workflow.py:88-95` — `repl_manager.complete(...)` off UI thread. Contrast: editor completion flows through `semantic_navigation_workflow` → `EditorIntelligenceController` → `SemanticSession`. `app/shell/main_window_composition.py:327-328` — `RuntimeIntrospectionCoordinator(runner_port=window._repl_manager)` wired beside session. `app/shell/semantic_navigation_workflow.py:528-536,559-586` — editor completion merges `coordinator.cached_items` / `fetch_and_cache_from_runner` into editor popup via `_merge_completion_items`. REPL stack leaks into editor completion at shell orchestration layer.
- **Code-judo alternative:** Keep stacks separate: editor completion = session + static indexes only; runtime-assisted items become an explicitly labeled optional tier with separate UI affordance, or move merge into `CompletionBroker` on worker thread with metadata labeling per §17.4.2. Console stays on `ReplCompletionPort` only.
- **Suggested remediation:** Document in shell seam whether REPL merge in editor is intentional product behavior; if yes, move merge off UI thread and through session/broker; if no, delete coordinator from editor completion path.
- **Tests that would prove fix:** Editor completion test without REPL running never calls `runner_port`; console test never touches `SemanticSession`.
- **Handoff overlap:** AD-016, R3

---

### TN-INT-SHELL-SEAM-8 — Python Console workflow: generation-only gate vs editor’s dual gate

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/python_console_widget.py:137-138` — `show_completion_items_for_request` drops stale via `request_generation` only; no buffer revision concept (single-line input buffer). `app/shell/python_console_workflow.py:78-109` — async work captures generation, never line-buffer snapshot; if user edits prompt during REPL round-trip, generation may still match while text changed. `app/shell/shell_composition.py:263-274` — composition correctly routes console work through `GeneralTaskScheduler` with key `"python_console_completion"` (AD-017), unlike default `PythonConsoleWorkflow` daemon thread fallback at `python_console_workflow.py:114-116`.
- **Code-judo alternative:** Capture `(request_generation, line_buffer_hash)` at request time; apply gate compares both. Align naming with AD-018 “revision” concept for console (`prompt_revision` counter on edit). Shared helper with editor policy where semantics align.
- **Suggested remediation:** Add prompt revision counter on console input edit; extend console apply gate; remove unused default thread starter in production path or mark `@deprecated` for tests only.
- **Tests that would prove fix:** Console widget test: edit prompt during inflight completion → results dropped despite matching generation if hash differs.
- **Handoff overlap:** AD-018

---

### TN-INT-SHELL-SEAM-9 — `PythonStyleWorkflow` uses `window: Any` while sibling intelligence workflows use Protocol hosts

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/python_style_workflow.py:23-24` — `def __init__(self, window: Any)`. Direct field access throughout (`window._workflow_broker`, `window._lint_workflow`, `window._loaded_project`, …). Contrast: `app/shell/lint_workflow.py:14-70` — `LintWorkflowHost` Protocol + `MainWindowLintHost`; `app/shell/intelligence_cache_workflow.py:15-50` — `IntelligenceCacheHost` Protocol; `app/shell/python_console_workflow.py:38-48` — `PythonConsoleWorkflowHost` Protocol. `main_window_composition.py:276` — `PythonStyleWorkflow(window)` breaks the host pattern used for lint/cache/console.
- **Code-judo alternative:** Introduce `PythonStyleWorkflowHost` Protocol (workflow_broker, lint_workflow, editor_manager, loaded_project, quick_fix prefs, …) + `MainWindowPythonStyleHost`. Matches lint seam; enables unit tests without full MainWindow.
- **Suggested remediation:** Extract host in same PR as TN-INT-SHELL-SEAM-4 lint-path consolidation; no new `window._` access in workflow body.
- **Tests that would prove fix:** Unit test with fake host triggers format/lint/safe-fix handlers; pyright strict on workflow module with Protocol.
- **Handoff overlap:** R4

---

### TN-INT-SHELL-SEAM-10 — `MainWindowPythonConsoleHost` erases typed console port at composition boundary

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/python_console_workflow.py:38-42,26-35` — `PythonConsoleWorkflowHost.python_console_widget() -> PythonConsoleWidgetPort | None` with typed `show_completion_items_for_request`. `app/shell/shell_composition.py:219-220` — `MainWindowPythonConsoleHost.python_console_widget(self) -> object | None`. Composition factory at `:263-274` loses type contract pyright could enforce.
- **Code-judo alternative:** Return `PythonConsoleWidgetPort | None`; import port type in shell_composition. Same pattern as `LintWorkflowHost.workflow_broker()`.
- **Suggested remediation:** Fix return annotation + host Protocol conformance; run pyright on shell_composition.
- **Tests that would prove fix:** pyright 0 errors on `shell_composition.py` for console host; no runtime change.
- **Handoff overlap:** none

---

### TN-INT-SHELL-SEAM-11 — Intelligence cache generation gate parallels lint revision gate without shared abstraction

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/intelligence_cache_workflow.py:65-66,128-129,149-150` — `bump_symbol_index_generation()` captured at start; callbacks drop when `generation != self._host.symbol_index_generation()`. `app/shell/lint_workflow.py:105,128` — per-file `buffer_revision` capture/drop. `app/shell/main_window_composition.py:302,417` — `_symbol_index_generation` and editor buffer revisions live on different controllers. Both implement “async result applies only if still current” but with different counters and no shared naming.
- **Code-judo alternative:** Extract `StaleAsyncResultPolicy` utility: `capture_token()` / `is_stale(token)` generic over int generation counters; document editor revision vs project index generation in ARCHITECTURE §17.4.7 footnote.
- **Suggested remediation:** Optional refactor when touching AD-018 helper (TN-INT-SHELL-SEAM-5); low priority if unified editor helper lands first.
- **Tests that would prove fix:** Cache workflow tests unchanged; shared utility unit test for token semantics.
- **Handoff overlap:** AD-018

---

### TN-INT-SHELL-SEAM-12 — `main_window_composition.py` intelligence slice adds orchestration surface without decomposition budget

- **Persona:** TN-INT-SHELL-SEAM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window_composition.py` — 595 LOC at baseline; intelligence-related fields and wiring (`_semantic_session`, `_intelligence_controller`, `_lint_workflow`, `_intelligence_cache_workflow`, `_python_console_workflow`, `_diagnostics_orchestrator`, prefs, timers) account for ~90 LOC plus imports. File grows monolithically via `install_main_window_composition`; no intelligence extraction yet. 1k-line rule (`thermo-nuclear` rubric) — currently safe at 595, but trend mirrors pre-split `main_window.py` debt noted in architecture §12.
- **Code-judo alternative:** Extract intelligence bootstrap (TN-INT-SHELL-SEAM-3) before next wave adds test-runner intelligence, plugin diagnostics hooks, or AI panels. Target: composition file stays transport-only for intelligence.
- **Suggested remediation:** Land `intelligence_composition.py` before wave 2 shell features; track LOC budget in TASKS.md slice exit criteria.
- **Tests that would prove fix:** `wc -l main_window_composition.py` decreases after extraction; bootstrap integration test green.
- **Handoff overlap:** R4

---

## Cross-cutting notes

| Theme | Status in shell seam slice |
|-------|----------------------------|
| AD-016: session owns semantic engines | Composition constructs session correctly; controller passthrough adds noise (TN-INT-SHELL-SEAM-1); UI-thread `complete_fast` breaks lane purity (TN-INT-SHELL-SEAM-2) |
| Lint via `workflow_broker`, not session | **Correct** in `LintWorkflow` (TN-INT-04 path); undermined by sync bypass in `PythonStyleWorkflow` (TN-INT-SHELL-SEAM-4) |
| §17.4.8 editor vs REPL completion split | Composition wires separate stacks; editor nav re-merges REPL runtime (TN-INT-SHELL-SEAM-7); console generation-only gate (TN-INT-SHELL-SEAM-8) |
| AD-018 revision gate | Helpers exist in nav workflow but not reused by lint; dual generation/revision split across layers (TN-INT-SHELL-SEAM-5, TN-INT-SHELL-SEAM-6) |
| Protocol host pattern | Strong for lint/cache/console; missing for python style (TN-INT-SHELL-SEAM-9) |
| 1k-line rule | All scoped files under 1k; composition at 595 needs extraction discipline (TN-INT-SHELL-SEAM-12) |

**Approval bar:** Block on TN-INT-SHELL-SEAM-2 (UI-thread broker mutation via composition API). Land TN-INT-SHELL-SEAM-1, TN-INT-SHELL-SEAM-4, and TN-INT-SHELL-SEAM-5 together with TN-INT-01 blockers before adding new shell intelligence workflows. REPL/editor merge policy (TN-INT-SHELL-SEAM-7) needs explicit product/architecture sign-off if retained.
