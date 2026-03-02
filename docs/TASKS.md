# ChoreBoy Code Studio — Tasks (v2)

## 1) Purpose

This file is the **execution backlog** for shipping a polished ChoreBoy Code Studio release within the constraints documented in:

1. `docs/PRD.md`
2. `docs/DISCOVERY.md`
3. `docs/ARCHITECTURE.md`
4. `docs/ACCEPTANCE_TESTS.md`
5. `AGENTS.md`

This version replaces the previous broad checklist with a **thin-slice, test-traceable plan**.

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
| Templates / New Project | TODO | no template assets under `/templates` yet |
| Acceptance coverage vs MVP gate | PARTIAL | foundational tests pass; MVP run path not implemented |

> Baseline test signal at rewrite time: `81 passed`.

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
- Keep project metadata filesystem-first (`.cbcs/project.json`).
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
  - create log path helper under `<project>/logs`
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

