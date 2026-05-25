# TN-RUNNER-01 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUNNER-01  
**Date:** 2026-05-25  
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
**Scope:** `app/runner/runner_main.py` (136 LOC), `app/runner/execution_context.py` (91 LOC), `app/runner/output_bridge.py` (80 LOC), `app/runner/traceback_formatter.py` (16 LOC). Cross-read: `tests/integration/runner/test_runner_main.py`, `tests/unit/runner/test_run_runner_entrypoint.py`, `tests/unit/runner/test_execution_context.py`, `tests/unit/runner/test_repl_console.py`, `tests/unit/runner/test_debug_runner.py` (output_bridge tests), `docs/deslop/AUDIT_app_remaining_handoff.md` R1 (output_bridge except).

---

## Executive verdict

**Mostly thermo-clean for size, not for contract sharpness.** The normal bootstrap path is four small modules (323 LOC total) with a clear `run_from_manifest_path` → `execute_manifest` → `apply_execution_context` → `runpy.run_path` spine, line-buffering before tee, and narrow `OSError` handling in `output_bridge` (R1 item already improved). Dominant risks in this slice: (1) **REPL `clear()` guidance text disagrees with shell clear semantics** (menu clears four sinks; hint claims “Python Console display” only); (2) **`TeeTextIO` is a partial `TextIO` wrapper** — log I/O failures and missing delegated methods can break user output mid-run; (3) **`sys.path` prepends only `project_root`**, not the entry script directory, diverging from CPython’s default script bootstrap for nested entries. No 1k-line god modules here; would approve small fixes without a redesign, but would not add bootstrap features until tee failure semantics and path rules are documented or tightened.

---

### TN-RUNNER-01-1 — REPL `clear()` hint references Run menu but describes toolbar-only semantics

- **Persona:** TN-RUNNER-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/runner_main.py:41-44` — `_ClearHint.__repr__` / `__call__` print `"Use Run \u2192 Clear Console to clear the Python Console display."` Shell Run menu → `app/shell/menu_wiring.py:63` → `app/shell/main_window.py:2365-2372` — `_handle_clear_console_action` clears `_console_model`, run log panel, python console widget, **and** debug panel output. In-tab toolbar → `app/shell/main_window_panels.py:250-262` — `clear_btn` tooltip `"Clear the Python Console display"` wired to `python_console_widget.clear_console` only. The runner steers users to the **menu** path while claiming **display-only** clearing — the two surfaces users actually have behave differently.
- **Code-judo alternative:** Pick one policy string: either `"Use the Clear button in the Python Console tab (display only)"` or `"Use Run \u2192 Clear Console to clear run output (console, run log, and debug output)"`. Inject via a single shared constant imported from a shell/run contract module, or pass hint text through `ReplControlConfig` if runner must stay shell-agnostic.
- **Suggested remediation:** Align copy with PRD/shell decision in TN-RUN-SHELL-7; update `_make_clear_helper` and `tests/unit/runner/test_repl_console.py` assertions together.
- **Tests that would prove fix:** Unit test asserts hint text matches chosen policy constant; optional manual acceptance row for REPL `clear()` vs menu Clear Console.
- **Handoff overlap:** shell-wave-1-followup

---

### TN-RUNNER-01-2 — `TeeTextIO` is an incomplete `TextIO` wrapper

- **Persona:** TN-RUNNER-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/output_bridge.py:19-40` — `TeeTextIO` implements only `write`, `flush`, `writable`, `isatty`, and `encoding`. No `fileno`, `readable`, `read`, `close`, or `__getattr__` delegation to `_primary`. Libraries or stdlib helpers that probe `fileno()` (progress bars, some logging handlers, subprocess pipe checks) will raise on teed streams for the entire run.
- **Code-judo alternative:** Delegate unknown attributes to `_primary` (`__getattr__`), implement `fileno()` when primary supports it, and treat log-stream writes as best-effort (see TN-RUNNER-01-3). Alternatively use a battle-tested tee from the stdlib/`io` stack if available in 3.9.
- **Suggested remediation:** Harden before adding rich console/progress output in user projects; document supported `TextIO` surface in module docstring.
- **Tests that would prove fix:** Unit test: teed `sys.stdout.fileno()` succeeds when primary has `fileno`; third-party smoke (e.g. `logging.StreamHandler(sys.stdout)`) under `redirect_output_to_log`.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-01-3 — Log mirror write failures abort user `print()` calls

- **Persona:** TN-RUNNER-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/output_bridge.py:27-30` — `write()` always calls `self._log_stream.write(text)` with no isolation; any `OSError` (disk full, permission revoked mid-run) propagates out of user code’s `print()`. Post-yield flush catches `OSError` only in the `finally` around context exit (`output_bridge.py:72-77`), not per write. Pipe delivery to the editor continues via `_primary`, so failing closed on the log side sacrifices the run for a non-critical artifact.
- **Code-judo alternative:** Best-effort log leg: wrap log writes in `try/except OSError`, set a `_log_failed` flag, emit one stderr diagnostic, continue mirroring to pipe only. Matches ARCHITECTURE intent that per-run logs are diagnostic, not process-boundary critical.
- **Suggested remediation:** Implement guarded log leg; optionally disable further log writes after first failure to avoid hot-loop warnings.
- **Tests that would prove fix:** Unit test with monkeypatched log stream whose `write` raises after N bytes — user `print` still succeeds, pipe capture intact, single warning emitted.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-01-4 — `sys.path` prepends project root only, not entry script directory

- **Persona:** TN-RUNNER-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/execution_context.py:69-70` — `sys.argv = [entry_script_path, *argv]` then `sys.path.insert(0, project_root)` only. CPython script launch (`python project/pkg/main.py`) inserts the script’s directory on `sys.path[0]`. A manifest with `entry_file="src/main.py"` and imports of sibling modules in `src/` (e.g. `import helpers` where `helpers.py` lives beside `main.py`) fails under runner bootstrap while succeeding under direct `python` invocation from the same cwd. DISCOVERY documents flat `main.py` at project root (`docs/DISCOVERY.md` bootstrap examples); nested entries are an undocumented gap.
- **Code-judo alternative:** After resolving `entry_script_path`, insert `str(Path(entry_script_path).parent)` at `sys.path[0]` (before or after project root per documented precedence), or document that all imports must be package-relative to `project_root` only.
- **Suggested remediation:** Decide contract in ARCHITECTURE §13 runner bootstrap; if nested entries are supported, insert script directory; if not, validate relative `entry_file` has no directory components beyond `./` or fail fast with `RunLifecycleError`.
- **Tests that would prove fix:** Unit/integration test: entry `pkg/run.py` importing sibling module in `pkg/` succeeds; characterization test locks precedence when both roots differ.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-01-5 — Bootstrap failure exit codes untested end-to-end

- **Persona:** TN-RUNNER-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/runner/runner_main.py:71-73` — missing entry / invalid cwd → `RUN_EXIT_BOOTSTRAP_ERROR`. `tests/integration/runner/test_runner_main.py` covers success, user traceback, and invalid manifest file only — no case for missing entry script or bad `working_directory`. `tests/unit/runner/test_execution_context.py` raises `RunLifecycleError` in isolation but never asserts `run_from_manifest_path` exit code or stderr message through the full tee + buffering stack.
- **Code-judo alternative:** One integration test per bootstrap failure mode through `run_from_manifest_path`; keep unit tests on `RunnerExecutionContext.from_manifest` for message matching.
- **Suggested remediation:** Add integration coverage when fixing bootstrap path (risk-first: irreversible wrong exit code mapping affects supervisor/session UX).
- **Tests that would prove fix:** `test_runner_returns_bootstrap_error_for_missing_entry` and `test_runner_returns_bootstrap_error_for_invalid_working_directory` asserting exit code `2`, stderr substring, and log file contents when tee succeeds.
- **Handoff overlap:** none

---

### TN-RUNNER-01-6 — `format_traceback` is dead public API

- **Persona:** TN-RUNNER-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/traceback_formatter.py:9-11` — `format_traceback(exc_type, exc, tb)` is defined and exported implicitly by module presence. `rg format_traceback` at baseline hits only this definition. `runner_main.py:96` uses `format_current_exception()` only. Module exists per `docs/TASKS.md` / ARCHITECTURE layout but half the surface is unused.
- **Code-judo alternative:** Delete `format_traceback` until a caller needs captured-trace formatting (debug host already uses traceback helpers locally), or wire debug runner to this module for one SSOT.
- **Suggested remediation:** R1 small cleanup — remove dead function or add single consumer; avoid growing a two-function “module” indefinitely.
- **Tests that would prove fix:** N/A if deleted; if kept, unit test with synthetic `(type, exc, tb)` tuple.
- **Handoff overlap:** R1

---

### TN-RUNNER-01-7 — Output-bridge unit tests live in debug runner test module

- **Persona:** TN-RUNNER-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/runner/test_debug_runner.py:362-401` — `test_redirect_output_to_log_mirrors_stdout_and_stderr` and `test_redirect_output_to_log_falls_back_when_log_file_open_fails` import `app.runner.output_bridge`, not `debug_runner`. Duplicates cross-critic note TN-RUNNER-03-12; obscures ownership for this slice.
- **Code-judo alternative:** Move to `tests/unit/runner/test_output_bridge.py`; leave debug runner tests focused on debug host behavior.
- **Suggested remediation:** Test file hygiene during R-run-2 runner package cleanup; no production behavior change.
- **Tests that would prove fix:** pytest collection paths unchanged after move.
- **Handoff overlap:** R-run-2

---

### TN-RUNNER-01-8 — `_ensure_line_buffering` swallows broad `Exception` on reconfigure

- **Persona:** TN-RUNNER-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/runner_main.py:53-62` — `stdout_reconfigure(line_buffering=True)` wrapped in `except Exception as exc` with stderr print. R1 handoff targets narrow handling in runner shutdown/bootstrap paths (`docs/deslop/AUDIT_app_remaining_handoff.md` §R1). `output_bridge.py` already uses `OSError`-only handlers (lines 53-63, 75-77) — inconsistency within the same bootstrap stack.
- **Code-judo alternative:** Catch `(OSError, ValueError)` (or `AttributeError` if reconfigure missing) explicitly; let unexpected exceptions surface during development.
- **Suggested remediation:** R1 sweep item alongside debug_runner shutdown handlers.
- **Tests that would prove fix:** Unit test with fake stdout whose `reconfigure` raises `OSError` — runner continues; `ValueError` propagates in test env if desired.
- **Handoff overlap:** R1

---

### TN-RUNNER-01-9 — `_LOGGER` diagnostics may be silent in runner subprocess

- **Persona:** TN-RUNNER-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/output_bridge.py:61` — `_LOGGER.warning(...)` when log open fails after stderr user message. `output_bridge.py:77` — `_LOGGER.debug` on flush failure. `run_runner.py` / runner subprocess bootstrap does not configure `logging`; default level WARNING may still reach nowhere if no handlers are attached. Operational signal relies on the stderr `print` loop (lines 55-60), making the logger line redundant noise.
- **Code-judo alternative:** Either configure a runner logging bootstrap once in `execute_manifest`, or drop logger calls and keep stderr prints only for child-process observability.
- **Suggested remediation:** R1 — pick one observability channel for runner child; avoid duplicate silent + visible paths.
- **Tests that would prove fix:** Characterization test asserting stderr message present on open failure (already in `test_redirect_output_to_log_falls_back_when_log_file_open_fails`); logging handler test only if logging bootstrap added.
- **Handoff overlap:** R1

---

### TN-RUNNER-01-10 — `runner_main` eagerly imports debug engine for all modes

- **Persona:** TN-RUNNER-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/runner/runner_main.py:12` — `from app.runner.debug_runner import run_debug_session` at module import time. Normal `python_script` runs pay import cost and coupling to the 803 LOC debug module (`TN-RUNNER-03` scope) even when `manifest.mode` is script or REPL.
- **Code-judo alternative:** Lazy-import inside the `RUN_MODE_PYTHON_DEBUG` branch, or a mode dispatch registry loaded on demand. Hard cutover — no fallback import chain.
- **Suggested remediation:** Optional micro-optimization during R-run-2 debug decomposition; measure before/after on AppRun cold start.
- **Tests that would prove fix:** Import smoke: `import app.runner.runner_main` does not import `debug_runner` until debug branch executes (use `sys.modules` guard in unit test).
- **Handoff overlap:** R-run-2

---

## Positive signals

| Signal | Evidence |
|--------|----------|
| Small, readable bootstrap spine | 323 LOC across four modules; `execute_manifest` is ~35 lines of orchestration (`runner_main.py:65-99`) |
| Process isolation preserved | `apply_execution_context` strips `app` / `app.*` from `sys.modules` before user code (`execution_context.py:72-74`); restored in `finally` |
| Output tee intent is explicit | Module docstring states pipe + log dual write (`output_bridge.py:3-6`); integration test asserts log mirroring (`test_runner_main.py:46-47`) |
| Log open failure degrades gracefully | `redirect_output_to_log` prints to stderr/`__stderr__`, yields without tee, does not abort run (`output_bridge.py:53-63`; unit test at `test_debug_runner.py:383-401`) |
| Narrow I/O exceptions on tee teardown | Flush failures after yield use `except OSError` + debug log, not bare `Exception` (`output_bridge.py:75-77`) — R1 `output_bridge` except item addressed |
| Line buffering before pipe tee | `_ensure_line_buffering()` runs before `redirect_output_to_log` (`runner_main.py:67-68`), matching editor pipe delivery needs |
| REPL prompt suppression documented | `_QuietConsole.raw_input` avoids `>>>` on piped stdout (`runner_main.py:19-33`); unit tests in `test_repl_console.py` |
| Execution context unit coverage | Path resolution, missing entry, REPL placeholder entry, cwd/argv/env restore (`test_execution_context.py`) |

---

## Inspection summary

| Area | Files read | Outcome |
|------|------------|---------|
| Primary | `runner_main.py`, `execution_context.py`, `output_bridge.py`, `traceback_formatter.py` | 10 findings (0 BLOCKER, 5 STRUCTURAL, 5 NICE-TO-HAVE) |
| Integration | `test_runner_main.py` | Happy path + traceback; bootstrap failures uncovered |
| Unit | `test_execution_context.py`, `test_repl_console.py`, `test_run_runner_entrypoint.py` | Good context/REPL/CLI seams; output_bridge tests misplaced |
| Shell cross-read | `main_window.py`, `main_window_panels.py`, `menu_wiring.py`, `TN-RUN-SHELL-7` | Clear-console hint mismatch confirmed |
| Handoff | `AUDIT_app_remaining_handoff.md` R1 | `output_bridge` except improved; `_ensure_line_buffering` still broad |
