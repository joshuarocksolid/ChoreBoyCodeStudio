# Run Wave 1 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-05-25** thermo-nuclear code quality pass on `app/run/`, `app/runner/`, `app/debug/`, and the shell run/debug seam @ HEAD (`24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`). Each file is named `TN-RUN-*.md` or `TN-RUNNER-*.md` or `TN-DEBUG-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../run_wave_1_thermo_review_2026-05-25.md`](../run_wave_1_thermo_review_2026-05-25.md).

**Scope:** Document only — no code changes in this round.

**Method:** 9 slice critics, then **TN-RUN-INTEG** meta reviewer dedupes cross-cutting themes.

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | Process-boundary violation, data loss, zombie subprocess, debug desync on main path |
| **STRUCTURAL** | High-conviction code-judo moves; debt that multiplies with next run/debug growth |
| **NICE-TO-HAVE** | Backlog: doc nits, minor duplication, test brittleness |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (11)

### Run package (3)

- [`TN-RUN-01.md`](TN-RUN-01.md) — manifest + launch contract
- [`TN-RUN-02.md`](TN-RUN-02.md) — subprocess lifecycle + RunService
- [`TN-RUN-03.md`](TN-RUN-03.md) — pytest services + problem parser

### Runner package (3)

- [`TN-RUNNER-01.md`](TN-RUNNER-01.md) — normal bootstrap path
- [`TN-RUNNER-02.md`](TN-RUNNER-02.md) — REPL sidecar + completion
- [`TN-RUNNER-03.md`](TN-RUNNER-03.md) — `debug_runner.py` alone

### Debug package (2)

- [`TN-DEBUG-01.md`](TN-DEBUG-01.md) — models, protocol, breakpoints, safe_eval
- [`TN-DEBUG-02.md`](TN-DEBUG-02.md) — session + transport

### Shell seam (1)

- [`TN-RUN-SHELL.md`](TN-RUN-SHELL.md) — run/debug orchestration workflows

### Integration meta (1)

- [`TN-RUN-INTEG.md`](TN-RUN-INTEG.md) — deduped CC-xx themes (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-RUN-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-RUN-XXX
**Date:** 2026-05-25
**Baseline commit:** `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-RUN-XXX-N — One-line headline

- **Persona:** TN-RUN-XXX
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ...
- **Tests that would prove fix:** ...
- **Handoff overlap:** R1 | R-run-2 | shell-wave-1-followup | none
```

Critics that find no issues write `## No findings` plus a one-paragraph note on what was inspected.

---

## Handoff rules

- Hard cutover importers; no compatibility shims.
- Do not grow `debug_runner.py` past 1k without decomposition.
- Shell seam workflows: prefer typed host bundles over `window: Any`.
- Write tests only when risk-first gate says justified (note in finding, do not add tests in this review round).
- Do not treat [`docs/deslop/AUDIT_app.md`](../../../deslop/AUDIT_app.md) as current.
