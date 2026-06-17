# TN-SHELL2-EDITOR-SEAM — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-EDITOR-SEAM  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `app/shell/editor_tab_workflow.py` (101 LOC), `editor_tab_*` sub-workflows (factory, mixins, bindings, buffer, lifecycle, markdown, outline, poll, preferences), `editor_tabs_coordinator.py`, `editor_tab_content_registry.py`, `markdown_tab_registry.py`, `main_window_editor_tab_host.py`. Cross-read: `project_tree_ui_workflow.py`, `shell_composition.py`, `main_window_composition.py`. Re-validate Editors Wave 2 **CC-EDIT-01**, **CC-EDIT-07**, **CC-EDIT-10**, **CC-EDIT-17** and Shell Wave 2 cross-wave gate 8.

---

## Executive verdict

**REJECT — shell editor-tab seam is not thermo-clean.** Editors Wave 1/2 decomposition **succeeded at the façade** (`editor_tab_workflow.py` 101 LOC vs 1,013 LOC pre-Wave 1) and **Editors Wave 2 ACCEPT gates hold with no regression** (CC-EDIT-17 grep gate, rename unwrap, poll orchestrator consumer). Delta vs baseline is small (+27 LOC `EditorTabContentRegistry`, +6 LOC `on_unwrap`, +18 LOC `replace_tab_content_widget`) and does not reintroduce god-module growth. Dominant shell-side debt: **registry seam is nominal not canonical** (three `MarkdownTabRegistry` construction sites, pass-through `EditorTabContentRegistry` that re-instantiates on every call), **coordinator ↔ workflow circular coupling** (`EditorTabsCoordinator` calls back into `window._editor_tab_workflow`), and **218 LOC mixin delegate graph typed with `Any`**. Positive keepers: poll tiering in `EditorTabPollWorkflow` (125 LOC), typed sub-protocols in `editor_tab_host_protocols.py`, rename md→non-md unwrap path wired through `on_unwrap` + `replace_tab_content_widget`. Risk: new tab/markdown hooks will land as more host pass-throughs or ad-hoc registry construction instead of extending one composition-owned seam.

---

## Editors Wave 2 ACCEPT gate verification

| Gate | Wave 2 requirement | Status @ HEAD | Evidence |
|------|-------------------|---------------|----------|
| **CC-EDIT-01** | `editor_tab_workflow.py` ≤ 200 LOC | **PASS (closed)** | `wc -l` → 101; façade + factory + 6 sub-workflows |
| **CC-EDIT-17** | Composition-level tab registry SSOT | **PASS (closed, shell fragmentation residual)** | `EditorTabContentRegistry`; `rg '_markdown_panes_by_path' app/shell/` → `main_window_composition.py` init + `editor_tab_content_registry.py` only |
| **CC-EDIT-17 rename** | md→non-md unwrap + tab reparent | **PASS** | `markdown_tab_registry.rekey_for_widget(..., on_unwrap=...)`; `project_tree_ui_workflow.update_widget_language_for_path` → `replace_tab_content_widget` |
| **CC-EDIT-10** | Poll consumes orchestrator snapshot | **PASS (partial fallback)** | `EditorTabPollWorkflow.scan_project_tree_signature` prefers `host.project_inventory_tree_signature()`; filesystem walk fallback when `None` |
| **CC-EDIT-07** | Factory intelligence closures removed | **PASS (residual Any at factory boundary)** | `editor_tab_factory.py` delegates bindings to workflow; `build_editor_tab_workflow(window: Any)` persists |
| **V0 grep** | `_markdown_panes_by_path` scoped | **PASS** | Only composition init + content registry property |
| **Unit tests** | Registry rename behavior | **PASS** | `tests/unit/shell/test_markdown_tab_registry.py`; `tests/unit/shell/test_editor_tab_workflow_inventory.py` |
| **Cross-wave regression** | Do not undo Editors thermo-clean | **NO REGRESSION** | Wave 2 closure report gates still satisfied @ `fccb611` |

**Editors Wave 2 cross-wave verdict:** **ACCEPT gates preserved.** Shell-side seam quality is a separate bar — fails thermo-clean below.

---

## CC re-validation summary

| CC | Theme | Status @ HEAD | Evidence |
|----|-------|---------------|----------|
| **CC-EDIT-01** | Tab workflow god module | **CLOSED** | 101 LOC façade; sub-workflows own outline/markdown/poll/lifecycle/buffer/prefs |
| **CC-EDIT-07** | Factory closure sprawl | **CLOSED (residual Any)** | Factory delegates to workflow; builder still `window: Any` |
| **CC-EDIT-10** | Poll ↔ orchestrator | **CLOSED (filesystem fallback residual)** | Poll host routes through orchestrator; fallback scan when signature `None` |
| **CC-EDIT-17** | Markdown dual-registry | **CLOSED (seam not fully canonical)** | `EditorTabContentRegistry` exists; callers still construct `MarkdownTabRegistry` ad hoc |

---

### TN-SHELL2-EDITOR-SEAM-1 — `EditorTabContentRegistry` is a pass-through wrapper that re-instantiates on every access

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** NEW (delta @ baseline)
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_content_registry.py:20-24` — `markdown_registry()` returns `MarkdownTabRegistry(self._markdown_panes_by_path)` on each call; `apply_all_markdown_themes` calls `markdown_registry()` again. No caching, no methods beyond dict passthrough + theme fan-out.
- **Code-judo alternative:** Either **delete the wrapper** and expose `MarkdownTabRegistry` once at composition init (single instance on `window._tab_content_registry`), or make `EditorTabContentRegistry` **own** the registry instance (`self._markdown_registry = MarkdownTabRegistry(...)`) and expose it as a property — one object, one API surface for register/rekey/release/theme.
- **Suggested remediation:** Composition assigns `window._tab_content_registry = EditorTabContentRegistry(...)` with internal single `MarkdownTabRegistry`; factory and project-tree call `host.tab_content_registry().markdown_registry` without constructing new wrappers.
- **Tests that would prove fix:** Unit test asserting `markdown_registry()` identity is stable across calls; grep gate `MarkdownTabRegistry(` → composition/factory only.
- **Handoff overlap:** CC-EDIT-17, Editors EDIT-R2-07, R2-08

---

### TN-SHELL2-EDITOR-SEAM-2 — Three `MarkdownTabRegistry` construction sites fragment CC-EDIT-17 SSOT

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `rg 'MarkdownTabRegistry\(' app/shell/` → `editor_tab_workflow_factory.py:49`, `editor_tab_content_registry.py:21`, `project_tree_ui_workflow.py:371`. All share the same dict via host/composition, but each site is an independent construction path — `project_tree_ui_workflow.release_editor_widget` bypasses `tab_content_registry()` entirely.
- **Code-judo alternative:** **One registry instance** wired at composition; all shell modules receive it via host protocol (`tab_content_registry().registry`) — zero `MarkdownTabRegistry(` outside composition + factory wiring.
- **Suggested remediation:** Hard cutover per EDIT-R2-08: route `project_tree_ui_workflow.release_editor_widget` through `tab_content_registry().markdown_registry()`; delete direct `MarkdownTabRegistry(...)` in tree workflow.
- **Tests that would prove fix:** `rg 'MarkdownTabRegistry\(' app/shell/` → ≤2 hits (composition + test doubles); existing `test_markdown_tab_registry.py` stays green.
- **Handoff overlap:** CC-EDIT-17, CC-SHELL2-typed-hosts (INTEG)

---

### TN-SHELL2-EDITOR-SEAM-3 — `EditorTabsCoordinator` ↔ `EditorTabWorkflow` circular coupling inverts layering

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tabs_coordinator.py:35-36,72,80` — coordinator methods call `window._editor_tab_workflow.tab_index_for_path`, `.refresh_tab_presentation`, `.promote_preview_tab` while workflow delegates tab chrome back to coordinator (`editor_tab_workflow_mixins.py:116-126`). L2 coordinator depends on L1 façade via `window._*` back-edge.
- **Code-judo alternative:** Coordinator becomes **pure Qt chrome** (tab index lookup, label/tooltip mutate, widget swap) with **no workflow imports**. Preview promotion and presentation refresh move entirely into `EditorTabLifecycleWorkflow` / buffer workflow — coordinator exposes only `tab_index_for_path`, `set_tab_label`, `replace_widget_at_index`.
- **Suggested remediation:** Remove `_editor_tab_workflow` references from coordinator; pass `tab_index_for_path` callable at construction or inject coordinator into lifecycle only (one direction).
- **Tests that would prove fix:** Unit test constructing `EditorTabsCoordinator` with fake window lacking `_editor_tab_workflow`; coordinator methods succeed without workflow attribute.
- **Handoff overlap:** CC-EDIT-01, CC-06, R2

---

### TN-SHELL2-EDITOR-SEAM-4 — 218 LOC mixin delegate graph hides real API behind `Any`-typed sub-workflows

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow_mixins.py:16-17,47-48,83-85,109-111,151-154,195-196` — six mixin classes declare `_outline_workflow: Any`, `_markdown_workflow: Any`, etc.; 40+ one-line passthrough methods. `wrap_tab_content_if_markdown` delegate uses `parent: Any, theme_tokens: Any, open_linked_file: Any` (`:71-73`) despite concrete types in `EditorTabMarkdownWorkflow`.
- **Code-judo alternative:** **Drop mixins** — expose sub-workflows as public read-only properties on `EditorTabWorkflow` (`workflow.outline`, `workflow.poll`) and update callers to use sub-workflows directly; or use `@property` delegates with typed return protocols instead of mixin inheritance. Deletes 218 LOC of ceremony.
- **Suggested remediation:** Phase 1: type mixin fields with concrete workflow classes. Phase 2: collapse to properties when caller count is low enough.
- **Tests that would prove fix:** pyright on `editor_tab_workflow_mixins.py` with zero `Any` workflow fields; no behavior change in shell unit tests.
- **Handoff overlap:** CC-07, CC-EDIT-01, CC-SHELL2-typed-hosts (INTEG)

---

### TN-SHELL2-EDITOR-SEAM-5 — `build_editor_tab_workflow(window: Any)` preserves untyped composition boundary

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_workflow.py:88-98` — factory reads `window._editor_manager`, `_save_workflow`, `_debug_control_workflow` without protocol; constructor accepts `save_workflow: Any`, `debug_control_workflow: Any`, `editor_sync_workflow: Any` (`:42-45`). `MainWindowEditorTabHost.__init__(self, window: Any)` at `main_window_editor_tab_host.py:19` — 234 LOC pass-through host.
- **Code-judo alternative:** Introduce **`EditorTabCompositionPorts` Protocol** (manager, coordinator, save, debug, sync, tab widget refs) passed to `build_editor_tab_workflow(ports)` — same pattern as `SettingsApplyWorkflow` fake hosts in unit tests.
- **Suggested remediation:** Extract minimal port bundle from `MainWindowEditorTabHost`; type `build_editor_tab_workflow` parameter; shrink host to protocol implementation only.
- **Tests that would prove fix:** Construct `EditorTabWorkflow` from stub ports without `MainWindow` import (extend `test_editor_tab_workflow_inventory.py` pattern).
- **Handoff overlap:** CC-07, CC-06, TN-SHELL2-COMP-2

---

### TN-SHELL2-EDITOR-SEAM-6 — Inline import in preferences delegate violates repo import rule

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tab_workflow_mixins.py:166` — `from app.shell.editor_latency_recorder import attach_editor_latency_recorder` inside `apply_runtime_intelligence_preferences_to_editor`. Repo rule `no-inline-imports.mdc` requires top-of-module imports unless documented circular-dep exception (none documented).
- **Code-judo alternative:** Move latency attachment into `EditorTabPreferencesWorkflow` where other preference application lives — delete cross-mixin intelligence hook entirely.
- **Suggested remediation:** Top-level import + delegate to preferences sub-workflow, or relocate method body to `editor_tab_preferences_workflow.py`.
- **Tests that would prove fix:** Lint/rule pass; existing preferences tests unchanged.
- **Handoff overlap:** none

---

### TN-SHELL2-EDITOR-SEAM-7 — `rekey_for_widget` optional `on_unwrap` leaves silent tab-orphan path

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** NEW (delta `@ baseline` adds branch)
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/markdown_tab_registry.py:47-54` — when `not is_markdown_path(new_path)` and `on_unwrap is None`, code calls `markdown_pane.deleteLater()` without reparenting `source_editor()` into the tab slot. Production path passes `on_unwrap` (`project_tree_ui_workflow.py:389-396`), but API allows callers to orphan tab content.
- **Code-judo alternative:** Make **`on_unwrap` required** when transitioning off markdown paths, or move unwrap+reparent into registry as default behavior using an injected `replace_tab_content: Callable[[str, QWidget], None]` — delete the `else: deleteLater()` silent path.
- **Suggested remediation:** Require `on_unwrap` when `not is_markdown_path(new_path)` (raise `ValueError` if missing); document contract on `MarkdownTabRegistry.rekey_for_widget`.
- **Tests that would prove fix:** Unit test asserting `rekey_for_widget` without `on_unwrap` on md→non-md raises; production call sites unchanged.
- **Handoff overlap:** CC-EDIT-17, Editors TN-EDIT-MD-2

---

### TN-SHELL2-EDITOR-SEAM-8 — Poll filesystem fallback bypasses orchestrator when tree signature is `None`

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tab_poll_workflow.py:107-122` — after `project_inventory_tree_signature()` returns `None`, falls back to `iter_project_entries` + `filter_tree_signature_entries`. CC-EDIT-10 closed orchestrator consumer path, but fallback duplicates inventory logic and bypasses generation-gated snapshot.
- **Code-judo alternative:** **Delete fallback** — poll host must always return orchestrator signature when project loaded; if orchestrator not ready, skip compare tier (same as stable-signature early return) instead of rescanning disk independently.
- **Suggested remediation:** Assert orchestrator signature non-`None` after project open; remove lines 111-122 or gate behind explicit "orchestrator unavailable" skip.
- **Tests that would prove fix:** Extend `test_editor_tab_workflow_inventory.py` — when orchestrator returns `None`, poll does not call `iter_project_entries`.
- **Handoff overlap:** CC-EDIT-10, CC-PROJ-03, TN-SHELL2-PROJECT

---

### TN-SHELL2-EDITOR-SEAM-9 — CC-EDIT-01 CLOSED: 101 LOC façade with focused sub-workflows (keeper)

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL (closed theme — positive)
- **Severity:** NICE-TO-HAVE
- **Evidence:** `editor_tab_workflow.py` 101 LOC; sub-workflows: poll 125, markdown 152, lifecycle 192, outline 199, buffer 116, preferences 160, bindings 122, factory 105. Wave 1 reduced 1,013 LOC monolith; Wave 2 did not regress LOC budget.
- **Code-judo alternative:** Maintain ≤150 LOC façade gate in AD-015; new tab behavior lands in sub-workflows only.
- **Suggested remediation:** None — preserve as template for other shell workflow clusters.
- **Tests that would prove fix:** CI `wc -l app/shell/editor_tab_workflow.py` ≤ 200.
- **Handoff overlap:** CC-EDIT-01, AD-015

---

### TN-SHELL2-EDITOR-SEAM-10 — CC-EDIT-17 rename unwrap path wired correctly (keeper)

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** NEW (delta @ baseline)
- **Severity:** NICE-TO-HAVE
- **Evidence:** `project_tree_ui_workflow.py:385-397` — `on_unwrap` calls `editor_tabs_coordinator().replace_tab_content_widget(normalized_path, source_editor)`; `editor_tabs_coordinator.py:48-64` preserves label/tooltip/index. `test_markdown_tab_registry.py::test_rekey_from_markdown_to_non_markdown_unwraps_pane` documents contract.
- **Code-judo alternative:** Fold `replace_tab_content_widget` into registry default unwrap callback supplied at composition — single rename pipeline.
- **Suggested remediation:** Optional consolidation with TN-SHELL2-EDITOR-SEAM-7; behavior is correct today.
- **Tests that would prove fix:** Existing unit test green; manual AT markdown rename scenario.
- **Handoff overlap:** CC-EDIT-17, Editors Wave 2 ACCEPT

---

### TN-SHELL2-EDITOR-SEAM-11 — `replace_tab_content_widget` uses untyped `object` and duplicates tab-bar surgery

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** NEW (delta @ baseline)
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/editor_tabs_coordinator.py:48-64` — `new_widget: object`; removeTab/insertTab/setToolTip/setCurrentIndex pattern mirrors tab open paths in `editor_tab_factory.py` without shared helper.
- **Code-judo alternative:** Typed `QWidget` parameter; extract **`replace_tab_widget_at_index(tabs, index, widget)`** helper shared with factory materialization to prevent label/tooltip drift on future tab mutations.
- **Suggested remediation:** Type annotation + shared Qt tab chrome helper under `editor_tab_bar.py` or coordinator private method reused by factory.
- **Tests that would prove fix:** Unit test on coordinator widget swap preserves tooltip and current index.
- **Handoff overlap:** CC-EDIT-17

---

### TN-SHELL2-EDITOR-SEAM-12 — `EditorTabMarkdownHost` still exposes raw dict; registry seam incomplete at protocol layer

- **Persona:** TN-SHELL2-EDITOR-SEAM
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_host_protocols.py:121-122` — `markdown_panes_by_path() -> dict[str, MarkdownEditorPane]` on protocol; `main_window_editor_tab_host.py:31-35` routes through `_tab_content_registry.markdown_panes_by_path` but protocol has no `tab_content_registry()` — project tree host adds it separately (`project_tree_ui_workflow.py` host protocol). Factory still reads dict directly (`editor_tab_workflow_factory.py:49`).
- **Code-judo alternative:** Protocol exposes **`markdown_registry() -> MarkdownTabRegistry`** only; delete dict from public host surface — forces all mutations through registry API.
- **Suggested remediation:** Deprecate `markdown_panes_by_path()` on `EditorTabMarkdownHost`; add `tab_content_registry()` to composite host protocol with typed return.
- **Tests that would prove fix:** pyright on host implementations; grep `markdown_panes_by_path()` call sites → zero outside registry module.
- **Handoff overlap:** CC-EDIT-17, CC-SHELL2-typed-hosts (INTEG)

---

## Approval summary

| Bar | Result |
|-----|--------|
| Editors Wave 2 ACCEPT gates | **PASS — no regression** |
| Shell editor-tab seam thermo-clean | **FAIL** |
| Structural regression in delta | **None** — delta is additive seam polish |
| 1k-line rule | **PASS** — largest file in cluster `editor_tab_host_protocols.py` 234 LOC |
| Cross-wave gate 8 | **PASS** — CC-EDIT-01/10/17 closed; CC-EDIT-07 closed with residual `Any` |

**Final verdict: REJECT** for Shell Wave 2 thermo-clean on the editor-tab seam slice. **Editors Wave 2 ACCEPT remains valid** — do not reopen Editors closure. Remediation belongs in Shell Wave 2 R2: canonicalize `EditorTabContentRegistry`, eliminate ad-hoc `MarkdownTabRegistry(` construction, break coordinator↔workflow cycle, and tighten host/registry protocols before adding new tab features.
