# Intelligence Wave 1 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-06-16** thermo-nuclear code quality pass on `app/intelligence/` plus the shell/editor intelligence seam @ HEAD (`ce176983f3d3434b390718692047583c9b38c4ed`). Each file is named `TN-INT-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../intelligence_wave_1_thermo_review_2026-06-16.md`](../intelligence_wave_1_thermo_review_2026-06-16.md).

**Scope:** Document only — no code changes in this round.

**Method:** 10 slice critics, then **TN-INT-INTEG** meta reviewer dedupes cross-cutting themes.

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | AD-016/§17.4 contract violation on main path: thread races, silent semantic/heuristic merge, stale UI application, hidden metadata |
| **STRUCTURAL** | High-conviction code-judo moves; debt that multiplies on next intelligence/shell growth |
| **NICE-TO-HAVE** | Backlog: test gaps, typing nits, doc drift, minor duplication |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (11)

### Intelligence package (7)

- [`TN-INT-01.md`](TN-INT-01.md) — semantic session, worker, facade, completion service
- [`TN-INT-02.md`](TN-INT-02.md) — completion broker, providers, context, resolver
- [`TN-INT-03.md`](TN-INT-03.md) — jedi engine, jedi runtime, semantic utils
- [`TN-INT-04.md`](TN-INT-04.md) — symbol index, api index, import resolver, cache controls
- [`TN-INT-05.md`](TN-INT-05.md) — diagnostics service, lint profile, code actions, import diagnostics
- [`TN-INT-06.md`](TN-INT-06.md) — outline service
- [`TN-INT-07.md`](TN-INT-07.md) — refactor engine, import rewrite, latency tracker

### Shell / editor seam (3)

- [`TN-INT-SHELL-NAV.md`](TN-INT-SHELL-NAV.md) — `semantic_navigation_workflow.py`
- [`TN-INT-SHELL-SEAM.md`](TN-INT-SHELL-SEAM.md) — composition, controller, lint/cache/console workflows
- [`TN-INT-SHELL-EDITORS.md`](TN-INT-SHELL-EDITORS.md) — editor layer intelligence imports

### Integration meta (1)

- [`TN-INT-INTEG.md`](TN-INT-INTEG.md) — deduped CC-xx themes (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-INT-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-INT-XXX
**Date:** 2026-06-16
**Baseline commit:** `ce176983f3d3434b390718692047583c9b38c4ed`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-INT-XXX-N — One-line headline

- **Persona:** TN-INT-XXX
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ...
- **Tests that would prove fix:** ...
- **Handoff overlap:** R4 | R5 | R2 | R3 | AD-016 | none
```

---

## Architecture gates (all critics)

1. Single owner: Jedi/Rope state only on `SemanticWorker`
2. No UI-thread semantic blocking
3. Facade/controller boundary — no direct Jedi/Rope/library calls from shell/editors
4. Merge policy owned by `CompletionBroker`, not widgets
5. No silent lexical+semantic or heuristic+semantic merge (§17.4.2)
6. Typed degradation metadata on all tiers
7. AD-018 revision gate before UI mutation
8. Completion priority + stale job skip
9. No editor-side execution of user project code for read-only semantics
10. Visible caches only (no dot-prefixed engine metadata)
11. No silent token-replace rename/reference fallback
12. SQLite/tree-sitter/index = acceleration, not semantic truth
13. Editor vs Python Console completion stay on separate stacks/channels
14. Selected-item resolve must not alter insert text/ranges
