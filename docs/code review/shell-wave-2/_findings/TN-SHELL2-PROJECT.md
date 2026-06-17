# TN-SHELL2-PROJECT — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-PROJECT  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**HEAD reviewed:** `430c56796089a8d25b082c44e1afa78e9a14d4ac` (delta: `project_tree_ui_workflow.py` only in this slice)  
**Scope:** `project_load_workflow.py` (116 LOC), `project_rescan_workflow.py` (145), `project_inventory_orchestrator.py` (71), `project_tree_ui_workflow.py` (652), `project_tree_action_coordinator.py` (240), `save_workflow.py` (329), `external_file_change_workflow.py` (234). Cross-read: `project_load_host.py`, `project_load_surface.py`, `project_tree_action_workflow.py`, `editor_tab_poll_workflow.py`. Re-validate Shell Wave 1 **CC-03**, **CC-11**, **CC-16** and Project SSOT **CC-PROJ-03**.

---

## Executive verdict

**REJECT — project orchestration is not thermo-clean.** Shell Wave 1 extractions **landed the right seams**: typed `ProjectLoadWorkflow`, delete-safe `ProjectTreeActionWorkflow`, well-ported `ExternalFileChangeWorkflow`, and a focused `ProjectInventoryOrchestrator` (71 LOC). **CC-03 (document safety) remains CLOSED** with no regression. Dominant debt: **CC-16** — every tree filesystem mutation still triggers a **full project rescan** via `_reload_project()`; **CC-PROJ-03** — orchestrator is wired to open/save/rescan consumers but **poll still performs an independent `iter_project_entries` walk** when the orchestrator signature is absent, and **rescan couples inventory rebuild to search-sidebar configuration** while `open_project` + `rebuild` double-walk the tree; **CC-11** — load phases exist but **`project_load_surface.py` remains an untyped `window: Any` mutation block** hosting intelligence/lint/plugin fan-out. **SaveWorkflow** is still the shell’s **sole `window: Any` workflow** (~35 private field touches) on the document-safety critical path. **No BLOCKER** in this slice, but structural findings block thermo-clean approval.

---

## CC re-validation summary

| CC | Wave 1 / SSOT theme | Status @ HEAD | Evidence |
|----|---------------------|---------------|----------|
| **CC-03** | Document safety gaps vs SaveWorkflow (tree delete, external reload, decline-reload) | **CLOSED** | Tree delete: `project_tree_action_workflow.py:72-74,91-96` → `confirm_proceed_before_tree_delete` before coordinator. External reload: `external_file_change_workflow.py:179-184` → `SaveWorkflowPort` + `DocumentScope.EXTERNAL_RELOAD`. Decline: `:144-146,186-187,233-234` → `acknowledge_disk_mtime`, no dirty-tab clobber. Tests: `test_save_workflow.py`, `test_external_file_change_workflow.py`, `test_project_tree_action_workflow.py`. |
| **CC-11** | Project load / settings-apply mega-orchestrators | **PARTIAL** | `ProjectLoadWorkflow` (116 LOC) + typed `ProjectLoadHost` extract phase boundaries (`project_load_workflow.py:51-116`). Residual: `project_load_surface.py:14-89` — untyped `apply_project_surface` / `finalize_project_open` still mutate 15+ `window._*` fields, run plugin reload, intelligence reindex, test discovery in one imperative block. Host adapter delegates straight through (`project_load_host.py:44-66`). |
| **CC-16** | Project tree: no action workflow; full reload cascade | **PARTIAL** | **Closed:** `ProjectTreeActionWorkflow` owns delete confirmation + history (`project_tree_action_workflow.py:50-111`); UI delegates delete to workflow (`project_tree_ui_workflow.py:327-337`). **Open:** `ProjectTreeActionCoordinator` calls `_reload_project()` after **every** FS op (`project_tree_action_coordinator.py:72,83,99,107,114,127,136,173,197`) → `refresh_project_tree_from_disk` → full `rescan_from_disk` (`project_tree_ui_workflow.py:474-478`). No tiered refresh. Clipboard still on MainWindow via host ports (`project_tree_ui_workflow.py:592-602`). |
| **CC-PROJ-03** | Shared `ProjectInventorySnapshot` orchestration; one walk per generation | **PARTIAL** | **Closed at shell boundary:** `ProjectInventoryOrchestrator` (71 LOC) owns generation + snapshot (`project_inventory_orchestrator.py:20-71`); injected on save (`save_workflow.py:214-216`), finalize open (`project_load_surface.py:62-73`), rescan reindex (`project_rescan_workflow.py:77-80`). **Open:** poll fallback walk (`editor_tab_poll_workflow.py:107-122`); orchestrator `rebuild` gated inside `configure_search_sidebar` (`project_rescan_workflow.py:103-114`, `project_load_surface.py:42-52`); rescan = `open_project` enumerate + orchestrator `rebuild` second walk (`project_rescan_workflow.py:58-62,113`). |

---

### TN-SHELL2-PROJECT-1 — CC-03 CLOSED: document-safety triad wired through SaveWorkflow + ExternalFileChangeWorkflow

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL (closure of Wave 1 CC-03)
- **Severity:** NICE-TO-HAVE (positive keeper — do not regress)
- **Evidence:** Tree delete save gate: `save_workflow.py:49-75` filters dirty tabs under delete targets; `project_tree_action_workflow.py:72-74` blocks delete on cancel. External reload: `external_file_change_workflow.py:25-39,179-210` uses `SaveWorkflowPort` with `DocumentScope.EXTERNAL_RELOAD`; dirty save-then-reload path re-reads disk. Clean-tab decline: `:144-146` acknowledges mtime without simulating buffer mutation.
- **Code-judo alternative:** Keep these seams. Any new destructive tree or disk-sync path must route through `SaveWorkflowPort` / `DocumentSafetyDecision`, not raw `QMessageBox`.
- **Suggested remediation:** None for CC-03 itself. Next: typed `SaveDocumentHost` so safety logic is testable without `MainWindow.__new__` (CC-07 joint fix).
- **Tests that would prove fix:** Existing unit tests above; manual acceptance in `docs/ACCEPTANCE_TESTS.md` for tree delete + external edit.
- **Handoff overlap:** CC-03, CC-07, TN-SHELL2-COMP-6

---

### TN-SHELL2-PROJECT-2 — CC-16 RESIDUAL: every tree FS mutation triggers full `rescan_from_disk`

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectTreeActionCoordinator` invokes `self._reload_project()` after new file, folder, rename, delete, duplicate, paste, drop (`project_tree_action_coordinator.py:72,83,99,107,114,127,136,173,197`). Composition wires `reload_project=window._project_tree_ui_workflow.refresh_project_tree_from_disk` (`main_window_composition.py:432`). That calls `rescan_from_disk()` with no tiering (`project_tree_ui_workflow.py:474-475`) → `open_project` re-enumeration + tree repopulate + search sidebar reconfigure (`project_rescan_workflow.py:49-81`). Wave 1 CC-16 flagged identical cascade from `_reload_current_project`.
- **Code-judo alternative:** **Tiered refresh policy:** (1) local tree presenter patch for single-file create/rename when signature delta is known; (2) light rescan (tree + signature only); (3) full rescan + reindex only when python file set or exclude patterns change. Coordinator takes `RefreshTier` enum instead of blind `reload_project()`.
- **Suggested remediation:** R2 wave-5: characterize refresh tiers with spy tests; default new/rename/delete to light path; reserve full rescan for poll-detected external changes and explicit Refresh button.
- **Tests that would prove fix:** Spy: `handle_new_file` → zero `open_project` when tree patch suffices; integration: rename preserves expanded folder state without plugin reload.
- **Handoff overlap:** CC-16, CC-PROJ-03, R2

---

### TN-SHELL2-PROJECT-3 — CC-11 PARTIAL: `ProjectLoadWorkflow` phases exist; surface mutations stay imperative

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Orchestrator class is clean (`project_load_workflow.py:51-116` — prepare → enumerate → surface → session → finalize with telemetry). Host is thin adapter (`project_load_host.py:13-66`). But `apply_project_surface` / `finalize_project_open` remain **89 lines of untyped `window: Any` side effects** (`project_load_surface.py:14-89`): plugin reload, lint clear, search sidebar, orchestrator rebuild, intelligence reindex, test discovery, event bus — same mega-orchestrator shape Wave 1 MW-05 flagged, only renamed.
- **Code-judo alternative:** Split surface into **phase handlers** mirroring workflow steps: `ProjectSurfaceApplier`, `ProjectOpenFinalizer` with typed ports (same pattern as `ExternalFileChangeWorkflow`). `ProjectLoadHost` implements ports; delete `project_load_surface.py` free functions.
- **Suggested remediation:** R2 wave-4 continuation after SaveWorkflow host extraction; move intelligence/test fan-out out of finalize into subscribed `ProjectOpenedEvent` handlers.
- **Tests that would prove fix:** Unit test constructs `ProjectLoadWorkflow` with fake host recording phase call order; integration: open project B after A without duplicate plugin reload.
- **Handoff overlap:** CC-11, CC-06, R2, R4

---

### TN-SHELL2-PROJECT-4 — CC-PROJ-03 PARTIAL: orchestrator rebuild coupled to search-sidebar presence

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectInventoryOrchestrator.rebuild` is invoked only inside `if window._search_sidebar is not None` on open (`project_load_surface.py:42-52`) and rescan configure path (`project_rescan_workflow.py:103-114`). Inventory SSOT is **logically independent** of search UI widget lifetime. Today search sidebar is always constructed (`main_window_panels.py:100`), but the coupling is a latent footgun and violates architecture gate 7 (“orchestrator sole owner”).
- **Code-judo alternative:** **`rebuild_project_inventory(project, effective_excludes)`** callable from open, rescan, exclude-change, and poll — never nested under search-sidebar setup. Search sidebar reads orchestrator snapshot; does not gate its creation.
- **Suggested remediation:** Extract inventory rebuild to `ProjectRescanWorkflow` / `ProjectLoadHost` directly; `configure_search_sidebar` only consumes snapshot + exclude list.
- **Tests that would prove fix:** Unit test: rescan with `search_sidebar=None` stub host still increments orchestrator generation exactly once.
- **Handoff overlap:** CC-PROJ-03, CC-11, architecture gate 7

---

### TN-SHELL2-PROJECT-5 — CC-PROJ-03 PARTIAL: poll retains independent `iter_project_entries` fallback walk

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `EditorTabPollWorkflow.scan_project_tree_signature` prefers orchestrator signature (`editor_tab_poll_workflow.py:108-110`) but falls back to full disk walk via `iter_project_entries` (`:111-122`) when orchestrator signature is `None`. Poll tick can therefore **bypass** `ProjectInventoryOrchestrator` and duplicate exclude logic on hot timer path. Editors Wave 2 TN-EDIT-SHELL-TAB flagged same seam (“poll/signature do not consume orchestrator”).
- **Code-judo alternative:** **Hard cutover:** poll never walks disk for signature; if orchestrator signature missing, trigger one `orchestrator.rebuild` (or defer rescan) and use stored signature. Delete fallback branch.
- **Suggested remediation:** Wave 6b wire-only PR: remove `iter_project_entries` import from poll workflow; assert orchestrator signature set on every project open/rescan path.
- **Tests that would prove fix:** Extend `test_inventory_orchestration.py` spy: poll tick with seeded orchestrator → zero entry walks.
- **Handoff overlap:** CC-PROJ-03, CC-PROJ-13, TN-SHELL2-EDITOR-SEAM, architecture gate 7

---

### TN-SHELL2-PROJECT-6 — CC-PROJ-03: rescan double-walks disk (`open_project` + orchestrator `rebuild`)

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `ProjectRescanWorkflow.rescan_from_disk` calls `open_project` to refresh `LoadedProject.entries` (`project_rescan_workflow.py:58-62`), then `configure_search_sidebar` calls `orchestrator.rebuild` → `build_project_inventory_snapshot` (`:113`, `project_inventory_orchestrator.py:31-34`). Two full tree walks per rescan event. Project SSOT Wave 1 CC-PROJ-03 acceptance criterion: **one walk per generation**.
- **Code-judo alternative:** Derive inventory snapshot from `LoadedProject.entries` when rescan source is `open_project` (adapter in `app/project/file_inventory.py`); or make `open_project` return/cache snapshot reference consumed by orchestrator without second walk.
- **Suggested remediation:** R4 follow-up: add `build_snapshot_from_loaded_entries(loaded_project, excludes)` fast path; orchestrator `rebuild_from_loaded` used by rescan.
- **Tests that would prove fix:** Spy on `build_project_inventory_snapshot`: single call per `rescan_from_disk` invocation.
- **Handoff overlap:** CC-PROJ-03, CC-16, R4

---

### TN-SHELL2-PROJECT-7 — SaveWorkflow remains sole `window: Any` workflow on document-safety path

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `SaveWorkflow.__init__(self, window: Any)` (`save_workflow.py:38-39`). `rg "window\._" app/shell/save_workflow.py` → **35** private field touches across save, autosave, tree-delete gate, intelligence reindex side effects. Contrast: `ExternalFileChangeWorkflow` depends on typed ports (`external_file_change_workflow.py:25-102`). Manifest P1: SaveWorkflow is **sole untyped `*Workflow` class**.
- **Code-judo alternative:** **`SaveDocumentHost` protocol** — `editor_manager`, `local_history`, `dialog_parent`, `project_rescan`, `intelligence_cache`, dirty-tab enumerator — mirror `ExternalFileChangeHostPorts` inversion already proven in this slice.
- **Suggested remediation:** Prioritize in R2 wave-4 before adding save-time side effects; composition passes narrow host from `shell_composition.py`.
- **Tests that would prove fix:** Refactor `test_save_workflow.py` to stub host only; zero `MainWindow` import.
- **Handoff overlap:** CC-07, CC-03, TN-SHELL2-COMP-6, architecture gate 3

---

### TN-SHELL2-PROJECT-8 — `project_tree_ui_workflow.py` at 652 LOC: emerging hotspot

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** 652 LOC merges explorer UI handlers, keyboard shortcuts, import-rewrite policy UI (`:406-472`), entry-point manifest mutation (`:489-529`), editor widget release, and rescan triggers. `ProjectTreeUiWorkflowHost` declares **15+ `Any` ports** (`:27-136`). Approaches manifest ≥700 LOC watch list (`local_history_workflow` 674 at kickoff).
- **Code-judo alternative:** Split: `project_tree_explorer_handlers.py` (sidebar + preview clicks), `project_tree_import_policy_workflow.py` (ASK/ALWAYS/NEVER dialogs), `project_tree_entry_point_workflow.py` (manifest default entry). Host protocol shrinks per submodule.
- **Suggested remediation:** Decompose before next tree feature; cap file at 500 LOC in AD-015 gate extension for workflows.
- **Tests that would prove fix:** Existing tree tests stay green per extracted module; no single file >700 LOC in project-tree cluster.
- **Handoff overlap:** CC-16, CC-21, R3

---

### TN-SHELL2-PROJECT-9 — Editors Wave 2 delta: dual markdown registry paths in same workflow

- **Persona:** TN-SHELL2-PROJECT
- **Status:** NEW (delta @ `430c567` vs `fccb611`)
- **Severity:** STRUCTURAL
- **Evidence:** `update_widget_language_for_path` migrated to `tab_content_registry().markdown_registry().rekey_for_widget` with `on_unwrap` callback (`project_tree_ui_workflow.py:385-397`, diff vs baseline). `release_editor_widget` still constructs standalone `MarkdownTabRegistry(self._host.markdown_panes_by_path())` (`:370-377`). Two registry access patterns in one workflow; host exposes both `markdown_panes_by_path()` and `tab_content_registry()` (`:99-106,610-617`).
- **Code-judo alternative:** Single **`TabContentRegistryPort`** on host; delete direct `markdown_panes_by_path` from protocol. Both release and rekey call `registry.markdown_registry()`.
- **Suggested remediation:** Hard cutover in Editors Wave 2 follow-up; remove `MarkdownTabRegistry` import from UI workflow once release path migrated.
- **Tests that would prove fix:** Rename/move markdown tab: rekey + unwrap + release all route through registry spy.
- **Handoff overlap:** CC-PROJ-03, Editors CC-EDIT-*, TN-SHELL2-EDITOR-SEAM

---

### TN-SHELL2-PROJECT-10 — Tree structure signature duplicated on MainWindow and orchestrator

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `window._project_tree_structure_signature` set on open (`project_load_surface.py:34-38`), rescan (`project_rescan_workflow.py:116-118`), and poll (`editor_tab_poll_workflow.py:93-97`). Orchestrator stores parallel copy via `set_tree_structure_signature` (`project_inventory_orchestrator.py:47-52`). Poll compares against host signature while orchestrator also holds copy — two SSOTs for same tuple.
- **Code-judo alternative:** **Orchestrator-only signature** — host reads `orchestrator.tree_structure_signature()`; delete `window._project_tree_structure_signature` field.
- **Suggested remediation:** Small hard cutover after CC-PROJ-03 poll fix; update `MainWindowEditorTabHost` to delegate exclusively to orchestrator.
- **Tests that would prove fix:** Poll/rescan tests assert single storage location; no drift between window field and orchestrator.
- **Handoff overlap:** CC-PROJ-03, CC-16

---

### TN-SHELL2-PROJECT-11 — Positive keeper: `ExternalFileChangeWorkflow` is the target port-inversion shape

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL (closure pattern)
- **Severity:** NICE-TO-HAVE (positive keeper)
- **Evidence:** `external_file_change_workflow.py:84-102` — constructor takes `EditorManager`, `EditorSyncWorkflow`, `SaveWorkflowPort`, `LocalHistoryPort`, `ExternalFileChangeHostPorts`; no `window: Any`. Outcome enum models all branches (`:15-22`). `_DirtyReloadPlan` dataclass isolates dirty-path logic (`:75-234`). **12** dedicated unit tests in `test_external_file_change_workflow.py`.
- **Code-judo alternative:** Use as template for `SaveWorkflow`, `ProjectTreeUiWorkflow` host extraction, and `ProjectLoadWorkflow` surface finalizer ports.
- **Suggested remediation:** Document in ARCHITECTURE §shell as reference workflow; new shell workflows must not ship with raw `window: Any`.
- **Tests that would prove fix:** Pattern replication tests (host stub only) for migrated workflows.
- **Handoff overlap:** CC-03, CC-07, architecture gate 3

---

### TN-SHELL2-PROJECT-12 — Inline import in `MainWindowProjectRescanHost.configure_search_sidebar`

- **Persona:** TN-SHELL2-PROJECT
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `project_rescan_workflow.py:106` — `from app.shell.project_tree_utils import effective_excludes_for` inside method body despite module-level import of `effective_excludes_for` at `:10`. Violates repo no-inline-imports rule; suggests copy-paste during R4 wiring.
- **Code-judo alternative:** Delete inner import; use top-level symbol already imported.
- **Suggested remediation:** One-line fix in next touch of rescan workflow (out of scope for document-only wave).
- **Tests that would prove fix:** Lint/import-order check; no behavior change.
- **Handoff overlap:** none

---

## Approval checklist (this slice)

| Gate | Result |
|------|--------|
| CC-03 document safety | **PASS** — CLOSED, no regression |
| CC-11 load orchestration | **PARTIAL** — phases extracted, surface imperative |
| CC-16 tree action / refresh | **PARTIAL** — delete workflow closed; full rescan cascade open |
| CC-PROJ-03 inventory SSOT | **PARTIAL** — orchestrator exists; poll fallback + double walk |
| No file >1k in slice | **PASS** (max 652 LOC) |
| Typed host ports | **FAIL** — SaveWorkflow + tree UI host `Any` |
| Hard-cutover bias | **PARTIAL** — markdown registry dual path (delta) |

**Verdict: REJECT** — ship-blocking document safety is sound, but tiered tree refresh, inventory walk consolidation, and SaveWorkflow typing must land before this cluster is thermo-clean.

---

## Suggested fix-wave ordering

1. **P1:** Decouple orchestrator rebuild from search sidebar; remove poll `iter_project_entries` fallback (CC-PROJ-03).
2. **P1:** Introduce refresh tiers in `ProjectTreeActionCoordinator` (CC-16).
3. **P1:** `SaveDocumentHost` protocol extraction (CC-07 / CC-03 hardening).
4. **P2:** Split `project_tree_ui_workflow.py`; unify markdown registry access (Editors seam).
5. **P2:** Typed surface applier for project open; collapse duplicate tree signatures.

---

## Test coverage notes

| Module / behavior | Tests | Gap |
|-------------------|-------|-----|
| `ProjectInventoryOrchestrator` | `test_project_inventory_orchestrator.py`, `test_inventory_orchestration.py` | No rescan single-walk spy; no poll-orchestrator integration |
| `SaveWorkflow` tree delete gate | `test_save_workflow.py` | Uses window stub; needs host protocol refactor test |
| `ExternalFileChangeWorkflow` | `test_external_file_change_workflow.py` (12 cases) | Low gap |
| `ProjectTreeActionWorkflow` | `test_project_tree_action_workflow.py` | Low gap |
| Full rescan cascade | — | **High gap** — no spy on `open_project` count per tree op |
| `ProjectLoadWorkflow` phases | — | **Medium gap** — no dedicated phase-order unit test |
