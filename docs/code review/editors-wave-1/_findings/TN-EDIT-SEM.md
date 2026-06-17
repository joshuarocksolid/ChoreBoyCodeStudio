# TN-EDIT-SEM — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SEM
**Date:** 2026-06-17
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** `app/editors/code_editor_semantics.py` (376 LOC), `app/editors/code_editor_editing.py` (250 LOC), `app/editors/code_editor_diagnostics.py` (137 LOC). Cross-read: `app/shell/editor_completion_workflow.py`, `app/shell/editor_tab_factory.py` (completion/hover/accept closures). Gates: AD-016, AD-018, §17.4.2 tier presentation, gate 8 intelligence import discipline.

---

## Executive verdict

**REJECT — improved since Intelligence Wave 1, but the semantics mixin is still not thermo-clean.** The prior **BLOCKER** prefix fork (`extract_completion_prefix`) and UI-thread acceptance bypass are **resolved**: the editor now calls `build_completion_context`, and factory acceptance routes through `semantic_navigation_workflow` → `EditorCompletionWorkflow.record_editor_completion_acceptance` → `SemanticSession.request_record_completion_acceptance` on the worker lane. The dead sync `_completion_provider` path is also gone. Dominant remaining risks in this slice: **(1) duplicate `build_completion_context` computation in the editor on every trigger while the shell workflow rebuilds the same context with a richer envelope (`project_root`, `buffer_revision`)** — the editor still owns classification policy instead of painting broker-issued context; **(2) gate-8 violations** (`completion_context`, `completion_merge_policy` imports in the editor layer); **(3) `cast(Any)` / `TypeError` requester shims and dead `_request_completion_with_metadata`**; **(4) `CodeEditorSemanticsMixin.keyPressEvent` owns editing shortcuts that belong to the editing mixin**, tangling two mixin contracts in one hot path; **(5) hover tooltip orchestration split across diagnostics vs semantics** with duplicated TYPE_CHECKING state. `CodeEditorEditingMixin` is the bright spot — focused transforms with no intelligence leakage. Would not approve further semantics-surface growth until context/build moves entirely shell-side and the requester contract is typed once.

---

## Prior-wave re-validation (TN-INT-SHELL-EDITORS 1, 2, 5, 6, 10)

| Prior ID | Headline | Status at `042be49` | Notes |
|----------|----------|---------------------|-------|
| TN-INT-SHELL-EDITORS-1 | Editor imports `extract_completion_prefix` | **RESOLVED** | `code_editor_semantics.py` imports and calls `build_completion_context` at `:12,126-136,359-367`. No `extract_completion_prefix` in `app/editors/`. **New debt:** duplicate context build (TN-EDIT-SEM-1). |
| TN-INT-SHELL-EDITORS-2 | Acceptance bypasses workflow / UI-thread session | **RESOLVED** | `editor_tab_factory.py:158-161` delegates to `semantic_navigation_workflow.record_editor_completion_acceptance`. `editor_completion_workflow.py:49-52` → `request_record_completion_acceptance` → `semantic_session.py:84-95` queues on worker (`priority=5`). AD-016 satisfied for acceptance routing. |
| TN-INT-SHELL-EDITORS-5 | Dead sync `_completion_provider` | **RESOLVED** | No `_completion_provider` / `set_completion_provider` in codebase. `trigger_completion` hides popup when requester is None (`code_editor_semantics.py:170-171`). |
| TN-INT-SHELL-EDITORS-6 | `cast(Any)` / `TypeError` requester shim | **STILL OPEN** | Shim at `code_editor_semantics.py:147-165`; dead helper at `:198-223`. See TN-EDIT-SEM-3, TN-EDIT-SEM-4. |
| TN-INT-SHELL-EDITORS-10 | Hover dispatch split diagnostics vs semantics | **STILL OPEN** | `code_editor_diagnostics.py:109-136` owns `QEvent.ToolTip`; semantics owns setters + `show_hover_text_for_request` (`:84-86,251-262`). See TN-EDIT-SEM-5. |

---

### TN-EDIT-SEM-1 — Editor rebuilds `build_completion_context` on every trigger; workflow rebuilds again

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:126-136` — `trigger_completion` calls `build_completion_context(source_text=..., current_file_path=self._active_file_path or "", project_root=None, ...)` for prefix gating and popup reuse. `app/shell/editor_completion_workflow.py:83-94` — `request_editor_completions_async` rebuilds the same function with `project_root=loaded_project.project_root` and `buffer_revision=requested_revision`. Editor passes computed `prefix` to the requester (`code_editor_semantics.py:149-157`); workflow ignores the editor's context object and recomputes.
- **Code-judo alternative:** Editor `trigger_completion` becomes a thin cursor snapshot + generation bump: `(source_text, cursor_position, manual, trigger_kind, trigger_character, request_generation)`. Shell workflow is the **sole** caller of `build_completion_context`; returns `(prefix, should_offer, replacement_range)` synchronously to the editor for popup reuse gating only, or editor waits for first gated deliver envelope that carries `valid_for.prefix`. Deletes intelligence import from semantics mixin entirely.
- **Suggested remediation:** Hard cutover: remove `build_completion_context` import from `code_editor_semantics.py`; move auto-trigger gating (`should_offer_automatic_results`) into workflow or a shell-side preflight that runs before async fan-out. Editor paints prefix from last delivered envelope.
- **Tests that would prove fix:** Typing in project-aware import context — editor auto-trigger gate matches workflow gate when `project_root` is set. Single `build_completion_context` call site per completion request (spy/assert in workflow test).
- **Handoff overlap:** AD-016, CC-05, TN-INT-SHELL-EDITORS-1

---

### TN-EDIT-SEM-2 — Gate 8 violation: semantics mixin imports context builder and merge policy

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:12-13` — `from app.intelligence.completion_context import build_completion_context` and `from app.intelligence.completion_merge_policy import is_tier_header_item`. Manifest gate 8 (`_findings/_README.md:87`) requires editors import typed **presentation models only**, not broker engines/session internals. `completion_context` is broker-owned classification (`ARCHITECTURE.md` §17.4.2, AD-016); `completion_merge_policy` is merge/tier policy, not a paint DTO.
- **Code-judo alternative:** Move `is_tier_header_item` check to popup controller only (already imported there) or expose a presentation flag on `CompletionItem` (`is_selectable: bool`). Context building never lives in `app/editors/`.
- **Suggested remediation:** Delete both imports from semantics; accept path rejects non-selectable items via popup `activated` filter (already skips tier headers in `completion_controller.py:225`). Context/replacement range always broker-stamped before paint.
- **Tests that would prove fix:** `rg "from app.intelligence.completion_context|completion_merge_policy" app/editors/code_editor_semantics.py` empty; accept-without-`replacement_*` becomes test-only edge with explicit no-op.
- **Handoff overlap:** AD-016, gate 8

---

### TN-EDIT-SEM-3 — `cast(Any)` + `TypeError` requester shim hides the completion contract

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:147-165` — `requester = cast(Any, self._completion_requester)` with `try/except TypeError` falling back from 7-arg to 5-arg call. `app/shell/editor_tab_factory.py:95-114` — production closure always supplies 7 args (`trigger_kind`, `trigger_character`). Shim sits in `trigger_completion`, invoked on every auto-trigger keystroke.
- **Code-judo alternative:** Define `CompletionRequester` Protocol in `completion_models.py` with the 7-arg contract. Type `_completion_requester` as that Protocol; delete `cast(Any)` and `TypeError` branch. Normalize legacy callers at shell wiring boundary once, not in editor hot path.
- **Suggested remediation:** Hard cutover per `hard_cutover_refactor.mdc`; pyright-clean semantics mixin.
- **Tests that would prove fix:** `npx pyright app/editors/code_editor_semantics.py` with no `Any` on requester path; factory closure satisfies Protocol structurally.
- **Handoff overlap:** R4, TN-INT-SHELL-EDITORS-6

---

### TN-EDIT-SEM-4 — Dead `_request_completion_with_metadata` duplicates the shim

- **Persona:** TN-EDIT-SEM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_semantics.py:198-223` — `_request_completion_with_metadata` mirrors the same `cast(Any)` / `TypeError` pattern as `trigger_completion`. `rg _request_completion_with_metadata app/` — **no callers** outside the definition.
- **Code-judo alternative:** Delete the method with TN-EDIT-SEM-3 shim removal; one call site, zero duplicate branching.
- **Suggested remediation:** Delete method; no replacement.
- **Tests that would prove fix:** `rg _request_completion_with_metadata` empty; fast shard green.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-6, hard-cutover bias

---

### TN-EDIT-SEM-5 — Hover tooltip entry in diagnostics; state and delivery in semantics

- **Persona:** TN-EDIT-SEM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_diagnostics.py:109-136` — `event(QEvent.ToolTip)` checks diagnostic ranges, then increments `_hover_request_generation` and calls `_hover_requester`. `app/editors/code_editor_semantics.py:57-60,84-86,251-262` — owns generation allocator, setters, and `show_hover_text_for_request`. MRO: `CodeEditorDiagnosticsMixin` before `CodeEditorSemanticsMixin` (`code_editor_widget.py:56-57`). TYPE_CHECKING stubs duplicate `_hover_request_generation`, `_hover_request_global_pos`, `_hover_requester` in both mixin base stubs (`diagnostics.py:26-28`, `semantics.py:34-36`).
- **Code-judo alternative:** Extract `CodeEditorTooltipsMixin` (or move full `event(ToolTip)` into semantics) where diagnostics contributes `_diagnostic_tooltip_at(pos) -> str | None` only. Single owner for generation counter and async deliver.
- **Suggested remediation:** Consolidate hover orchestration under semantics; diagnostics mixin stops calling `_hover_requester` directly.
- **Tests that would prove fix:** Existing `tests/unit/editors/test_semantic_editor_interactions.py` tooltip tests pass with single mixin owner; one generation counter increment site.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-10

---

### TN-EDIT-SEM-6 — Semantics `keyPressEvent` owns editing shortcuts outside the editing mixin

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:270-294` — `keyPressEvent` handles Tab/Backtab indent/outdent (`:279-285`), smart backspace (`:287-290`), and auto-indent newline (`:291-294`) by calling methods defined on `CodeEditorEditingMixin`. Editing mixin has **no** `keyPressEvent`; all keyboard editing policy flows through semantics file alongside completion popup navigation (`:271-272`) and auto-trigger (`:303-319`).
- **Code-judo alternative:** Move generic editing key handling to `CodeEditorEditingMixin.keyPressEvent` (or widget hub) that calls `super()` then semantics override for completion-only keys. Semantics mixin overrides only completion/signature keys; deletes indent/newline branches.
- **Suggested remediation:** Split `keyPressEvent`: editing mixin first in MRO chain or explicit delegate from widget hub; semantics retains completion trigger/navigation only.
- **Tests that would prove fix:** Characterization tests for Tab/Enter/Backspace unchanged; semantics file LOC drops ~25 lines of non-semantic key handling.
- **Handoff overlap:** §12.4 mixin composition

---

### TN-EDIT-SEM-7 — Accept-path fallback re-computes context when broker metadata missing

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:354-372` — when `item.replacement_start/end` is None, `_insert_completion_from_item` calls `build_completion_context(..., project_root=None, trigger_is_manual=True)` and deletes `replacement_range` locally. Broker/session stamps ranges via `attach_replacement_metadata` in workflow (`editor_completion_workflow.py:106,165`); this fallback reintroduces a second truth for delete span if metadata is ever missing.
- **Code-judo alternative:** Require `replacement_start/end` on every selectable item before paint; accept is no-op + log if missing. Delete fallback context rebuild from editor entirely (pairs with TN-EDIT-SEM-2).
- **Suggested remediation:** Broker guarantee + editor assert/no-op; remove lines 359-372 fallback branch.
- **Tests that would prove fix:** Parametrize `foo.bar|` accept — always uses broker-stamped span; item without `replacement_*` does not delete text.
- **Handoff overlap:** AD-016, TN-INT-SHELL-EDITORS-1

---

### TN-EDIT-SEM-8 — Dead sync `hover_provider` path mirrors removed completion provider

- **Persona:** TN-EDIT-SEM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_semantics.py:80-82` — `set_hover_provider` retained. `app/editors/code_editor_diagnostics.py:130-134` — sync `_hover_provider` fallback in tooltip event. `editor_tab_factory.py:168` wires **requester only**, never provider. Tests use provider (`tests/unit/editors/test_semantic_editor_interactions.py:163-165`).
- **Code-judo alternative:** Hard cutover: delete provider fields/setters; tests use requester stub + `show_hover_text_for_request`. Same cutover applied to completion provider (TN-INT-SHELL-EDITORS-5).
- **Suggested remediation:** Remove sync hover provider path; update unit tests to async requester pattern.
- **Tests that would prove fix:** `rg set_hover_provider` empty outside tests; factory wiring unchanged.
- **Handoff overlap:** AD-016, hard-cutover bias

---

### TN-EDIT-SEM-9 — `trigger_completion` calls popup prefix reuse with broker-incompatible heuristic

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:145-146` — while async work runs, `self._completion_popup.reuse_items_for_prefix(prefix)`. `app/editors/completion_popup/completion_controller.py:117-130` — filters with `item.label.lower().startswith(prefix.lower())`, a third prefix definition alongside `build_completion_context.prefix` and `compute_match_ranges` subsequence fuzzy (`completion_item_model.py:26-60`).
- **Code-judo alternative:** Reuse delegates to shell-delivered envelope slice or intelligence helper keyed by `context_fingerprint`; controller stores broker prefix object, not re-filtered label heuristic.
- **Suggested remediation:** Pass envelope fingerprint through `show_completion_items_for_request`; disable label-based reuse until broker-side filter exists, or reuse only lengthens prefix within same `valid_for` snapshot.
- **Tests that would prove fix:** Dotted-member typing retains correct subset during debounced semantic return; TN-INT-SHELL-EDITORS-7 regression closed.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-7, CC-05, TN-EDIT-COMP

---

### TN-EDIT-SEM-10 — Factory still embeds six per-tab intelligence closures

- **Persona:** TN-EDIT-SEM
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:95-169` — nested closures for completion, hover, signature, resolve, accept, plus text/cursor/breakpoint handlers capture `tab_file_path` and `editor_widget`. Acceptance now correctly routes workflow (`:158-161`), but each new intelligence callback still requires factory edits and duplicated capture pattern.
- **Code-judo alternative:** `EditorTabWorkflow.attach_intelligence_bindings(file_path, editor_widget)` returns wired callbacks; factory stays materialization-only. Pairs with TN-EDIT-SHELL-FACTORY critic.
- **Suggested remediation:** Move closure block to workflow module; factory calls one attach method.
- **Tests that would prove fix:** Single test on attach verifies all requesters delegate to navigation/completion workflows with correct `file_path`.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-8, TN-EDIT-SHELL-FACTORY, AD-016

---

### TN-EDIT-SEM-11 — AD-018 generation gating present on async paint; acceptance ungated (acceptable)

- **Persona:** TN-EDIT-SEM
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_semantics.py:237-238,253-254,266-267` — `show_completion_items_for_request`, `show_hover_text_for_request`, `show_calltip_for_request` compare `request_generation` before mutating UI. Shell adds revision gate via `deliver_revision_gated_editor_result` (`editor_completion_workflow.py:38-47`). `_insert_completion_from_item` fires `_completion_accepted_callback` after local insert (`:375-376`) with no revision check — records acceptance on worker asynchronously, not a stale paint risk.
- **Code-judo alternative:** No change required for acceptance; optional pass `buffer_revision` into acceptance record for session dedupe telemetry.
- **Suggested remediation:** Document as intentional; defer revision on acceptance unless broker needs it for cache invalidation.
- **Tests that would prove fix:** Existing stale-result tests for completion/hover deliver; acceptance test confirms worker queue not UI mutation.
- **Handoff overlap:** AD-018

---

## Cross-cutting notes

| Theme | Status in TN-EDIT-SEM slice |
|-------|----------------------------|
| AD-016 session boundary | **Requests + acceptance** route workflow → session worker. **Context classification** still duplicated in editor (`build_completion_context`) — presentation layer owns broker policy. |
| AD-018 revision gate | **Applied** on async completion/hover/signature paint via generation + shell revision gate. Outline out of slice scope. |
| §17.4.2 tier separation | Tier headers injected in shell merge (`completion_merge_policy.flatten_tiered_items`); editor skips headers on accept (`is_tier_header_item`). Delegate paints headers as normal rows — TN-EDIT-COMP scope. |
| Gate 8 intelligence imports | **Violated** in semantics (`completion_context`, `completion_merge_policy`). Diagnostics/semantics correctly use `diagnostics_service` + `completion_models` presentation types. |
| Mixin composition §12.4 | Editing mixin clean; semantics mixin overloaded (completion + editing keys + context build). |
| 1k-line rule | All three scoped files well under 1k (376/250/137). |
| Prior TN-INT blockers 1, 2, 5 | **Resolved** at this baseline. |
| Prior TN-INT 6, 10 | **Still open.** |

**Approval bar for this slice:** Prior wave blockers on prefix fork and UI-thread acceptance are cleared — material progress. **REJECT** for thermo-clean semantics boundary because the editor still executes broker context policy (`build_completion_context`), retains cast/shim/dead-helper debt, splits hover ownership, and couples editing keyboard policy into the semantics mixin. **`CodeEditorEditingMixin` alone would APPROVE** — no intelligence imports, pure transforms, clear API.

---

*End of TN-EDIT-SEM. Integration rollup: pending [`TN-EDIT-INTEG.md`](TN-EDIT-INTEG.md). Prior wave reference: [`TN-INT-SHELL-EDITORS.md`](../../intelligence-wave-1/_findings/TN-INT-SHELL-EDITORS.md).*
