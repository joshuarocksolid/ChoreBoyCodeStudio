# TN-SHELL2-MW — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-MW  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/main_window.py` (542 LOC, 45 methods), `app/shell/main_window_panels.py` (335 LOC), `app/shell/menu_wiring.py` (154 LOC), `app/shell/menus.py` (212 LOC). Cross-read: `app/shell/main_window_composition.py` (menu/panel install), `app/shell/main_window_lifecycle.py` (close path), `app/shell/help_controller.py`, `app/shell/find_replace_workflow.py`, `app/shell/file_project_commands_workflow.py`. Gates: AD-015 composition root, shrink-rule delegators, cohesive menu workflow extraction.

**Delta note:** These four files are **unchanged** between baseline `fccb611` and post-remediation HEAD `430c567`. This critic audits the **post–Shell Wave 1 decomposition state** only — it does **not** re-run obsolete `main_window.py` line-range critics from the 5,549 LOC / 332-method era.

---

## Executive verdict

**APPROVE for the MainWindow delta slice.** Shell Wave 1’s composition cutover landed: `main_window.py` is **542 LOC / 45 methods** (down from 5,549 / 332), `__init__` delegates to `install_main_window_composition`, panels live in `main_window_panels.py`, and menus bind through `menu_wiring.py` → `menus.py` builders. **CC-06** (god file) is **substantially closed**; **CC-20** (cohesive menu workflows) is **materially improved** with `FindReplaceWorkflow`, `FileProjectCommandsWorkflow`, and direct Help wiring; **CC-13** (shrink-rule delegators) is **partially closed** — zoom/markdown/find/help bypass MainWindow, but editor-text and python-tooling pass-throughs remain. Method count sits at the AD-015 ceiling (45); P1 shrink targets are enumerated below. **No REGRESSION** detected in this slice relative to Shell Wave 1 remediation intent.

---

## Prior-wave re-validation (CC-06, CC-13, CC-20)

| CC ID | Shell Wave 1 headline | Status @ `fccb611` | Evidence |
|-------|----------------------|-------------------|----------|
| **CC-06** | MainWindow god file (5,549 LOC, 332 methods, 460-line `__init__`) | **SUBSTANTIALLY CLOSED** | `wc -l main_window.py` → **542**; `rg "^    def " main_window.py \| wc -l` → **45**; `__init__` ends at `:128` with single `install_main_window_composition(...)` call; layout in `main_window_layout.py` + `main_window_panels.py`; lifecycle in `main_window_lifecycle.py`. Remaining MW logic is feature-sized (language mode dialog, project-entry picker, run stop/restart), not composition sprawl. |
| **CC-13** | One-line MainWindow delegators violate shrink rule | **PARTIALLY CLOSED** | **Closed paths:** `menu_wiring.py:74-76` zoom → `editor_tab_workflow`; `:77-80` markdown → `editor_tab_workflow`; `:101-104` find → `find_replace_workflow`; `:121-128` help → `ShellHelpController` lambdas (no MW pass-through). **Open paths:** `:108-112` editor text → `_handle_toggle_comment_action` / indent / outdent / flat-Python on MW; `:163-167` python-tooling trio returns through MW; lazy `_get_editor_tabs_coordinator` / `_get_problems_controller` at `main_window.py:348-360`. |
| **CC-20** | Cohesive menu workflows not extracted | **SUBSTANTIALLY CLOSED** | **Extracted:** find/replace (`find_replace_workflow`), quick open / project create / go-to-line (`file_project_commands_workflow`), plugin dialogs (`plugin_dialog_workflow`), semantic nav (`semantic_navigation_workflow`), run launch (`run_launch_workflow`), save (`save_workflow`), local history (`local_history_workflow`). **Residual on MW:** run stop/restart/clear (`:468-482`), language-mode dialogs (`:304-339`), flat-Python status orchestration (`:273-302`), project-entry replacement picker (`:408-454`). |

---

### TN-SHELL2-MW-1 — CC-06 win: MainWindow is a composition façade, not a god file

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL (closure of Wave 1 CC-06)
- **Severity:** NICE-TO-HAVE (positive keeper — do not regress)
- **Evidence:** `main_window.py:74-128` — field declarations + `install_main_window_composition(self, ...)`; no panel construction, no menu build, no workflow `__init__` soup. `main_window_layout.py` imports `build_*_panel` from `main_window_panels.py`; `main_window_composition.py:522` calls `build_main_window_menus`.
- **Code-judo alternative:** Keep this boundary. New shell features must land in workflows/composition, not MW method growth.
- **Suggested remediation:** Gate future PRs: `rg "^    def " app/shell/main_window.py | wc -l` must not exceed 45 without net extraction in the same diff.
- **Tests that would prove fix:** Manifest metric sweep; AD-015 review on any MW method-count increase.
- **Handoff overlap:** CC-06, AD-015, TN-SHELL2-COMP

---

### TN-SHELL2-MW-2 — CC-13 residual: editor text menu actions still bound through MainWindow thin handlers

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:255-287` — `_handle_toggle_comment_action`, `_handle_indent_action`, `_handle_outdent_action` each fetch `active_editor_widget()` and forward one call. `menu_wiring.py:108-112` binds `MenuCallbacks.on_toggle_comment` / `on_indent` / `on_outdent` to these MW methods. Shell Wave 1 MW-05-5 flagged identical pattern at 5,549 LOC.
- **Code-judo alternative:** Wire menus directly to `EditorTabsCoordinator` or a tiny `EditorTextActions` helper constructed in composition (mirror `PythonStyleWorkflow` for format/lint). Delete three MW methods; method count **45 → 42**.
- **Suggested remediation:** Hard cutover `menu_wiring` bindings in one PR; no new MW methods for editor chrome.
- **Tests that would prove fix:** Method count decreases; manual acceptance unchanged (editor comment/indent behavior).
- **Handoff overlap:** CC-13, R2

---

### TN-SHELL2-MW-3 — CC-13 residual: python-tooling status pass-through trio on MainWindow

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:163-178` — `_current_python_tooling_status_context`, `_settings_dialog_python_tooling_copy`, `_refresh_python_tooling_status` are identity/passthrough to `_python_tooling_status_controller` with MW as the only public seam settings dialogs reach.
- **Code-judo alternative:** Expose `PythonToolingStatusController` (or a narrow protocol) to `settings_dialog_handlers` / composition directly; delete trio from MW.
- **Suggested remediation:** TN-SHELL2-SETTINGS slice pairs with this; inject controller into settings workflow host.
- **Tests that would prove fix:** Settings dialog opens with correct tooling copy without calling MW private methods.
- **Handoff overlap:** CC-13, TN-SHELL2-SETTINGS

---

### TN-SHELL2-MW-4 — CC-20 substantially closed: menu_wiring is the cohesive workflow registry

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL (closure of Wave 1 CC-20)
- **Severity:** NICE-TO-HAVE (positive keeper)
- **Evidence:** `menu_wiring.py:30-129` — `MenuCallbacks(...)` binds 60+ actions to named workflows (`_file_project_commands_workflow`, `_find_replace_workflow`, `_run_launch_workflow`, `_semantic_navigation_workflow`, `_plugin_dialog_workflow`, etc.) with only **11** callbacks still targeting `window._handle_*` (stop/restart/clear console, editor text ×5, language mode ×2, inspect token). Find/replace bar signals wire to workflow in `main_window_panels.py:224-230`, not MW.
- **Code-judo alternative:** Keep `menu_wiring` as single menu binding site; migrate remaining `_handle_*` targets in shrink PRs.
- **Suggested remediation:** Document in ARCHITECTURE §shell that `build_main_window_menus` is the menu SSOT; forbid new `MainWindow._handle_*` menu targets.
- **Tests that would prove fix:** `rg "window\._handle_" app/shell/menu_wiring.py` count monotonically decreases.
- **Handoff overlap:** CC-20, R2

---

### TN-SHELL2-MW-5 — CC-20 residual: run session stop/restart/clear still orchestrated on MainWindow

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:465-482` — `_prepare_for_session_start`, `_handle_stop_action`, `_handle_restart_action`, `_handle_clear_console_action` coordinate `_run_session_controller`, `_run_service`, `_run_launch_workflow`, `_run_event_workflow`, and `clear_console_policy` hosts. `menu_wiring.py:51-52,63` binds run menu to MW stop/restart; `:63` clear console to MW.
- **Code-judo alternative:** Move to `RunSessionWorkflow` or extend `RunEventWorkflow` with `stop()`, `restart()`, `clear_sinks()` — menus wire direct. MW keeps only `MainWindowClearConsoleHost` adapter if policy requires window ports.
- **Suggested remediation:** TN-SHELL2-DEBUG-RUN slice; hard cutover menu bindings after workflow extraction.
- **Tests that would prove fix:** Integration run/stop tests unchanged; MW method count −4.
- **Handoff overlap:** CC-20, TN-SHELL2-DEBUG-RUN, CC-12

---

### TN-SHELL2-MW-6 — Help menu direct wiring to ShellHelpController (shrink-rule exemplar)

- **Persona:** TN-SHELL2-MW
- **Status:** NEW (post–Wave 1 pattern at baseline)
- **Severity:** NICE-TO-HAVE (positive)
- **Evidence:** `menu_wiring.py:121-128` — seven help callbacks are lambdas calling `window._help_controller.show_*` / `open_*` with `parent=window`; no `_handle_help_*` on MainWindow. `help_controller.py:21-35` — typed constructor with `resolve_theme_tokens` / `reveal_path_in_file_manager` callables (not `window: Any`).
- **Code-judo alternative:** Replicate this pattern for remaining MW-bound menus (editor text, run session).
- **Suggested remediation:** Use as template in implementation plan for CC-13 shrink PRs.
- **Tests that would prove fix:** Manual Help menu acceptance; no `rg "_handle_help" app/shell/main_window.py` matches.
- **Handoff overlap:** CC-13, CC-20

---

### TN-SHELL2-MW-7 — `main_window_panels.py` is a `window: Any` duck-typing graph (335 LOC)

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window_panels.py:40,60,113,203,254` — all builders take `window: Any` and mutate `window._activity_bar`, `window._search_sidebar`, `window._editor_tabs_widget`, etc. `build_bottom_panel` reaches `window._handle_python_console_submit` (`:279-281`), `window._editor_widgets_by_path` (`:144` via test explorer in `menu_wiring.py`), and six debug panel signals to `debug_control_workflow` (`:291-301`).
- **Code-judo alternative:** Introduce `MainWindowPanelHost` protocol (typed ports for theme tokens, workflows, widget slots) passed into builders — same decomposition move as `ShellHelpController` constructor injection. Deletes implicit private-field contract between panels and MW.
- **Suggested remediation:** Pair with TN-SHELL2-COMP typed-host migration; do not add new `window._*` reads in panel builders without protocol entry.
- **Tests that would prove fix:** Pyright clean on panel module with protocol stub; panel build smoke test with fake host.
- **Handoff overlap:** CC-20, CC-22, TN-SHELL2-COMP

---

### TN-SHELL2-MW-8 — Panel builder couples Python Console to private MainWindow handlers

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window_panels.py:279-281` — `input_submitted.connect(window._handle_python_console_submit)`, `interrupt_requested.connect(window._handle_python_console_interrupt)`, `restart_requested.connect(window._handle_start_python_console_action)`. REPL orchestration logic lives on MW (`main_window.py:456-499`) while `python_console_workflow.py` only supplies completion requester (`:282`).
- **Code-judo alternative:** `PythonConsoleWorkflow.bind_widget(console_widget)` owns submit/interrupt/restart; panel builder connects signals to workflow methods only.
- **Suggested remediation:** TN-SHELL2-CONSOLE slice; delete three MW handlers after cutover.
- **Tests that would prove fix:** REPL integration tests pass with workflow-owned bindings; `rg "_handle_python_console" app/shell/main_window.py` empty.
- **Handoff overlap:** CC-20, TN-SHELL2-CONSOLE, CC-18

---

### TN-SHELL2-MW-9 — `MenuCallbacks` 95-field dataclass is a dual-edit tax

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `menus.py:33-128` — `MenuCallbacks` declares **95** optional `Callable` fields. Every new menu action requires edits in **two** files: field in `menus.py` + binding in `menu_wiring.py`. `build_menu_stubs` (`:157-188`) fans out to six `*_menu_builder` modules via `MenuBuildContext`.
- **Code-judo alternative:** Collapse to per-menu callback dataclasses (`FileMenuCallbacks`, `RunMenuCallbacks`, …) colocated with builders, or register commands by ID in `ActionRegistry` only (menus become declarative command tables). New action = one row, not two dataclass fields.
- **Suggested remediation:** P2 refactor after P1 delegator shrink; avoid growing `MenuCallbacks` for plugin-only commands — use `register_runtime_menu_command`.
- **Tests that would prove fix:** Add-menu-action PR touches ≤2 modules with net LOC decrease.
- **Handoff overlap:** CC-20, CC-22

---

### TN-SHELL2-MW-10 — Language mode and project-entry dialogs are feature orchestrators still on MainWindow

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:304-339` — `_handle_set_language_mode_action` / `_handle_clear_language_override_action` own `QInputDialog`, mode list assembly, and status refresh (~36 LOC). `main_window.py:408-454` — `_resolve_project_entry_for_project_run` / `_prompt_for_project_entry_replacement` own missing-entry UX and `iter_python_files` candidate list (~47 LOC). `menu_wiring.py:118-119` binds language mode to MW.
- **Code-judo alternative:** `EditorTabWorkflow.handle_set_language_mode()` (dialog + override already editor-adjacent); `RunLaunchWorkflow.resolve_project_entry()` (entry resolution belongs with run launch, already owns project run actions).
- **Suggested remediation:** Extract in editor/run slices; wire menus direct.
- **Tests that would prove fix:** Unit tests on workflow methods with stub dialogs; MW loses ~80 LOC.
- **Handoff overlap:** CC-20, TN-SHELL2-EDITOR-SEAM, TN-SHELL2-DEBUG-RUN

---

### TN-SHELL2-MW-11 — Lifecycle correctly extracted; `closeEvent` is thin delegation

- **Persona:** TN-SHELL2-MW
- **Status:** NEW (post–Wave 1 pattern at baseline)
- **Severity:** NICE-TO-HAVE (positive)
- **Evidence:** `main_window.py:512-513` — `closeEvent` → `MainWindowLifecycle.handle_close_event(self, event)` only. `main_window_lifecycle.py:17-42` — unsaved-change decision via `SaveWorkflow`, `_is_shutting_down` flag, teardown, layout/history persistence, console history save. Document-safety path uses `DocumentScope.APPLICATION` (`:20`).
- **Code-judo alternative:** Keep; move timer `hasattr` soup in `begin_shutdown_teardown` (`:52-65`) to composition-owned timer registry in TN-SHELL2-COMP follow-up.
- **Suggested remediation:** None for MW slice; cross-reference COMP critic for teardown brittleness.
- **Tests that would prove fix:** Existing close/dirty-tab integration tests; manual decline-close acceptance.
- **Handoff overlap:** CC-06, TN-SHELL2-COMP, CC-05

---

### TN-SHELL2-MW-12 — CC-20 typing residual: `_semantic_navigation_workflow: Any` on MainWindow

- **Persona:** TN-SHELL2-MW
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `main_window.py:110` — `self._semantic_navigation_workflow: Any` in `__init__` field block (only explicit `Any` in MW module). `menu_wiring.py:106-107,113-117` binds five intelligence menu actions through duck-typed workflow. TYPE_CHECKING block (`:39-66`) omits semantic navigation workflow import.
- **Code-judo alternative:** Add `SemanticNavigationWorkflow` to TYPE_CHECKING imports; type field as concrete class or narrow protocol.
- **Suggested remediation:** Optional P2 typing pass (INT-R-19 analog); zero runtime change.
- **Tests that would prove fix:** `npx pyright app/shell/main_window.py` — no new errors; field typed.
- **Handoff overlap:** CC-20, Intelligence CC-10

---

## Slice metrics (baseline `fccb611`)

| Metric | Value |
|--------|------:|
| `main_window.py` LOC | 542 |
| `MainWindow` methods | 45 |
| `main_window_panels.py` LOC | 335 |
| `menu_wiring.py` LOC | 154 |
| `menus.py` LOC | 212 |
| `menu_wiring` → `window._handle_*` bindings | 11 |
| `menu_wiring` → `_help_controller` direct | 7 |
| Files ≥1k in slice | 0 |
| Delta vs baseline in slice files | 0 bytes (unchanged @ kickoff) |

---

## Verdict summary

| Gate | Result |
|------|--------|
| AD-015 method ceiling (≤45 @ baseline) | **PASS** (exactly 45) |
| 1k-line rule (slice) | **PASS** |
| CC-06 god file | **SUBSTANTIALLY CLOSED** |
| CC-13 delegators | **PARTIALLY CLOSED** — P1 shrink backlog |
| CC-20 menu workflows | **SUBSTANTIALLY CLOSED** — P1 run/editor/console residuals |
| REGRESSION vs Shell Wave 1 intent | **NONE** in slice |

**APPROVE.** The MainWindow delta slice achieves the Shell Wave 1 decomposition goal and must not be re-opened to the obsolete 5.5k monolith audit. Ship-blocking issues live elsewhere (`icon_provider` 1k+, composition injection soup in TN-SHELL2-COMP). **P1 before method-count target <40:** TN-SHELL2-MW-2, MW-5, MW-8 (editor text + run session + console handler shrink). **Keepers:** TN-SHELL2-MW-1, MW-4, MW-6, MW-11.
