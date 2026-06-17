# Shell Wave 2 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-06-17** thermo-nuclear **delta re-baseline** of `app/shell/` @ HEAD (`fccb6113577752eed330fd8910f72de598c97ec2`). Each file is named `TN-SHELL2-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../shell_wave_2_thermo_review_2026-06-17.md`](../shell_wave_2_thermo_review_2026-06-17.md).

**Scope:** Document only — no code changes in this round.

**Method:** 12 slice critics, then **TN-SHELL2-INTEG** meta reviewer dedupes cross-cutting themes and maps Shell Wave 1 `CC-01…CC-25` supersession.

**Delta rule:** Every finding must declare **Status:** `NEW` | `RESIDUAL` | `REGRESSION` relative to [Shell Wave 1](../shell-wave-1/shell_wave_1_thermo_review_2026-05-25.md).

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | Ship-blocking: data loss, document-safety regression, >1k-line god module, orchestrator bypass, P0 CC regression, or four-theme contract break with user-visible impact |
| **STRUCTURAL** | High-conviction code-judo: `window: Any` workflows, composition injection soup, unwired workflows, duplicate orchestration, handlers monolith, icon/diff decomposition debt |
| **NICE-TO-HAVE** | Backlog: typing hygiene, test brittleness, doc drift, minor four-theme polish, dead API surface |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (13)

### Shell slices (12)

- [`TN-SHELL2-ICON.md`](TN-SHELL2-ICON.md) — `icon_provider` (1k+), file/menu icons
- [`TN-SHELL2-COMP.md`](TN-SHELL2-COMP.md) — composition root (`main_window_composition`, `shell_composition`, `intelligence_composition`)
- [`TN-SHELL2-MW.md`](TN-SHELL2-MW.md) — `main_window` delta (542 LOC / 45 methods)
- [`TN-SHELL2-SETTINGS.md`](TN-SHELL2-SETTINGS.md) — settings dialog/models/handlers/apply
- [`TN-SHELL2-STYLES.md`](TN-SHELL2-STYLES.md) — stylesheets, `shell_theme_workflow`, tokens
- [`TN-SHELL2-OUTLINE.md`](TN-SHELL2-OUTLINE.md) — `outline/` package + symbol navigation
- [`TN-SHELL2-DEBUG-RUN.md`](TN-SHELL2-DEBUG-RUN.md) — debug panel, run launch, breakpoints
- [`TN-SHELL2-CONSOLE.md`](TN-SHELL2-CONSOLE.md) — Python console + REPL workflows
- [`TN-SHELL2-SEARCH.md`](TN-SHELL2-SEARCH.md) — search sidebar, find/replace coordinator
- [`TN-SHELL2-PROJECT.md`](TN-SHELL2-PROJECT.md) — project load/rescan/orchestrator/tree/save
- [`TN-SHELL2-EDITOR-SEAM.md`](TN-SHELL2-EDITOR-SEAM.md) — editor tab workflows + poll (Editors cross-wave)
- [`TN-SHELL2-LHIST-DIFF.md`](TN-SHELL2-LHIST-DIFF.md) — local history, `diff_view`, draft recovery

### Integration meta (1)

- [`TN-SHELL2-INTEG.md`](TN-SHELL2-INTEG.md) — deduped `CC-SHELL2-*` themes + Wave 1 supersession (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-SHELL2-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-XXX
**Date:** 2026-06-17
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-SHELL2-XXX-N — One-line headline

- **Persona:** TN-SHELL2-XXX
- **Status:** NEW | RESIDUAL | REGRESSION
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ...
- **Tests that would prove fix:** ...
- **Handoff overlap:** R2 | R3 | CC-XX | CC-PROJ-XX | CC-SHELL2-XX | none
```

---

## Architecture gates (all critics)

1. **AD-015** — `MainWindow` is composition root, not god file; method count must not grow without net extraction.
2. **1k-line rule** — `icon_provider.py` at 1,106 LOC is presumptive blocker; flag ≥700 LOC without decomposition plan.
3. **Typed host ports** — flag `window: Any` workflows and lambda/`setattr` injection grids.
4. **Document safety** — tree delete, external reload, decline-reload via `SaveWorkflow` / themed dialogs.
5. **Settings SSOT** — dual-scope OK preserves global + project + highlighting runtime fields.
6. **Four-theme** — UI findings note Light/Dark/HC Light/HC Dark; use `ShellThemeTokens` only.
7. **Project inventory orchestration** — `ProjectInventoryOrchestrator` owns snapshot per generation.
8. **Cross-wave contracts** — do not regress Editors Wave 2, Project SSOT P0, Intelligence/Run shell seams.
9. **Hard-cutover bias** — delete dead paths over parallel modes.
10. **Process boundaries** — shell orchestrates; does not execute user project code.
11. **Canonical helpers** — reuse `app/project/`, `app/persistence/`, `app/editors/` primitives.
12. **No dot-prefixed runtime paths** — `cbcs/`, `choreboy_code_studio_state/` only.

---

## Approval bar

`app/shell/` is **not thermo-clean** at HEAD unless:

- No `app/` file >1,000 LOC without compelling structure;
- Shell Wave 1 P0 themes CC-01…05 remain CLOSED (no REGRESSION);
- `MainWindow` methods ≤45 at baseline (target <40 after remediation);
- `ProjectInventoryOrchestrator` is sole poll/rescan inventory owner;
- No unwired `ShellThemeWorkflow` if theme fan-out still on `MainWindow`;
- Four-theme gaps documented or closed.

Presumptive blockers unless justified:

- `icon_provider.py` >1k;
- REGRESSION on CC-02/03/05;
- orchestrator bypass in poll;
- `window: Any` workflow growth without typed host migration plan.
