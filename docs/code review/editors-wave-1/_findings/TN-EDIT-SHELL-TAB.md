# TN-EDIT-SHELL-TAB — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SHELL-TAB  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/shell/editor_tab_workflow.py` (1,013 LOC), `app/shell/editor_tab_bar.py` (55 LOC), `app/shell/editor_tabs_coordinator.py` (75 LOC). Cross-read: `app/shell/project_rescan_workflow.py`, `app/shell/project_inventory_orchestrator.py`, `app/intelligence/outline_service.py`, `app/shell/symbol_navigation_workflow.py`, `app/shell/semantic_navigation_host.py`, `app/shell/editor_stale_result_policy.py`, `tests/unit/shell/test_editor_tab_workflow_inventory.py`, `tests/unit/shell/test_project_tree_refresh_state.py`. Gates: AD-018 revision gating, R4 inventory SSOT, 1k-line rule, four-theme markdown seam (TN-EDIT-MD), hard-cutover bias.

---

## Executive verdict

**REJECT — `editor_tab_workflow.py` crossed the 1k presumptive blocker at 1,013 LOC and absorbed debt that Intelligence Wave 1 shed from `semantic_navigation_workflow`.** Credible partial extractions exist (`EditorTabsCoordinator`, `MiddleClickTabBar`, `deliver_revision_gated_editor_result` on async outline deliver, light poll tier via `rescan_project_from_disk(reload_plugins=False, reindex=False)`), but the workflow module still owns six unrelated concerns (outline, markdown, tab lifecycle, editor prefs/zoom/indent, external poll, and a 195-line `MainWindowEditorTabHost` adapter) behind a 40-method `EditorTabWorkflowHost` protocol. Dominant risks: **no decomposition plan before the next tab hook**, **poll still re-walks the tree every second and bypasses `ProjectInventoryOrchestrator`**, **`cbcs/cache` signature churn still triggers rescans without Python-set change (TN-PROJ-SHELL-3)**, **sync UI-thread outline parse on Go-to-Symbol cache miss**, and **asymmetric tab teardown between preview eviction and user close**. `editor_tab_bar.py` is thermo-clean; the blocker is entirely the workflow god-module and its inventory/outline seams.

---

## Prior-wave re-validation

| Prior ID | Headline | Status at `042be49` | Notes |
|----------|----------|---------------------|-------|
| **TN-INT-SHELL-EDITORS-3** | Outline refresh outside session / UI-thread policy | **PARTIAL** | `refresh_outline_for_active_tab` (`:246-302`) schedules `build_outline_from_source` on `background_tasks` and gates panel apply via `deliver_revision_gated_editor_result` (AD-018). Not on `SemanticSession` worker lane. **Still open:** `flat_outline_symbols_for_path` (`:304-309`) parses synchronously on UI thread for Go-to-Symbol miss path. |
| **TN-INT-SHELL-EDITORS-4** | Two outline pipelines and caches diverge | **PARTIAL** | `semantic_navigation_workflow` no longer calls `build_outline_from_source`; `symbol_navigation_workflow.py:95` delegates to `flat_outline_symbols_for_path`. **Still open:** two parse triggers (debounced async refresh vs sync miss); dead `set_outline_symbols_for_path` on `SemanticNavigationHost` (`semantic_navigation_host.py:43,152`) with `list[object]` type erasure. |
| **TN-PROJ-SHELL-2** | Poll-driven reload performs three full traversals | **PARTIAL** | Poll no longer calls `reload_current_project()`; uses `rescan_project_from_disk(reload_plugins=False, reindex=False)` (`:787`) and conditional `start_symbol_indexing_for_loaded_project` on python fingerprint delta (`:786-790`). Tests in `test_editor_tab_workflow_inventory.py:42-94` lock this tier. **Still open:** 1 s `scan_project_tree_signature` → `enumerate_project_entries` walk (`:792-802`) plus `open_project` on mismatch (`project_rescan_workflow.py:58-61`); no shared snapshot reuse. |
| **TN-PROJ-SHELL-3** | Tree signature file set diverges from intelligence Python file set | **STILL OPEN** | `filter_tree_signature_entries` (`project_tree_utils.py:14-25`) strips only `cbcs/runs/` and `cbcs/logs/`, not `cbcs/cache/`. `test_editor_tab_workflow_inventory.py:58-65` asserts `cbcs/cache/state.json` in signature triggers light rescan while python fingerprint stable — intentional spurious rescan tier. Intelligence `iter_python_files` prunes all `cbcs/`. |
| **TN-PROJ-SHELL-12** | Poll reaches into `project_service` instead of inventory SSOT | **STILL OPEN** | `editor_tab_workflow.py:18,797-801` imports `enumerate_project_entries` from `app.project.project_service`. Orchestrator exists (`project_inventory_orchestrator.py`) but poll never reads `python_paths_fingerprint` or snapshot generation for structure detection. |

---

### TN-EDIT-SHELL-TAB-1 — `editor_tab_workflow.py` at 1,013 LOC is a presumptive 1k blocker

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** BLOCKER
- **Evidence:** `wc -l app/shell/editor_tab_workflow.py` → **1,013**. Module docstring claims "lifecycle, preferences, markdown, and external-change polling" but file also owns outline async, indent/editorconfig, zoom, context menus, and `MainWindowEditorTabHost` (`:805-999`). Intelligence CC-06 debt explicitly **moved** from slimmed `semantic_navigation_workflow` (132 LOC per manifest) into this file.
- **Code-judo alternative:** Hard decomposition before any new tab hook: `editor_tab_outline_workflow.py` (refresh + flat symbols + symbol activation), `editor_tab_poll_workflow.py` (signature + external poll), `editor_tab_preferences_workflow.py` (zoom/indent/editorconfig), `editor_tab_markdown_commands.py` (mode/actions only), `main_window_editor_tab_host.py` (adapter only). `EditorTabWorkflow` becomes a thin façade delegating to sub-workflows constructed in `build_editor_tab_workflow`.
- **Suggested remediation:** Land decomposition as first Editors Wave 1 shell slice; cap each extracted module ≤350 LOC; block feature additions to monolith until split merges.
- **Tests that would prove fix:** Import/smoke tests per sub-module; `wc -l editor_tab_workflow.py` ≤200 (facade only); existing `test_editor_tab_workflow_inventory.py` and tab lifecycle tests green.
- **Handoff overlap:** CC-02, Intelligence CC-06, CC-PROJ-13

---

### TN-EDIT-SHELL-TAB-2 — `EditorTabWorkflowHost` protocol sprawl hides real boundaries

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `EditorTabWorkflowHost` (`:26-207`) declares **40** host methods spanning editor prefs, outline, lint, local history, project rescan, symbol indexing, debug, and menu registry. `MainWindowEditorTabHost` (`:805-999`) is 195 lines of one-line `_window._*` pass-through with no grouping. Poll needs only ~8 host ports; markdown mode needs ~4; outline needs ~6 — all flattened into one protocol.
- **Code-judo alternative:** Split host protocols by sub-workflow (`EditorTabOutlineHost`, `EditorTabPollHost`, `EditorTabLifecycleHost`). `MainWindowEditorTabHost` composes them or delegates to existing window workflows instead of re-exporting private fields. Deletes the "add one method to protocol + adapter" tax on every shell feature.
- **Suggested remediation:** Extract adapters with the module split (TN-EDIT-SHELL-TAB-1); pyright `Protocol` per slice; forbid new methods on monolithic host.
- **Tests that would prove fix:** Fake host stubs per sub-protocol in unit tests; `EditorTabWorkflowHost` method count drops below 15 aggregate across protocols.
- **Handoff overlap:** CC-02, Intelligence CC-10

---

### TN-EDIT-SHELL-TAB-3 — Outline panel path is async + revision-gated; Go-to-Symbol miss path is still sync UI-thread parse

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** Async path: `refresh_outline_for_active_tab` (`:265-302`) — `background_tasks().run(key=f"outline::{file_path}", ...)` + `deliver_revision_gated_editor_result` (`:283-292`). Sync miss path: `flat_outline_symbols_for_path` (`:304-309`) — `symbols = build_outline_from_source(fallback_source or "")` on caller thread; invoked from `symbol_navigation_workflow.py:95` before `QuickSymbolDialog`. `on_error` swallows exceptions (`:294-295`, `_ = exc`).
- **Code-judo alternative:** Single `ensure_outline_async(file_path, source, revision, *, on_ready)` used by both outline panel timer and Go-to-Symbol; dialog opens with loading state or waits on cached revision. Delete sync `build_outline_from_source` from `flat_outline_symbols_for_path`; return cache-only or schedule shared async job keyed `outline::{file_path}`.
- **Suggested remediation:** Route Go-to-Symbol through same `background_tasks` key as panel refresh; gate dialog population with revision. Log outline failures at warning level.
- **Tests that would prove fix:** Edit buffer during Go-to-Symbol open — stale symbols not shown; large-file outline does not block Qt event loop (manual or perf threshold). Closes TN-INT-SHELL-EDITORS-3 residual.
- **Handoff overlap:** AD-018, TN-INT-SHELL-EDITORS-3, TN-INT-SHELL-EDITORS-4

---

### TN-EDIT-SHELL-TAB-4 — Outline cache has one dict but two parse entry points and dead host mutators

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** Storage: `main_window_composition.py:284` → `_outline_symbols_by_path`. Writers: `refresh_outline_for_active_tab` (`:273`) and `flat_outline_symbols_for_path` (`:308`). Readers: outline panel via refresh; `symbol_navigation_workflow.py:95` via host `flat_outline_symbols_for_path`. Dead API: `SemanticNavigationHost.set_outline_symbols_for_path` / `outline_symbols_for_path` (`semantic_navigation_host.py:40-43,149-153`) — no production caller after navigation refactor; types erased to `list[object]`.
- **Code-judo alternative:** One `OutlineCache` module: `get(file_path) -> tuple[OutlineSymbol, ...] | None`, `schedule_refresh(...)`, keyed by `(file_path, buffer_revision)`. Delete host outline getters/setters; navigation imports cache module only.
- **Suggested remediation:** Hard cutover remove dead host outline methods; consolidate parse scheduling. Pair with TN-EDIT-SHELL-TAB-3.
- **Tests that would prove fix:** `rg set_outline_symbols_for_path app/shell` — only test doubles; Go-to-Symbol and outline panel share one parse per revision (mock `build_outline_from_source` call count).
- **Handoff overlap:** TN-INT-SHELL-EDITORS-4, R5

---

### TN-EDIT-SHELL-TAB-5 — Poll tier improved but still performs independent tree walk every second

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `main_window_composition.py:555` — 1 s timer → `poll_external_file_changes`. Each tick: `scan_project_tree_signature` (`:778,792-802`) calls `enumerate_project_entries` full walk. On mismatch: `rescan_project_from_disk(reload_plugins=False, reindex=False)` (`:787`) → `open_project` second enumeration (`project_rescan_workflow.py:58-61`). `configure_search_sidebar` rebuilds `ProjectInventoryOrchestrator` (`project_rescan_workflow.py:108-114`) — third walk product. Python-only reindex gated separately (`:786-790`). Progress vs TN-PROJ-SHELL-2 baseline: no longer `reload_current_project()` with plugin reload + forced reindex.
- **Code-judo alternative:** Poll compares `ProjectInventoryOrchestrator.generation` or cheap snapshot fingerprint; structure change triggers one orchestrated `rebuild` whose product feeds tree, search, and fingerprint. Delete per-tick `enumerate_project_entries` when project loaded and generation stable.
- **Suggested remediation:** Wire poll to orchestrator generation counter; single rescan returns `(LoadedProject, OwnedProjectInventory)`. Extend `test_editor_tab_workflow_inventory.py` with stable-tree zero-walk assertion.
- **Tests that would prove fix:** Poll with unchanged tree ⇒ zero `enumerate_project_entries` calls; add `.py` file ⇒ one enumeration + one orchestrator rebuild total.
- **Handoff overlap:** TN-PROJ-SHELL-2, CC-PROJ-03, CC-PROJ-13, R4

---

### TN-EDIT-SHELL-TAB-6 — Tree signature still includes `cbcs/cache/`; metadata churn triggers rescans without Python change

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `project_tree_utils.py:14-25` — `PROJECT_TREE_SIGNATURE_IGNORED_PREFIXES` omits `cbcs/cache/`. `scan_project_tree_signature` (`:797-802`) materializes all filtered entries. `test_editor_tab_workflow_inventory.py:58-65` — signature delta `("main.py", "cbcs/cache/state.json")` calls `rescan_project_from_disk` while `project_python_paths_fingerprint` unchanged. `project_inventory_orchestrator.py:59-62` — intelligence fingerprint is `python_file_paths` only (excludes all `cbcs/`).
- **Code-judo alternative:** Derive poll fingerprint from `OwnedProjectInventory.snapshot` paths plus explicit manifest paths (`cbcs/project.json`), not full entry enumeration. Add `cbcs/cache/` to ignored prefixes **or** stop using tree signature for poll entirely.
- **Suggested remediation:** Align signature with intelligence file set per gate 3; update test to expect **no** rescan on cache-only churn once fixed.
- **Tests that would prove fix:** `cbcs/cache/index.bin` write during poll ⇒ no `rescan_project_from_disk`; new `.py` on disk ⇒ rescan once.
- **Handoff overlap:** TN-PROJ-SHELL-3, CC-PROJ-03, gate 3

---

### TN-EDIT-SHELL-TAB-7 — Poll imports `enumerate_project_entries` from `project_service`, not inventory SSOT surface

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** NICE-TO-HAVE
- **Evidence:** `editor_tab_workflow.py:18,797-801` — `from app.project.project_service import enumerate_project_entries`. `project_inventory_orchestrator.py` and `file_inventory.py` are the R4 canonical walk layer; `project_service` is load/open orchestration. `test_scan_project_tree_signature_calls_enumerate_without_type_error` (`test_editor_tab_workflow_inventory.py:97-110`) encodes current import path.
- **Code-judo alternative:** Preferred: delete poll-time enumeration (TN-EDIT-SHELL-TAB-5). Interim: import `iter_project_entries` from `file_inventory` only; deprecate shell `project_service` enumeration imports.
- **Suggested remediation:** Fold into poll/orchestrator refactor; add architectural grep rule: `app/shell/` must not import `enumerate_project_entries` from `project_service`.
- **Tests that would prove fix:** Import-layer test or `rg` gate clean after orchestrator poll lands.
- **Handoff overlap:** TN-PROJ-SHELL-12, R4, gate 1

---

### TN-EDIT-SHELL-TAB-8 — Tab close paths diverge: preview eviction vs user close leave different shell state

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** Preview eviction: `remove_tab_widget_for_path` (`:327-343`) — `removeTab`, `pop_editor`, `release_editor_widget`, pops `indent_source_by_path`, refresh save/run; **does not** `close_file` on `EditorManager`, clear breakpoints, lint diagnostics, or `outline_symbols_by_path`. User close: `handle_tab_close_requested` (`:548-580`) — unsaved decision, `close_file`, breakpoint clear, lint pop, problems panel; **does not** pop `indent_source_by_path` or `outline_symbols_by_path`. Caller: `editor_tab_factory.py:62` uses light path for preview replacement.
- **Code-judo alternative:** One `_teardown_tab(file_path, *, manager_close: bool, unsaved_prompt: bool)` internal method; both public entry points call it with flags. Guarantees symmetric cleanup of indent, outline, markdown (via `release_editor_widget`), lint, breakpoints.
- **Suggested remediation:** Extract shared teardown; add unit test both paths leave identical per-path dict state (empty keys).
- **Tests that would prove fix:** Close preview tab then open same path — no stale outline symbols or indent status; close user tab — indent/outline entries removed.
- **Handoff overlap:** TN-EDIT-MD-1, CC-02

---

### TN-EDIT-SHELL-TAB-9 — `reset_editor_tabs` omits outline, lint, and breakpoint caches

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `reset_editor_tabs` (`:590-616`) clears widgets, markdown panes, indent source, replaces `EditorManager`; called from `project_load_surface.py:37` on project open/switch. **Does not** clear `_outline_symbols_by_path`, `_stored_lint_diagnostics`, breakpoint store, or stop outline refresh timer. New project can inherit prior project's outline symbols until active tab refresh overwrites one path.
- **Code-judo alternative:** `reset_editor_tabs` calls `_teardown_all_tabs()` then explicit cache clears: `outline_symbols_by_path.clear()`, lint dict clear, `stop_outline_refresh_timer`, breakpoint store reset for all paths. Single atomic project-switch boundary.
- **Suggested remediation:** Add cache clears to reset; verify project switch does not flash wrong-file outline.
- **Tests that would prove fix:** Open project A, open Python tab, switch to project B — outline panel shows unsupported/empty until B's tab active, never A's symbols.
- **Handoff overlap:** AD-018, CC-02

---

### TN-EDIT-SHELL-TAB-10 — Markdown mode control triplicated in workflow without SSOT (pane toolbar / View menu / tab menu)

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `set_active_markdown_mode` + View actions (`:360-397`). Tab context menu (`:520-542`) calls `markdown_pane.set_mode(...)` directly with duplicate `MarkdownPreviewMode` constants instead of workflow helpers. `refresh_markdown_action_states` (`:383-397`) sets `setEnabled` only — no `setChecked` sync; `MarkdownEditorPane.mode_changed` not wired at factory (see TN-EDIT-MD-3). Three entry points for same mode transition.
- **Code-judo alternative:** Context menu invokes `set_active_markdown_mode` only; wire `mode_changed → refresh_markdown_action_states` at factory; menu actions mirror `pane.mode()` checked state. Delete inline `set_mode` branches in context menu.
- **Suggested remediation:** Collapse to one command path in `editor_tab_workflow`; extend refresh to checked state.
- **Tests that would prove fix:** Toggle from pane toolbar updates View menu checks; context menu "Show Split" uses same code path as View action.
- **Handoff overlap:** TN-EDIT-MD-3, four-theme seam

---

### TN-EDIT-SHELL-TAB-11 — Inconsistent `file_path` key normalization across widget lookups

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** Resolved keys: `refresh_outline_for_active_tab` (`:261-262`), `open_file_at_line` (`:317-318`), revision gate lambda (`:287-288`). Raw keys: `update_editor_status_for_path` (`:451`), `refresh_open_tabs_from_disk` (`:745`), `EditorTabsCoordinator.active_editor_widget` (`editor_tabs_coordinator.py:69`). Tab tooltips use normalized paths (`editor_tabs_coordinator.py:22-24`). Mixed lookup risks `editor_widget is None` on status update while outline finds widget.
- **Code-judo alternative:** One `normalize_editor_path(file_path: str) -> str` helper used at every `_editor_widgets_by_path` access; or store only normalized keys at registration in `editor_tab_factory`.
- **Suggested remediation:** Normalize at widget registration boundary; audit `rg editor_widgets_by_path.get` in shell for raw vs resolved.
- **Tests that would prove fix:** Tab opened with relative path segment — status bar line/column updates on cursor move match outline refresh behavior.
- **Handoff overlap:** none

---

### TN-EDIT-SHELL-TAB-12 — `EditorTabsCoordinator` is credible extraction; `MiddleClickTabBar` is thermo-clean

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** NICE-TO-HAVE
- **Evidence:** `editor_tabs_coordinator.py` (75 LOC) — tab index, presentation, preview promotion, buffer revision delegation. `editor_tab_bar.py` (55 LOC) — middle-click close (`:22-27`), double-click promote callback (`:30-36`), preview italic paint via `tabData` (`:43-54`). No spaghetti branching; preview styling reads dict flag, not file-type special cases in workflow.
- **Code-judo alternative:** Use coordinator + tab bar as the template for further splits (TN-EDIT-SHELL-TAB-1). Keep custom `paintEvent` in tab bar; do not move preview styling back into workflow.
- **Suggested remediation:** None required for these files; reference as decomposition pattern in remediation plan.
- **Tests that would prove fix:** Existing tab bar behavior covered by manual acceptance; coordinator paths exercised via tab workflow integration tests.
- **Handoff overlap:** none

---

### TN-EDIT-SHELL-TAB-13 — `flat_outline_symbols_for_path` can return stale symbols after buffer edit

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `flat_outline_symbols_for_path` (`:304-309`) returns cached `outline_symbols_by_path[file_path]` without checking `buffer_revision`. Cache populated by async refresh on debounced timer (`handle_editor_text_changed` → `start_outline_refresh_timer`, `:428`). User can invoke Go-to-Symbol immediately after edit; dialog shows pre-edit symbols while panel path would eventually revision-gate. No invalidation on `advance_buffer_revision` except non-Python suffix pop (`:259`).
- **Code-judo alternative:** Cache keyed by `(file_path, revision)` or invalidate on revision bump; `flat_outline_symbols_for_path` drops cache when `buffer_revision(file_path)` ≠ cached revision.
- **Suggested remediation:** Store revision alongside symbols in cache tuple; miss triggers async refresh or sync wait with gate.
- **Tests that would prove fix:** Edit function name, immediately Ctrl+R — symbol list reflects new source or waits for refresh, not stale tree.
- **Handoff overlap:** AD-018, TN-INT-SHELL-EDITORS-4

---

### TN-EDIT-SHELL-TAB-14 — Python fingerprint reindex uses orchestrator snapshot but poll structure scan does not

- **Persona:** TN-EDIT-SHELL-TAB
- **Severity:** STRUCTURAL
- **Evidence:** `start_symbol_indexing_for_loaded_project` (`MainWindowEditorTabHost :962-968`) passes `inventory_snapshot=self._window._project_inventory_orchestrator.snapshot` — correct R4 injection on reindex path. Poll structure detection (`scan_project_tree_signature`) ignores orchestrator entirely and rebuilds relative-path tuple from scratch. After light rescan, `configure_search_sidebar` rebuilds orchestrator (`project_rescan_workflow.py:113`) but poll signature compare remains on parallel enumeration semantics.
- **Code-judo alternative:** `poll_external_file_changes` compares `project_inventory_orchestrator.generation` and `python_paths_fingerprint` only; drop `scan_project_tree_signature` once non-Python tree changes are classified (manifest-only tier vs source tier).
- **Suggested remediation:** Unify poll triggers with orchestrator generation; document tiers: cache churn (ignore), non-Python tree (light tree only), Python set change (reindex).
- **Tests that would prove fix:** Orchestrator generation increments once per real rescan; poll does not call `enumerate_project_entries` when generation stable.
- **Handoff overlap:** CC-PROJ-03, TN-PROJ-SHELL-1, TN-EDIT-SHELL-TAB-5

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| 1k-line rule | **BLOCKER** — `editor_tab_workflow.py` at 1,013 LOC |
| AD-018 revision gate | **Partial** — async outline panel yes; Go-to-Symbol cache no |
| R4 inventory SSOT | **Partial** — reindex injects snapshot; poll/signature bypass orchestrator |
| `editor_tab_bar.py` | **Thermo-clean** — keep as-is |
| `EditorTabsCoordinator` | **Credible** — extend pattern to workflow split |
| Markdown shell seam | **Structural debt** — triplicated mode control (TN-EDIT-MD-3) |
| TN-INT-SHELL-EDITORS-3/4 | **Partial** — async panel + navigation delegation; sync miss + dead host API remain |
| TN-PROJ-SHELL-2/3/12 | **2 partial, 1 open** — light rescan tier landed; cache signature mismatch + `project_service` import remain |

**Approval bar:** **REJECT.** Block on TN-EDIT-SHELL-TAB-1 (1k decomposition) and TN-EDIT-SHELL-TAB-6 (signature/intelligence file-set mismatch). Land TN-EDIT-SHELL-TAB-5/14 (poll ↔ orchestrator unification) with Project SSOT Wave 1 orchestrator work before adding tab-workflow features. Close TN-INT-SHELL-EDITORS-3/4 residuals via TN-EDIT-SHELL-TAB-3/4/13 (single outline coordinator with revision-aware cache). `editor_tab_bar.py` and `editor_tabs_coordinator.py` are not blockers.

*End of TN-EDIT-SHELL-TAB. Integration rollup: pending [`TN-EDIT-INTEG.md`](TN-EDIT-INTEG.md). Prior waves: [`TN-INT-SHELL-EDITORS.md`](../../intelligence-wave-1/_findings/TN-INT-SHELL-EDITORS.md), [`TN-PROJ-SHELL.md`](../../project-ssot-wave-1/_findings/TN-PROJ-SHELL.md). Markdown seam: [`TN-EDIT-MD.md`](TN-EDIT-MD.md).*
