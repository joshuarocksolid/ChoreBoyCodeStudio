# TN-SHELL-TEST-UI — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-TEST-UI  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/test_explorer_panel.py` (830 LOC), `app/shell/test_runner_workflow.py` (428 LOC). Cross-read: `app/shell/menu_wiring.py`, `app/shell/style_sheet_sections_panels.py`, `app/shell/toolbar_icons.py`, `app/run/pytest_discovery_service.py`, `app/run/pytest_runner_service.py`, `tests/unit/shell/test_test_explorer_panel.py`, `tests/unit/shell/test_test_runner_workflow.py`, `docs/deslop/AUDIT_app_remaining_handoff.md` R3 § TestExplorerPanel.

---

## Executive verdict

**Not thermo-clean.** `TestRunnerWorkflow` is a real extraction — pytest discovery, run, debug, and result fan-out live outside `MainWindow` — but the pair still carries significant incidental complexity. `test_explorer_panel.py` is an **830-line** widget monolith with **~270 lines of hand-painted icon boilerplate** that duplicates the `toolbar_icons.py` pattern instead of sharing a module. Outcome state is mirrored in **two places** (workflow dict + panel dict), three panel APIs (`set_outcomes`, `update_outcomes`, `set_discovering`) diverge in behavior, and **`set_discovering` is never called from production code** so the discovering UX is dead on arrival. Theme integration is split-brain: global QSS already styles summary count labels from tokens, yet `apply_theme` also pushes inline `setStyleSheet` overrides. R3 explicitly names this panel for decomposition; that work has not started. Workflow unit coverage is solid on the main paths; panel tests exist but lean heavily on private widget fields contrary to the R3 handoff rule.

---

### TN-SHELL-TEST-UI-1 — 830-line panel monolith; ~33% is icon paint that should be its own module

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_panel.py:34-304` — five outcome builders, three kind builders, three action builders, three module-level caches, and `clear_icon_caches()` occupy ~270 LOC before `TestExplorerPanel` begins at line 348. File total: 830 LOC (under 1k but R3 hotspot).
- **Code-judo alternative:** Extract `app/shell/test_explorer_icons.py` (outcome/kind/action icon factories + caches + `clear_icon_caches`) mirroring `toolbar_icons.py`. Panel imports icons and owns only layout, tree model binding, filters, and signals — same split R3 prescribes for `OutlinePanel`.
- **Suggested remediation:** R3 step 4: split into `test_explorer_icons.py` + slim `test_explorer_panel.py` (~550 LOC). Optionally fold action icons (`play`/`refresh`/`rerun`) into shared primitives with `toolbar_icons.icon_run` / a small `icon_refresh` helper to delete duplicate QPainter setup.
- **Tests that would prove fix:** Move existing icon cache tests to `tests/unit/shell/test_test_explorer_icons.py`; panel tests keep public behavior (`update_discovery`, `set_outcomes`, `failed_node_ids`, filter visibility) without importing `_OUTCOME_ICON_CACHE`.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-2 — Dual outcome SSOT: workflow dict and panel dict mirror the same map

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_runner_workflow.py:99-100,357-358` — `_test_outcomes_by_node_id` is workflow SSOT; every run/discovery refresh pushes `set_outcomes(self._test_outcomes_by_node_id)` to the panel. `app/shell/test_explorer_panel.py:362,628-635` — panel maintains its own `_outcomes` copy. `_failed_node_ids()` at `test_runner_workflow.py:419-428` prefers panel then falls back to workflow dict, papering over optional panel with branching instead of one owner.
- **Code-judo alternative:** Pick one owner. **View-only panel:** panel holds display snapshot only; workflow owns outcomes; `failed_node_ids()` reads workflow dict only (panel exposes no outcome storage). **Or panel-owned:** workflow stops `_test_outcomes_by_node_id` and queries `test_explorer_panel.failed_node_ids()` / a narrow `outcomes_snapshot()` after runs. Either path deletes the mirror + fallback chain.
- **Suggested remediation:** Extend `TestExplorerView` with the chosen contract; delete `update_outcomes` if incremental merge is unused (see TN-SHELL-TEST-UI-6). Collapse `_failed_node_ids()` to a single read path.
- **Tests that would prove fix:** `test_test_runner_workflow.py` asserts outcomes after run without duplicating state in `FakeExplorer`; rerun-failed still resolves IDs when panel is `None`.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-3 — `set_discovering` is implemented and tested but never wired; discovery has no in-flight UX

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_panel.py:649-656` — `set_discovering(active)` swaps to empty label, disables refresh, sets status dot/text. Repo-wide search: **only** `tests/unit/shell/test_test_explorer_panel.py:243-248` calls it. `app/shell/test_runner_workflow.py:247-278` — `refresh_discovery()` schedules background work but never notifies the panel; refresh button stays enabled during subprocess collect.
- **Code-judo alternative:** `refresh_discovery` calls `test_explorer_panel.set_discovering(True)` before `background_tasks.run`, and `on_success`/`on_error` call `set_discovering(False)` (or fold discovering into `set_running` with a `mode: Literal["run","discover"]` if you want one spinner API — but wiring the existing method is simpler).
- **Suggested remediation:** Add `set_discovering` to `TestExplorerView`; wire in `refresh_discovery` success/error paths. Consider disabling run-all during discover to avoid overlapping pytest subprocesses.
- **Tests that would prove fix:** Workflow test: `refresh_discovery` records `[True, False]` discovering states on fake explorer; manual acceptance: save `.py` file triggers rediscover with visible “Discovering…” empty state.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-4 — Copy-pasted “refresh everything” cascade across three public panel methods

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_panel.py:619-626`, `628-635`, and partially `564-617` — `update_outcomes`, `set_outcomes`, and `update_discovery` each call overlapping chains: `_refresh_outcome_icons` → `_refresh_failed_action_states` → `_refresh_filter_counts` → `_apply_filters` → `_refresh_summary` (discovery adds tree rebuild). Any new visual concern (e.g. filter bar, rerun buttons) requires editing multiple entry points.
- **Code-judo alternative:** Single `_sync_view(*, rebuild_tree: bool = False)` (or `TestExplorerViewState` dataclass + one `apply(state)`), called from all public mutators. Tree rebuild stays the only branch.
- **Suggested remediation:** Extract private `_sync_after_outcome_change()` and `_sync_after_discovery(result)` that share the common tail; delete `update_outcomes` if unused externally (TN-SHELL-TEST-UI-6).
- **Tests that would prove fix:** One parametrized panel test: after `set_outcomes` vs `update_discovery`+preserved outcomes, filter counts and rerun button state match expected — guards against drift when editing one path only.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-5 — Inline `setStyleSheet` on summary labels fights central QSS token styling

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_panel.py:784-790` — `_refresh_summary_colors` sets per-label `setStyleSheet(f"color: {pc};")`. `app/shell/style_sheet_sections_panels.py:498-511` — `countPassed` / `countFailed` / `countSkipped` already receive `{passed_color}`, `{tokens.diag_error_color}`, `{tokens.text_muted}` from `ShellThemeTokens`. `apply_theme` at `test_explorer_panel.py:539-560` clears icon caches **and** calls `_refresh_summary_colors`, overriding global QSS with inline rules on every theme change.
- **Code-judo alternative:** Delete `_refresh_summary_colors` entirely; rely on `style_sheet_sections_panels` token bindings (HC Light/Dark included). Icon colors already rebuild from tokens in `_refresh_outcome_icons` / toolbar icon refresh.
- **Suggested remediation:** Remove inline stylesheets; verify four-theme summary badge contrast via existing QSS selectors only. If dynamic passed-color is required at runtime, expose it through QSS custom property + `polish()` like `_set_status_dot_state`, not `setStyleSheet`.
- **Tests that would prove fix:** Panel theme test asserts count labels have **empty** inline stylesheet after `apply_theme`; manual four-theme check on summary badges (Light, Dark, HC Light, HC Dark).
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-6 — Dead and divergent API surface: `_OUTCOME_ICONS_TEXT`, `update_outcomes`, incomplete `TestExplorerView`

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/test_explorer_panel.py:310-316` — `_OUTCOME_ICONS_TEXT` dict is never read. `619-621` — `update_outcomes` merges into `_outcomes` but has **zero production callers** (only `set_outcomes` used from workflow). `app/shell/test_runner_workflow.py:26-37` — `TestExplorerView` Protocol lists four methods; actual panel exposes `set_discovering`, `update_outcomes`, `apply_theme`, navigation signals — protocol drift hides the real contract from type checkers.
- **Code-judo alternative:** Delete dead symbols; keep `set_outcomes` only; expand Protocol to match wired surface **or** shrink panel public API to what workflow/menu need.
- **Suggested remediation:** Hygiene pass during R3 split: remove `_OUTCOME_ICONS_TEXT`, drop or wire `update_outcomes`, align Protocol with `menu_wiring.connect_test_explorer_navigation` + workflow usage.
- **Tests that would prove fix:** `rg update_outcomes` / `_OUTCOME_ICONS_TEXT` returns no definitions-only hits; pyright on workflow with strict Protocol shows no attribute gaps.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-7 — `TestRunnerWorkflow` constructor remains a 17-dependency injection wall with `Any` ports

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_runner_workflow.py:55-77` — 17 constructor parameters (`workflow_broker: Any`, `logger: Any`, twelve `Callable` hooks, optional panel). `main_window.py:687-707` wires it with lambdas closing over `self` (TN-SHELL-MW-01-4 overlap). Typed islands (`ActiveTestEditor`, `DiscoveryResult`, `PytestRunResult`) sit beside untyped broker/logger/debug policy `object | None`.
- **Code-judo alternative:** Introduce `TestRunnerHost` / `TestRunShellPorts` dataclass bundling console/problems/focus/dialog/auto-open callbacks (same move as TN-SHELL-MW-01-2 for other workflows). Workflow ctor drops to ~6 parameters: host ports, background tasks, panel, run/discover callables, debug session launcher.
- **Suggested remediation:** R3 follow-on after panel split: collapse shell callbacks into one frozen ports object constructed in composition root; tighten `debug_exception_policy_provider` to `DebugExceptionPolicy | None`.
- **Tests that would prove fix:** Existing `WorkflowHarness` builds ports object instead of 12 lambdas; no behavior change in `test_test_runner_workflow.py`.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-TEST-UI-8 — Outcome vocabulary is raw strings repeated across panel, workflow, and run layer

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_panel.py:121-127,366-372,687-690,704-711,743-746` — `"passed"`, `"failed"`, `"skipped"`, `"error"`, `"not_run"` scattered in builders, filters, counters. `app/shell/test_runner_workflow.py:339,354-356,427` — string compare for outcomes. `app/run/pytest_discovery_service.py:58` — `DiscoveredTestResult.outcome: str` comment lists same literals. No shared `Literal`/`Enum`/frozen set; filter logic hardcodes `show.add("not_run")` as special case at line 712.
- **Code-judo alternative:** Single `TestOutcome` alias or small enum in `app/run/pytest_discovery_service.py` (or `app/core/models.py`) imported by panel + workflow; filter visibility becomes `frozenset[TestOutcome]` math instead of string set soup.
- **Suggested remediation:** Add typed outcome constant module; panel `_OUTCOME_BUILDERS` keys become enum members; counts dict typed once, shared by filter bar and summary bar (also removes duplicate counting loops in `_refresh_filter_counts` and `_refresh_summary`).
- **Tests that would prove fix:** Type checker enforces outcome keys; one helper test for `count_outcomes(mapping) -> OutcomeCounts` used by both filter and summary paths.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-9 — Stylesheet gap: `debugFailedBtn` omitted from test-explorer QSS block

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/test_explorer_panel.py:427` — `shell.testExplorer.debugFailedBtn` object name set. `app/shell/style_sheet_sections_panels.py:372-395` — QSS selectors list `runAllBtn`, `runFailedBtn`, `refreshBtn` only; **no** `debugFailedBtn` hover/pressed/disabled rules.
- **Code-judo alternative:** Add `debugFailedBtn` to the same QToolButton selector group as `runFailedBtn` (likely identical styling).
- **Suggested remediation:** One-line QSS selector extension; four-theme visual spot-check on Debug Failed button states.
- **Tests that would prove fix:** Manual acceptance only (stylesheet string snapshot tests are low signal per test anti-pattern catalog); optional grep guard in lint if desired.
- **Handoff overlap:** R3

---

### TN-SHELL-TEST-UI-10 — Panel unit tests overfit private widget graph (`_tree`, `_run_failed_btn`, …)

- **Persona:** TN-SHELL-TEST-UI
- **Severity:** NICE-TO-HAVE
- **Evidence:** `tests/unit/shell/test_test_explorer_panel.py:166-167,171,177,184,198-207,225,241,267,292-305` — assertions on `panel._tree`, `panel._stack_layout`, `panel._run_failed_btn`, `panel._status_dot.property(...)`. R3 handoff: “Do not overfit tests to private child widget names.”
- **Code-judo alternative:** Test through public seams: signal emissions (`run_failed_requested` when clicking enabled button via `QTest`), visible widget discovery by `objectName` (stable contract per handoff), or small test-only accessors if truly needed.
- **Suggested remediation:** During R3 panel split, rewrite tests to public behavior; keep objectName checks where stylesheets depend on them.
- **Tests that would prove fix:** Refactored suite passes without referencing `_`-prefixed panel fields except `objectName`-based lookups.
- **Handoff overlap:** R3

---

## Positive signals (not findings)

- **`TestRunnerWorkflow` ownership** — pytest run/discover/debug orchestration is out of `MainWindow`; `menu_wiring.connect_test_explorer_navigation` wires panel signals directly to workflow methods (`menu_wiring.py:146-152`).
- **Background task keying** — discovery uses `key="test_discovery"`; `GeneralTaskScheduler` cancels superseded runs (`background_tasks.py:44-47`), reducing stale UI updates on rapid save-triggered refresh (`save_workflow.py:191-193`).
- **Workflow unit tests** — `test_test_runner_workflow.py` covers project/file/cursor run, rerun failed args, debug failed, discovery push, outcome/problem fan-out with a lightweight harness (no `MainWindow`).
- **Theme-aware icon rebuild** — `apply_theme` clears caches and remaps outcome colors to `ShellThemeTokens` (`test_explorer_panel.py:539-560`); status dot uses QSS `testState` property pattern compatible with HC modes.
- **Stable object names** — `shell.testExplorer.*` IDs align with `style_sheet_sections_panels.py` for tree, filters, status bar (minus TN-SHELL-TEST-UI-9 gap).

---

## Slice metrics (baseline commit)

| Metric | Value |
|--------|-------|
| `test_explorer_panel.py` LOC | 830 |
| Icon/helper LOC (approx.) | ~270 (lines 34–304) |
| `test_runner_workflow.py` LOC | 428 |
| `TestRunnerWorkflow.__init__` parameters | 17 |
| Production callers of `set_discovering` | 0 |
| Production callers of `update_outcomes` | 0 |

## Cross-slice notes

- **Init ordering:** Panel ref must exist before `TestRunnerWorkflow` construction — TN-SHELL-MW-01-4; fixing composition root helps this pair.
- **Optional `getattr` refresh on project load:** TN-SHELL-MW-07-9 (`main_window.py:2776-2778`) — same workflow, cleaner injection would drop defensive `getattr`.
- **Debug target dicts:** `record_debug_target` + rerun debug paths tie to TN-SHELL-MW-08; keep test-node targets typed when debug workflow moves.

## Approval bar (this slice)

**Blocked for thermo-clean approval** until: (1) panel icon/layout decomposition per R3 (TN-SHELL-TEST-UI-1), (2) single outcome SSOT (TN-SHELL-TEST-UI-2), (3) discovery in-flight UX wired or dead API removed (TN-SHELL-TEST-UI-3), (4) inline summary styles removed in favor of central QSS (TN-SHELL-TEST-UI-5). Workflow DI consolidation (TN-SHELL-TEST-UI-7) and typed outcomes (TN-SHELL-TEST-UI-8) should ship in the same R3 tranche to prevent the next feature from landing in the 830-line file unchanged.
