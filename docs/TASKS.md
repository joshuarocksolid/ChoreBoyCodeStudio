# ChoreBoy Code Studio — Tasks (v2)

## 1) Purpose

This file is the **execution backlog** for shipping a polished ChoreBoy Code Studio release within the constraints documented in:

1. `docs/PRD.md`
2. `docs/DISCOVERY.md`
3. `docs/ARCHITECTURE.md`
4. `docs/ACCEPTANCE_TESTS.md`
5. `AGENTS.md`

This version replaces the previous broad checklist with a **thin-slice, test-traceable plan**.

> Designer planning artifacts are tracked separately under `docs/designer/`:
> - `docs/designer/TASKS.md`
> - `docs/designer/WIREFRAME.md`
> - `docs/designer/ARCHITECTURE_PLAN.md`

---

## 2) How to use this backlog

### Status legend

- `DONE` — implemented and validated
- `PARTIAL` — foundational implementation exists, but required behavior is incomplete
- `TODO` — not started
- `BLOCKED` — cannot proceed without external decision/prerequisite

### Execution rules

1. Move one vertical slice at a time.
2. Update status immediately when a slice lands.
3. For non-trivial logic, follow red → green → refactor.
4. For UI changes, validate in **light and dark** themes.
5. No slice is complete without explicit validation evidence.

### Task card contract (required fields for new/updated tasks)

Every non-trivial task entry must explicitly include:

- `Status`
- `Objective`
- `Primary files`
- `Automated test layer` (`unit` / `integration` / `runtime_parity`)
- `Validation method` (exact command or manual evidence expectation)
- `Acceptance linkage` (`AT-*` IDs or explicit post-MVP note)
- `Release class` (`MVP-BLOCKING`, `RELEASE-CRITICAL`, `ENHANCEMENT`)
- `Depends on`
- `Done when`

---

## 3) Current implementation baseline (as of 2026-03-01)

The repository is no longer “empty scaffolding.” Core foundation work is already present.

| Area | Baseline status | Evidence |
|---|---|---|
| App skeleton / entrypoints | DONE | `run_editor.py`, `run_runner.py`, `launcher.py` exist |
| Deterministic paths | DONE | `app/bootstrap/paths.py` + unit tests |
| App logging | DONE | `app/bootstrap/logging_setup.py` + unit tests |
| Startup capability probe | DONE | `app/bootstrap/capability_probe.py` + integration wiring tests |
| Main shell scaffold | DONE | `app/shell/main_window.py`, `menus.py`, `status_bar.py` |
| Project metadata schema | DONE | `app/project/project_manifest.py`, `app/core/models.py` |
| Project open/load + structure validation | DONE | `app/project/project_service.py` |
| Recent projects persistence | DONE | `app/project/recent_projects.py` |
| Settings persistence foundation | DONE | `app/persistence/settings_store.py` |
| Runner orchestration / execution | DONE | `app/run/*` + `app/runner/*` implemented with manifest-driven execution |
| Templates / New Project | DONE | template assets + materialization service under `templates/` and `app/templates/` |
| Acceptance coverage vs MVP gate | PARTIAL | broad automated coverage exists; manual acceptance lane remains required for release |

> Baseline test signal at rewrite time: `539 passed` (cloud VM, Qt-dependent tests skipped when PySide2 shared libs unavailable).

---

## 4) Delivery north star

### MVP critical path (must work end-to-end)

1. Open project
2. Open/edit/save files
3. Run in separate runner process
4. Stream stdout/stderr
5. Show traceback on failure
6. Persist per-run logs
7. Stop long-running runs safely
8. Keep editor alive when user code fails

### Polish bar (post-MVP but release-important)

- Keyboard-first UX (discoverable shortcuts)
- Clear error/recovery flows
- Useful project search/open ergonomics
- ChoreBoy-specific help surfaces
- Stable behavior in both light/dark themes

### Release class definitions

- `MVP-BLOCKING`: required to declare MVP complete.
- `RELEASE-CRITICAL`: not part of strict MVP gate, but required for top-tier shippable quality.
- `ENHANCEMENT`: high-value improvements that can ship after initial v1 if schedule requires.

---

## 5) Cross-cutting quality gates (apply to every phase)

### Architecture guardrails

- Never execute user project code in the editor process.
- Keep project metadata filesystem-first (`cbcs/project.json`).
- Use explicit JSON contracts for runner manifests.
- Prefer diagnosability over cleverness.

### Testing guardrails

- Use pytest markers: `unit`, `integration`, `runtime_parity`, `manual_acceptance`.
- Run the smallest relevant suite for each slice.
- Add/adjust tests whenever behavior contracts change.

### UI guardrails

- Any UI change must be theme-safe (light + dark).
- Avoid hardcoded one-theme-only color assumptions.
- Validate readability for normal/hover/selected/error states.

---

## 6) Phase A — Foundation (completed)

These slices are complete and should be treated as the stable base.

### A01 — Repository/app skeleton
- Status: `DONE`
- Legacy mapping: `T01`

### A02 — Path/bootstrap helpers
- Status: `DONE`
- Legacy mapping: `T02`

### A03 — Application logging bootstrap
- Status: `DONE`
- Legacy mapping: `T03`

### A04 — Runtime capability probe
- Status: `DONE`
- Legacy mapping: `T04`

### A05 — Main window shell scaffold
- Status: `DONE`
- Legacy mapping: `T05`

### A06 — Project metadata schema/model
- Status: `DONE`
- Legacy mapping: `T06`

### A07 — Project open/load service
- Status: `DONE`
- Legacy mapping: `T07`

### A08 — Recent projects persistence
- Status: `DONE`
- Legacy mapping: `T08`

### A09 — Settings store foundation
- Status: `DONE`
- Legacy mapping: `T23` (foundation portion)

---

## 7) Phase B — MVP completion slices (highest priority)

Release class default for this phase: `MVP-BLOCKING`

The following slices finish the MVP gate defined in `docs/ACCEPTANCE_TESTS.md`.

### B01 — Wire **Open Project** action in shell
- Status: `DONE`
- Objective: connect menu action + folder picker + project service load.
- Scope:
  - enable `File -> Open Project...`
  - successful open updates shell state
  - failed open surfaces actionable error dialog + log entry
- Primary files:
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
  - `app/project/project_service.py`
- Tests:
  - unit tests for action dispatch/error mapping
  - integration test for open-project happy/failure path
- Acceptance linkage: `AT-03`, `AT-04`
- Depends on: `A05`, `A07`, `A08`
- Done when: project loads from UI without restart; invalid project fails clearly.

### B02 — Populate **Open Recent** menu + selection flow
- Status: `DONE`
- Objective: turn persisted recents into usable UX.
- Scope:
  - render recents submenu
  - selecting an item opens project
  - invalid recents prune safely
- Primary files:
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `app/project/recent_projects.py`
- Tests:
  - unit tests for menu model shaping
  - integration test for open-recent selection
- Acceptance linkage: `AT-17`
- Depends on: `B01`
- Done when: recents survive restart and remain stable when paths disappear.

### B03 — Add project tree view to left sidebar
- Status: `DONE`
- Objective: show project files/folders in shell.
- Scope:
  - add model/view bridge for `LoadedProject.entries`
  - refresh tree on project switch
  - support selection signal for file-open path
- Primary files:
  - `app/project/project_tree.py` (new)
  - `app/shell/main_window.py`
- Tests:
  - unit tests for tree model construction/order
  - integration test for tree refresh on project open
- Acceptance linkage: `AT-05`
- Depends on: `B01`
- Done when: tree reflects project reliably and emits file selection events.

### B04 — Implement tabbed file open flow from project tree
- Status: `DONE`
- Objective: open selected text files in editor tabs.
- Scope:
  - add editor manager + tab model
  - open file on tree selection
  - prevent duplicate tabs for same file
- Primary files:
  - `app/editors/editor_tab.py` (new)
  - `app/editors/editor_manager.py` (new)
  - `app/shell/main_window.py`
- Tests:
  - unit tests for tab dedupe/current-tab behavior
  - integration test tree-click -> tab-open
- Acceptance linkage: `AT-06`
- Depends on: `B03`
- Done when: selected file opens once and active tab state is deterministic.

### B05 — Dirty tracking + single-file Save
- Status: `DONE`
- Objective: track modifications and persist current file.
- Scope:
  - dirty marker per tab
  - Save action writes to disk
  - save failure surfaced clearly
- Primary files:
  - `app/editors/editor_tab.py`
  - `app/editors/editor_manager.py`
  - `app/shell/menus.py`
- Tests:
  - unit tests for dirty-state transitions
  - integration test edit+save persistence
- Acceptance linkage: `AT-07`, `AT-08`
- Depends on: `B04`
- Done when: modified file saves correctly and dirty indicator clears.

### B06 — Save All + unsaved-change UX on close/switch
- Status: `DONE`
- Objective: protect user data in multi-tab editing.
- Scope:
  - Save All action
  - unsaved warning flow before destructive actions (close project/exit)
  - no silent data loss
- Primary files:
  - `app/editors/editor_manager.py`
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
- Tests:
  - unit tests for save-all ordering/error handling
  - integration test unsaved guardrail behavior
- Acceptance linkage: `AT-09`
- Depends on: `B05`
- Done when: multi-file edits persist predictably with clear prompts.

### B07 — Status bar editing telemetry
- Status: `DONE`
- Objective: surface active file + line/column + modified state.
- Scope:
  - status bar updates on cursor movement/tab switch
  - retain startup/runtime indicator text from capability probe
- Primary files:
  - `app/shell/status_bar.py`
  - `app/shell/main_window.py`
  - `app/editors/editor_tab.py`
- Tests:
  - unit tests for status mapping
  - integration check for status updates during editing
- Acceptance linkage: supports `AT-06`..`AT-09`
- Depends on: `B04`
- Done when: status bar is always coherent with active editor state.

### B08 — Run manifest model + JSON IO contract
- Status: `DONE`
- Objective: create explicit runner input contract.
- Scope:
  - implement run manifest datamodel + schema version
  - serialize/deserialize + validation errors
- Primary files:
  - `app/run/run_manifest.py` (new)
  - `app/core/models.py`
  - `app/core/errors.py`
- Tests:
  - unit tests for manifest validation/round-trip
- Acceptance linkage: prerequisite for `AT-10`..`AT-16`
- Depends on: `A02`, `A06`
- Done when: manifests are deterministic, validated, and file-backed.

### B09 — Run ID + per-run log path generation
- Status: `DONE`
- Objective: guarantee one durable log file per run.
- Scope:
  - create run ID generation helper
  - create log path helper under `<project>/cbcs/logs`
  - ensure dirs exist
- Primary files:
  - `app/run/run_service.py` (new)
  - `app/bootstrap/paths.py`
- Tests:
  - unit tests for uniqueness, naming, path validity
- Acceptance linkage: `AT-14`
- Depends on: `B08`
- Done when: each run has a stable per-run log target.

### B10 — Process supervisor (editor side)
- Status: `DONE`
- Objective: launch/track/stop external runner process.
- Scope:
  - AppRun command assembly
  - lifecycle states (idle/running/stopping/exited)
  - stop with graceful terminate -> forced kill fallback
- Primary files:
  - `app/run/process_supervisor.py` (new)
  - `app/run/run_service.py`
- Tests:
  - integration tests for spawn/state transitions/termination
- Acceptance linkage: `AT-10`, `AT-15`, `AT-16`
- Depends on: `B08`, `B09`
- Done when: runner always executes out-of-process and can be stopped safely.

### B11 — Runner bootstrap entrypoint + manifest loading
- Status: `DONE`
- Objective: make `run_runner.py` a real runner boot surface.
- Scope:
  - parse manifest path argument
  - validate manifest and bootstrap runner context
  - return clear exit codes for bootstrap/manifest failures
- Primary files:
  - `run_runner.py`
  - `app/runner/runner_main.py` (new)
  - `app/runner/execution_context.py` (new)
- Tests:
  - unit tests for CLI/manifest failure cases
  - integration tests for invalid manifest handling
- Acceptance linkage: prerequisite for `AT-10`..`AT-16`
- Depends on: `B08`
- Done when: runner starts deterministically from manifest input.

### B12 — Execute user entry script in runner (`python_script`)
- Status: `DONE`
- Objective: run project `main.py` inside runner process.
- Scope:
  - set cwd and `sys.path` deterministically
  - execute entrypoint
  - return success/failure exit semantics
- Primary files:
  - `app/runner/runner_main.py`
  - `app/runner/execution_context.py`
- Tests:
  - integration tests: success/failure script execution
- Acceptance linkage: `AT-10`, `AT-11`, `AT-12`, `AT-16`
- Depends on: `B11`
- Done when: simple projects run end-to-end with isolated failure behavior.

### B13 — Stream stdout/stderr to console panel
- Status: `DONE`
- Objective: show live run output in UI.
- Scope:
  - consume process pipes
  - append output to console model/view
  - distinguish stderr from stdout visually
- Primary files:
  - `app/run/console_model.py` (new)
  - `app/run/process_supervisor.py`
  - `app/shell/main_window.py`
- Tests:
  - integration tests for stdout+stderr ordering/visibility
- Acceptance linkage: `AT-11`, `AT-13`
- Depends on: `B10`, `B12`
- Done when: output appears live and remains readable.

### B14 — Persist run logs + full traceback capture
- Status: `DONE`
- Objective: durable diagnostics on every run.
- Scope:
  - write merged run output to per-run log
  - preserve full traceback on exception
  - expose log location in UI
- Primary files:
  - `app/runner/output_bridge.py` (new)
  - `app/runner/traceback_formatter.py`
  - `app/run/run_service.py`
- Tests:
  - integration tests validating log file contents
- Acceptance linkage: `AT-12`, `AT-14`
- Depends on: `B09`, `B12`, `B13`
- Done when: failure diagnosis is possible from log files alone.

### B15 — Problems pane summary for run failures
- Status: `DONE`
- Objective: provide concise, actionable failure summary beyond raw console output.
- Scope:
  - parse traceback into file/line summaries
  - show summary list in Problems pane
  - keep full traceback accessible
- Primary files:
  - `app/run/problem_parser.py` (new)
  - `app/shell/main_window.py`
- Tests:
  - unit tests for traceback parsing
  - integration test for problems pane population
- Acceptance linkage: strengthens `AT-12`, `AT-13`
- Depends on: `B14`
- Done when: common failures are navigable from concise summaries.

### B16 — Run/Stop actions + run-state UX
- Status: `DONE`
- Objective: complete visible run lifecycle controls.
- Scope:
  - enable/disable Run/Stop correctly by state
  - status updates for running/success/failure/terminated
  - prevent accidental parallel launches (v1 single-run policy)
- Primary files:
  - `app/shell/actions.py` (new)
  - `app/shell/menus.py`
  - `app/shell/status_bar.py`
  - `app/run/process_supervisor.py`
- Tests:
  - integration tests for state transitions and button availability
- Acceptance linkage: `AT-10`, `AT-15`, `AT-16`
- Depends on: `B10`, `B13`, `B14`
- Done when: run controls are predictable and safe.

### B17 — MVP acceptance gate pass
- Status: `DONE`
- Objective: prove MVP on target workflow.
- Scope:
  - execute minimum acceptance gate from `docs/ACCEPTANCE_TESTS.md`
  - collect objective evidence (terminal output/log excerpts and UI artifacts)
- Required acceptance tests:
  - `AT-01`, `AT-03`, `AT-05`, `AT-06`, `AT-07`, `AT-08`
- `AT-10`, `AT-11`, `AT-12`, `AT-13`, `AT-14`, `AT-15`, `AT-16`
- Depends on: `B01`..`B16`
- Done when: minimum gate is demonstrably passing.

---

## 8) Phase C — Data safety, diagnostics, and supportability

Release class default for this phase: `RELEASE-CRITICAL`

### C01 — Draft autosave/recovery foundation
- Status: `DONE`
- Objective: recover unsaved work after abnormal exit without silent overwrite.
- Primary files:
  - `app/persistence/autosave_store.py` (new)
  - `app/editors/editor_manager.py`
- Tests:
  - unit tests for draft persistence semantics
  - integration test for recovery after simulated crash
- Acceptance linkage: `AT-18` (required if feature is included in MVP scope)
- Depends on: `B05`, `B06`, `A09`

### C02 — Project health check command
- Status: `DONE`
- Objective: pre-run diagnostics for common project/runtime issues.
- Primary files:
  - `app/support/diagnostics.py` (new)
  - `app/project/project_service.py`
  - `app/bootstrap/capability_probe.py`
- Tests:
  - unit tests for diagnostic result shaping
  - integration tests for valid/invalid project diagnostics
- Acceptance linkage: `AT-22`
- Depends on: `B11`, `B14`

### C03 — Support bundle generation
- Status: `DONE`
- Objective: package logs + project metadata for field troubleshooting.
- Primary files:
  - `app/support/support_bundle.py` (new)
  - `app/support/diagnostics.py`
- Tests:
  - integration tests for bundle artifact composition
- Acceptance linkage: `AT-23`
- Depends on: `C02`, `B14`, `A09`

---

## 9) Phase D — New Project workflow and templates

Release class default for this phase: `RELEASE-CRITICAL`

### D01 — Template registry + loader
- Status: `DONE`
- Objective: discover and materialize built-in templates deterministically.
- Primary files:
  - `app/templates/template_service.py` (new)
  - `templates/` metadata layout
- Tests:
  - unit tests for template discovery/metadata validation
- Acceptance linkage: prerequisite for `AT-19`..`AT-21`

### D02 — `utility_script` template
- Status: `DONE`
- Objective: ship simplest starter project.
- Primary files:
  - `templates/utility_script/**` (new)
- Tests:
  - integration test for generated project validity + run
- Acceptance linkage: `AT-19`
- Depends on: `D01`, `B12`, `B14`

### D03 — `qt_app` template
- Status: `DONE`
- Objective: ship starter GUI project aligned with runtime constraints.
- Primary files:
  - `templates/qt_app/**` (new)
- Tests:
  - integration test for generated project boot path
  - manual acceptance with GUI evidence
- Acceptance linkage: `AT-20`
- Depends on: `D01`

### D04 — `headless_tool` template
- Status: `DONE`
- Objective: ship starter FreeCAD-headless-safe project.
- Primary files:
  - `templates/headless_tool/**` (new)
- Tests:
  - integration test for generated project contract
  - runtime-parity/manual validation for headless guidance correctness
- Acceptance linkage: `AT-21`
- Depends on: `D01`

### D05 — New Project wizard flow
- Status: `DONE`
- Objective: create/open template projects from UI.
- Primary files:
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
  - `app/templates/template_service.py`
- Tests:
  - integration tests for create/open flow
- Acceptance linkage: `AT-19`, `AT-20`, `AT-21`
- Depends on: `D02`, `D03`, `D04`

---

## 10) Phase E — Developer comfort and UX polish

Release class default for this phase: `ENHANCEMENT` unless explicitly marked otherwise.

### E01 — In-file Find/Replace and Go-to-Line
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: fast single-file navigation/editing workflows.
- Primary files:
  - `app/editors/editor_tab.py`
  - `app/shell/menus.py`
- Tests:
  - unit tests for find/goto behavior
  - integration tests for menu/shortcut wiring
- Legacy mapping: expands `T13`

### E02 — Find in Files
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: project-wide text search with jump-to-result.
- Primary files:
  - `app/editors/search_panel.py` (new)
  - `app/shell/main_window.py`
- Tests:
  - integration tests over fixture project trees
- Acceptance linkage: post-MVP ergonomics
- Legacy mapping: `T31`

### E03 — Quick Open (`Ctrl+P`)
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: filename-first project navigation.
- Primary files:
  - `app/editors/quick_open.py` (new)
  - `app/shell/main_window.py`
- Tests:
  - unit tests for matching/ranking
  - integration tests for open behavior
- Legacy mapping: `T32`

### E04 — Output UX polish
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: make console output easy to read and debug.
- Scope:
  - clear stdout/stderr styling contrast
  - run separators and timestamps
  - copy selected output
- Primary files:
  - `app/run/console_model.py`
  - `app/shell/main_window.py`
- Tests:
  - integration tests for formatting behavior

### E05 — Onboarding/help surfaces for ChoreBoy constraints
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: reduce user confusion around runtime/headless limitations.
- Scope:
  - Getting Started panel content
  - FreeCAD headless notes and actionable links
  - shortcut reference exposure
- Primary files:
  - `app/shell/main_window.py`
  - `app/ui/help/**` (new)
- Tests:
  - manual acceptance checks for content discoverability

### E06 — Theme compatibility validation pass
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: verify all UI states used by editor are legible in light and dark mode.
- Scope:
  - validate shell, tree, tabs, status bar, console, problems
  - fix theme-breaking hardcoded styling
- Tests:
  - manual validation artifacts in both themes
- Depends on: completion of major UI slices (`B01`..`E05`)

### E07 — Responsiveness/performance acceptance thresholds
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: define and verify baseline responsiveness so the editor feels polished on constrained systems.
- Scope:
  - project open (small/medium project fixtures) remains responsive with visible progress feedback
  - file open latency feels immediate for typical script sizes
  - Find in Files returns first result chunk quickly for medium projects
  - console rendering remains usable during sustained output bursts
- Thresholds (target baselines for release sign-off):
  - Open project (<= 500 files): initial tree visible in <= 1.0s on target-like VM
  - Open file (~2,000 LOC): tab visible + editable in <= 250ms
  - Find in Files (<= 500 files): first results in <= 1.5s
  - Console burst (>= 2,000 lines): UI remains interactive; no hard freeze > 500ms
- Primary files:
  - `app/shell/main_window.py`
  - `app/project/project_tree.py`
  - `app/editors/search_panel.py`
  - `app/run/console_model.py`
- Tests:
  - integration tests for non-blocking behavior where practical
  - manual timing evidence from target-like runtime for final sign-off
- Depends on: `B03`, `E02`, `E04`

### E09 — Help-menu example project loader
- Status: `DONE`
- Release class: `ENHANCEMENT`
- Objective: provide a runnable CRUD showcase project accessible only through Help > Load Example Project.
- Scope:
  - bundled example project under `example_projects/crud_showcase/`
  - `ExampleProjectService` in `app/examples/example_project_service.py`
  - Help menu action + handler in `app/shell/menus.py` and `app/shell/main_window.py`
  - Getting Started content updated to advertise the example project
- Primary files:
  - `example_projects/crud_showcase/**`
  - `app/examples/example_project_service.py`
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `app/ui/help/getting_started.md`
- Tests:
  - unit tests for menu wiring, service materialization, and SQLite CRUD logic
  - integration tests for project creation and metadata validation
- Acceptance linkage: `AT-33`
- Depends on: `D01`, `E05`

---

## 11) Phase F — Release hardening and final gate

Release class default for this phase: `RELEASE-CRITICAL`

### F01 — Automated test coverage expansion for implemented contracts
- Status: `DONE`
- Objective: close obvious coverage gaps in run/runner/editor boundaries.
- Scope:
  - targeted unit + integration suites for all newly added modules
  - runtime-parity tests where FreeCAD AppRun behavior matters
- Depends on: completion of MVP + template slices

### F02 — Full manual acceptance runbook execution
- Status: `DONE`
- Objective: execute end-to-end acceptance checks on target-like environment.
- Scope:
  - run `AT-01` through `AT-23` as applicable
  - document pass/fail evidence
- Depends on: `B17`, `C02`, `C03`, `D05`, key `E*` polish tasks

### F03 — Documentation contract sync
- Status: `DONE`
- Objective: ensure docs reflect shipped behavior exactly.
- Scope:
  - update `ARCHITECTURE.md` for any contract changes
  - update `ACCEPTANCE_TESTS.md` for changed validation criteria
  - update `TESTS.md` to remove setup-era drift and reflect real test inventory
- Depends on: final implementation scope

### F04 — Final release checklist + backlog closure
- Status: `DONE`
- Objective: produce a supportable, handoff-ready v1.
- Scope:
  - confirm no open MVP-critical defects
  - mark all completed tasks with evidence links
  - move non-v1 items to explicit deferred list
- Depends on: `F01`, `F02`, `F03`

---

## 12) Execution traceability matrix (task → test layer → validation)

This matrix provides the canonical test-layer + validation expectations for remaining non-foundation slices.

| Task | Automated test layer | Validation method (minimum) | Release class |
|---|---|---|---|
| B01 | integration (+ targeted unit) | `python -m pytest -m integration tests/integration/...` + UI open-project manual check | MVP-BLOCKING |
| B02 | integration (+ targeted unit) | integration test for menu wiring + restart persistence check | MVP-BLOCKING |
| B03 | unit + integration | tree model unit tests + integration refresh check | MVP-BLOCKING |
| B04 | unit + integration | tab manager unit tests + tree-click integration check | MVP-BLOCKING |
| B05 | unit + integration | dirty/save unit tests + edit/save integration check | MVP-BLOCKING |
| B06 | unit + integration | save-all + unsaved-guard integration checks | MVP-BLOCKING |
| B07 | unit + integration | status mapping unit tests + UI telemetry integration check | MVP-BLOCKING |
| B08 | unit | manifest model validation + round-trip tests | MVP-BLOCKING |
| B09 | unit | run-id/log-path determinism tests | MVP-BLOCKING |
| B10 | integration | spawn/stop lifecycle integration checks | MVP-BLOCKING |
| B11 | unit + integration | runner CLI/manifest failure tests + integration bootstrap check | MVP-BLOCKING |
| B12 | integration | success/failure execution integration tests | MVP-BLOCKING |
| B13 | integration | stdout/stderr streaming integration tests | MVP-BLOCKING |
| B14 | integration | log/traceback persistence integration tests | MVP-BLOCKING |
| B15 | unit + integration | traceback parsing unit tests + problems-pane integration check | MVP-BLOCKING |
| B16 | integration | run-state transition integration tests + manual stop-flow check | MVP-BLOCKING |
| B17 | manual_acceptance | execute MVP AT gate with evidence artifacts | MVP-BLOCKING |
| C01 | unit + integration | draft recovery tests + crash-recovery integration test | RELEASE-CRITICAL |
| C02 | unit + integration | diagnostics result tests + invalid project checks | RELEASE-CRITICAL |
| C03 | integration | support bundle artifact verification tests | RELEASE-CRITICAL |
| D01 | unit | template registry/metadata contract tests | RELEASE-CRITICAL |
| D02 | integration | template generate + run validation | RELEASE-CRITICAL |
| D03 | integration + manual_acceptance | template generate test + GUI launch evidence | RELEASE-CRITICAL |
| D04 | integration + runtime_parity/manual_acceptance | headless template contract checks + runtime guidance validation | RELEASE-CRITICAL |
| D05 | integration | New Project flow integration checks | RELEASE-CRITICAL |
| E01 | unit + integration | find/goto unit tests + shortcut wiring check | RELEASE-CRITICAL |
| E02 | integration | project search integration tests | RELEASE-CRITICAL |
| E03 | unit + integration | matching unit tests + open-file integration checks | RELEASE-CRITICAL |
| E04 | integration + manual_acceptance | console formatting behavior + readability evidence | RELEASE-CRITICAL |
| E05 | manual_acceptance | onboarding discoverability walkthrough evidence | RELEASE-CRITICAL |
| E06 | manual_acceptance | light/dark visual validation artifacts | RELEASE-CRITICAL |
| E07 | integration + manual_acceptance | responsiveness checks + timing evidence against thresholds | RELEASE-CRITICAL |
| E09 | unit + integration | menu wiring, service materialization, CRUD repository, project load | ENHANCEMENT |
| F01 | unit + integration + runtime_parity | run targeted suites for all shipped modules | RELEASE-CRITICAL |
| F02 | manual_acceptance | execute AT runbook and capture outcomes | RELEASE-CRITICAL |
| F03 | n/a (docs contract) | doc diff review aligned to shipped behavior | RELEASE-CRITICAL |
| F04 | n/a (release process) | closure checklist + deferred backlog curation | RELEASE-CRITICAL |

---

## 13) Legacy mapping (continuity with previous T01–T33 plan)

| Legacy ID | New mapping |
|---|---|
| T01 | A01 |
| T02 | A02 |
| T03 | A03 |
| T04 | A04 |
| T05 | A05 |
| T06 | A06 |
| T07 | A07 |
| T08 | A08 |
| T09 | B01 |
| T10 | B03 |
| T11 | B04 |
| T12 | B05 + B06 |
| T13 | B07 + E01 |
| T14 | B08 |
| T15 | B09 |
| T16 | B10 |
| T17 | B11 |
| T18 | B12 |
| T19 | B13 |
| T20 | B14 |
| T21 | B15 |
| T22 | B16 |
| T23 | A09 |
| T24 | C01 |
| T25 | C02 |
| T26 | D01 |
| T27 | D02 |
| T28 | D03 |
| T29 | D04 |
| T30 | D05 |
| T31 | E02 |
| T32 | E03 |
| T33 | C03 |

---

## 14) Definition of MVP achieved

MVP is achieved only when the following are demonstrably true on target-like runtime:

- Editor launches and probes runtime safely.
- Project open/edit/save path is stable.
- Runner executes out-of-process with output capture.
- Failures preserve traceback and logs.
- Stop flow is safe for long-running code.
- Editor survives user-code crashes.
- Required acceptance tests pass with evidence.

Until then, polish work is secondary.

---

## 15) Post-MVP UX2 Enhancements (2026-03-01)

Release class default for this section: `RELEASE-CRITICAL` unless noted.

### G01 — Layout persistence and reset ergonomics
- Status: `DONE`
- Objective: persist splitter/window layout and restore productive defaults.
- Primary files:
  - `app/shell/main_window.py`
  - `app/shell/layout_persistence.py`
  - `app/persistence/settings_store.py`
  - `tests/unit/shell/test_layout_persistence.py`
- Validation:
  - automated: unit + integration suite pass
  - manual: layout can be reset and persisted between sessions

### G02 — Interactive Python console mode
- Status: `DONE`
- Objective: enable stdin-backed interactive console session in runner process, including projectless startup and multiline REPL semantics.
- Primary files:
  - `app/run/process_supervisor.py`
  - `app/run/run_manifest.py`
  - `app/run/run_service.py`
  - `app/runner/runner_main.py`
  - `app/shell/main_window.py`
  - `tests/integration/run/test_run_service_integration.py`
- Validation:
  - REPL input/output (single-line + multiline, including projectless startup) covered by integration tests

### G03 — Run/Debug top toolbar and lifecycle controls
- Status: `DONE`
- Objective: expose run/debug controls in a top command bar with state-aware enablement.
- Primary files:
  - `app/shell/toolbar.py`
  - `app/shell/actions.py`
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_actions.py`

### G04 — File tree parity operations
- Status: `DONE`
- Objective: tree context-menu operations (create/rename/delete/copy/cut/paste/duplicate/path copy/reveal) and drag-drop move callback support.
- Primary files:
  - `app/project/file_operations.py`
  - `app/project/file_operation_models.py`
  - `app/project/project_tree_widget.py`
  - `app/shell/main_window.py`
  - `tests/unit/project/test_file_operations.py`

### G05 — Import rewrite policy with Ask/Always/Never
- Status: `DONE`
- Objective: update Python imports on module move/rename with default Ask policy and optional persisted Always/Never preference.
- Primary files:
  - `app/intelligence/import_rewrite.py`
  - `app/shell/main_window.py`
  - `app/core/constants.py`
  - `tests/unit/intelligence/test_import_rewrite.py`
  - `tests/unit/persistence/test_settings_store.py`

### G06 — Code pane modernization foundation
- Status: `DONE`
- Objective: add code editor widget with line numbers, current-line highlighting, syntax highlighting, breadcrumbs, and breakpoint gutter.
- Primary files:
  - `app/editors/code_editor_widget.py`
  - `app/editors/syntax_python.py`
  - `app/editors/syntax_json.py`
  - `app/editors/syntax_markdown.py`
  - `app/shell/main_window.py`

### G07 — Navigation and import diagnostics baseline
- Status: `DONE`
- Objective: provide go-to-definition and unresolved import analysis workflow.
- Primary files:
  - `app/intelligence/symbol_index.py`
  - `app/intelligence/navigation_service.py`
  - `app/intelligence/diagnostics_service.py`
  - `app/shell/main_window.py`
  - `tests/unit/intelligence/test_symbol_index.py`
  - `tests/unit/intelligence/test_navigation_service.py`
  - `tests/unit/intelligence/test_diagnostics_service.py`

### G08 — Debugger workflow baseline
- Status: `DONE`
- Objective: run Python code under debug mode with breakpoints, pause markers, continue/step commands, and inspector command helpers.
- Primary files:
  - `app/run/run_manifest.py`
  - `app/run/run_service.py`
  - `app/runner/runner_main.py`
  - `app/shell/main_window.py`
  - `tests/integration/run/test_run_service_integration.py`

### G09 — Theme-safe shell polish
- Status: `DONE`
- Objective: centralize shell styling through theme token + stylesheet modules and preserve light/dark usability.
- Primary files:
  - `app/shell/theme_tokens.py`
  - `app/shell/style_sheet.py`
  - `app/shell/main_window.py`

### G10 — Debug pause control and state gating
- Status: `DONE`
- Objective: support explicit debug pause requests and state-aware pause action enablement.
- Primary files:
  - `app/run/process_supervisor.py`
  - `app/run/run_service.py`
  - `app/shell/actions.py`
  - `app/shell/menus.py`
  - `app/shell/toolbar.py`
  - `tests/integration/run/test_process_supervisor.py`

### G11 — Non-blocking search + background symbol indexing
- Status: `DONE`
- Objective: move key expensive operations off UI thread and preserve responsiveness.
- Primary files:
  - `app/editors/search_panel.py`
  - `app/intelligence/symbol_index.py`
  - `app/shell/main_window.py`
  - `tests/unit/editors/test_search_panel.py`
  - `tests/unit/intelligence/test_symbol_index.py`

### G12 — Runner debug module extraction + structured inspector sync
- Status: `DONE`
- Objective: isolate runner debug logic and provide structured pause payload for stack/variables inspector panes.
- Primary files:
  - `app/runner/debug_runner.py`
  - `app/runner/runner_main.py`
  - `app/debug/*`
  - `app/shell/main_window.py`
  - `tests/unit/runner/test_debug_runner.py`
  - `tests/integration/debug/*`

### G13 — Bounded run-output tail + debounced autosave writes
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: prevent unbounded run-output memory growth and reduce per-keystroke autosave I/O pressure.
- Primary files:
  - `app/run/output_tail_buffer.py`
  - `app/shell/main_window.py`
  - `tests/unit/run/test_output_tail_buffer.py`
  - `tests/integration/performance/test_responsiveness_thresholds.py`

### G14 — Incremental symbol indexing + cooperative search cancellation
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: improve medium-project responsiveness by avoiding full index rebuilds and ensuring cancellable search traversal.
- Primary files:
  - `app/intelligence/symbol_index.py`
  - `app/editors/search_panel.py`
  - `app/persistence/sqlite_index.py`
  - `tests/unit/intelligence/test_symbol_index.py`
  - `tests/unit/editors/test_search_panel.py`
  - `tests/unit/persistence/test_sqlite_index.py`

### G15 — Process supervisor event-ordering hardening
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: make run lifecycle events deterministic and resilient to observer callback failures.
- Primary files:
  - `app/run/process_supervisor.py`
  - `tests/integration/run/test_process_supervisor.py`

### G16 — Background-task runner for blocking shell actions
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: offload heavy shell actions from UI thread with keyed cancellation/replacement semantics.
- Primary files:
  - `app/shell/background_tasks.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_background_tasks.py`

### G17 — Shell controller decomposition (project/run/tree)
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: reduce top-level shell coupling by extracting project-open, run-session, and tree-side-effect orchestration into focused controllers.
- Primary files:
  - `app/shell/project_controller.py`
  - `app/shell/run_session_controller.py`
  - `app/shell/project_tree_controller.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_project_controller.py`
  - `tests/unit/shell/test_run_session_controller.py`
  - `tests/unit/shell/test_project_tree_controller.py`

### G18 — Qt-runtime test harness resilience + typing cleanup
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: keep CI/local validation stable across environments lacking full native Qt runtime and restore strict type-check pass.
- Primary files:
  - `app/editors/text_editing.py`
  - `tests/unit/editors/test_code_editor_widget.py`
  - `tests/integration/shell/test_run_debug_toolbar_integration.py`
  - `app/shell/status_bar.py`
  - `app/run/run_manifest.py`
  - `app/run/process_supervisor.py`
  - `app/editors/code_editor_widget.py`
  - `run_editor.py`

### G19 — Syntax highlighting modernization (historical precursor)
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: close the initial syntax-highlighting quality gap with shared token taxonomy, theme-tokenized syntax colors, and bounded large-file behavior. The final shipped implementation later consolidated onto the tree-sitter-only renderer described in `G22`.
- Scope:
  - shared syntax engine/token contract and language registry for editor highlighters
  - early lexical-quality upgrades for Python/JSON/Markdown and the theme-token palette
  - large-file safeguards for bracket matching/search overlay density
  - pure-Python vendoring decision gate executed; keep stdlib/stateful in-repo backend for now, revisit vendoring only if future benchmark deltas justify it
- Primary files:
  - `app/editors/syntax_engine.py`
  - `app/editors/syntax_registry.py`
  - `app/editors/syntax_python.py`
  - `app/editors/syntax_json.py`
  - `app/editors/syntax_markdown.py`
  - `app/editors/code_editor_widget.py`
  - `app/intelligence/semantic_tokens.py`
  - `app/shell/theme_tokens.py`
  - `app/shell/main_window.py`
  - `tests/unit/editors/test_syntax_highlighters.py`
  - `tests/unit/editors/test_code_editor_widget_highlighting.py`
  - `tests/unit/editors/test_syntax_registry.py`
  - `tests/unit/intelligence/test_semantic_tokens.py`
  - `tests/integration/performance/test_editor_highlighting_performance.py`

### G20 — Syntax highlighting v2 hard cutover + perf gates
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: finish the modernization cutover with adaptive scheduling, expanded semantic taxonomy, viewport-aware limits, and enforceable regression gates. The final renderer no longer uses delayed semantic overlays; those roles now flow through the tree-sitter highlighter path.
- Scope:
  - shared highlighting thresholds centralized in runtime settings/constants (`normal`/`reduced`/`lexical_only`)
  - `.pyw` / shebang parity and richer registry/sniff coverage
  - Python lexical v2 upgrades (soft keywords, f-string expression tokening, multiline signature parameters)
  - Markdown/JSON/registry modernization for richer edge handling and extensionless sniff coverage
  - theme taxonomy expansion for semantic method/variable/property parity in light+dark modes
  - viewport-capped work and no-op refresh guards in large buffers
  - regression gates for lexical/semantic/theme-switch/adaptive-mode behavior + docs contract sync
- Primary files:
  - `app/core/constants.py`
  - `app/intelligence/cache_controls.py`
  - `app/intelligence/semantic_tokens.py`
  - `app/intelligence/latency_tracker.py`
  - `app/editors/code_editor_widget.py`
  - `app/editors/syntax_python.py`
  - `app/editors/syntax_json.py`
  - `app/editors/syntax_markdown.py`
  - `app/editors/syntax_registry.py`
  - `app/editors/syntax_engine.py`
  - `app/shell/theme_tokens.py`
  - `app/shell/main_window.py`
  - `tests/unit/intelligence/test_latency_tracker.py`
  - `tests/unit/intelligence/test_cache_controls.py`
  - `tests/unit/intelligence/test_semantic_tokens.py`
  - `tests/unit/shell/test_settings_models.py`
  - `tests/unit/shell/test_theme_tokens.py`
  - `tests/unit/shell/test_main_window_semantic_policy.py`
  - `tests/unit/editors/test_syntax_highlighters.py`
  - `tests/unit/editors/test_syntax_registry.py`
  - `tests/unit/editors/test_code_editor_widget_highlighting.py`
  - `tests/integration/performance/test_editor_highlighting_performance.py`
  - `tests/integration/performance/test_responsiveness_thresholds.py`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TASKS.md`

### G21 — Customizable editor settings (shortcuts, syntax colors, linter)
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: deliver user-facing customization for keybindings, syntax token colors (light/dark), and lint rule behavior with persisted settings.
- Scope:
  - keybinding metadata + override model with conflict detection and runtime application
  - settings dialog Keybindings tab (search/edit/reset)
  - syntax color override model + Settings Syntax Colors tab with theme-specific overrides and color picking
  - lint profile model + Settings Linter tab (rule enablement + severity overrides)
  - linter runtime controls: global enable/disable toggle + provider selector (`default`, `pyflakes`)
  - diagnostics pipeline integration for lint profile suppression/severity remap
  - docs/test coverage updates for new settings contracts
- Primary files:
  - `app/core/constants.py`
  - `app/shell/shortcut_preferences.py`
  - `app/shell/syntax_color_preferences.py`
  - `app/intelligence/lint_profile.py`
  - `app/shell/settings_models.py`
  - `app/shell/settings_dialog.py`
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `app/shell/theme_tokens.py`
  - `app/intelligence/diagnostics_service.py`
  - `tests/unit/shell/test_settings_models.py`
  - `tests/unit/shell/test_shortcut_preferences.py`
  - `tests/unit/shell/test_syntax_color_preferences.py`
  - `tests/unit/shell/test_menus_shortcut_overrides.py`
  - `tests/unit/shell/test_settings_dialog.py`
  - `tests/unit/intelligence/test_lint_profile.py`
  - `tests/unit/intelligence/test_diagnostics_service.py`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TASKS.md`

### G23 — Scoped global + per-project settings layering and scope controls
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: deliver layered settings resolution (`defaults -> global -> project`) with explicit settings scope controls in the UI.
- Scope:
  - add per-project settings path and persistence (`<project>/cbcs/settings.json`)
  - enforce project-overridable vs global-only settings boundaries
  - add effective settings merge helpers and scope-aware merge-back logic
  - add Settings dialog scope selector (Global / Project), project-scope reset-to-global controls, and disabled project scope when no project is open
  - wire MainWindow to consume layered effective settings and show project-override status indicator
  - preserve `cbcs/` visibility and extend exclude parsing for project scope
- Primary files:
  - `app/core/constants.py`
  - `app/bootstrap/paths.py`
  - `app/persistence/settings_store.py`
  - `app/persistence/settings_service.py`
  - `app/shell/settings_models.py`
  - `app/shell/settings_dialog.py`
  - `app/shell/main_window.py`
  - `app/project/file_excludes.py`
  - `tests/unit/bootstrap/test_paths.py`
  - `tests/unit/core/test_constants.py`
  - `tests/unit/persistence/test_settings_store.py`
  - `tests/unit/persistence/test_settings_service.py`
  - `tests/unit/shell/test_settings_models.py`
  - `tests/unit/shell/test_settings_dialog.py`
  - `tests/unit/project/test_file_excludes.py`
  - `docs/PRD.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/USER_REQUESTS_TODO.md`
  - `docs/TASKS.md`

### G22 — Tree-sitter syntax-highlighting hard cutover
- Status: `DONE`
- Release class: `RELEASE-CRITICAL`
- Objective: route editor highlighting through a single tree-sitter engine loaded via the memfd runtime path, with highlights/locals/injections query layers, token inspection, and manual language overrides where detection needs help.
- Scope:
  - add startup tree-sitter runtime boot (`ExtensionFileLoader` for `_binding`, memfd `ctypes.CDLL` for `languages.so`)
  - add tree-sitter language/query registry with `highlights`, `locals`, and `injections` assets
  - add tree-sitter `QSyntaxHighlighter` with incremental parse state (`tree.edit` + changed-range capture refresh)
  - ship bundled Python/JSON/HTML/XML/CSS/Bash/Markdown/YAML/JavaScript/TOML grammars plus optional SQL
  - cover `.ui` / `.qrc` through the XML grammar, `pyproject.toml` through TOML, and `.desktop` through the INI fallback path
  - add embedded-language injections for HTML `<script>/<style>` and Markdown fenced code / HTML blocks
  - add token inspection and manual language override tooling in the shell
  - update architecture/tasks/acceptance docs for the shipped highlighting contract
- Primary files:
  - `run_editor.py`
  - `app/editors/code_editor_widget.py`
  - `app/editors/ini_highlighter.py`
  - `app/editors/syntax_registry.py`
  - `app/treesitter/loader.py`
  - `app/treesitter/language_registry.py`
  - `app/treesitter/highlighter.py`
  - `app/treesitter/queries/*.scm`
  - `vendor/tree_sitter/*`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TASKS.md`

---

## 16) Phase H — Plugin Platform Delivery

Release class default for this phase: `RELEASE-CRITICAL`

### H00 — Pre-plugin stabilization seams
- Status: `DONE`
- Objective: reduce plugin integration risk by tightening shell/runtime contracts before plugin features.
- Scope completed:
  - project tree now includes `cbcs/` metadata entries
  - centralized settings IO through `SettingsService`
  - runtime command/action registration seam via `CommandBroker` + `ShellActionRegistry`
  - shared host process orchestration via `HostProcessManager`
  - typed shell event contracts for run/project lifecycle via `ShellEventBus`
- Primary files:
  - `app/project/project_service.py`
  - `app/persistence/settings_service.py`
  - `app/shell/main_window.py`
  - `app/shell/command_broker.py`
  - `app/shell/action_registry.py`
  - `app/run/host_process_manager.py`
  - `app/shell/repl_session_manager.py`
  - `app/shell/events.py`

### H01 — Plugin manifest + discovery/index
- Status: `DONE`
- Objective: define plugin manifest schema and deterministic discovery/compatibility indexing.
- Primary files:
  - `app/plugins/manifest.py`
  - `app/plugins/discovery.py`
  - `app/plugins/models.py`
  - `app/core/constants.py`
  - `app/bootstrap/paths.py`
- Acceptance linkage: `AT-37`, `AT-42`

### H02 — Offline install/uninstall/update registry
- Status: `DONE`
- Objective: support local plugin package/folder install and lifecycle persistence.
- Primary files:
  - `app/plugins/installer.py`
  - `app/plugins/registry_store.py`
  - `app/plugins/package_format.py`
  - `app/persistence/settings_store.py`
- Acceptance linkage: `AT-37`, `AT-39`, `AT-42`

### H03 — Plugin Manager UX
- Status: `DONE`
- Objective: add first-class UI for plugin lifecycle management.
- Primary files:
  - `app/shell/plugins_panel.py`
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
  - `app/shell/settings_dialog.py`
- Acceptance linkage: `AT-37`, `AT-39`, `AT-42`

### H04 — Declarative contribution runtime
- Status: `DONE`
- Objective: wire validated plugin contributions into commands/menus/keybindings/hook events.
- Primary files:
  - `app/plugins/contributions.py`
  - `app/shell/action_registry.py`
  - `app/shell/shortcut_preferences.py`
  - `app/shell/events.py`
- Acceptance linkage: `AT-41`

### H05 — Runtime plugin host + IPC
- Status: `DONE`
- Objective: execute runtime plugin code in isolated host process with explicit protocol.
- Primary files:
  - `app/plugins/host_supervisor.py`
  - `app/plugins/rpc_protocol.py`
  - `app/plugins/runtime_manager.py`
  - `run_plugin_host.py`
- Acceptance linkage: `AT-38`, `AT-40`

### H06 — Safety controls (safe mode + quarantine)
- Status: `DONE`
- Objective: provide recovery UX and automatic containment of failing plugins.
- Primary files:
  - `app/plugins/security_policy.py`
  - `app/plugins/trust_store.py`
  - `app/shell/main_window.py`
  - `app/shell/plugins_panel.py`
- Acceptance linkage: `AT-40`

### H07 — Plugin documentation and authoring contracts
- Status: `DONE`
- Objective: publish plugin author contract and compatibility lifecycle policy.
- Primary files:
  - `docs/plugins/PRD.md`
  - `docs/plugins/AUTHORING_GUIDE.md`
  - `docs/plugins/API_REFERENCE.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`

---

## 17) Phase I — Trusted Python semantics and navigation

Release class default for this phase: `RELEASE-CRITICAL`

### I01 — Semantic contract and acceptance coverage
- Status: `TODO`
- Objective: lock the architecture, backlog, and acceptance contract for trusted Python semantics before behavior changes land.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `unit` (docs-adjacent contract tests land in follow-on slices, not here)
- Validation method: doc review plus subsequent slices linking to the new semantic acceptance IDs
- Acceptance linkage: `AT-45`, `AT-46`, `AT-47`, `AT-48`, `AT-49`, `AT-50`, `AT-51`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: semantic layering, safety rules, rollout slices, and acceptance scenarios are all explicitly documented and traceable.

### I02 — Semantic fixture corpus and failing contract tests
- Status: `TODO`
- Objective: create representative fixture projects and failing tests that expose the current heuristic trust gaps before the engine cutover.
- Primary files:
  - `tests/fixtures/semantic/**`
  - `tests/unit/intelligence/test_semantic_facade.py`
  - `tests/integration/intelligence/test_semantic_navigation_integration.py`
  - existing intelligence unit tests under `tests/unit/intelligence/`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/ tests/integration/intelligence/`
- Acceptance linkage: `AT-45`, `AT-46`, `AT-47`, `AT-49`, `AT-50`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I01`
- Done when: fixtures cover import graphs, shadowing, `vendor/`, syntax-broken buffers, runtime imports, and dynamic-code degradation, with failing tests proving the gap.

### I03 — AppRun semantic-engine compatibility spike
- Status: `TODO`
- Objective: validate Jedi and Rope in the real AppRun path with visible cache policy, no hidden-folder writes, and safe in-process configuration.
- Primary files:
  - `app/intelligence/jedi_runtime.py`
  - `app/intelligence/refactor_runtime.py`
  - `tests/runtime_parity/intelligence/test_semantic_engine_runtime.py`
  - `docs/ARCHITECTURE.md`
- Automated test layer: `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/runtime_parity/intelligence/test_semantic_engine_runtime.py`
- Acceptance linkage: `AT-50`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I01`, `I02`
- Done when: Jedi and Rope run under AppRun without hidden engine metadata paths, unsafe extension loading, or unsupported subprocess assumptions.

### I04 — Semantic facade and serialized worker
- Status: `TODO`
- Objective: introduce a facade, typed semantic result models, deterministic `sys.path` handling, and a serialized worker/session layer for Python semantics.
- Primary files:
  - `app/intelligence/semantic_models.py`
  - `app/intelligence/semantic_facade.py`
  - `app/intelligence/semantic_worker.py`
  - `app/intelligence/jedi_engine.py`
  - `app/intelligence/cache_controls.py`
  - `app/shell/main_window.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/ tests/unit/shell/`
- Acceptance linkage: `AT-45`, `AT-46`, `AT-47`, `AT-50`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I02`, `I03`
- Done when: shell/editor callers depend on the facade contract, and semantic work no longer relies on ad-hoc concurrent background calls.

### I05 — Read-only semantic cutover
- Status: `TODO`
- Objective: replace heuristic completion, definition, hover, signature help, and references with project-aware semantic queries while preserving unsaved-buffer support.
- Primary files:
  - `app/intelligence/navigation_service.py`
  - `app/intelligence/completion_service.py`
  - `app/intelligence/hover_service.py`
  - `app/intelligence/signature_service.py`
  - `app/intelligence/reference_service.py`
  - `app/editors/code_editor_widget.py`
  - `app/shell/main_window.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/ tests/integration/intelligence/`
- Acceptance linkage: `AT-45`, `AT-46`, `AT-47`, `AT-48`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I03`, `I04`
- Done when: semantic read-only actions are correct on fixture projects, confidence/degradation states are explicit, and ambiguous definitions no longer silently choose the first result.

### I06 — Trusted rename planner and patch preview
- Status: `TODO`
- Objective: hard-cut rename to a trusted project-wide planner with grouped patch previews, rollback, and no token-replace fallback.
- Primary files:
  - `app/intelligence/refactor_service.py`
  - `app/intelligence/refactor_engine.py`
  - `app/intelligence/import_rewrite.py`
  - `app/shell/main_window.py`
  - `tests/unit/intelligence/test_refactor_service.py`
  - `tests/integration/intelligence/test_semantic_rename_integration.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/test_refactor_service.py tests/integration/intelligence/test_semantic_rename_integration.py`
- Acceptance linkage: `AT-49`, `AT-50`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I03`, `I04`, `I05`
- Done when: rename preview/apply is semantic, grouped by patch, rollback-safe, and blocked when safe proof is unavailable.

### I07 — Trust UX, async completion, and performance hardening
- Status: `TODO`
- Objective: ship inline/editor-driven trust UX, async semantic completion, theme-safe states, and measured cold/warm performance gates.
- Primary files:
  - `app/editors/code_editor_widget.py`
  - `app/shell/main_window.py`
  - `app/intelligence/semantic_facade.py`
  - `app/intelligence/cache_controls.py`
  - `tests/integration/performance/test_semantic_intelligence_performance.py`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `integration`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/performance/test_semantic_intelligence_performance.py` plus manual light/dark validation on semantic UI states
- Acceptance linkage: `AT-45`, `AT-46`, `AT-47`, `AT-48`, `AT-49`, `AT-51`
- Release class: `RELEASE-CRITICAL`
- Depends on: `I05`, `I06`
- Done when: semantic completion is async/cancellable, trust states are legible in both themes, and latency gates have passing evidence.

---

## 18) Phase J — Real Python formatting and import management

Release class default for this phase: `RELEASE-CRITICAL`

### J01 — Formatting/import-management contract and acceptance coverage
- Status: `TODO`
- Objective: lock the in-process, project-local `pyproject.toml` contract for Python formatting and import management before behavior changes land.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `unit` (docs-adjacent contract tests land in follow-on slices, not here)
- Validation method: doc review plus subsequent slices linking to the new formatting/import acceptance IDs
- Acceptance linkage: `AT-52`, `AT-53`, `AT-54`, `AT-55`, `AT-56`, `AT-57`, `AT-58`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: the formatter/import stack rules, configuration boundaries, rollout slices, and acceptance coverage are all explicit and traceable.

### J02 — Fixture corpus and failing format/import tests
- Status: `TODO`
- Objective: add representative fixture projects and failing tests for `pyproject.toml` handling, Python-version-aware import grouping, comment preservation, broken buffers, and editor text-apply behavior before the adapter cutover.
- Primary files:
  - `tests/fixtures/formatting/**`
  - `tests/unit/python_tools/**`
  - `tests/unit/editors/test_code_editor_widget_editing.py`
  - `tests/integration/shell/**`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/python_tools/ tests/unit/editors/test_code_editor_widget_editing.py tests/integration/shell/`
- Acceptance linkage: `AT-52`, `AT-53`, `AT-54`, `AT-55`, `AT-57`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J01`
- Done when: fixtures cover `src/` projects, `__future__` imports, relative imports, comments, syntax-broken buffers, and Python-3.9-sensitive stdlib classification, with failing tests demonstrating the current gap.

### J03 — AppRun formatter/import compatibility spike
- Status: `TODO`
- Objective: validate Black, isort, and TOML parsing in the real AppRun path with visible-path behavior, package-size discipline, and no formatter CLI dependency.
- Primary files:
  - `vendor/README.md`
  - `docs/PACKAGING.md`
  - `tests/runtime_parity/python_tools/test_python_format_runtime.py`
  - `app/python_tools/vendor_runtime.py`
- Automated test layer: `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/runtime_parity/python_tools/test_python_format_runtime.py`
- Acceptance linkage: `AT-56`, `AT-58`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J01`, `J02`
- Done when: the chosen Black/isort/tomli stack runs under AppRun without hidden cache/config paths, unsupported subprocess assumptions, or installer-budget regressions.

### J04 — Python tooling layer and config resolver
- Status: `TODO`
- Objective: introduce a dedicated Python tooling layer with explicit config resolution, typed result models, and vendored dependency bootstrap helpers.
- Primary files:
  - `app/python_tools/config.py`
  - `app/python_tools/models.py`
  - `app/python_tools/black_adapter.py`
  - `app/python_tools/isort_adapter.py`
  - `app/python_tools/vendor_runtime.py`
  - `app/project/project_service.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/python_tools/`
- Acceptance linkage: `AT-52`, `AT-53`, `AT-54`, `AT-56`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J02`, `J03`
- Done when: callers can request Python formatting/import actions through one focused service layer with explicit config and failure-state metadata.

### J05 — Editor text-apply helper for full-buffer transforms
- Status: `TODO`
- Objective: add a document-apply helper that lets formatter/import actions replace full buffers without destroying practical undo/cursor trust.
- Primary files:
  - `app/editors/code_editor_widget.py`
  - `app/editors/text_editing.py`
  - `tests/unit/editors/test_code_editor_widget_editing.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/editors/test_code_editor_widget_editing.py`
- Acceptance linkage: `AT-52`, `AT-57`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J02`
- Done when: formatter/import callers can apply full-document changes through a tested helper rather than raw `setPlainText(...)` replacement.

### J06 — Manual Python format command cutover
- Status: `TODO`
- Objective: replace whitespace-only Python formatting with a Black-backed manual format action while preserving non-Python fallback behavior.
- Primary files:
  - `app/editors/formatting_service.py`
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
  - `tests/unit/shell/test_main_window_format_actions.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_main_window_format_actions.py tests/integration/shell/`
- Acceptance linkage: `AT-52`, `AT-54`, `AT-57`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J04`, `J05`
- Done when: manual format on Python uses the Black-backed path with explicit failure classification, and non-Python files still use deterministic hygiene formatting.

### J07 — Manual organize-imports command
- Status: `TODO`
- Objective: add a dedicated Python-only organize-imports command using isort with Black-compatible output and Python-target-aware import grouping.
- Primary files:
  - `app/python_tools/isort_adapter.py`
  - `app/shell/main_window.py`
  - `app/shell/menus.py`
  - `tests/unit/python_tools/test_isort_adapter.py`
  - `tests/unit/shell/test_main_window_format_actions.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/python_tools/test_isort_adapter.py tests/unit/shell/test_main_window_format_actions.py tests/integration/shell/`
- Acceptance linkage: `AT-53`, `AT-54`, `AT-57`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J04`, `J05`
- Done when: organize-imports is a separate, trustworthy command that preserves comments/futures ordering and does not reuse unsafe quick-fix line deletion.

### J08 — Save pipeline hardening and settings
- Status: `TODO`
- Objective: upgrade save-time Python formatting/import organization with explicit settings, failure resilience, and measurable guardrails.
- Primary files:
  - `app/core/constants.py`
  - `app/shell/settings_models.py`
  - `app/shell/settings_dialog.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_settings_models.py`
  - `tests/unit/shell/test_settings_dialog.py`
  - `tests/unit/shell/test_main_window_format_actions.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_settings_models.py tests/unit/shell/test_settings_dialog.py tests/unit/shell/test_main_window_format_actions.py tests/integration/shell/`
- Acceptance linkage: `AT-54`, `AT-55`, `AT-57`, `AT-58`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J06`, `J07`
- Done when: save-time organize+format ordering is explicit, settings are layered correctly, failures do not block save, and large-file guardrails are enforced.

### J09 — Formatter/import readiness surfaces
- Status: `TODO`
- Objective: expose formatter/import readiness and project-local configuration detection through existing capability and settings/status seams.
- Primary files:
  - `app/bootstrap/capability_probe.py`
  - `app/shell/status_bar.py`
  - `app/shell/settings_dialog.py`
  - `tests/unit/bootstrap/test_capability_probe.py`
  - `tests/unit/shell/test_status_bar.py`
  - `tests/unit/shell/test_settings_dialog.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/bootstrap/test_capability_probe.py tests/unit/shell/test_status_bar.py tests/unit/shell/test_settings_dialog.py`
- Acceptance linkage: `AT-54`, `AT-56`, `AT-57`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J04`, `J08`
- Done when: users can see whether Black/isort are available and whether project-local formatting/import configuration was detected, without adding a second style editor UI.

### J10 — Structural import-management follow-on alignment
- Status: `TODO`
- Objective: define the post-phase cutover from regex import rewrites and unsafe unused-import cleanup toward structural tooling aligned with trusted semantics.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `app/intelligence/import_rewrite.py`
  - `app/intelligence/code_actions.py`
- Automated test layer: `unit` (follow-on implementation slices add behavior tests)
- Validation method: design review plus follow-on slices referencing the structural acceptance contract
- Acceptance linkage: `AT-53`, `AT-56`
- Release class: `RELEASE-CRITICAL`
- Depends on: `J01`, `J07`
- Done when: the repo explicitly documents that organize-imports is not the long-term structural refactor lane and links the eventual cutover to the trusted-semantics roadmap.

---

## 19) Phase K — Better debugger and runtime inspection

Release class default for this phase: `RELEASE-CRITICAL`

### K01 — Debugger contract and acceptance cutover docs
- Status: `TODO`
- Objective: document the north-star debugger architecture, engine decision gate, and acceptance bar before replacing the current `pdb` text bridge.
- Primary files:
  - `docs/PRD.md`
  - `docs/ARCHITECTURE.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TASKS.md`
  - `docs/manual/chapters/06_run_debug_console.md`
- Automated test layer: `manual_acceptance`
- Validation method: doc review plus follow-on slices explicitly linking to `AT-30`, `AT-31`, and `AT-59` through `AT-64`
- Acceptance linkage: `AT-30`, `AT-31`, `AT-59`, `AT-60`, `AT-61`, `AT-62`, `AT-63`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: the repo states that debugger control is structured, stdout/stderr are not the steady-state debug protocol, and the engine decision gate is explicit.

### K02 — Runtime-parity debugger engine spike
- Status: `TODO`
- Objective: validate the AppRun-safe debugger engine choice against subprocess restrictions, dirty-buffer remap, watch evaluation, exception stops, and thread behavior.
- Primary files:
  - `tests/runtime_parity/debug/**`
  - `app/debug/debug_runtime_probe.py`
  - `app/runner/debug_runner.py`
- Automated test layer: `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/runtime_parity/debug/`
- Acceptance linkage: `AT-59`, `AT-61`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K01`
- Done when: the repo has passing runtime evidence for the chosen engine and a written rejection reason for the losing approach.

### K03 — Engine-neutral debug manifest and session contracts
- Status: `TODO`
- Objective: expand run/debug manifests, breakpoint models, exception policy, and session state so shell logic no longer depends on raw `pdb` commands.
- Primary files:
  - `app/run/run_manifest.py`
  - `app/run/run_service.py`
  - `app/debug/debug_models.py`
  - `app/debug/debug_session.py`
  - `app/debug/debug_breakpoints.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/debug/ tests/unit/run/test_run_service.py`
- Acceptance linkage: `AT-30`, `AT-31`, `AT-59`, `AT-61`, `AT-63`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K02`
- Done when: debug sessions are described with typed structured contracts for transport, breakpoints, exception policy, and selected-frame inspection.

### K04 — Dedicated debug transport cutover
- Status: `TODO`
- Objective: move debugger traffic onto a dedicated control transport and remove stdout-marker parsing from the steady-state path.
- Primary files:
  - `app/debug/debug_transport.py`
  - `app/debug/debug_protocol.py`
  - `app/run/process_supervisor.py`
  - `app/run/run_service.py`
  - `app/shell/run_output_coordinator.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/debug/ tests/integration/debug/ tests/integration/run/`
- Acceptance linkage: `AT-30`, `AT-31`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K03`
- Done when: user stdout/stderr no longer doubles as the active debugger control protocol and disconnect/failure states are explicit.

### K05 — Runner debugger engine replacement
- Status: `TODO`
- Objective: replace the CLI-style `MarkedPdb` loop with the chosen structured engine and support verified breakpoints, conditions, hit thresholds, and exception stops.
- Primary files:
  - `app/runner/debug_runner.py`
  - `app/runner/runner_main.py`
  - `app/debug/debug_command_service.py`
  - `tests/unit/runner/test_debug_runner.py`
  - `tests/integration/debug/**`
- Automated test layer: `unit`, `integration`, `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/runner/test_debug_runner.py tests/integration/debug/ tests/runtime_parity/debug/`
- Acceptance linkage: `AT-30`, `AT-59`, `AT-61`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K03`, `K04`
- Done when: structured pause/continue/step/breakpoint/exception flows work without raw `pdb` command strings.

### K06 — Debug inspector overhaul
- Status: `TODO`
- Objective: rebuild the Debug panel around threads, selected frames, scope-aware variables, lazy expansion, bounded previews, and watch results.
- Primary files:
  - `app/debug/debug_models.py`
  - `app/debug/debug_session.py`
  - `app/shell/debug_panel_widget.py`
  - `app/shell/main_window.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/debug/ tests/unit/shell/ tests/integration/debug/`
- Acceptance linkage: `AT-31`, `AT-60`, `AT-61`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K03`, `K04`, `K05`
- Done when: paused state is represented as selected thread/frame/scope data with lazy variable loading and clear watch/error states.

### K07 — End-user debug workflow surface
- Status: `TODO`
- Objective: finish workflow-level UX for debug current file/project/test, rerun last target, breakpoint properties, exception policy, and dirty-buffer source remap.
- Primary files:
  - `app/shell/menus.py`
  - `app/shell/toolbar.py`
  - `app/shell/main_window.py`
  - `app/run/test_runner_service.py`
  - `app/shell/actions.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/ tests/integration/shell/ tests/integration/debug/`
- Acceptance linkage: `AT-59`, `AT-61`, `AT-62`, `AT-63`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K05`, `K06`
- Done when: the visible run/debug surface supports the full planned workflows without asking users to type raw debugger commands.

### K08 — Debug reliability, performance, and supportability hardening
- Status: `TODO`
- Objective: add the final test, latency, theme, and support-bundle coverage needed to ship the richer debugger safely.
- Primary files:
  - `tests/unit/debug/**`
  - `tests/integration/debug/**`
  - `tests/runtime_parity/debug/**`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/manual/chapters/06_run_debug_console.md`
- Automated test layer: `unit`, `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/debug/ tests/integration/debug/ tests/runtime_parity/debug/` plus manual light/dark validation
- Acceptance linkage: `AT-30`, `AT-31`, `AT-59`, `AT-60`, `AT-61`, `AT-62`, `AT-63`, `AT-64`
- Release class: `RELEASE-CRITICAL`
- Depends on: `K05`, `K06`, `K07`
- Done when: debugger behavior has passing automated evidence, documented manual coverage, theme safety, and actionable diagnostics for real-world failures.

