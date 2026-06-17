# TN-EDIT-SHELL-FACTORY — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SHELL-FACTORY
**Date:** 2026-06-17
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** `app/shell/editor_tab_factory.py` (217 LOC), `app/shell/editor_tabs_coordinator.py` (75 LOC), `app/shell/editor_workspace_controller.py` (44 LOC), `app/shell/editor_session_workflow.py` (245 LOC), `app/shell/editor_sync_workflow.py` (96 LOC). Cross-read: `app/shell/editor_tab_workflow.py` (revision advance, `refresh_open_tabs_from_disk`), `app/shell/main_window_composition.py` (wiring), `app/shell/local_history_workflow.py` (session host), `app/shell/editor_stale_result_policy.py`, `app/shell/shell_composition.py` (`MainWindowEditorSyncHost`). Gates: AD-018 revision monotonicity, AD-016 intelligence lane at wiring boundary, materialization vs intelligence separation, session persist/restore, TN-INT-SHELL-EDITORS-8 factory closure sprawl.

---

## Executive verdict

**REJECT — directional extractions are credible, but the factory seam is still not thermo-clean.** `EditorWorkspaceController` is the right AD-018 revision SSOT (monotonic global counter, per-path stored revision, `register_editor` bump on materialize), and `EditorSyncWorkflow` / `EditorSessionWorkflow` are focused modules under the 1k line. Dominant risks: **(1) TN-INT-SHELL-EDITORS-8 factory closure sprawl is still open** — six per-tab nested closures in `editor_tab_factory.py:95-178` wire intelligence, debug, and tab lifecycle in the materialization path; **(2) session restore reuses the user-facing `open_file_in_editor` path with `restore_draft=True`**, so `maybe_restore_draft` can silently overwrite buffers after session open and before cursor restore, desynchronizing persisted cursor/scroll from buffer content; **(3) disk-to-buffer sync is forked** — `EditorSyncWorkflow.apply_disk_content` advances revision correctly, but `editor_tab_workflow.refresh_open_tabs_from_disk` duplicates the same block-signals / `setPlainText` / `advance_buffer_revision` sequence for tool/rename refresh, bypassing the unified workflow; **(4) revision and tab-index APIs are scattered** across workspace controller, tabs coordinator, and tab workflow with pass-through hops and duplicate `tab_index_for_path` implementations. Acceptance routing through `semantic_navigation_workflow` (TN-INT-SHELL-EDITORS-2) is resolved. Would not approve further factory hooks until intelligence bindings move to a single workflow-owned attach method and session restore gets a draft-free materialization entry.

---

## Prior-wave re-validation (TN-INT-SHELL-EDITORS-8 and related)

| Prior ID | Headline | Status at `042be49` | Notes |
|----------|----------|---------------------|-------|
| TN-INT-SHELL-EDITORS-2 | Acceptance bypasses workflow / UI-thread session | **RESOLVED** | `editor_tab_factory.py:158-161` → `semantic_navigation_workflow.record_editor_completion_acceptance`. No direct `_intelligence_controller` reach from factory. |
| TN-INT-SHELL-EDITORS-8 | Factory embeds per-tab intelligence closures | **STILL OPEN** | Closure block unchanged at `editor_tab_factory.py:95-178`. Each new callback still edits factory. See TN-EDIT-SHELL-FACTORY-1. |
| TN-INT-SHELL-EDITORS-3/4 | Outline duplication / UI thread | **Partially out of slice** | Outline lives in `editor_tab_workflow.py`; now uses `deliver_revision_gated_editor_result` + background task. Not factory scope but session restore opens tabs that trigger outline timers. |

---

### TN-EDIT-SHELL-FACTORY-1 — TN-INT-SHELL-EDITORS-8 still open: six nested closures in materialization path

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:95-178` — per-tab nested closures `completion_requester`, `hover_requester`, `signature_requester`, `completion_resolve_requester`, `on_breakpoint_toggled`, `on_text_changed`, `on_cursor_position_changed`, `on_completion_accepted` each capture `tab_file_path` and `editor_widget` and delegate to `_semantic_navigation_workflow` or `_editor_tab_workflow`. Factory imports `CompletionItem` (`:14`) for closure typing. Intelligence Wave 1 evidence cited the same line range; acceptance path fix (TN-INT-SHELL-EDITORS-2) did not collapse the binding site.
- **Code-judo alternative:** `EditorTabWorkflow.attach_editor_bindings(file_path, editor_widget) -> None` (or return a small `EditorBindings` dataclass) owns all requester wiring; factory stops at widget create, theme, preferences, tab add, and `register_editor`. One attach call replaces ~80 lines of closures.
- **Suggested remediation:** Hard cutover: move closure block to tab workflow or dedicated `editor_bindings_workflow.py`; factory calls single attach after `register_editor`.
- **Tests that would prove fix:** Unit test on attach verifies each requester delegates to navigation workflow with captured `file_path`/`editor_widget`; factory test mocks attach only (no intelligence imports in factory).
- **Handoff overlap:** TN-INT-SHELL-EDITORS-8, AD-016, R3

---

### TN-EDIT-SHELL-FACTORY-2 — Materialization and intelligence wiring fused in one 120-line method

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:50-217` — `_materialize_opened_editor_tab` owns preview close, widget construction, preferences, theme, intelligence closures, breakpoint wiring, signal connects, workspace registration, markdown pane fork, tab chrome, draft restore, indentation detection, tab-changed hook, telemetry. Intelligence wiring (`:89-178`) sits between preference setup and tab insertion — every materialization change risks touching async callback contracts.
- **Code-judo alternative:** Split into `_create_editor_widget`, `_attach_shell_bindings` (workflow-owned), `_insert_tab_content` (markdown fork). Factory file stays orchestration-only (~60 LOC).
- **Suggested remediation:** Extract bindings per TN-EDIT-SHELL-FACTORY-1 first; then peel markdown pane insertion to tab workflow helper already used elsewhere for presentation refresh.
- **Tests that would prove fix:** Materialization integration test opens file with mocked navigation workflow; asserts widget exists and bindings attached without factory importing `CompletionItem`.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-8, R3

---

### TN-EDIT-SHELL-FACTORY-3 — Session restore uses user open path with `restore_draft=True`; draft can clobber session buffer

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_session_workflow.py:183-191` — `_restore_file_state` calls `self._open_file_in_editor(file_state.file_path)`. `main_window_composition.py:364` wires that to `window._editor_tab_factory.open_file_in_editor(file_path, preview=False)`. `editor_tab_factory.py:35,201-202` — normal open always passes `restore_draft=True` into `_materialize_opened_editor_tab`; `maybe_restore_draft` runs before session cursor restore (`editor_session_workflow.py:191` → `restore_editor_cursor_and_scroll`). `local_history_workflow.py:399-415` — silent draft restore replaces buffer via `_apply_content_to_open_tab` when policy is `RESTORE_SILENTLY` and content differs. Persisted `cursor_line`/`cursor_column`/`scroll_position` were captured against pre-restore buffer, not post-draft buffer.
- **Code-judo alternative:** Session restore calls `open_file_in_editor(..., restore_draft=False)` or dedicated `open_file_for_session_restore` that skips draft and local-history side effects; cursor/scroll apply immediately after disk content load in one atomic step.
- **Suggested remediation:** Add `restore_draft: bool = True` to `open_file_in_editor`; session workflow passes `False`. Optionally defer `maybe_restore_draft` until after project session restore completes (tree finalize flag).
- **Tests that would prove fix:** Session round-trip with pending silent draft: restored cursor matches session file, not draft-shifted content; draft offered only after session restore when policy is PROMPT.
- **Handoff overlap:** CC-PROJ-13, none

---

### TN-EDIT-SHELL-FACTORY-4 — `EditorSyncWorkflow` unified path bypassed by `refresh_open_tabs_from_disk` duplicate

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_sync_workflow.py:68-96` — canonical disk apply: `blockSignals`, `setPlainText`, `advance_buffer_revision`, indentation, `update_tab_content`, `mark_saved`, refresh chrome. `app/shell/editor_tab_workflow.py:742-763` — `refresh_open_tabs_from_disk` reimplements the same sequence inline (no `EditorSyncWorkflow`, no `EditorDiskSyncSource`). External reload uses sync workflow via `external_file_change_workflow.py`; tool refresh / rename uses tab-workflow duplicate (`semantic_rename_workflow.py:120`, `python_style_workflow.py:261` → `refresh_open_tabs_from_disk`). AD-018 revision bump happens in both paths but divergent maintenance guarantees stale-behavior drift (e.g. `last_known_mtime` handling differs).
- **Code-judo alternative:** Tab workflow delegates `refresh_open_tabs_from_disk` to `EditorSyncWorkflow.apply_disk_content(..., source=EditorDiskSyncSource.TOOL_REFRESH)` per file; delete duplicate block.
- **Suggested remediation:** Inject `EditorSyncWorkflow` into tab workflow host or call existing `build_editor_sync_workflow` instance from composition; hard cutover rename/style callers.
- **Tests that would prove fix:** `test_editor_sync_workflow` cases cover tool-refresh source; `refresh_open_tabs_from_disk` becomes thin loop with zero inline `setPlainText`.
- **Handoff overlap:** AD-018, hard-cutover bias

---

### TN-EDIT-SHELL-FACTORY-5 — AD-018 revision SSOT is correct in workspace controller; forwarding chain adds three hops

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_workspace_controller.py:33-36` — global `_next_buffer_revision` monotonic increment; per-path `_buffer_revisions[file_path]` assignment. `register_editor` (`:19-21`) bumps on materialize. `editor_tab_workflow.py:402` bumps on `handle_editor_text_changed`. `editor_sync_workflow.py:86` bumps on disk apply. Read path: `editor_tabs_coordinator.py:71-75` → `editor_tab_workflow.py:465-469` → workspace controller — three delegation layers for the same two methods. `editor_stale_result_policy.py:24` compares `buffer_revision(file_path) != requested_revision` — contract satisfied when all mutators call `advance_buffer_revision`.
- **Code-judo alternative:** Expose `EditorWorkspaceController` on tab-workflow host protocol; delete coordinator revision pass-through. Intelligence workflows read revision from workspace controller directly (already partially via `semantic_navigation_host.editor_buffer_revision`).
- **Suggested remediation:** Collapse coordinator revision methods; tab workflow holds `workspace_controller` reference from composition.
- **Tests that would prove fix:** Edit → async completion deliver drops when revision advanced; existing `test_editor_stale_result_policy` + sync workflow revision bump tests stay green.
- **Handoff overlap:** AD-018, R3

---

### TN-EDIT-SHELL-FACTORY-6 — `EditorTabsCoordinator.tab_index_for_path` duplicates workflow lookup; refresh uses workflow anyway

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tabs_coordinator.py:17-26` — walks `tabToolTip` vs normalized path. `editor_tab_workflow.py` owns parallel `tab_index_for_path` used by factory (`editor_tab_factory.py:65`), session restore host (`main_window_composition.py:367`), and coordinator itself (`editor_tabs_coordinator.py:35` calls `window._editor_tab_workflow.tab_index_for_path`, not `self.tab_index_for_path`). Two implementations of the same invariant; coordinator method is dead for refresh path.
- **Code-judo alternative:** Single `tab_index_for_path` on coordinator or tab workflow; delete the duplicate. Factory and session inject one callable.
- **Suggested remediation:** Keep lookup on coordinator (presentation layer); tab workflow delegates to coordinator only; remove workflow duplicate.
- **Tests that would prove fix:** Tab index resolution test with preview tab promotion and normalized path aliases; one implementation in codebase (`rg tab_index_for_path` shows single body).
- **Handoff overlap:** R3, none

---

### TN-EDIT-SHELL-FACTORY-7 — `EditorTabFactory` typed as `window: Any`; materialization is private-field soup

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:20-21,24-25` — `__init__(self, window: Any)`; `_materialize_opened_editor_tab` reads `window._editor_tabs_widget`, `_editor_manager`, `_editor_tab_workflow`, `_semantic_navigation_workflow`, `_workspace_controller`, `_local_history_workflow`, `_markdown_panes_by_path`, `_debug_control_workflow`, `_shell_theme_workflow`, and six preference fields. No `EditorTabFactoryHost` Protocol unlike `EditorSyncHostPorts` (`editor_sync_workflow.py:29-53`).
- **Code-judo alternative:** Define `EditorTabFactoryHost` Protocol with explicit ports (manager, tabs widget, tab workflow, workspace controller, theme tokens, open-linked-file callback). Factory depends on protocol; composition implements once.
- **Suggested remediation:** Introduce host protocol in same module; pyright-check factory against protocol; shrink `Any` surface.
- **Tests that would prove fix:** `npx pyright app/shell/editor_tab_factory.py` with protocol-typed host stub; no `Any` on factory constructor.
- **Handoff overlap:** R3, none

---

### TN-EDIT-SHELL-FACTORY-8 — `MainWindowEditorSyncHost.advance_buffer_revision` violates `EditorSyncHostPorts` return contract

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_sync_workflow.py:35-36` — Protocol requires `advance_buffer_revision(...) -> int`. `app/shell/shell_composition.py:38-39` — `MainWindowEditorSyncHost.advance_buffer_revision` annotated `-> None` and ignores return value from tab workflow. Runtime still advances revision; type contract and callers that might need the new revision cannot rely on host.
- **Code-judo alternative:** Host returns `int` from `editor_tab_workflow.advance_buffer_revision`; align annotation with Protocol.
- **Suggested remediation:** One-line return fix in `MainWindowEditorSyncHost`; pyright on sync workflow + composition.
- **Tests that would prove fix:** `test_editor_sync_workflow` host fake already returns `int`; composition host satisfies Protocol structurally.
- **Handoff overlap:** AD-018, none

---

### TN-EDIT-SHELL-FACTORY-9 — `EditorSessionWorkflow` embedded in `LocalHistoryWorkflow`; session not a top-level composition peer

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:97-111` — constructs `EditorSessionWorkflow` internally; `main_window_composition.py:357-385` wires session callbacks into `LocalHistoryWorkflow`, not `EditorSessionWorkflow` directly. `project_load_host.py:52` restores via `local_history_workflow.restore_session_state`. Session persist/restore is logically separate from draft autosave but shares the same workflow object and open-file callback that triggers draft restore (TN-EDIT-SHELL-FACTORY-3).
- **Code-judo alternative:** Compose `EditorSessionWorkflow` at `main_window_composition` alongside `LocalHistoryWorkflow`; local history delegates session methods or receives session workflow as dependency.
- **Suggested remediation:** Lift session workflow to composition; local history holds reference for lifecycle hooks only.
- **Tests that would prove fix:** `test_editor_session_workflow` unchanged; integration test wires session workflow directly without local-history indirection.
- **Handoff overlap:** CC-PROJ-13, R3

---

### TN-EDIT-SHELL-FACTORY-10 — `open_restored_history_buffer` correctly skips draft; asymmetric API not exposed to session restore

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tab_factory.py:37-48` — `open_restored_history_buffer` passes `restore_draft=False` to `_materialize_opened_editor_tab`. `main_window_composition.py:365` exposes it for local-history buffer restore. Session restore (`editor_session_workflow.py:184`) uses only `open_file_in_editor` (draft-on). The correct flag already exists on the materialize helper; session path does not use it.
- **Code-judo alternative:** Unify on `_materialize_opened_editor_tab(..., restore_draft: bool)` with three public entry points: user open (draft on), session open (draft off), history buffer open (draft off, custom content).
- **Suggested remediation:** Same as TN-EDIT-SHELL-FACTORY-3; document the three entry semantics in factory module docstring.
- **Tests that would prove fix:** Parametrized factory test: `restore_draft=False` never calls `maybe_restore_draft` spy.
- **Handoff overlap:** none

---

### TN-EDIT-SHELL-FACTORY-11 — Session restore batches via `QTimer` without suppressing intelligence side effects during multi-tab open

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_session_workflow.py:153-178` — `SESSION_RESTORE_BATCH_SIZE = 2` with `QTimer.singleShot(0, ...)` between batches; tree reveal suppressed (`:142-151`) but not lint/outline/completion timers. Each `_restore_file_state` → `open_file_in_editor` → `handle_editor_tab_changed` (`editor_tab_factory.py:208`) can schedule outline refresh and realtime lint (`editor_tab_workflow.py:427-428`) while later tabs still opening. AD-018 gates async deliver, but wasted work and flicker during restore remain.
- **Code-judo alternative:** `EditorSessionWorkflow` sets host flag `session_restore_in_progress`; tab workflow suppresses lint/outline timers until `_finalize_editor_restore`.
- **Suggested remediation:** Optional restore guard on tab workflow; pair with TN-EDIT-SHELL-FACTORY-3 draft fix.
- **Tests that would prove fix:** Restore 5 files: outline background task count ≤ 1 until finalize; lint scheduler not invoked mid-batch (mock host).
- **Handoff overlap:** AD-018, TN-EDIT-SHELL-TAB

---

### TN-EDIT-SHELL-FACTORY-12 — `EditorSyncWorkflow` discards `source` param; no caller-specific post-sync seam

- **Persona:** TN-EDIT-SHELL-FACTORY
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_sync_workflow.py:73-77` — `del source  # reserved for caller-specific post-sync hooks`. Enum `EditorDiskSyncSource` (`:11-16`) documents three origins but nothing branches on them. External reload vs tool refresh vs quick-fix share identical behavior; future divergence will reintroduce forked paths (see TN-EDIT-SHELL-FACTORY-4).
- **Code-judo alternative:** Either delete `source` until needed, or wire `on_applied(source)` host callback once in Protocol to keep one apply implementation.
- **Suggested remediation:** Add optional `post_apply` hook to `EditorSyncHostPorts` keyed by source, or remove enum from public API until used.
- **Tests that would prove fix:** Quick-fix apply triggers host post-hook; external reload does not when hook unset.
- **Handoff overlap:** hard-cutover bias, none

---

## Cross-cutting notes

| Theme | Status in TN-EDIT-SHELL-FACTORY slice |
|-------|--------------------------------------|
| AD-018 revision monotonicity | **Applied** — `EditorWorkspaceController` owns monotonic counter; text change, disk sync, and `register_editor` advance. Stale gate reads via tab-workflow → coordinator → controller. **Risk:** duplicate disk-apply path (TN-EDIT-SHELL-FACTORY-4). |
| AD-016 session boundary | **Requests + acceptance** route through `semantic_navigation_workflow` from factory closures. **Debt:** closures live in factory, not workflow (TN-EDIT-SHELL-FACTORY-1). |
| Materialization vs intelligence | **Fused** — factory owns widget + bindings (TN-EDIT-SHELL-FACTORY-2). Workspace registration (`:179`) is correctly separated. |
| Session persist/restore | **Partial** — persist snapshots cursor/scroll/breakpoints (`editor_session_workflow.py:63-112`); restore batches OK (`:153-178`). **Gap:** draft restore on open path (TN-EDIT-SHELL-FACTORY-3). |
| TN-INT-SHELL-EDITORS-8 | **STILL OPEN** — closure sprawl unchanged. |
| TN-INT-SHELL-EDITORS-2 | **RESOLVED** — acceptance via navigation workflow. |
| 1k-line rule | All five scoped files well under 1k (217/75/44/245/96). |
| Hard-cutover | `open_restored_history_buffer` shows draft flag pattern exists; session path not cut over (TN-EDIT-SHELL-FACTORY-10). |

**Approval bar for this slice:** `EditorWorkspaceController` and focused sync/session modules are the right decomposition direction. **REJECT** because factory closure sprawl (TN-INT-SHELL-EDITORS-8) remains, session restore can conflict with draft recovery, and disk sync maintains two parallel implementations — any new intelligence callback or restore feature will land in the wrong layer. Ship TN-EDIT-SHELL-FACTORY-1, -3, and -4 as P1 before adding factory hooks; coordinator dedup and host typing as P1/P2.

---

*End of TN-EDIT-SHELL-FACTORY. Integration rollup: pending [`TN-EDIT-INTEG.md`](TN-EDIT-INTEG.md). Prior wave reference: [`TN-INT-SHELL-EDITORS.md`](../../intelligence-wave-1/_findings/TN-INT-SHELL-EDITORS.md).*
