# TN-SHELL-MW-01 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-01  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 1–772 — imports, `MainWindow.__init__`, widget graph construction, controller/workflow wiring. Cross-read: `save_workflow.py`, `python_style_workflow.py`, `debug_control_workflow.py`, `plugin_activation_workflow.py`, `runtime_support_workflow.py`, `local_history_workflow.py`, `test_runner_workflow.py`, `editor_tabs_coordinator.py`, `editor_tab_factory.py`, `editor_workspace_controller.py`, `project_controller.py`, `project_tree_action_coordinator.py`, `diagnostics_search_coordinator.py`, `problems_controller.py`, `run_debug_presenter.py`, `main_window_layout.py`, `python_tooling_status_controller.py`.

---

## Executive verdict

**Not thermo-clean.** AD-015 decomposition has started, but this slice is still a 460-line `__init__` inside a **5,549-line** file (332 methods at kickoff). Several extracted modules exist on paper; many are **ceremonial** — they take `window: Any` and reach into `MainWindow` private fields instead of owning state or accepting narrow collaborators. Real ownership shows up in `EditorWorkspaceController`, `ProjectController`, and `PluginActivationWorkflow`; the dominant pattern elsewhere is **complexity relocation** (10–17 lambda injections, `setattr` mutators) rather than deletion. The highest risk for the next shell wave is that new features will keep landing as more init wiring and more `window._*` couplings, violating R2’s “method count must go down” rule. No four-theme UI regression is introduced in this slice (wiring only); `_apply_theme_styles()` at line 732 delegates to later theme logic (MW-03).

---

### TN-SHELL-MW-01-1 — 5.5× past the 1k-line boundary; __init__ is a second monolith

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:308-771` — `MainWindow.__init__` spans ~460 lines and assigns 50+ instance fields before startup timers; file total is 5,549 LOC per wave manifest.
- **Code-judo alternative:** Treat `MainWindow` strictly as a **thin composition root**: one `ShellCompositionContext` dataclass holding shared services (settings, event bus, schedulers), plus focused `build_*` modules that return wired subsystems. `__init__` should read like 30–40 lines of assembly, not a scroll of field declarations.
- **Suggested remediation:** Introduce `app/shell/shell_composition.py` (or split by concern: `shell_preferences.py`, `shell_widget_graph.py`, `shell_workflow_wiring.py`) and move init clusters out wholesale. Target: each new R2 PR drops **MainWindow method count** and **init LOC**, not just adds a workflow file.
- **Tests that would prove fix:** `tests/unit/shell/test_shell_composition.py` — assert all workflows/controllers are constructible from a fake context without importing half of `app/`; smoke test that editor opens after composition refactor.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-2 — “Extracted” workflows are god-object facades (`window: Any`)

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/save_workflow.py:38-39` — `def __init__(self, window: Any) -> None: self._window = window` with ~40 `window._*` accesses in the same module. Same pattern in `python_style_workflow.py:22-23`, `debug_control_workflow.py:25-26`, `editor_tabs_coordinator.py:14-15`, `editor_tab_factory.py:20-21`, `problems_controller.py:16-17`, `run_debug_presenter.py:19-20`. Wired from `main_window.py:507-508`, `336`, `435`, `549-551`, `357`.
- **Code-judo alternative:** Invert dependency: workflows receive **explicit ports** (editor access, run service, settings snapshot, dialog parent) via a small typed `ShellEditorHost` / `ShellRunHost` protocol bundle — the same shape `ProjectController.open_project_by_path` already uses with `confirm_proceed` / `on_loaded` callbacks (`project_controller.py:22-29`).
- **Suggested remediation:** For R2 wave-4 items (Save/PythonStyle/Debug), replace `window: Any` with constructor-injected callables and **move breakpoint/diagnostic state** into `DebugControlWorkflow` / `ProblemsController` instead of leaving dicts on `MainWindow`. Delete MainWindow pass-through methods as each workflow absorbs real ownership.
- **Tests that would prove fix:** Unit tests construct `SaveWorkflow` / `DebugControlWorkflow` with stub hosts (no `MainWindow` import); existing `tests/unit/shell/` characterization tests stay green.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-3 — Settings/preferences bootstrap is an __init__ waterfall

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:368-497` — sequential `_load_runtime_onboarding_state()`, `_load_import_update_policy()`, `_load_editor_preferences()`, `_load_completion_preferences()`, `_load_diagnostics_preferences()`, `_load_output_preferences()`, `_load_intelligence_runtime_settings()`, `_load_local_history_retention_policy()`, `_load_theme_mode()`, `_load_ui_font_weight()`, `_load_shortcut_overrides()`, `_load_syntax_color_overrides()`, `_load_lint_rule_overrides()`, `_load_selected_linter()` (implementations begin at line 885+ but **all invocation lives in this slice**).
- **Code-judo alternative:** Single `ShellPreferencesSnapshot.load(settings_service, state_root)` returning an immutable dataclass consumed by theme, editor, intelligence, and plugin subsystems — one read pass, no 15-tuple unpacking into loose fields.
- **Suggested remediation:** Add `app/shell/shell_preferences.py` with `load_shell_preferences()` / `ShellPreferencesSnapshot`; `__init__` assigns `self._prefs = ...` once. Align with `settings_models.py` parsers already imported at lines 141-151.
- **Tests that would prove fix:** Unit test: given fixture settings JSON, snapshot matches current scattered `_load_*` outputs; regression on effective editor settings when project overrides exist.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-4 — Fragile init ordering: layout before `TestRunnerWorkflow`

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:673-707` — `_configure_window_frame()` / `_build_layout_shell()` run at 673–674; nested `active_test_editor()` and `TestRunnerWorkflow(...)` construction at 676–707 **after** layout because `test_explorer_panel=self._test_explorer_panel` (692) is populated by `build_layout_shell` → panel builders.
- **Code-judo alternative:** Two-phase composition: (1) build widget graph and capture panel refs in a `ShellWidgetGraph` return value; (2) wire workflows from that struct. No workflow constructor should depend on “hope `_build_layout_shell` ran first.”
- **Suggested remediation:** Have `build_layout_shell` return a dataclass of panel refs; pass into `TestRunnerWorkflow` in a dedicated `_wire_test_runner()` called immediately after graph build. Consider lazy `TestRunnerWorkflow` property if panel optional.
- **Tests that would prove fix:** Unit test that `TestRunnerWorkflow` receives non-`None` explorer panel when layout builder ran; integration test: test discovery refresh on startup (line 741) still fires.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-5 — Lambda / `setattr` injection soup relocates coupling, does not remove it

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:578-596` — `RuntimeSupportWorkflow` takes 15 callables including `set_latest_health_report=lambda report: setattr(self, "_latest_health_report", report)`. Similar at `621-645` (`DiagnosticsOrchestrator` with `setattr` for pending lint path and runtime modules), `652-671` (`ProjectTreeActionCoordinator` with 14 lambdas), `386-405` (`DeclarativeContributionManager` with 9 `self`-closing lambdas), `428` (`on_catalog_changed=lambda catalog: setattr(self, "_workflow_provider_catalog", catalog)`).
- **Code-judo alternative:** Shared **mutable context object** (e.g. `ShellRuntimeState`, `ShellEditorState`) owned by composition root and passed by reference — workflows mutate documented fields instead of anonymous `setattr` closures. Plugin bridge becomes `PluginShellBridge.register_with(contribution_manager, command_broker, event_bus)`.
- **Suggested remediation:** Collapse runtime issue report fields (`_latest_health_report`, `_latest_import_issue_report`, etc., lines 540-545) into one `RuntimeIssueState` dataclass owned by `RuntimeSupportWorkflow` or a `RuntimeStateHolder`. Replace `DeclarativeContributionManager` inline lambdas with a small adapter class.
- **Tests that would prove fix:** Unit tests on `RuntimeIssueState` merge behavior; plugin contribution registration test without constructing full `MainWindow`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-6 — Debug breakpoint state wired into unrelated workflows at init

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:437-438`, `616-619`, `661-662` — `_breakpoints_by_file` / `_breakpoint_specs_by_key` live on `MainWindow` but are injected into `LocalHistoryWorkflow` (`ensure_breakpoint_spec`, `breakpoints_by_file`, `breakpoint_specs_by_key`, `refresh_breakpoints_list`) and `ProjectTreeActionCoordinator` (`breakpoints_by_file`, `refresh_breakpoints_list`). `DebugControlWorkflow` also mutates the same dicts (`debug_control_workflow.py:70-71`).
- **Code-judo alternative:** `BreakpointStore` (or full ownership inside `DebugControlWorkflow`) as the single SSOT; tree/history workflows call `breakpoint_store.remap_paths()` / `clear_for_file()` through a narrow interface.
- **Suggested remediation:** Move breakpoint dicts into `DebugControlWorkflow` (R2 candidate #2); expose `remap_for_move`, `clear_all`, `specs_for_launch` methods. Remove debug parameters from `LocalHistoryWorkflow.__init__`.
- **Tests that would prove fix:** Unit test: file move remaps breakpoints in store and syncs editors; debug panel list refresh still correct after tree delete.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-7 — Startup timer cluster belongs in `RuntimeOnboardingWorkflow`

- **Persona:** TN-SHELL-MW-01
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:743-771` — eight `QTimer` instances started at end of `__init__` (`_run_event_timer`, `_repl_event_timer`, `_external_change_poll_timer`, `_restore_project_timer`, `_auto_start_repl_timer`, `_runtime_probe_timer`, `_startup_probe_refresh_timer`) plus `StartupCapabilityFacade.set_refresh_callback` at 771; overlaps R2 brief item 3 (runtime onboarding / probe refresh).
- **Code-judo alternative:** `ShellStartupLifecycle.start()` encapsulates timer creation, intervals, and ordering; `MainWindow.__init__` calls one method. Probe/onboarding timers co-locate with `_load_runtime_onboarding_state()` (368–371).
- **Suggested remediation:** Extract `RuntimeOnboardingWorkflow` or `ShellStartupLifecycle` per handoff R2 § candidate 3; move `_start_runtime_module_probe` / `_refresh_startup_capability_report_async` wiring with it.
- **Tests that would prove fix:** Unit test with `QTest`/`QTimer` fakes: lifecycle starts expected timers once; shutdown (MW-16) stops them — no duplicate starts on re-init.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-01-8 — 265-line import block makes every domain a shell dependency

- **Persona:** TN-SHELL-MW-01
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:37-264` — imports span intelligence, debug, packaging, plugins, run, editors, persistence, templates, examples, python_tools, and 30+ shell submodules in one file header.
- **Code-judo alternative:** Composition modules own their imports (`shell_workflow_wiring.py` imports run/debug; `shell_intelligence_wiring.py` imports intelligence). `main_window.py` imports only composition facades + Qt + core shell chrome.
- **Suggested remediation:** Split imports by following the same decomposition as findings 1 and 3; avoid TYPE_CHECKING re-exports unless needed for annotations.
- **Tests that would prove fix:** Import-lint or pyright package boundary check: `main_window.py` import count drops materially post-split.
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `EditorWorkspaceController` (`main_window.py:431-433`) — real state ownership with a clean alias export.
- `ProjectController` — callback-based boundary, no `window: Any`.
- `PluginActivationWorkflow` — typed protocols and explicit dependencies (`plugin_activation_workflow.py`).
- `main_window_layout.build_layout_shell` — layout logic lives outside the class (though `MainWindow._build_layout_shell` at line 4419 is a one-line delegator R2 explicitly discourages).

---

## Approval bar (this slice)

**Would not approve** a change that adds more `__init__` fields or `window: Any` workflows without a parallel reduction in `MainWindow` method count and god-object couplings. R2 acceptance criteria require net method shrink on every MainWindow-touching PR.
