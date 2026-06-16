# TN-INT-SHELL-NAV — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-SHELL-NAV  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/shell/semantic_navigation_workflow.py` (1103 LOC — **CC-10: sole `app/` module above 1k lines**). Cross-read: `app/shell/editor_intelligence_controller.py`, `app/shell/editor_tab_factory.py`, `app/shell/menu_wiring.py`, `app/shell/shell_composition.py`, `app/intelligence/runtime_introspection.py`, `app/intelligence/completion_context.py`, `tests/unit/shell/test_semantic_navigation_workflow.py`, `docs/ARCHITECTURE.md` §28 (file ownership), AD-016, AD-018. Gates: facade/controller boundary (§17.4), AD-018 revision gate, 1k-line decomposition rule.

---

## Executive verdict

**Not thermo-clean — CC-10 is a presumptive BLOCKER and this file is the dominant shell maintainability debt in intelligence wave 1.** At 1103 lines it is the only module under `app/` above the 1k boundary; further intelligence/shell growth lands here by default. `SemanticNavigationWorkflow` is a god orchestrator (navigation, inline intelligence, completions + runtime introspection merge, import analysis, rename, references) with a 30-method host protocol and a 110-line MainWindow adapter. Seven direct `app.intelligence.*` imports bypass `EditorIntelligenceController`, and AD-018 revision gating is applied inconsistently across async editor paths — including a bespoke resolve gate that uses a different widget lookup than every other path. The completion fast path merges runtime introspection beside the controller while the semantic slow path repaints without that merge, so three delivery channels compete in one method. Would not approve additional features in this file until decomposition and boundary cleanup land first.

---

### TN-INT-SHELL-NAV-1 — CC-10: sole `app/` file above 1k lines (1103 LOC)

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** BLOCKER
- **Evidence:** `wc -l app/shell/semantic_navigation_workflow.py` → 1103. Baseline `ce17698` already 1103 — not a single-PR spike, but the file **is** the CC-10 violation: next-largest `app/` module is `editor_tab_workflow.py` at 937 LOC (~166 lines headroom). Thermo-nuclear rule: no file should sit above 1k without compelling structure; this one holds workflow class (~800 LOC), host protocol (~100 LOC), host adapter (~110 LOC), and revision helpers.
- **Code-judo alternative:** Hard cutover split before any new shell intelligence surface: (1) `semantic_navigation_host.py` — `SemanticNavigationHost` + `MainWindowSemanticNavigationHost`; (2) `editor_completion_workflow.py` — `request_editor_completions_async`, `request_completion_item_resolve_async`, `_merge_completion_items`; (3) `import_analysis_workflow.py` — `handle_analyze_imports_action`; (4) `symbol_navigation_workflow.py` — go-to-def, find-refs, rename, goto-symbol-in-file menu handlers; (5) keep `semantic_navigation_workflow.py` as thin coordinator or delete in favor of composition wiring. Target: no slice file >600 LOC.
- **Suggested remediation:** Block new LOC in this path; land extraction PR as wave-1 P0 follow-up. Update `docs/ARCHITECTURE.md` §28 ownership bullets to name the split modules.
- **Tests that would prove fix:** Existing `tests/unit/shell/test_semantic_navigation_workflow.py` green against new import paths; `find app -name '*.py' -exec wc -l {} + | awk '$1>1000'` returns empty under `app/`.
- **Handoff overlap:** CC-10, R5

---

### TN-INT-SHELL-NAV-2 — God workflow: one class owns ten unrelated editor intelligence surfaces

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** Module docstring L1 — “Semantic navigation, inline intelligence, and import analysis.” `SemanticNavigationWorkflow` methods span: `handle_go_to_definition_action` (192), `handle_signature_help_action` (252), `handle_hover_info_action` (271), `handle_analyze_imports_action` (290), `handle_goto_symbol_in_file_action` (354), async inline signature/hover (393–479), `request_editor_completions_async` (481–659), `handle_find_references_action` (705), `handle_rename_symbol_action` (801), `request_completion_item_resolve_async` (933). Menu wiring (`menu_wiring.py:106–117`) binds **six** menu entries to this single object. ARCHITECTURE §28 lists only “find references, rename, and completion resolve” — doc ownership already understates actual scope.
- **Code-judo alternative:** Reframe by **delivery channel**, not feature name: `EditorIntelligenceAsyncWorkflow` (all revision-gated editor callbacks), `EditorNavigationMenuWorkflow` (modal/menu actions), `ImportAnalysisWorkflow` (background diagnostics + Runtime Center). MainWindow holds three composed instances; menu wiring imports the right one per action. Deletes the “everything navigation” naming lie.
- **Suggested remediation:** Split along channel boundaries above; do not add methods to `SemanticNavigationWorkflow`.
- **Tests that would prove fix:** Parametrize menu/handler tests by workflow class; each test module <300 LOC focused on one surface.
- **Handoff overlap:** CC-10, R5

---

### TN-INT-SHELL-NAV-3 — Seven direct `app.intelligence.*` imports bypass `EditorIntelligenceController`

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L12–27 import seven intelligence submodules directly: `completion_context.build_completion_context`, `completion_models.*`, `completion_service.CompletionRequest`, `diagnostics_service.find_unresolved_imports` + `CodeDiagnostic`, `lint_profile.resolve_lint_rule_settings`, `outline_service.build_outline_from_source` / `flatten_symbols`, `runtime_introspection.*`. ARCHITECTURE §28 L686–697 assigns “semantic request routing and inline result formatting” to `editor_intelligence_controller`; this workflow calls the controller for some paths (`request_lookup_definition`, `complete_fast`, `request_completion`) but **not** for import analysis, outline build, completion context, or runtime introspection merge. Integration gate 3: “Facade/controller boundary — no direct Jedi/Rope/library calls from shell/editors” — same principle applies to intelligence services.
- **Code-judo alternative:** Extend controller (or a narrow `EditorIntelligenceFacade` port) with: `build_completion_context`, `analyze_unresolved_imports`, `outline_for_source`, `runtime_completion_items_for_context`. Shell workflow only talks to controller + host; intelligence imports drop to zero in shell navigation layer.
- **Suggested remediation:** Move direct intelligence calls behind controller methods; shell file imports only `EditorIntelligenceController` types re-exported at controller boundary if needed.
- **Tests that would prove fix:** `rg '^from app\.intelligence' app/shell/semantic_navigation_workflow.py` → no matches; controller unit tests cover new passthrough/seams.
- **Handoff overlap:** AD-016, R3

---

### TN-INT-SHELL-NAV-4 — AD-018 revision gate applied three different ways in one module

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** BLOCKER
- **Evidence:** Canonical helpers L33–66: `is_stale_revision_gated_editor_request` uses `editor_widget_for_path`; `deliver_revision_gated_editor_result` wraps deliver. **Path A (consistent):** signature/hover async L415–421, L459–465; semantic completion slow path L641–647 — use `deliver_revision_gated_editor_result` with snapshot `requested_revision`. **Path B (inline duplicate):** completion fast paint L538–544 and runtime introspection success L570–576 call `is_stale_revision_gated_editor_request` directly with manual early-return/show — same logic, no shared deliver wrapper, telemetry interleaved differently. **Path C (bespoke):** `request_completion_item_resolve_async` L957–961 uses `editor_widgets_by_path().get(file_path)` instead of `editor_widget_for_path`, and compares `editor_buffer_revision(file_path) != result.buffer_revision` (response revision) rather than snapshot at request time L943. AD-018 L1977–1982: validate against **current** buffer revision before mutating editor UI — all three paths must share one lookup + one snapshot rule.
- **Code-judo alternative:** Single internal `_with_editor_gate(*, file_path, editor_widget, requested_revision, deliver)` used by **every** async editor mutation including fast completion, runtime introspection repaint, resolve, signature, hover, semantic completion. Delete Path B/C variants. Resolve path must use same widget resolver as gate helper.
- **Suggested remediation:** Hard cutover resolve + fast paths to shared gate; add regression test that resolve uses `editor_widget_for_path` contract.
- **Tests that would prove fix:** Parametrized test: stale widget swap + revision bump drops delivery for fast, slow, runtime, and resolve paths identically. Test that resolve rejects when `editor_widgets_by_path` and `editor_widget_for_path` diverge (if ever possible).
- **Handoff overlap:** AD-018, TN-INT-01-1

---

### TN-INT-SHELL-NAV-5 — Sync menu hover/signature bypass revision gate entirely

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** `handle_signature_help_action` L252–269 and `handle_hover_info_action` L271–288 call `_build_inline_*` synchronously and `editor_widget.show_calltip(tooltip_text)` with no `request_generation`, no `requested_revision`, no stale check. Async counterparts L393–479 use generation + AD-018 gate. Same feature, two contracts — menu path can paint stale calltips if invoked during async race (unlikely but inconsistent with AD-018 spirit). Cross-ref TN-INT-01-1: blocking resolvers on UI thread.
- **Code-judo alternative:** Delete sync menu builders; menu actions call the same async methods as editor hooks (`request_inline_*_async` with a fresh generation). One code path, one gate.
- **Suggested remediation:** Menu handlers dispatch async paths only; remove `_build_inline_*` from menu flow or restrict to tests.
- **Tests that would prove fix:** Menu action test asserts `request_inline_hover_text_async` called, not `build_inline_hover_text`.
- **Handoff overlap:** AD-018, TN-INT-01-1

---

### TN-INT-SHELL-NAV-6 — Runtime introspection merge orchestrated in shell beside `complete_fast`, not in broker/controller

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** `request_editor_completions_async` L510–533 builds `completion_context`, calls `resolve_runtime_introspection_query_with_inference`, reads `coordinator.cached_items`, `attach_replacement_metadata`, merges via `_merge_completion_items` L536, paints fast merged popup L553–557. L559–600 schedules `coordinator.fetch_and_cache_from_runner` via `background_tasks` with second merge L581–585. L535 calls `intelligence_controller.complete_fast(request=request)` on caller thread. ARCHITECTURE gate 4: “Merge policy owned by `CompletionBroker`, not widgets.” TN-INT-02 flags broker/UI double-fast-path; this file **adds a third merge locus** in shell.
- **Code-judo alternative:** Controller method `complete_fast_with_runtime(request, context) -> merged envelope` owns: context build, runtime query, cache read, broker fast tier, merge policy. Shell only: gate + `show_completion_items_for_request`. Background runtime fetch becomes controller/session job keyed `runtime_introspect:{path}` with callback that re-invokes same merge helper.
- **Suggested remediation:** Move L510–600 intelligence orchestration into controller/session; shell retains paint + gate only.
- **Tests that would prove fix:** Unit test on controller merge (not shell); shell test mocks controller returning pre-merged envelope.
- **Handoff overlap:** TN-INT-02, AD-016, R4

---

### TN-INT-SHELL-NAV-7 — Semantic completion slow path repaints without runtime merge (three-channel race)

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** Fast path L536–557 shows `_merge_completion_items(fast_envelope.items, runtime_items)`. Runtime async success L581–585 merges `fast_envelope.items` with `attached`. Semantic `on_success` deliver L635–638 sets `items=completions` where `completions = result.envelope.items` only — **no** `_merge_completion_items(..., runtime_items)` and no re-read of coordinator cache. User who waits for semantic tier can lose runtime introspection items that were shown (or would have been merged) in fast tier; ordering depends on timing.
- **Code-judo alternative:** One function `final_completion_items(fast_envelope, runtime_items, semantic_envelope) -> list[CompletionItem]` called from all three delivery points after gate passes. Or semantic tier merge happens in broker before envelope returns (preferred — gate 4).
- **Suggested remediation:** Unify merge at controller/broker; shell never chooses which items survive per phase.
- **Tests that would prove fix:** Integration test: runtime items present + semantic completion returns → popup contains union of both, regardless of phase order.
- **Handoff overlap:** TN-INT-02, R4

---

### TN-INT-SHELL-NAV-8 — `request_editor_completions_async` (~180 LOC) is unmaintainable orchestration soup

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L481–659 single method: perf timer, duplicate request/context construction L497–521, runtime cache branch, sync fast complete on UI thread L535, conditional fast paint with nested telemetry L545–552, background introspection task with nested success/error L566–600, semantic async callback with nested deliver + telemetry + degradation status L602–648, error handler L650–651. Four nested closure levels; three separate `show_completion_items_for_request` call sites.
- **Code-judo alternative:** Extract pure phases: `_snapshot_completion_request(...) -> (request, context, revision)`, `_paint_fast_completions(...)`, `_schedule_runtime_fetch(...)`, `_deliver_semantic_completions(...)`. Each ≤40 LOC, each calls shared gate + merge. Method becomes linear 15-line conductor.
- **Suggested remediation:** Extract helpers in same PR as controller merge move (TN-INT-SHELL-NAV-6/7); do not grow inline.
- **Tests that would prove fix:** Phase helpers unit-tested independently; existing completion workflow tests unchanged behavior.
- **Handoff overlap:** CC-10, R4

---

### TN-INT-SHELL-NAV-9 — Duplicate `CompletionRequest` and `build_completion_context` parameter blocks

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L497–508 `CompletionRequest(...)` and L510–521 `build_completion_context(...)` pass identical fields: `source_text`, `cursor_position`, `current_file_path`, `project_root`, `trigger_is_manual`, `min_prefix_chars`, `max_results`, `trigger_kind`, `trigger_character`, `buffer_revision`. Any new field must be edited twice — drift risk already visible if one path omits a flag.
- **Code-judo alternative:** `build_completion_context` returns both context and `CompletionRequest` (or context exposes `.to_completion_request()`). Single construction site in intelligence layer, not shell.
- **Suggested remediation:** Collapse in `completion_context.py` or controller; delete duplicate block from shell.
- **Tests that would prove fix:** One test asserting request fields == context-derived request for all trigger kinds.
- **Handoff overlap:** TN-INT-02

---

### TN-INT-SHELL-NAV-10 — `handle_analyze_imports_action` duplicates diagnostics orchestration owned elsewhere

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L290–352: collects editor overrides, calls `find_unresolved_imports` directly, maps PY200 severity via `resolve_lint_rule_settings`, builds `CodeDiagnostic` list, pushes to problems panel, builds `build_import_issue_report`, opens Runtime Center. ARCHITECTURE §28 assigns lint execution to `lint_workflow` and `DiagnosticsOrchestrator`. TN-INT-05 notes `allow_runtime_import_probe=True` here bypasses manual-trigger policy used in `lint_workflow.py:106`.
- **Code-judo alternative:** `ImportAnalysisWorkflow` calls controller/lint orchestrator `run_import_analysis(overrides) -> ImportAnalysisResult` dataclass; shell only renders panel + optional Runtime Center dialog from result.
- **Suggested remediation:** Move analysis + severity mapping to intelligence/diagnostics layer; align probe policy with lint workflow.
- **Tests that would prove fix:** Import analysis behavior tested on diagnostics service/orchestrator; shell test asserts panel wiring given stub result.
- **Handoff overlap:** TN-INT-05, R3

---

### TN-INT-SHELL-NAV-11 — `SemanticNavigationHost` protocol is a 30+ method god port

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L69–169 `SemanticNavigationHost` Protocol declares 30 methods spanning editor tabs, intelligence controller, problems panel, runtime onboarding, lint overrides, completion settings, local history, project rescan. Every new intelligence UI need widens the port; `MainWindowSemanticNavigationHost` L993–1103 implements each as one-line `self._window._*` reach-through.
- **Code-judo alternative:** Split ports: `EditorSurfaceHost` (widgets, revisions, open_at_line), `ProblemsSurfaceHost`, `IntelligenceSettingsHost`, `RuntimeReportsHost`. Workflow classes take only the port they need. Adapter composes mixins or delegates to existing controllers (`_problems_controller`, `_runtime_onboarding_workflow`).
- **Suggested remediation:** Narrow host before next feature; avoid adding methods to monolithic protocol.
- **Tests that would prove fix:** Fake hosts in tests implement ≤8 methods each; no full 30-method stub required per test class.
- **Handoff overlap:** R5

---

### TN-INT-SHELL-NAV-12 — `handle_rename_symbol_action` nests four callback layers with modal UI in async success

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** L801–931: sync validation + save gate L834–836 → `on_success(plan)` with telemetry L843–864 → preview QMessageBox L882–895 → nested `on_apply_success` / `on_apply_error` L897–918 → second controller call L914. No revision gate on plan/apply (multi-file mutation — different AD-018 scope but stale plan risk if buffer changed after save_all). 130 LOC in one handler; hardest to characterize in tests (`test_main_window_reference_rename_actions.py` still targets window, not workflow — TN-SHELL-MW-06).
- **Code-judo alternative:** Extract `RenameSymbolWorkflow` with states `prompt → plan → confirm → apply`; each state a method; controller callbacks land on workflow methods not nested closures. Plan staleness: reject if buffer revision changed since `save_all`.
- **Suggested remediation:** Extract rename workflow module; add revision check after plan returns.
- **Tests that would prove fix:** `test_semantic_navigation_workflow.py` owns rename tests; nested closure depth gone.
- **Handoff overlap:** TN-SHELL-MW-06, AD-018

---

### TN-INT-SHELL-NAV-13 — Repeated menu-action boilerplate (project/tab/cursor guards) copy-pasted eight times

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** NICE-TO-HAVE
- **Evidence:** Patterns repeat in `handle_go_to_definition_action`, `handle_find_references_action`, `handle_rename_symbol_action`, sync hover/signature: fetch `dialog_parent`, `loaded_project` None → QMessageBox “Open a project first”; `active_tab`/`editor_widget` None → “Open a file tab first”; cursor symbol empty → “Place cursor on a symbol first.” Only message box titles differ.
- **Code-judo alternative:** `@require_project` / `@require_active_editor` decorators or `_with_active_editor(*, require_project, require_symbol)` context yielding `(parent, tab, widget, project_root)` or early-return dialog. Deletes ~80 LOC of guards.
- **Suggested remediation:** Extract when splitting navigation handlers (TN-INT-SHELL-NAV-2); low priority alone.
- **Tests that would prove fix:** Guard helper unit tests; handler tests supply invalid states once parametrized.
- **Handoff overlap:** none

---

### TN-INT-SHELL-NAV-14 — Type erasure and duck-typing at navigation boundaries

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** NICE-TO-HAVE
- **Evidence:** `# type: ignore[no-untyped-def]` on callbacks L213, 304, 314, 406, 450, 661, 723, 843, 897. `_choose_definition_location` L661–687 uses `getattr(location, "file_path", "")` on `list[object]`. `SemanticNavigationHost` returns `Any` for `editor_manager`, `intelligence_controller`, `background_tasks`, `problems_panel`. `cast(Any, location)` L237 before navigation.
- **Code-judo alternative:** Import `SemanticDefinitionLocation` (or shared navigation models) from `semantic_models`; type `on_success` callbacks with real result types; narrow host protocol return types to concrete controller/panel interfaces.
- **Suggested remediation:** Typing pass after controller boundary cleanup; not blocking if structure splits first.
- **Tests that would prove fix:** `pyright` on shell navigation modules with zero `Any` casts in workflow bodies.
- **Handoff overlap:** none

---

### TN-INT-SHELL-NAV-15 — Extraction map (actionable decomposition checklist)

- **Persona:** TN-INT-SHELL-NAV
- **Severity:** STRUCTURAL
- **Evidence:** Consolidated from findings above — current file bundles unrelated layers:

| Candidate module | Lines (approx) | Owns |
|------------------|----------------|------|
| `revision_gated_editor.py` | 33–66 | `is_stale_*`, `deliver_*` (shared AD-018) |
| `semantic_navigation_host.py` | 69–169, 993–1103 | Protocol + MainWindow adapter |
| `editor_completion_workflow.py` | 172–184, 481–659, 933–974 | Merge helper, completion async, resolve |
| `import_analysis_workflow.py` | 290–352 | Analyze imports menu action |
| `symbol_navigation_handlers.py` | 192–391, 661–687, 705–931 | Go-to-def, symbol-in-file, refs, rename |
| `inline_intelligence_handlers.py` | 252–479, 689–703, 976–990 | Sync/async hover & signature |

- **Code-judo alternative:** Land extractions in dependency order: (1) revision gate module — zero behavior change; (2) host split; (3) completion workflow + controller merge move; (4) menu handler splits. `semantic_navigation_workflow.py` deleted or reduced to `build_semantic_navigation_workflow()` factory re-exporting composed instances for `shell_composition.py:283`.
- **Suggested remediation:** Track as intelligence-wave-1 P1 epic; block feature PRs that add LOC to monolith.
- **Tests that would prove fix:** Test files mirror module split; CC-10 grep clean.
- **Handoff overlap:** CC-10, R5

---

## Summary table

| ID | Severity | Theme |
|----|----------|-------|
| TN-INT-SHELL-NAV-1 | **BLOCKER** | CC-10 / 1k LOC |
| TN-INT-SHELL-NAV-2 | STRUCTURAL | God workflow |
| TN-INT-SHELL-NAV-3 | STRUCTURAL | 7 direct intelligence imports |
| TN-INT-SHELL-NAV-4 | **BLOCKER** | AD-018 inconsistent gates |
| TN-INT-SHELL-NAV-5 | STRUCTURAL | Sync menu bypasses gate |
| TN-INT-SHELL-NAV-6 | STRUCTURAL | Runtime merge beside controller |
| TN-INT-SHELL-NAV-7 | STRUCTURAL | Semantic path drops runtime merge |
| TN-INT-SHELL-NAV-8 | STRUCTURAL | 180 LOC completion method |
| TN-INT-SHELL-NAV-9 | STRUCTURAL | Duplicate request/context build |
| TN-INT-SHELL-NAV-10 | STRUCTURAL | Import analysis wrong layer |
| TN-INT-SHELL-NAV-11 | STRUCTURAL | God host protocol |
| TN-INT-SHELL-NAV-12 | STRUCTURAL | Rename callback nesting |
| TN-INT-SHELL-NAV-13 | NICE-TO-HAVE | Guard boilerplate |
| TN-INT-SHELL-NAV-14 | NICE-TO-HAVE | Type erasure |
| TN-INT-SHELL-NAV-15 | STRUCTURAL | Extraction checklist |

**Blockers:** 2 (CC-10 file size; AD-018 gate inconsistency). **Structural:** 11. **Nice-to-have:** 2. **Total findings:** 15.
