# TN-SHELL-MW-11 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-11  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 4224–4477 — project tree display, selection, refresh (slice manifest). Cross-read: `project_tree_controller.py`, `project_tree_presenter.py`, `project_tree_action_coordinator.py`, `project_tree_widget.py`, `main_window_panels.py` (explorer wiring), `tests/unit/shell/test_project_tree_refresh_state.py`.

**Scope note:** Only lines **4440–4477** are project-tree display/selection code. Lines 4224–4438 are search-results tail, symbol indexing, problems handlers, window close/shutdown, and sidebar routing — unrelated concerns packed into the same slice because `MainWindow` has no coherent module boundaries at this offset.

---

## Executive verdict

**Not thermo-clean.** Tree **presentation** was extracted to `ProjectTreePresenter`, and **editor/path side effects** to `ProjectTreeController` + `ProjectTreeActionCoordinator`, but this slice still shows **split ownership**: expand/collapse icon policy and toolbar target resolution live on `MainWindow`, while populate/restore/reveal/selection parsing live in a presenter that reaches through `window: Any`. The dominant structural risks are (1) **`populate(..., preserve_state=True)` restores selection then unconditionally `reveal_path`s the active editor**, which can overwrite restored tree selection on every refresh; (2) **folder open/closed icon logic triplicated** across MainWindow handlers, presenter `restore_state`, and presenter `populate`; (3) **`_selected_tree_directory` re-implements item parsing** and uses `currentItem()` while the widget is in `ExtendedSelection` mode. Refresh is wired to `_reload_current_project()` (outside this slice), a project-wide reload cascade — not a tree-local refresh. Four-theme impact: tree item icons are rebuilt from `ShellThemeTokens` via `_apply_explorer_theme` → full `_populate_project_tree(preserve_state=True)` (`main_window.py:1267-1281`, cross-ref `TN-SHELL-MW-03-3`); HC Light/HC Dark must be re-validated after any change to display/selection/refresh paths.

---

### TN-SHELL-MW-11-1 — `preserve_state` refresh immediately overwritten by `reveal_path(active_file)`

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/project_tree_presenter.py:32-62` — after `restore_state(expanded_paths, selected_paths)` on preserve refresh, `populate` always calls `reveal_path(active_path)` when an editor tab is active. `reveal_path` (`project_tree_presenter.py:146-148`) clears selection, selects the active file, and scrolls to center. Callers: `_reload_current_project` → `_populate_project_tree(..., preserve_state=True)` (`main_window.py:4818`), theme apply (`main_window.py:1281`), external poll (`main_window.py:5504`).
- **Code-judo alternative:** Split **structural refresh** (rebuild items, restore expansion/selection/scroll) from **sync-to-editor** (reveal active file only when selection is empty or user explicitly navigates). On preserve refresh, skip `reveal_path` or gate it behind “no restored selection” / “active file not in restored selection”.
- **Suggested remediation:** Add a `reveal_active_file: bool = True` flag to `populate`, default `False` when `preserve_state=True`; or move reveal into editor-tab activation only. Keep one atomic tree-state transaction in `ProjectTreePresenter`.
- **Tests that would prove fix:** Extend `test_project_tree_refresh_state.py`: set non-active file selected, refresh with preserve_state + active editor open → selection stays on chosen item; separate test that tab switch still reveals in tree when intended.
- **Handoff overlap:** R3 (explorer panel / presenter ownership)

---

### TN-SHELL-MW-11-2 — Folder open/closed icon policy triplicated across three call sites

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:**
  - MainWindow Qt signal handlers: `main_window.py:4474-4480` — `_handle_tree_item_expanded` / `_handle_tree_item_collapsed` set icons from `self._tree_folder_open_icon` / `self._tree_folder_icon`.
  - Presenter restore: `project_tree_presenter.py:105-110` — same open/closed branch during `restore_state`.
  - Presenter initial build: `project_tree_presenter.py:52-54`, `179-180`, `143-144` — default expand + icon on populate and ancestor expand in `reveal_path`.
  Wiring: `main_window_panels.py:154-155` connects `itemExpanded` / `itemCollapsed` to MainWindow.
- **Code-judo alternative:** Single `set_folder_icon(item, *, expanded: bool)` on `ProjectTreePresenter` (or `ProjectTreeWidget.sync_folder_icon(item)`) called from populate, restore, reveal, and optionally from widget signals — **delete** MainWindow expand/collapse handlers entirely.
- **Suggested remediation:** Move signal connections to presenter or widget; remove `_handle_tree_item_expanded/collapsed` from `MainWindow` (net method count down per R2 handoff).
- **Tests that would prove fix:** Unit test on presenter: expand/collapse/restore/reveal each produce correct icon without MainWindow handlers; four-theme pass after icon helper uses token-refreshed icons from host.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-11-3 — `ProjectTreePresenter` is an untyped MainWindow back-reference shell, not a presentation boundary

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** `project_tree_presenter.py:21-30` — `window: Any`. Direct private access throughout: `_project_tree_widget`, `_tree_*_icon`, `_loaded_project`, `_editor_manager`, `_run_service`, `_tree_clipboard_*`, and `_handle_tree_*` callbacks from context menus (`247-378`). `ProjectTreeController` (`project_tree_controller.py:21-138`) is a clean, injected, typed coordinator — the presenter is the opposite pattern.
- **Code-judo alternative:** `ExplorerPanel` (or `ProjectTreePresenter` with explicit `ExplorerHost` protocol) receives widget + icon factories + `LoadedProject` snapshot + action callbacks at construction — no `Any`, no `_window._handle_tree_new_file` from inside presenter menu code (menus belong in shell action layer or a `ProjectTreeContextMenu` builder).
- **Suggested remediation:** R3 explorer split per `AUDIT_Maintainability.md`; align presenter boundary with `ProjectTreeController`’s callback-injection style.
- **Tests that would prove fix:** Presenter unit tests with fake host protocol (no `MainWindow` import); existing `tests/unit/project/test_project_tree_presenter.py` extended for populate/restore/reveal without full window.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-11-4 — `_selected_tree_directory` bypasses presenter and ignores multi-selection semantics

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py:4449-4462` — reads `TREE_ROLE_*` from `currentItem()` with manual parent-dir logic. Toolbar handlers `44464-4472` route New File/Folder through this path. Presenter already exposes `item_entry` (`project_tree_presenter.py:214-222`) and `selected_paths` via `selectedItems()` (`201-212`). Widget uses `ExtendedSelection` (`project_tree_widget.py:21`).
- **Code-judo alternative:** `ProjectTreePresenter.selected_destination_directory() -> str | None` — if exactly one selected item, use it; if multiple, use common parent or project root; if none, project root. Toolbar and context menu share one helper (context menu already duplicates parent-dir logic at `302-304`, `318`).
- **Suggested remediation:** Delete `_selected_tree_directory`; wire explorer buttons to presenter method; collapse duplicate parent-dir resolution in context menus into the same helper.
- **Tests that would prove fix:** Unit tests: multi-select → toolbar new file targets expected directory; no selection → project root; file selected → parent dir.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-11-5 — Nine one-line presenter delegators (display slice tail); violates R2 “method count down”

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** Immediately after slice end, `main_window.py:4482-4501` — `_populate_project_tree`, `_capture_project_tree_state`, `_restore_project_tree_state`, `_iter_project_tree_items`, `_collect_tree_descendants`, `_build_tree_item` each forward to `_get_project_tree_presenter()` in one line. Presenter is **already** constructed eagerly in `__init__` (`main_window.py:329-334`).
- **Code-judo alternative:** Call `self._project_tree_presenter` directly from the few real callers (`_apply_loaded_project`, `_reload_current_project`, theme apply, tests) and **delete** the delegators. Do not add `_get_project_tree_presenter()` lazy factory (`2788-2798`) — it duplicates eager init (dead branch when `__init__` ran).
- **Suggested remediation:** Hard cutover: remove delegators + lazy getter; update tests that call `window._populate_project_tree` to use presenter or a single package-level test hook if needed.
- **Tests that would prove fix:** `test_project_tree_refresh_state.py` updated to call presenter or public explorer API; grep confirms zero `_populate_project_tree` on `MainWindow`.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-11-6 — “Refresh Explorer” triggers full project reload cascade, not tree display refresh

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** Refresh button: `main_window_panels.py:133` — `clicked.connect(window._reload_current_project)`. `_reload_current_project` (`main_window.py:4809-4833`, outside slice) re-`open_project`s disk, reloads plugins, refreshes tooling, repopulates tree, updates search sidebar excludes, resets structure signature, **restarts symbol indexing**, refreshes test discovery. Slice only enables the button (`main_window.py:4440-4447`). External poll also calls same path (`main_window.py:5496-5504`).
- **Code-judo alternative:** `ProjectRefreshWorkflow` with tiers: (1) `refresh_tree_from_disk()` — re-enumerate entries, `presenter.populate(preserve_state=True)`; (2) optional `reload_project_metadata()` when manifest changes; (3) debounced intelligence/test rediscovery. Manual refresh button uses tier 1; poll uses signature diff to pick tier.
- **Suggested remediation:** Extract workflow; keep `_reload_current_project` as thin orchestrator or rename to `refresh_explorer` with explicit side-effect list. Coordinate with `ProjectTreeActionCoordinator`’s `reload_project` callback (already calls full reload after every file op — `project_tree_action_coordinator.py:71-82`).
- **Tests that would prove fix:** Characterization: refresh button does not restart symbol indexer when only unrelated cbcs run artifacts change (see `test_poll_external_file_changes_ignores_run_artifact_writes`); integration test that scroll/selection preserved without active-file reveal override (finding 1).
- **Handoff overlap:** R2, R4

---

### TN-SHELL-MW-11-7 — Three `ProjectTree*` types with overlapping names; controller is mislabeled for this slice

- **Persona:** TN-SHELL-MW-11
- **Severity:** NICE-TO-HAVE
- **Evidence:** `ProjectTreeController` (`project_tree_controller.py`) — editor/breakpoint remap on delete/move only; no tree widget. `ProjectTreePresenter` — widget populate/restore/menus. `ProjectTreeActionCoordinator` — filesystem ops + calls controller + `reload_project`. Display slice readers must hold all three mental models; `project_tree_controller.py` docstring says “operation coordination” but is narrower than `ProjectTreeActionCoordinator`.
- **Code-judo alternative:** Rename `ProjectTreeController` → `ProjectTreeEditorRemapService` (or fold into action coordinator as private methods); single `ProjectTree*` namespace for explorer UI.
- **Suggested remediation:** Rename in a dedicated refactor PR with import cutover; no behavior change.
- **Tests that would prove fix:** Import-only rename; existing `test_project_tree_controller.py` / `test_project_tree_action_coordinator.py` unchanged behavior.
- **Handoff overlap:** none

---

### TN-SHELL-MW-11-8 — Slice line range is ~75% non-tree code — symptom of 5549-line god file

- **Persona:** TN-SHELL-MW-11
- **Severity:** STRUCTURAL
- **Evidence:** `main_window.py` is **5549 lines** (well past 1k rule). Lines 4224–4438 in scope: `_set_search_results`, symbol index workers, `_clear_problems`, `closeEvent` / `_begin_shutdown_teardown`, sidebar view routing — only `4356-4357` (preview timer stop) and `4440-4477` touch project tree display/selection.
- **Code-judo alternative:** Decompose `MainWindow` into workflows/panels so slice critics map to modules (`SearchResultsCoordinator` already exists for search tail; symbol indexing → intelligence workflow; shutdown → lifecycle module). Target: no critic slice spans unrelated domains.
- **Suggested remediation:** Track in R2/R3 shell wave; do not add new methods in 4224–4477 band without extracting adjacent concerns first.
- **Tests that would prove fix:** Module-level unit tests replace `MainWindow.__new__` partial mocks (`test_project_tree_refresh_state.py:74-96` pattern).
- **Handoff overlap:** R2

---

## Positive signals (not findings)

- `ProjectTreePresenter.populate` / `capture_state` / `restore_state` with deferred scroll restore (`QTimer.singleShot(0)`) — thoughtful Qt lifecycle handling (`project_tree_presenter.py:57-79`).
- `ProjectTreeController` — clean injected callbacks, typed generic editor widget, no UI (`project_tree_controller.py:24-138`).
- Structure signature filtering ignores run artifacts — prevents refresh storms during run/debug (`test_project_tree_refresh_state.py:98-136`, `_filter_tree_signature_entries`).
- State preservation tests exist (`test_populate_project_tree_preserves_expansion_and_selection`).
- Explorer toolbar button enablement is centralized (`_update_explorer_buttons_enabled`).

---

## Approval bar (this slice)

**Would not approve** changes that add MainWindow tree display handlers, one-line presenter delegators, or another special-case branch in `_selected_tree_directory` without (1) fixing preserve-then-reveal selection clobber, (2) consolidating folder icon policy into presenter/widget, and (3) net **reducing** `MainWindow` method count. Any explorer/refresh refactor must validate tree icons and toolbar chrome in **all four theme modes** (Light, Dark, HC Light, HC Dark).
