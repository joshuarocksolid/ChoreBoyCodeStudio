# Shell Wave 1 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-05-25** thermo-nuclear code quality pass on `app/shell/` @ HEAD (`7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`). Each file is named `TN-SHELL-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../shell_wave_1_thermo_review_2026-05-25.md`](../shell_wave_1_thermo_review_2026-05-25.md).

**Scope:** Document only — no code changes in this round.

**Method:** 21 slice critics (16 MainWindow line ranges + 5 hotspot modules), then **TN-SHELL-INTEG** meta reviewer dedupes cross-cutting themes.

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | Structural regression, coordination split, silent wrong behavior on main path |
| **STRUCTURAL** | High-conviction code-judo moves; debt that multiplies with next shell growth |
| **NICE-TO-HAVE** | Backlog: doc nits, minor duplication, test sprawl |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (22)

### MainWindow slices (16)

- [`TN-SHELL-MW-01.md`](TN-SHELL-MW-01.md) — lines 1–772: init, wiring
- [`TN-SHELL-MW-02.md`](TN-SHELL-MW-02.md) — lines 773–1117: startup, onboarding, layout
- [`TN-SHELL-MW-03.md`](TN-SHELL-MW-03.md) — lines 1118–1395: outline layout, theme
- [`TN-SHELL-MW-04.md`](TN-SHELL-MW-04.md) — lines 1396–1557: zoom, settings loaders, events
- [`TN-SHELL-MW-05.md`](TN-SHELL-MW-05.md) — lines 1558–1996: open, find/replace, editing
- [`TN-SHELL-MW-06.md`](TN-SHELL-MW-06.md) — lines 1997–2664: intelligence actions
- [`TN-SHELL-MW-07.md`](TN-SHELL-MW-07.md) — lines 2665–2936: templates, packaging
- [`TN-SHELL-MW-08.md`](TN-SHELL-MW-08.md) — lines 2937–3483: run/debug session
- [`TN-SHELL-MW-09.md`](TN-SHELL-MW-09.md) — lines 3484–3827: python console
- [`TN-SHELL-MW-10.md`](TN-SHELL-MW-10.md) — lines 3828–4223: search sidebar
- [`TN-SHELL-MW-11.md`](TN-SHELL-MW-11.md) — lines 4224–4477: project tree display
- [`TN-SHELL-MW-12.md`](TN-SHELL-MW-12.md) — lines 4478–4681: tree context menu
- [`TN-SHELL-MW-13.md`](TN-SHELL-MW-13.md) — lines 4682–4911: tree bulk ops
- [`TN-SHELL-MW-14.md`](TN-SHELL-MW-14.md) — lines 4912–5368: markdown, plugins
- [`TN-SHELL-MW-15.md`](TN-SHELL-MW-15.md) — lines 5369–5522: indent/lint hooks
- [`TN-SHELL-MW-16.md`](TN-SHELL-MW-16.md) — lines 5523–EOF: realtime lint, lifecycle

### Hotspot modules (5)

- [`TN-SHELL-SETTINGS.md`](TN-SHELL-SETTINGS.md) — `settings_dialog.py`, `settings_models.py` (R3)
- [`TN-SHELL-OUTLINE.md`](TN-SHELL-OUTLINE.md) — `outline_panel.py` (R3)
- [`TN-SHELL-DEBUG.md`](TN-SHELL-DEBUG.md) — `debug_panel_widget.py`, `debug_control_workflow.py` (R2/R3)
- [`TN-SHELL-TEST-UI.md`](TN-SHELL-TEST-UI.md) — `test_explorer_panel.py`, `test_runner_workflow.py` (R3)
- [`TN-SHELL-LHIST.md`](TN-SHELL-LHIST.md) — `local_history_workflow.py`, `local_history_dialog.py` (R3)

### Integration meta (1)

- [`TN-SHELL-INTEG.md`](TN-SHELL-INTEG.md) — vertical slice + deduped CC-xx themes (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-SHELL-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-XXX
**Date:** 2026-05-25
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-SHELL-XXX-N — One-line headline

- **Persona:** TN-SHELL-XXX
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ... (name target controller/workflow if applicable)
- **Tests that would prove fix:** ...
- **Handoff overlap:** R2 | R3 | none
```

Critics that find no issues write `## No findings` plus a one-paragraph note on what was inspected.

---

## Handoff rules (from deslop brief)

- If touching MainWindow, method count must go **down** — no new one-line delegators.
- Hard cutover importers; no compatibility shims.
- UI changes: note four-theme impact (Light, Dark, HC Light, HC Dark).
- Do not treat [`docs/deslop/AUDIT_app.md`](../../deslop/AUDIT_app.md) as current.
