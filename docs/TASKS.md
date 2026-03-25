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
  - `tests/integration/run/test_process_supervisor_integration.py`

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
  - `tests/integration/run/test_process_supervisor_integration.py`

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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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
- Status: `DONE`
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

---

## 20) Phase L — Local History, Diffs, and Recovery UX

Release class default for this phase: `RELEASE-CRITICAL`

### L01 — Local history contract and acceptance cutover docs
- Status: `TODO`
- Objective: define the local-history architecture, safety model, retention rules, and acceptance contract before feature code lands.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `unit` (docs-adjacent contract tests land in follow-on slices, not here)
- Validation method: doc review plus follow-on slices explicitly linking to `AT-65` through `AT-71`
- Acceptance linkage: `AT-65`, `AT-66`, `AT-67`, `AT-68`, `AT-69`, `AT-70`, `AT-71`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: the repo explicitly documents local-history storage location, draft-vs-checkpoint semantics, restore-to-buffer rules, lineage behavior, and user-visible acceptance scenarios.

### L02 — Atomic source save foundation
- Status: `TODO`
- Objective: harden file writes with one atomic text-write path before durable history depends on save correctness.
- Primary files:
  - `app/persistence/atomic_write.py`
  - `app/editors/editor_manager.py`
  - `app/shell/main_window.py`
  - `tests/unit/persistence/test_atomic_write.py`
  - `tests/unit/editors/test_editor_manager.py`
  - `tests/integration/shell/test_main_window_shutdown_integration.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/persistence/test_atomic_write.py tests/unit/editors/test_editor_manager.py tests/integration/shell/test_main_window_shutdown_integration.py`
- Acceptance linkage: `AT-65`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L01`
- Done when: editor save, save-all, and auto-save-to-file share one atomic write primitive and only clear dirty state after the real file write succeeds.

### L03 — Project identity and file-lineage foundation
- Status: `TODO`
- Objective: add stable project identity and logical file lineage so history survives move/rename/delete flows.
- Primary files:
  - `app/project/project_manifest.py`
  - `app/core/models.py`
  - `app/shell/project_tree_controller.py`
  - `app/shell/project_tree_action_coordinator.py`
  - `tests/unit/project/test_project_manifest.py`
  - `tests/unit/shell/test_project_tree_controller.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/project/test_project_manifest.py tests/unit/shell/test_project_tree_controller.py tests/integration/shell/`
- Acceptance linkage: `AT-68`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L01`, `L02`
- Done when: projects expose a stable identity, app-driven path changes update logical history lineage, and deleted resources can still be referenced by history metadata.

### L04 — Unified local history store and legacy draft migration
- Status: `TODO`
- Objective: replace the one-draft JSON store with a unified local-history substrate backed by SQLite metadata and content-addressed blobs, while migrating existing drafts forward safely.
- Primary files:
  - `app/persistence/history_models.py`
  - `app/persistence/local_history_store.py`
  - `app/persistence/history_retention.py`
  - `app/persistence/autosave_store.py`
  - `tests/unit/persistence/test_local_history_store.py`
  - `tests/unit/persistence/test_autosave_store.py`
  - `tests/runtime_parity/persistence/test_local_history_runtime.py`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/persistence/test_local_history_store.py tests/unit/persistence/test_autosave_store.py tests/runtime_parity/persistence/test_local_history_runtime.py`
- Acceptance linkage: `AT-65`, `AT-66`, `AT-68`, `AT-70`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L02`, `L03`
- Done when: drafts and checkpoints share one history backend, legacy autosave entries migrate on access, and retention metadata exists without hidden paths.

### L05 — Checkpoint capture integration
- Status: `TODO`
- Objective: create durable history checkpoints for save, reload, refactor, quick-fix, import-rewrite, and delete workflows.
- Primary files:
  - `app/shell/main_window.py`
  - `app/editors/editor_manager.py`
  - `app/intelligence/refactor_engine.py`
  - `app/intelligence/code_actions.py`
  - `app/intelligence/import_rewrite.py`
  - `tests/integration/persistence/test_local_history_checkpoints.py`
- Automated test layer: `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/persistence/test_local_history_checkpoints.py tests/integration/shell/`
- Acceptance linkage: `AT-65`, `AT-68`, `AT-69`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L03`, `L04`
- Done when: all high-value editor write paths emit labeled, bounded history checkpoints and grouped multi-file operations are recorded as one transaction.

### L06 — Draft recovery compare/restore UX
- Status: `TODO`
- Objective: replace the yes/no draft prompt with a reviewable compare-and-restore workflow that restores into the buffer first.
- Primary files:
  - `app/shell/main_window.py`
  - `app/editors/code_editor_widget.py`
  - `tests/integration/persistence/test_autosave_recovery.py`
  - `tests/integration/shell/test_local_history_recovery_ui.py`
- Automated test layer: `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/persistence/test_autosave_recovery.py tests/integration/shell/test_local_history_recovery_ui.py`
- Acceptance linkage: `AT-66`, `AT-67`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L04`, `L05`
- Done when: crash recovery offers compare/restore choices, restores do not silently overwrite disk, and editor context remains trustworthy after restore-to-buffer.

### L07 — Per-file local history dialog
- Status: `TODO`
- Objective: ship a first-class timeline and diff viewer for the active file with compare and restore actions.
- Primary files:
  - `app/shell/local_history_dialog.py`
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_local_history_dialog.py`
  - `tests/integration/shell/test_local_history_dialog_integration.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_local_history_dialog.py tests/integration/shell/test_local_history_dialog_integration.py`
- Acceptance linkage: `AT-65`, `AT-67`, `AT-71`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L04`, `L05`, `L06`
- Done when: users can browse a file timeline, inspect lazy-loaded diffs, compare revisions, and restore a chosen revision into the live buffer.

### L08 — Global history restore and deleted-file recovery
- Status: `TODO`
- Objective: add global search/picker flows for history entries whose live files were renamed, moved, or deleted.
- Primary files:
  - `app/shell/history_restore_picker.py`
  - `app/shell/menus.py`
  - `app/shell/main_window.py`
  - `tests/integration/shell/test_global_history_restore.py`
- Automated test layer: `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/shell/test_global_history_restore.py`
- Acceptance linkage: `AT-68`, `AT-69`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L03`, `L04`, `L05`, `L07`
- Done when: deleted or moved files can be found from global history and restored through an explicit, understandable workflow.

### L09 — Local history settings, retention, and validation hardening
- Status: `TODO`
- Objective: finish settings, pruning, theme safety, performance gates, runtime-parity checks, and supportability coverage for shipping the feature confidently.
- Primary files:
  - `app/core/constants.py`
  - `app/shell/settings_models.py`
  - `app/shell/settings_dialog.py`
  - `app/support/support_bundle.py`
  - `tests/unit/persistence/test_local_history_store.py`
  - `tests/unit/shell/test_settings_models.py`
  - `tests/unit/shell/test_settings_dialog.py`
  - `tests/integration/performance/test_local_history_performance.py`
  - `tests/runtime_parity/persistence/test_local_history_runtime.py`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `unit`, `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/persistence/test_local_history_store.py tests/unit/shell/test_settings_models.py tests/unit/shell/test_settings_dialog.py tests/integration/performance/test_local_history_performance.py tests/runtime_parity/persistence/test_local_history_runtime.py` plus manual light/dark validation
- Acceptance linkage: `AT-70`, `AT-71`
- Release class: `RELEASE-CRITICAL`
- Depends on: `L04`, `L05`, `L06`, `L07`, `L08`
- Done when: retention and exclusion controls are configurable, history pruning remains bounded, support diagnostics include history context when appropriate, and the local-history UI is validated for theme safety and responsiveness.

---

## 21) Phase M — Editor architecture hygiene

Release class default for this phase: `RELEASE-CRITICAL`

This phase turns section 8 of `docs/NEXT_LEVEL_PYTHON_EDITOR_ANALYSIS.md` into an
explicit implementation track. The goal is to keep future editor work reliable and
fast by reducing shell complexity, centralizing semantic ownership, and making the
repo's test/runtime/tooling truth explicit.

### M01 — Contract and acceptance sync for architecture hygiene
- Status: `DONE`
- Objective: make the architecture-hygiene phase explicit across backlog, architecture, acceptance, and validation docs.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TESTS.md`
  - `AGENTS.md`
- Automated test layer: `unit`
- Validation method: doc review plus explicit linkage to `AT-72`
- Acceptance linkage: `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: the repo documents the composition-root rule, worker/scheduler ownership, validation gate, and future contributors can find the architecture-hygiene phase without relying on external planning artifacts.

### M02 — Truthful validation baseline and Python 3.9 tooling alignment
- Status: `DONE`
- Objective: align `pyrightconfig.json`, test commands, and agent guidance with the real runtime/support contract.
- Primary files:
  - `pyrightconfig.json`
  - `docs/TESTS.md`
  - `AGENTS.md`
- Automated test layer: `unit`, `integration`, `runtime_parity`
- Validation method: `pyright` plus the architecture-focused automated suites documented in `docs/TESTS.md`
- Acceptance linkage: `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M01`
- Done when: Python 3.9 is the documented and configured source-compatibility target, stale known-failure notes are removed, and the latest validation checkpoint is recorded truthfully.

### M03 — Single-owner semantic session and worker cutover
- Status: `DONE`
- Objective: route editor semantic work through one owned semantic session instead of mixed shell-thread access.
- Primary files:
  - `app/intelligence/semantic_session.py`
  - `app/intelligence/semantic_worker.py`
  - `app/shell/editor_intelligence_controller.py`
  - `app/shell/main_window.py`
  - `tests/unit/intelligence/test_semantic_session.py`
  - `tests/unit/intelligence/test_semantic_worker.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/test_semantic_worker.py tests/unit/intelligence/test_semantic_session.py`
- Acceptance linkage: `AT-45`, `AT-47`, `AT-49`, `AT-50`, `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M01`
- Done when: completion, hover, signature help, definitions, references, and rename planning all route through one session/worker ownership model with explicit shutdown and cancellation.

### M04 — Bounded general scheduler and stale-result guards
- Status: `DONE`
- Objective: replace ad-hoc shell threads with a reusable bounded scheduler and prevent stale async diagnostics/results from mutating newer buffers.
- Primary files:
  - `app/shell/background_tasks.py`
  - `app/shell/editor_workspace_controller.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_background_tasks.py`
  - `tests/unit/shell/test_main_window_lint_probe_policy.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_background_tasks.py tests/unit/shell/test_main_window_lint_probe_policy.py`
- Acceptance linkage: `AT-51`, `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M03`
- Done when: keyed shell background work uses the bounded scheduler, cancellation/replacement is explicit, and stale diagnostics or semantic payloads are dropped via buffer revision checks.

### M05 — `MainWindow` composition-root decomposition
- Status: `DONE`
- Objective: move editor workflow ownership into focused controllers so `MainWindow` coordinates instead of hosting deep implementation logic.
- Primary files:
  - `app/shell/main_window.py`
  - `app/shell/editor_workspace_controller.py`
  - `app/shell/editor_intelligence_controller.py`
  - `tests/unit/shell/test_main_window_semantic_navigation_actions.py`
  - `tests/unit/shell/test_main_window_reference_rename_actions.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_main_window_semantic_navigation_actions.py tests/unit/shell/test_main_window_reference_rename_actions.py`
- Acceptance linkage: `AT-45`, `AT-49`, `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M03`, `M04`
- Done when: editor-workspace ownership and semantic routing live behind focused controllers and `MainWindow` remains the composition root for those seams.

### M06 — Large UI module splitting without UX regression
- Status: `DONE`
- Objective: split `CodeEditorWidget`, `SettingsDialog`, and stylesheet builders by reason to change while preserving existing UX and theme behavior.
- Primary files:
  - `app/editors/code_editor_widget.py`
  - `app/editors/code_editor_semantics.py`
  - `app/editors/code_editor_search.py`
  - `app/editors/code_editor_editing.py`
  - `app/editors/code_editor_diagnostics.py`
  - `app/shell/settings_dialog.py`
  - `app/shell/settings_dialog_sections.py`
  - `app/shell/style_sheet.py`
  - `app/shell/style_sheet_sections.py`
  - `tests/unit/editors/test_semantic_editor_interactions.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/editors/test_semantic_editor_interactions.py`
- Acceptance linkage: `AT-35`, `AT-36`, `AT-43`, `AT-51`, `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M04`, `M05`
- Done when: editor/search/diagnostics/semantic UI logic, settings-tab construction, and stylesheet builders are decomposed into focused modules without breaking light/dark usability.

### M07 — Hard cutover of transitional legacy paths
- Status: `DONE`
- Objective: remove short-lived compatibility shims so the new scheduler/controller/session path is the only supported editor-architecture lane.
- Primary files:
  - `app/shell/background_tasks.py`
  - `app/shell/main_window.py`
  - `tests/unit/shell/test_background_tasks.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_background_tasks.py tests/unit/shell/test_main_window_semantic_navigation_actions.py tests/unit/shell/test_main_window_reference_rename_actions.py`
- Acceptance linkage: `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M04`, `M05`, `M06`
- Done when: transitional aliases are removed and future editor work only targets the bounded scheduler plus controller/session architecture.

### M08 — Validation gates before future editor feature phases
- Status: `DONE`
- Objective: make unit, integration, runtime-parity, performance, theme, and static-analysis validation a required gate before future editor-intelligence feature work proceeds.
- Primary files:
  - `docs/TESTS.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `AGENTS.md`
  - focused tests under `tests/unit/`, `tests/integration/`, and `tests/runtime_parity/`
- Automated test layer: `unit`, `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: run the full architecture-hygiene command set documented in `docs/TESTS.md`, then execute `AT-72`
- Acceptance linkage: `AT-72`
- Release class: `RELEASE-CRITICAL`
- Depends on: `M01`, `M02`, `M03`, `M04`, `M05`, `M06`, `M07`
- Done when: the repo contains a repeatable validation gate covering architecture-focused automated suites plus light/dark manual confirmation for the touched shell/editor surfaces.

---

## 22) Phase N — Better onboarding and runtime explanation

Release class default for this phase: `RELEASE-CRITICAL`

This phase turns section 9 of `docs/NEXT_LEVEL_PYTHON_EDITOR_ANALYSIS.md` into an
explicit implementation track. The goal is to make the editor unusually clear about
its constrained runtime, active run target, recovery paths, and packaging/export
behavior without requiring terminal knowledge or trial-and-error.

### N01 — Contract and acceptance cutover for runtime explanation
- Status: `TODO`
- Objective: document the runtime-onboarding architecture, backlog slices, and acceptance bar before behavior changes land.
- Primary files:
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `app/ui/help/getting_started.md`
  - `app/ui/help/headless_notes.md`
  - `docs/manual/chapters/01_quick_start.md`
  - `docs/manual/chapters/10_troubleshooting.md`
  - `docs/manual/chapters/11_shortcuts.md`
  - `docs/manual/chapters/12_appendix_limits_and_quickref.md`
- Automated test layer: `unit` (docs-adjacent contract tests land in follow-on slices, not here)
- Validation method: doc review plus subsequent slices explicitly linking to `AT-73` through `AT-80`
- Acceptance linkage: `AT-73`, `AT-74`, `AT-75`, `AT-76`, `AT-77`, `AT-78`, `AT-79`, `AT-80`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: runtime-explanation ownership, rollout slices, and acceptance scenarios are explicit, and user-facing onboarding copy no longer contradicts shipped shortcuts or startup wording.

### N02 — Structured runtime explanation models and preflight core
- Status: `TODO`
- Objective: introduce machine-readable explanation models, issue classification, and editor-side preflight rules on top of existing probes/diagnostics.
- Primary files:
  - `app/core/models.py`
  - `app/support/diagnostics.py`
  - `app/support/runtime_explainer.py`
  - `app/support/preflight.py`
  - `tests/unit/support/test_runtime_explainer.py`
  - `tests/unit/support/test_preflight.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/support/test_runtime_explainer.py tests/unit/support/test_preflight.py`
- Acceptance linkage: `AT-73`, `AT-76`, `AT-77`, `AT-78`, `AT-79`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N01`
- Done when: the same issue/preflight objects can feed status summaries, drill-down UI, workflow guards, and support-bundle artifacts without duplicated rule logic.

### N03 — Runtime Center shell surface and status-bar drill-down
- Status: `TODO`
- Objective: replace terse startup/health summaries with a reusable drill-down surface for runtime and project explanation.
- Primary files:
  - `app/shell/status_bar.py`
  - `app/shell/main_window.py`
  - `app/shell/help_controller.py`
  - `app/shell/runtime_center_dialog.py`
  - `tests/unit/shell/test_runtime_center_dialog.py`
  - `tests/integration/shell/test_runtime_center_integration.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/shell/test_runtime_center_dialog.py tests/integration/shell/test_runtime_center_integration.py`
- Acceptance linkage: `AT-73`, `AT-79`, `AT-80`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N02`
- Done when: startup status, project health, and support-oriented next steps are accessible through one structured runtime surface instead of scattered one-shot message boxes.

### N04 — First-run checklist and welcome/help integration
- Status: `TODO`
- Objective: make onboarding re-openable and discoverable even when recent projects auto-load.
- Primary files:
  - `app/shell/welcome_widget.py`
  - `app/shell/main_window.py`
  - `app/ui/help/getting_started.md`
  - `app/ui/help/headless_notes.md`
  - `tests/integration/shell/test_welcome_runtime_onboarding.py`
- Automated test layer: `integration`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/shell/test_welcome_runtime_onboarding.py` plus manual light/dark walkthrough
- Acceptance linkage: `AT-74`, `AT-80`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N01`, `N03`
- Done when: first-run guidance remains easy to reach from welcome and Help surfaces, and recent-project auto-load no longer hides onboarding.

### N05 — Run-target clarity and run preflight
- Status: `TODO`
- Objective: make active file vs project vs named configuration explicit before execution and catch obvious non-code blockers without launching the runner.
- Primary files:
  - `app/project/run_configs.py`
  - `app/shell/run_config_controller.py`
  - `app/shell/main_window.py`
  - `app/shell/toolbar.py`
  - `tests/unit/project/test_run_configs.py`
  - `tests/integration/shell/test_run_preflight_integration.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/project/test_run_configs.py tests/integration/shell/test_run_preflight_integration.py`
- Acceptance linkage: `AT-75`, `AT-80`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N02`
- Done when: users can see the active run target/configuration before execution, and invalid run metadata fails through clear preflight messaging rather than runner trial-and-error.

### N06 — Contextual import, headless, and packaging explainers
- Status: `TODO`
- Objective: attach deterministic ChoreBoy-aware explanations to the common failure modes called out in the strategy analysis.
- Primary files:
  - `app/intelligence/diagnostics_service.py`
  - `app/bootstrap/runtime_module_probe.py`
  - `app/intelligence/runtime_import_probe.py`
  - `app/packaging/packager.py`
  - `app/shell/main_window.py`
  - `tests/unit/intelligence/test_diagnostics_service.py`
  - `tests/unit/packaging/test_packager.py`
  - `tests/integration/shell/test_runtime_explanations_integration.py`
- Automated test layer: `unit`, `integration`, `runtime_parity`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/intelligence/test_diagnostics_service.py tests/unit/packaging/test_packager.py tests/integration/shell/test_runtime_explanations_integration.py tests/runtime_parity/bootstrap/`
- Acceptance linkage: `AT-76`, `AT-77`, `AT-78`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N02`, `N03`, `N05`
- Done when: common import/headless/package failures yield consistent, actionable guidance without requiring terminal access or arbitrary code execution in the editor.

### N07 — Support-bundle explanation snapshot and help-source cleanup
- Status: `TODO`
- Objective: package the same runtime explanation facts into support artifacts and reduce duplicated help/shortcut sources.
- Primary files:
  - `app/support/support_bundle.py`
  - `app/ui/help/getting_started.md`
  - `app/ui/help/headless_notes.md`
  - `app/ui/help/shortcuts.md`
  - `app/shell/help_controller.py`
  - `docs/manual/chapters/09_packaging_backup.md`
  - `tests/integration/support/test_support_bundle.py`
- Automated test layer: `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/support/test_support_bundle.py`
- Acceptance linkage: `AT-79`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N03`, `N04`, `N05`, `N06`
- Done when: support bundles include machine-readable runtime explanation data and help/manual/runtime-center wording no longer drifts from live shortcuts or workflow behavior.

### N08 — Runtime-parity, theme, and responsiveness hardening
- Status: `TODO`
- Objective: validate that the richer onboarding/runtime surfaces remain fast, theme-safe, and truthful on AppRun-sensitive paths.
- Primary files:
  - `app/bootstrap/capability_probe.py`
  - `app/bootstrap/runtime_module_probe.py`
  - `app/intelligence/runtime_import_probe.py`
  - `app/shell/status_bar.py`
  - `app/shell/welcome_widget.py`
  - `tests/integration/performance/test_runtime_onboarding_performance.py`
  - `tests/runtime_parity/support/test_runtime_explanation_runtime.py`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/integration/performance/test_runtime_onboarding_performance.py tests/runtime_parity/support/test_runtime_explanation_runtime.py` plus manual light/dark validation
- Acceptance linkage: `AT-73`, `AT-74`, `AT-75`, `AT-76`, `AT-77`, `AT-78`, `AT-79`, `AT-80`
- Release class: `RELEASE-CRITICAL`
- Depends on: `N03`, `N04`, `N05`, `N06`, `N07`
- Done when: the runtime-explanation feature set has passing automated evidence, theme-safe manual validation, and no noticeable regression in startup or routine shell responsiveness.

---

## 23) Phase O — Packaging and Distribution Polish

Release class default for this phase: `RELEASE-CRITICAL`

This phase turns section 10 of `docs/NEXT_LEVEL_PYTHON_EDITOR_ANALYSIS.md` into an
explicit implementation track. The goal is to make packaging/export a validated,
manifest-driven, AppRun-native distribution workflow with a clear install/upgrade
story for both Code Studio itself and packaged user projects.

### O01 — Packaging profiles, metadata contract, and docs cutover
- Status: `DONE`
- Objective: define the shared packaging contract, supported profiles, and user-facing packaging docs before deeper implementation layers land.
- Primary files:
  - `docs/PACKAGING.md`
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/manual/chapters/09_packaging_backup.md`
  - `app/ui/help/packaging_backup.md`
- Automated test layer: `unit` (docs-adjacent contract tests land in follow-on slices, not here)
- Validation method: doc review plus follow-on slices explicitly linking to `AT-81` through `AT-84`
- Acceptance linkage: `AT-81`, `AT-82`, `AT-83`, `AT-84`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: `installable` vs `portable`, `cbcs/package.json`, package manifests, install markers, and ChoreBoy staging/install language are consistent across architecture, backlog, manual, and help sources.

### O02 — Shared packaging substrate and artifact manifests
- Status: `DONE`
- Objective: split project packaging into focused modules for config, validation, dependency audit, desktop generation, artifact building, and installer manifests.
- Primary files:
  - `app/packaging/models.py`
  - `app/packaging/config.py`
  - `app/packaging/layout.py`
  - `app/packaging/validator.py`
  - `app/packaging/dependency_audit.py`
  - `app/packaging/desktop_builder.py`
  - `app/packaging/installer_manifest.py`
  - `app/packaging/artifact_builder.py`
  - `app/packaging/packager.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/packaging/test_package_config.py tests/unit/packaging/test_dependency_audit.py tests/unit/packaging/test_packager.py tests/integration/packaging/test_project_packaging_workflow.py`
- Acceptance linkage: `AT-81`, `AT-82`, `AT-83`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O01`
- Done when: project packaging emits shared manifests/reports/docs and product/project packaging stop inventing separate launcher/metadata shapes.

### O03 — Preflight validation and dependency audit
- Status: `DONE`
- Objective: catch packaging blockers before export and explain dependency/runtime issues in ChoreBoy-aware terms.
- Primary files:
  - `app/support/preflight.py`
  - `app/packaging/validator.py`
  - `app/packaging/dependency_audit.py`
  - `tests/unit/support/test_preflight.py`
  - `tests/unit/packaging/test_dependency_audit.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/support/test_preflight.py tests/unit/packaging/test_dependency_audit.py`
- Acceptance linkage: `AT-81`, `AT-83`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O01`, `O02`
- Done when: package metadata, output overlap, entry-file validity, hidden/excluded paths, native-extension risk, and direct subprocess assumptions are surfaced before confusing export failures.

### O04 — Packaging wizard and installable project package flow
- Status: `DONE`
- Objective: replace one-shot export with a wizard-driven packaging workflow and make installable packages the supported default.
- Primary files:
  - `app/shell/package_wizard_dialog.py`
  - `app/shell/main_window.py`
  - `app/shell/style_sheet.py`
  - `app/shell/style_sheet_sections.py`
  - `app/packaging/packager.py`
  - `tests/unit/packaging/test_packager.py`
  - `tests/integration/packaging/test_project_packaging_workflow.py`
- Automated test layer: `unit`, `integration`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/packaging/test_packager.py tests/integration/packaging/test_project_packaging_workflow.py`
- Acceptance linkage: `AT-81`, `AT-84`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O02`, `O03`
- Done when: users can choose a profile, review package metadata, export an installable artifact by default, and inspect the generated manifest/report/docs afterward.

### O05 — Portable profile runtime gate
- Status: `DONE`
- Objective: keep portable packaging explicit, tested, and separate from the installer-grade contract.
- Primary files:
  - `app/packaging/desktop_builder.py`
  - `app/packaging/validator.py`
  - `tests/runtime_parity/packaging/test_launcher_profiles_runtime.py`
- Automated test layer: `runtime_parity`, `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/runtime_parity/packaging/test_launcher_profiles_runtime.py tests/unit/packaging/test_packager.py`
- Acceptance linkage: `AT-83`, `AT-84`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O02`, `O03`
- Done when: portable launchers use `%k` as a separate desktop-file argument, their bootstrap logic has AppRun runtime-parity coverage, and UX/docs make the profile trade-offs explicit.

### O06 — Product packaging convergence on the shared installer contract
- Status: `DONE`
- Objective: make Code Studio product packaging use the same manifest/installer contract as project packages without losing the 15 MB archive gate.
- Primary files:
  - `package.py`
  - `packaging/install.py`
  - `docs/PACKAGING.md`
  - `vendor/README.md`
  - `tests/unit/packaging/test_distribution_installer.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/packaging/test_distribution_installer.py`
- Acceptance linkage: `AT-82`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O01`, `O02`
- Done when: product packaging writes the shared manifest/docs/layout, the standalone installer publishes menu/Desktop launchers consistently, and the product zip budget remains enforced separately from project exports.

### O07 — Packaging validation gates
- Status: `DONE`
- Objective: add explicit automated and manual validation gates for packaging/distribution before rollout.
- Primary files:
  - `docs/ACCEPTANCE_TESTS.md`
  - `docs/TASKS.md`
  - `tests/unit/packaging/`
  - `tests/integration/packaging/`
  - `tests/runtime_parity/packaging/`
- Automated test layer: `unit`, `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: `python3 run_tests.py -v --import-mode=importlib tests/unit/packaging/ tests/integration/packaging/ tests/runtime_parity/packaging/`
- Acceptance linkage: `AT-81`, `AT-82`, `AT-83`, `AT-84`
- Release class: `RELEASE-CRITICAL`
- Depends on: `O02`, `O03`, `O04`, `O05`, `O06`
- Done when: packaging/distribution is a first-class validated phase with explicit unit, integration, runtime-parity, and manual acceptance coverage.

---

## 31) Phase P — Python Workflow Plugin Ecosystem

Release class default for this phase: `RELEASE-CRITICAL`

This phase is the provider-based follow-on to the original plugin platform. It maps to the
workflow-plugin implementation plan tracked in active execution as `o01-*` through `o10-*`
todo ids.

### P01 — Provider contract/doc cutover (`o01-contract-cutover`)
- Status: `DONE`
- Objective: codify provider-based plugin architecture, phased scope, and acceptance linkage in the canonical docs.
- Primary files:
  - `docs/plugins/PRD.md`
  - `docs/plugins/API_REFERENCE.md`
  - `docs/plugins/AUTHORING_GUIDE.md`
  - `docs/ARCHITECTURE.md`
  - `docs/TASKS.md`
  - `docs/ACCEPTANCE_TESTS.md`
- Automated test layer: `unit` (doc-driven contract coverage lands in follow-on slices)
- Validation method: doc review plus traceability from `P02`-`P10`
- Acceptance linkage: `AT-37`, `AT-38`, `AT-39`, `AT-40`, `AT-41`, `AT-42`, `AT-85`, `AT-86`, `AT-87`, `AT-88`, `AT-89`
- Release class: `RELEASE-CRITICAL`
- Depends on: none
- Done when: the provider model, bundled-plugin strategy, project pinning, and rollout slices are explicitly documented and traceable.

### P02 — Manifest v2 and visible project plugin policy (`o02-manifest-pinning`)
- Status: `DONE`
- Objective: extend plugin manifests with permissions/provider metadata and store project-scoped plugin policy in visible project metadata.
- Primary files:
  - `app/plugins/manifest.py`
  - `app/plugins/models.py`
  - `app/plugins/project_config.py`
  - `app/core/constants.py`
  - `app/bootstrap/paths.py`
  - `tests/unit/plugins/test_manifest.py`
  - `tests/unit/plugins/test_project_config.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/`
- Acceptance linkage: `AT-39`, `AT-42`, `AT-86`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P01`
- Done when: manifests support workflow providers/permissions, and `cbcs/plugins.json` persists pins, enablement overrides, and preferred providers.

### P03 — Workflow provider catalog and broker (`o03-provider-broker`)
- Status: `DONE`
- Objective: move Python workflow surfaces from raw plugin command dispatch to typed provider resolution.
- Primary files:
  - `app/plugins/workflow_catalog.py`
  - `app/plugins/workflow_broker.py`
  - `app/plugins/workflow_adapters.py`
  - `tests/unit/plugins/test_workflow_catalog.py`
- Automated test layer: `unit`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/`
- Acceptance linkage: `AT-85`, `AT-86`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P02`
- Done when: shell code can resolve the effective provider for a workflow kind/language/path without importing plugin runtime code directly.

### P04 — IPC v2 with query/job workflow lanes (`o04-ipc-v2`)
- Status: `DONE`
- Objective: support fast query providers, streaming workflow jobs, structured events, and cancellation in the plugin host protocol.
- Primary files:
  - `app/plugins/rpc_protocol.py`
  - `app/plugins/runtime_manager.py`
  - `app/plugins/api_broker.py`
  - `app/plugins/host_runtime.py`
  - `run_plugin_host.py`
  - `tests/unit/plugins/test_rpc_protocol.py`
  - `tests/unit/plugins/test_runtime_manager.py`
  - `tests/runtime_parity/plugins/test_workflow_plugin_runtime.py`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/runtime_parity/plugins/test_workflow_plugin_runtime.py`
- Acceptance linkage: `AT-38`, `AT-40`, `AT-87`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P03`
- Done when: workflow queries and jobs execute through isolated host IPC with structured results, events, and cancellation.

### P05 — Core workflow adapters behind provider contracts (`o05-core-adapters`)
- Status: `DONE`
- Objective: wrap template, packaging, runtime explanation, FreeCAD helper, dependency-audit, and pytest services behind the workflow broker without changing core UX ownership.
- Primary files:
  - `app/plugins/builtin_workflows.py`
  - `app/plugins/workflow_adapters.py`
  - `app/shell/main_window.py`
  - `bundled_plugins/cbcs.templates.standard/**`
  - `bundled_plugins/cbcs.packaging_tools/**`
  - `bundled_plugins/cbcs.runtime_explainers/**`
  - `bundled_plugins/cbcs.freecad_helpers/**`
  - `bundled_plugins/cbcs.dependency_audit/**`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/runtime_parity/plugins/test_workflow_plugin_runtime.py`
- Acceptance linkage: `AT-78`, `AT-79`, `AT-81`, `AT-85`, `AT-87`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P04`
- Done when: the shell talks to typed workflow adapters for these surfaces and continues to own final UI/rendering behavior.

### P06 — Python formatting/diagnostics provider cutover (`o06-python-cutover`)
- Status: `DONE`
- Objective: expose Python formatting, import organization, and diagnostics through provider contracts while keeping editor-owned edit application.
- Primary files:
  - `bundled_plugins/cbcs.python_tools/**`
  - `bundled_plugins/cbcs.python_diagnostics/**`
  - `app/plugins/builtin_workflows.py`
  - `app/plugins/workflow_adapters.py`
  - `app/shell/main_window.py`
  - `tests/runtime_parity/python_tools/test_python_format_runtime.py`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/runtime_parity/python_tools/test_python_format_runtime.py`
- Acceptance linkage: `AT-52`, `AT-53`, `AT-54`, `AT-55`, `AT-56`, `AT-57`, `AT-58`, `AT-85`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P04`, `P05`
- Done when: formatting/import/diagnostics workflows resolve through providers but edits and diagnostics presentation remain editor-controlled.

### P07 — Bundled first-party workflow plugins (`o07-reference-plugins`)
- Status: `DONE`
- Objective: dogfood the workflow API with bundled first-party plugins and real sample implementations.
- Primary files:
  - `bundled_plugins/cbcs.python_tools/**`
  - `bundled_plugins/cbcs.python_diagnostics/**`
  - `bundled_plugins/cbcs.pytest/**`
  - `bundled_plugins/cbcs.templates.standard/**`
  - `bundled_plugins/cbcs.packaging_tools/**`
  - `bundled_plugins/cbcs.runtime_explainers/**`
  - `bundled_plugins/cbcs.freecad_helpers/**`
  - `bundled_plugins/cbcs.dependency_audit/**`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/runtime_parity/plugins/test_workflow_plugin_runtime.py`
- Acceptance linkage: `AT-85`, `AT-87`, `AT-89`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P05`, `P06`
- Done when: at least one bundled provider exists for each initial workflow lane and serves as a maintained compatibility reference.

### P08 — Workflow-plugin UX, provenance, and supportability (`o08-ui-support`)
- Status: `DONE`
- Objective: surface provider provenance, project policy, permissions, and failure state clearly in the shell and support tooling.
- Primary files:
  - `app/shell/plugins_panel.py`
  - `app/shell/main_window.py`
  - `app/support/support_bundle.py`
  - `tests/integration/plugins/test_support_bundle_plugins_integration.py`
- Automated test layer: `integration`, `unit`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/integration/plugins/test_support_bundle_plugins_integration.py`
- Acceptance linkage: `AT-85`, `AT-86`, `AT-88`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P02`, `P03`, `P04`, `P07`
- Done when: Plugin Manager and support bundles expose project pins, provider inventory, permissions, source/provenance, and recent failure state.

### P09 — Safety and performance gates for workflow plugins (`o09-safety-performance`)
- Status: `DONE`
- Objective: enforce phase-1 workflow-plugin safety rules and prevent silent editor degradation.
- Primary files:
  - `app/plugins/auditor.py`
  - `app/plugins/discovery.py`
  - `app/plugins/installer.py`
  - `app/plugins/host_runtime.py`
  - `app/run/test_runner_service.py`
  - `tests/unit/plugins/test_auditor.py`
  - `tests/unit/plugins/test_discovery.py`
  - `tests/unit/plugins/test_installer.py`
- Automated test layer: `unit`, `runtime_parity`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/runtime_parity/plugins/test_workflow_plugin_runtime.py tests/unit/run/test_test_runner_service.py`
- Acceptance linkage: `AT-40`, `AT-87`, `AT-89`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P04`, `P07`
- Done when: install/discovery audits block incompatible phase-1 plugins, runtime loading stays lazy, hidden-path writes are avoided, and provider timeout/performance visibility is explicit.

### P10 — Validation matrix, author SDK, and compatibility policy (`o10-validation-sdk`)
- Status: `DONE`
- Objective: ship a real validation story and author-facing contract around workflow plugins.
- Primary files:
  - `docs/plugins/PRD.md`
  - `docs/plugins/API_REFERENCE.md`
  - `docs/plugins/AUTHORING_GUIDE.md`
  - `docs/plugins/COMPATIBILITY_POLICY.md`
  - `docs/plugins/SDK.md`
  - `tests/unit/plugins/`
  - `tests/integration/plugins/`
  - `tests/runtime_parity/plugins/`
- Automated test layer: `unit`, `integration`, `runtime_parity`, `manual_acceptance`
- Validation method: `python3 run_tests.py -q --import-mode=importlib tests/unit/plugins/ tests/integration/plugins/test_support_bundle_plugins_integration.py tests/runtime_parity/plugins/test_workflow_plugin_runtime.py`
- Acceptance linkage: `AT-85`, `AT-86`, `AT-87`, `AT-88`, `AT-89`
- Release class: `RELEASE-CRITICAL`
- Depends on: `P01`, `P07`, `P08`, `P09`
- Done when: workflow-plugin behavior has unit/integration/runtime-parity/manual coverage, sample plugins live in-tree, and author docs define a stable compatibility/deprecation story.

