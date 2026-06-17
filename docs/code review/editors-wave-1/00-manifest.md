# Scope manifest: editors-wave-1 thermo-nuclear review

Status: Wave 1 kickoff
Baseline commit: `042be49e5777c587391ddbb396b7ea150e296dfe`
Date: 2026-06-17
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear maintainability pass over the editor subsystem:

- [`app/editors/`](../../app/editors/) — `CodeEditorWidget` mixin stack, completion popup, search, markdown, syntax, tab/disk state (~6,935 LOC, 34 modules)
- Shell editor seam — tab factory/workflow, workspace revisions, intelligence routing (~2.5k LOC across 10 `editor_*` shell modules)

This wave follows completion of Shell Wave 1, Run Wave 1, Intelligence Wave 1, and Project SSOT Wave 1. Prior waves skimmed the editor boundary via [TN-INT-SHELL-EDITORS](../intelligence-wave-1/_findings/TN-INT-SHELL-EDITORS.md) and [TN-PROJ-SHELL](../project-ssot-wave-1/_findings/TN-PROJ-SHELL.md); this review verifies whether editor ownership is thermo-clean end-to-end.

---

## Metric sweep (at kickoff)

| Metric | Value |
|--------|------:|
| Baseline commit | `042be49e5777c587391ddbb396b7ea150e296dfe` |
| `app/editors/` Python LOC | 6,935 (34 modules) |
| Shell editor seam LOC (10 `editor_*` modules) | ~2,519 |
| Largest editor modules | `code_editor_widget.py` 754, `text_editing.py` 525, `quick_open_dialog.py` 458, `code_editor_semantics.py` 376 |
| **>1k violation** | `editor_tab_workflow.py` **1,013** (only scoped file >1k) |
| Files ≥700 LOC in scope | `code_editor_widget.py` 754 |
| Intelligence imports in `app/editors/` | 9 files (presentation models + merge policy) |
| Shell files importing `app.editors` | 28 |
| Bare `except Exception:` in `app/editors/` | 4 |
| `# type: ignore` in `app/editors/` | 22 |
| `: Any` annotations in `app/editors/` | 24 |
| Unit tests `tests/unit/editors/` | 22 files |
| Shell editor tests `tests/unit/shell/test_editor*` | 6 files |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/editors -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
wc -l app/shell/editor_tab_workflow.py app/editors/code_editor_widget.py
rg "from app\.intelligence|import app\.intelligence" app/editors --type py -l
rg "from app\.editors|import app\.editors" app/shell --type py -l | wc -l
rg "^\s*except\s+Exception\s*:\s*$" app/editors --type py | wc -l
find app -name '*.py' -exec wc -l {} + | awk '$1 >= 1000 {print}'
```

---

## Prep findings (merged from P1–P4)

### P1 — Dependency graph (summary)

- **Hub:** `code_editor_widget.py` composes 6 mixins + `completion_popup` + `syntax_registry`.
- **Intelligence touch:** 9 editor files; gate-8 violations: `completion_context`, `completion_merge_policy`, `latency_tracker` (not presentation-only).
- **Project touch:** `search_panel.py` only (`file_inventory` + `file_excludes`).
- **Shell seam:** 7/10 `editor_*` modules import `app.editors`; 28 shell files total.
- **Top risks:** semantics builds completion context in-editor; `editor_tab_workflow` 1,013 LOC + direct outline/poll; factory closure sprawl; inventory fragmentation search vs poll.

### P2 — Metric sweep (summary)

| Threshold | Files |
|-----------|-------|
| ≥1000 LOC | `editor_tab_workflow.py` (1,013) |
| ≥700 LOC | `code_editor_widget.py` (754) |
| Hygiene | 4 bare `except Exception`, 22 `# type: ignore`, 21 `: Any` (top-level editors) |

### P3 — Prior-wave cross-read (summary)

| Status | Count | Examples |
|--------|------:|----------|
| OBSOLETE | 2 | TN-INT-2 acceptance path; TN-INT-5 dead sync provider |
| PARTIALLY FIXED | 11 | TN-INT-1 prefix (now `build_completion_context`); TN-INT-3 outline off UI thread; CC-06 nav split → tab workflow 1k |
| STILL OPEN | 2 | TN-INT-7 popup prefix reuse; TN-INT-8 factory closures |

### P4 — Test coverage map (summary)

| Behavior | Tests | Gap |
|----------|-------|-----|
| Completion prefix/accept/tiers | `test_semantic_editor_interactions.py`, `test_completion_item_model.py` (partial) | **High** — no prefix parity matrix |
| `editor_completion_workflow` acceptance | `test_editor_completion_workflow.py` (resolve gate only) | **High** — no acceptance routing test |
| Poll/fingerprint tier | `test_editor_tab_workflow_inventory.py` | **High** — no outline async/revision tests |
| `editor_stale_result_policy` | `test_editor_stale_result_policy.py` | Medium |
| `search_panel` R4 | `test_search_panel.py` | Medium |
| Highlighting perf | `test_editor_highlighting_performance.py` | Low (perf only) |

---

## Architecture gates (all critics)

1. Process boundary — editor never executes user project code.
2. AD-016 — semantic work via `SemanticSession`/workflows; editors paint only.
3. AD-018 — revision-gated async UI mutation.
4. §17.4.2 tier separation in completion UI.
5. §12.4 mixin model — no god-widget growth.
6. No semantic `ExtraSelection` overlays.
7. 1k-line rule — `editor_tab_workflow.py` presumptive blocker.
8. Intelligence import discipline — presentation models only in editors.
9. R4 inventory SSOT for search + poll paths.
10. Four-theme compatibility for UI findings.
11. Hard-cutover bias — delete dead paths.
12. Canonical helpers from `app/project/` and `app/persistence/`.

---

## In scope — slice critics (11)

| ID | Primary files | Cluster |
|----|---------------|---------|
| TN-EDIT-CORE | `code_editor_widget.py`, chrome/bracket/overlay mixins, `paste_hint_overlay.py` | Widget composition hub |
| TN-EDIT-SEM | `code_editor_semantics.py`, `code_editor_editing.py`, `code_editor_diagnostics.py` | Intelligence presentation boundary |
| TN-EDIT-COMP | `completion_popup/*` | Popup MVC + tiers |
| TN-EDIT-SEARCH | `search_panel.py`, `find_replace_bar.py`, `code_editor_search.py` + shell search coordinators | R4 consumer + bounded search |
| TN-EDIT-MGR | `editor_manager.py`, `editor_tab.py`, `editorconfig.py`, `indentation.py`, `formatting_service.py` | Tab/disk SSOT |
| TN-EDIT-MD | `markdown_editor_pane.py`, `markdown_preview_widget.py`, `markdown_rendering.py` | Markdown dual-pane |
| TN-EDIT-SYNTAX | `syntax_engine.py`, `syntax_registry.py`, `ini_highlighter.py` + treesitter read-only | Highlighting pipeline |
| TN-EDIT-AUX | `text_editing.py`, `quick_open.py`, `quick_open_dialog.py` | Pure text + fuzzy open |
| TN-EDIT-SHELL-TAB | `editor_tab_workflow.py`, `editor_tab_bar.py` | 1k+ tab lifecycle + poll |
| TN-EDIT-SHELL-FACTORY | `editor_tab_factory.py`, `editor_tabs_coordinator.py`, `editor_workspace_controller.py`, session/sync workflows | Materialization + AD-018 |
| TN-EDIT-SHELL-INTEL | `editor_intelligence_controller.py`, completion/inline/stale-result workflows, `semantic_navigation_workflow` editor paths | Session routing |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-EDIT-INTEG | Dedupe cross-cutting themes → `CC-EDIT-01…`; map to R3/R4 fix waves |

---

## Test coverage gaps (critics must validate)

| Module / behavior | Dedicated tests | Gap severity |
|-------------------|-----------------|--------------|
| `code_editor_semantics.py` completion accept/trigger | `test_semantic_editor_interactions.py` (partial) | **High** |
| `editor_tab_workflow.py` poll/outline | `test_editor_tab_workflow_inventory.py` (inventory only) | **High** |
| `completion_popup/` tier headers | `test_completion_item_model.py`, `test_completion_kind_style.py` | **High** |
| `search_panel.py` exclude/cancel | `test_search_panel.py` | Medium |
| `editor_manager.py` dirty/dedupe | `test_editor_manager.py` | Low–Medium |
| `syntax_registry.py` / tree-sitter | `test_syntax_highlighters.py`, `test_code_editor_widget_highlighting.py` | Medium |
| `editor_completion_workflow` | `test_editor_completion_workflow.py` | **High** |
| `editor_stale_result_policy` | `test_editor_stale_result_policy.py` | Medium |

---

## Prior wave cross-read

| Theme | Status at kickoff |
|-------|-------------------|
| TN-INT-SHELL-EDITORS (10 findings) | Re-validate — prefix/accept/outline/factory closures |
| TN-PROJ-SHELL poll/signature (CC-PROJ-13) | Re-validate — `editor_tab_workflow` enumeration |
| Intelligence CC-02 flat tier merge | Re-validate at popup boundary |
| Intelligence CC-06 `semantic_navigation_workflow` 1k+ | **Partially fixed** — now 132 LOC; debt moved to `editor_tab_workflow` |
| Intelligence CC-10 shell decomposition | Re-validate factory + tab workflow |
| Project CC-PROJ-03 snapshot orchestration | Open — poll still independent walk |

---

## Out of scope

- Fix commits, new tests, pyright fixes
- Full `app/intelligence/` re-review
- Full `app/project/` SSOT implementation (except search/poll call sites)
- Full `app/treesitter/` package (SYNTAX critic read-only cross-read)
- `app/shell/icon_provider.py` (1,106 LOC)
- R6 test audit, R7 out-of-scope audit
- `bundled_plugins/`, launchers, packaging

---

## Artifact layout

```text
docs/code review/editors-wave-1/
├── 00-manifest.md
├── editors_wave_1_thermo_review_2026-06-17.md
├── editors_wave_1_remediation_plan.md
├── editors_wave_1_implementation_plan.md
└── _findings/
    ├── _README.md
    ├── TN-EDIT-CORE.md … TN-EDIT-SHELL-INTEL.md
    └── TN-EDIT-INTEG.md
```
