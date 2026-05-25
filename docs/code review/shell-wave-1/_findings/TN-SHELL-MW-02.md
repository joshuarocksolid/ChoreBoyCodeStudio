# TN-SHELL-MW-02 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-02  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 773–1117 — startup restore, runtime onboarding, welcome widget, layout persist/restore. Referenced helpers: `runtime_support_workflow.py`, `layout_persistence.py`, `welcome_widget.py`, `runtime_center_dialog.py`, `main_window_panels.py`, `status_bar.py` (`map_startup_report_to_status`).

---

## Executive verdict

This slice is **not thermo-clean**. It concentrates ~345 lines and **22 instance methods** in the composition root, mixing four distinct ownership domains (session restore, runtime diagnostics/onboarding, welcome UX, shell layout). `RuntimeSupportWorkflow` exists but is only a partial extraction: MainWindow still owns report assembly, runtime-center presentation, startup probe refresh, and help-topic routing while injecting those back into the workflow via lambdas — a circular split that violates AD-015 and the R2 brief’s `RuntimeOnboardingWorkflow` target. The welcome/onboarding block duplicates signal wiring and embeds dialog construction inline. Layout persistence has a clean typed model (`layout_persistence.py`) but MainWindow still duplicates apply/reset orchestration and couples outline panel state into the same path. Fix agents should prioritize collapsing runtime-center + onboarding into one workflow module and extracting welcome wiring before touching cosmetic cleanup.

---

### TN-SHELL-MW-02-1 — Runtime center logic is split across MainWindow and RuntimeSupportWorkflow via circular callbacks

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:578-596` — `RuntimeSupportWorkflow(..., build_runtime_issue_report=self._build_runtime_issue_report, open_runtime_center_dialog=lambda **kwargs: self._open_runtime_center_dialog(**kwargs))`; `836-883` — `_build_runtime_issue_report`, `_open_runtime_center_dialog`, `_handle_runtime_center_action`, `_open_runtime_help_topic` remain on `MainWindow`.
- **Code-judo alternative:** Move `_build_runtime_issue_report`, `_open_runtime_center_dialog`, `_open_runtime_help_topic`, `_handle_runtime_center_action`, `set_startup_report` side-effects (except status-bar seam), `_refresh_startup_capability_report_async`, and `_handle_startup_report_refresh` into `RuntimeSupportWorkflow` (or the R2 `RuntimeOnboardingWorkflow` slice of it). MainWindow passes narrow getters/setters for issue-report fields and `resolve_theme_tokens`; workflow exposes `refresh_startup_report`, `open_runtime_center`, `handle_startup_report`.
- **Suggested remediation:** Extend `RuntimeSupportWorkflow` to own the full runtime-center vertical slice; delete the callback ping-pong. Keep `MainWindow.set_startup_report` as a thin extension seam that forwards to workflow + `_status_controller` only.
- **Tests that would prove fix:** Unit tests on workflow for report merge + dialog open; integration test that health-check success opens runtime center without reaching into `MainWindow._build_runtime_issue_report`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-2 — Duplicate runtime issue report assembly in two places

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:836-852` — `_build_runtime_issue_report` merges startup, health, import, run, and package reports; `app/shell/runtime_support_workflow.py:108-123` — `handle_generate_support_bundle_action` rebuilds the same report list inline before `merge_runtime_issue_reports`.
- **Code-judo alternative:** One function — e.g. `build_merged_runtime_issue_report(startup, health, import, run, package) -> RuntimeIssueReport` in `app/support/runtime_explainer.py` or on the workflow — called from both runtime-center open and support-bundle generation. Delete the duplicated conditional append blocks.
- **Suggested remediation:** Extract shared merge builder; workflow and MainWindow (until cutover) call the same helper. No third copy when packaging updates issue reports elsewhere.
- **Tests that would prove fix:** Parametrized unit test: given fixture reports with/without issues, merged output matches current behavior for center dialog and bundle paths.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-3 — Welcome + runtime onboarding orchestration should not live in MainWindow

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:931-1035` — `_refresh_welcome_widget_state`, `_connect_welcome_widget_actions` (13 signal lambdas), `_invoke_welcome_action`, onboarding dismiss/complete handlers, `_handle_runtime_onboarding_action` (inline `QDialog` + `WelcomeWidget` assembly).
- **Code-judo alternative:** Introduce `WelcomeWorkflow` or fold into R2 **`RuntimeOnboardingWorkflow`**: owns widget refresh, signal connection table, onboarding dialog lifecycle, and persistence hooks. MainWindow holds `_welcome_workflow` and calls `workflow.attach_widget(widget)` from `main_window_panels.build_center_panel`; menu wiring connects to `workflow.open_onboarding_dialog()`.
- **Suggested remediation:** Extract cohesive workflow with explicit action callbacks (`open_project`, `open_runtime_center`, `run_health_check` → delegate health to `RuntimeSupportWorkflow`). Replace per-signal lambdas with a single `connect_welcome_widget(widget, *, close_after: Callable | None)` on the workflow.
- **Tests that would prove fix:** Unit-test workflow signal wiring with a stub `WelcomeWidget`; keep `test_welcome_runtime_onboarding.py` green via public workflow API instead of `_handle_runtime_onboarding_action`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-4 — Onboarding dismissed/completed state is persisted but never read

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:368-371` — loads `_runtime_onboarding_dismissed` / `_runtime_onboarding_completed`; `946` — `_refresh_welcome_widget_state` only calls `widget.set_onboarding_visible(force_show_onboarding)` (default `False`); repo-wide grep shows no other reads of these fields.
- **Code-judo alternative:** Either wire state into visibility policy (`show_onboarding = not dismissed and not completed` on main welcome) or delete the unused instance fields and merge helpers if product intent is Help-menu-only onboarding (per `test_welcome_runtime_onboarding.py`). Half-implemented state model adds concepts without deleting branches.
- **Suggested remediation:** Product decision + code-judo: complete the state machine in the extracted onboarding workflow, or remove dead load/persist paths and keep only dialog-scoped onboarding.
- **Tests that would prove fix:** Tests for first-run vs dismissed vs completed visibility; or test asserting persist keys removed if state is intentionally unused.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-5 — Inline onboarding dialog construction bypasses existing dialog patterns

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1024-1035` — `_handle_runtime_onboarding_action` builds `QDialog`, sets object name/size, nests `WelcomeWidget`, wires actions, calls `exec_()` with no theme/stylesheet hook visible in this slice (contrast `RuntimeCenterDialog` in `runtime_center_dialog.py`).
- **Code-judo alternative:** `RuntimeOnboardingDialog` (or workflow-owned factory) mirroring `RuntimeCenterDialog` — accepts tokens, welcome widget factory, and `exec` boundary. MainWindow/menu wiring triggers one workflow method.
- **Suggested remediation:** Extract dialog module; ensure four-theme styling goes through `ShellThemeTokens` / existing stylesheet composer (R3 stylesheet split may apply).
- **Tests that would prove fix:** Unit test dialog object names and minimum size; theme integration test extending `test_runtime_explanation_theme_integration.py` pattern.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-02-6 — Layout apply/reset duplicates orchestration; outline state tangled into layout path

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1057-1116` — `_restore_layout_from_settings` and `_handle_reset_layout_action` repeat resize + three splitter `setSizes` + outline field assignment + `_apply_outline_layout_state`; outline collapse/follow/sort persisted alongside window geometry in the same methods.
- **Code-judo alternative:** `ShellLayoutWorkflow` or functions in `layout_persistence.py`: `read_layout(settings) -> ShellLayoutState`, `apply_layout(window_refs, state)`, `capture_layout(window_refs) -> ShellLayoutState`, `reset_layout() -> ShellLayoutState`. Reset becomes `apply_layout(defaults); persist`. Outline panel apply stays in one place (coordinate with MW-03 `_apply_outline_layout_state`).
- **Suggested remediation:** Extract apply/capture pair; MainWindow keeps only `_persist_layout_to_settings` / `_restore_layout_from_settings` one-liners delegating to workflow. Reduces drift when a fourth splitter or panel is added.
- **Tests that would prove fix:** Extend `tests/unit/shell/test_layout_persistence.py` with apply/capture tests using stub splitters; optional integration test for reset menu action.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-02-7 — `_try_restore_last_project` is session-restore workflow leaking into the composition root

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:773-800` — settings load, path validation, `assess_project_root`, `_open_project_by_path`; wired from `__init__` via single-shot timer (`755-758`).
- **Code-judo alternative:** `StartupSessionWorkflow` or method on `ProjectController`: `restore_last_project_if_needed() -> bool` with the same guards (`_is_shutting_down`, `_loaded_project`). MainWindow timer connects to one workflow entry point.
- **Suggested remediation:** Move logic next to `project_controller.py` / recent-projects; keep timer wiring in MainWindow only.
- **Tests that would prove fix:** Relocate existing `tests/unit/shell/test_main_window_session_restore.py` to target the new owner without `MainWindow.__new__` shims.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-8 — Inconsistent settings-load error handling on startup paths

- **Persona:** TN-SHELL-MW-02
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:782-786` — `_try_restore_last_project` catches settings failures; `885-890` — `_load_runtime_onboarding_state` catches failures; `1057-1058` — `_restore_layout_from_settings` calls `load_global()` with **no** try/except during `__init__` (line 736 caller).
- **Code-judo alternative:** Uniform policy: either all startup settings reads go through a resilient `SettingsService.load_global_or_default()` or each startup slice handles failure the same way. Layout restore should not be the brittle path.
- **Suggested remediation:** Align `_restore_layout_from_settings` with onboarding/restore guards; or centralize in settings service used by layout workflow.
- **Tests that would prove fix:** Unit test: corrupt/missing global settings still yields default layout without raising during window construction.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-9 — `_open_runtime_help_topic` silently maps unknown topics to Getting Started

- **Persona:** TN-SHELL-MW-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:854-864` — after explicit branches, `self._handle_getting_started_action()` runs for all other `topic_id` values including typos.
- **Code-judo alternative:** Explicit dispatch dict or exhaustive match on known `HELP_TOPIC_*` constants; log warning + no-op (or runtime-center fallback) for unknown ids.
- **Suggested remediation:** Move topic routing into help workflow or runtime support workflow when extracting TN-SHELL-MW-02-1.
- **Tests that would prove fix:** Unit test unknown `topic_id` does not invoke getting-started handler.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-02-10 — `set_project_placeholder` mixes status formatting with settings I/O

- **Persona:** TN-SHELL-MW-02
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:1037-1055` — updates placeholder label and loads project settings to append `(project overrides)` before `_status_controller.set_project_state_text`.
- **Code-judo alternative:** `StatusController.set_project_placeholder(name, loaded_project, settings_service)` or project controller emits a structured `ProjectStatusView` so MainWindow does not load settings for display strings.
- **Suggested remediation:** Defer to status/project controller extraction (adjacent slices); do not expand this method during R2 runtime work.
- **Tests that would prove fix:** Unit test on status controller for override suffix behavior.
- **Handoff overlap:** none

---

## Slice metrics (context)

| Metric | Value |
|--------|------:|
| Lines in scope | 773–1117 (~345) |
| Methods wholly in scope | 22 |
| `main_window.py` total LOC | 5,549 |
| `MainWindow` method count (file) | 332 |

AD-015 expectation: composition root wires; workflows own cohesive user actions. This slice is a primary R2 extraction target per `AUDIT_app_remaining_handoff.md` § R2 items 3–4 and global rule “method count must go down.”

---

## Approval bar (this slice)

**Do not approve** structural status quo. Minimum bar for thermo-clean: runtime-center + onboarding + welcome wiring extracted to workflow module(s), single owner for merged runtime issue reports, layout apply/reset deduplicated, onboarding state either wired or removed, session restore moved out of MainWindow. NICE-TO-HAVE items can follow in the same R2 PR series if bundled with structural wins.
