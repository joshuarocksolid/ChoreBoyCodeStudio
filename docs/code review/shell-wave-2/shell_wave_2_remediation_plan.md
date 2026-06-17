# Shell Wave 2 — Remediation Plan (Phase 2)

Status: ready for implementation approval  
Implementation plan: [`shell_wave_2_implementation_plan.md`](shell_wave_2_implementation_plan.md)  
Baseline: `fccb6113577752eed330fd8910f72de598c97ec2`  
Source review: [`shell_wave_2_thermo_review_2026-06-17.md`](shell_wave_2_thermo_review_2026-06-17.md)  
Integration themes: [`_findings/TN-SHELL2-INTEG.md`](_findings/TN-SHELL2-INTEG.md)

**Do not start implementation until this plan is approved.** Phase 1 (document-only review) is complete.

---

## Goals

1. Resolve **CC-SHELL2-01** — no `app/` file >1,000 LOC without compelling structure.
2. Execute **CC-SHELL2-05** typed host migration — `SaveWorkflow` and presenter/launch hosts first.
3. Close **CC-SHELL2-14** — one inventory walk per project generation at shell boundary.
4. Fix **CC-SHELL2-17** debug/run restart race (Run Wave 1 CC-17 shell debt).
5. Decompose **CC-SHELL2-22** `diff_view` before new history/diff UX.
6. Shrink **MainWindow** to **≤40 methods** without reintroducing god-file patterns.
7. Preserve **Editors Wave 2 ACCEPT** grep gates and **Project SSOT P0** closures.

---

## Non-negotiable rules (every PR)

- Hard cutover importers; no long-lived parallel theme/search/inventory modes.
- Python 3.9 syntax; no dot-prefixed runtime paths.
- **MainWindow method count must not grow** on any touching PR; net-reduce or hold ≤45 until Wave 5 target ≤40.
- No new one-line MainWindow delegators.
- Do not grow `icon_provider.py`, `main_window_composition.py`, or `diff_view.py` without decomposition plan landing in same program.
- UI-touching PRs record four-theme validation (Light, Dark, HC Light, HC Dark) or document gap.
- Tests only when risk-first gate applies: restart race, inventory walk count, document safety regression, icon cache invalidation, tiered tree refresh.
- Preserve Editors Wave 2 gates (`_markdown_panes_by_path`, `hover_provider`, poll orchestrator consumer).

---

## Wave 0 — Icon 1k architecture gate

**Blocks:** CC-SHELL2-01, CC-SHELL2-02 (partial), CC-SHELL2-03 (partial)

**Goal:** Split `icon_provider.py` below 1k; establish SVG registry and shared render primitives.

### Step 0.1 — SVG registry extraction

**Files:** new `app/shell/icons/svg_registry.py` (or `icon_svg_registry.py`), slim `icon_provider.py` facade

**Work:**
1. Move per-glyph `*_icon` factories into data-driven registry (path + viewBox + token keys).
2. Keep public `icon_provider` API stable for importers (`menu_icons`, `toolbar`, panels).
3. Add `clear_icon_caches()` called from theme apply preamble.

**Gate:** `find app -name '*.py' -exec wc -l {} + | awk '$1>=1000'` → empty; `test_menu_icons` + `test_toolbar_icons` green.

### Step 0.2 — Shared QPainter primitives

**Files:** new `app/shell/icons/render.py`; update `file_type_icons.py`, `outline/outline_icons.py`, `test_explorer_icons.py` consumers

**Work:**
1. Single `render_svg_pixmap` / `render_themed_icon` helper using `ShellThemeTokens`.
2. Delete duplicate QPainter blocks flagged in TN-SHELL2-ICON.

**Gate:** No new QPainter duplication in panel modules; four-theme icon smoke on toolbar + outline kinds.

---

## Wave 1 — Composition + typed host ports

**Blocks:** CC-SHELL2-04, CC-SHELL2-05, CC-SHELL2-06, CC-SHELL2-07

**Goal:** Replace setattr mega-installer with phased context; type SaveWorkflow and critical hosts.

### Step 1.1 — `ShellCompositionContext` phased install

**Files:** `main_window_composition.py`, `shell_composition.py`

**Work:**
1. Introduce dataclass context holding wired workflows/controllers (pattern: `EditorTabContentRegistry`).
2. Split install into ordered phases: layout → persistence → editors → intelligence → run/debug → theme.
3. Register QTimers in one place; delete scattered `hasattr` timer guards.

**Gate:** `main_window_composition.py` installer block ≤250 LOC; cold-start smoke test.

### Step 1.2 — `SaveDocumentHost` protocol

**Files:** `save_workflow.py`, `shell_composition.py`, `project_tree_action_workflow.py`, `external_file_change_workflow.py`

**Work:**
1. Replace `SaveWorkflow(window: Any)` with typed host protocol (editor manager, history, cache, dialogs).
2. Invert dependencies — workflow methods take explicit ports, not `window._*`.

**Gate:** `rg 'def __init__\(self, window: Any\)' app/shell/save_workflow.py` → empty; `test_save_workflow` green.

### Step 1.3 — Delete upward composition import

**Files:** `editor_tab_workflow.py`, `shell_composition.py`, new `editor_sync_factory.py` (or move to `editor_sync_workflow.py`)

**Work:**
1. Extract `build_editor_sync_workflow` to neutral module owned by editor-tab layer.
2. Import-graph test: workflows must not import `shell_composition`.

### Step 1.4 — `LocalHistoryEditorHost`

**Files:** `local_history_workflow.py`, `main_window_composition.py`

**Work:**
1. Collapse 16+ callable injection into typed host protocol.
2. Delete dead `ensure_breakpoint_spec` injection if unused.

---

## Wave 2 — Theme + four-theme QSS

**Blocks:** CC-SHELL2-08, CC-SHELL2-09, CC-SHELL2-03

**Goal:** Move surface appliers out of composition host; tokenize accent hover/pressed.

### Step 2.1 — Token fields for accent states

**Files:** `theme_tokens.py`, `style_sheet_sections_*.py`

**Work:**
1. Add `accent_hover`, `accent_pressed` (or semantic equivalents) to `ShellThemeTokens` for all four modes.
2. Replace `#4D7AFF` / `#2952CC` ternaries in section modules.

**Gate:** `rg '#4D7AFF|#2952CC' app/shell/style_sheet` → empty or documented exceptions only.

### Step 2.2 — `ShellThemeSurfaceAppliers`

**Files:** new `shell_theme_surface_appliers.py`, shrink `MainWindowShellThemeHost` in `shell_composition.py`

**Work:**
1. Move menu/toolbar/statusbar/editor chrome apply fan-out from host callbacks into applier module.
2. Remove deferred editor rehighlight `QTimer` chain from host — single orchestrated pass in workflow.

**Gate:** `test_shell_theme_workflow.py` extended; composition theme host ≤80 LOC.

### Step 2.3 — Token-driven outline/console/search chrome

**Files:** `outline/outline_icons.py`, `main_window_panels.py`, `python_console_widget.py`

**Work:**
1. Replace binary `is_dark` kind palettes with per-mode token maps.
2. Remove hardcoded explorer toolbar hex; use `diag_error_color` for console stderr.

---

## Wave 3 — Project inventory + tree refresh

**Blocks:** CC-SHELL2-13, CC-SHELL2-14, CC-SHELL2-15, CC-SHELL2-21 (partial)

**Goal:** One walk per generation; tiered tree refresh; canonical editor tab registry.

### Step 3.1 — Orchestrator decoupling

**Files:** `project_inventory_orchestrator.py`, `project_rescan_workflow.py`, `search_sidebar_widget.py`, `editor_tab_poll_workflow.py`

**Work:**
1. Remove orchestrator rebuild gate under search sidebar presence.
2. Delete poll `iter_project_entries` fallback when orchestrator signature is `None` — fail loud or rebuild orchestrator first.
3. Spy test: open/rescan performs one snapshot build before index/analysis.

### Step 3.2 — Tiered `RefreshTier` for tree coordinator

**Files:** `project_tree_action_coordinator.py`, `project_rescan_workflow.py`

**Work:**
1. Introduce tiers: `metadata_only`, `tree_entries`, `full_rescan` (plugins/reindex).
2. Map FS operations (rename, delete, new file) to minimal tier — not always `open_project`.

### Step 3.3 — Canonical `MarkdownTabRegistry`

**Files:** `editor_tab_content_registry.py`, `markdown_tab_registry.py`, `project_tree_ui_workflow.py`

**Work:**
1. Single registry instance owned by content registry; delete per-call `MarkdownTabRegistry()` construction.
2. `rg 'MarkdownTabRegistry\(' app/shell/` → ≤2 (definition + registry owner).

---

## Wave 4 — Debug/run lifecycle

**Blocks:** CC-SHELL2-17, CC-SHELL2-18, CC-SHELL2-19

**Goal:** Exit-gated restart; single breakpoint clear path; typed presenter/launch hosts.

### Step 4.1 — Restart exit gate

**Files:** `run_event_workflow.py`, `run_debug_presenter.py`, `main_window.py`, `menu_wiring.py`

**Work:**
1. Move stop/restart/clear-console off MainWindow to presenter/workflow.
2. Gate relaunch on prior session `exited` event — no `ALREADY_RUNNING` race.

**Gate:** Integration test `test_run_debug_toolbar_integration` restart path green.

### Step 4.2 — Breakpoint clear-all SSOT

**Files:** `debug_control_workflow.py`, `debug_panel/debug_panel_widget.py`

**Work:**
1. Route panel "clear all" through workflow atomic `clear_all_breakpoints`.
2. Delete N-emit loop in panel.

### Step 4.3 — `RunDebugPresenterHost` + launch host narrowing

**Files:** `run_debug_presenter.py`, `run_launch_workflow.py`, `run_launch/debug_targets.py`

**Work:**
1. Replace presenter `window: Any` with typed host protocol.
2. Narrow `RunLaunchWorkflowHost` `Any` ports to explicit session/output/breakpoint interfaces.

---

## Wave 5 — Console + MainWindow shrink

**Blocks:** CC-SHELL2-20, CC-SHELL2-11

**Goal:** Full `PythonConsoleWorkflow`; typed `ReplEvent`; MW ≤40 methods.

### Step 5.1 — Expand console workflow

**Files:** `python_console_workflow.py`, `main_window.py`, `main_window_panels.py`, `repl_event_workflow.py`

**Work:**
1. Move submit/interrupt/restart/session lifecycle into workflow.
2. Replace tuple `ReplEvent` queue with typed union dataclass.

### Step 5.2 — Shared completion typing controller

**Files:** `python_console_widget.py`, `python_console_workflow.py`, shared helper with editor completion

**Work:**
1. Extract prefix reuse + tier-header guard shared with editor path.
2. Fix stale `_active_completion_prefix` on empty async responses.

### Step 5.3 — MainWindow delegator shrink

**Files:** `main_window.py`, `menu_wiring.py`, `editor_tabs_coordinator.py`, `run_debug_presenter.py`

**Work:**
1. Editor text menu actions → coordinator.
2. Run session handlers → presenter (completes Wave 4 wiring).

**Gate:** `rg "^    def " app/shell/main_window.py | wc -l` → ≤40.

---

## Wave 6 — Settings + history/diff R3

**Blocks:** CC-SHELL2-10, CC-SHELL2-16, CC-SHELL2-22

**Goal:** Split handlers/models; decompose diff_view; outline in-place theme repaint.

### Step 6.1 — Settings handler split

**Files:** split `settings_dialog_handlers.py` into tab modules; `settings_apply_workflow.py`

**Work:**
1. One module per tab group (general, editor, intelligence, output, lint).
2. Collapse `SettingsApplyBaseline` duplication; wire `retention_policy_changed` or delete flag.
3. Apply diff runs only changed subsystems.

**Gate:** No handler module >400 LOC.

### Step 6.2 — `diff_view` layer split

**Files:** new `diff_parser.py`, `diff_gutter.py`, slim `diff_view.py` widget

**Work:**
1. Parser pure functions tested (extend `test_diff_view.py`).
2. Widget owns scroll/sync only.

### Step 6.3 — History dispatch consolidation

**Files:** `local_history_workflow.py`, new `recovery_orchestrator.py`

**Work:**
1. Single `_execute_history_action` dispatcher; delete triplicate restore paths.
2. Target `local_history_workflow.py` facade <450 LOC.

### Step 6.4 — Outline in-place theme repaint

**Files:** `outline/outline_panel.py`, `shell_theme_workflow.py`

**Work:**
1. Update icons/colors without `_tree.clear()` full rebuild on theme pass.

---

## Wave 7 — Hygiene (R6)

**Blocks:** CC-24, CC-25, P2 rollup

**Goal:** Test brittleness reduction; typing cleanup; contract tests.

### Step 7.1 — Test harness migration

**Work:** Migrate high-signal tests off `MainWindow.__new__` to workflow public APIs.

### Step 7.2 — Contract tests

**Work:** QSS builder smoke; icon cache clear; diff widget render smoke.

### Step 7.3 — Typing cleanup

**Work:** Positional `MainWindowSettingsSnapshot` tuples; `MenuCallbacks` field reduction where safe.

---

## Deferred / explicit non-goals

- Full `app/intelligence/` re-review (Intelligence Wave 1 scope).
- Full R6 wholesale test audit beyond Wave 7 high-signal migrations.
- `symbol_navigation_workflow.py` 380 LOC nested callback refactor — track as Intelligence/shell follow-up unless it crosses 1k.

---

## Program completion definition

Shell subsystem is **thermo-clean** when:

1. **CC-SHELL2-01** closed — no `app/` file >1k.
2. **CC-SHELL2-05** substantially closed — `SaveWorkflow` + presenter/launch hosts typed; `window: Any` count trending down with no new untyped workflows.
3. **CC-SHELL2-14** closed — one inventory walk per generation; poll uses orchestrator only.
4. **CC-SHELL2-17** closed — restart integration test green.
5. **CC-SHELL2-22** closed — `diff_view` children each <400 LOC.
6. MainWindow methods ≤40.
7. Editors Wave 2 + Project SSOT P0 grep gates remain green.
8. Four-theme manual acceptance recorded for UI-touching waves or documented gap closed.
