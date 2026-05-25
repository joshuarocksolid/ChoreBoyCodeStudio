# TN-SHELL-MW-10 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-10  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 3828–4223 — assigned slice (Python Console completion, debug inspector, REPL/run event queues, problems merge, shutdown hooks touching search worker). Cross-read for search-in-files sidebar and result navigation: `app/shell/search_sidebar_widget.py`, `app/shell/main_window_panels.py` (signal wiring), `app/shell/diagnostics_search_coordinator.py`, and adjacent `main_window.py` lines 4224–4249, 4380–4382, 4422–4438, 4835–4841.

---

## Executive verdict

**Not thermo-clean.** The assigned line range is **mostly not search** (~90% REPL/run-event/problems plumbing); search-in-files was extracted to `SearchSidebarWidget`, but `MainWindow` still carries a **ghost second search pipeline** (`_active_search_worker`, `SearchResultsCoordinator`, `_set_search_results` → Problems panel) with **zero production callers** for the async dispatch path. Shutdown cancels the never-assigned MainWindow worker while the **live** sidebar worker is untouched. Result navigation is three one-line delegators duplicating the problems-panel pattern instead of a shared open-at-line port. The slice also contains **agent debug instrumentation** (`#region agent log`, hardcoded `.cursor/debug-*.log` path) embedded in `_request_python_console_completion_async` — accidental complexity unrelated to search that must not ship. Four-theme impact: sidebar delegate defaults hardcode light-theme hex colors until `apply_theme_tokens` runs; QSS lives in `shell_section_search_sidebar` — any extraction must preserve token plumbing and re-check HC Light/HC Dark.

---

### TN-SHELL-MW-10-1 — Ghost MainWindow search pipeline parallel to `SearchSidebarWidget`

- **Persona:** TN-SHELL-MW-10
- **Severity:** STRUCTURAL
- **Evidence:** Production search runs entirely inside `SearchSidebarWidget._run_search` → `SearchWorker` (`search_sidebar_widget.py:533-560`). On `MainWindow`, `_active_search_worker` is declared (`main_window.py:536`) and cleared on shutdown (`4380-4382`) but **never assigned** in production (grep: only `test_main_thread_dispatcher.py:114` sets it). `_schedule_search_results_update` (`4239-4244`), `_handle_search_worker_done` (`4246-4249`), and `_set_search_results` → `_problems_panel.set_results(f"Search: {query}", ...)` (`4224-4237`) have **no production callers**; only unit tests invoke the schedule/done helpers. `SearchResultsCoordinator` (`diagnostics_search_coordinator.py:117-130`) is a one-line dispatch wrapper wired at init (`main_window.py:646-649`) for a path that nothing uses.
- **Code-judo alternative:** Hard cutover — delete `_active_search_worker`, `_schedule_search_results_update`, `_handle_search_worker_done`, `_set_search_results`, and `SearchResultsCoordinator`; remove Problems-panel-as-search-results UX (only reference: `main_window.py:4236`). Single owner: `SearchSidebarWidget` (+ optional thin `SearchWorkflow` if MainWindow must stay dumb).
- **Suggested remediation:** One deletion PR; update/delete `tests/unit/shell/test_main_thread_dispatcher.py` search-worker tests that exist only to guard dead code. Net **method count down** on `MainWindow`.
- **Tests that would prove fix:** Grep/characterization: no `Search:` results title in runtime paths; sidebar integration test still opens file on activate; shutdown during active sidebar search does not crash (pairs with finding 4).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-10-2 — Agent debug logging embedded in production MainWindow hot path

- **Persona:** TN-SHELL-MW-10
- **Severity:** BLOCKER
- **Evidence:** `main_window.py:3843-3907` — `#region agent log` block inside `_request_python_console_completion_async`: inline imports (`json`, `threading`, `time`, `traceback`), hardcoded `_AGENT_LOG_PATH = "/home/joshua/Documents/ChoreBoyCodeStudio/.cursor/debug-0b96d3.log"`, nested `_agent_log_mw`, and try/except wrappers around `_repl_manager.complete` and UI apply that exist solely for logging. Swallows all logging failures silently; adds thread/work noise on every completion request.
- **Code-judo alternative:** Delete the entire `#region agent log` block. If telemetry is needed, use `self._logger.debug(...)` behind existing `metrics_logging_enabled` or structured logging — no filesystem path, no inline imports, no structural wrapping of business logic.
- **Suggested remediation:** Immediate removal before any shell-wave merge; not R2 backlog — this is debug slop in the assigned slice.
- **Tests that would prove fix:** Existing REPL/completion tests pass unchanged; grep confirms no `.cursor/debug-` paths under `app/`.
- **Handoff overlap:** none

---

### TN-SHELL-MW-10-3 — Search lifecycle split: shutdown cancels dead worker, ignores live sidebar worker

- **Persona:** TN-SHELL-MW-10
- **Severity:** STRUCTURAL
- **Evidence:** `_begin_shutdown_teardown` (`main_window.py:4380-4382`) cancels `self._active_search_worker` (never set in production — see finding 1). `SearchSidebarWidget` owns `self._active_worker` (`search_sidebar_widget.py:269`, cancel at `534-535`) with **no** `shutdown()`/`closeEvent` hook and no call from MainWindow teardown. Window close during an in-flight project search can leave a daemon thread invoking `_on_search_results` → `_apply_results_requested` after partial teardown.
- **Code-judo alternative:** Either (a) sidebar exposes `cancel_active_search()` called from `_begin_shutdown_teardown`, or (b) delete MainWindow worker field and add `SearchSidebarWidget.shutdown()` invoked once from teardown — one cancellation site, one worker owner.
- **Suggested remediation:** Pair with finding 1 hard cutover; wire teardown to sidebar cancel, not ghost field.
- **Tests that would prove fix:** Unit test: construct sidebar, start search with slow stub worker, call shutdown/cancel, assert no apply callback after cancel; optional slow integration on window close.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-10-4 — Result navigation is duplicated one-line delegators, not a shared navigation port

- **Persona:** TN-SHELL-MW-10
- **Severity:** STRUCTURAL
- **Evidence:** Search signals wired in `main_window_panels.py:88-89` to `_handle_search_preview_file_at_line` / `_handle_search_open_file_at_line` (`main_window.py:4434-4438`) — each forwards to `_open_file_at_line(..., preview=...)`. Identical pattern for problems panel: `_handle_problem_item_preview` / `_handle_problem_item_activation` (`4323-4331`). Four methods, one behavior: open-or-preview at line.
- **Code-judo alternative:** Single bound method or small `EditorNavigationPort` with `open_at_line(path, line, *, preview: bool)`; connect `SearchSidebarWidget.preview_file_at_line`, `open_file_at_line`, and problems panel signals directly (or via one lambda each). Delete four private handlers; satisfies handoff “no new one-line delegators” in reverse by removing four.
- **Suggested remediation:** R2 shell extraction — collapse during `EditorWorkspaceController` / navigation workflow pass; do not add a fifth delegator for the next panel.
- **Tests that would prove fix:** Existing `test_search_sidebar_widget.py` signal tests unchanged; problems-panel activation tests still reach editor at line via shared port.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-10-5 — `SearchResultsCoordinator` is a pass-through that buys nothing

- **Persona:** TN-SHELL-MW-10
- **Severity:** STRUCTURAL
- **Evidence:** `diagnostics_search_coordinator.py:117-130` — entire class is `schedule_results_update` → `_dispatch_to_main_thread(lambda: self._set_search_results(...))`. `_schedule_search_results_update` on MainWindow duplicates the fallback when coordinator is `None` (`main_window.py:4240-4243`). Coordinator exists only to test thread dispatch (`test_main_thread_dispatcher.py:85-105`) for dead search path (finding 1).
- **Code-judo alternative:** Delete coordinator with ghost search path; if async search results ever return to Problems panel, dispatch at the worker callback site once — no intermediate 13-line class.
- **Suggested remediation:** Delete in same PR as finding 1; do not extract to another file.
- **Tests that would prove fix:** Remove coordinator-specific tests; keep generic `_dispatch_to_main_thread` tests only.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-10-6 — Assigned slice boundary obscures search ownership (file sprawl on `MainWindow`)

- **Persona:** TN-SHELL-MW-10
- **Severity:** STRUCTURAL
- **Evidence:** Lines 3828–4223 contain Python Console completion (`3833-3912`), debug inspector (`3919-3950`), REPL queue (`4032-4088`), run output coordinator lazy init (`4090-4124`), run event fan-out (`4126-4177`), and problems merge (`4203-4222`). Search-specific MainWindow code in/near slice: ghost worker teardown (`4380-4382`, just past end), `_set_search_results` starts at `4224` (next critic slice). Real search UI/logic: `search_sidebar_widget.py` (670 lines). `MainWindow` is **5,549 lines / ~332 methods** — search concerns scattered across init, theme, settings apply, find-in-files action (2033-2045), project reload (2746-2752, 4819-4821), and orphaned results API.
- **Code-judo alternative:** Treat `SearchSidebarWidget` + `search_panel.py` as the search subsystem; MainWindow retains only: activity-bar view switch (`4422-4430`), project-root/exclude push (`set_project_root` / `set_exclude_patterns`), and direct signal → navigation port (finding 4). Document slice map accordingly for wave-2 critics.
- **Suggested remediation:** R2 — no new search methods on `MainWindow`; consolidate project-root/exclude updates into one `refresh_search_sidebar_context()` called from project open/reload/settings.
- **Tests that would prove fix:** Single call site test for exclude/root push after project open + settings apply (extends TN-SHELL-MW-05-2 dedup theme).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-10-7 — `SearchResultDelegate` hardcodes theme colors; four-theme gap until tokens applied

- **Persona:** TN-SHELL-MW-10
- **Severity:** NICE-TO-HAVE
- **Evidence:** `search_sidebar_widget.py:48-61` — constructor defaults `match_bg="#FFE066"`, `text_primary="#212529"`, `text_muted="#6C757D"`, `badge_bg="#E9ECEF"`. Delegate paints from these fields; `apply_theme_tokens` (`456-470`) updates them when MainWindow theme runs (`main_window.py:1238-1244`). Widgets constructed before first theme pass or in tests render with light-theme literals; HC modes depend entirely on later token push. QSS for chrome is separate (`style_sheet_sections_workspace.py:491+`).
- **Code-judo alternative:** Require `ShellThemeTokens` (or minimal token subset) at `SearchSidebarWidget` construction — no hex defaults; delegate reads tokens only. Matches workspace UI rule: never hardcode one-theme-only colors.
- **Suggested remediation:** R3 sidebar polish; extend `test_apply_theme_tokens` to assert construction-with-tokens path; manual four-theme pass on search results tree (match highlight, badge, selected row).
- **Tests that would prove fix:** Widget init test with injected tokens; visual/manual HC Light (#FFFFFF bg) and HC Dark (#000000) contrast check on match highlight.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-10-8 — Sidebar result tree lacks keyboard navigation orchestration

- **Persona:** TN-SHELL-MW-10
- **Severity:** NICE-TO-HAVE
- **Evidence:** `search_sidebar_widget.py:447-449,522-531,636-646` — navigation is click → `preview_file_at_line`, activate/double-click → `open_file_at_line`. Enter on search field focuses first result (`_on_search_enter`) but no F3/Shift+F3, Up/Down-through-matches, or Enter-on-selected-match handlers. `MainWindow._handle_find_in_files_action` (`2033-2045`) only seeds query and focuses input.
- **Code-judo alternative:** `SearchSidebarWidget` owns key handling on `_results_tree` and `_search_input` (VS Code–style next/previous match); emits same two signals — no MainWindow growth.
- **Suggested remediation:** Backlog unless PRD requires parity with editor find bar; if added, keep logic in widget module only.
- **Tests that would prove fix:** Unit tests simulating key events on populated tree; manual acceptance in `docs/ACCEPTANCE_TESTS.md`.
- **Handoff overlap:** none

---

## Positive signals (not findings)

- **Search extraction succeeded for UI/worker:** `SearchSidebarWidget` owns debounce, filters, replace-all, tree population, and worker lifecycle (`search_sidebar_widget.py:257-669`) — correct layer vs MainWindow god object.
- **Main-thread marshaling for results apply:** `_apply_results_requested` signal (`562-565`, `570-625`) avoids cross-thread tree mutation from `SearchWorker` callbacks.
- **Preview vs permanent navigation:** Click vs activate mirrors problems panel / VS Code peek pattern; wired through `_open_file_at_line(..., preview=)` (`4835-4841`).
- **Theme token plumbing exists:** `apply_theme_tokens` on sidebar + delegate update (`1238-1244`, `456-470`); QSS section `shell_section_search_sidebar` integrated in global stylesheet.
- **Unit tests on widget:** `tests/unit/shell/test_search_sidebar_widget.py` covers tree roles, signals, empty state, and token update — higher signal than MainWindow ghost-path dispatcher tests.

---

## Approval bar (this slice)

**Would not approve** changes that add MainWindow search methods, retain the Problems-panel search results path, or leave agent debug logging in `_request_python_console_completion_async`. Approve only after hard cutover deletes ghost search infrastructure (findings 1, 3, 5), removes debug instrumentation (finding 2), and consolidates navigation to a shared port (finding 4). Any sidebar theme work must validate match highlight and badges in **Light, Dark, HC Light, HC Dark**.
