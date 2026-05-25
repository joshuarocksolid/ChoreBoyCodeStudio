# TN-SHELL-MW-09 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-09  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 3484–3827 (python console orchestration). Cross-read: `app/shell/python_console_widget.py`, `app/shell/main_window_panels.py` (console tab wiring), `app/shell/repl_session_manager.py`, `app/shell/python_console_history.py`. Adjacent (outside slice end): `main_window.py:3833–3912` (async completion), `main_window.py:4030–4088` (REPL event queue pump), `main_window.py:3429–3432` (menu restart).

---

## Executive verdict

**Not thermo-clean.** `ReplSessionManager` and `PythonConsoleWidget` are the right boundaries, but **orchestration is still scattered**: thin submit/interrupt/history handlers in this slice, REPL event pumping and auto-start **below** the slice, completion on a **raw daemon thread**, and panel wiring in `main_window_panels.py`. Dominant risks: (1) **committed agent-debug instrumentation** on the console hot path (keypress + completion) writing to a hardcoded `.cursor` log; (2) **three different “clear” behaviors** (Run menu vs in-tab toolbar vs context menu); (3) **no `PythonConsoleWorkflow`** — MainWindow remains the integration hub for queue + timers + REPL lifecycle. `main_window.py` is **5549 lines** (~5× the 1k guideline); this slice also contains **~300 lines of non-console code** (plugins, lint, runtime probe), which is slice-assignment noise for INTEG. Four-theme impact: `PythonConsoleWidget.apply_theme` partially uses `ShellThemeTokens` but **hardcodes stderr/error colors**, so HC Light/Dark contrast tuning does not flow through tokens.

---

### TN-SHELL-MW-09-1 — Agent-debug logging is embedded in production console hot paths

- **Persona:** TN-SHELL-MW-09
- **Severity:** BLOCKER
- **Evidence:** `app/shell/python_console_widget.py:33-57` — module-level `_AGENT_LOG_PATH = "/home/joshua/Documents/ChoreBoyCodeStudio/.cursor/debug-0b96d3.log"` and `_agent_log_con` writing JSON on every instrumented path. `python_console_widget.py:256-274` — `keyPressEvent` wrapped with depth counter, recursion guard, and exception logging before delegating to `_keyPressEvent_inner`. `main_window.py:3843-3906` — duplicate inline `_agent_log_mw` inside `_request_python_console_completion_async` (starts at line 3833, one past slice end). Related: `app/runner/repl_completion.py:19-99`.
- **Code-judo alternative:** Delete all `#region agent log` blocks before ship; use structured `_logger.debug` behind an explicit diagnostics flag, or a temporary branch-only patch. Never hardcode developer-machine paths in `app/shell` or `app/runner`.
- **Suggested remediation:** Hard cutover — remove agent regions from `python_console_widget.py`, `main_window.py` completion handler, and `repl_completion.py` in one diff; restore normal `keyPressEvent` → `_keyPressEvent_inner` without depth tracking.
- **Tests that would prove fix:** Grep gate in CI (`rg 'debug-0b96d3|#region agent log'` → empty under `app/`); existing `tests/unit/shell/test_python_console_widget.py` still passes without log side effects.
- **Handoff overlap:** none (pre-R2 hygiene)

---

### TN-SHELL-MW-09-2 — “Clear Console” has three incompatible behaviors

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** Run menu → `menu_wiring.py:63` → `main_window.py:3484-3491` — `_handle_clear_console_action` clears `_console_model`, run log panel, python widget, **and** debug panel. In-tab toolbar → `main_window_panels.py:261` — `clear_btn.clicked.connect(window._python_console_widget.clear_console)` (display only, preserves session/history). Context menu → `python_console_widget.py:463-465` — `clear_action.triggered.connect(self.clear_console)` (same as toolbar). Runner hint text references “Run → Clear Console” (`app/runner/runner_main.py:41-44`) implying menu semantics, not in-tab button.
- **Code-judo alternative:** One policy object: `PythonConsoleWorkflow.clear_display()` vs `clear_all_output_sinks()` with explicit names; menu and toolbar call the intended entry; debug/run log clears move to their own actions or a separate “Clear All Output” menu item.
- **Suggested remediation:** Decide product semantics in PRD, then route all three UI surfaces through workflow methods; avoid widening `_handle_clear_console_action` without renaming the menu label.
- **Tests that would prove fix:** Characterization tests: menu clear vs toolbar clear assert which sinks are touched (mock run log / debug panel / `ConsoleModel`).
- **Handoff overlap:** R3 (UX copy), R2 (workflow owner)

---

### TN-SHELL-MW-09-3 — Console orchestration has no workflow; MainWindow owns queue, timers, and handlers

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** Slice handlers only forward to `ReplSessionManager` / widget: `main_window.py:3790-3831`. Wiring lives in `main_window_panels.py:254-261` (signals → `MainWindow` private methods). REPL lifecycle outside slice: `main_window.py:553-559` (manager + callbacks enqueue), `747-750` (`_repl_event_timer` → `_process_queued_repl_events`), `759-762` (`_auto_start_repl_timer` → `_auto_start_repl`), `4047-4088` (tuple dispatch `("output"|"started"|"ended", ...)`). `ReplSessionManager` (`repl_session_manager.py:39-256`) owns subprocess but not UI/session messaging.
- **Code-judo alternative:** `PythonConsoleWorkflow` (or extend `ReplSessionManager` with a small presenter) owns: auto-start policy, queued event drain → widget updates, history restore/persist hooks, submit/interrupt/restart, and coordinates with `ReplSessionManager` callbacks. `MainWindow` connects menu IDs once; delete `_enqueue_repl_*`, `_process_queued_repl_events`, and thin handlers from the god object.
- **Suggested remediation:** R2 extraction per shell deslop handoff — **net method count down** on `MainWindow`; wire `build_bottom_panel` signals to workflow public methods, not `window._handle_*`.
- **Tests that would prove fix:** Unit-test workflow with fake manager + fake widget (no `MainWindow` import); port REPL event sequencing tests to workflow; keep `test_repl_session_manager.py` for subprocess boundary.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-09-4 — Live completion spawns unbounded daemon threads instead of using `GeneralTaskScheduler`

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:3833-3912` — `_request_python_console_completion_async` defines nested `work()` and `threading.Thread(target=work, daemon=True).start()` with no dedupe key, no cancel-on-new-request beyond widget generation check. Contrast lint in same file: `main_window.py:3668-3673` uses `self._background_tasks.run(key=key, ...)`. `ReplSessionManager.complete` (`repl_session_manager.py:111-148`) does synchronous socket I/O — appropriate off UI thread, wrong orchestrator.
- **Code-judo alternative:** Register completion work on `_background_tasks` with key `repl_complete::{generation}` or a single `repl_complete` key that cancels prior; `on_success` marshals to main thread via existing `dispatch_to_main_thread` (same as lint `on_success`).
- **Suggested remediation:** Move completion orchestration into `PythonConsoleWorkflow` or a dedicated `ReplCompletionCoordinator` that wraps `_background_tasks`; delete raw `threading.Thread` from `MainWindow`.
- **Tests that would prove fix:** Unit test: rapid Tab triggers cancel/replace prior task; generation stale → no `show_completion_items_for_request`; no thread count growth under burst input (manual or slow integration).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-09-5 — Submit/interrupt failures are silent to the user

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:3790-3805` — `_handle_python_console_submit` catches `Exception` on `send_input`, logs warning only; `_handle_python_console_interrupt` same pattern; interrupt is a no-op when `not self._repl_manager.is_running` with no status feedback. `ReplSessionManager.send_input` (`repl_session_manager.py:105-109`) can fail if process not running; `start()` swallows launch failures (`repl_session_manager.py:77-80`).
- **Code-judo alternative:** Workflow returns a small result enum (`sent`, `started_and_sent`, `repl_unavailable`); status bar or `append_output(..., stream="system")` for user-visible errors; interrupt always gives feedback when REPL is down.
- **Suggested remediation:** Centralize error surfacing in `PythonConsoleWorkflow`; use existing degradation pattern from completion (`statusBar().showMessage` at `main_window.py:3898-3901`).
- **Tests that would prove fix:** Unit test with mock manager raising on `send_input` → system line or status message appended; interrupt when not running → user-visible hint.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-09-6 — REPL event queue uses untyped tuple protocol on MainWindow

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:300` — `ReplEvent = tuple[str, object, object]`. Enqueue: `4032-4045` — `("output", text, stream)`, `("ended", return_code, terminated_by_user)`, `("started", None, False)`. Dispatch: `4057-4082` — `kind, arg1, arg2 = item` with `# type: ignore[assignment]` casts.
- **Code-judo alternative:** `@dataclass` frozen events (`ReplOutput`, `ReplStarted`, `ReplEnded`) in `repl_session_manager.py` or `python_console_workflow.py`; queue `Queue[ReplEventUnion]`; single `handle(event)` eliminates stringly-typed branches and mypy ignores.
- **Suggested remediation:** Introduce typed events when extracting workflow; manager callbacks enqueue typed instances directly.
- **Tests that would prove fix:** Parametrized tests per event type updating widget session flag and output lines.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-09-7 — Three REPL start paths with different semantics (auto-start, lazy start, restart)

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** Auto-start: `main_window.py:759-762`, `4087-4088` — `_auto_start_repl` → `start()`. Submit path: `3793-3794` — `if not is_running: start()` then `send_input`. Menu/context restart: `3429-3431` — `restart()` (stop + launch, clears rapid-restart window in manager). `ReplSessionManager.start` vs `restart` (`repl_session_manager.py:70-103`) differ in auto-restart flags and `_recent_exit_times` reset.
- **Code-judo alternative:** Workflow exposes `ensure_session_ready()` used by submit and startup; menu “Restart Python Console” calls `restart()` only; document that submit does not force restart on crash loops (manager handles auto-restart).
- **Suggested remediation:** Collapse policy into workflow; remove duplicate start calls from `MainWindow` handlers.
- **Tests that would prove fix:** Tests for: cold app auto-start; submit when stopped starts once; restart menu calls `restart` not `start`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-09-8 — `PythonConsoleWidget` theme path bypasses semantic error tokens (four-theme gap)

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_widget.py:132-145` — `apply_theme` sets text/muted/accent/bg from tokens but assigns `self._col_error` / `self._col_error_dim` via hardcoded hex branches on `tokens.is_dark`. `ShellThemeTokens` already defines `diag_error_color` (`theme_tokens.py:69`). Startup defaults `python_console_widget.py:104-109` are fixed dark-theme literals before first `apply_theme`.
- **Code-judo alternative:** Map stderr/traceback colors from `tokens.diag_error_color` and a derived dim variant (or add `console_stderr_dim` to tokens once for all four modes).
- **Suggested remediation:** R3 UI pass — wire console colors through `ShellThemeTokens`; manually verify Light, Dark, HC Light, HC Dark per workspace UI rule.
- **Tests that would prove fix:** Manual acceptance in four themes; optional unit test that `apply_theme` copies `diag_error_color` into `_col_error` (no hardcoded `#FF6B6B` in widget).
- **Handoff overlap:** R3

---

### TN-SHELL-MW-09-9 — Critic slice 3484–3827 includes ~300 lines of non-console orchestration

- **Persona:** TN-SHELL-MW-09
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:3493-3788` in scope — plugin manager, dependency inspector, plugin safe mode, full lint/diagnostics pipeline (`_render_lint_diagnostics_for_file`, `_lint_all_open_files`, problems delegators), runtime module probe with `getattr(self, "_diagnostics_orchestrator", None)` fallback chains. Python-console-specific code in range is essentially `3484-3491` (clear), `3790-3827` (submit/interrupt/history/append line).
- **Code-judo alternative:** Reslice critics by feature (console vs diagnostics vs plugins) or document explicit “padding” slices; INTEG meta should not attribute lint/plugin debt to TN-SHELL-MW-09.
- **Suggested remediation:** TN-SHELL-INTEG dedupe — map lint/probe findings to diagnostics critic or MW-16; keep MW-09 rollup console-only.
- **Tests that would prove fix:** N/A (documentation/process).
- **Handoff overlap:** none (INTEG)

---

### TN-SHELL-MW-09-10 — Widget `_trigger_completion` contains unreachable duplicate call (dead code)

- **Persona:** TN-SHELL-MW-09
- **Severity:** NICE-TO-HAVE
- **Evidence:** `python_console_widget.py:392-411` — `return` at line 403 ends the function; lines 405-411 duplicate `self._completion_requester(...)` and are unreachable (leftover from agent-log edit).
- **Code-judo alternative:** Delete lines 405-411; keep single requester invocation in the try block.
- **Suggested remediation:** Remove with agent-log cleanup (TN-SHELL-MW-09-1).
- **Tests that would prove fix:** Existing completion widget tests unchanged; coverage unchanged.
- **Handoff overlap:** none

---

## Slice note (inspected, not filed as separate findings)

- **`_append_python_console_line` / history helpers** (`3807-3831`): thin null-guard delegators — acceptable only until workflow extraction; do not add more one-line pass-throughs (R2 rule).
- **`max_entries=200`**: duplicated magic number in `main_window.py:3812,3823` and `python_console_widget.py:64` — collapse to one module constant when workflow owns history.
- **Tests:** `tests/unit/shell/test_python_console_widget.py` covers widget behavior; no tests for `_handle_clear_console_action` sink matrix or menu vs toolbar clear — add only if clear policy is formalized (risk-first gate).
