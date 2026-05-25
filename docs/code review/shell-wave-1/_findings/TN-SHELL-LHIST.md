# TN-SHELL-LHIST — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-LHIST  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/local_history_workflow.py` (765 LOC), `app/shell/local_history_dialog.py` (533 LOC). Cross-read: `history_restore_picker.py`, `recovery_center_dialog.py`, `session_persistence.py`, `main_window.py` wiring (597–620, 5219, 5270–5279), `editor_tab_factory.py` (`maybe_restore_draft`), `unsaved_changes_dialog.py` (parallel token resolution). Handoff: R3.

---

## Executive verdict

**Not thermo-clean.** AD-015 extraction from `MainWindow` is real — checkpoints, autosave, dialogs, and recovery menus no longer live in the 5.5k-line monolith — but `LocalHistoryWorkflow` has become a **second orchestration monolith** that owns four unrelated domains (local history, draft autosave, per-project session persistence, recovery/global-history UI dispatch) and still reaches into debug breakpoint state. At **765 LOC** it has crossed the project's own 700-line smell threshold from the original deslop brief. The dialog module is cleaner (chrome + `DiffView`, lazy checkpoint loading, theme tokens), but draft recovery is implemented **twice** with divergent disk/buffer semantics that can mis-handle open dirty tabs. Dominant R3 risk: the next history/recovery feature will add another branch to an already crowded workflow instead of splitting ownership. Dialog surfaces appear four-theme capable when tokens are supplied; the Recovery Center draft path omits timestamp meta chips and relies on parent token fallback only.

---

### TN-SHELL-LHIST-1 — Four-domain god workflow past the 700-line smell bar

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:69-756` — single `LocalHistoryWorkflow` class spans checkpoint recording (`236-307`), autosave timer/flush (`502-575`), session persist/restore (`144-220`), global-history picker (`436-637`), recovery center (`639-739`), and draft review (`464-500`, `682-707`). File is **765 LOC**; deslop brief acceptance criterion was "under 700 lines" (`docs/deslop/AUDIT_app.md` Brief E).
- **Code-judo alternative:** Split by ownership boundary already implied by imports: `EditorSessionWorkflow` (persist/restore + cursor/scroll only), `DraftAutosaveWorkflow` (timer, flush, keep/discard on exit), `LocalHistoryOrchestrator` (checkpoints, transactions, restore-to-buffer), `RecoveryMenuWorkflow` (recovery center + global history dispatch). Each stays under ~300 LOC with narrow constructor surfaces.
- **Suggested remediation:** R3 slice: extract session + autosave first (lowest UI coupling), leave history/recovery orchestration in a slimmed workflow. Do not add methods to the current class until the split lands.
- **Tests that would prove fix:** Move existing `tests/unit/shell/test_session_persistence.py` and autosave characterization tests to construct the new modules directly; assert `LocalHistoryWorkflow` public surface shrinks to history/recovery only.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-2 — Session persistence and debug breakpoints live in the history workflow

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:144-220` — `persist_session_state` / `restore_session_state` read/write `SessionFileState` and mutate `self._breakpoints_by_file`, `self._breakpoint_specs_by_key`, call `ensure_breakpoint_spec`, `refresh_breakpoints_list`. Constructor accepts those debug ports at `92-95`, wired from `main_window.py:616-619`.
- **Code-judo alternative:** `EditorSessionWorkflow` owns open-tab/cursor/scroll restore; debug session restore is a **callback or `BreakpointStore` port** invoked once after tabs open — same SSOT fix as TN-SHELL-MW-01-6. Session JSON already lives in `session_persistence.py`; orchestration should sit beside it, not inside history.
- **Suggested remediation:** Move session methods to `app/shell/editor_session_workflow.py` (or extend `EditorWorkspaceController` if it already owns tab open/close). Drop breakpoint parameters from any workflow whose name contains "history."
- **Tests that would prove fix:** Session restore integration test passes with breakpoints injected via debug workflow only; `LocalHistoryWorkflow` constructible without breakpoint dicts.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-LHIST-3 — Constructor is relocation soup: 18+ injected callables

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:72-96` — fourteen required callables plus four optional debug/background ports. `main_window.py:597-620` wires each as a one-off lambda (`open_file_in_editor`, `set_current_tab_index`, `show_status_message`, etc.).
- **Code-judo alternative:** Typed host protocol bundle — e.g. `LocalHistoryEditorHost` with `editor_manager`, `open_file`, `apply_text`, `tab_index_for`, `refresh_tab`, `status_message`, `parent_widget` — mirroring `ProjectController`'s callback boundary. One object from composition root replaces the lambda grid.
- **Suggested remediation:** Introduce a small dataclass/protocol in `app/shell/local_history_ports.py`; collapse MainWindow wiring to a single host instance. Count MainWindow methods/lambdas removed, not added.
- **Tests that would prove fix:** Unit tests build workflow from a fake host stub without 15 constructor kwargs.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-4 — Duplicate draft recovery paths with divergent disk/buffer semantics

- **Persona:** TN-SHELL-LHIST
- **Severity:** BLOCKER
- **Evidence:** `app/shell/local_history_workflow.py:464-500` vs `682-707` — two separate flows construct `DraftRecoveryDialog`. `maybe_restore_draft` compares `draft_entry.content == tab_state.current_content` and passes `disk_text=tab_state.current_content` (`471-483`). `_review_draft_entry` uses `disk_text = tab_state.original_content` when tab is open (`684-686`) and short-circuits with `draft_entry.content == disk_text` (`693-696`), deleting the draft and showing "The draft already matches the saved file."
- **Code-judo alternative:** One private `_offer_draft_recovery(draft_entry, *, disk_text, buffer_text, editor_widget)` that always compares draft against **live buffer** for skip logic and uses **original_content** only as the diff "Saved on Disk" pane label. Delete `_review_draft_entry` body duplication.
- **Suggested remediation:** Unify both call sites through the helper; add unit test: open dirty tab (`current ≠ original`), draft equals `original_content` — must **not** auto-dismiss; dialog must show buffer vs draft.
- **Tests that would prove fix:** `tests/unit/shell/test_local_history_workflow.py` parametrized case: dirty tab + draft matching disk but not buffer → dialog shown, draft not deleted.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-5 — Triplicate restore-latest / open-timeline dispatch

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:628-637` and `673-680` — near-identical blocks load `latest_revision_id`, warn on failure, call `restore_local_history_content_to_buffer` or `show_local_history_for_entry`. Same action constants re-imported from `history_restore_picker` and `recovery_center_dialog`.
- **Code-judo alternative:** Single `_execute_history_action(summary: LocalHistoryFileSummary, action: str) -> None` on the workflow; both pickers become thin views that return `(summary, action)` tuples.
- **Suggested remediation:** Extract helper; consider whether `HistoryRestorePickerDialog` should be a filtered mode of `RecoveryCenterDialog` (history-only) to delete one picker class long-term.
- **Tests that would prove fix:** One unit test table drives `_execute_history_action` for both action enums; picker tests only assert selection → action mapping.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-6 — Global History and Recovery Center are parallel product surfaces with overlapping data

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:436-462` (`open_global_history` + async list) vs `639-680` (`open_recovery_center` sync list of drafts **and** history). Separate dialogs: `history_restore_picker.py`, `recovery_center_dialog.py`. Menu exposes both (`menu_wiring.py:97-98`).
- **Code-judo alternative:** Recovery Center as the single entry; "Global History" menu item opens the same dialog filtered to `RECOVERY_ENTRY_KIND_HISTORY`. Deletes async-only code path duplication and one dialog maintenance burden.
- **Suggested remediation:** R3 product decision first; if both menus stay, share list+action orchestration and async loading wrapper for both entry points.
- **Tests that would prove fix:** Integration test: global-history menu and recovery-center history row invoke identical restore behavior.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-7 — Misleading `record_transaction` empty guard

- **Persona:** TN-SHELL-LHIST
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/local_history_workflow.py:290-291` — `if not any(payload is not None for payload in payloads_by_path.values()): return`. Values are typed `str`; `None` never appears. Guard only catches an empty mapping, not empty strings.
- **Code-judo alternative:** `if not payloads_by_path:` or explicit `if all(not p.strip() for p in payloads_by_path.values()):` if whitespace-only payloads should skip.
- **Suggested remediation:** Replace with `if not payloads_by_path:` and document intent; add test if empty-string semantics matter.
- **Tests that would prove fix:** Unit test: `{}` no-ops; `{"a": ""}` behavior documented and asserted.
- **Handoff overlap:** none

---

### TN-SHELL-LHIST-8 — Dead helper and duplicated disk-mtime logic across modules

- **Persona:** TN-SHELL-LHIST
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/local_history_dialog.py:127-134` — `_disk_mtime_iso` is defined but never referenced in the module or repo. `app/shell/local_history_workflow.py:759-765` — `_resolve_disk_saved_at_iso` is the live copy used by `maybe_restore_draft` (`486`).
- **Code-judo alternative:** Delete `_disk_mtime_iso`; if dialog ever needs disk timestamps, import the workflow helper or move both to `session_persistence.py` / a shared `shell/time_format.py` next to `_format_relative`.
- **Suggested remediation:** Delete dead function in dialog cleanup PR; optionally co-locate mtime + relative timestamp helpers.
- **Tests that would prove fix:** Grep/compile check; no behavior change.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-9 — Recovery Center draft dialog omits meta chips and explicit tokens

- **Persona:** TN-SHELL-LHIST
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/local_history_workflow.py:697-702` — `DraftRecoveryDialog(..., parent=self._parent)` without `tokens`, `disk_saved_at`, or `draft_saved_at`. Contrast `481-488` in `maybe_restore_draft`, which passes all three plus `tokens=self._resolve_parent_tokens()`.
- **Code-judo alternative:** Always call the unified draft-recovery helper from finding 4; pass `draft_entry.saved_at`, `_resolve_disk_saved_at_iso(path)`, and resolved tokens so both entry paths render identical chrome/meta chips in all four theme modes.
- **Suggested remediation:** Fix as part of TN-SHELL-LHIST-4 unification; verify HC Light/Dark meta chip contrast manually per workspace UI rule.
- **Tests that would prove fix:** UI/characterization test asserts meta chip count > 0 for recovery-center path; theme integration test covers both entry paths.
- **Handoff overlap:** R3

---

### TN-SHELL-LHIST-10 — `LocalHistoryDialog` compare mode as ad-hoc string state

- **Persona:** TN-SHELL-LHIST
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/local_history_dialog.py:307`, `460-472`, `497-514` — `self._compare_mode = "current" | "previous"` with string equality branches and manual fallback to current when previous unavailable.
- **Code-judo alternative:** Module-level constants (mirror `DIFF_VIEW_MODE_*`) or a two-value enum; `_refresh_diff_view` dispatches on mode without nested string compares and repeated `_compare_current_button.setChecked(True)` escape hatches.
- **Suggested remediation:** Low-cost cleanup while touching dialog for R3 polish; optional extract of compare-toolbar builder alongside existing `_build_view_mode_toolbar`.
- **Tests that would prove fix:** Existing dialog tests stay green; optional unit test on mode dispatch pure function if extracted.
- **Handoff overlap:** R3

---

## Positive signals (not findings)

- `LocalHistoryDialog` uses `build_dialog_chrome`, `DiffView`, lazy `_loaded_checkpoint_contents` cache (`480-483`), and `_resolve_tokens` fallback chain — aligned with four-theme token discipline when tokens are passed.
- `DraftRecoveryDialog` disables restore when diff stats are empty (`276-285`) — good guard against no-op restores.
- Workflow correctly delegates persistence to `LocalHistoryStore`, `AutosaveStore`, and `record_local_history_transaction` rather than reimplementing storage.
- `open_global_history` async path via `GeneralTaskScheduler` (`436-462`) keeps UI thread off SQLite listing — appropriate boundary.
- Extraction from `MainWindow` is materially complete for call sites (no one-line `_record_local_history_*` delegators remain per deslop progress notes).

---

## Approval bar (this slice)

**Would not approve** R3 changes that add methods or branches to `LocalHistoryWorkflow` without (a) splitting session/autosave ownership out, (b) unifying draft recovery into one code path, and (c) net LOC reduction toward the sub-700 target. TN-SHELL-LHIST-4 is a presumptive **BLOCKER** until the dirty-tab dismissal bug is ruled out or fixed. Any new UI work must pass four-theme validation (Light, Dark, HC Light, HC Dark) on both `DraftRecoveryDialog` and `LocalHistoryDialog` entry paths.
