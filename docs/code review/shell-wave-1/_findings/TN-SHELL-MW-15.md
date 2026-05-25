# TN-SHELL-MW-15 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-15  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 5369–5522 — indent source recording/status, disk tab refresh, external file change detection/reload, project-tree poll hook, scheduled realtime lint pass-throughs. Cross-read: `python_style_workflow.py` (safe-fix disk refresh contract), `diagnostics_search_coordinator.py` (`DiagnosticsOrchestrator`), `status_bar.py` (`map_indent_status_view`), `_apply_detected_indentation_for_widget` at `main_window.py:5322–5367` (immediate caller context for indent/paste repair).

---

## Executive verdict

**Not thermo-clean.** This tail slice is **editor-sync orchestration spaghetti** on a **5,549-line** `MainWindow`: indent metadata lives in an ad-hoc path dict with status-bar glue, two disk-reload paths copy the same widget/tab mutation sequence with **divergent revision semantics**, external-change handling embeds local-history transactions and a **non-obvious “decline reload” branch** that mutates tab dirtiness without touching the editor, and a 1 s poll timer **fuses unrelated concerns** (stale open files vs project-tree signature → full project reload). Realtime lint is correctly delegated to `DiagnosticsOrchestrator`, but `MainWindow` still carries **two shutdown-guard pass-through methods** wired from the timer — the opposite of the handoff “method count down” rule. `PythonStyleWorkflow` already depends on `_refresh_open_tabs_from_disk` as its post-fix contract; there is no parallel `EditorIndentWorkflow` / `EditorSyncWorkflow` for indent detection or disk reconciliation despite `PythonStyleWorkflow` setting the extraction pattern. Four-theme impact: external-change and dirty-buffer dialogs use standard `QMessageBox`; any workflow extraction must re-validate those surfaces in Light, Dark, HC Light, and HC Dark.

---

### TN-SHELL-MW-15-1 — Decline-reload branch marks clean tabs dirty without editor mutation

- **Persona:** TN-SHELL-MW-15
- **Severity:** BLOCKER
- **Evidence:** When the user answers **No** to an external reload, `_check_for_external_file_change` acknowledges disk mtime, and if the tab is not dirty sets `tab_state.original_content = disk_content` then calls `_handle_editor_text_changed` without changing the widget text (`main_window.py:5481–5484`). `EditorTabState.is_dirty` is `current_content != original_content` (`app/editors/editor_tab.py:40–42`). Disk content already differs from buffer (earlier guard at `5432–5435`), so assigning `original_content = disk_content` makes a previously clean tab **dirty with no visible edit**, then fires the full text-changed side-effect chain (autosave schedule, save-action refresh, lint schedule, outline timer) against unchanged editor text.
- **Code-judo alternative:** `ExternalFileChangeWorkflow.decide_and_apply(file_path) -> ReloadOutcome` with explicit outcomes: `reloaded`, `declined_keep_buffer`, `declined_ack_only`. Decline on a clean tab either (a) only `acknowledge_disk_mtime` and surface a status-bar “disk newer” hint, or (b) offer a dedicated “compare” path — never silently flip `original_content` and simulate a text change.
- **Suggested remediation:** Hard cutover fix in workflow extraction or immediate bugfix PR before R2; delete the `original_content` assignment + `_handle_editor_text_changed` call from the decline path.
- **Tests that would prove fix:** Unit test: clean open tab, disk changes, user clicks No → tab stays not dirty, editor text unchanged, no autosave/lint scheduled; integration test: dirty tab + No → buffer preserved, mtime acknowledged.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-15-2 — Duplicate disk→editor sync choreography; revision handling diverges

- **Persona:** TN-SHELL-MW-15
- **Severity:** STRUCTURAL
- **Evidence:** `_refresh_open_tabs_from_disk` (`5394–5414`) and the Yes branch of `_check_for_external_file_change` (`5461–5469`) both: `blockSignals` → `setPlainText` → `_apply_detected_indentation_for_widget` → `update_tab_content` → `mark_saved` → optional `_refresh_tab_presentation`. Only `_refresh_open_tabs_from_disk` calls `_advance_editor_buffer_revision` (`5407`); external reload omits it. `_refresh_open_tabs_from_disk` is also invoked from `PythonStyleWorkflow.apply_safe_fixes_for_file` (`python_style_workflow.py:189`) and rename/reference paths on `MainWindow` (`2228`, `4762`) — all consumers inherit the same partial contract.
- **Code-judo alternative:** One `EditorSyncWorkflow.apply_disk_content(file_path, text, *, source: Literal["external_reload","tool_refresh","quick_fix"], record_history: bool)` owning widget mutation, indent re-detection, tab-state update, buffer-revision bump, and optional local-history checkpoint. External-change workflow calls it with `record_history=True`; style/rename callers use `tool_refresh`.
- **Suggested remediation:** R2 extraction; external reload and `_refresh_open_tabs_from_disk` become thin callers. Unify revision bump so completion/intelligence invalidation is consistent across reload sources.
- **Tests that would prove fix:** Parametrized test: both entry points advance buffer revision and re-detect indent; characterization test that quick-fix refresh still matches current on-disk editor state.
- **Handoff overlap:** R2, R3 (`python_style_workflow.py`)

---

### TN-SHELL-MW-15-3 — No EditorIndentWorkflow; indent detect/record/status scattered on MainWindow

- **Persona:** TN-SHELL-MW-15
- **Severity:** STRUCTURAL
- **Evidence:** `_indent_source_by_path: dict[str, tuple[str, int, str]]` (`436`), `_apply_detected_indentation_for_widget` with three near-identical `set_editor_preferences` blocks (`5322–5367`), `_record_indent_source` (`5369–5379`), and `_update_indent_status_for_path` (`5381–5392`) all live on `MainWindow`. Paste/auto-reindent handlers and settings persistence sit far away (`1989–2018`, `_enable_auto_reindent_flat_python_paste_from_hint`). `PythonStyleWorkflow` (`python_style_workflow.py:19–193`) already owns format/import/lint/safe-fix user actions with a `window` port — indent/paste repair did not follow the same boundary.
- **Code-judo alternative:** `EditorIndentWorkflow(window_ports)` owning: per-path indent source map, `apply_detected_indentation_for_widget`, status-bar indent updates via `ShellStatusBarController`, and hooks for flat-Python paste repair feedback. `MainWindow` deletes the four indent methods and the dict; tab switch calls `workflow.refresh_status_for_path`.
- **Suggested remediation:** R2 wave alongside flat-Python action consolidation (TN-SHELL-MW-05-5 territory); pass `status_controller` and editor widget lookup as explicit ports, not `window: Any`.
- **Tests that would prove fix:** Unit tests on workflow for editorconfig vs auto-detect vs user fallback paths; status-bar text matches `map_indent_status_view` for each source.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-15-4 — Realtime lint schedulers are unnecessary MainWindow pass-throughs

- **Persona:** TN-SHELL-MW-15
- **Severity:** STRUCTURAL
- **Evidence:** `_schedule_realtime_lint` and `_run_scheduled_realtime_lint` (`5518–5526`) only guard `_is_shutting_down` then delegate to `self._diagnostics_orchestrator`. Timer wiring at init connects directly to `_run_scheduled_realtime_lint` (`517`); text-changed handler calls `_schedule_realtime_lint` (`4969`). `DiagnosticsOrchestrator` already owns debounce, pending path, and active-tab guard (`diagnostics_search_coordinator.py:49–64`).
- **Code-judo alternative:** Pass `is_shutting_down=lambda: self._is_shutting_down` into `DiagnosticsOrchestrator` at construction (`621–645`); connect `_realtime_lint_timer.timeout` to `orchestrator.run_scheduled_realtime_lint`; call `orchestrator.schedule_realtime_lint` from `_handle_editor_text_changed`. Delete both MainWindow methods — **net −2 methods**.
- **Suggested remediation:** Hard cutover in R2 shell cleanup PR; no compatibility shims.
- **Tests that would prove fix:** Existing diagnostics orchestrator tests plus grep/assertion: zero `_schedule_realtime_lint` on `MainWindow`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-15-5 — `_poll_external_file_changes` fuses stale-file checks and full project reload

- **Persona:** TN-SHELL-MW-15
- **Severity:** STRUCTURAL
- **Evidence:** Single 1 s timer callback (`753–754`, `5486–5504`) (1) checks `stale_open_paths()` but only prompts for the **active** tab if it is stale (`5487–5491`), then (2) scans project tree signature via `_scan_project_tree_signature` (`5506–5516`) and calls `_reload_current_project()` on any structural diff (`5501–5504`). Full reload cascade is the same heavy path flagged in TN-SHELL-MW-11-6.
- **Code-judo alternative:** Split timers or a small `ShellPollCoordinator` with two policies: `ExternalFileWatchPolicy` (iterate all stale paths or queue prompts) and `ProjectTreeWatchPolicy` (signature diff → tiered refresh, not always full reload). `_scan_project_tree_signature` moves next to tree/project inventory ownership.
- **Suggested remediation:** Coordinate with TN-SHELL-MW-11-6 `ProjectRefreshWorkflow`; at minimum extract poll body off `MainWindow` so this slice’s methods shrink.
- **Tests that would prove fix:** Extend `test_project_tree_refresh_state.py` to assert stale **background** tab gets checked when policy demands it; tiered refresh does not restart symbol index on noop signature changes.
- **Handoff overlap:** R2, R4 (file inventory SSOT)

---

### TN-SHELL-MW-15-6 — `_refresh_open_tabs_from_disk` omits lint/outline/status side effects that manual reload paths expect

- **Persona:** TN-SHELL-MW-15
- **Severity:** STRUCTURAL
- **Evidence:** After disk sync loop, `_refresh_open_tabs_from_disk` only calls `_refresh_save_action_states` (`5414`). It does not `_schedule_realtime_lint`, `_update_editor_status_for_path`, or outline refresh for affected paths. `PythonStyleWorkflow.apply_safe_fixes_for_file` compensates partially by calling `_render_lint_diagnostics_for_file(file_path, trigger="manual")` for the **original** file only (`python_style_workflow.py:192`), not every path in `affected_files`. Rename/reference refresh callers (`2228`, `4762`) get no lint pass at all.
- **Code-judo alternative:** Central `EditorSyncWorkflow` post-sync hook list: `on_paths_synced(paths) -> None` invoking lint schedule (or orchestrator batch), active-tab status/outline refresh, save-action refresh once at end.
- **Suggested remediation:** Define explicit post-sync contract when extracting finding 2; safe-fix workflow calls one hook instead of ad-hoc lint + refresh pair.
- **Tests that would prove fix:** Quick-fix test with two open Python files changed → both relinted; rename refresh test asserts diagnostics updated for renamed path.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-15-7 — Ad-hoc `tuple[str, int, str]` indent record obscures invariants

- **Persona:** TN-SHELL-MW-15
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_indent_source_by_path` stores `(style, size, source)` tuples (`436`, `5376`); callers unpack by position (`5391`). `source` is a stringly-typed discriminator consumed by `map_indent_status_view` (`status_bar.py:167–187`) with values `"auto"`, `"editorconfig"`, `"user"` — not enumerated in the type system.
- **Code-judo alternative:** Frozen dataclass `IndentSourceRecord(style: str, size: int, source: Literal["auto","editorconfig","user"])` in `app/editors/` or `app/shell/` shared by workflow and status mapper.
- **Suggested remediation:** Introduce when extracting `EditorIndentWorkflow`; not a standalone PR.
- **Tests that would prove fix:** Type-checking only; optional round-trip on status copy for each source.
- **Handoff overlap:** none

---

### TN-SHELL-MW-15-8 — Active-tab-only stale check leaves background tabs silently diverged

- **Persona:** TN-SHELL-MW-15
- **Severity:** NICE-TO-HAVE
- **Evidence:** `_poll_external_file_changes` builds `stale_paths` for all open files (`5487`) but calls `_check_for_external_file_change` only when the active tab’s path is in that set (`5489–5491`). Background tabs with disk changes are not prompted until the user switches to them (tab switch does call `_check_for_external_file_change` at `5162`).
- **Code-judo alternative:** Either document as intentional lazy prompt policy in workflow, or queue stale non-active paths for prompt-on-switch without requiring poll coupling to active tab only.
- **Suggested remediation:** Product decision during `ExternalFileChangeWorkflow` extraction; if lazy is intended, move comment + test to workflow; if not, iterate stale paths in poll.
- **Tests that would prove fix:** Characterization test encoding chosen policy (background stale → prompt on switch vs on poll).
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `DiagnosticsOrchestrator` cleanly owns realtime lint debounce, pending path, and active-tab guard — the right layer for scheduling logic (`diagnostics_search_coordinator.py:49–64`).
- External reload **Yes** path records local-history checkpoints for both discarded buffer and reloaded content, and discards drafts (`5455–5476`) — recoverability intent is sound.
- `_record_indent_source` updates status only when the affected path is the active tab (`5377–5379`) — avoids redundant status-bar churn.
- `map_indent_status_view` centralizes user-facing indent copy and tooltips (`status_bar.py:167–187`); HC/Light theming flows through `ShellStatusBarController.set_indent_status`.
- `PythonStyleWorkflow` demonstrates the target extraction shape for shell editor actions (`python_style_workflow.py:19–193`).
- Characterization tests exist for poll/tree signature filtering (`tests/unit/shell/test_project_tree_refresh_state.py`).

---

## Approval bar (this slice)

**Would not approve** further growth of indent/disk-sync/lint pass-through methods on `MainWindow` without (1) fixing the decline-reload dirty-state bug (finding 1), (2) extracting a single disk-sync workflow with unified revision and post-sync hooks (findings 2 and 6), and (3) **net-reducing** method count by deleting lint pass-throughs (finding 4) and indent orchestration (finding 3). Any dialog/workflow move must note four-theme validation status for external-change confirmation surfaces.
