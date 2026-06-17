# TN-SHELL2-LHIST-DIFF — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-LHIST-DIFF  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**HEAD reviewed:** `430c56796089a8d25b082c44e1afa78e9a14d4ac` (no delta on slice files vs baseline)  
**Scope:** `app/shell/local_history_workflow.py` (674 LOC), `app/shell/local_history_dialog.py` (533 LOC), `app/shell/diff_view.py` (830 LOC), `app/shell/draft_autosave_workflow.py` (141 LOC), `app/shell/editor_session_workflow.py` (251 LOC). Cross-read: `main_window_composition.py` (`LocalHistoryWorkflow` wiring `:360-393`), `history_restore_picker.py`, `recovery_center_dialog.py`, `project_tree_action_workflow.py` (`LocalHistoryWorkflowPort`). Re-validate Shell Wave 1 **CC-05**, **CC-07**, **CC-21**.

---

## Executive verdict

**REJECT — not thermo-clean, but Wave 1 P0 document-safety on draft recovery is fixed.** Shell Wave 1 **CC-05** is **CLOSED**: `_offer_draft_recovery` is the single draft-recovery path for both tab-open (`maybe_restore_draft`) and Recovery Center (`_review_draft_entry`), with buffer-based skip logic and consistent tokens/meta chips; regression test `test_review_draft_entry_shows_dialog_when_draft_matches_disk_but_not_buffer` guards the dirty-tab dismissal bug. R3 partial extraction **landed**: `EditorSessionWorkflow` (251 LOC) and `DraftAutosaveWorkflow` (141 LOC) pulled session/autosave out of the history monolith; `local_history_workflow.py` is **674 LOC** (down from 765, now under the 700 smell bar). Dominant remaining risk: **`diff_view.py` at 830 LOC** is an undecomposed widget monolith (gutter painter, dual highlighters, side-by-side aligner, theme QSS) with **parser-only** unit tests; `LocalHistoryWorkflow` still owns **triplicate history-restore dispatch** and a **16+ callable constructor grid** with no typed host port (**CC-07 OPEN**). Do not add features to `diff_view.py` or grow history orchestration until decomposition and `_execute_history_action` consolidation land.

---

## Wave 1 CC re-validation

| CC | Wave 1 theme | Wave 2 status | Evidence |
|----|--------------|---------------|----------|
| **CC-05** | Draft recovery divergent paths (dirty-tab dismissal risk) | **CLOSED** | Unified `_offer_draft_recovery` (`local_history_workflow.py:596-634`); both call sites pass `disk_text=tab_state.original_content or tab_state.current_content`, `buffer_text=tab_state.current_content`; skip when `draft_entry.content == buffer_text` (`:608-609`); `DraftRecoveryDialog` always receives `tokens`, `disk_saved_at`, `draft_saved_at` (`:610-617`). Test: `test_review_draft_entry_shows_dialog_when_draft_matches_disk_but_not_buffer` (`test_local_history_workflow.py:165-226`). |
| **CC-07** | `window: Any` ceremonial workflows / injection soup | **OPEN** | Workflow modules avoid `window: Any`, but `LocalHistoryWorkflow.__init__` still accepts **16 required + 8 optional** injected callables (`:52-79`); `main_window_composition.py:360-393` wires each as a one-off lambda/`window._*` forwarder. No `LocalHistoryEditorHost` protocol (contrast `LocalHistoryWorkflowPort` in `project_tree_action_workflow.py:21` for delete snapshots only). Dead `ensure_breakpoint_spec` param still in signature and composition wire (`:73`, `main_window_composition.py:384`) — never stored or used after session split. |
| **CC-21** | R3 hotspot modules oversized | **PARTIAL** | **Improved:** `local_history_workflow.py` **674** (was 765); `editor_session_workflow.py` **251**; `draft_autosave_workflow.py` **141** — session/autosave extraction closed their LOC debt. **Residual:** `diff_view.py` **830** (≥700 hotspot, manifest high-gap); `local_history_dialog.py` **533** (dialog + compare toolbar still monolithic). Tests: workflow/autosave/session suites strong (`test_local_history_workflow.py` 423 LOC, `test_editor_session_workflow.py` 300 LOC); `test_diff_view.py` 126 LOC covers **parser only** — no `DiffView` widget/gutter/theme contract tests. |

---

### TN-SHELL2-LHIST-DIFF-1 — `diff_view.py` 830 LOC: widget monolith without decomposition plan

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `diff_view.py` **830 LOC** — single module owns `compute_diff_hunks` pure parser (`:93-168`), `_DiffInlineHighlighter`, `_PaneHighlighter`, `_GutterArea` QPainter gutter (`:282-420`), `DiffView` stacked inline/side-by-side builders (`:423-669`), and `_side_by_side_buffers` aligner (`:721-806`). Manifest kickoff flags **high test gap**; only file in history/diff slice above 700 LOC.
- **Code-judo alternative:** Split by layer: `diff_parser.py` (~180 LOC: hunks/stats/types), `diff_gutter.py` (~140 LOC: `_GutterArea`), `diff_highlighters.py` (~90 LOC), `diff_view_widget.py` (~250 LOC: `DiffView` orchestration). Re-export from `diff_view.py` shim for one release, then hard cutover.
- **Suggested remediation:** First LHIST-DIFF wave PR: split only — no new diff modes. Cap each child **< 400 LOC**; parent shim **< 50 LOC** or delete after cutover.
- **Tests that would prove fix:** Existing `test_diff_view.py` imports move to `diff_parser`; add one characterization test that `DiffView.set_texts` + `apply_theme` round-trip without painting private attrs.
- **Handoff overlap:** R3, CC-21, architecture gate §2 (≥700 LOC)

---

### TN-SHELL2-LHIST-DIFF-2 — CC-21 PARTIAL: R3 session/autosave split landed; history orchestrator still crowded

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** NEW (improvement vs Wave 1)
- **Severity:** STRUCTURAL
- **Evidence:** Wave 1 `TN-SHELL-LHIST-1` — 765 LOC four-domain god workflow. Current: `EditorSessionWorkflow` (`editor_session_workflow.py:26-216`) owns persist/restore + batched tab open; `DraftAutosaveWorkflow` (`draft_autosave_workflow.py:42-141`) owns timer/flush; `LocalHistoryWorkflow` delegates via `self._session_workflow` / `self._draft_autosave` (`local_history_workflow.py:98-121`, `:144-148`, `:430-462`). Net LOC on history file **674** — under 700 bar but still bundles checkpoints, global history, recovery center, and draft review (`:164-567`).
- **Code-judo alternative:** Extract `RecoveryOrchestrator` (~200 LOC) for `_recovery_center_entries`, `open_recovery_center`, `_open_global_history_picker`, and shared history-action dispatch; leave `LocalHistoryWorkflow` as checkpoint/restore API + thin facade.
- **Suggested remediation:** Next R3 slice after `diff_view` split: recovery/history dispatch module; target history facade **< 450 LOC**.
- **Tests that would prove fix:** Existing workflow tests stay green; new module constructible without autosave/session deps.
- **Handoff overlap:** R3, CC-21, TN-SHELL-LHIST-1 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-3 — CC-07 OPEN: `LocalHistoryWorkflow` constructor remains lambda relocation soup

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `local_history_workflow.py:52-79` — fourteen required callables + eight optional ports. `main_window_composition.py:360-393` — **34 lines** of `lambda`/`window._*` wiring (editor factory, tab workflow, debug breakpoints, tree presenter). `ensure_breakpoint_spec` accepted at `:73` but **never assigned** — composition still passes `window._debug_control_workflow.ensure_breakpoint_spec` (`main_window_composition.py:384`) after breakpoints moved to `EditorSessionWorkflow` via `breakpoint_store`.
- **Code-judo alternative:** Introduce `LocalHistoryEditorHost` protocol/dataclass (`editor_manager`, `open_file`, `apply_text`, `tab_index_for`, `refresh_tab`, `status_message`, `parent_widget`, `theme_tokens`) built once in composition; delete per-field lambdas and dead `ensure_breakpoint_spec`.
- **Suggested remediation:** One PR: host port + remove dead breakpoint param; count net lambda lines removed from `main_window_composition.py`.
- **Tests that would prove fix:** `LocalHistoryWorkflow` unit tests build from fake host stub with **≤5** constructor kwargs beyond stores/logger.
- **Handoff overlap:** CC-07, CC-SHELL2-typed-hosts (INTEG), R2, TN-SHELL-LHIST-3 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-4 — Triplicate history restore / open-timeline dispatch

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Near-identical restore-latest / open-timeline blocks: `_open_global_history_picker` (`local_history_workflow.py:515-524`) vs `open_recovery_center` history branch (`:560-567`). Separate action constant imports from `history_restore_picker` and `recovery_center_dialog` (`:33-45`). Same load-check-restore / show-timeline pattern duplicated with only dialog type differing.
- **Code-judo alternative:** Single `_execute_history_action(summary: LocalHistoryFileSummary, action: str) -> None`; both pickers return `(summary, action)` tuples. Long-term: Recovery Center filtered to history-only replaces Global History menu duplicate (`TN-SHELL-LHIST-6`).
- **Suggested remediation:** Extract helper in same PR as recovery orchestrator split (TN-SHELL2-LHIST-DIFF-2).
- **Tests that would prove fix:** One parametrized unit test drives `_execute_history_action` for both action enums.
- **Handoff overlap:** R3, TN-SHELL-LHIST-5 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-5 — Global History and Recovery Center: parallel product surfaces, overlapping orchestration

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `open_global_history` async list + picker (`local_history_workflow.py:373-524`) vs `open_recovery_center` sync merge of drafts + history (`:526-567`). Separate dialog classes maintained; menu exposes both (per Wave 1 `menu_wiring.py:97-98` — unchanged at baseline).
- **Code-judo alternative:** Recovery Center as single entry; "Global History" opens same dialog filtered to `RECOVERY_ENTRY_KIND_HISTORY` — deletes async-only picker path and one dialog class long-term.
- **Suggested remediation:** Product decision first; if both menus stay, share list+action orchestration and async loading wrapper for both entry points.
- **Tests that would prove fix:** Integration test: global-history menu and recovery-center history row invoke identical restore behavior.
- **Handoff overlap:** R3, TN-SHELL-LHIST-6 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-6 — `diff_view` widget layer: high test gap (parser-only coverage)

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `tests/unit/shell/test_diff_view.py` — **126 LOC**, **8 tests**, all target `compute_diff_hunks` and `_format_relative` (imported from dialog). File header explicitly excludes "Visual layout, gutter painting, and stylesheet output." No `DiffView` instantiation tests. `tests/integration/shell/test_local_history_theme_integration.py` — one dialog open smoke under light/dark only (not HC modes; not gutter/mode switch).
- **Code-judo alternative:** After `diff_parser` extraction, add risk-first tests at widget seam: `DiffView.set_mode` + `set_texts` + `stats()` + `toPlainText()` stable contract; theme integration extends to HC Light/Dark per workspace UI rule.
- **Suggested remediation:** Bundle widget contract tests with `diff_view` decomposition PR; do not add private `_GutterArea` probing.
- **Tests that would prove fix:** Parametrized inline/side-by-side mode test asserts `stats()` and `raw_diff_text()` without QWidget paint inspection.
- **Handoff overlap:** R6, CC-21, manifest P5 high-gap row

---

### TN-SHELL2-LHIST-DIFF-7 — Misleading `record_transaction` empty guard

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `local_history_workflow.py:218-219` — `if not any(payload is not None for payload in payloads_by_path.values()): return`. Values are typed `str`; `None` never appears. Guard only catches empty mapping, not empty strings — same smell as Wave 1 `TN-SHELL-LHIST-7`.
- **Code-judo alternative:** `if not payloads_by_path:` or explicit `if all(not p.strip() for p in payloads_by_path.values()):` if whitespace-only payloads should skip.
- **Suggested remediation:** Replace with `if not payloads_by_path:` when next touching transaction path.
- **Tests that would prove fix:** Unit test: `{}` no-ops; `{"a": ""}` behavior documented and asserted.
- **Handoff overlap:** none

---

### TN-SHELL2-LHIST-DIFF-8 — Dead `_disk_mtime_iso` in dialog; live copy in workflow module

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `local_history_dialog.py:127-134` — `_disk_mtime_iso` defined, **never referenced** in module or repo (`rg '_disk_mtime_iso' app/` → definition only). Live helper `_resolve_disk_saved_at_iso` at `local_history_workflow.py:668-674` used by `_offer_draft_recovery` (`:615`).
- **Code-judo alternative:** Delete dead dialog helper; if dialog needs disk timestamps, import workflow helper or move both to `session_persistence.py` / shared timestamp util next to `_format_relative`.
- **Suggested remediation:** Delete in next dialog cleanup PR (hard-cutover bias).
- **Tests that would prove fix:** Grep/compile check; no behavior change.
- **Handoff overlap:** R3, TN-SHELL-LHIST-8 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-9 — `LocalHistoryDialog` compare mode as ad-hoc string state

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `local_history_dialog.py:307`, `460-472`, `497-514` — `self._compare_mode = "current" | "previous"` with string equality branches and manual `_compare_current_button.setChecked(True)` escape when previous unavailable.
- **Code-judo alternative:** Module-level constants (mirror `DIFF_VIEW_MODE_*`) or two-value enum; `_refresh_diff_view` dispatches on mode without nested string compares.
- **Suggested remediation:** Low-cost cleanup while touching dialog for R3 polish.
- **Tests that would prove fix:** Existing dialog tests stay green; optional pure dispatch test if extracted.
- **Handoff overlap:** R3, TN-SHELL-LHIST-10 (Wave 1)

---

### TN-SHELL2-LHIST-DIFF-10 — CC-05 CLOSED: unified draft recovery with dirty-tab regression test

- **Persona:** TN-SHELL2-LHIST-DIFF
- **Status:** NEW (closure vs Wave 1 BLOCKER)
- **Severity:** (positive — not a finding debt item)
- **Evidence:** Wave 1 `TN-SHELL-LHIST-4` BLOCKER — divergent `maybe_restore_draft` vs `_review_draft_entry` semantics. Current single `_offer_draft_recovery` (`local_history_workflow.py:596-634`); buffer-based skip (`:608-609`); meta chips/tokens on all paths (`:610-617`). `test_review_draft_entry_shows_dialog_when_draft_matches_disk_but_not_buffer` asserts dialog shown when draft matches disk but not buffer; draft not deleted (`test_local_history_workflow.py:165-226`).
- **Code-judo alternative:** N/A — fix landed; preserve helper on future entry points.
- **Suggested remediation:** None for CC-05; gate new recovery UI through `_offer_draft_recovery` only.
- **Tests that would prove fix:** Already present; extend only if new entry points added.
- **Handoff overlap:** CC-05, TN-SHELL-LHIST-4 (Wave 1)

---

## Positive signals (not findings)

- `EditorSessionWorkflow` batched restore (`SESSION_RESTORE_BATCH_SIZE = 2`, `:159-187`) keeps UI responsive; breakpoints via `BreakpointStore` port (`:133-137`) — debug coupling removed from history class name.
- `DraftAutosaveWorkflow` uses typed `_AutosaveTimer` protocol (`draft_autosave_workflow.py:26-39`) — testable without real `QTimer`.
- `DraftRecoveryDialog` disables restore when diff stats empty (`local_history_dialog.py:276-285`) — good no-op guard.
- `LocalHistoryDialog` lazy `_loaded_checkpoint_contents` cache (`:480-483`), `build_dialog_chrome`, token fallback chain — four-theme capable when tokens supplied.
- `compute_diff_hunks` pure API with typed `DiffHunk`/`DiffStats` models — strong parser test surface (`test_diff_view.py`).
- `ProjectTreeActionCoordinator` depends on `LocalHistoryWorkflowPort` protocol for delete snapshots — partial typed boundary exists.

---

## Approval bar (this slice)

| Gate | Result |
|------|--------|
| CC-05 remains CLOSED | **PASS** |
| CC-07 host typing for history workflow | **FAIL** — OPEN |
| CC-21 decomposition (history/autosave/session/diff) | **PARTIAL** — session/autosave split done; `diff_view` 830 LOC unresolved |
| No file in slice >1k LOC | **PASS** (`diff_view` 830) |
| No REGRESSION on Wave 1 P0 draft recovery | **PASS** |
| Widget-layer test gap closed | **FAIL** |

**Verdict: REJECT.** Wave 1 P0 **CC-05** closure is real and must not regress, but the history/diff slice fails the thermo-clean bar: **`diff_view.py` is the dominant ≥700 hotspot** with parser-only tests; history orchestration still carries **triplicate dispatch** and **untyped 16+ callable injection** (**CC-07**). Do not add diff modes or recovery features until `diff_view` layer split and `_execute_history_action` / host-port consolidation land (R3/CC-21/CC-07 track).
