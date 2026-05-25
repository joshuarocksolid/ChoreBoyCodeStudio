# TN-SHELL-MW-13 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-13  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 4682–4911 — tree bulk duplicate, paste, drag-drop move, thin coordinator pass-throughs, import-rewrite dialogs, project reload cascade, outline/tab helpers, markdown mode stubs at slice tail. Cross-read: `project_tree_action_coordinator.py`, `project_tree_controller.py`, `project_tree_presenter.py` (bulk context menu + clipboard), `tests/unit/shell/test_project_tree_action_coordinator.py`, `TN-SHELL-MW-12` (delete/safety + workflow extraction).

**Scope note:** Manifest labels this slice “tree bulk ops,” but lines **4744–4911** are mostly non-tree orchestration (import policy UI, `_reload_current_project`, outline, tab chrome, markdown). Findings below prioritize **4682–4708** (duplicate/paste/drop/reveal) and flag slice-tail bleed as secondary.

---

## Executive verdict

**Not thermo-clean.** Coordinator extraction did the filesystem/editor remaps well (`ProjectTreeActionCoordinator.handle_bulk_duplicate`, `handle_paste`, `handle_drop_move`), but **MainWindow still owns clipboard mutation, paste routing, and QMessageBox error surfacing** while the presenter writes `_tree_clipboard_*` directly. The dominant structural risks are (1) **cut-paste clears the clipboard even when some moves fail**, leaving a half-applied cut with no retry handle; (2) **every duplicate/paste/drop ends in `_reload_current_project()`**, a full project reopen + plugin/test/symbol cascade—not a tree-local refresh; (3) **no `ProjectTreeActionWorkflow`**, so bulk duplicate is a four-line shell wrapper and the next tree action will add another handler. Document safety for delete is covered in `TN-SHELL-MW-12`; move/paste paths remap dirty tabs (acceptable) but still skip any “overwrite destination?” gate. Four-theme impact today is limited to standard `QMessageBox.warning` on paste/duplicate/drop failures; any workflow extraction should re-check those dialogs in Light, Dark, HC Light, and HC Dark.

---

### TN-SHELL-MW-13-1 — Cut-paste clears clipboard after partial move failures

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectTreeActionCoordinator.handle_paste` (`project_tree_action_coordinator.py:138-173`) loops clipboard paths, collects `failed`, then unconditionally sets `next_clipboard_paths = []` and `next_clipboard_cut = False` when `clipboard_cut` is true—**even if `failed` is non-empty**. `MainWindow._handle_tree_paste` always applies returned clipboard state (`main_window.py:4687-4694`). Bulk menu cut→paste routes through the same handler (`project_tree_presenter.py:367-373`).
- **Code-judo alternative:** Return `(failed, remaining_paths, remaining_cut)` where cut mode keeps only paths that did not move (or keeps full clipboard until all succeed). Workflow owns clipboard model; presenter never mutates `window._tree_clipboard_*` directly.
- **Suggested remediation:** Fix semantics in coordinator first; add workflow clipboard type; update `test_handle_paste_cut_applies_moves_and_clears_clipboard` with a partial-failure case asserting clipboard retention.
- **Tests that would prove fix:** Coordinator unit test: two-path cut, first move fails → `next_paths` still contains both (or failed-only retry set) and `next_cut` still true; integration: user can retry paste after partial failure.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-13-2 — Tree clipboard is mutable MainWindow state; presenter and handler fight over it

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** Clipboard fields initialized on shell (`main_window.py:441-442`). Presenter bulk menu assigns them directly (`project_tree_presenter.py:365-369`); single-item menu does the same (`312-316`). Paste reads/writes via `_handle_tree_paste` (`4687-4694`). Enablement checks `len(window._tree_clipboard_paths)` in presenter (`296`, `355`). No typed model, no single owner—three call sites must stay in sync.
- **Code-judo alternative:** `TreeClipboard` dataclass on `ProjectTreeActionWorkflow` (or coordinator) with `copy(paths)`, `cut(paths)`, `clear()`, `paths`, `is_cut`; presenter receives workflow reference and calls `workflow.clipboard.copy(...)` instead of touching `MainWindow` privates.
- **Suggested remediation:** Introduce with `ProjectTreeActionWorkflow` extraction (`TN-SHELL-MW-12-3`); hard cutover—delete `_tree_clipboard_*` from `MainWindow`.
- **Tests that would prove fix:** Workflow unit test: copy then paste delegates to coordinator with correct paths; presenter test with fake workflow never accesses `window._tree_clipboard_paths`.
- **Handoff overlap:** R2, R3 (`project_tree_presenter.py`)

---

### TN-SHELL-MW-13-3 — Bulk/single duplicate handlers are empty shells; no workflow, no coordinator tests

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_tree_bulk_duplicate` (`main_window.py:4682-4685`) is coordinator call + `QMessageBox.warning`. Single-item `_handle_tree_duplicate` (`4656-4659`, adjacent slice) is identical shape. Coordinator implements loop + reload (`project_tree_action_coordinator.py:129-136`) but `tests/unit/shell/test_project_tree_action_coordinator.py` covers bulk delete, paste, drop, rename—**no** `handle_duplicate` / `handle_bulk_duplicate` cases. Bulk menu dispatches through presenter (`project_tree_presenter.py:362-363`).
- **Code-judo alternative:** `ProjectTreeActionWorkflow.duplicate_paths(paths)` → coordinator `duplicate_paths` (rename `handle_bulk_duplicate` to accept length-1 list); delete `_handle_tree_duplicate` and `_handle_tree_bulk_duplicate`. Mirror bulk-delete unification from `TN-SHELL-MW-12-6`.
- **Suggested remediation:** Fold into R2 workflow PR; add parametrized coordinator tests for success, per-item failure messages, and single reload at end.
- **Tests that would prove fix:** `test_duplicate_paths_single_and_bulk` on coordinator; workflow test asserts one reload and warning only when `failed` non-empty.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-13-4 — Every tree filesystem op triggers full `_reload_current_project` cascade

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** Coordinator injects `reload_project=self._reload_current_project` (`main_window.py:668`). Duplicate, bulk duplicate, paste, drop each call `self._reload_project()` once per operation (`project_tree_action_coordinator.py:113-114`, `135-136`, `172-173`, `196-197`). `_reload_current_project` (`main_window.py:4809-4833`) re-`open_project`, reloads plugins, refreshes Python tooling, repopulates tree with `preserve_state=True`, updates search excludes, resets structure signature, restarts symbol indexing, refreshes test discovery—far beyond “tree item appeared.”
- **Code-judo alternative:** `ProjectTreeRefreshPolicy`: lightweight `refresh_tree_entries()` for create/duplicate/copy; reserve full reload for metadata-affecting ops. Coordinator accepts `reload_mode: Literal["tree", "project"]` or callback pair injected at composition root.
- **Suggested remediation:** Profile cost on large projects first; extract tree-only refresh into presenter/controller before deleting full reload from hot paths.
- **Tests that would prove fix:** Coordinator test with spy: duplicate calls tree refresh once, does not invoke plugin reload; integration: duplicate file does not reset unrelated sidebar state.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-13-5 — Paste/drop handlers duplicate the coordinator→QMessageBox pattern; block workflow extraction

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_tree_paste` (`4687-4696`) and `_handle_project_tree_drop` (`4698-4703`) follow the same template as bulk duplicate: delegate to coordinator, join failures, warn. Drop is also invoked from tree widget DnD (outside this slice). Presenter bulk menu adds a third entry for paste (`370-373`) with **destination derived only from `selected[0]`** when multiple items are selected—ambiguous when selection mixes files and folders.
- **Code-judo alternative:** `ProjectTreeActionWorkflow.paste_into(destination_dir)` and `move_via_drop(source, target)` own coordinator calls, clipboard updates, and dialogs; `MainWindow` deletes both handlers.
- **Suggested remediation:** Implement alongside `TN-SHELL-MW-12-3` workflow; define explicit destination rule (e.g. common parent of selection, or disable paste when selection is heterogeneous).
- **Tests that would prove fix:** Workflow tests for drop failure message; presenter test for bulk paste destination when first selected entry is a file vs directory.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-13-6 — Two more one-line `MainWindow` delegators to the coordinator

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** `_close_deleted_editor_paths` (`4721-4722`) and `_apply_path_move_updates` (`4724-4725`) only forward to `self._project_tree_action_coordinator`. Wired from coordinator init (`652-670`) as callbacks into the same coordinator that already owns `ProjectTreeController`—indirection with no added policy.
- **Code-judo alternative:** Coordinator calls `self._project_tree_controller` directly for close/move (it already does inside `close_deleted_editor_paths` / `apply_path_move_updates` methods at `199-226`); remove MainWindow methods and shrink constructor callback surface.
- **Suggested remediation:** Hard cutover in R2: delete both methods, inline controller access inside coordinator, update any external callers (grep `_apply_path_move_updates` on `MainWindow`).
- **Tests that would prove fix:** Existing coordinator/controller tests suffice; grep gate that `MainWindow` no longer exposes these symbols.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-13-7 — Import-update policy UI stranded in tree-ops slice on `MainWindow`

- **Persona:** TN-SHELL-MW-13
- **Severity:** STRUCTURAL
- **Evidence:** `_maybe_rewrite_imports_for_move` delegates to controller (`4744-4753`), but `_resolve_import_update_policy_for_operation` (`4777-4807`) is a 30-line `QInputDialog` + nested `QMessageBox` chain on `MainWindow`, plus untyped `_handle_import_rewrites_applied` (`4755-4762`, `# type: ignore[no-untyped-def]`). Triggered from coordinator via `maybe_rewrite_imports` callback on paste cut and drop move—not tree presentation.
- **Code-judo alternative:** `ImportRewriteWorkflow` (or extend move workflow) owns policy resolution, persistence (`_save_import_update_policy`), confirmation, and local-history `record_transaction`; shell exposes thin port.
- **Suggested remediation:** Extract when touching move/paste; do not add more import dialogs on `MainWindow`.
- **Tests that would prove fix:** Workflow unit test with stub dialogs returning each `ImportUpdatePolicy`; assert rewrite only when policy allows.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-13-8 — Outline and tab-removal orchestration live in the tree-bulk slice by line accident

- **Persona:** TN-SHELL-MW-13
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_refresh_outline_for_active_tab` (`4843-4866`) encodes language gating, symbol build, and cursor-follow on `MainWindow`. `_remove_tab_widget_for_path` (`4874-4888`) couples tab widget, workspace controller, indent state, and run/save action refresh. Neither is invoked from bulk duplicate/paste/drop handlers in this slice; they share the line range only because the class is monolithic (5,549 lines).
- **Code-judo alternative:** Move outline refresh to `OutlinePanel` host/workflow (`TN-SHELL-OUTLINE`); tab removal to `EditorTabsCoordinator` (already partially extracted via `_get_editor_tabs_coordinator` at `4871-4891`).
- **Suggested remediation:** Defer to outline/tab critics; do not expand these methods during tree workflow work.
- **Tests that would prove fix:** Covered by existing outline/tab tests when moved.
- **Handoff overlap:** R3 (`TN-SHELL-OUTLINE`)

---

### TN-SHELL-MW-13-9 — Markdown mode handlers at slice tail belong to MW-14, not tree bulk ops

- **Persona:** TN-SHELL-MW-13
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_active_markdown_pane`, `_set_active_markdown_mode`, and three action stubs (`4899-4919`) are pure editor-mode routing—no tree coupling. Slice ends at 4911; MW-14 starts at 4912 per manifest.
- **Code-judo alternative:** None required in this critic; cross-reference `TN-SHELL-MW-14` for markdown extraction.
- **Suggested remediation:** Ignore for tree bulk-op PRs; avoid editing these lines when implementing findings 1–6.
- **Tests that would prove fix:** n/a
- **Handoff overlap:** none (see MW-14)

---

## Positive signals (not findings)

- Filesystem I/O and editor/breakpoint remaps for paste cut and drop are centralized in `ProjectTreeActionCoordinator` with focused unit tests for paste cut and drop guards (`test_project_tree_action_coordinator.py:112-210`).
- `apply_path_move_updates` keeps dirty buffers on disk move by remapping tabs rather than closing them—correct contrast to delete’s `close_editor_file` path (`TN-SHELL-MW-12-1`).
- Bulk duplicate failure reporting is consistent with bulk delete (`name: message` per item).
- `ProjectTreeController` remains a typed, callback-driven boundary for delete/move side effects (`project_tree_controller.py:24-86`).

---

## Approval bar (this slice)

**Would not approve** adding new `_handle_tree_*` methods or presenter clipboard mutations on `MainWindow` without (1) fixing cut-paste partial-failure clipboard semantics, (2) extracting `ProjectTreeActionWorkflow` with clipboard + duplicate/paste/drop entry points, and (3) **net-reduced** `MainWindow` method count (delete pass-through delegators in finding 6). Any new failure dialogs must note four-theme validation status. Prefer tree-local refresh over wiring more calls to `_reload_current_project` without measuring blast radius.
