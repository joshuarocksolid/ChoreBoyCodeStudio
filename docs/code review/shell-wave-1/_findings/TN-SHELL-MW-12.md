# TN-SHELL-MW-12 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-12  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 4478–4681 — tree expand/collapse chrome, presenter pass-throughs, preview-click routing, context-menu delegation, rename/delete/delete-key/bulk-delete orchestration. Cross-read: `project_tree_presenter.py` (context menu + reveal dispatch), `project_tree_action_coordinator.py`, `project_tree_controller.py`, `save_workflow.py`, `local_history_workflow.py`. Reveal handler `_reveal_path_in_file_manager` at `main_window.py:4705-4708` included because the single-item context menu dispatches to it (`project_tree_presenter.py:323-324`).

---

## Executive verdict

**Not thermo-clean.** Extraction landed the filesystem/editor side effects in `ProjectTreeActionCoordinator` and `ProjectTreeController`, but this slice is still **UI orchestration spaghetti on `MainWindow`**: QMessageBox prompts, local-history snapshot timing, and coordinator calls for rename/delete sit beside a **12-method presenter delegator farm** and an 80-line `elif` dispatch chain in `ProjectTreePresenter`. The dominant risk is **asymmetric document safety**: tab close and app exit route through `SaveWorkflow`, but tree delete closes dirty tabs via `editor_manager.close_file` with **no save/discard prompt** — a PRD violation (“never lose user work”). Secondary risk: the next tree action added here will compound method count on a 5,549-line class and duplicate the confirm → side-effect → warn pattern again. Four-theme impact is indirect today (standard `QMessageBox` / `QInputDialog` chrome inherits shell stylesheet); any workflow extraction must re-validate delete/rename dialogs in Light, Dark, HC Light, and HC Dark.

---

### TN-SHELL-MW-12-1 — Tree delete bypasses SaveWorkflow; silently drops dirty buffers

- **Persona:** TN-SHELL-MW-12
- **Severity:** BLOCKER
- **Evidence:** Tab close prompts via `SaveWorkflow` before removing tabs (`main_window.py:5230-5241`). Tree delete does not: `_handle_tree_delete` confirms trash, captures disk snapshots, calls coordinator, records history (`main_window.py:4635-4654`). Coordinator closes editors through `close_editor_file=self._editor_manager.close_file` (`main_window.py:660`), and `EditorManager.close_file` pops tab state with no dirty check (`app/editors/editor_manager.py:227-237`). Bulk delete and Delete-key routing share the same gap (`main_window.py:4626-4633`, `4661-4680`).
- **Code-judo alternative:** `ProjectTreeActionWorkflow.delete_paths(...)` (or extend `SaveWorkflow`) collects affected open tabs, calls `request_unsaved_changes_decision("moving items to trash", scope=DocumentScope.PROJECT, dirty_buffers=affected)` **before** filesystem delete; on proceed/discard, run coordinator delete + local-history transaction. Single and bulk collapse to one method with a shared confirmation builder.
- **Suggested remediation:** Wire delete through `SaveWorkflow` the same way `_handle_tab_close_requested` does; optionally merge dirty-buffer content into local-history capture when discarding. Hard cutover — no silent `close_file` on dirty tabs from tree actions.
- **Tests that would prove fix:** Unit test: open dirty tab → tree delete → assert unsaved dialog shown and tab not closed on Cancel; integration test: Proceed+Save persists before trash; Discard closes without writing disk.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-12-2 — Local history capture reads disk, not in-memory dirty content

- **Persona:** TN-SHELL-MW-12
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_tree_delete` calls `capture_text_history_snapshots([target_path])` before delete (`main_window.py:4645`). `LocalHistoryWorkflow.capture_text_history_snapshots` reads files from disk via `read_text` (`local_history_workflow.py:309-324`), not `EditorManager` tab content. Unsaved edits that differ from disk are invisible to the pre-delete snapshot even if finding 1 is fixed for tab-close semantics.
- **Code-judo alternative:** Delete workflow merges disk snapshots with dirty-buffer payloads from open tabs (same source `SaveWorkflow` uses via `dirty_buffer_snapshots`) before `record_transaction`; coordinator delete runs only after safety decision resolves buffer state.
- **Suggested remediation:** Move snapshot assembly into `ProjectTreeActionWorkflow` or `LocalHistoryWorkflow.capture_delete_snapshots(paths, open_tabs)` that prefers dirty buffer text when present.
- **Tests that would prove fix:** Unit test: dirty buffer differs from disk → delete+discard → local-history transaction contains buffer text, not stale disk read.
- **Handoff overlap:** R2, R3 (`local_history_workflow.py`)

---

### TN-SHELL-MW-12-3 — No ProjectTreeActionWorkflow; MainWindow owns confirm → history → coordinator glue

- **Persona:** TN-SHELL-MW-12
- **Severity:** STRUCTURAL
- **Evidence:** Rename/delete/new-file handlers on `MainWindow` repeat the same shape: modal input or confirm → `self._project_tree_action_coordinator.handle_*` → `QMessageBox.warning` on error (`main_window.py:4597-4624`, `4635-4654`, `4661-4680`). Local-history orchestration (capture, filter, record) lives only on delete paths in `MainWindow`, not in `ProjectTreeActionCoordinator`. `SaveWorkflow` already models the parallel pattern for save/unsaved (`save_workflow.py:35-195`) but tree mutations did not follow it.
- **Code-judo alternative:** `ProjectTreeActionWorkflow(window_ports)` with public methods `rename_item`, `delete_items`, `new_file`, `new_folder` matching user actions — owns dialogs, `SaveWorkflow` gates, coordinator calls, and local-history transactions. `MainWindow` deletes `_handle_tree_rename`, `_handle_tree_delete`, `_handle_tree_bulk_delete`, `_handle_project_tree_delete_key`.
- **Suggested remediation:** R2 extraction alongside finding 1; connect context menu and Delete-key signal directly to workflow methods; net **method count down** on `MainWindow`.
- **Tests that would prove fix:** Workflow unit tests with stub coordinator + stub save workflow; port `test_main_window_tree_delete_copy.py` to workflow public API.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-12-4 — Twelve one-line presenter delegators violate R2 shrink rule

- **Persona:** TN-SHELL-MW-12
- **Severity:** STRUCTURAL
- **Evidence:** Lines 4482–4549 and 4592–4595 are pure pass-throughs: `_populate_project_tree`, `_capture_project_tree_state`, `_restore_project_tree_state`, `_iter_project_tree_items`, `_collect_tree_descendants`, `_build_tree_item`, `_get_selected_tree_paths`, `_tree_item_entry`, `_show_project_tree_context_menu`, `_show_single_item_context_menu`, `_show_bulk_context_menu` each forward to `_get_project_tree_presenter()`. Presenter is **eagerly** constructed at `main_window.py:329-334` while `_get_project_tree_presenter` (`2788-2798`) retains vestigial lazy-init duplication.
- **Code-judo alternative:** Wire tree widget signals directly to `self._project_tree_presenter` methods at composition root (`__init__` or shell wiring module); delete all 12 delegators and the lazy getter. Callers outside this slice that still invoke `MainWindow._populate_project_tree` migrate to presenter reference held by `ProjectController` or tree wiring.
- **Suggested remediation:** Hard cutover per handoff “no new one-line delegators”; grep-remove delegators in same PR as workflow extraction.
- **Tests that would prove fix:** Grep/assertion test or review checklist: `MainWindow` method count decreases; tree refresh tests call presenter or workflow without patching `MainWindow._populate_project_tree`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-12-5 — Context menu split: presenter builds menu, MainWindow executes via 80-line elif chain

- **Persona:** TN-SHELL-MW-12
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectTreePresenter.show_single_item_context_menu` (`project_tree_presenter.py:247-332`) builds `QMenu`, enables/disables actions (run, paste, entry point), then dispatches 15 branches to `window._handle_tree_*`, `window._reveal_path_in_file_manager`, clipboard mutation on `window._tree_clipboard_*`, and `window._set_project_entry_point`. Rename/delete/reveal are three of those branches (`305-308`, `323-324`). Every new tree action extends this chain **and** adds a `MainWindow` handler.
- **Code-judo alternative:** Presenter emits a typed `TreeContextAction` enum/dataclass; `ProjectTreeActionWorkflow.handle(action)` executes. Or: presenter receives workflow + run/debug collaborators at construction and calls them directly — no bounce through `MainWindow` private methods. Menu enablement rules move to small policy helpers colocated with workflow.
- **Suggested remediation:** Collapse dispatch when extracting `ProjectTreeActionWorkflow`; presenter keeps view concerns (menu labels, enablement) only.
- **Tests that would prove fix:** Parametrized test: each menu action id maps to one workflow method; presenter test with fake workflow records chosen action without `MainWindow`.
- **Handoff overlap:** R2, R3 (`project_tree_presenter.py`)

---

### TN-SHELL-MW-12-6 — Single vs bulk delete duplicate confirmation and history orchestration

- **Persona:** TN-SHELL-MW-12
- **Severity:** STRUCTURAL
- **Evidence:** `_handle_tree_delete` (`4635-4654`) and `_handle_tree_bulk_delete` (`4661-4680`) both: `QMessageBox.question` → capture snapshots → coordinator delete → `record_transaction` → optional warning. Bulk adds `filter_snapshots_for_paths` and partial-failure reporting; single records only on full success. Delete-key router adds a third entry point (`4626-4633`).
- **Code-judo alternative:** One `delete_paths(paths: list[str]) -> DeleteOutcome` on workflow: builds confirmation text from path list, runs safety gate once for all affected open tabs, calls `handle_bulk_delete` always (coordinator already loops), records one transaction with filtered snapshots.
- **Suggested remediation:** Implement as part of finding 3; delete `_handle_tree_delete` / `_handle_tree_bulk_delete` split.
- **Tests that would prove fix:** Extend `test_main_window_tree_delete_copy.py` cases for single==bulk path of length 1; assert one coordinator call and one history transaction.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-12-7 — Ad-hoc `tuple[str, str, bool]` tree entry shape across presenter and MainWindow

- **Persona:** TN-SHELL-MW-12
- **Severity:** NICE-TO-HAVE
- **Evidence:** `selected_paths`, `item_entry`, and context-menu `entry` use `(absolute_path, relative_path, is_directory)` tuples (`project_tree_presenter.py:201-222`, `247-254`; `main_window.py:4536-4541`). Index `[0]`/`[1]`/`[2]` at call sites (`4626-4633`, bulk menu) obscures invariants.
- **Code-judo alternative:** Frozen dataclass `TreeItemEntry` in `app/project/` or `app/shell/` shared by presenter, workflow, and coordinator inputs.
- **Suggested remediation:** Introduce when touching tree workflow extraction; not a standalone PR.
- **Tests that would prove fix:** Type-checking only; optional round-trip test on presenter `item_entry`.
- **Handoff overlap:** none

---

### TN-SHELL-MW-12-8 — Reveal is trivial but stranded on MainWindow; presenter still callbacks through shell

- **Persona:** TN-SHELL-MW-12
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_reveal_path_in_file_manager` is four lines (`main_window.py:4705-4708`); injected into `ShellHelpController` at init (`main_window.py:492`) and invoked from tree menu via presenter (`project_tree_presenter.py:323-324`). Presenter already depends on `window: Any`.
- **Code-judo alternative:** Module-level `reveal_path_in_file_manager(path: str) -> None` in `app/shell/file_reveal.py` (or presenter method) shared by help controller and tree menu — delete `MainWindow._reveal_path_in_file_manager`.
- **Suggested remediation:** Fold into R2 tree workflow PR or help-controller cleanup; low priority alone.
- **Tests that would prove fix:** Single unit test on pure function with mocked `QDesktopServices.openUrl`.
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `ProjectTreeActionCoordinator` cleanly owns filesystem I/O plus editor/breakpoint remaps; rename/delete delegate to `ProjectTreeController` (`project_tree_action_coordinator.py:85-127`, `199-226`).
- `ProjectTreeController.close_deleted_editor_paths` and `apply_path_move_updates` are focused, callback-driven, and testable in isolation (`project_tree_controller.py:24-86`).
- Pre-delete local-history capture (disk-based) shows intent to preserve recoverability (`main_window.py:4645-4654`).
- Characterization tests exist for Move-to-Trash copy strings (`tests/unit/shell/test_main_window_tree_delete_copy.py`).
- `SaveWorkflow` provides the canonical unsaved-buffer contract that delete should reuse (`save_workflow.py:41-102`).

---

## Approval bar (this slice)

**Would not approve** a change that adds tree action handlers or presenter delegators on `MainWindow` without (1) routing delete through `SaveWorkflow` document safety, and (2) extracting `ProjectTreeActionWorkflow` with **net-reduced** `MainWindow` method count. Any dialog/workflow move must note four-theme validation status for rename/delete confirmation surfaces.
