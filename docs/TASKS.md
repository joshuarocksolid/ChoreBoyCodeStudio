# ChoreBoy Code Studio — Tasks (v1)

## 1. Purpose

This file translates the product goals in `PRD.md`, the runtime facts in `DISCOVERY.md`, and the system structure in `ARCHITECTURE.md` into an ordered implementation backlog.

This is the canonical task list for v1.

Guiding principles:

- prioritize the first working vertical slice
- keep tasks small and verifiable
- respect the editor/runner boundary
- prefer explicit file-based contracts
- avoid speculative abstraction

---

## 2. Status Legend

- `TODO` — not started
- `IN PROGRESS` — currently being worked on
- `BLOCKED` — cannot proceed without a decision or prerequisite
- `DONE` — completed and validated

---

## 3. MVP Priority

The highest-priority vertical slice is:

1. open a project
2. open and edit `run.py`
3. save changes
4. run in a separate runner process
5. capture stdout/stderr
6. show traceback on failure
7. write per-run log
8. stop the run safely

All early tasks should support this path.

---

## 4. Phase 1 — Bootstrap and App Skeleton

### T01 — Create repository/app skeleton
**Status:** DONE

**Goal:**  
Create the initial source tree that matches the architecture.

**Why:**  
This gives the repo stable structure before implementation begins.

**Scope:**  
- create `run_editor.py`
- create `run_runner.py`
- create `launcher.py`
- create `app/` package and first-level subpackages
- add `__init__.py` files where needed
- do not implement real behavior yet

**Likely files:**  
- `run_editor.py`
- `run_runner.py`
- `launcher.py`
- `app/bootstrap/__init__.py`
- `app/core/__init__.py`
- `app/shell/__init__.py`
- `app/project/__init__.py`
- `app/run/__init__.py`
- `app/runner/__init__.py`
- `app/persistence/__init__.py`
- `app/templates/__init__.py`
- `app/support/__init__.py`

**Depends on:**  
- none

**Done when:**  
- the repo structure exists and matches the architecture doc
- imports can resolve at the package level without implementation errors

---

### T02 — Implement path/bootstrap helpers
**Status:** DONE

**Goal:**  
Create a central path utility that normalizes app root, user state root, temp paths, and project-relative paths.

**Why:**  
The architecture requires deterministic bootstrapping and no reliance on accidental current working directory behavior.

**Scope:**  
- define app root resolution
- define global state root (for example `~/.choreboy_code_studio/`)
- define helper functions for logs, cache, crash reports, and settings
- do not implement project loading yet

**Likely files:**  
- `app/bootstrap/paths.py`
- `app/core/constants.py`

**Depends on:**  
- T01

**Done when:**  
- app/global paths can be generated consistently
- missing directories can be created safely
- no logic depends on the shell’s current working directory

---

### T03 — Implement application logging setup
**Status:** TODO

**Goal:**  
Create a shared logging setup for the editor application.

**Why:**  
Persistent logs are a first-class requirement and essential for supportability.

**Scope:**  
- configure app log path
- define common log format
- expose helper for subsystem loggers
- ensure startup failures can be logged

**Likely files:**  
- `app/bootstrap/logging_setup.py`
- `app/core/constants.py`

**Depends on:**  
- T02

**Done when:**  
- the editor can initialize logging without crashing
- logs are written to the expected persistent location
- log format includes timestamp, level, subsystem, and message

---

### T04 — Implement runtime capability probe
**Status:** TODO

**Goal:**  
Add startup checks for required environment capabilities.

**Why:**  
The discovery doc proved the environment is unusual and the architecture requires capability probing over assumption.

**Scope:**  
- check AppRun presence
- check `PySide2` availability
- check `FreeCAD` availability
- check writable state/log/temp paths
- expose structured results
- do not build final UI for the report yet

**Likely files:**  
- `app/bootstrap/capability_probe.py`
- `app/core/models.py`

**Depends on:**  
- T02
- T03

**Done when:**  
- a capability probe can run on startup
- results are available as structured data
- failures are reported clearly rather than crashing silently

---

### T05 — Create minimal main window shell
**Status:** TODO

**Goal:**  
Create the main Qt window and top-level layout shell.

**Why:**  
We need a stable editor host before project and runner features can plug in.

**Scope:**  
- create main window
- add placeholder left/center/bottom regions
- add menu bar and status bar stubs
- show application startup state
- do not implement editor tabs or run logic yet

**Likely files:**  
- `app/shell/main_window.py`
- `app/shell/menus.py`
- `app/shell/status_bar.py`
- `run_editor.py`

**Depends on:**  
- T03
- T04

**Done when:**  
- the editor window launches through `run_editor.py`
- menu and status bar appear
- startup does not depend on a loaded project

---

## 5. Phase 2 — Project Model and Persistence

### T06 — Define project metadata schema and model
**Status:** TODO

**Goal:**  
Define the canonical `.cbcs/project.json` structure in code.

**Why:**  
Project metadata is a core filesystem contract and must be explicit before project loading is built.

**Scope:**  
- define schema version
- define project metadata model
- define required and optional fields
- add validation rules
- do not build editing UI yet

**Likely files:**  
- `app/project/project_manifest.py`
- `app/core/models.py`
- `app/core/errors.py`

**Depends on:**  
- T01

**Done when:**  
- project metadata can be loaded into a structured model
- invalid metadata raises a clear validation error
- default values are explicit and documented in code

---

### T07 — Implement project open/load service
**Status:** TODO

**Goal:**  
Load a project folder from disk and validate its structure.

**Why:**  
Opening an existing project is part of the very first MVP workflow.

**Scope:**  
- accept a selected folder
- locate `.cbcs/project.json`
- validate project structure
- load project metadata
- enumerate project files
- return a structured project object

**Likely files:**  
- `app/project/project_service.py`
- `app/project/project_manifest.py`
- `app/core/models.py`

**Depends on:**  
- T06

**Done when:**  
- a valid project folder can be opened successfully
- invalid or incomplete projects fail with actionable errors
- the editor receives enough data to display the project

---

### T08 — Implement recent projects persistence
**Status:** TODO

**Goal:**  
Track and restore recent projects.

**Why:**  
This is a small but high-value part of the project-first workflow.

**Scope:**  
- store recent project paths
- deduplicate entries
- prune invalid entries
- expose load/save helpers
- do not build final menu UX polish yet

**Likely files:**  
- `app/project/recent_projects.py`
- `app/persistence/settings_store.py`

**Depends on:**  
- T02
- T07

**Done when:**  
- opening a project updates the recent-project list
- recent projects persist between sessions
- invalid entries are handled safely

---

### T09 — Connect main window to project open flow
**Status:** TODO

**Goal:**  
Allow the editor shell to open a project and show its basic structure.

**Why:**  
This is the first real user-visible milestone of the MVP path.

**Scope:**  
- add “Open Project…” action
- connect file picker
- call project service
- display loaded project name/state
- wire recent-project updates
- do not open files in tabs yet

**Likely files:**  
- `app/shell/main_window.py`
- `app/shell/menus.py`
- `app/project/project_service.py`

**Depends on:**  
- T05
- T07
- T08

**Done when:**  
- a user can choose a project folder
- the editor opens it without restarting
- project state is visible in the shell

---

### T10 — Add project tree view
**Status:** TODO

**Goal:**  
Show the project’s files and folders in the left sidebar.

**Why:**  
Project browsing is required before file editing becomes useful.

**Scope:**  
- create tree model/view
- show folders/files
- exclude internal noise if needed
- support selection events
- do not implement rename/delete yet

**Likely files:**  
- `app/project/project_tree.py`
- `app/shell/main_window.py`

**Depends on:**  
- T09

**Done when:**  
- the project tree renders the selected project
- clicking a file emits an open-file action/event
- tree refresh works after project load

---

## 6. Phase 3 — Basic Editor

### T11 — Implement editor tab model and file open flow
**Status:** TODO

**Goal:**  
Open selected files into editor tabs.

**Why:**  
The MVP requires opening and editing `run.py` inside the app.

**Scope:**  
- define editor tab state
- open text files from project tree
- reuse existing tab if file is already open
- track current tab
- do not implement save yet

**Likely files:**  
- `app/editors/editor_tab.py`
- `app/editors/editor_manager.py`
- `app/shell/main_window.py`

**Depends on:**  
- T10

**Done when:**  
- clicking a text file opens it in a tab
- the same file does not open duplicate tabs unnecessarily
- current file path is visible in the UI

---

### T12 — Implement dirty state and save/save-all
**Status:** TODO

**Goal:**  
Support editing and saving project files safely.

**Why:**  
Saving changes is part of the first core vertical slice.

**Scope:**  
- detect modified state
- save current file
- save all open modified files
- update UI modified indicators
- basic save error handling
- do not implement autosave recovery yet

**Likely files:**  
- `app/editors/editor_tab.py`
- `app/editors/editor_manager.py`
- `app/shell/menus.py`
- `app/shell/status_bar.py`

**Depends on:**  
- T11

**Done when:**  
- edited files show as modified
- save writes updated contents to disk
- save all persists all modified open files
- save failures are surfaced clearly

---

### T13 — Add Python syntax highlighting and basic editor UX
**Status:** TODO

**Goal:**  
Make Python editing usable and readable.

**Why:**  
Even a lightweight IDE should provide a minimally competent code editing experience.

**Scope:**  
- Python syntax highlighting
- tab/indent behavior
- line/column status reporting
- optional go-to-line hook point
- do not add advanced refactors or LSP features

**Likely files:**  
- `app/editors/syntax_python.py`
- `app/editors/editor_tab.py`
- `app/shell/status_bar.py`

**Depends on:**  
- T11

**Done when:**  
- Python files are syntax highlighted
- line/column updates appear in the status area
- indentation behavior is usable for normal editing

---

## 7. Phase 4 — Runner Contract and Process Launch

### T14 — Define run manifest model and JSON serialization
**Status:** TODO

**Goal:**  
Define the file-based contract used by the editor to instruct the runner.

**Why:**  
The architecture explicitly requires JSON manifests rather than fragile shell argument strings.

**Scope:**  
- define manifest schema/version
- define required fields
- add JSON serialization/deserialization
- validate required fields
- do not launch processes yet

**Likely files:**  
- `app/run/run_manifest.py`
- `app/core/models.py`
- `app/core/errors.py`

**Depends on:**  
- T02
- T06

**Done when:**  
- a run manifest object can be created and serialized
- required fields are validated
- manifest version is explicit

---

### T15 — Implement per-run log path generation
**Status:** TODO

**Goal:**  
Create deterministic log paths for each run.

**Why:**  
Per-run logs are part of the MVP and core support workflow.

**Scope:**  
- generate run IDs
- generate log file paths
- ensure project log directory exists
- expose helper for editor and runner use

**Likely files:**  
- `app/run/run_service.py`
- `app/core/constants.py`
- `app/bootstrap/paths.py`

**Depends on:**  
- T02
- T07

**Done when:**  
- each run gets a stable unique log file path
- log directories are created as needed
- naming is predictable and support-friendly

---

### T16 — Implement process supervisor
**Status:** TODO

**Goal:**  
Launch and stop the external runner process from the editor.

**Why:**  
The editor/runner boundary is the most important runtime boundary in the system.

**Scope:**  
- launch runner via AppRun
- pass manifest path
- capture stdout/stderr pipes
- track process state
- implement stop/terminate
- do not yet parse tracebacks

**Likely files:**  
- `app/run/process_supervisor.py`
- `app/run/run_service.py`
- `run_runner.py`

**Depends on:**  
- T14
- T15

**Done when:**  
- the editor can launch a separate runner process
- the process can be stopped by the editor
- process state transitions are tracked clearly

---

### T17 — Implement runner bootstrap and manifest loading
**Status:** TODO

**Goal:**  
Create the runner-side entrypoint that receives and validates a manifest.

**Why:**  
The runner must be a real standalone execution surface, not implicit shared editor logic.

**Scope:**  
- parse manifest path argument
- load manifest JSON
- validate manifest
- initialize runner logging/output setup
- return meaningful exit codes for invalid manifest/bootstrap failures
- do not execute user code yet

**Likely files:**  
- `run_runner.py`
- `app/runner/runner_main.py`
- `app/runner/execution_context.py`

**Depends on:**  
- T14
- T15

**Done when:**  
- the runner starts from a manifest path
- invalid manifests fail clearly
- bootstrap errors are logged and mapped to clear exit codes

---

### T18 — Implement user code execution in runner
**Status:** TODO

**Goal:**  
Execute the project’s selected entry file in the runner process.

**Why:**  
This is the heart of the product.

**Scope:**  
- set working directory
- prepare `sys.path`
- execute selected entry file
- support initial `python_script` mode
- do not implement all future run modes yet

**Likely files:**  
- `app/runner/runner_main.py`
- `app/runner/execution_context.py`

**Depends on:**  
- T17

**Done when:**  
- a simple project `run.py` can execute in the runner
- working directory and import behavior are deterministic
- success/failure exit codes are returned correctly

---

## 8. Phase 5 — Console, Tracebacks, and Logs

### T19 — Stream stdout/stderr into editor console
**Status:** TODO

**Goal:**  
Display near-live runner output in the editor UI.

**Why:**  
A real run experience requires immediate feedback.

**Scope:**  
- read stdout/stderr from process supervisor
- append to console model/view
- preserve output ordering as reasonably as possible
- do not implement rich structured events yet

**Likely files:**  
- `app/run/console_model.py`
- `app/run/process_supervisor.py`
- `app/shell/main_window.py`

**Depends on:**  
- T16
- T18

**Done when:**  
- `print()` output from user code appears in the console pane
- stderr appears distinctly enough to be useful
- console can be cleared between runs

---

### T20 — Persist full traceback and run log output
**Status:** TODO

**Goal:**  
Ensure failures are preserved to disk even if the UI view is transient.

**Why:**  
Persistent logs and full tracebacks are mandatory in the PRD and discovery-based debugging model.

**Scope:**  
- write run output to per-run log file
- preserve full traceback on failure
- include timestamps and subsystem labels where appropriate
- do not implement support bundle export yet

**Likely files:**  
- `app/runner/output_bridge.py`
- `app/runner/traceback_formatter.py`
- `app/run/run_service.py`

**Depends on:**  
- T15
- T18
- T19

**Done when:**  
- each run produces a persistent log file
- exceptions are written fully to the log
- a failed run can be diagnosed from disk output alone

---

### T21 — Add basic problems/error presentation
**Status:** TODO

**Goal:**  
Present runner failures in a clearer form than raw console text alone.

**Why:**  
The architecture calls for summarized problems in addition to full logs.

**Scope:**  
- parse traceback into a user-visible problem summary
- expose filename/line if available
- show basic problems pane or error panel
- do not implement full linting yet

**Likely files:**  
- `app/run/problem_parser.py`
- `app/shell/main_window.py`

**Depends on:**  
- T20

**Done when:**  
- a failing run surfaces a concise summary in the UI
- the summary points users toward the relevant file/line when possible
- full traceback remains available elsewhere

---

### T22 — Add stop/terminate UI flow
**Status:** TODO

**Goal:**  
Allow users to stop long-running code safely from the editor.

**Why:**  
Run/Stop is part of the core product behavior in the PRD.

**Scope:**  
- add Run / Stop actions
- connect to process supervisor
- update UI while run is active
- handle “terminated by user” state cleanly

**Likely files:**  
- `app/shell/menus.py`
- `app/shell/actions.py`
- `app/run/process_supervisor.py`
- `app/shell/status_bar.py`

**Depends on:**  
- T16
- T19

**Done when:**  
- users can stop an active run
- the runner process exits cleanly or is forcibly terminated if necessary
- the UI reflects the final terminated state clearly

---

## 9. Phase 6 — Recovery, Settings, and Polish for MVP

### T23 — Implement basic settings store
**Status:** TODO

**Goal:**  
Persist app-level preferences and basic shell state.

**Why:**  
This supports recent projects, future editor preferences, and a stable app experience.

**Scope:**  
- JSON-backed settings store
- basic read/write helpers
- storage for recent projects and simple UI preferences
- do not add every future setting yet

**Likely files:**  
- `app/persistence/settings_store.py`

**Depends on:**  
- T02

**Done when:**  
- settings can be loaded and saved safely
- missing/corrupt settings files fail gracefully
- recent-project support can rely on this layer

---

### T24 — Implement autosave draft/recovery foundation
**Status:** TODO

**Goal:**  
Protect user work from crashes and power loss.

**Why:**  
The PRD explicitly calls out not losing work, and the architecture recommends recovery-based autosave.

**Scope:**  
- save draft copies outside the source file
- associate drafts with open files
- restore draft candidates on restart
- do not enable silent overwrite autosave-to-file by default

**Likely files:**  
- `app/persistence/autosave_store.py`
- `app/editors/editor_manager.py`

**Depends on:**  
- T12
- T23

**Done when:**  
- unsaved work can be recovered after abnormal exit
- recovery drafts do not silently overwrite source files
- recovery state is inspectable and supportable

---

### T25 — Add project health check
**Status:** TODO

**Goal:**  
Provide a simple diagnostic check for project/run readiness.

**Why:**  
This aligns with the supportability goals and constrained runtime environment.

**Scope:**  
- validate project structure
- validate entry file presence
- validate write access for logs
- validate runner prerequisites
- show concise results

**Likely files:**  
- `app/support/diagnostics.py`
- `app/project/project_service.py`
- `app/bootstrap/capability_probe.py`

**Depends on:**  
- T07
- T17
- T20

**Done when:**  
- users can run a health check
- the output identifies actionable issues before a run
- results are easy to understand

---

## 10. Phase 7 — New Project and Templates

### T26 — Implement template registry and template loader
**Status:** TODO

**Goal:**  
Create the internal system for project templates.

**Why:**  
The PRD calls out new-project workflows and curated starter templates.

**Scope:**  
- define available template types
- define template metadata/version markers
- load template definitions from the repo
- do not create full wizard UI yet

**Likely files:**  
- `app/templates/template_service.py`
- `templates/`

**Depends on:**  
- T01

**Done when:**  
- template types are discoverable in code
- template metadata is explicit
- templates can be copied into a target location predictably

---

### T27 — Create utility_script template
**Status:** TODO

**Goal:**  
Ship the simplest useful starter project.

**Why:**  
This is the lowest-risk template and ideal for validating the new-project path.

**Scope:**  
- add starter `run.py`
- add `.cbcs/project.json`
- add README
- include basic logging/error example

**Likely files:**  
- `templates/utility_script/`

**Depends on:**  
- T26

**Done when:**  
- a new utility script project can be created from the template
- it runs successfully through the runner path
- the template layout matches architecture expectations

---

### T28 — Create qt_app template
**Status:** TODO

**Goal:**  
Ship a starter GUI project using PySide2.

**Why:**  
Qt UI is one of the core breakthroughs behind the product.

**Scope:**  
- add starter Qt app structure
- include entry point and main window
- include project metadata and README
- include basic crash/log behavior

**Likely files:**  
- `templates/qt_app/`

**Depends on:**  
- T26

**Done when:**  
- a new Qt template project can be created
- it launches successfully through the runner path or documented Qt mode path
- the template is understandable and supportable

---

### T29 — Create headless_tool template
**Status:** TODO

**Goal:**  
Ship a starter project for headless FreeCAD-safe backend work.

**Why:**  
The discovery doc makes clear that some FreeCAD GUI paths are unavailable in console mode, so we should guide users toward headless-safe patterns.

**Scope:**  
- add starter backend structure
- document headless-safe assumptions
- include project metadata and README
- avoid GUI-only export examples

**Likely files:**  
- `templates/headless_tool/`

**Depends on:**  
- T26

**Done when:**  
- a new headless template project can be created
- it demonstrates `import FreeCAD`-style backend work without GUI assumptions
- template docs warn clearly about headless limitations

---

### T30 — Implement New Project flow
**Status:** TODO

**Goal:**  
Allow users to create a new project from a built-in template.

**Why:**  
Creating a project from scratch is one of the core v1 use cases.

**Scope:**  
- add “New Project…” action
- choose template
- choose destination folder
- create project files
- open the new project in the editor

**Likely files:**  
- `app/templates/template_service.py`
- `app/shell/main_window.py`
- `app/shell/menus.py`

**Depends on:**  
- T26
- T27
- T28
- T29

**Done when:**  
- a user can create and open a project from a template
- generated files are valid
- the new project is immediately usable

---

## 11. Phase 8 — Post-MVP Developer Comfort

### T31 — Add Find in Files
**Status:** TODO

**Goal:**  
Search across the current project.

**Why:**  
This is one of the highest-value lightweight IDE features after the MVP slice is solid.

**Scope:**  
- basic project text search
- result list with file/line preview
- jump to result in editor
- start with filesystem scan; no index required

**Likely files:**  
- `app/editors/search_panel.py`
- `app/shell/main_window.py`

**Depends on:**  
- T10
- T11

**Done when:**  
- users can search project text
- clicking a result opens the correct file/location
- feature works without an indexing database

---

### T32 — Add Quick Open
**Status:** TODO

**Goal:**  
Open files quickly by name.

**Why:**  
This is a strong usability improvement with low architectural risk.

**Scope:**  
- basic quick-open UI
- fuzzy or partial matching
- open selected file in editor
- no symbol index required for v1

**Likely files:**  
- `app/editors/quick_open.py`
- `app/shell/main_window.py`

**Depends on:**  
- T10
- T11

**Done when:**  
- users can invoke quick open
- matching files appear from the current project
- selecting a result opens the correct tab

---

### T33 — Add support bundle generator
**Status:** TODO

**Goal:**  
Package logs and basic metadata into a supportable artifact.

**Why:**  
The PRD explicitly calls for a report/support workflow suitable for USB transfer.

**Scope:**  
- collect app log
- collect last run log
- collect project metadata
- zip into a bundle
- do not add advanced telemetry or hidden data collection

**Likely files:**  
- `app/support/support_bundle.py`
- `app/support/diagnostics.py`

**Depends on:**  
- T20
- T23
- T25

**Done when:**  
- a support bundle can be generated successfully
- the bundle contains the expected diagnostic artifacts
- bundle creation failures are reported clearly

---

## 12. Deferred / Explicitly Out of Scope for v1

These are intentionally not part of the first implementation wave:

- debugger / breakpoints
- LSP integration
- refactors
- Git integration
- plugin system
- package manager workflows
- internet-dependent features
- collaborative editing
- generalized sandboxing
- GUI-dependent FreeCAD export workflows
- heavy indexing infrastructure
- advanced Postgres workflows inside the IDE

---

## 13. Recommended First Execution Order

If we are implementing from scratch, start here:

1. T01 — repository/app skeleton
2. T02 — path/bootstrap helpers
3. T03 — logging setup
4. T04 — capability probe
5. T05 — main window shell
6. T06 — project metadata schema
7. T07 — project open/load service
8. T09 — connect shell to project open
9. T10 — project tree
10. T11 — editor tab/file open flow
11. T12 — save/save-all
12. T14 — run manifest model
13. T15 — per-run log path generation
14. T16 — process supervisor
15. T17 — runner bootstrap
16. T18 — user code execution
17. T19 — stdout/stderr console
18. T20 — traceback + persistent run log
19. T22 — stop/terminate UI

That sequence proves the product.

---

## 14. Task Maintenance Rules

When a task is completed:

- mark its status
- record any follow-up tasks discovered
- update dependencies if sequencing changed
- update docs if the implementation changed a contract

If implementation reveals that a task is too large, split it into smaller tasks rather than letting it sprawl.

---

## 15. Definition of “MVP Achieved”

MVP is achieved when the following is true on the real ChoreBoy runtime:

- the editor launches successfully
- a project can be opened
- a file can be opened and edited
- changes can be saved
- user code can run in a separate runner process
- stdout/stderr are visible
- failures produce visible tracebacks
- per-run logs are written to disk
- the run can be stopped safely

Until that works end-to-end, other improvements are secondary.