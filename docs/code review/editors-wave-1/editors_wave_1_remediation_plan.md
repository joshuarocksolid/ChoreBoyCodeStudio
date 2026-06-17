# Editors Wave 1 — Remediation Plan (Phase 2)

Status: ready for implementation approval  
Implementation plan: [`editors_wave_1_implementation_plan.md`](editors_wave_1_implementation_plan.md)  
Baseline: `042be49e5777c587391ddbb396b7ea150e296dfe`  
Source review: [`editors_wave_1_thermo_review_2026-06-17.md`](editors_wave_1_thermo_review_2026-06-17.md)  
Integration themes: [`_findings/TN-EDIT-INTEG.md`](_findings/TN-EDIT-INTEG.md)

**Do not start implementation until this plan is approved.** Phase 1 (document-only review) is complete.

---

## Goals

1. Close all **P0** themes CC-EDIT-01, CC-EDIT-04, CC-EDIT-05, CC-EDIT-09, CC-EDIT-10, CC-EDIT-12, CC-EDIT-14 before declaring editors thermo-clean.
2. Decompose `editor_tab_workflow.py` below 200 LOC facade (CC-EDIT-01 / 1k rule).
3. Establish **single completion context owner** — not in `app/editors/` (CC-EDIT-04 / AD-016).
4. Fix §17.4.2 tier presentation at popup boundary — headers survive prefix reuse (CC-EDIT-05 / CC-02).
5. Move runtime introspection merge into session/broker; shell gate-and-paint only (CC-EDIT-09 / CC-10).
6. Wire poll to `ProjectInventoryOrchestrator`; stop `cbcs/cache/` signature churn (CC-EDIT-10 / CC-PROJ-13).
7. Unify tab/disk text authority through `EditorManager` (CC-EDIT-12).
8. Scope project replace-all to capped match tuples only (CC-EDIT-14).

---

## Non-negotiable rules (every PR)

- Hard cutover importers; no long-lived parallel completion/search/poll modes.
- Python 3.9 syntax; no dot-prefixed runtime paths.
- `editor_tab_workflow.py` method count must not grow during decomposition — extract, do not wrap.
- Factory materializes widgets only; intelligence bindings attach from workflow.
- One `build_completion_context` per completion request — shell workflow sole owner.
- Tier headers must survive prefix reuse and render as non-selectable section UI.
- Replace-all edits only spans from displayed `SearchMatch` tuples.
- Poll compares orchestrator generation/fingerprint — no per-tick `enumerate_project_entries` when stable.
- Format/save reads `EditorManager` first; widget is projection.
- UI-touching PRs record four-theme validation (Light, Dark, HC Light, HC Dark) or document gap.
- Tests only when risk-first gate applies: tier reuse, replace scope, AD-018 stale matrix, poll walk count, tab/disk SSOT.

---

## Wave 0 — Contracts + test scaffolding

**Blocks:** CC-EDIT-04 (partial), CC-EDIT-05 (partial), CC-EDIT-14 (partial), CC-EDIT-08 (partial)

**Goal:** Named contracts and failing/skeleton tests before behavior moves.

### Step 0.1 — Completion requester protocol

**Files:** `app/editors/code_editor_semantics.py`, `app/shell/editor_completion_workflow.py`, new `app/shell/editor_completion_contracts.py` (or `app/intelligence/completion_contracts.py`)

**Work:**
1. Define `CompletionRequester` Protocol with typed 7-arg signature.
2. Document single context owner: workflow builds `CompletionContext`; editor receives prefix/range metadata only.
3. Plan deletion of dead `prefix` param on workflow entry.

**Gate:** Types/docs only until Wave 2a.

### Step 0.2 — Tier row metadata contract

**Files:** `app/editors/completion_popup/completion_item_model.py`, tests under `tests/unit/editors/completion_popup/`

**Work:**
1. Add `row_kind: header | item` (or equivalent) to popup view model.
2. Parametrize test: tier headers + items → model preserves header rows after prefix lengthen.

**Gate:** Test scaffold exists; may fail until Wave 3a.

### Step 0.3 — Replace-scope fixture

**Files:** `tests/unit/editors/test_search_panel.py` or new `test_search_replace_scope.py`

**Work:**
1. Fixture: file with 10 matches, UI cap 3 → `replace_in_files` must edit exactly 3 spans.
2. Document CC-EDIT-14 blocker with failing test.

**Gate:** Failing test documents blocker until Wave 5a.

### Step 0.4 — AD-018 gate matrix

**Files:** `docs/ARCHITECTURE.md` §17.4.7, `tests/unit/shell/test_editor_stale_result_policy.py`

**Work:**
1. Document required `(revision, generation)` gates per surface: completion, inline, menu, outline, search.
2. Extend stale-policy tests for inline/menu generation omission cases.

**Gate:** Doc + expanded test matrix; behavior fix in Wave 3c.

---

## Wave 1 — Tab workflow 1k decomposition (R3)

**Blocks:** CC-EDIT-01, CC-EDIT-07 (partial), CC-EDIT-17 (partial)

**Goal:** Split `editor_tab_workflow.py` without growing `MainWindow` method count.

### Step 1.1 — Extract sub-workflows

**Files:** New `app/shell/editor_tab_outline_workflow.py`, `editor_tab_poll_workflow.py`, `editor_tab_preferences_workflow.py`, `main_window_editor_tab_host.py`

**Work:**
1. Move outline debounce/refresh to outline workflow.
2. Move poll/signature/rescan to poll workflow.
3. Move zoom/prefs/indent hooks to preferences workflow.
4. Move 195-line host adapter to dedicated host module.

**Gate:** `wc -l app/shell/editor_tab_workflow.py` ≤ 200.

### Step 1.2 — Host protocol slice

**Files:** `editor_tab_workflow.py`, `editor_tab_factory.py`

**Work:**
1. Split `EditorTabWorkflowHost` into sub-protocols (outline, poll, tabs, markdown).
2. Factory calls `attach_editor_bindings` on workflow — not nested closures.

**Gate:** Each protocol ≤ 15 methods; TN-INT-8 closure count zero in factory.

### Step 1.3 — Markdown registry

**Files:** New `app/shell/markdown_tab_registry.py`, `editor_tab_workflow.py`, `project_tree_ui_workflow.py`

**Work:**
1. Single `release_editor_widget` / unwrap implementation.
2. Shared registry for code vs markdown panes.

**Gate:** One registry module; duplicate unwrap deleted.

---

## Wave 2 — AD-016 editor/intelligence boundary (R3)

**Blocks:** CC-EDIT-04, CC-EDIT-03, CC-EDIT-09, CC-EDIT-07

**Goal:** Editors paint; session/workflow owns semantic policy.

### Step 2.1 — Remove context build from editor

**Files:** `app/editors/code_editor_semantics.py`, `app/shell/editor_completion_workflow.py`

**Work:**
1. Delete `build_completion_context` import and calls from semantics mixin.
2. Editor trigger passes cursor/file only; workflow returns synchronous prefix/range metadata envelope.
3. Delete intelligence imports from `app/editors/` for `completion_context`.

**Gate:** `rg completion_context app/editors/` empty.

### Step 2.2 — Runtime tier into session

**Files:** `app/shell/editor_completion_workflow.py`, `app/intelligence/semantic_session.py`, `app/intelligence/completion_broker.py`

**Work:**
1. Move runtime fetch/attach/merge into session/broker.
2. Shell workflow gate-and-paint only.

**Gate:** `rg runtime_introspection app/shell/editor_completion_workflow.py` empty.

### Step 2.3 — Factory attach extraction

**Files:** `app/shell/editor_tab_factory.py`, `app/shell/editor_tab_workflow.py`

**Work:**
1. Move six nested closures to `EditorTabWorkflow.attach_editor_bindings`.
2. Factory ≤ 60 LOC orchestration (materialize + register).

**Gate:** `rg "def on_" app/shell/editor_tab_factory.py` intelligence closures → zero.

### Step 2.4 — Relocate latency tracker

**Files:** `app/editors/code_editor_widget.py`, new `app/core/metrics.py` or `app/support/latency_tracker.py`

**Work:**
1. Move `RollingLatencyTracker` out of intelligence package.
2. Widget imports neutral metrics module.

**Gate:** `rg latency_tracker app/editors/` empty.

---

## Wave 3 — Tier popup + AD-018 gates (CC-02)

**Blocks:** CC-EDIT-05, CC-EDIT-06, CC-EDIT-08, CC-EDIT-23

**Goal:** §17.4.2 honored at popup; uniform stale gates.

### Step 3.1 — Tier-preserving reuse

**Files:** `app/editors/completion_popup/completion_controller.py`, `completion_item_delegate.py`, `completion_list_view.py`

**Work:**
1. Reuse preserves tier header rows or disable label reuse when tiers present.
2. Delegate paints headers as non-selectable section rows.
3. List view skips header selection on accept.

**Gate:** Prefix lengthen test: tier headers survive.

### Step 3.2 — Atomic session merge

**Files:** `app/shell/editor_completion_workflow.py`, `app/intelligence/semantic_session.py`

**Work:**
1. Single paint per `request_generation`; session-owned merge envelope.
2. Delete mutable `runtime_items` / `fast_envelope[0]` shared across callbacks.

**Gate:** Out-of-order callback test → one stable tier order.

### Step 3.3 — AD-018 uniformity

**Files:** `app/shell/inline_intelligence_workflow.py`, `app/shell/editor_stale_result_policy.py`, menu/hover paths

**Work:**
1. Inline/menu pass generation to `deliver_revision_gated_editor_result`.
2. Menu hover uses gated calltip delivery.

**Gate:** Stale generation matrix green for completion + inline + menu.

### Step 3.4 — Console completion parity

**Files:** `app/shell/python_console_widget.py`, completion popup modules

**Work:**
1. Console uses shared prefix/tier contract; delete console-only prefix helper.

**Gate:** Console tier headers honored.

### Step 3.5 — QuickOpen single model

**Files:** `app/editors/quick_open_dialog.py`

**Work:**
1. Replace `QStringListModel` + `_QuickOpenItemModel` with one `QAbstractListModel`.

**Gate:** Dialog refresh single sync point.

---

## Wave 4 — Tab/disk SSOT + session restore (R3)

**Blocks:** CC-EDIT-12, CC-EDIT-13, CC-EDIT-02, CC-EDIT-21 (partial)

### Step 4.1 — Manager-first buffer writes

**Files:** `app/editors/editor_manager.py`, `app/shell/save_workflow.py`, `app/shell/python_style_workflow.py`

**Work:**
1. Add `EditorManager.replace_tab_content`.
2. `_apply_text_to_open_tab` updates manager before widget.
3. Format-on-save reads manager, not widget `toPlainText()`.

**Gate:** Save-without-`textChanged` test green.

### Step 4.2 — Single disk sync path

**Files:** `app/shell/editor_tab_workflow.py`, `app/shell/editor_sync_workflow.py`

**Work:**
1. `refresh_open_tabs_from_disk` delegates to `EditorSyncWorkflow` only.

**Gate:** Zero inline `setPlainText` in tab workflow for disk refresh.

### Step 4.3 — Session restore draft policy

**Files:** `app/shell/editor_session_workflow.py`, `app/shell/editor_tab_workflow.py`

**Work:**
1. Session restore uses `open_file_in_editor(..., restore_draft=False)`.

**Gate:** Session round-trip cursor matches persisted state.

### Step 4.4 — Typed requester + mixin cleanup

**Files:** `app/editors/code_editor_semantics.py`, `code_editor_widget.py`

**Work:**
1. Delete `cast(Any)` / `TypeError` shim; use Protocol.
2. Move editing shortcuts from semantics `keyPressEvent` to editing mixin.
3. Extract paste-hint + overlay mixins; hub ≤ 650 LOC.

**Gate:** `wc -l code_editor_widget.py` ≤ 650; pyright clean semantics.

---

## Wave 5 — Search SSOT + replace fix (R4)

**Blocks:** CC-EDIT-14, CC-EDIT-15, CC-EDIT-16, CC-EDIT-08 (search), CC-EDIT-22 (partial)

### Step 5.1 — Scoped replace

**Files:** `app/editors/search_panel.py`, `app/shell/search_sidebar_widget.py`

**Work:**
1. Replace edits line/column spans from `SearchMatch` tuples only.
2. Reject replace when results truncated without explicit confirm.

**Gate:** Cap-3 replaces exactly 3 occurrences.

### Step 5.2 — Unified search compiler

**Files:** `app/editors/search_panel.py`, `app/editors/find_replace_bar.py`, `app/editors/code_editor_search.py`

**Work:**
1. Single `SearchPatternOptions` + `compile_search_pattern`.
2. Delete duplicate regex compilers and megabyte UI-thread literal scan.

**Gate:** One compiler in codebase.

### Step 5.3 — Exclude glob integration

**Files:** `app/editors/search_panel.py`, `app/project/file_excludes.py`

**Work:**
1. Fold UI globs into `EffectiveExcludes` pre-walk.

**Gate:** Parity with inventory matchers (CC-PROJ-01 facet).

### Step 5.4 — Search stale gate + shutdown

**Files:** `app/shell/search_sidebar_widget.py`, shutdown hooks

**Work:**
1. Generation token on worker callback.
2. Cancel `SearchWorker` on shutdown.

**Gate:** Rapid double-query test green.

### Step 5.5 — Dead search coordinator deletion

**Files:** `app/shell/diagnostics_search_coordinator.py`

**Work:**
1. Delete unwired `SearchResultsCoordinator`.

**Gate:** `rg SearchResultsCoordinator app/` empty.

---

## Wave 6 — Poll/inventory + outline + markdown + syntax (R4 + R3)

**Blocks:** CC-EDIT-10, CC-EDIT-11, CC-EDIT-17, CC-EDIT-19, CC-EDIT-20, CC-EDIT-18

### Step 6.1 — Poll orchestrator consumer

**Files:** `app/shell/editor_tab_poll_workflow.py`, `app/shell/project_inventory_orchestrator.py`

**Work:**
1. Poll compares orchestrator generation/fingerprint.
2. Drop per-tick `enumerate_project_entries`.

**Gate:** Stable tree → zero walks per poll tick.

### Step 6.2 — Signature alignment

**Files:** `app/shell/project_tree_utils.py`, poll workflow

**Work:**
1. Align signature with intelligence Python set; ignore `cbcs/cache/` churn.

**Gate:** Cache-only write → no rescan.

### Step 6.3 — Outline coordinator

**Files:** New outline coordinator or session method, `editor_tab_outline_workflow.py`, `symbol_navigation_workflow.py`

**Work:**
1. Single async outline entry; revision-keyed cache.
2. Go-to-Symbol never sync-parses on UI thread.

**Gate:** Edit during slow outline → stale symbols not applied.

### Step 6.4 — Markdown mode SSOT

**Files:** `app/shell/markdown_tab_registry.py`, `markdown_editor_pane.py`

**Work:**
1. Rename unwrap; wire `mode_changed`; theme pane chrome.

**Gate:** `.md`→`.txt` single widget; four-theme pane chrome.

### Step 6.5 — Syntax package neutralization

**Files:** `app/editors/syntax_registry.py`, `app/treesitter/highlighter_core.py`, `app/shell/theme_tokens.py`

**Work:**
1. Break editors↔treesitter import cycle.
2. Collapse triplicate token maps; wire or delete dead HC palette flag.

**Gate:** Import cycle test green.

### Step 6.6 — Extract flat-Python repair

**Files:** `app/editors/text_editing.py`, new `app/editors/flat_python_indent_repair.py`

**Work:**
1. Extract ~380 LOC repair engine.

**Gate:** `wc -l text_editing.py` ≤ 200.

### Step 6.7 — Four-theme token pass

**Files:** bracket mixin, paste hint, completion delegate, markdown pane, quick-open, search delegate

**Work:**
1. Replace hardcoded hex / `is_dark` collapse with `ShellThemeTokens`.

**Gate:** Manual HC Light/Dark acceptance recorded.

---

## Intelligence / Project SSOT convergence

| Editors wave | Upstream prerequisite |
|--------------|----------------------|
| Wave 2b | Intelligence CC-10 runtime/session cutover |
| Wave 3 | Intelligence CC-02 popup boundary |
| Wave 6a–6b | Project CC-PROJ-03 orchestrator exists — wire consumer only |
| Wave 5.3 | Project CC-PROJ-01 exclude parity |

Do not rebuild inventory or classifier policy in editors remediation — consume Project SSOT artifacts.

---

## Program complete when

1. All P0 CC-EDIT-01 … CC-EDIT-14 closed with evidence.
2. `editor_tab_workflow.py` ≤ 200 LOC.
3. `rg completion_context app/editors/` empty.
4. `rg runtime_introspection app/shell/editor_completion_workflow.py` empty.
5. Tier header reuse test green in four themes.
6. Poll stable-tree walk count = 0 per tick.
7. Replace cap test green.
8. `python3 testing/run_test_shard.py fast` + `npx pyright` green.
9. P1 themes CC-EDIT-02 … CC-EDIT-23 closed or explicitly backlog-waived.

---

## Deferred / backlog (P2)

- CC-EDIT-18 four-theme hex cleanup where not covered in 6.7.
- CC-EDIT-22 dead-path sweep (`SearchResultsCoordinator`, sync hover provider, dead helpers).
- R6 full test audit — only risk-first gaps listed in Wave 0.
