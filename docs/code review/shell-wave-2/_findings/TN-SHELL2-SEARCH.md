# TN-SHELL2-SEARCH — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-SEARCH  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/search_sidebar_widget.py` (687 LOC), `app/shell/find_replace_workflow.py` (153 LOC), `app/shell/diagnostics_search_coordinator.py` (113 LOC). Cross-read: `app/shell/main_window_panels.py` (sidebar + find-bar signal wiring), `app/shell/menu_wiring.py` (find/replace menu bindings), `app/shell/main_window_lifecycle.py` (shutdown cancel), `app/shell/project_tree_ui_workflow.py` (search open-at-line), `app/shell/shell_composition.py` (workflow host + theme apply), `app/editors/search_panel.py` (`SearchWorker`, `replace_in_files`), `tests/unit/shell/test_search_sidebar_widget.py`, `tests/unit/shell/test_diagnostics_search_coordinator.py`. Gates: CC-17 ghost search hard cutover, CC-20 cohesive find/replace workflow, 700 LOC decomposition, four-theme `ShellThemeTokens`, R4 inventory SSOT, hard-cutover bias.

**Delta note:** These three modules are **unchanged** between baseline `fccb611` and post-remediation HEAD. This critic audits the **post–Shell Wave 1 search-pipeline state** only.

---

## Executive verdict

**APPROVE for the search-pipeline delta slice.** Shell Wave 1 remediation landed: the ghost MainWindow search path is **gone**, `SearchSidebarWidget` owns the live `SearchWorker`, shutdown calls `cancel_active_search()`, and find/replace menus + bar signals route through `FindReplaceWorkflow` with a typed `FindReplaceBarHost`. **CC-17 is CLOSED**; **CC-20** (find/replace menu workflow) is **SUBSTANTIALLY CLOSED** for this slice. The slice is **not thermo-clean** overall: `search_sidebar_widget.py` remains a **687 LOC** UI/orchestration/delegate monolith, inline vs project search still fork `FindOptions`/`SearchOptions`, and `diagnostics_search_coordinator.py` is a misnamed diagnostics-only module with 14-callable constructor injection. **No REGRESSION** relative to Shell Wave 1 CC-17/CC-20 intent. Block further search-surface growth until sidebar decomposition and options SSOT are addressed (P1).

---

## Prior-wave re-validation (CC-17, CC-20)

| CC ID | Shell Wave 1 headline | Status @ `fccb611` | Evidence |
|-------|----------------------|-------------------|----------|
| **CC-17** | Ghost MainWindow search pipeline + shutdown gap | **CLOSED** | `rg "_active_search_worker\|SearchResultsCoordinator\|_set_search_results\|_schedule_search_results" app/` → **empty**. `main_window.py` retains only `_search_sidebar` field (`:97`); no search orchestration methods. `SearchResultsCoordinator` **deleted** — `diagnostics_search_coordinator.py` is 113 LOC, `DiagnosticsOrchestrator` only. Live path: `SearchSidebarWidget._run_search` → `SearchWorker` (`search_sidebar_widget.py:541-571`). Shutdown: `main_window_lifecycle.py:75-76` → `cancel_active_search()`. Open-at-line: `main_window_panels.py:101-102` → `project_tree_ui_workflow.handle_search_*` (`project_tree_ui_workflow.py:159-163`), not MW one-liners. Stale-result guard: `_apply_search_results` generation + query check (`search_sidebar_widget.py:583-588`); tested at `test_search_sidebar_widget.py:133-143`. |
| **CC-20** | Cohesive menu workflows not extracted (find/replace ×7) | **SUBSTANTIALLY CLOSED** (find/replace slice) | `find_replace_workflow.py:35-125` — `FindReplaceWorkflow` owns bar handlers + `open_find` / `open_replace` / `open_find_in_files`. `menu_wiring.py:101-104` binds menus direct to workflow (no MW `_handle_find_*`). `main_window_panels.py:223-230` wires `FindReplaceBar` signals to workflow. `shell_composition.py:284-286` constructs `FindReplaceWorkflow(MainWindowFindReplaceHost(window))`. Residual: `MainWindowFindReplaceHost` uses `window: Any` (`find_replace_workflow.py:128-153`). |

---

### TN-SHELL2-SEARCH-1 — CC-17 closed: single search owner, ghost pipeline hard-deleted

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL (closure of Wave 1 CC-17)
- **Severity:** NICE-TO-HAVE (positive keeper — do not regress)
- **Evidence:** `rg SearchResultsCoordinator app/` → empty. `main_window_lifecycle.py:75-76` — `window._search_sidebar.cancel_active_search()` on teardown. `search_sidebar_widget.py:476-481` — debounce stop + worker cancel. No Problems-panel-as-search-results path remains.
- **Code-judo alternative:** Keep sidebar + `search_panel.SearchWorker` as sole async owner; any new search UX lands in `SearchSidebarWidget` or a extracted `SearchPanelWorkflow`, never MainWindow fields.
- **Suggested remediation:** Gate future PRs: `rg "_active_search_worker\|SearchResultsCoordinator" app/` must stay empty; lifecycle must keep `cancel_active_search` call.
- **Tests that would prove fix:** `test_search_sidebar_widget.py` generation-drop test; integration shutdown during in-flight search (manual acceptance).
- **Handoff overlap:** CC-17, R2

---

### TN-SHELL2-SEARCH-2 — CC-20 substantially closed: `FindReplaceWorkflow` is the find/replace SSOT

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL (closure of Wave 1 CC-20)
- **Severity:** NICE-TO-HAVE (positive keeper)
- **Evidence:** `find_replace_workflow.py:13-32` — `FindReplaceBarHost` Protocol with explicit ports. `menu_wiring.py:101-104` — `on_find` / `on_replace` / `on_find_in_files` → workflow. `main_window_panels.py:223-230` — bar signals bypass MainWindow. `open_find_in_files` (`find_replace_workflow.py:61-71`) routes activity view + sidebar focus with project guard.
- **Code-judo alternative:** Migrate `MainWindowFindReplaceHost` to a typed `MainWindowFindReplaceHost` protocol (mirror `ShellHelpController`); delete `window: Any`.
- **Suggested remediation:** Document in ARCHITECTURE §shell that find/replace menu + bar paths must not reappear on MainWindow.
- **Tests that would prove fix:** Existing menu wiring smoke; no `rg "_handle_find" app/shell/main_window.py` matches.
- **Handoff overlap:** CC-20, R2, TN-SHELL2-MW

---

### TN-SHELL2-SEARCH-3 — `search_sidebar_widget.py` is a 687 LOC monolith (delegate + UI + async orchestration)

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `wc -l search_sidebar_widget.py` → **687** (manifest ≥700 hotspot band). `SearchResultDelegate` occupies `:45-254` (~210 LOC custom painting). `SearchSidebarWidget._build_ui` occupies `:282-455` (~174 LOC). Search/replace orchestration `:541-687`. Single file owns Qt delegate, panel chrome, debounce, worker lifecycle, replace-all confirmation, and result tree population.
- **Code-judo alternative:** Extract `search_result_delegate.py` (delegate only) and `search_sidebar_controller.py` (worker debounce, generation guards, replace-all) — widget becomes thin view binding signals. Target: widget <350 LOC, no new concepts.
- **Suggested remediation:** P1 decomposition PR before any feature adds to this file; do not cross 700 LOC without split plan.
- **Tests that would prove fix:** Existing `test_search_sidebar_widget.py` green after extract-only refactor; LOC gate in manifest sweep.
- **Handoff overlap:** CC-21, R3, CC-SHELL2-DECOMPOSE

---

### TN-SHELL2-SEARCH-4 — `FindReplaceWorkflow` duplicates `open_find` / `open_replace` bodies

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `find_replace_workflow.py:41-59` — `open_find` and `open_replace` are identical except final `find_bar.open_find(initial)` vs `open_bar.open_find_replace(initial)`. Each repeats editor/bar null guards and `selected_text() or word_under_cursor()` seeding.
- **Code-judo alternative:** Private `_open_bar(mode: Literal["find", "replace"])` or pass `open_mode: Callable[[str], None]` to one method; two public one-liners remain for menu clarity.
- **Suggested remediation:** Collapse in next touch of this file; no behavior change.
- **Tests that would prove fix:** Existing find/replace menu acceptance unchanged.
- **Handoff overlap:** CC-20, none

---

### TN-SHELL2-SEARCH-5 — `MainWindowFindReplaceHost` erases the typed workflow boundary with `window: Any`

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `find_replace_workflow.py:128-153` — host adapter stores `window: Any` and reaches `window._editor_tab_workflow`, `window._find_replace_bar`, `window._loaded_project`, `window._activity_bar`, `window._project_tree_ui_workflow`, `window._search_sidebar` without protocol enforcement. `FindReplaceBarHost` Protocol exists on the workflow side but the production adapter is untyped.
- **Code-judo alternative:** Define `MainWindowFindReplaceHostPorts` Protocol with the six accessors; composition passes a narrow host object (same pattern as `ShellHelpController` constructor injection). Deletes implicit private-field contract.
- **Suggested remediation:** TN-SHELL2-COMP typed-host migration wave; pair with `main_window_panels.py` `window: Any` builders.
- **Tests that would prove fix:** Pyright clean on `find_replace_workflow.py` without `Any` on host adapter.
- **Handoff overlap:** CC-20, CC-22, TN-SHELL2-COMP

---

### TN-SHELL2-SEARCH-6 — `diagnostics_search_coordinator.py` is misnamed and out-of-slice for search

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Module filename and TN-SHELL2-SEARCH scope imply search coordination; file contains **only** `DiagnosticsOrchestrator` (lint schedule, runtime probe — `diagnostics_search_coordinator.py:12-113`). `SearchResultsCoordinator` removed (CC-17 closure). `main_window_composition.py:439-463` wires 14 lambdas/`setattr` into constructor — injection soup unrelated to search sidebar.
- **Code-judo alternative:** Rename module to `diagnostics_orchestrator.py` (hard cutover import update); keep out of search slice docs. Optional: `DiagnosticsHost` protocol replaces 14 callables.
- **Suggested remediation:** Rename in dedicated PR; update manifest scope line to avoid future critic confusion.
- **Tests that would prove fix:** `rg diagnostics_search_coordinator app/` empty after rename; existing `test_diagnostics_search_coordinator.py` green.
- **Handoff overlap:** CC-17, CC-EDIT-22, R2

---

### TN-SHELL2-SEARCH-7 — Inline `FindOptions` vs project `SearchOptions` fork across shell/editor layers

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `find_replace_workflow.py:73-118` — bar handlers use `FindOptions` from `app.editors.find_replace_bar`. `search_sidebar_widget.py:498-507` — sidebar builds `SearchOptions` from `app.editors.search_panel`. Case/whole-word/regex toggles exist twice (bar toolbuttons vs sidebar `_case_btn` / `_word_btn` / `_regex_btn`). Pattern compilation lives in `code_editor_search` vs `search_panel` (Editors Wave 1 TN-EDIT-SEARCH-4).
- **Code-judo alternative:** Single `SearchOptions` (or shared frozen dataclass) consumed by inline highlighter and `SearchWorker`; `FindReplaceBar` adapts at the boundary. Deletes parallel toggle semantics.
- **Suggested remediation:** Editors + shell joint PR; sidebar must not grow a third options type.
- **Tests that would prove fix:** Parametrized parity: same query + flags → same match count inline and in-files.
- **Handoff overlap:** TN-EDIT-SEARCH, CC-SHELL2-SEARCH-SSOT

---

### TN-SHELL2-SEARCH-8 — Second include/exclude glob plane on sidebar bypasses inventory matcher SSOT

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Project excludes SSOT: `project_load_surface.py:48` / `project_rescan_workflow.py:114` push `effective.as_list()` via `set_exclude_patterns`. Sidebar **also** exposes session `_include_input` / `_exclude_input` (`search_sidebar_widget.py:399-410`) merged in `_search_options` (`:498-507`) into `include_globs` / `exclude_globs` — post-walk filter in `search_panel._should_include_file`, not `should_exclude_relative_path`. `test_search_sidebar_widget.py:96-100` documents comma-split without `.strip()` → `["*.py", " *.txt"]` leading-space glob bug.
- **Code-judo alternative:** Fold UI filters into `EffectiveExcludes` before `iter_text_file_paths`; delete post-walk `_should_include_file` pass. Strip glob tokens on split.
- **Suggested remediation:** Hard cutover with R4 parity tests; at minimum `.strip()` each glob segment in `_search_options`.
- **Tests that would prove fix:** `*.py, *.txt` → `["*.py", "*.txt"]`; nested `build/out.py` exclude parity with project excludes.
- **Handoff overlap:** R4, TN-EDIT-SEARCH, CC-PROJ-01

---

### TN-SHELL2-SEARCH-9 — `SearchResultDelegate` ships empty color defaults until `apply_theme_tokens` runs

- **Persona:** TN-SHELL2-SEARCH
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `search_sidebar_widget.py:48-61` — delegate defaults `match_bg=""`, `text_primary=""`, `text_muted=""`, `badge_bg=""`. `QColor("")` invalid until `apply_theme_tokens` (`:457-471`) called from `shell_composition.py:508-515` on theme apply. First paint before theme fan-out may render invisible/muted match highlights (HC modes sensitive).
- **Code-judo alternative:** Require tokens at delegate construct time (no empty defaults); or read `ShellThemeTokens` in `paint()` via injected token getter.
- **Suggested remediation:** Pass tokens when `_delegate` is created in `_build_ui`; verify HC Light/HC Dark search result badges in manual acceptance.
- **Tests that would prove fix:** Widget constructed with explicit token fixture colors; delegate paint does not use empty `QColor`.
- **Handoff overlap:** CC-23, four-theme gate

---

### TN-SHELL2-SEARCH-10 — Alt+C / Alt+W / Alt+R tooltips advertise shortcuts with no handlers

- **Persona:** TN-SHELL2-SEARCH
- **Status:** NEW
- **Severity:** NICE-TO-HAVE
- **Evidence:** `search_sidebar_widget.py:344,353,362` — tooltips claim `Alt+C`, `Alt+W`, `Alt+R`. `rg "keyPress\|Alt\+" search_sidebar_widget.py` — **only tooltip strings**; no `keyPressEvent` or `QShortcut` registration on widget or toggle buttons.
- **Code-judo alternative:** Either implement shortcuts via existing shell shortcut registry or remove misleading tooltip suffixes.
- **Suggested remediation:** Align with `configure_*_shortcuts` patterns used elsewhere in shell; four-theme neutral.
- **Tests that would prove fix:** Unit test: simulated Alt+C toggles `_case_btn` when widget focused (if implemented).
- **Handoff overlap:** none

---

## Architecture gate checklist (this slice)

| Gate | Result |
|------|--------|
| CC-17 ghost search hard cutover | **PASS** — dead path deleted; sidebar owns worker; shutdown cancel wired |
| CC-20 find/replace workflow extraction | **PASS** (slice) — menus + bar → `FindReplaceWorkflow` |
| 1k / 700 LOC rule | **WARN** — `search_sidebar_widget.py` 687 LOC without decomposition plan |
| Typed host ports | **FAIL** (residual) — `MainWindowFindReplaceHost(window: Any)` |
| Four-theme | **PARTIAL** — QSS + `apply_theme_tokens`; delegate empty-default bootstrap gap |
| Hard-cutover bias | **PASS** — `SearchResultsCoordinator` gone; no parallel MainWindow search path |
| Canonical helpers | **PARTIAL** — walk SSOT via `SearchWorker`; session globs bypass inventory matchers |
| Cross-wave (Editors TN-EDIT-SEARCH) | **IMPROVED** — span-scoped `replace_in_files`; generation guard landed; options fork remains |

---

## Summary table

| Theme | Status |
|-------|--------|
| CC-17 ghost search / shutdown | **CLOSED** |
| CC-20 find/replace menu workflow | **SUBSTANTIALLY CLOSED** |
| Sidebar monolith decomposition | **OPEN** (P1) |
| Options / glob SSOT | **OPEN** (P1) |
| Diagnostics module naming | **OPEN** (P2) |
| REGRESSION vs Shell Wave 1 | **none** |

**Verdict: APPROVE** (search-pipeline delta slice @ `fccb611`). Shell Wave 1 CC-17 and CC-20 find/replace remediation objectives are met. **Not thermo-clean** — treat sidebar decomposition and search-options SSOT as P1 before expanding search surface area.
