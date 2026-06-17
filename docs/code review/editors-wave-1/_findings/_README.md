# Editors Wave 1 — Thermo-Nuclear Per-Critic Findings

This directory holds per-critic findings from the **2026-06-17** thermo-nuclear code quality pass on `app/editors/` plus the shell editor seam @ HEAD (`042be49e5777c587391ddbb396b7ea150e296dfe`). Each file is named `TN-EDIT-*.md` and follows the thermo-nuclear finding template.

Consolidated summary: [`../editors_wave_1_thermo_review_2026-06-17.md`](../editors_wave_1_thermo_review_2026-06-17.md).

**Scope:** Document only — no code changes in this round.

**Method:** 11 slice critics, then **TN-EDIT-INTEG** meta reviewer dedupes cross-cutting themes.

---

## Severity model

| Tier | Meaning |
|------|---------|
| **BLOCKER** | AD-016/AD-018/§17.4 contract violation with user-visible impact: wrong completion delete span, UI-thread session mutation, stale async paint, inventory walk drift, or >1k-line god module blocking safe extension |
| **STRUCTURAL** | High-conviction code-judo moves: mixin god growth, duplicate outline/completion paths, factory closure sprawl, forked prefix/context, poll-tier reload cascades, or ownership boundaries that will multiply debt |
| **NICE-TO-HAVE** | Backlog: typing hygiene, dead helpers, doc drift, four-theme polish gaps, or cleanup that does not change editor contracts |

Integration rollup maps deduped themes to **P0/P1/P2** (P0 = BLOCKER, P1 = STRUCTURAL, P2 = NICE-TO-HAVE).

---

## Expected files (12)

### Editor slices (11)

- [`TN-EDIT-CORE.md`](TN-EDIT-CORE.md) — `CodeEditorWidget` hub + chrome/bracket/overlay mixins
- [`TN-EDIT-SEM.md`](TN-EDIT-SEM.md) — semantics/editing/diagnostics mixins + intelligence presentation boundary
- [`TN-EDIT-COMP.md`](TN-EDIT-COMP.md) — `completion_popup/` MVC + tier presentation
- [`TN-EDIT-SEARCH.md`](TN-EDIT-SEARCH.md) — search panel, find/replace, shell search coordinators
- [`TN-EDIT-MGR.md`](TN-EDIT-MGR.md) — `EditorManager`, tab state, editorconfig, formatting
- [`TN-EDIT-MD.md`](TN-EDIT-MD.md) — markdown editor/preview/rendering
- [`TN-EDIT-SYNTAX.md`](TN-EDIT-SYNTAX.md) — syntax engine/registry + treesitter seam
- [`TN-EDIT-AUX.md`](TN-EDIT-AUX.md) — text_editing, quick open
- [`TN-EDIT-SHELL-TAB.md`](TN-EDIT-SHELL-TAB.md) — `editor_tab_workflow` (1k+), tab bar
- [`TN-EDIT-SHELL-FACTORY.md`](TN-EDIT-SHELL-FACTORY.md) — factory, workspace, session/sync workflows
- [`TN-EDIT-SHELL-INTEL.md`](TN-EDIT-SHELL-INTEL.md) — intelligence controller + completion/inline/stale-result workflows

### Integration meta (1)

- [`TN-EDIT-INTEG.md`](TN-EDIT-INTEG.md) — deduped `CC-EDIT-*` themes (runs last)

---

## Finding template

Each critic file should start with a header block, then findings:

```markdown
# TN-EDIT-XXX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-XXX
**Date:** 2026-06-17
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`
**Scope:** ...

---

## Executive verdict

One paragraph: thermo-clean or not; dominant risk in this slice.

---

### TN-EDIT-XXX-N — One-line headline

- **Persona:** TN-EDIT-XXX
- **Severity:** BLOCKER | STRUCTURAL | NICE-TO-HAVE
- **Evidence:** `path/to/file.py:LINE` — verbatim quote
- **Code-judo alternative:** ...
- **Suggested remediation:** ...
- **Tests that would prove fix:** ...
- **Handoff overlap:** R3 | R4 | AD-016 | AD-018 | CC-02 | CC-PROJ-13 | none
```

---

## Architecture gates (all critics)

1. Editor never executes user project code (`ARCHITECTURE.md` §4.1).
2. **AD-016** — Semantic work routes through `SemanticSession` / workflows; editors paint results.
3. **AD-018** — Async results verify buffer revision before UI mutation.
4. **§17.4.2** — Completion tiers must not present as one homogeneous list without explicit tier UI.
5. **§12.4** — `CodeEditorWidget` mixin composition; flag god-widget growth.
6. No semantic `ExtraSelection` overlays in the editor path.
7. **1k-line rule** — `editor_tab_workflow.py` at 1,013 LOC is presumptive blocker.
8. Editors import typed presentation models only; no broker engines/session internals.
9. **R4 inventory SSOT** — `search_panel` and poll paths use `file_inventory`; no ad-hoc walks.
10. **Four-theme compatibility** — UI findings note Light/Dark/HC Light/HC Dark impact.
11. **Hard-cutover bias** — delete dead paths over parallel modes.
12. **Canonical helpers** — reuse `app/project/` and `app/persistence/` primitives.

---

## Approval bar

`app/editors/` is **not thermo-clean** merely because mixins exist. The bar is:

- no AD-016 bypass on completion accept or outline build;
- no forked completion prefix/context between editors and broker;
- credible decomposition plan for `editor_tab_workflow.py` before feature growth;
- `search_panel` and poll paths do not conflict with R4 inventory SSOT;
- no unjustified >1k files;
- tiered completion presentation at the popup boundary per §17.4.2.

Treat as presumptive blockers unless justified:

- `editor_tab_workflow.py` >1k without decomposition plan;
- completion prefix fork or wrong delete span on accept;
- UI-thread broker/session mutation;
- duplicate outline caches with independent `build_outline_from_source` paths;
- dead sync `_completion_provider` preserving session bypass.
