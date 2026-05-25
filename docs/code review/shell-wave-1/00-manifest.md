# Scope manifest: shell-wave-1 thermo-nuclear review

Status: Wave 1 kickoff  
Baseline commit: `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
Date: 2026-05-25  
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear maintainability pass over `app/shell/`, led by `main_window.py` decomposition assessment and R2/R3 hotspot modules from [`docs/deslop/AUDIT_app_remaining_handoff.md`](../../deslop/AUDIT_app_remaining_handoff.md).

---

## Metric sweep (at kickoff)

| Metric | Value |
|--------|------:|
| Baseline commit | `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9` |
| `app/shell/` Python LOC | 30,766 |
| `main_window.py` LOC | 5,549 |
| `MainWindow` method count | 332 |
| Bare `except Exception:` in `app/shell/` | 14 |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/shell -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
rg "^    def " app/shell/main_window.py | wc -l
rg "^\s*except\s+Exception\s*:\s*$" app/shell/ --type py | wc -l
wc -l app/shell/main_window.py
```

---

## In scope

### MainWindow slices (16 critics)

| ID | Lines | Cluster |
|----|-------|---------|
| TN-SHELL-MW-01 | 1–772 | Imports, `__init__`, widget graph, controller/workflow wiring |
| TN-SHELL-MW-02 | 773–1117 | Startup restore, runtime onboarding, welcome, layout |
| TN-SHELL-MW-03 | 1118–1395 | Outline layout, theme tokens, stylesheets |
| TN-SHELL-MW-04 | 1396–1557 | Editor zoom, settings snapshots, shell event bus |
| TN-SHELL-MW-05 | 1558–1996 | Project/file open, settings entry, find/replace, text editing |
| TN-SHELL-MW-06 | 1997–2664 | Intelligence menu actions |
| TN-SHELL-MW-07 | 2665–2936 | Templates/examples, packaging, misc workflows |
| TN-SHELL-MW-08 | 2937–3483 | Run session, debug start/stop, run configs |
| TN-SHELL-MW-09 | 3484–3827 | Python console orchestration |
| TN-SHELL-MW-10 | 3828–4223 | Search-in-files sidebar |
| TN-SHELL-MW-11 | 4224–4477 | Project tree display/selection/refresh |
| TN-SHELL-MW-12 | 4478–4681 | Tree context menu ops |
| TN-SHELL-MW-13 | 4682–4911 | Tree bulk ops |
| TN-SHELL-MW-14 | 4912–5368 | Markdown preview, plugin panels/commands |
| TN-SHELL-MW-15 | 5369–5522 | Indent/paste repair, scheduled lint hooks |
| TN-SHELL-MW-16 | 5523–EOF | Realtime lint, close/save guards, lifecycle |

### Hotspot modules (5 critics)

| ID | Files | Handoff |
|----|-------|---------|
| TN-SHELL-SETTINGS | `settings_dialog.py`, `settings_models.py` | R3 |
| TN-SHELL-OUTLINE | `outline_panel.py` | R3 |
| TN-SHELL-DEBUG | `debug_panel_widget.py`, `debug_control_workflow.py` | R2/R3 |
| TN-SHELL-TEST-UI | `test_explorer_panel.py`, `test_runner_workflow.py` | R3 |
| TN-SHELL-LHIST | `local_history_workflow.py`, `local_history_dialog.py` | R3 |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-SHELL-INTEG | Dedupe cross-cutting themes → CC-01… IDs; map to R2/R3 |

---

## Out of scope (wave 2+)

- `app/intelligence/`, `app/runner/`, `app/run/`, `app/debug/` (except where MainWindow slice references them)
- R4 project file inventory SSOT, R5 dependency classifier SSOT
- R6 wholesale test audit
- `bundled_plugins/`, launchers, top-level packaging

---

## Canonical read order for critics

1. [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — AD-015 composition root
2. [`docs/deslop/AUDIT_app_remaining_handoff.md`](../../deslop/AUDIT_app_remaining_handoff.md) — R2/R3 rules
3. Assigned slice or module
4. Referenced controllers/workflows (read-only context)

---

## High-risk hotspots

- `app/shell/main_window.py` — 5,549 LOC orchestration monolith
- `app/shell/settings_dialog.py` — 1,311 LOC
- `app/shell/outline_panel.py` — 1,155 LOC
- Ceremonial extractions vs real ownership in existing controllers/workflows

---

## Output artifacts

```
docs/code review/shell-wave-1/
├── 00-manifest.md                    (this file)
├── _findings/
│   ├── _README.md
│   ├── TN-SHELL-MW-01.md … MW-16.md
│   ├── TN-SHELL-SETTINGS.md … LHIST.md
│   └── TN-SHELL-INTEG.md
└── shell_wave_1_thermo_review_2026-05-25.md
```

---

## Validation commands (for fix agent, not this review round)

```bash
python3 testing/run_test_shard.py fast
npx pyright
```
