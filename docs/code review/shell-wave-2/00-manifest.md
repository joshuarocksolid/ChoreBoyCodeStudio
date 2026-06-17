# Scope manifest: shell-wave-2 thermo-nuclear review

Status: Wave 2 kickoff (delta re-baseline)
Baseline commit: `fccb6113577752eed330fd8910f72de598c97ec2`
Date: 2026-06-17
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear **delta re-baseline** of `app/shell/` after Shell Wave 1 remediation (May 2025 baseline: `main_window.py` 5,549 LOC / 332 methods). Wave 2 does **not** re-run 16 `main_window.py` line-range critics. It:

1. Reconciles Shell Wave 1 `CC-01…CC-25` against the live tree
2. Audits post-remediation composition architecture
3. Focuses slice critics on remaining hotspots and cross-wave shell seams

Prior waves: [shell-wave-1](../shell-wave-1/), [editors-wave-1](../editors-wave-1/), [project-ssot-wave-1](../project-ssot-wave-1/), [intelligence-wave-1](../intelligence-wave-1/), [run-wave-1](../run-wave-1/).

---

## Metric sweep (at kickoff)

| Metric | Shell Wave 1 (2026-05-25) | Shell Wave 2 kickoff |
|--------|---------------------------|----------------------|
| Baseline commit | `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9` | `fccb6113577752eed330fd8910f72de598c97ec2` |
| `app/shell/` Python LOC | 30,766 | **42,446** |
| `main_window.py` LOC | 5,549 | **542** |
| `MainWindow` method count | 332 | **45** |
| Files ≥1,000 LOC in `app/` | many | **1** (`icon_provider.py` 1,106) |
| Agent debug logging | present | **0** (`rg 'debug-0b96d3\|#region agent log' app/`) |
| Bare `except Exception:` in `app/shell/` | 14 | **13** |
| `# type: ignore` in `app/shell/` | — | **80** |
| `window: Any` in `app/shell/` | — | **79** |
| Unit tests `tests/unit/shell/` | — | **106** files |

**Files ≥700 LOC (shell, kickoff):**

| LOC | File |
|----:|------|
| 1,106 | `icon_provider.py` |
| 830 | `diff_view.py` |
| 782 | `python_console_widget.py` |
| 778 | `settings_dialog_handlers.py` |
| 736 | `settings_models.py` |
| 687 | `search_sidebar_widget.py` |
| 674 | `local_history_workflow.py` |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/shell -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
rg "^    def " app/shell/main_window.py | wc -l
rg "^\s*except\s+Exception\s*:\s*$" app/shell --type py | wc -l
rg "# type: ignore" app/shell --type py | wc -l
rg "window: Any" app/shell --type py | wc -l
find app -name '*.py' -exec wc -l {} + | awk '$1 >= 1000 {print}'
rg 'debug-0b96d3|#region agent log' app/
```

---

## Prep findings (merged from P1–P5)

*Coordinator merges prep agent output below after Step 1.*

### P1 — Dependency graph

*(pending)*

### P2 — Metric sweep detail

*(pending)*

### P3 — Shell Wave 1 CC reconciliation (CC-01…CC-25)

*(pending)*

### P4 — Cross-wave closure cross-read

*(pending)*

### P5 — Test coverage map

*(pending)*

---

## Architecture gates (all critics)

1. AD-015 composition root — MainWindow method count must not grow without net extraction.
2. 1k-line rule — `icon_provider.py` presumptive blocker.
3. Typed host ports — no `window: Any` workflow growth without migration plan.
4. Document safety — SaveWorkflow / themed dialogs for destructive paths.
5. Settings SSOT — dual-scope OK + highlighting field round-trip.
6. Four-theme compatibility — `ShellThemeTokens` only.
7. Project inventory orchestration — `ProjectInventoryOrchestrator` sole owner.
8. Cross-wave contracts — Editors Wave 2, Project SSOT P0, Intelligence/Run seams.
9. Hard-cutover bias — delete dead paths.
10. Process boundaries — shell orchestrates only.
11. Canonical helpers — `app/project/`, `app/persistence/`, `app/editors/`.
12. No dot-prefixed runtime paths.

---

## In scope — slice critics (12)

| ID | Primary files | Cluster | Re-validate CC |
|----|---------------|---------|----------------|
| TN-SHELL2-ICON | `icon_provider.py`, `file_type_icons.py`, `menu_icons.py` | 1k icon pipeline | CC-21, CC-23 |
| TN-SHELL2-COMP | `main_window_composition.py`, `shell_composition.py`, `intelligence_composition.py`, `main_window_lifecycle.py` | Composition root | CC-06, CC-07, CC-22 |
| TN-SHELL2-MW | `main_window.py`, `main_window_panels.py`, `menu_wiring.py`, `menus.py` | MainWindow delta | CC-06, CC-13, CC-20 |
| TN-SHELL2-SETTINGS | `settings_dialog*.py`, `settings_models.py`, `settings_apply_workflow.py`, `shell_preferences.py` | Settings SSOT | CC-02, CC-08, CC-21 |
| TN-SHELL2-STYLES | `style_sheet*.py`, `shell_theme_workflow.py`, `theme_tokens.py` | Theme/QSS | CC-04, CC-09, CC-23 |
| TN-SHELL2-OUTLINE | `outline/`, `symbol_navigation_workflow.py` | Outline panel split | CC-09, CC-21, CC-23 |
| TN-SHELL2-DEBUG-RUN | `debug_panel/`, `run_launch/`, `debug_control_workflow.py`, `run_launch_workflow.py` | Run/debug seam | CC-12, CC-14 |
| TN-SHELL2-CONSOLE | `python_console_widget.py`, `python_console_workflow.py`, REPL workflows | Console/REPL | CC-18, CC-23 |
| TN-SHELL2-SEARCH | `search_sidebar_widget.py`, `find_replace_workflow.py`, `diagnostics_search_coordinator.py` | Search pipeline | CC-17, CC-20 |
| TN-SHELL2-PROJECT | `project_*_workflow.py`, `project_inventory_orchestrator.py`, `save_workflow.py` | Project orchestration | CC-03, CC-11, CC-16, CC-PROJ-03 |
| TN-SHELL2-EDITOR-SEAM | `editor_tab_*`, poll/content/markdown registries | Editors cross-wave | Editors CC-EDIT-* |
| TN-SHELL2-LHIST-DIFF | `local_history_*`, `diff_view.py`, `draft_autosave_workflow.py` | History/diff | CC-05, CC-07, CC-21 |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-SHELL2-INTEG | Dedupe `CC-SHELL2-*`; Wave 1 supersession table; fix waves |

---

## Test coverage gaps (critics must validate)

| Module / behavior | Dedicated tests | Gap severity |
|-------------------|-----------------|--------------|
| `icon_provider.py` decomposition | partial icon tests | **High** |
| `settings_dialog_handlers.py` dual-scope | `test_settings_models.py`, `test_settings_dialog.py` | Medium |
| `shell_theme_workflow` wiring | `test_shell_theme_workflow.py` | **High** — wiring vs module-only |
| `project_inventory_orchestrator` | `test_editor_tab_workflow_inventory.py` | Medium |
| `diff_view.py` | sparse | **High** |
| `MainWindow.__new__` harness | many shell tests | Medium (CC-24) |

---

## Out of scope

- Fix commits, new tests, pyright fixes
- Full `app/editors/`, `app/intelligence/`, `app/run/`, `app/project/` re-review (seam critics only)
- R6 wholesale test audit, R7 out-of-scope audit
- `app/packaging/`, `bundled_plugins/`, launchers

---

## Artifact layout

```text
docs/code review/shell-wave-2/
├── 00-manifest.md
├── shell_wave_2_thermo_review_2026-06-17.md
├── shell_wave_2_remediation_plan.md
├── shell_wave_2_implementation_plan.md
└── _findings/
    ├── _README.md
    ├── TN-SHELL2-*.md (12 slices)
    └── TN-SHELL2-INTEG.md
```
