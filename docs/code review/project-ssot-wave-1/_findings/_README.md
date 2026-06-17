# Project SSOT Wave 1 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-06-16** thermo-nuclear code quality pass on R4/R5 Project SSOT: project file inventory, dependency classification, diagnostics/package audit convergence, and shell/packaging orchestration @ HEAD (`042be49e5777c587391ddbb396b7ea150e296dfe`). Each file is named `TN-PROJ-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../project_ssot_wave_1_thermo_review_2026-06-16.md`](../project_ssot_wave_1_thermo_review_2026-06-16.md).

**Scope:** Document only — no code changes in this round.

**Method:** 7 slice critics, then **TN-PROJ-INTEG** meta reviewer dedupes cross-cutting themes.

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | SSOT contract violation with user-visible or ship-blocking impact: file-set disagreement, `cbcs/`/exclude regression, packaging-vs-diagnostics classification disagreement, native-extension false negative/positive, or runtime probes on hot lint paths. |
| **STRUCTURAL** | High-conviction code-judo moves: duplicated full-project walks, forked AST/structure extractors, parallel classification trees, non-atomic index/cache writes, or ownership boundaries that will multiply debt. |
| **NICE-TO-HAVE** | Backlog: fingerprint weakness, dead helpers, stale docs, minor typing/test gaps, or cleanup that does not change SSOT contracts. |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (8)

### Project SSOT slices (7)

- [`TN-PROJ-INV.md`](TN-PROJ-INV.md) — inventory core, excludes, project enumeration, search
- [`TN-PROJ-CONSUMERS.md`](TN-PROJ-CONSUMERS.md) — symbol index, completion providers, diagnostics inventory consumers
- [`TN-PROJ-REWRITE.md`](TN-PROJ-REWRITE.md) — import layout and rewrite ownership
- [`TN-PROJ-CLASS.md`](TN-PROJ-CLASS.md) — dependency classifier, ingest, manifest, plugin auditor
- [`TN-PROJ-DIAG.md`](TN-PROJ-DIAG.md) — diagnostics/classifier convergence and runtime probe ownership
- [`TN-PROJ-PKG.md`](TN-PROJ-PKG.md) — packaging enumeration, dependency audit, layout excludes
- [`TN-PROJ-SHELL.md`](TN-PROJ-SHELL.md) — shell orchestration of inventory refresh

### Integration meta (1)

- [`TN-PROJ-INTEG.md`](TN-PROJ-INTEG.md) — deduped `CC-PROJ-*` themes (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-PROJ-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-PROJ-XXX
**Date:** 2026-06-16
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-PROJ-XXX-N — One-line headline

- **Persona:** TN-PROJ-XXX
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ...
- **Tests that would prove fix:** ...
- **Handoff overlap:** R4 | R5 | CC-15 | CC-14 | none
```

---

## Architecture gates (all critics)

1. All project `.py` discovery routes through `app/project/file_inventory.py`; no new `rglob('*.py')` or ad-hoc `cbcs/` skip.
2. Packaging project enumeration routes through the inventory API, or the exception is documented and protected by parity tests.
3. `cbcs/` policy is explicit per API: tree enumeration may include it, intelligence/package analysis must not accidentally drift.
4. Exclude policy has one effective source per use case; avoid a third unowned plane between `file_excludes`, packaging layout, and import layout.
5. One project generation should not trigger N independent full walks; snapshot orchestration must be owned.
6. `ProjectInventorySnapshot` is the canonical module-list contract for intelligence subsystems.
7. Import classification routes through `dependency_classifier.py`; no parallel stdlib lists or native-extension scans without a clearly named lower-level primitive.
8. `classify_module` and `is_module_resolvable` must agree on representative packaging-vs-PY200 cases, or the difference must be an explicit product policy.
9. `explain_unresolved_import` should adapt classifier/layout results, not grow a second classifier.
10. Dependency direction should be `intelligence -> project`, not `project -> intelligence`.
11. Packaging must not import private intelligence symbols.
12. Native-extension detection must not fork between ingest, audit, and plugin auditor.

---

## Approval bar

`app/project/` inventory and classifier SSOT is **not thermo-clean** merely because `file_inventory.py` and `dependency_classifier.py` exist. The bar is:

- no clear file-set disagreement between search, tree enumeration, diagnostics, symbol index, completion, import rewrite, and packaging;
- no unowned extra traversal path that changes `cbcs/`, vendor, symlink, ordering, or exclude semantics;
- no duplicated classification path that can make packaging, diagnostics, and explain UI disagree for the same import;
- no layer inversion that makes project-layer SSOT depend on intelligence implementation details;
- no native-extension detector fork that could miss or mislabel native dependencies;
- no obvious missing orchestration for sharing one project snapshot per generation.

Treat these as presumptive blockers unless the author can justify them clearly:

- packaging copies a file set that dependency audit never considered;
- diagnostics and package audit classify the same import differently without an explicit policy;
- a new traversal or classifier is added outside the SSOT modules;
- a PR preserves multiple full-project walks where a single project-generation snapshot is available;
- explain/quick-fix code reaches into private project helpers or parses diagnostic strings instead of using explicit contracts.
