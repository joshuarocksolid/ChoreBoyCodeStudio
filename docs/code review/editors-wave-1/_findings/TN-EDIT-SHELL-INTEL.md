# TN-EDIT-SHELL-INTEL — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SHELL-INTEL  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/shell/editor_intelligence_controller.py` (259 LOC), `app/shell/editor_completion_workflow.py` (313 LOC), `app/shell/inline_intelligence_workflow.py` (206 LOC), `app/shell/editor_stale_result_policy.py` (54 LOC), `app/shell/semantic_navigation_workflow.py` (132 LOC, editor paths only), `app/shell/semantic_navigation_host.py` (232 LOC). Cross-read: `app/intelligence/semantic_session.py`, `app/intelligence/completion_merge_policy.py`, `app/shell/editor_tab_factory.py` (acceptance closure). Gates: AD-016, AD-018, §17.4.2 tier merge, CC-02, CC-06, CC-10, prior TN-INT-SHELL-EDITORS acceptance path.

---

## Executive verdict

**REJECT — CC-06/CC-10 decomposition is real progress, but the shell intelligence lane is not thermo-clean yet.** `semantic_navigation_workflow.py` is now a 132-line coordinator (down from 1,103 LOC — CC-06 substantially closed at the nav monolith), and `editor_stale_result_policy.py` is the right canonical AD-018 helper. Dominant remaining risks in this slice: **(1) runtime introspection remains a third merge locus in `editor_completion_workflow.py`, orchestrating query inference, cache fetch, metadata attach, and tier merge beside broker/session** (AD-016 / CC-10); **(2) tier assembly is non-atomic across three callbacks mutating shared `runtime_items` / `fast_envelope[0]`** (CC-02 partial); **(3) AD-018 gating is inconsistent — completion uses revision + generation in the policy module, inline async delegates generation to editor paint methods, menu actions skip generation entirely**; **(4) `EditorIntelligenceController` is still mostly identity passthrough while completion workflow bypasses it for four direct `app.intelligence.*` imports**. TN-INT acceptance routing (TN-INT-SHELL-EDITORS-2) is **obsolete as a blocker** — acceptance now flows workflow → session worker. Would not approve further completion/runtime merge features in the shell until runtime tier feeds session/broker and all async editor intelligence paths share one gated deliver helper.

---

## Prior-wave re-validation (CC-02, CC-06, CC-10, TN-INT acceptance)

| Prior ID | Headline | Status at `042be49` | Notes |
|----------|----------|---------------------|-------|
| **CC-02** | §17.4.2 flat merge mislabels tiers | **PARTIAL** | `merge_completion_for_display` → `CompletionService.merge_for_editor_display` injects tier headers (`completion_merge_policy.py`). Shell still owns runtime tier fetch/attach before merge (`editor_completion_workflow.py:95-106,154-189`). Popup boundary still homogeneous (see [`TN-EDIT-COMP.md`](TN-EDIT-COMP.md)). |
| **CC-06** | `semantic_navigation_workflow.py` 1k+ monolith + inconsistent AD-018 gates | **PARTIALLY FIXED** | Nav workflow **132 LOC** — god module split into `EditorCompletionWorkflow`, `InlineIntelligenceWorkflow`, `SymbolNavigationWorkflow`, `SemanticRenameWorkflow`, `editor_stale_result_policy`. **Still open:** generation gating not applied uniformly (INTEL-3, INTEL-4). |
| **CC-10** | Shell bypasses controller — direct intelligence imports | **PARTIALLY FIXED** | `semantic_navigation_workflow.py` / `inline_intelligence_workflow.py` import no intelligence engines. **`editor_completion_workflow.py:9-18`** still imports `completion_context`, `completion_service`, `runtime_introspection` directly — CC-10 checklist fails for completion lane. |
| **TN-INT-SHELL-EDITORS-2** | Acceptance bypasses workflow / UI-thread session | **OBSOLETE (resolved)** | `editor_tab_factory.py:158-159` → `record_editor_completion_acceptance` → `editor_completion_workflow.py:49-52` → `request_record_completion_acceptance` → `semantic_session.py:84-95` (worker `priority=5`). AD-016 satisfied for acceptance. |
| **TN-INT-SHELL-EDITORS-5** | Dead sync `_completion_provider` | **OBSOLETE (resolved)** | No provider path in production wiring (see [`TN-EDIT-SEM.md`](TN-EDIT-SEM.md)). |

---

### TN-EDIT-SHELL-INTEL-1 — Runtime introspection is still the third merge locus (AD-016 / CC-10)

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_completion_workflow.py:95-106,154-189` — shell calls `resolve_runtime_introspection_query_with_inference`, `coordinator.cached_items` / `fetch_and_cache_from_runner`, `attach_replacement_metadata`, mutates `runtime_items`, then `intelligence_controller.merge_completion_for_display(...)`. Broker/session owns fast + semantic tiers only; runtime tier is assembled in shell beside the controller merge API. Mirrors TN-INT-INTEG CC-10 gate 4 (“runtime merge is third locus beside broker”).
- **Code-judo alternative:** Move runtime query inference + cache fetch + replacement attach into `SemanticSession.request_completion_with_runtime(...)` (or broker provider tier). Shell workflow passes `CompletionContext` once; receives a single gated envelope per phase from session callbacks. Deletes ~90 LOC of shell orchestration and the mutable `runtime_items` list.
- **Suggested remediation:** Session method returns `(fast_envelope, runtime_envelope, semantic_envelope)` or pre-merged display envelope; shell only gates and paints. Hard cutover — no shell-side `attach_replacement_metadata`.
- **Tests that would prove fix:** `rg "runtime_introspection" app/shell/editor_completion_workflow.py` empty; contract test: runtime items appear in `CompletionEnvelope.tiers` without shell merge calls.
- **Handoff overlap:** AD-016, CC-10, CC-02

---

### TN-EDIT-SHELL-INTEL-2 — Non-atomic tier merge across three async callbacks (CC-02)

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_completion_workflow.py:108-109,111-141,164-189,205-255` — shared mutable state: `runtime_items: list[CompletionItem]`, `fast_envelope: list[CompletionEnvelope | None] = [None]`. Three independent `on_success` handlers each call `merge_completion_for_display` and may repaint. Fast path can paint runtime-only merge before semantic arrives; introspection can repaint with partial fast; semantic path merges all three — order-dependent popup flicker and tier header duplication risk.
- **Code-judo alternative:** Session owns merge state machine: emit monotonic `CompletionDisplayRevision` per `(file_path, request_generation)`; shell delivers only the latest merged snapshot. Or single callback with phased envelope updates keyed by tier completion bitmap.
- **Suggested remediation:** Collapse to one merge owner (session) with internal fast/runtime/semantic latch; shell `_deliver_gated_completion_result` called once per logical paint generation.
- **Tests that would prove fix:** Simulated out-of-order fast/runtime/semantic callbacks → single paint with stable tier order; no duplicate tier headers in delivered items.
- **Handoff overlap:** CC-02, AD-018

---

### TN-EDIT-SHELL-INTEL-3 — Inline/menu paths omit generation from canonical stale policy (AD-018)

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_completion_workflow.py:38-47` — passes `requested_generation` + `current_generation=editor_widget.completion_request_generation()` to `deliver_revision_gated_editor_result`. Contrast `app/shell/inline_intelligence_workflow.py:49-56,98-105,142-149,186-193` — all four `deliver_revision_gated_editor_result` calls pass **revision only**; `requested_generation` / `current_generation` omitted despite allocating `request_generation` at `:30,83,127,175` and receiving `generation` in `on_success` payloads at `:35-36,88-89,133-134,177-178`.
- **Code-judo alternative:** Thin wrapper `_deliver_gated_inline_result(file_path, editor_widget, requested_revision, request_generation, deliver, *, kind="hover"|"signature")` mirroring completion workflow — one policy module, one contract.
- **Suggested remediation:** Pass generation into policy for all async inline paths; menu actions (`handle_*_action`) use `show_hover_text_for_request` / `show_calltip_for_request` with payload generation instead of ungated `show_calltip`.
- **Tests that would prove fix:** Unit test: inline hover delivery skipped when `hover_request_generation` advanced but revision unchanged (mirror `test_editor_completion_workflow.py` resolve gate).
- **Handoff overlap:** AD-018, CC-06

---

### TN-EDIT-SHELL-INTEL-4 — Three AD-018 gate patterns in one intelligence slice

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** Completion: policy module revision **and** generation (`editor_stale_result_policy.py:26-28`) plus editor double-check (`code_editor_semantics.py:237`). Inline async: policy revision-only; generation checked inside `show_hover_text_for_request` / `show_calltip_for_request` (`code_editor_semantics.py:253,266`). Menu inline: `handle_signature_help_action` / `handle_hover_info_action` call ungated `show_calltip` (`inline_intelligence_workflow.py:47,96`) — no generation parameter at all.
- **Code-judo alternative:** **Policy module owns all stale drops** before any editor paint method runs. Editor paint methods become dumb applicators; delete generation checks from semantics mixin for shell-delivered results (single gate locus).
- **Suggested remediation:** Align with CC-06 remediation plan: one gate, all async intelligence deliver paths. Document in ARCHITECTURE §17.4 AD-018 table.
- **Tests that would prove fix:** Matrix test across completion/hover/signature/menu: stale generation never reaches popup/tooltip paint APIs.
- **Handoff overlap:** AD-018, CC-06

---

### TN-EDIT-SHELL-INTEL-5 — `EditorIntelligenceController` passthrough does not close CC-10 for completion

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_intelligence_controller.py:45-92` — `request_completion_fast`, `request_completion`, `merge_completion_for_display` delegate to `SemanticSession` with no shell-facing consolidation. `request_completion_fast` types `on_success: Callable[[object], None]` (`:51`) — erases `CompletionFastResult`. Workflow imports intelligence directly for context/runtime (`editor_completion_workflow.py:9-18`) while controller imports the same packages (`editor_intelligence_controller.py:6-22`). Two parallel facades for one lane.
- **Code-judo alternative:** Controller exposes `request_editor_completions(context, generation, callbacks)` absorbing context build + runtime tier + merge; workflow becomes gate-and-paint only (~80 LOC). Or delete controller and inject `SemanticSession` into workflows with typed port — pick one facade.
- **Suggested remediation:** Extend controller with runtime/context methods; remove direct intelligence imports from `editor_completion_workflow.py`. Tighten fast callback type to `CompletionFastResult`.
- **Tests that would prove fix:** `rg '^from app\.intelligence' app/shell/editor_completion_workflow.py` → no matches; pyright clean on controller callbacks.
- **Handoff overlap:** CC-10, AD-016

---

### TN-EDIT-SHELL-INTEL-6 — Duplicate `CompletionRequest` + `build_completion_context` field lists

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_completion_workflow.py:70-94` — parallel construction of `CompletionRequest(...)` and `build_completion_context(...)` with identical kwargs duplicated across 12 fields (`trigger_kind`, `trigger_character`, `buffer_revision`, etc.). Any broker context field added here requires two edits; drift already visible vs editor-side duplicate build (TN-EDIT-SEM-1).
- **Code-judo alternative:** `build_completion_context` returns `(context, request)` or session factory `completion_request_from_editor_snapshot(...)`. Single call site in workflow.
- **Suggested remediation:** Extract `build_completion_request_and_context(...)` in intelligence layer; workflow calls once.
- **Tests that would prove fix:** Field parity test: request and context always share fingerprint/revision/prefix.
- **Handoff overlap:** AD-016, CC-05

---

### TN-EDIT-SHELL-INTEL-7 — Prefix source splits between fast/runtime and semantic delivery paths

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_completion_workflow.py:108,131-132,179-180` — fast and runtime introspection deliver with `prefix=popup_prefix` from local `completion_context.prefix`. Semantic path at `:207-208,245-246` uses `completion_prefix = result.prefix` from worker result. If broker adjusts prefix between fast and semantic phases (import/member context refinement), popup prefix can change mid-request without reuse coherence.
- **Code-judo alternative:** Broker stamps authoritative `valid_for.prefix` on every envelope; all three deliver paths read `merged.valid_for.prefix` or `result.envelope.valid_for.prefix` — one prefix per request_generation.
- **Suggested remediation:** Use merged envelope `valid_for` for all paints; delete `popup_prefix` closure variable.
- **Tests that would prove fix:** Semantic slow path returns different prefix than context — UI still uses envelope authoritative prefix consistently.
- **Handoff overlap:** CC-02, CC-05, TN-INT-SHELL-EDITORS-7

---

### TN-EDIT-SHELL-INTEL-8 — Unused `prefix` parameter signals forked editor/shell contract

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_completion_workflow.py:54-66,97-108` — `request_editor_completions_async(..., prefix: str, ...)` receives `prefix` from editor trigger but never reads it; workflow recomputes via `build_completion_context`. `semantic_navigation_workflow.py:89-100` forwards the dead parameter.
- **Code-judo alternative:** Drop `prefix` from workflow signature; editor passes cursor snapshot only. Forces single context owner (shell/intelligence).
- **Suggested remediation:** Hard cutover signature change at factory closure + navigation coordinator.
- **Tests that would prove fix:** pyright flags removed param; no editor call passes prefix.
- **Handoff overlap:** AD-016, TN-EDIT-SEM-1

---

### TN-EDIT-SHELL-INTEL-9 — CC-06 win: thin navigation coordinator (keep, don't regress)

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE (positive)
- **Evidence:** `app/shell/semantic_navigation_workflow.py:25-132` — delegates to `_symbols`, `_inline`, `_rename`, `_completions`; no intelligence imports; 132 LOC vs prior 1,103 (`TN-INT-SHELL-NAV-1`). Editor paths (`record_editor_completion_acceptance`, `request_editor_completions_async`, inline async, resolve) are one-line forwards.
- **Code-judo alternative:** Maintain strict pass-through — resist re-inlining completion/runtime logic here during fixes (address INTEL-1/2 in `EditorCompletionWorkflow` or session instead).
- **Suggested remediation:** Add LOC budget test: `semantic_navigation_workflow.py` stays under 200 LOC.
- **Tests that would prove fix:** `wc -l app/shell/semantic_navigation_workflow.py` < 200; no new `app.intelligence` imports.
- **Handoff overlap:** CC-06, CC-10

---

### TN-EDIT-SHELL-INTEL-10 — `editor_stale_result_policy` is correct extraction; adoption incomplete

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_stale_result_policy.py:10-54` — pure policy with revision + optional generation; tested (`tests/unit/shell/test_editor_stale_result_policy.py`). Used by completion workflow and outline path (`editor_tab_workflow.py:283`). **Not** used with full parameter set by inline workflow (INTEL-3).
- **Code-judo alternative:** Workflow base mixin or shared `_EditorDeliverGate` host method wrapping policy with standard generation accessors per intelligence kind.
- **Suggested remediation:** Complete adoption per INTEL-3/4; avoid a fourth bespoke gate variant in future shell modules.
- **Tests that would prove fix:** All shell async editor intelligence modules call policy with generation where applicable.
- **Handoff overlap:** AD-018, CC-06

---

### TN-EDIT-SHELL-INTEL-11 — Menu vs async inline duplication in `InlineIntelligenceWorkflow`

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/inline_intelligence_workflow.py:18-69` vs `:120-162` (signature) and `:71-118` vs `:164-206` (hover) — near-identical snapshot gather, revision capture, session request, gated deliver; differs only in QMessageBox vs `show_*_for_request` and menu parent handling. ~120 LOC duplicated branching.
- **Code-judo alternative:** `_request_inline_intelligence(kind, *, menu: bool, ...)` with deliver strategy enum; menu and async share one implementation.
- **Suggested remediation:** Extract private `_run_inline_lookup(...)`; menu handlers call with `presentation="dialog"|"editor"`.
- **Tests that would prove fix:** Single code path covered by one parametrized unit test.
- **Handoff overlap:** CC-06, hard-cutover bias

---

### TN-EDIT-SHELL-INTEL-12 — `SemanticNavigationHost` remains `Any`-heavy 30-method protocol

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/semantic_navigation_host.py:10-113` — `dialog_parent`, `editor_manager`, `intelligence_controller`, `background_tasks`, `runtime_introspection_coordinator`, `problems_panel` return `Any`. `MainWindowSemanticNavigationHost` reaches through `_window._*` private fields (`:119-232`). Blocks typed `EditorIntelligenceController` port required by CC-10.
- **Code-judo alternative:** Split host into composable protocols: `EditorIntelligenceHost`, `SymbolNavigationHost`, `RenameHost` — intelligence workflows depend on narrow ports with typed controller return.
- **Suggested remediation:** Incremental: type `intelligence_controller() -> EditorIntelligenceController` first; defer rename/import-analysis ports to rename workflow slice.
- **Tests that would prove fix:** pyright on workflows with typed host stub; no `Any` on intelligence controller accessor.
- **Handoff overlap:** CC-10, R3

---

### TN-EDIT-SHELL-INTEL-13 — CC-02 closed at merge policy, not at shell orchestration boundary

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** STRUCTURAL
- **Evidence:** `app/intelligence/semantic_session.py:153-167` → `merge_for_editor_display` applies tier headers (`completion_merge_policy.py:23-73`). Shell repaints can still drop runtime tier on semantic-only merge if `runtime_items` list not yet populated (`editor_completion_workflow.py:208-212` passes whatever shell accumulated). §17.4.2 trust contract requires tier separation at **presentation** — popup still flat ([`TN-EDIT-COMP.md`](TN-EDIT-COMP.md)). Shell orchestration can merge tiers correctly then lose them at popup reuse.
- **Code-judo alternative:** Deliver immutable `CompletionDisplayEnvelope` snapshot to editor; popup model consumes `envelope.tiers` directly without shell-side list mutation between phases.
- **Suggested remediation:** Pair session-owned merge (INTEL-1/2) with popup tier view-model work (TN-EDIT-COMP); do not mark CC-02 closed until both land.
- **Tests that would prove fix:** `test_completion_merge_policy.py` + integration test: three-phase callback order → tier headers present at editor paint boundary.
- **Handoff overlap:** CC-02, §17.4.2

---

### TN-EDIT-SHELL-INTEL-14 — TN-INT acceptance path: obsolete blocker, keep as regression guard

- **Persona:** TN-EDIT-SHELL-INTEL
- **Severity:** NICE-TO-HAVE (positive closure)
- **Evidence:** `app/shell/editor_tab_factory.py:158-159` — `window._semantic_navigation_workflow.record_editor_completion_acceptance(file_path=..., item=...)`. `app/shell/editor_completion_workflow.py:49-52` — `request_record_completion_acceptance(item=item)` (ignores `file_path` but routes correctly). `app/intelligence/semantic_session.py:84-95` — worker-serialized `record_acceptance`. Prior TN-INT-SHELL-EDITORS-2 BLOCKER **closed**.
- **Code-judo alternative:** Add thin workflow test asserting factory never calls `_intelligence_controller.record_completion_acceptance` directly; optional: pass `buffer_revision` into acceptance for audit trail.
- **Suggested remediation:** Mark TN-INT-SHELL-EDITORS-2 **OBSOLETE** in integration rollup; keep one regression test on routing.
- **Tests that would prove fix:** Factory callback spy → workflow only; session queue invoked.
- **Handoff overlap:** AD-016, TN-INT-SHELL-EDITORS-2

---

## Cross-cutting gate checklist

| Gate | Status in TN-EDIT-SHELL-INTEL slice |
|------|-------------------------------------|
| AD-016 session boundary | **Partial** — requests/acceptance/merge API route through session; runtime tier fetch+attach still shell-owned (INTEL-1). Acceptance path **pass**. |
| AD-018 revision gate | **Partial** — canonical policy exists; completion uses full gate; inline/menu inconsistent (INTEL-3, INTEL-4). |
| §17.4.2 tier separation | **Partial** — merge policy injects headers; shell non-atomic merge + popup flat presentation (INTEL-2, INTEL-13; see TN-EDIT-COMP). |
| CC-02 | **PARTIAL** — data tier merge fixed; shell orchestration + popup boundary not. |
| CC-06 | **PARTIALLY FIXED** — nav monolith split; gate uniformity debt remains. |
| CC-10 | **PARTIALLY FIXED** — nav/inline clean; completion workflow direct imports remain. |
| 1k-line rule | **Pass** — largest scoped file 313 LOC (`editor_completion_workflow.py`). |
| TN-INT acceptance (EDITORS-2) | **OBSOLETE (resolved)** — document only; guard with test (INTEL-14). |

---

## Approval bar

**REJECT.** CC-06 decomposition and `editor_stale_result_policy` extraction are keepers — do not revert the coordinator split. Blockers for this slice: **runtime introspection third locus (INTEL-1)**, **non-atomic tier merge (INTEL-2)**, **AD-018 gate fragmentation (INTEL-3/4)**, **CC-10 completion-lane controller bypass (INTEL-5)**, **CC-02 not closable at shell boundary without session-owned merge + popup tier UI (INTEL-13)**. TN-INT acceptance routing is resolved (INTEL-14); treat as closed in integration rollup, not as open debt.

P0 for fix-agent: INTEL-1, INTEL-2, INTEL-3, INTEL-5. P1: INTEL-4, INTEL-6, INTEL-7, INTEL-13. P2: INTEL-8, INTEL-11, INTEL-12.

Integration rollup: pending [`TN-EDIT-INTEG.md`](TN-EDIT-INTEG.md). Prior wave reference: [`TN-INT-SHELL-NAV.md`](../../intelligence-wave-1/_findings/TN-INT-SHELL-NAV.md), [`TN-INT-SHELL-EDITORS.md`](../../intelligence-wave-1/_findings/TN-INT-SHELL-EDITORS.md).

---

*End of TN-EDIT-SHELL-INTEL.*
