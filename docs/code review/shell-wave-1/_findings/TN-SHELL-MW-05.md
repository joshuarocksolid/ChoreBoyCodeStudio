# TN-SHELL-MW-05 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-05  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 1558–1996 — project/file open, new window, project creation, settings dialog entry/apply, quick open, find/replace bar handlers, and text-editing menu actions. Context: `ProjectController`, `SaveWorkflow`, `EditorWorkspaceController`, `EditorTabFactory`, `main_window_panels.py` find-bar wiring.

---

## Executive verdict

**Not thermo-clean.** This slice is where AD-015 composition-root drift is most visible on user-facing file workflows: `_handle_open_settings_action` is a ~135-line sequential orchestrator that persists settings, reloads six preference tuples (see TN-SHELL-MW-04-1), reapplies theme/editor/diagnostics/runtime state, may full-reload the project, and redundantly reconfigures search excludes. Project **open** is correctly thin-delegated to `ProjectController` + `SaveWorkflow`, but **create** flows (blank, template, parent-dir bootstrap, prompts) and **quick open** lifecycle still live entirely on `MainWindow`. Find/replace adds seven near-identical guard-and-forward handlers instead of a `FindReplaceWorkflow` beside `SaveWorkflow` / `PythonStyleWorkflow`. Text-editing actions are additional one-line delegators that violate the handoff shrink rule. Dominant risk: **settings-apply + open/create orchestration spaghetti on a 5,549-line / 332-method class** — the next menu item in this band will compound method count and partial-update ordering bugs.

---

### TN-SHELL-MW-05-1 — Settings dialog OK path is a monolithic orchestrator on MainWindow

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1709–1844` — `_handle_open_settings_action` loads payloads, runs `SettingsDialog`, merges/saves, then sequentially mutates ~25 instance fields, stops/starts timers, reloads preferences via six `_load_*_preferences` calls (`1781–1809`), applies editor/intelligence/shortcut/theme, conditionally relints, clears diagnostics, reloads project on exclude change, and updates search sidebar + placeholder.
- **Code-judo alternative:** `SettingsApplyWorkflow` (or extend `settings_models` + a narrow `SettingsRuntimeApplier` collaborator) owning: open-dialog inputs, merge/save, snapshot diff, and `apply_runtime(snapshot_delta, window_ports)` where `window_ports` is an explicit dataclass of callables (`apply_theme`, `reload_project`, `relint_open_files`, …). `MainWindow` keeps `_handle_open_settings_action` as one line: `self._settings_apply_workflow.run_dialog_and_apply()`.
- **Suggested remediation:** R2 extraction per `AUDIT_app_remaining_handoff.md` R2 (thin pass-through cleanup + workflow modules). Hard cutover `menu_wiring.on_open_settings` to workflow method. Pair with TN-SHELL-MW-04-1 single-load fix in the same PR or immediately before.
- **Tests that would prove fix:** Characterization test: mock `SettingsService` + dialog accept → assert field values and side effects (timer stopped, relint invoked) match current behavior; mock-count test for one settings load per apply (after MW-04-1 consolidation).
- **Handoff overlap:** R2 (MainWindow), R3 (`settings_dialog.py` if dialog/workflow boundary moves)

---

### TN-SHELL-MW-05-2 — Exclude-pattern change triggers redundant project + search work

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1832–1841` — on exclude change, calls `_reload_current_project()` then, if search sidebar exists, calls `_load_effective_exclude_patterns` again and `set_exclude_patterns(compute_effective_excludes(...))`. `_reload_current_project` at `4809–4826` already reopens the project, repopulates the tree, and sets search excludes on the sidebar.
- **Code-judo alternative:** Settings apply workflow calls one `refresh_project_inventory(reason="settings_excludes")` that owns reopen + tree + sidebar + symbol index + test discovery — no second exclude pass in the settings handler.
- **Suggested remediation:** R2 — fold into `SettingsApplyWorkflow` or `ProjectController` inventory refresh API; delete the duplicate block at `1835–1841` in the same hard-cutover PR.
- **Tests that would prove fix:** Unit/integration test with mock sidebar: single `set_exclude_patterns` per settings apply when excludes change; project entries match `open_project` with new patterns.
- **Handoff overlap:** R2, R4 (exclude SSOT — `file_inventory` brief)

---

### TN-SHELL-MW-05-3 — Project creation and workspace bootstrap bypass ProjectController

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectController` only exposes `open_project_by_path` and `refresh_open_recent_menu` (`app/shell/project_controller.py:22–80`). Creation/bootstrap remains on `MainWindow`: `_handle_new_project_action` / `_handle_new_project_from_template_action` (`1652–1695`), `_prompt_for_new_project_destination` (`1697–1707`), `_prompt_for_template` (`1846–1854`), `_maybe_open_parent_directory_as_project` (`1606–1621`), and multi-file open bootstrap in `_handle_open_file_action` (`1591–1604`). Open path correctly delegates at `2671–2678` with `SaveWorkflow.confirm_proceed_with_unsaved_changes`.
- **Code-judo alternative:** Extend `ProjectController` (or `ProjectCreationWorkflow` with injected dialog callables) to own: blank create, template materialize, parent-dir assessment + open, and “open files then ensure workspace” — `MainWindow` wires menu → `project_controller.create_and_open(...)` / `open_files_with_workspace(...)`.
- **Suggested remediation:** R2 MainWindow wave 4 — one cohesive extraction PR; pass `choose_existing_directory`, `QInputDialog`, and `on_opened` callback rather than `MainWindow` self. Reuse `assess_project_root` / `ProjectRootState` from project service (already used at `1615–1620`).
- **Tests that would prove fix:** Unit tests on controller for parent-dir bootstrap (canonical/importable vs generic), template create error mapping; existing `tests/integration/project/test_project_import_open.py` still pass via shell wiring.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-4 — Find/replace is seven duplicate MainWindow handlers

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_panels.py:201–207` wires six signals to `MainWindow._handle_find_bar_*`. Handlers at `app/shell/main_window.py:1904–1969` each repeat:

  ```python
  editor_widget = self._active_editor_widget()
  if editor_widget is None or self._find_replace_bar is None:
      return
  ```

  `_handle_find_action` / `_handle_replace_action` (`1904–1920`) duplicate the same initial-text selection pattern.
- **Code-judo alternative:** `FindReplaceWorkflow(window)` (mirror `SaveWorkflow`) holding bar + active editor resolution; one `bind_bar(find_replace_bar)` connects signals internally. Menu `on_find` / `on_replace` call `workflow.open_find()` / `open_replace()`. Optional: move search highlight orchestration next to `CodeEditorWidget` mixin seam if editor layer should own match navigation.
- **Suggested remediation:** R2 — extract module under `app/shell/`; hard cutover panel wiring to workflow; delete seven `MainWindow` methods (method count **down** per handoff §3).
- **Tests that would prove fix:** Unit test on workflow with stub editor + bar: find updates match count, replace_all clears count, close clears highlights; no new tests on private `_handle_find_bar_*` names.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-5 — Text-editing menu actions are forbidden one-line delegators

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1971–1995` — `_handle_toggle_comment_action`, `_handle_indent_action`, `_handle_outdent_action`, and flat-Python paste/selection handlers only fetch `_active_editor_widget()` and forward. `app/shell/menu_wiring.py:106–107` binds menus to these methods. Handoff: “If touching MainWindow, the method count must go down. Do not add new one-line delegator methods.” (`docs/deslop/AUDIT_app_remaining_handoff.md` §3)
- **Code-judo alternative:** Wire `on_toggle_comment` / `on_indent` / `on_outdent` directly to `EditorTabsCoordinator` or a tiny `EditorTextActions` helper constructed in `__init__` (same pattern as `PythonStyleWorkflow` for format/lint). Status-bar messaging for flat-Python can be a callback passed once.
- **Suggested remediation:** R2 — remove four+ methods; update `menu_wiring` and any shortcut tables in one hard-cutover PR.
- **Tests that would prove fix:** `rg "^    def " app/shell/main_window.py | wc -l` decreases; optional unit test on `EditorTextActions` if logic grows; manual acceptance unchanged (editor behavior).
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-6 — Quick Open dialog lifecycle and signal lambdas anchored on MainWindow

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1856–1902` — `_handle_quick_open_action` builds candidate list, lazily constructs `QuickOpenDialog`, connects four lambdas to `_editor_tab_factory` / `_open_file_at_line`, sets candidates, opens dialog. ARCHITECTURE §12.3 lists quick open as a product feature but no shell workflow owns it yet.
- **Code-judo alternative:** `QuickOpenWorkflow` with `open(project, editor_open_fn, open_at_line_fn)`; dialog created once per window lifetime inside workflow; `MainWindow` exposes one `handle_quick_open_action` that delegates (or menu wires directly to workflow).
- **Suggested remediation:** R2 — extract before search sidebar / intelligence slices add more open-file entry points.
- **Tests that would prove fix:** Unit test: given stub project entries + open callbacks, workflow passes `is_open` flags correctly; preview vs commit paths invoke callbacks with expected `preview=` flag.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-7 — New Window subprocess launch is shell orchestration noise

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1623–1650` — `_handle_new_window_action`, `_resolve_repo_root_for_launch`, `_build_new_window_command` embed AppRun detection, `build_runpy_bootstrap_payload`, and `subprocess.Popen` in `MainWindow`. R2 candidate list includes `RuntimeOnboardingWorkflow` / startup facade for repo-root launch (`AUDIT_app_remaining_handoff.md` R2 §Candidate extractions §3).
- **Code-judo alternative:** Move to `startup_facade` or `RuntimeOnboardingWorkflow.launch_additional_editor_window(parent)`; `MainWindow` calls one workflow method from menu.
- **Suggested remediation:** R2 — extract with existing `resolve_runtime_executable` / bootstrap helpers; keep QMessageBox error UX identical.
- **Tests that would prove fix:** Unit test on command builder: FreeCAD vs plain Python runtime paths; integration optional with mocked `Popen`.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-8 — `_handle_open_file_action` mixes three unrelated concerns

- **Persona:** TN-SHELL-MW-05
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1567–1604` — (1) computes `start_dir` from home/project/active tab, (2) optionally bootstraps parent directory as project when no project loaded (`1591–1596`), (3) loops `open_file_in_editor` for each path, (4) forces editor screen visibility with comment documenting welcome-page bug.
- **Code-judo alternative:** `ProjectController.open_files_in_workspace(file_paths, *, editor_factory, show_editor_screen)` or split: `resolve_open_file_start_dir(...)` + `ensure_workspace_for_paths(...)` + editor factory loop; welcome-screen transition owned by shell navigation helper used by all “surface editor” paths.
- **Suggested remediation:** R2 — extract with TN-SHELL-MW-05-3 parent-dir bootstrap; ensure `_show_editor_screen()` is called from one canonical “editor became visible” path (tree open, quick open, file menu).
- **Tests that would prove fix:** Characterization: open file with no project → parent assessed → editor stack index 1; multi-select opens N tabs.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-9 — `EditorWorkspaceController` unused for find/editing seams

- **Persona:** TN-SHELL-MW-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `docs/ARCHITECTURE.md` §12.3 — `editor_workspace_controller` “for open-editor ownership and monotonic buffer revisions.” Implementation (`app/shell/editor_workspace_controller.py`) is a thin path→widget map. This slice resolves editors via `_active_editor_widget()` → tabs coordinator (`5000–5001`), not `_workspace_controller.widget_for_path`.
- **Code-judo alternative:** Either document that workspace controller is revision-only and find/editing stay on tabs coordinator, or consolidate “active editor” resolution through workspace controller so find workflow and intelligence share one seam.
- **Suggested remediation:** Defer until TN-SHELL-MW-05-4/5 extractions; avoid expanding `MainWindow` with more `_active_editor_widget` call sites.
- **Tests that would prove fix:** N/A unless boundary moves; pyright/module doc update if ownership clarifies.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-05-10 — Parent-project bootstrap swallows assessment failures silently

- **Persona:** TN-SHELL-MW-05
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:1614–1618` —

  ```python
  except Exception as exc:
      self._logger.debug("Skipped parent project assessment for %s: %s", parent_dir, exc)
      return
  ```

  User still gets a tab from `_handle_open_file_action` but may lack tree/search/quick-open project context when assessment fails.
- **Code-judo alternative:** Narrow exceptions to expected `OSError` / validation errors; optional one-line status bar hint when bootstrap skipped (non-modal).
- **Suggested remediation:** R2 project bootstrap extraction; align with project service error taxonomy.
- **Tests that would prove fix:** Unit test: assessment raises → file opens, project remains `None`, no `_open_project_by_path` call.
- **Handoff overlap:** R2

---

## Cross-slice notes (for TN-SHELL-INTEG)

- **Settings load amplification:** TN-SHELL-MW-04-1 covers six `_load_*_preferences` calls inside this slice’s apply block (`1781–1809`); integration should merge MW-04 and MW-05-1 into one P1 “settings runtime apply” theme.
- **Theme / HC syntax:** TN-SHELL-MW-03-1 (HC overrides) affects `_apply_theme_styles` invoked from settings apply at `1818`; four-theme validation belongs to that fix, not re-audited here.
- **Positive pattern:** `_open_project_by_path` → `ProjectController` + `SaveWorkflow.confirm_proceed_with_unsaved_changes` is the target shape for the rest of this slice.
- **Method-count metric:** This slice adds ~22 `MainWindow` methods in the 1558–1996 band; R2 PRs touching it must net **fewer** methods, not moved delegators.
- **Four-theme impact:** No new hardcoded colors in this slice. Settings apply triggers `_handle_set_theme` and `_apply_theme_styles` — HC/Light/Dark correctness depends on MW-03 loader fix; record manual four-theme check when extracting settings apply workflow.
