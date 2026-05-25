# TN-SHELL-MW-07 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-07  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 2665–2936 — help tail pass-throughs, project open/load funnel (`_open_project_by_path`, `_apply_loaded_project`), welcome/editor screen switching, menu state sync, lazy presenter getters, run preflight, run/debug project entry points. Upstream callers in adjacent slices: template/example/new-project actions (MW-05/06) converge on `_open_project_by_path`; packaging actions live in `runtime_support_workflow.py` (not this line range) but project load resets packaging issue state here.

---

## Executive verdict

**Not thermo-clean.** This slice is the shared **project-load choke point** for template, example, blank, and recent-project flows, yet almost all post-open orchestration still lives in `_apply_loaded_project` — a ~60-line, 25-step sequential mutator on a **5,549-line / 332-method** class. `ProjectController` extracted confirm/open/error only; the `on_loaded` lambda keeps every subsystem touch on `MainWindow`, violating AD-015 and the R2 handoff (“method count must go down; no one-line delegators”). Run/debug project handlers duplicate the same guard + config-resolution + preflight path; run preflight presentation starts here and continues into MW-08. Packaging is not implemented in this range, but runtime/package issue reports are cleared here, coupling project open to `RuntimeSupportWorkflow` state. Dominant risk: **non-decomposable project-load orchestration that will absorb the next template, exclude, or runtime feature unless cut over to a `ProjectLoadWorkflow` first.**

---

### TN-SHELL-MW-07-1 — `_apply_loaded_project` is a mega-orchestrator that should not live on MainWindow

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2717-2778` — single method persists prior local-history state, assigns `_loaded_project`, clears five runtime issue report fields, reloads lint/plugin tooling, switches center stack, retitles window, repopulates tree, resets tabs, reconfigures search excludes, clears breakpoints, restores local history, lints all files, refreshes debug breakpoints, menus, run states, optionally rebuilds intelligence cache, starts symbol indexing, publishes events, persists last path, and refreshes test discovery.
- **Code-judo alternative:** Introduce **`ProjectLoadWorkflow`** (R2) with a typed `ProjectLoadContext` and phased hooks: `persist_previous_session`, `reset_runtime_diagnostics`, `apply_shell_chrome`, `apply_editor_surface`, `apply_search_and_indexing`. MainWindow passes narrow collaborators (tree populator, tab coordinator, event bus) — not `self`. `_open_project_by_path` becomes `project_controller.open(..., on_loaded=workflow.apply)`.
- **Suggested remediation:** Characterize current ordering with one integration test, then hard-cut `_apply_loaded_project` body into the workflow module. MainWindow retains wiring only.
- **Tests that would prove fix:** Integration test opening project A then B asserts tab reset, tree signature, issue-report clears, and event publish order; unit tests on workflow phases without constructing full `MainWindow`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-2 — `ProjectController` extraction stopped halfway; load UI state still bounces through lambdas

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2671-2678` —

  ```python
  return self._project_controller.open_project_by_path(
      project_root,
      confirm_proceed=self._save_workflow.confirm_proceed_with_unsaved_changes,
      on_loaded=lambda loaded_project: self._apply_loaded_project(loaded_project, started_at=started_at),
      on_error=self._show_open_project_error,
      exclude_patterns=self._load_effective_exclude_patterns(project_root),
  )
  ```

  `app/shell/project_controller.py:22-49` owns disk open + recent tracking only; all shell mutation remains in MainWindow callbacks.
- **Code-judo alternative:** Extend `ProjectController` or add `ProjectLoadWorkflow` as the **`on_loaded` owner** so template/example/new-project/recent flows share one module, not four copies of “call `_open_project_by_path`”.
- **Suggested remediation:** Move `_show_open_project_error`, telemetry (`started_at`), and exclude loading into the workflow/controller pair; delete the lambda sandwich.
- **Tests that would prove fix:** Existing `tests/unit/shell/test_project_controller.py` plus new workflow tests; integration tests call public workflow API instead of `_open_project_by_path`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-3 — Run and debug project handlers are near-duplicate branches

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2903-2935` — `_handle_run_project_action` and `_handle_debug_project_action` share identical “no project” guard, `_resolve_active_named_run_config()` branch, default-entry preflight via `_ensure_run_preflight_ready`, and differ only in debug breakpoints / `_last_debug_target` assignment.
- **Code-judo alternative:** One `_start_project_session(*, debug: bool) -> bool` on a **`RunLaunchWorkflow`** (or `RunDebugPresenter`) that accepts optional breakpoint builder and post-start hook. Menu actions become one-liners wired directly to the workflow — not two nearly identical MainWindow methods.
- **Suggested remediation:** Collapse before MW-08 extracts `_start_session`; avoids duplicating the same refactor twice.
- **Tests that would prove fix:** Parametrized unit/integration tests: `(debug=False/True) × (named config / default entry / preflight failure)`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-4 — Run preflight orchestration belongs with run session code, not MainWindow

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2873-2895` — `_show_run_preflight_result` builds `RuntimeIssueReport`, opens runtime center, appends console line; `_ensure_run_preflight_ready` wraps `build_run_preflight(...)` and gates project run/debug entry points in this slice.
- **Code-judo alternative:** Move preflight gate + presentation to `RunSessionController` or `RunDebugPresenter` (already owns run UX messaging at `run_debug_presenter.py:53-73`). MainWindow run menu callbacks delegate to presenter/workflow only.
- **Suggested remediation:** Extract as part of run-session decomposition (coordinate with TN-SHELL-MW-08); delete `_show_run_preflight_result` / `_ensure_run_preflight_ready` from MainWindow.
- **Tests that would prove fix:** Relocate/extend `tests/integration/shell/test_run_preflight_integration.py` to target the new owner’s public API.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-5 — One-line delegators and help pass-throughs violate MainWindow shrink rule

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2665-2669` — `_handle_headless_notes_action` / `_handle_about_action` forward to `_help_controller` only; `2681-2682` — `_load_effective_exclude_patterns` wraps `load_effective_exclude_patterns`; `2690-2693` — `_refresh_welcome_project_list` wraps `_refresh_welcome_widget_state`; `2897-2901` — `_handle_run_action` / `_handle_debug_action` delegate to `_start_active_file_session`.
- **Code-judo alternative:** Wire menus in `menu_wiring.py` directly to `HelpController`, `load_effective_exclude_patterns`, welcome workflow refresh, and run-session starter — matching the R2 “thin pass-through cleanup” note for help actions. No new MainWindow methods for pure forwards.
- **Suggested remediation:** R2 pass-through cleanup PR: connect callbacks at wiring site; remove methods; verify `rg "^    def " app/shell/main_window.py | wc -l` decreases.
- **Tests that would prove fix:** Menu wiring tests assert correct callback targets without requiring `_handle_about_action` on MainWindow.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-6 — Project load resets packaging/runtime issue state inside shell orchestration

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2723-2728` —

  ```python
  self._latest_health_report = None
  self._latest_import_issue_report = RuntimeIssueReport(workflow="import", issues=[])
  self._latest_run_issue_report = RuntimeIssueReport(workflow="run", issues=[])
  self._latest_package_issue_report = RuntimeIssueReport(workflow="package", issues=[])
  self._latest_runtime_issue_report = self._build_runtime_issue_report()
  ```

  Packaging actions are owned by `RuntimeSupportWorkflow.handle_package_project_action` (`runtime_support_workflow.py:146+`), yet project open clears package issues on MainWindow.
- **Code-judo alternative:** `RuntimeSupportWorkflow.reset_diagnostics_for_project_change()` (or store issue reports inside the workflow) called from `ProjectLoadWorkflow` — one owner for health/import/run/package report lifecycle.
- **Suggested remediation:** Co-locate reset with TN-SHELL-MW-02 runtime-center extraction; stop scattering report field writes across MainWindow.
- **Tests that would prove fix:** Unit test: after open project B, runtime center shows empty package issues until a new packaging run; no direct MainWindow field mutation required.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-07-7 — Exclude merge at project load duplicates policy soon to be SSOT in R4

- **Persona:** TN-SHELL-MW-07
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:2748-2752` —

  ```python
  effective_excludes = compute_effective_excludes(
      self._load_effective_exclude_patterns(loaded_project.project_root),
      loaded_project.metadata.exclude_patterns,
  )
  self._search_sidebar.set_exclude_patterns(effective_excludes)
  ```

  Same layered exclude pattern appears at `1837-1838`, `4822-4823`, `5507-5508` (grep). Handoff R4 targets a single project inventory / exclude API.
- **Code-judo alternative:** `project_inventory.effective_excludes(settings, loaded_project) -> list[str]` consumed by search, tree refresh, and open path — delete repeated `load_effective + compute_effective` pairs.
- **Suggested remediation:** When R4 lands, project load workflow calls inventory API once and passes result to search sidebar and tree population.
- **Tests that would prove fix:** Characterization tests in `tests/unit/project/` for merged excludes; search sidebar integration unchanged.
- **Handoff overlap:** R4

---

### TN-SHELL-MW-07-8 — Lazy `getattr` presenter factories defer composition-root wiring

- **Persona:** TN-SHELL-MW-07
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:2788-2812` — `_get_project_tree_presenter`, `_get_editor_tabs_coordinator`, `_get_problems_controller` use `getattr(self, "_…", None)` lazy init instead of `__init__` construction.
- **Code-judo alternative:** Construct presenters/coordinators in `__init__` (or a `MainWindowComposition` factory module) with explicit dependencies; drop lazy getters and hidden `None` first-access paths.
- **Suggested remediation:** Fold into R2/R3 shell decomposition when tree/problems panels split; low urgency vs TN-SHELL-MW-07-1.
- **Tests that would prove fix:** Init-order tests confirm presenters exist before first project open; no behavior change in tree/problems panels.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-07-9 — Optional `getattr` for test runner workflow suggests incomplete wiring seam

- **Persona:** TN-SHELL-MW-07
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:2776-2778` —

  ```python
  test_runner_workflow = getattr(self, "_test_runner_workflow", None)
  if test_runner_workflow is not None:
      test_runner_workflow.refresh_discovery()
  ```

  `_test_runner_workflow` is assigned in `__init__` elsewhere; optional access in production load path hides missing collaborator instead of failing fast or injecting via workflow.
- **Code-judo alternative:** `ProjectLoadWorkflow` takes optional `TestRunnerWorkflow` collaborator explicitly; refresh is a no-op when absent — no `getattr` on MainWindow.
- **Suggested remediation:** Resolve when extracting TN-SHELL-MW-07-1; use constructor injection or protocol.
- **Tests that would prove fix:** Project load with test workflow stub asserts `refresh_discovery` called; without stub, load still succeeds.
- **Handoff overlap:** R2

---

## Slice metrics (baseline commit)

| Metric | Value |
|--------|-------|
| Lines in scope | ~272 (2665–2936) |
| Methods in scope | 25 |
| `main_window.py` total lines | 5,549 |
| `MainWindow` method count | 332 |

## Cross-slice notes

- **Templates / examples:** `_handle_new_project_from_template_action` (1666–1695) and `_handle_load_example_project_action` (2636–2651) sit in MW-05/06 but **only differ before** `_open_project_by_path`; fixing TN-SHELL-MW-07-1 unblocks all creation flows at once.
- **Packaging:** No packaging handlers in this line range; menu wiring delegates to `RuntimeSupportWorkflow.handle_package_project_action`. Issue-report reset on load (TN-SHELL-MW-07-6) is the packaging touchpoint here.
- **Run/debug depth:** `_start_active_file_session` begins at line 2937 (MW-08); coordinate run-session extraction across MW-07 and MW-08 to avoid double moves.

## Approval bar (this slice)

**Blocked for thermo-clean approval** until `_apply_loaded_project` and the project-open callback sandwich move behind a cohesive workflow (TN-SHELL-MW-07-1, TN-SHELL-MW-07-2) and run-project entry duplication is collapsed (TN-SHELL-MW-07-3, TN-SHELL-MW-07-4). Pass-through method removal (TN-SHELL-MW-07-5) should ship in the same R2 tranche to satisfy the handoff method-count rule.
