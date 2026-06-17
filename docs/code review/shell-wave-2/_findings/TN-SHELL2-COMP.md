# TN-SHELL2-COMP — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-COMP  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/main_window_composition.py` (590 LOC), `app/shell/shell_composition.py` (584 LOC), `app/shell/intelligence_composition.py` (32 LOC), `app/shell/main_window_lifecycle.py` (98 LOC). Cross-read: `main_window.py` (542 LOC / 45 methods), `editor_tab_workflow.py`, `editor_tab_content_registry.py`, `save_workflow.py`, `runtime_support_workflow.py`, `local_history_workflow.py`. Re-validate Shell Wave 1 **CC-06**, **CC-07**, **CC-22**.

---

## Executive verdict

**REJECT — composition root is not thermo-clean.** Shell Wave 1’s MainWindow god-file split **worked at the class boundary** (`main_window.py` 542 LOC / 45 methods vs 5,549 / 332), but the dominant complexity **relocated** into `install_main_window_composition` (465-line setattr grid, 53 shell imports + 29 cross-domain imports, 339 `window._*` touches) and `shell_composition.py` (six `MainWindow*Host` adapters, all `window: Any`). **CC-06** is **PARTIALLY FIXED** (MainWindow slim; mega-compositor debt persists). **CC-07** remains **OPEN** (79 `window: Any` shell-wide; SaveWorkflow and host ports untyped). **CC-22** is **PARTIAL** (layout-before-test-runner ordering preserved; forward-reference lambdas; `hasattr` timer guards in lifecycle). Positive keepers: `intelligence_composition.py` extraction, `EditorTabContentRegistry` seam, `editor_tab_workflow.py` at 101 LOC. Dominant risk: new features will keep landing as more host adapters and composition-line growth without a typed `ShellCompositionContext`.

---

## CC re-validation summary

| CC | Wave 1 theme | Status @ HEAD | Evidence |
|----|--------------|---------------|----------|
| **CC-06** | MainWindow god file / composition monolith | **PARTIALLY FIXED** | `main_window.py` 542 LOC / 45 methods — AD-015 win. Debt → `main_window_composition.py` 590 LOC, 82 import lines, single 465-line installer. |
| **CC-07** | `window: Any` ceremonial workflows | **OPEN** | `install_main_window_composition(window: Any)`; `SaveWorkflow(window)`; 6 hosts in `shell_composition.py` all `window: Any`; 79 shell-wide `window: Any` (manifest kickoff). |
| **CC-22** | Init ordering / lambda injection soup | **PARTIAL** | Test runner after layout (482–517); `LocalHistoryWorkflow` lambdas reference `_editor_tab_workflow` before assignment (360–405); 28 `lambda:` in composition; 9 `setattr(window` closures; lifecycle `hasattr` timer guards (52–65). |

---

### TN-SHELL2-COMP-1 — CC-06 debt relocated: mega-compositor replaces god `__init__`

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:125-590` — `install_main_window_composition` assigns 100+ `window._*` fields across 465 lines. Import block `:41-112` pulls **53** `app.shell.*` modules plus bootstrap/core/editors/intelligence/persistence/plugins/run domains. `rg "window\._" app/shell/main_window_composition.py` → **339** touches.
- **Code-judo alternative:** Replace the setattr grid with a **`ShellCompositionContext` dataclass** (services, schedulers, panel refs, preference snapshot) built in phased `build_*` functions that return wired subsystems. `MainWindow.__init__` holds context + delegates; composition file splits by concern (`shell_services.py`, `shell_workflows.py`, `shell_timers.py`) each under ~200 LOC.
- **Suggested remediation:** R2 wave-4 continuation — extract preference loading into immutable `ShellPreferencesSnapshot` (CC-06/CC-22 joint fix); cap `main_window_composition.py` at orchestration calls only; track LOC/method budget in AD-015 gate.
- **Tests that would prove fix:** `tests/unit/shell/test_shell_composition.py` — construct all workflows from fake context without `MainWindow`; smoke: editor opens after refactor.
- **Handoff overlap:** CC-06, CC-22, R2, AD-015

---

### TN-SHELL2-COMP-2 — CC-07 OPEN: `shell_composition.py` host adapter explosion (`window: Any`)

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/shell_composition.py:33-437` — six `MainWindow*Host` classes (`EditorSync`, `ExternalFileChange`, `SettingsApply`, `PythonConsole`, `RunLaunch`, `ShellTheme`), each `def __init__(self, window: Any)`. `MainWindowRunLaunchHost` exposes **11** methods returning `Any` (`:307-374`). All `build_*_workflow(window: Any)` factories at `:235-567`. Shell-wide **25** `MainWindow*Host` classes across `app/shell/` (host proliferation without shared port bundle).
- **Code-judo alternative:** Collapse per-workflow host classes into **typed protocol bundles** (`ShellEditorPorts`, `ShellRunPorts`, `ShellThemePorts`) defined once; workflows depend on protocols, not `MainWindow` private fields. Delete pass-through host methods that only forward `window._foo`.
- **Suggested remediation:** Migration plan per manifest gate 3: one workflow per PR inverts deps (Save → Debug → RunLaunch); introduce `Protocol`/`TypedDict` host ports; stop adding new `MainWindow*Host` classes.
- **Tests that would prove fix:** Unit tests construct `SettingsApplyWorkflow` / `RunLaunchWorkflow` with stub hosts — no `MainWindow` import (pattern: `test_settings_apply_workflow.py` fake host).
- **Handoff overlap:** CC-07, CC-SHELL2-typed-hosts (INTEG), R2

---

### TN-SHELL2-COMP-3 — CC-22 PARTIAL: ordering-sensitive composition with forward-reference lambdas

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:360-405` — `LocalHistoryWorkflow(...)` wired at 360 with `tab_index_for_path=lambda: window._editor_tab_workflow.tab_index_for_path` but `window._editor_tab_workflow = build_editor_tab_workflow(window)` not until **405** (forward reference via deferred lambda). `:482-517` — `build_layout_shell(window)` before `TestRunnerWorkflow(..., test_explorer_panel=window._test_explorer_panel)` — same fragile layout-first pattern from Wave 1 MW-01-4. `:325` — `bootstrap_intelligence_runtime` before `_editor_tab_workflow`, `_settings_apply_workflow`, theme workflow exist on window.
- **Code-judo alternative:** **Two-phase composition:** (1) `ShellWidgetGraph = build_layout_shell(...)` returns panel refs; (2) `wire_workflows(graph, services)` with explicit dependency DAG — no field may be read before its builder returns. Replace forward lambdas with late-bound registry or explicit `wire_local_history(editor_tab_workflow)` call after both exist.
- **Suggested remediation:** Document init DAG in `ARCHITECTURE.md`; refactor `build_layout_shell` to return struct; add composition-order unit test asserting no AttributeError on cold start.
- **Tests that would prove fix:** Unit test: simulate composition phases; assert `LocalHistoryWorkflow` callbacks only registered after `EditorTabWorkflow` exists; integration: close/reopen project with history restore.
- **Handoff overlap:** CC-22, CC-06, R2

---

### TN-SHELL2-COMP-4 — CC-22: lambda / `setattr` injection soup persists at composition root

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:335-359` — `RuntimeSupportWorkflow` takes 15+ callables including `set_latest_health_report=lambda report: setattr(window, "_latest_health_report", report)` and four sibling `set_latest_*` setattr mutators. `:155-181` — `DeclarativeContributionManager` with 9 `self`-closing lambdas. `:442-444` — `DiagnosticsOrchestrator` setattr for pending lint path and runtime modules. **28** `lambda:` occurrences in file.
- **Code-judo alternative:** Single **`ShellRuntimeState`** / `RuntimeIssueState` dataclass passed by reference; plugin bridge becomes `PluginShellBridge.register(contribution_manager, command_broker)` — zero anonymous setattr closures.
- **Suggested remediation:** Extract runtime issue fields (`_latest_health_report`, `_latest_import_issue_report`, etc.) into owned state object; collapse `_plugin_activation_workflow.on_catalog_changed` setattr into context field.
- **Tests that would prove fix:** Unit test on `RuntimeIssueState` merge; plugin registration without full MainWindow.
- **Handoff overlap:** CC-22, CC-07, R2

---

### TN-SHELL2-COMP-5 — Layer inversion: L1 workflow imports L0 composition upward

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:23` — `from app.shell.shell_composition import build_editor_sync_workflow`. Manifest P1 dependency graph flags this as top risk (“workflow→composition upward import”). L0 `main_window_composition` imports `editor_tab_workflow`; L1 `editor_tab_workflow` imports L0 `shell_composition` — circular coupling seam.
- **Code-judo alternative:** Move `build_editor_sync_workflow` / `MainWindowEditorSyncHost` to **`editor_sync_composition.py`** (or inline factory next to `EditorSyncWorkflow`) so workflows never import the mega-compositor module. Composition root imports both; dependency arrow is one-way.
- **Suggested remediation:** Extract editor-sync host+factory from `shell_composition.py`; delete upward import from `editor_tab_workflow.py`; add import-lint rule: workflows must not import `shell_composition` or `main_window_composition`.
- **Tests that would prove fix:** Import graph test: `editor_tab_workflow` has no transitive import of `main_window_composition`.
- **Handoff overlap:** CC-06, CC-SHELL2-layer-inversion (INTEG), Editors CC-EDIT-01

---

### TN-SHELL2-COMP-6 — CC-07: SaveWorkflow still raw `window: Any` at composition seam

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:275` — `window._save_workflow = SaveWorkflow(window)`. Wave 1 TN-SHELL-MW-01-2 documented ~40 `window._*` accesses inside SaveWorkflow with no typed host. Document-safety gate 4 depends on this path (`MainWindowLifecycle.handle_close_event` → `_save_workflow.request_unsaved_changes_decision`).
- **Code-judo alternative:** `SaveWorkflow(ShellDocumentHost)` protocol with explicit ports: `editor_manager`, `loaded_project`, `dialog_parent`, dirty-tab enumerator — same inversion already used by `ProjectController` callback ports.
- **Suggested remediation:** Prioritize SaveWorkflow host extraction in R2 wave-4; wire from composition via narrow port bundle, not whole window.
- **Tests that would prove fix:** `tests/unit/shell/test_save_workflow.py` with stub host only; close-event integration without `MainWindow.__new__`.
- **Handoff overlap:** CC-07, CC-03 (document safety), R2

---

### TN-SHELL2-COMP-7 — Theme fan-out: nested QTimer deferred-rehighlight chain in host adapter

- **Persona:** TN-SHELL2-COMP
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/shell_composition.py:475-495` — `MainWindowShellThemeHost._build_child_callbacks.apply_editor_themes` builds `deferred_widgets` list, applies theme with `defer_syntax_rehighlight`, then chains `flush_next_deferred_editor` via recursive `QTimer.singleShot(0, ...)`. Orchestration lives inside a host callback factory, not `ShellThemeWorkflow` or editor domain.
- **Code-judo alternative:** **`EditorThemeBatchPolicy`** in editors layer: `apply_theme_to_all_editors(widgets, active_path, tokens)` owns defer/flush semantics; host callback is one line. Removes timer recursion from composition.
- **Suggested remediation:** Extract defer/flush policy to `app/editors/` or `shell_theme_workflow.py`; host delegates; add perf test under `tests/integration/performance/` if behavior is perf-motivated.
- **Tests that would prove fix:** Unit test: N editors → active immediate, inactive deferred flush order; four-theme smoke unchanged.
- **Handoff overlap:** CC-09, CC-23, TN-SHELL2-STYLES

---

### TN-SHELL2-COMP-8 — `MainWindowShellThemeHost._build_child_callbacks` is a 90-line closure factory

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/shell_composition.py:472-563` — `_build_child_callbacks` defines 10 nested functions closing over `window._*` (editors, markdown registry, console, run log, search sidebar, activity bar, menus, test explorer, outline, app tooltip). Host class mixes **port forwarding** with **feature orchestration**.
- **Code-judo alternative:** Split into **`ShellThemeSurfaceAppliers`** module with one function per surface, each taking explicit widget refs from `ShellWidgetGraph` — `MainWindowShellThemeHost` only exposes properties, no nested defs.
- **Suggested remediation:** Co-locate appliers with `shell_theme_workflow.py`; shrink host to token/property accessor only.
- **Tests that would prove fix:** `test_shell_theme_workflow.py` extended to cover deferred editor path and markdown registry delegate.
- **Handoff overlap:** CC-09, CC-23, TN-SHELL2-STYLES

---

### TN-SHELL2-COMP-9 — `intelligence_composition.py` extraction is correct direction but untyped

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/intelligence_composition.py:13-32` — `bootstrap_intelligence_runtime(window: Any, ...)` assigns five intelligence fields via setattr. Called from `main_window_composition.py:325` mid-installer before downstream workflows consume `_semantic_session`.
- **Code-judo alternative:** Return **`IntelligenceRuntimeBundle`** (session, controller, background_tasks, coordinator, generation counter); composition assigns `window._intelligence = bundle` once. Enables testing bootstrap without MainWindow.
- **Suggested remediation:** Keep module; add typed return dataclass in follow-up PR — low risk, high clarity.
- **Tests that would prove fix:** Unit test: bootstrap from fake dispatch callable yields wired controller + session.
- **Handoff overlap:** CC-10, Intelligence CC-06/CC-10, TN-SHELL2-EDITOR-SEAM

---

### TN-SHELL2-COMP-10 — Lifecycle `hasattr` timer guards signal optional wiring debt (CC-22 symptom)

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window_lifecycle.py:52-65` — `begin_shutdown_teardown` uses `hasattr(window, "_run_event_timer")` (and 5 more timers) before `.stop()`. Contrasts with unconditional stops at `:47-49` for timers always created in composition.
- **Code-judo alternative:** **`ShellTimerRegistry`** created in composition registers all QTimers; lifecycle calls `timer_registry.stop_all()` — no hasattr, no missed timer on partial init failure.
- **Suggested remediation:** Register timers in composition return struct; lifecycle stops registry unconditionally.
- **Tests that would prove fix:** `test_main_window_background_teardown.py` extended — partial-init mock still teardown-safe.
- **Handoff overlap:** CC-22, CC-24

---

### TN-SHELL2-COMP-11 — Positive: `EditorTabContentRegistry` is the right composition seam

- **Persona:** TN-SHELL2-COMP
- **Status:** NEW
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** `app/shell/editor_tab_content_registry.py:10-24` — typed registry wrapping markdown panes; `main_window_composition.py:211` wires once; `shell_composition.py:497-498` delegates `apply_all_markdown_themes` to registry instead of iterating panes inline.
- **Code-judo alternative:** **Extend pattern** — code-editor widget map could move under same registry so theme host stops touching `window._editor_widgets_by_path` directly.
- **Suggested remediation:** Do not revert; use as template for editor surface SSOT in TN-SHELL2-STYLES / TN-SHELL2-EDITOR-SEAM.
- **Tests that would prove fix:** Unit test on registry theme fan-out (missing today per manifest gap table).
- **Handoff overlap:** Editors CC-EDIT-*, TN-SHELL2-EDITOR-SEAM

---

### TN-SHELL2-COMP-12 — Composition test gap: no installer characterization tests

- **Persona:** TN-SHELL2-COMP
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** Manifest P5: **High gap** for `main_window_composition` / `shell_composition`. `rg` tests → only `test_main_window_lifecycle.py` (lifecycle) and `test_main_window_debug_routing.py` (imports `MainWindowRunLaunchHost` only). No test executes `install_main_window_composition` wiring order or host port contracts.
- **Code-judo alternative:** Fake-window composition test harness (minimal QWidget + namespace) validating field presence and workflow non-None after install — catches CC-22 ordering regressions without full UI.
- **Suggested remediation:** Add after CC-06 decomposition PR, not before — test the stable context API, not the setattr list.
- **Tests that would prove fix:** `test_shell_composition_wiring.py` — field DAG / smoke.
- **Handoff overlap:** CC-24, P5 test map

---

## Approval bar checklist

| Gate | Result |
|------|--------|
| AD-015 MainWindow method count ≤45 | **PASS** (45 @ HEAD) |
| No composition file >1k LOC | **PASS** (590 / 584 max) |
| CC-06 closed | **FAIL** — PARTIAL; debt in mega-compositor |
| CC-07 closed | **FAIL** — OPEN |
| CC-22 closed | **FAIL** — PARTIAL |
| Typed host ports | **FAIL** — presumptive blocker |
| No upward workflow→composition import | **FAIL** — `editor_tab_workflow` → `shell_composition` |
| Document safety via SaveWorkflow | **PASS** (behavior wired; typing debt) |

**Verdict: REJECT.** Ship Wave 1 P0 closures (CC-01…05) remain intact, but the composition slice fails the thermo-clean bar: complexity was **relocated**, not **deleted**; host adapter and `window: Any` growth continue; init ordering and layer inversion remain exploitable debt. Do not add features to `install_main_window_composition` until phased context extraction lands (R2/CC-06/CC-22/CC-07 track).
