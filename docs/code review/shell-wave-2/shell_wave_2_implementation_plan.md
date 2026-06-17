# Shell Wave 2 — End-to-End Implementation Plan

Status: **implementation-ready** (Phase 2 execution)  
Baseline: `fccb6113577752eed330fd8910f72de598c97ec2`  
Source review: [`shell_wave_2_thermo_review_2026-06-17.md`](shell_wave_2_thermo_review_2026-06-17.md)  
Strategy doc: [`shell_wave_2_remediation_plan.md`](shell_wave_2_remediation_plan.md)  
Integration themes: [`_findings/TN-SHELL2-INTEG.md`](_findings/TN-SHELL2-INTEG.md)

Executable companion: every CC-SHELL2 theme maps to concrete PRs, files, verification gates, and dependencies.

---

## 1. Program scope and completion definition

### In scope

- Close **CC-SHELL2-01** (mandatory P0 architecture gate).
- Close all **P1** themes CC-SHELL2-02 … CC-SHELL2-22 (mandatory for thermo-clean declaration).
- P2 hygiene in Wave 7 where risk-first gate applies.

### Out of scope

- Intelligence engine internals; full Run transport P0s (already run-layer); packaging SSOT.

### Completion gates

| # | Gate | Verification |
|---|------|--------------|
| 1 | No `app/` file >1000 LOC | `find app -name '*.py' -exec wc -l {} + \| awk '$1>=1000'` empty |
| 2 | Wave 1 P0 remains closed | `rg 'debug-0b96d3\|#region agent log' app/` empty; settings/draft/safety tests green |
| 3 | Inventory one-walk | spy test + `test_project_inventory_orchestrator` + poll unit tests |
| 4 | Restart reliability | `tests/integration/shell/test_run_debug_toolbar_integration.py` |
| 5 | MainWindow ≤40 methods | `rg "^    def " app/shell/main_window.py \| wc -l` |
| 6 | Editors Wave 2 gates | grep gates in INTEG §7 |
| 7 | fast shard + pyright | `python3 testing/run_test_shard.py fast`; `npx pyright` |

---

## 2. CC theme closure matrix

| CC-SHELL2 | Priority | Wave | PR range |
|-----------|----------|------|----------|
| CC-SHELL2-01 | P0 | 0 | SHELL-R-01, R-02 |
| CC-SHELL2-02 | P1 | 0 | SHELL-R-02 |
| CC-SHELL2-03 | P1 | 2 | SHELL-R-10 |
| CC-SHELL2-04 | P1 | 1 | SHELL-R-03 |
| CC-SHELL2-05 | P1 | 1,4,5 | SHELL-R-04, R-15, R-16 |
| CC-SHELL2-06 | P1 | 1 | SHELL-R-03, R-05 |
| CC-SHELL2-07 | P1 | 1 | SHELL-R-06 |
| CC-SHELL2-08 | P1 | 2 | SHELL-R-11 |
| CC-SHELL2-09 | P1 | 2 | SHELL-R-09 |
| CC-SHELL2-10 | P1 | 6 | SHELL-R-17, R-18 |
| CC-SHELL2-11 | P1 | 4,5 | SHELL-R-14, R-16 |
| CC-SHELL2-12 | P1 | 3, joint | SHELL-R-12 (optional sidebar split) |
| CC-SHELL2-13 | P1 | 3 | SHELL-R-13 |
| CC-SHELL2-14 | P1 | 3 | SHELL-R-12 |
| CC-SHELL2-15 | P1 | 3 | SHELL-R-13 |
| CC-SHELL2-16 | P1 | 6 | SHELL-R-20 |
| CC-SHELL2-17 | P1 | 4 | SHELL-R-14 |
| CC-SHELL2-18 | P1 | 4 | SHELL-R-15 |
| CC-SHELL2-19 | P1 | 4 | SHELL-R-16 |
| CC-SHELL2-20 | P1 | 5 | SHELL-R-17 |
| CC-SHELL2-21 | P1 | 3 | SHELL-R-12 |
| CC-SHELL2-22 | P1 | 6 | SHELL-R-19 |

---

## 3. PR catalog (SHELL-R-01 … SHELL-R-20)

### Wave 0 — Icon pipeline

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-01** | CC-SHELL2-01 | Split `icon_provider.py` → `icons/svg_registry.py` + facade | — | No file >1k; `test_menu_icons` |
| **SHELL-R-02** | CC-SHELL2-02 | `icons/render.py`; `clear_icon_caches()`; panel dedupe | R-01 | Theme apply clears caches |

### Wave 1 — Composition + typed ports

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-03** | CC-SHELL2-04, CC-SHELL2-06 | `ShellCompositionContext`; phased `install_main_window_composition` | R-02 | Installer LOC ↓; startup smoke |
| **SHELL-R-04** | CC-SHELL2-05 | `SaveDocumentHost`; refactor `save_workflow.py` | R-03 | `test_save_workflow`; no `window: Any` in save_workflow |
| **SHELL-R-05** | CC-SHELL2-06 | `LocalHistoryEditorHost`; collapse LHIST lambdas | R-03 | `test_local_history_workflow` |
| **SHELL-R-06** | CC-SHELL2-07 | `editor_sync_factory.py`; delete upward import | R-03 | Import graph test |

### Wave 2 — Theme + QSS

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-09** | CC-SHELL2-09 | `theme_tokens.py`; `style_sheet_sections_*.py` accent tokens | R-03 | `rg '#4D7AFF' app/shell/style_sheet` empty |
| **SHELL-R-10** | CC-SHELL2-03 | `outline_icons.py`, `python_console_widget.py`, `main_window_panels.py` token colors | R-09 | Four-theme manual smoke |
| **SHELL-R-11** | CC-SHELL2-08 | `shell_theme_surface_appliers.py`; shrink theme host | R-09 | `test_shell_theme_workflow` |

### Wave 3 — Inventory + tree + registry

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-12** | CC-SHELL2-14, CC-SHELL2-21 | `project_inventory_orchestrator.py`, `editor_tab_poll_workflow.py`, `editor_tab_content_registry.py` | R-03 | `test_editor_tab_workflow_inventory`; registry grep gate |
| **SHELL-R-13** | CC-SHELL2-13, CC-SHELL2-15 | `project_tree_action_coordinator.py`, `project_load_surface.py`, `RefreshTier` | R-12 | Tree op without full `open_project` test |

### Wave 4 — Debug/run

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-14** | CC-SHELL2-17, CC-SHELL2-11 | `run_event_workflow.py`, `run_debug_presenter.py`, `main_window.py`, `menu_wiring.py` | R-04 | Restart integration test |
| **SHELL-R-15** | CC-SHELL2-18 | `debug_control_workflow.py`, `debug_panel/` | R-14 | Single clear-all path test |
| **SHELL-R-16** | CC-SHELL2-19, CC-SHELL2-05 | `run_debug_presenter.py`, `run_launch_workflow.py` typed hosts | R-14 | Presenter unit tests without MW |

### Wave 5 — Console + MW shrink

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-17** | CC-SHELL2-20 | `python_console_workflow.py`, `repl_event_workflow.py`, `python_console_widget.py` | R-04, R-14 | `test_python_console_workflow`; no console handlers on MW |
| **SHELL-R-18** | CC-SHELL2-11 | `editor_tabs_coordinator.py`, `menu_wiring.py` editor text routes | R-17 | MW methods ≤40 |

### Wave 6 — Settings + history + outline

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-19** | CC-SHELL2-22 | `diff_parser.py`, `diff_gutter.py`, slim `diff_view.py`; `recovery_orchestrator.py` | R-05 | `test_diff_view`; `test_local_history_workflow` |
| **SHELL-R-20** | CC-SHELL2-10, CC-SHELL2-16 | settings handler split; `settings_apply_workflow` diff; `outline_panel` in-place theme | R-11 | `test_settings_models`; outline theme test |

### Wave 7 — Hygiene (optional batch)

| PR | CC | Files | Depends | Verification |
|----|-----|-------|---------|--------------|
| **SHELL-R-21** | P2 / CC-24 | Migrate `MainWindow.__new__` tests | R-18 | Fewer harness tests |
| **SHELL-R-22** | P2 / CC-25 | Settings tuple cleanup; `MenuCallbacks` trim | R-20 | pyright clean |

---

## 4. Parallel agent batches (remediation execution)

| Batch | PRs | Parallel safe? |
|-------|-----|----------------|
| A | R-01, R-02 | Serial (same icon tree) |
| B | R-03, R-09 | After A |
| C | R-04, R-05, R-06, R-11 | After B — disjoint files |
| D | R-12, R-13 | After C |
| E | R-14, R-15, R-16 | After C (needs R-04) |
| F | R-17, R-18 | After E |
| G | R-19, R-20 | After B (theme) + F optional |
| H | R-21, R-22 | Last |

---

## 5. Global verification commands (every PR)

```bash
python3 testing/preflight_test_env.py
python3 testing/run_test_shard.py fast
npx pyright
rg "^    def " app/shell/main_window.py | wc -l
rg 'debug-0b96d3|#region agent log' app/
find app -name '*.py' -exec wc -l {} + | awk '$1>=1000 {print}'
```

### Targeted suites by wave

```bash
# Wave 0
python3 run_tests.py tests/unit/shell/test_menu_icons.py tests/unit/shell/test_toolbar_icons.py

# Wave 1
python3 run_tests.py tests/unit/shell/test_save_workflow.py tests/unit/shell/test_local_history_workflow.py

# Wave 2
python3 run_tests.py tests/unit/shell/test_shell_theme_workflow.py tests/unit/shell/test_main_window_syntax_override_loading.py

# Wave 3
python3 run_tests.py tests/unit/shell/test_project_inventory_orchestrator.py tests/unit/shell/test_editor_tab_workflow_inventory.py tests/unit/shell/test_project_tree_action_workflow.py

# Wave 4
python3 run_tests.py tests/integration/shell/test_run_debug_toolbar_integration.py tests/unit/shell/test_run_debug_presenter.py

# Wave 5
python3 run_tests.py tests/unit/shell/test_python_console_workflow.py tests/unit/shell/test_python_console_widget.py

# Wave 6
python3 run_tests.py tests/unit/shell/test_diff_view.py tests/unit/shell/test_settings_models.py tests/unit/shell/test_outline_panel.py
```

### Editors / Project preservation gates

```bash
rg '_markdown_panes_by_path' app/shell/
rg 'hover_provider' app/
rg 'build_project_inventory_snapshot' app/intelligence/
rg 'from app\.intelligence' app/project/
```

---

## 6. MainWindow method budget

| Checkpoint | Max methods |
|------------|---------------|
| Baseline | 45 |
| After Wave 4 | ≤43 |
| After Wave 5 (R-18) | **≤40** |

Any PR that increases method count is **stop-the-line** unless paired with net extraction in same PR.

---

## 7. Four-theme manual acceptance

UI-touching PRs: R-02, R-10, R-11, R-19, R-20 require spot-check in Light, Dark, HC Light, HC Dark per [`docs/ACCEPTANCE_TESTS.md`](../../ACCEPTANCE_TESTS.md) or documented gap in PR summary.

---

## 8. Closure report artifact

When program completes, add `shell_wave_2_remediation_closure_YYYY-MM-DD.md` mirroring Editors Wave 2 closure format with CC-SHELL2 matrix and **ACCEPT/REJECT** verdict.

---

## 9. Coordinator anti-patterns

- Do not add glyphs to `icon_provider.py` before R-01 lands.
- Do not add `window: Any` workflows — extend typed host protocols.
- Do not reintroduce ghost MainWindow search worker or independent poll walks.
- Do not break Editors Wave 2 grep gates for shell convenience.
