# TN-INT-SHELL-EDITORS — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-SHELL-EDITORS  
**Date:** 2026-06-16  
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`  
**Scope:** `app/editors/code_editor_semantics.py` (349 LOC), `app/editors/code_editor_widget.py` intelligence wiring (755 LOC), `app/editors/code_editor_diagnostics.py` (137 LOC), `app/shell/editor_tab_factory.py` (214 LOC), `app/shell/editor_tab_workflow.py` outline + prefs hooks (937 LOC), `app/editors/completion_popup/` (controller, model, container, delegate, list view, docs panel, kind style). Cross-read: `app/shell/semantic_navigation_workflow.py` completion/outline paths, `app/shell/editor_intelligence_controller.py`, `app/intelligence/completion_context.py`, `app/intelligence/completion_providers.py`, `app/intelligence/outline_service.py`. Gates: AD-016, AD-018, `docs/ARCHITECTURE.md` §17.4.1–§17.4.3, §17.4.7–§17.4.8.

---

## Executive verdict

**Not thermo-clean — the editor layer re-implements completion context and acceptance on the wrong side of the session/workflow seam.** The split into `CodeEditorSemanticsMixin`, `CompletionController`, and shell callbacks is directionally right, but three AD-016/§17.4 contract leaks dominate: **(1) `code_editor_semantics` imports `extract_completion_prefix` from `completion_providers`, forked from `build_completion_context` used by the broker** — prefix gating and fallback insertion disagree with dotted-member/import contexts; **(2) completion acceptance is wired factory → controller, bypassing `semantic_navigation_workflow` and mutating broker state on the UI thread** (pairs with TN-INT-01-2 / TN-INT-02-2); **(3) outline refresh in `editor_tab_workflow` calls `build_outline_from_source` directly on the UI thread with a second cache path from navigation**, outside any serialized session and without AD-018 revision gating. Secondary debt: dead sync `_completion_provider` path, `TypeError`/`cast(Any)` requester shims, popup prefix filtering that diverges from broker prefix semantics, per-tab closure sprawl in `editor_tab_factory`, and hover dispatch split across diagnostics vs semantics mixins. Would not approve further editor intelligence surface growth without collapsing prefix/context into one broker-owned contract, routing acceptance through the workflow into the worker lane, and extracting a single outline coordinator.

---

### TN-INT-SHELL-EDITORS-1 — Editor imports `extract_completion_prefix`, bypassing `build_completion_context`

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** BLOCKER
- **Evidence:** `app/editors/code_editor_semantics.py:13,118,342` — imports and calls `extract_completion_prefix` for auto-trigger gating and fallback text removal on accept. `app/intelligence/completion_providers.py:80-87` — prefix is **last identifier segment only** (`_IDENTIFIER_PREFIX_PATTERN`). `app/intelligence/completion_context.py:190-211` — dotted-member context uses `_DOTTED_MEMBER_CONTEXT_PATTERN`, sets `prefix` to member segment after `.`, and `replacement_start=safe_position - len(prefix)`. Import contexts (`:144-188`) use line-scoped regex with different replacement ranges. Broker stamps ranges via `context.replacement_range` (`completion_broker.py:322-325`); shell attaches the same via `attach_replacement_metadata` (`runtime_introspection.py:266-267`). Editor fallback at `code_editor_semantics.py:342-345` deletes the wrong span when `replacement_*` is missing.
- **Code-judo alternative:** Delete the `completion_providers` import from editors entirely. Editor receives `(prefix, replacement_range)` from the shell callback that already built `CompletionContext`, or calls a thin `completion_context.prefix_and_range(source, cursor)` re-export owned by the broker package — one regex set, one truth. `_insert_completion_from_item` requires `replacement_start/end` on every item; broker/session must guarantee them before paint.
- **Suggested remediation:** Hard cutover: `trigger_completion` takes prefix/range from requester metadata returned synchronously or from last `show_completion_items_for_request` envelope. Remove identifier-only fallback deletion. Align `CompletionController.reuse_items_for_prefix` with the same prefix object, not a re-derived string.
- **Tests that would prove fix:** Parametrize `foo.bar|` and `from os import pa|` — editor deletes member/import prefix length matching broker context, not whole-line identifier tail. Regression when `replacement_*` omitted → accept is no-op + log, not wrong delete.
- **Handoff overlap:** AD-016, TN-INT-02, R4

---

### TN-INT-SHELL-EDITORS-2 — Completion acceptance bypasses workflow and hits broker on UI thread

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** BLOCKER
- **Evidence:** `app/shell/editor_tab_factory.py:158-159,164` — `on_completion_accepted` calls `window._intelligence_controller.record_completion_acceptance(item)` directly. Contrast completion **request** path: same factory wires `completion_requester` → `semantic_navigation_workflow.request_editor_completions_async` (`:104-114`). `app/shell/editor_intelligence_controller.py:37-38` — passthrough to `SemanticSession.record_completion_acceptance`. `app/intelligence/semantic_session.py:57-59` — mutates `CompletionService`/broker on caller thread. `app/editors/code_editor_semantics.py:348-349` — fires callback **after** local insert, with no revision/generation gate. §17.4.3 requires broker/session ownership on the worker lane (TN-INT-01-2, TN-INT-02-2).
- **Code-judo alternative:** Route acceptance through `semantic_navigation_workflow.record_editor_completion_acceptance(file_path, item, buffer_revision)` → session queues `record_acceptance` on worker at priority above hover. Editor callback becomes one line delegating to workflow; factory stops importing controller for acceptance. Optional: batch acceptance with debounce on worker.
- **Suggested remediation:** Move closure body to workflow method; session enqueues broker mutation. Drop direct `_intelligence_controller` reference from factory for acceptance.
- **Tests that would prove fix:** Factory/workflow test: accept callback invokes workflow, never controller directly. Stress: acceptance during in-flight `complete_semantic` — no broker dict corruption.
- **Handoff overlap:** AD-016, TN-INT-01-2, TN-INT-02-2

---

### TN-INT-SHELL-EDITORS-3 — Outline refresh lives in `editor_tab_workflow`, outside session and off-thread policy

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:17,234-258,377,436-437` — `refresh_outline_for_active_tab` synchronously calls `build_outline_from_source(source)` on the UI thread when debounce timer fires or tab changes. No `SemanticSession`, no worker, no AD-018 revision check — reads `editor_widget.toPlainText()` at refresh time only. `app/intelligence/outline_service.py:48-62` — tree-sitter walk + AST fallback; non-trivial work on large buffers. §17.4.3: semantic-adjacent structure work should not block Qt UI thread when a serialized lane exists.
- **Code-judo alternative:** Introduce `OutlineCoordinator` (or session method `request_outline(file_path, source, revision)`) scheduled on `SemanticWorker` at low priority (below completion). Panel updates only through revision-gated callback mirroring completion/hover. Editor workflow owns **when** to request (timer/tab), not **how** to parse.
- **Suggested remediation:** Extract outline build from `editor_tab_workflow` into intelligence session or dedicated outline worker task; gate UI apply with `buffer_revision` like `deliver_revision_gated_editor_result`.
- **Tests that would prove fix:** Edit buffer during slow outline task — stale symbols not applied. Timer coalesces; outline job keyed per `file_path`.
- **Handoff overlap:** AD-018, TN-INT-06, R5

---

### TN-INT-SHELL-EDITORS-4 — Two outline pipelines and caches diverge between tab workflow and navigation

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:253-254` — stores symbols in `outline_symbols_by_path()[file_path]`. `app/shell/semantic_navigation_workflow.py:365-370` — Go to Symbol path reads `outline_symbols_for_path`; on miss calls `build_outline_from_source` again and `set_outline_symbols_for_path`. Host adapters at `editor_tab_workflow.py:771-772` vs `semantic_navigation_workflow.py:1026-1030` — same underlying dict but **different accessor methods** and independent miss paths. Outline panel fed only from tab workflow refresh; navigation can rebuild without updating panel cache timing.
- **Code-judo alternative:** One `OutlineCache` module keyed by `(file_path, buffer_revision)` with single `ensure_outline(file_path, source, revision)` entry. Tab workflow and navigation both call it; panel subscribe is a view concern.
- **Suggested remediation:** Collapse duplicate `build_outline_from_source` call sites; delete navigation-side rebuild when tab workflow already maintains revision-aware cache.
- **Tests that would prove fix:** Open Go to Symbol after edit — uses same symbol tree as outline panel without second parse when revision matches.
- **Handoff overlap:** R5, TN-INT-06

---

### TN-INT-SHELL-EDITORS-5 — Dead sync `_completion_provider` path preserves a session bypass in the editor mixin

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:52-54,153-160` — when `_completion_requester` is None, `trigger_completion` calls `_completion_provider` synchronously and paints immediately. `app/shell/editor_tab_factory.py:162-166` — production wiring sets **requester only**, never provider. `rg set_completion_provider` — no shell caller. Tests/console could wire provider and skip session, broker merge, revision gates, and degradation metadata entirely.
- **Code-judo alternative:** Delete sync provider path and `set_completion_provider`. Editor always requires async requester wired from shell; REPL/console keep their own stack per §17.4.8. Cuts ~15 LOC and removes a whole completion mode from the mental model.
- **Suggested remediation:** Hard cutover remove provider fields from widget + semantics mixin; update any test doubles to use requester stub.
- **Tests that would prove fix:** `rg _completion_provider` empty in `app/editors/`; editor completion tests use requester mock only.
- **Handoff overlap:** AD-016, §17.4.8

---

### TN-INT-SHELL-EDITORS-6 — `TypeError`/`cast(Any)` requester shim hides evolving completion contract

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_semantics.py:130-148,200-212` — `requester = cast(Any, self._completion_requester)` with `try/except TypeError` to support 5-arg vs 7-arg signatures. Factory always passes 7-arg closure (`editor_tab_factory.py:95-114`). `_request_completion_with_metadata` duplicates the same shim (`:187-212`) but appears **unused** in the mixin (no callers in file). This is incidental branching in `keyPressEvent`'s hot path.
- **Code-judo alternative:** Type the requester once as the 7-arg contract (trigger_kind, trigger_character). Delete `_request_completion_with_metadata` and the `TypeError` branch. If backward compat is needed, normalize at shell wiring boundary, not inside editor key handling.
- **Suggested remediation:** Single typed `CompletionRequester` Protocol in `completion_models.py`; pyright on editors proves no `cast(Any)`.
- **Tests that would prove fix:** pyright clean on `code_editor_semantics.py`; remove dead `_request_completion_with_metadata`.
- **Handoff overlap:** R4

---

### TN-INT-SHELL-EDITORS-7 — Popup prefix reuse diverges from broker prefix semantics

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/completion_popup/completion_controller.py:116-129` — `reuse_items_for_prefix` filters with `item.label.lower().startswith(prefix.lower())`. `app/editors/code_editor_semantics.py:127` — passes prefix from `extract_completion_prefix` (identifier tail). Broker ranks/filter on `CompletionContext.prefix` (member/import/dotted). `completion_item_model.py:26-60` — `compute_match_ranges` adds a **third** prefix matching strategy (subsequence fuzzy). Three prefix definitions in one popup refresh cycle.
- **Code-judo alternative:** Popup model stores the broker-issued `CompletionContext.prefix` (or full valid_for object) at `set_items` time; reuse calls broker-side `filter_items_for_prefix(envelope, new_prefix)` or reuses cached envelope slice — no label.startswith heuristic in UI layer.
- **Suggested remediation:** Pass context fingerprint + prefix from shell through `show_completion_items_for_request`; controller reuse delegates to intelligence helper.
- **Tests that would prove fix:** Dotted member typing keeps correct subset when async semantic returns; label that doesn't start with member prefix but matches insert_text is not dropped incorrectly.
- **Handoff overlap:** TN-INT-02, R4

---

### TN-INT-SHELL-EDITORS-8 — `editor_tab_factory` embeds per-tab intelligence closures instead of workflow-owned bindings

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:95-175` — six nested closures (`completion_requester`, `hover_requester`, `signature_requester`, `completion_resolve_requester`, `on_completion_accepted`, cursor/text handlers) capture `tab_file_path` and `editor_widget`. Each new intelligence callback requires editing factory **and** duplicating file_path/editor_widget capture pattern already repeated in `semantic_navigation_workflow` method signatures (`request_editor_completions_async`, etc.). Factory imports `CompletionItem` and reaches `_intelligence_controller` directly for acceptance (TN-INT-SHELL-EDITORS-2).
- **Code-judo alternative:** `EditorTabWorkflow.attach_intelligence_bindings(file_path, editor_widget) -> EditorIntelligenceBindings` returns wired callbacks; factory calls one method. Acceptance, resolve, and async requests share one object stored on workflow host.
- **Suggested remediation:** Move closure block to workflow; factory stays materialization-only (widget create, theme, tab add).
- **Tests that would prove fix:** Single test on `attach_intelligence_bindings` verifies all requesters delegate to navigation workflow with correct file_path.
- **Handoff overlap:** R5, AD-016

---

### TN-INT-SHELL-EDITORS-9 — Editor paints shell-merged completion tiers with no tier awareness

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/semantic_navigation_workflow.py:535-557,581-585` — merges `complete_fast` envelope with runtime introspection items via `_merge_completion_items` before `editor_widget.show_completion_items_for_request`. Editor popup (`completion_controller.py:102-106`, `completion_item_model.py`) renders a **flat** list with kind glyphs only — no section headers for approximate vs semantic vs runtime (§17.4.2). `code_editor_semantics.py:214-227` — applies items blindly when generation matches; no degradation surfacing at editor boundary.
- **Code-judo alternative:** Broker owns merge policy and tier structure; editor popup accepts `CompletionPresentation(tiers=[...])` or renders `CompletionItem.tier` / mandatory section breaks. Shell stops merging outside broker — runtime introspection feeds broker as another provider tier.
- **Suggested remediation:** Extend `CompletionItemModel.set_items` to accept tier boundaries; navigation workflow passes broker envelope unchanged. Pair with TN-INT-02-1 broker tier work.
- **Tests that would prove fix:** Popup model row count includes section headers; approximate+semantic merge shows two labeled sections in UI contract test (manual acceptance doc update).
- **Handoff overlap:** §17.4.2, TN-INT-02-1, R4

---

### TN-INT-SHELL-EDITORS-10 — Hover dispatch split across diagnostics and semantics mixins

- **Persona:** TN-INT-SHELL-EDITORS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_diagnostics.py:109-136` — `event(QEvent.ToolTip)` dispatches diagnostic tooltips, then `_hover_requester` / `_hover_provider`. `app/editors/code_editor_semantics.py:74-88,236-247` — owns hover requester setters and `show_hover_text_for_request` but not tooltip event entry. `CodeEditorWidget` MRO: `CodeEditorDiagnosticsMixin` before `CodeEditorSemanticsMixin` (`code_editor_widget.py:53-60`) — hover policy lives in diagnostics file while completion/hover request state is split across both mixins (`_hover_request_generation` duplicated in TYPE_CHECKING stubs for both).
- **Code-judo alternative:** Move all semantic tooltip orchestration into `CodeEditorSemanticsMixin.event` (or shared `CodeEditorTooltipsMixin`); diagnostics mixin returns diagnostic tooltip text only via helper, no hover requester calls.
- **Suggested remediation:** Single mixin owns `_hover_request_generation` and tooltip event; diagnostics contributes range lookup only.
- **Tests that would prove fix:** Characterization: diagnostic range wins over hover when overlapping; one generation counter incremented.
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| AD-016 session boundary | Completion **requests** go workflow → controller → session; **prefix**, **acceptance**, and **outline** bypass the lane |
| AD-018 revision gate | Applied on async completion deliver in navigation workflow; **not** on outline refresh or acceptance |
| §17.4.2 tier separation | Shell merges before editor paint; popup is flat (TN-INT-SHELL-EDITORS-9) |
| 1k-line rule | `editor_tab_workflow.py` at 937 LOC with outline+indent+tab logic — next hook risks crossing 1k (TN-INT-SHELL-EDITORS-3) |
| Code-judo target | One context contract (broker), one workflow binding site, one outline coordinator — deletes provider import, sync path, duplicate outline builds, and factory closure sprawl |

**Approval bar:** Block on TN-INT-SHELL-EDITORS-1 and TN-INT-SHELL-EDITORS-2 before adding editor-side intelligence imports or popup features. Outline consolidation (TN-INT-SHELL-EDITORS-3/4) should ride with session/worker work, not defer as cosmetic.
