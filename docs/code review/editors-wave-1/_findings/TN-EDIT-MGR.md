# TN-EDIT-MGR — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-MGR  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/editor_manager.py` (295 LOC), `app/editors/editor_tab.py` (59 LOC), `app/editors/editorconfig.py` (101 LOC), `app/editors/indentation.py` (82 LOC), `app/editors/formatting_service.py` (30 LOC). Cross-read: `app/shell/save_workflow.py` (329 LOC), `app/shell/python_style_workflow.py` (327 LOC). Focus: tab/disk SSOT, dirty tracking, `atomic_write`, format-on-save seam, dedupe open paths.

---

## Executive verdict

**Not thermo-clean — `EditorManager` + `EditorTabState` are a credible tab/disk core, but the shell integration undermines the SSOT model the manager is trying to own.** Path dedupe via resolved keys, dirty baseline on `original_content`, and `atomic_write_text` in `save_tab` are the right primitives; `formatting_service`, `editorconfig`, and `indentation` are small, pure, and well-bounded. Dominant risks: **dual text authority** (`EditorTabState.current_content` vs `CodeEditorWidget.toPlainText()`) with format-on-save relying on a Qt signal round-trip instead of an explicit manager update; **split format read/write paths** between `SaveWorkflow` (tab-first) and `PythonStyleWorkflow` (widget-first); **side-effectful `stale_open_paths`** mutating mtime snapshots during poll; and **~40 lines of duplicated open/dedupe logic** in `open_file` / `open_file_with_content`. No scoped file crosses 1k LOC; no AD-016/AD-018 violations in this slice. **REJECT** until `_apply_text_to_open_tab` and format actions route through one explicit tab-content API, `stale_open_paths` becomes a pure query, and open/dedupe paths collapse to a single internal helper.

---

### TN-EDIT-MGR-1 — Format-on-save updates widget but persists tab via implicit signal sync

- **Persona:** TN-EDIT-MGR
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/save_workflow.py:258-319,176-189` — `apply_save_transforms` reads `tab_state.current_content`, then calls `window._apply_text_to_open_tab(file_path, transformed_text)` before `editor_manager.save_tab(file_path)`. `app/shell/main_window.py:383-392` — when a widget exists, `_apply_text_to_open_tab` calls `editor_widget.replace_document_text(replacement_text)` and **returns without** `editor_manager.update_tab_content`. `app/editors/code_editor_editing.py:203-207` — `replace_document_text` mutates the document via `insertText`, which emits `textChanged`; tab sync depends on `editor_tab_factory.py:153-177` wiring to `handle_editor_text_changed`.
- **Code-judo alternative:** Make `EditorManager` the sole write authority: add `replace_tab_content(file_path, content, *, mark_dirty: bool = True)` that sets `current_content` and returns the tab; `_apply_text_to_open_tab` always updates manager first, then mirrors to widget if present. Delete the signal round-trip from the save critical path.
- **Suggested remediation:** Refactor `_apply_text_to_open_tab` to call `update_tab_content` (or new replace API) before widget mirror; add a unit test where widget exists and save-on-format persists transformed bytes without relying on `textChanged`.
- **Tests that would prove fix:** Extend `test_main_window_format_actions.py` with a fake widget that does **not** emit `textChanged`; assert saved disk content matches transformed text.
- **Handoff overlap:** TN-EDIT-SHELL-FACTORY, CC-EDIT (tab SSOT theme)

---

### TN-EDIT-MGR-2 — Manual format reads widget; save reads tab — split SSOT for the same buffer

- **Persona:** TN-EDIT-MGR
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/python_style_workflow.py:81-89,123-128` — `handle_format_current_file_action` pulls `source_text = editor_widget.toPlainText()` and writes back via `editor_widget.replace_document_text`, never consulting `EditorManager`. `app/shell/save_workflow.py:260-264` — `apply_save_transforms` reads `tab_state.current_content`. `app/shell/editor_tab_workflow.py:399-403` — keystroke sync is widget → manager only on `textChanged`.
- **Code-judo alternative:** One canonical read: `editor_manager.get_tab(path).current_content` (or `active_tab_content()` helper). Format actions update via manager API + optional widget mirror helper shared with save path. Widget becomes a view; manager owns buffer text.
- **Suggested remediation:** Route `PythonStyleWorkflow` format/organize through `SaveWorkflow`-style tab read + `_apply_text_to_open_tab`; or extract `EditorBufferCoordinator` used by both workflows.
- **Tests that would prove fix:** Characterization test: tab and widget diverge (tab updated without widget signal); manual format uses tab content or fails loudly; save and format agree on source.
- **Handoff overlap:** TN-EDIT-SHELL-TAB, CC-EDIT

---

### TN-EDIT-MGR-3 — `open_file` and `open_file_with_content` duplicate dedupe/preview/promotion orchestration

- **Persona:** TN-EDIT-MGR
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/editor_manager.py:32-49` vs `72-97` — identical blocks for normalized-path lookup, preview promotion, `_active_file_path` assignment, and `OpenedTabResult(was_already_open=True, ...)`. Lines `51-70` vs `99-118` repeat preview-close + register + order append + preview tracking with only content source differing (disk read vs constructor).
- **Code-judo alternative:** Extract `_open_or_activate_tab(normalized_path, *, preview, content_factory)` where `content_factory` is `None` for dedupe-only, or returns `(content, original, mtime)` for new tabs. One code path owns dedupe, promotion, preview replacement, and order insertion.
- **Suggested remediation:** Private helper collapse in `editor_manager.py`; existing `test_editor_manager.py` dedupe/preview tests remain the regression gate.
- **Tests that would prove fix:** All current `test_editor_manager.py` cases pass unchanged; `wc -l editor_manager.py` drops ~25–35 LOC.
- **Handoff overlap:** none

---

### TN-EDIT-MGR-4 — `stale_open_paths` mutates tab state during a poll query

- **Persona:** TN-EDIT-MGR
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/editor_manager.py:201-214` — loop calls `tab.set_last_known_mtime(current_mtime)` when `tab.last_known_mtime is None`, then `continue`. Invoked from `app/shell/editor_tab_workflow.py:768-773` on every external-change poll. A read/query API silently establishes mtime baselines, making poll order affect staleness results.
- **Code-judo alternative:** Split into pure `stale_open_paths()` (compare only; no mutation) and explicit `initialize_mtime_baselines()` at open/refresh time. `open_file` / `refresh_open_tabs_from_disk` already set mtime; poll should not backfill as side effect.
- **Suggested remediation:** Move baseline init to `from_file` / `acknowledge_disk_mtime` callers; make `stale_open_paths` read-only; adjust `test_stale_open_paths_reports_disk_modified_files` if it relied on implicit init (it should not — open sets mtime).
- **Tests that would prove fix:** Test that calling `stale_open_paths` twice without intervening disk change returns identical results and does not mutate `last_known_mtime` on tabs opened with `None` baseline.
- **Handoff overlap:** TN-EDIT-SHELL-TAB

---

### TN-EDIT-MGR-5 — Preview promotion logic triplicated across manager and tab workflow

- **Persona:** TN-EDIT-MGR
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/editor_manager.py:39-43,87-91,158-161,189-192` — promotion on reopen, content edit, and explicit `promote_tab`. `app/shell/editor_tab_workflow.py:403-408` — after `update_tab_content` (which already promotes preview when dirty at `:158-161`), calls `promote_preview_tab` again when `tab_state.is_preview and tab_state.is_dirty` (unreachable after manager promote). `app/shell/editor_tabs_coordinator.py:48-55` — thin delegate back to workflow for UI refresh.
- **Code-judo alternative:** Manager owns preview lifecycle exclusively; shell reacts to `OpenedTabResult.promoted_from_preview` / tab state flags for presentation only. Delete redundant `promote_preview_tab` call in `handle_editor_text_changed`.
- **Suggested remediation:** Remove dead branch in `handle_editor_text_changed`; document manager as sole preview authority in `ARCHITECTURE.md` editor section.
- **Tests that would prove fix:** `test_editing_preview_tab_promotes_to_permanent` unchanged; grep shows single promotion trigger on edit path.
- **Handoff overlap:** TN-EDIT-SHELL-TAB

---

### TN-EDIT-MGR-6 — Format-on-save and manual format duplicate pipeline orchestration

- **Persona:** TN-EDIT-MGR
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/save_workflow.py:265-316` — `format_text_basic` → optional isort → optional Black via workflow broker, with guardrail and warning aggregation. `app/shell/python_style_workflow.py:89-128,146-167` — parallel broker calls for manual format/organize with separate QMessageBox UX. Both import `format_text_basic` from `app/editors/formatting_service.py` but compose Python tooling independently.
- **Code-judo alternative:** Extract `EditorTextTransformPipeline` (pure: settings + text in → transformed text + warnings out) in `app/editors/` or `app/shell/editor_transforms.py`; `SaveWorkflow` and `PythonStyleWorkflow` differ only in UX (silent vs dialog). Keeps format-on-save seam testable without MainWindow.
- **Suggested remediation:** Single pipeline module; save path passes `show_warnings` flag; manual path reuses pipeline then handles dialogs.
- **Tests that would prove fix:** Pipeline unit tests cover guardrail, isort-then-black ordering, failure retention; both workflows become thin wrappers.
- **Handoff overlap:** TN-EDIT-SHELL-FACTORY

---

### TN-EDIT-MGR-7 — `EditorTabState` dirty model and `atomic_write` placement are correct (positive control)

- **Persona:** TN-EDIT-MGR
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/editor_tab.py:39-51` — dirty = `current_content != original_content`; `mark_saved` resets baseline and mtime snapshot. `app/editors/editor_manager.py:164-170` — save path uses `atomic_write_text` then `mark_saved`; failure leaves dirty state (`test_save_tab_keeps_dirty_state_when_atomic_write_fails`). Path keys normalized via `Path(...).resolve()` for dedupe (`test_open_file_is_deduplicated_and_marks_active_tab`).
- **Code-judo alternative:** Preserve this as the disk SSOT contract; extend it upward so widget/shell never bypass manager on write.
- **Suggested remediation:** Document in architecture: manager owns persisted baseline; widget is projection.
- **Tests that would prove fix:** Existing `tests/unit/editors/test_editor_manager.py` (17 cases) remain green.
- **Handoff overlap:** CC-PROJ-13 (persistence primitives)

---

### TN-EDIT-MGR-8 — `editorconfig`, `indentation`, `formatting_service` are appropriately scoped pure modules

- **Persona:** TN-EDIT-MGR
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/formatting_service.py:16-30` — deterministic, no Qt, returns `FormatResult`. `app/editors/editorconfig.py:19-63` — nearest-file walk + fnmatch, no shell imports. `app/editors/indentation.py:13-47` — content inference with bounded sample. Consumption lives in `editor_tab_workflow.apply_detected_indentation_for_widget` (`:653-699`), not in manager — acceptable boundary (indent is view preference, not tab/disk state).
- **Code-judo alternative:** Keep these modules as-is; do not fold into `editor_manager.py`. If indentation resolution grows, add `indentation_policy.py` rather than expanding manager.
- **Suggested remediation:** None required for this wave beyond SSOT fixes above.
- **Tests that would prove fix:** `test_editorconfig.py`, `test_indentation.py`, `test_formatting_service.py` continue to pass.
- **Handoff overlap:** none

---

### TN-EDIT-MGR-9 — `save_all` / multi-tab save lacks batch atomicity across files

- **Persona:** TN-EDIT-MGR
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/editor_manager.py:216-225` — iterates dirty tabs, calls `save_tab` per path; mid-loop failure leaves earlier tabs saved and later tabs dirty. `app/persistence/atomic_write.py:53-67` exposes `atomic_write_batch` with rollback, unused by editor save paths. `app/shell/save_workflow.py:139-148` — `handle_save_all_action` same sequential pattern.
- **Code-judo alternative:** For Save All, either document best-effort partial save (current behavior) explicitly, or route multi-file saves through `atomic_write_batch` when orchestrating project-wide operations. Single-tab save stays as-is.
- **Suggested remediation:** Product decision: if Save All should be all-or-nothing, wire batch helper; otherwise add docstring contract on partial success.
- **Tests that would prove fix:** Integration test: simulated failure on second tab leaves first tab persisted (current) or rolls back (if batch adopted).
- **Handoff overlap:** CC-PROJ-13

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| Tab/disk SSOT | **Partial** — manager owns baseline + atomic write; shell/widget bypass on read/write |
| Dirty tracking | **Good** — simple string equality on `EditorTabState` |
| Path dedupe | **Good** — resolved-path dict keys; tests cover preview replacement |
| `atomic_write` | **Good** — canonical in `EditorManager.save_tab`; failure preserves dirty |
| Format-on-save seam | **Split** — transforms in `SaveWorkflow`, basic format in `formatting_service`, manual path in `PythonStyleWorkflow` |
| 1k-line rule | **Clear** — largest scoped file `save_workflow.py` 329 LOC |
| Pure editor modules | **Good** — `editorconfig`, `indentation`, `formatting_service` earn their files |

---

## Verdict

**REJECT** — Core manager/tab modules are small and test-backed, but thermo-clean tab/disk SSOT requires fixing the widget-orchestrated write path (TN-EDIT-MGR-1, TN-EDIT-MGR-2) and collapsing duplicated open/format orchestration (TN-EDIT-MGR-3, TN-EDIT-MGR-6) before this wave closes. Ship TN-EDIT-MGR-1 through TN-EDIT-MGR-4 as P1; preview dedupe and batch-save clarity are P2. Positive controls (TN-EDIT-MGR-7, TN-EDIT-MGR-8) should be preserved as the target architecture, not replaced.
