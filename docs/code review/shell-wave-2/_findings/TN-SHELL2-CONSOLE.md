# TN-SHELL2-CONSOLE — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-CONSOLE  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/python_console_widget.py` (782 LOC), `app/shell/python_console_workflow.py` (132 LOC), `app/shell/repl_session_manager.py` (266 LOC), `app/shell/repl_event_workflow.py` (152 LOC), `app/shell/clear_console_policy.py` (106 LOC). Cross-read: `app/shell/shell_composition.py` (`build_python_console_workflow`), `app/shell/main_window.py` (console handlers), `app/shell/main_window_panels.py` (signal wiring), `app/editors/code_editor_semantics.py` (completion parity). Re-validate Shell Wave 1 **CC-18**, **CC-23**.

**Delta note:** Between baseline `fccb611` and HEAD, only `python_console_widget.py` (+7 net) and `python_console_workflow.py` (import swap `build_completion_context` → `resolve_completion_prefix`) changed. The other three scope files are **unchanged** at baseline but remain in scope for CC re-validation and structural debt audit.

---

## Executive verdict

**REJECT — console/REPL seam is not thermo-clean.** Shell Wave 1 landed the right modules (`PythonConsoleWorkflow`, `ReplEventWorkflow`, `clear_console_policy`) and composition now routes completion through `_background_tasks` instead of ad-hoc `threading.Thread` on MainWindow — material CC-18 progress. The post-baseline delta closes Editors Wave 2 **CC-EDIT-06** prefix-reuse parity and intelligence prefix SSOT (`resolve_completion_prefix`), which is the correct direction. Dominant blockers remain: **`PythonConsoleWorkflow` owns only async completion** while submit/interrupt/restart and panel signal wiring still live on MainWindow; **`ReplEvent` is still a stringly-typed tuple queue** with `# type: ignore` casts; **`python_console_widget.py` is a 782-line monolith** (prompt, I/O, history, DnD, completion, theme) trending toward the 1k gate; **CC-23 four-theme gaps persist** (stderr colors branch on binary `is_dark` hex literals, ignoring `ShellThemeTokens.diag_error_color` and HC-specific tuning). Copy-paste completion state (`_active_completion_prefix` + dual `reuse_items_for_prefix` branches) mirrors `code_editor_semantics.py` without a shared helper, and the console omits the editor’s `is_tier_header_item` insert guard.

---

## CC re-validation summary

| CC | Wave 1 theme | Status @ HEAD | Evidence |
|----|--------------|---------------|----------|
| **CC-18** | Python console: no workflow; raw threads + tuple REPL events | **PARTIAL** | `PythonConsoleWorkflow` + typed host + `_background_tasks` wiring (`shell_composition.py:269-279`) — completion path closed. Submit/interrupt/restart on `main_window.py:456-499`; panel signals → MW handlers (`main_window_panels.py:279-281`). `ReplEvent = tuple[str, object, object]` + casts (`repl_event_workflow.py:12-13,86-99`). Default workflow still falls back to raw `threading.Thread` (`python_console_workflow.py:129-131`). |
| **CC-23** | Four-theme gaps (HC kind colors, inline styles, QSS omissions) | **PARTIAL** | Console stderr/error colors use hardcoded hex + binary `tokens.is_dark` (`python_console_widget.py:115-116`), not `tokens.diag_error_color`. Pre-theme startup literals assume dark chrome (`:81-86`). HC Light/Dark share Light/Dark error palettes — no `is_high_contrast` branch. |

No **REGRESSION** on CC-18 relative to Wave 1 remediation (workflows exist, agent debug gone, clear policy formalized). Delta improves completion prefix contract; CC-23 console stderr gap unchanged since Wave 1 TN-SHELL-MW-09-8.

---

### TN-SHELL2-CONSOLE-1 — CC-18 PARTIAL: `PythonConsoleWorkflow` is completion-only; REPL lifecycle still on MainWindow

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_workflow.py:68-127` — single public method `request_completion_async`. `main_window.py:484-499` — `_handle_python_console_submit` / `_handle_python_console_interrupt` call `ReplSessionManager` directly with log-only error handling. `main_window_panels.py:279-281` — widget signals wired to MW private handlers, not workflow. Wave 1 TN-SHELL-MW-09-4 / TN-SHELL2-MW-8 documented same split.
- **Code-judo alternative:** Expand `PythonConsoleWorkflow` (or `ReplConsoleSessionWorkflow`) to own submit/interrupt/restart/auto-start policy, user-visible error feedback, and `bind_widget(console)` signal connections. MainWindow retains only host adapter; delete three `_handle_python_console_*` methods.
- **Suggested remediation:** Hard cutover panel wiring to workflow methods; move exception→status-bar/system-line policy into workflow return enum.
- **Tests that would prove fix:** `rg "_handle_python_console" app/shell/main_window.py` empty; unit tests on workflow submit/interrupt with fake `ReplSessionManager`; existing REPL integration shard green.
- **Handoff overlap:** CC-18, CC-20, TN-SHELL2-MW-8

---

### TN-SHELL2-CONSOLE-2 — CC-18 PARTIAL: `ReplEventWorkflow` still tuple-discriminated queue with type-ignore casts

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `repl_event_workflow.py:12-13` — `ReplEvent = tuple[str, object, object]`. `:61-74` enqueue `("output"|"started"|"ended", ...)`. `:86-99` unpack with `# type: ignore[assignment]` per field. Wave 1 TN-SHELL-MW-09-6 recommended frozen `@dataclass` events.
- **Code-judo alternative:** Replace with frozen dataclasses (`ReplOutput`, `ReplStarted`, `ReplEnded`) and `queue.Queue[ReplEventUnion]`; single `handle(event: ReplEventUnion)` eliminates string branches and mypy ignores.
- **Suggested remediation:** One PR hard cutover: update `ReplSessionManager` callbacks and `MainWindowReplEventHost` enqueue sites; delete tuple type alias.
- **Tests that would prove fix:** Extend `test_repl_event_workflow.py` with typed enqueue/process cases; pyright clean on workflow without ignores.
- **Handoff overlap:** CC-18, CC-07 (typed boundaries)

---

### TN-SHELL2-CONSOLE-3 — CC-18 positive keeper: composition wires completion through `_background_tasks`

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** NEW (positive)
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** `shell_composition.py:269-279` — `build_python_console_workflow` injects `start_background_work` via `window._background_tasks.run(key="python_console_completion", ...)`. Replaces Wave 1 blocker of nested `threading.Thread` in MainWindow completion handler. `PythonConsoleWorkflowHost` protocol (`python_console_workflow.py:42-52`) is typed (not `window: Any`).
- **Code-judo alternative:** Keep; delete `_default_start_background_work` raw-thread fallback once all call sites inject scheduler (or assert injector required in `__init__`).
- **Suggested remediation:** None for wiring; optional: make `start_background_work` required param to prevent accidental raw-thread use in tests/tools.
- **Tests that would prove fix:** Existing `test_python_console_workflow.py` already uses injectable starter.
- **Handoff overlap:** CC-18 (partial close)

---

### TN-SHELL2-CONSOLE-4 — CC-23 PARTIAL: console stderr/error colors ignore `ShellThemeTokens.diag_error_color`

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_widget.py:115-116` — `self._col_error = "#FF6B6B" if tokens.is_dark else "#CC0000"` and `_col_error_dim` similarly hardcoded. `theme_tokens.py:224,264,309` defines per-mode `diag_error_color` including HC Light (`#9C0000`) and HC Dark (`#FF8080`) distinct from generic dark/light. Wave 1 CC-23 / TN-SHELL-MW-09-8 flagged console stderr hex.
- **Code-judo alternative:** `apply_theme` sets `_col_error = tokens.diag_error_color` and derives dim variant via token helper or semantic `text_muted` blend — zero `is_dark` branching in widget.
- **Suggested remediation:** TN-SHELL2-STYLES joint PR; manual four-theme acceptance on stderr lines in Python Console tab.
- **Tests that would prove fix:** Parametrized unit test: `apply_theme` for four token presets → `_col_error` matches `tokens.diag_error_color`.
- **Handoff overlap:** CC-23, TN-SHELL2-STYLES, R3

---

### TN-SHELL2-CONSOLE-5 — CC-23 PARTIAL: pre-`apply_theme` startup colors assume dark chrome

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_widget.py:81-86` — constructor sets `#E9ECEF`, `#1B1F23`, etc. before first `apply_theme`. Light/HC Light users see dark-flash hint/prompt until theme workflow runs. Contrasts with `apply_theme` path that reads tokens (`:109-123`).
- **Code-judo alternative:** Lazy-render startup hint after first theme apply, or initialize from neutral token defaults exported by `theme_tokens` module constant.
- **Suggested remediation:** Defer `_render_startup_hint` / `_show_prompt` until `apply_theme` called once, or pass tokens at construction from panel builder.
- **Tests that would prove fix:** Widget constructed under Light tokens → background matches `editor_bg` before user interaction.
- **Handoff overlap:** CC-23, TN-SHELL2-STYLES

---

### TN-SHELL2-CONSOLE-6 — `python_console_widget.py` at 782 LOC: monolith without decomposition plan

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Single class owns appearance/theme (`:96-123`), session lifecycle (`:150-180`), output formatting (`:186+`), key handling/completion (`:250-396`), context menu, DnD, history, prompt management, multiline `code` completeness — **782 LOC**, manifest kickoff #3 shell file by size. Baseline `fccb611` was 775 LOC (+7 from prefix-reuse delta only).
- **Code-judo alternative:** Extract focused modules: `python_console_prompt.py` (anchor/prompt/multiline), `python_console_output_format.py` (stream styles), `python_console_completion_mixin` or shared completion typing helper with editor. Widget becomes thin Qt shell.
- **Suggested remediation:** Cap growth — no new features land in widget until split plan exists; target <500 LOC widget + helpers.
- **Tests that would prove fix:** Existing `test_python_console_widget.py` passes against extracted modules; LOC gate in review checklist.
- **Handoff overlap:** CC-21 (hotspot split), AD-015

---

### TN-SHELL2-CONSOLE-7 — Delta adds copy-paste completion branching instead of shared typing policy

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** NEW (delta regression risk)
- **Severity:** STRUCTURAL
- **Evidence:** Baseline diff adds `_active_completion_prefix` (`python_console_widget.py:74,338-340,349-350,367-369`) mirroring `code_editor_semantics.py:126-127,192` — identical dual guard `is_visible() and self._active_completion_prefix` in both `keyPressEvent` and `_trigger_completion`. Two modules now maintain the same state machine; any fix to reuse semantics requires dual edit.
- **Code-judo alternative:** Extract `CompletionTypingController` (or reuse editor helper) owning prefix cache, reuse-before-request, and generation bump coordination; widget/editor delegate keypress hooks.
- **Suggested remediation:** Follow Editors Wave 2 plan EDIT-R2-05 follow-up — shared module used by console widget and `code_editor_semantics`.
- **Tests that would prove fix:** One parametrized test suite drives shared controller; console + editor tests shrink to integration smoke.
- **Handoff overlap:** CC-EDIT-06, CC-18 (intelligence prefix SSOT partial)

---

### TN-SHELL2-CONSOLE-8 — Console completion insert lacks `is_tier_header_item` guard (editor has it)

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_widget.py:375-396` — `_insert_completion_from_item` accepts any `CompletionItem` with identifier fallback deletion. `code_editor_semantics.py:301` — `if is_tier_header_item(item): return`. `test_python_console_widget.py:579-609` tests tier headers survive **reuse** but not insert rejection.
- **Code-judo alternative:** Shared insert path with tier-header guard and replacement-range SSOT from completion envelope metadata.
- **Suggested remediation:** Add guard matching editor; extend widget test to assert header row activation is no-op.
- **Tests that would prove fix:** Unit test: activate tier header item → document unchanged.
- **Handoff overlap:** CC-EDIT-06, TN-EDIT-COMP

---

### TN-SHELL2-CONSOLE-9 — `show_completion_items_for_request` stale/empty paths leave `_active_completion_prefix` set

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `python_console_widget.py:139-144` — on empty items, hides popup and returns **without** clearing `_active_completion_prefix`. `:139-140` — generation mismatch returns silently, prefix may remain from prior request. `_show_completion_items` correctly clears on empty (`:365-368`). Inconsistent state can leave typing branch (`:338-339`) firing reuse against stale prefix after async drop.
- **Code-judo alternative:** Centralize prefix lifecycle in one helper: `set_active_prefix("")` on hide, generation mismatch, and empty envelope.
- **Suggested remediation:** Align `show_completion_items_for_request` with `_show_completion_items` clear semantics; add regression test.
- **Tests that would prove fix:** Test: show items → empty async response → `_active_completion_prefix == ""` and reuse branch inactive.
- **Handoff overlap:** CC-EDIT-06, CC-18

---

### TN-SHELL2-CONSOLE-10 — `clear_console_policy.py` formalizes behavior but host ports are all `Any`; no tests

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Wave 1 CC-18 targeted three incompatible clear behaviors — policy module (`clear_console_policy.py:41-70`) now names `clear_run_output_sinks`, `clear_python_console_display`, `prepare_new_run`. `ClearConsoleHost` returns `Any` for every port (`:13-26`); `MainWindowClearConsoleHost.__init__(window: Any)` (`:76-77`). Zero pytest modules reference `clear_console_policy`. High-blast-radius sink matrix (run log, debug panel, console model) lacks automated guard.
- **Code-judo alternative:** Narrow protocols per sink (`ConsoleModelPort`, `RunLogPanelPort`); fake host unit tests assert each policy touches expected sinks only.
- **Suggested remediation:** Risk-first tests per `testing_when_to_write.mdc` gate #2 (irreversible multi-sink clear); typed host ports when SaveWorkflow-style inversion lands.
- **Tests that would prove fix:** `test_clear_run_output_sinks_clears_all_four`; `test_clear_python_console_display_only_widget`.
- **Handoff overlap:** CC-18, CC-03 (run prep), TN-SHELL2-DEBUG-RUN

---

### TN-SHELL2-CONSOLE-11 — `ReplSessionManager.complete` / `introspect` duplicate socket RPC envelope

- **Persona:** TN-SHELL2-CONSOLE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `repl_session_manager.py:108-146` vs `:148-184` — nearly identical connect/send/`_read_json_line`/error mapping; differs only in payload method name and fields. ~70 duplicated LOC in subprocess boundary module.
- **Code-judo alternative:** Single `_request_control(method: str, payload: dict) -> CompletionEnvelope` private helper; `complete`/`introspect` build payload dicts only.
- **Suggested remediation:** Extract helper in same PR as any REPL protocol change; keeps socket timeout and degradation reasons in one place.
- **Tests that would prove fix:** Existing REPL/session tests green; optional unit test on helper with mocked socket.
- **Handoff overlap:** CC-18, run-wave seams

---

## Approval bar

| Gate | Result |
|------|--------|
| CC-18 console workflow extraction | **PARTIAL** — completion + clear policy + event drain exist; lifecycle handlers + tuple events open |
| CC-23 four-theme console colors | **PARTIAL** — stderr/error hex + startup flash |
| 1k-line rule | **PASS** @ 782 LOC — but **WARN** (manifest #3 shell file; no split plan) |
| Spaghetti / special-case growth (delta) | **FAIL** — prefix-reuse branches duplicated from editor without shared abstraction |
| Structural regression vs Wave 1 | **NONE** on CC-18; delta improves prefix SSOT |
| Test signal at policy boundaries | **FAIL** — `clear_console_policy` untested; tier-header insert unguarded |

**Verdict: REJECT.** Do not expand `python_console_widget.py` further until TN-SHELL2-CONSOLE-6 split plan lands. Parallel P1 track: TN-SHELL2-CONSOLE-1/2 (full workflow + typed events), TN-SHELL2-CONSOLE-4/5 (CC-23 token wiring), TN-SHELL2-CONSOLE-7/8/9 (shared completion typing + insert guard + prefix lifecycle). Keep TN-SHELL2-CONSOLE-3 (`_background_tasks` wiring) and Wave 1 `clear_console_policy` naming (extend with tests in TN-SHELL2-CONSOLE-10).

---

## Fix wave hints

| Priority | Findings | Action |
|----------|----------|--------|
| P1 | CONSOLE-1, CONSOLE-2 | Expand `PythonConsoleWorkflow` + typed `ReplEvent` union |
| P1 | CONSOLE-4, CONSOLE-5 | Wire `diag_error_color`; defer startup render until themed |
| P1 | CONSOLE-7, CONSOLE-8, CONSOLE-9 | Shared completion typing controller; tier-header guard; prefix clear on stale |
| P2 | CONSOLE-6 | Split widget monolith before next feature |
| P2 | CONSOLE-10, CONSOLE-11 | Clear-policy tests + typed host; dedupe REPL control RPC |
