# ChoreBoy Code Studio — Architecture (v1)

## 1. Purpose

This document defines the target architecture for **ChoreBoy Code Studio**, a project-first editor and runner for building Python applications inside the constraints of the ChoreBoy environment.

It translates the product intent from `PRD.md` and the runtime facts from `DISCOVERY.md` into a concrete technical design that is:

* reliable on locked-down ChoreBoy systems
* friendly to AI-assisted development
* resilient to user-code crashes
* simple enough to ship and support
* extensible enough to grow beyond MVP

This architecture is the canonical source of truth for:

* process boundaries
* module boundaries
* runtime contracts
* project layout
* persistence strategy
* run lifecycle
* error handling
* extension points
* implementation sequencing

---

## 2. Architectural Goals

The architecture must optimize for the following outcomes:

### 2.1 Reliability first

The editor must stay alive even if user code crashes, hangs, or spawns long-running work.

### 2.2 Filesystem-first workflow

Projects must remain ordinary folders that users can copy, zip, back up to USB, and inspect without proprietary tooling.

### 2.3 Zero system installation dependency

Everything must run using what already exists on ChoreBoy, primarily the FreeCAD AppRun runtime and shipped project files.

### 2.4 Clear AI-agent boundaries

The codebase should be easy for Cursor and other AI agents to understand:

* small modules
* explicit contracts
* minimal hidden coupling
* strong conventions
* thin vertical slices

### 2.5 Progressive enhancement

MVP should deliver real value without requiring advanced services like LSP, heavy indexing, or complex plugin frameworks.

---

## 3. Constraints and Operating Reality

The architecture must explicitly respect these runtime realities:

1. Users cannot install normal editors, IDEs, or Python packages system-wide.
2. The guaranteed runtime is FreeCAD’s embedded Python launched through `/opt/freecad/AppRun`.
3. PySide2 is available inside that runtime.
4. `import FreeCAD` works for headless backend operations.
5. Some FreeCAD operations that depend on GUI modules fail in console mode.
6. SQLite works and is suitable for local persistence.
7. `subprocess` works and is a core primitive.
8. Detached process launch is proven and necessary for robust app lifetime behavior.
9. Optional pure-Python vendored packages are acceptable; compiled/system dependencies are not.

These are not implementation details. They are first-class architectural constraints.

---

## 4. Architectural Principles

## 4.1 Single editor process, separate runner process

The editor and user code must never run in the same Python process.

**Reason:** crash isolation, responsiveness, simpler supervision, cleaner stdout/stderr capture.

## 4.2 Files are the source of truth

Projects, settings, logs, run outputs, templates, and support bundles should all map to real files on disk.

## 4.3 Simple protocols over cleverness

Whenever components communicate, prefer:

* JSON files
* JSON Lines
* plain stdout/stderr
* explicit paths
* explicit exit codes

Avoid magic imports, implicit globals, and hidden IPC complexity.

## 4.4 Bootstrapping must be deterministic

Because the AppRun launch environment is unusual, startup must be explicit:

* known entry script
* known working directory
* known path setup
* known log destination
* known run manifest

## 4.5 Capability probing over assumption

At startup, the editor should probe what the local runtime supports and adapt or warn accordingly.

## 4.6 Small replaceable modules

Subsystems should be independently swappable:

* editor shell
* project store
* runner bridge
* indexing
* linting
* templates
* support bundle generation

---

## 5. High-Level System Overview

The system consists of five major parts:

1. **Editor Application**
   The main Qt desktop app launched inside FreeCAD AppRun.

2. **Runner Process**
   A separate AppRun-launched process used to execute user code safely.

3. **Project Workspace**
   A folder on disk containing source files, project metadata, logs, and optional vendored libraries.

4. **Global App State**
   User-level settings, recents, cache, and optional indexes stored under a dedicated home directory.

5. **Templates and Support Assets**
   Shipped starter projects, built-in help, and support bundle logic.

### High-level flow

1. User opens Code Studio.
2. Editor performs startup capability probe.
3. User opens or creates a project folder.
4. Editor loads `.cbcs/project.json` and project files.
   If metadata is missing but the folder is a Python project, editor bootstraps canonical
   `.cbcs/project.json` metadata on first open, then proceeds through normal load.
5. User edits files in tabs.
6. On run, editor creates a run manifest and launches a separate runner process.
7. Runner executes user code in AppRun runtime.
8. Runner streams stdout/stderr and writes a per-run log.
9. Editor displays console output, status, and failures.
10. Logs and support bundles remain available on disk.

---

## 6. Process Model

## 6.1 Editor Process

The editor process is responsible for:

* main window and menus
* project tree
* tabbed editors
* save/autosave
* search and quick open
* run configuration UI
* launching and supervising runner processes
* displaying console/problems/logs
* global and per-project settings
* support bundle generation
* capability probe and compatibility reporting

The editor process must **never** execute arbitrary user project code directly.

## 6.2 Runner Process

The runner process is responsible for:

* receiving run instructions
* setting up `sys.path`
* choosing execution mode
* executing the selected entry point
* writing per-run logs
* streaming stdout/stderr
* surfacing exception tracebacks
* returning a final exit status

The runner is disposable and isolated. Each run gets a fresh process.

## 6.3 Optional Background Workers

For v1, background tasks should remain simple and in-process where possible. Examples:

* file indexing
* find-in-files
* project health check
* syntax/lint scans

If a background job proves expensive, it can later be moved to a dedicated worker process. That should be a future optimization, not an MVP requirement.

---

## 7. Launch and Bootstrap Strategy

## 7.1 Boot model

All application launch should be rooted in real Python files, not long inline strings, except for the minimal `AppRun -c` bridge required to enter the runtime.

Recommended pattern:

* `launcher.py` or equivalent host-side bootstrap triggers AppRun
* AppRun invokes a tiny stable boot file
* boot file imports the real application package

### Recommended boot style

```python
/opt/freecad/AppRun -c 'exec(open("/absolute/path/to/run_editor.py").read(), {"__name__": "__main__"})'
```

And similarly for runner:

```python
/opt/freecad/AppRun -c 'exec(open("/absolute/path/to/run_runner.py").read(), {"__name__": "__main__"})'
```

## 7.2 Why this design

This keeps the unusual AppRun invocation surface extremely small and pushes real logic into normal Python files, where architecture, imports, logging, and testing are easier to reason about.

## 7.3 Path rules

Boot scripts must immediately normalize:

* absolute app root
* project root
* working directory
* log path
* `sys.path` ordering

No subsystem should rely on accidental current working directory behavior.

---

## 8. Runtime Modes

The runner should support explicit execution modes.

## 8.1 Normal runs

Normal script execution uses `python_script` internally. There is no separate
`qt_app` or `freecad_headless` mode; all script runs follow the same launch
path. The only user-facing mode distinctions are **Run** vs **Debug** vs **REPL**.

## 8.2 `python_repl`

For interactive Python console sessions where users submit commands over stdin and receive near-live output in the shell.

## 8.3 `python_debug`

For breakpoint-driven debug sessions. This mode executes user code inside the runner process under debugger control and accepts debug commands from the editor.

## 8.4 Future `freecad_gui`

Reserved for future cases where GUI-dependent export workflows need a different launch strategy.

### Rule

Execution mode must be explicit in run config or inferable from template defaults, not guessed from fragile heuristics.

For `python_debug`, breakpoints and debug-control commands must flow through explicit editor↔runner contracts; the editor process must never execute debug-target project code directly.

---

## 9. Repository / Source Layout

Recommended internal app layout:

```text
choreboy_code_studio/
  run_editor.py
  run_runner.py
  launcher.py
  docs/
    PRD.md
    DISCOVERY.md
    ARCHITECTURE.md
    ACCEPTANCE_TESTS.md
    TASKS.md
    AGENTS.md
  app/
    __init__.py
    bootstrap/
      __init__.py
      paths.py
      logging_setup.py
      capability_probe.py
    core/
      __init__.py
      constants.py
      models.py
      errors.py
    shell/
      __init__.py
      main_window.py
      menus.py
      actions.py
      status_bar.py
    editors/
      __init__.py
      editor_tab.py
      editor_manager.py
      syntax_python.py
      search_panel.py
      quick_open.py
    project/
      __init__.py
      project_service.py
      project_tree.py
      project_manifest.py
      recent_projects.py
    run/
      __init__.py
      run_service.py
      run_manifest.py
      process_supervisor.py
      console_model.py
      problem_parser.py
    runner/
      __init__.py
      runner_main.py
      execution_context.py
      traceback_formatter.py
    persistence/
      __init__.py
      settings_store.py
      sqlite_index.py
      autosave_store.py
    templates/
      __init__.py
      template_service.py
    support/
      __init__.py
      support_bundle.py
      diagnostics.py
    ui/
      icons/
      help/
  templates/
    qt_app/
    headless_tool/
    utility_script/
```

This layout intentionally separates:

* app shell
* project logic
* run logic
* persistence
* bootstrapping
* support tooling

That makes the codebase more legible to both humans and AI agents.

---

## 10. Project-on-Disk Model

Each user project is a plain folder.

Recommended project shape:

```text
my_project/
  .cbcs/
    project.json
    runs/
    logs/
    cache/
  vendor/
  app/
  main.py
  README.md
```

## 10.1 Canonical project metadata

Per-project metadata lives at:

```text
<project>/.cbcs/project.json
```

If the folder is opened without existing metadata and contains Python source files, the
editor initializes this file automatically with canonical defaults and an inferred entrypoint.
The initialized file remains the single source of truth going forward.

This file should be human-readable JSON and contain:

* project name
* schema version
* default entry point
* default working directory
* saved run configurations
* template type
* optional env overrides
* optional project notes

### Example

```json
{
  "schema_version": 1,
  "name": "My Project",
  "default_entry": "main.py",
  "working_directory": ".",
  "template": "utility_script",
  "run_configs": []
}
```

## 10.2 Why JSON, not SQLite, for primary project metadata

* easy to inspect
* easy to copy
* easy for support
* easy for AI agents
* resilient under partial project transfer

SQLite can still be used for caches and indexes, but not for the project’s primary identity.

---

## 11. Global App State

Global app state should live under a single dedicated home path, for example:

```text
~/.choreboy_code_studio/
```

Recommended contents:

```text
~/.choreboy_code_studio/
  settings.json
  recent_projects.json
  logs/
  cache/
  state.sqlite3
  crash_reports/
```

## 11.1 What belongs here

* recent projects
* editor preferences
* global shortcuts/preferences
* last-opened window layout
* compatibility probe results cache
* optional global search/index cache
* editor crash logs

## 11.2 What does not belong here

* project source files
* project logs that should travel with the project
* project-specific run configs

---

## 12. Module Responsibilities

## 12.1 `bootstrap`

Handles:

* path normalization
* environment detection
* logging setup
* capability checks

No UI logic. No project logic.

## 12.2 `core`

Shared models, enums, constants, and errors.

This layer should have minimal dependencies and be import-safe everywhere.

## 12.3 `shell`

Owns the main window and top-level composition.

It coordinates services but should not contain deep business logic.

Current implementation keeps `MainWindow` as composition root and delegates
domain orchestration to focused shell controllers:

* `project_controller` for open/recent project flows
* `run_session_controller` for run/debug/repl lifecycle control wiring
* `project_tree_controller` for tree move/delete/remap side effects
* `background_tasks` for keyed off-UI-thread task execution and replacement

Key shell responsibilities include:

* run/debug toolbar and action state mapping
* split-pane layout persistence and reset behavior
* project-tree context action wiring
* bottom-pane composition (console, Python console, problems, debug inspector, run log)

## 12.4 `editors`

Text editing behavior:

* tabs
* dirty state
* syntax highlighting
* stateful lexical highlighting per language (multiline-aware block state)
* language highlighter registry (extension/sniff based) to avoid hardcoded branching
* semantic token overlay fed by background analysis with document-revision guards
* debounced/coalesced semantic refresh scheduling with keyed background-task replacement
* cancellation-aware semantic extraction to avoid stale or long-running token walks
* adaptive highlighting modes (`normal`, `reduced`, `lexical_only`) driven by shared document-size thresholds
* viewport-capped overlay application for large buffers (diagnostics/search/semantic decorations)
* line numbers and breakpoint gutter markers
* search within file
* quick open support
* code-navigation affordances (go-to-definition, breadcrumbs)

## 12.5 `project`

Filesystem/project abstraction:

* open project
* enumerate files
* validate project structure
* read/write project metadata

## 12.6 `run`

Editor-side execution subsystem:

* create run manifest
* launch runner
* read output
* update run state
* stop/terminate process

## 12.7 `runner`

Runner-side subsystem:

* load manifest
* configure execution
* redirect output
* execute entrypoint
* format failures
* finalize run result

## 12.8 `persistence`

Stores:

* settings
* autosave drafts
* optional indexes
* lightweight caches

## 12.9 `templates`

Creates new projects from curated starter templates.

## 12.10 `support`

Diagnostics, health checks, report bundles, and other support workflows.

---

## 13. Runner Contract

The runner contract is one of the most important parts of the system.

## 13.1 Input to runner

The editor should generate a **run manifest** as a JSON file before launch.

Recommended manifest contents:

* manifest version
* run id
* project root
* entry file
* working directory
* execution mode
* argv
* environment overrides
* log file path
* timestamp
* optional breakpoint payloads (for `python_debug`)

### Example

```json
{
  "manifest_version": 1,
  "run_id": "20260228_153500_001",
  "project_root": "/home/default/projects/my_project",
  "entry_file": "main.py",
  "working_directory": "/home/default/projects/my_project",
  "mode": "python_script",
  "argv": [],
  "env": {},
  "log_file": "/home/default/projects/my_project/.cbcs/logs/run_20260228_153500.log",
  "breakpoints": [
    {
      "file_path": "/home/default/projects/my_project/app/main.py",
      "line_number": 42
    }
  ]
}
```

## 13.2 Why manifest files instead of giant CLI argument strings

This architecture strongly prefers a manifest file over complex shell quoting because it is:

* more robust
* easier to debug
* easier to log
* easier for AI agents to generate and inspect
* less fragile in unusual launcher environments

## 13.3 Runner output protocol

For baseline run mode, standard stdout/stderr is sufficient.

Recommended enhancement:

* prefix structured status messages with a recognizable marker, such as JSON lines on stdout
* example categories:

  * `run_started`
  * `run_finished`
  * `traceback`
  * `warning`
  * `status`

Current debug-capable builds may also emit explicit debug lifecycle markers (for example paused/running markers) so editor controls can synchronize state while preserving full output logs.

Human output and structured output may coexist, but the protocol must stay simple.

## 13.4 Exit codes

Define clear meanings:

* `0`: success
* `1`: user code failed
* `2`: runner bootstrap/config failure
* `3`: manifest invalid
* `130`: terminated by user

---

## 14. Console, Problems, and Logs

## 14.1 Console

The console pane should show near-live stdout/stderr from the current run.

For responsiveness on high-output workloads, console buffering should be bounded and trim oldest entries once the configured cap is exceeded.

Current implementation also maintains a bounded run-output tail buffer for
traceback/problem extraction so very long runs do not accumulate unbounded
in-memory output strings.

## 14.2 Problems

The problems pane should show:

* syntax errors
* parse failures
* optional lint results
* runner-reported tracebacks summarized into clickable entries

## 14.3 Run Log

The run log pane should show saved per-run log content from disk, not only transient pipe output.
Current implementation refreshes the Run Log tab from the active run log file after run exit.

## 14.4 Application Log

The editor must write a persistent app log for the shell itself.

## 14.5 Log paths

Editor log:

```text
~/.choreboy_code_studio/logs/app.log
```

Project run logs:

```text
<project>/.cbcs/logs/run_YYYYMMDD_HHMMSS.log
```

## 14.6 Logging requirements

All logs should include:

* timestamp
* level
* subsystem
* message

Tracebacks should always be fully preserved in logs, even if the UI shows a summarized version.

---

## 15. Error Handling and Failure Model

## 15.1 Error categories

Use clear categories:

* bootstrap errors
* project validation errors
* editor UI errors
* runner launch errors
* user code errors
* headless/GUI capability errors
* filesystem permission errors
* support bundle errors

## 15.2 User-facing failure principles

* never fail silently
* always preserve traceback somewhere
* always preserve unsaved text when possible
* surface actionable error messages
* link errors to log file or support bundle

## 15.3 Crash popup

A crash dialog should show:

* short explanation
* full traceback
* copy-to-clipboard
* open log folder
* build support bundle

---

## 16. Editor State Model

Each open tab should track:

* file path
* original contents hash
* current contents
* modified state
* last save time
* syntax mode
* cursor position
* scroll position

This allows stable reopen and recovery workflows.

## 16.1 Autosave strategy

Recommended v1 behavior:

* autosave drafts to a recovery store
* debounce draft writes to avoid per-keystroke disk churn
* do not silently overwrite source files unless autosave-to-file is explicitly enabled
* restore drafts after crash

This is safer for support and easier to reason about.

---

## 17. Search and Indexing

## 17.1 v1 approach

Start with filesystem-based search and optional in-memory indexing.

Current implementation uses cooperative-cancel search workers and line-streaming
file scans so cancellation and first-result latency remain responsive.

## 17.2 SQLite-backed index

If project size justifies it, use SQLite for:

* file inventory
* quick-open candidate cache
* symbol cache
* search acceleration

Current implementation stores per-file symbol index fingerprints
(`mtime_ns` + file size) so symbol indexing can update incrementally instead of
rebuilding every file on each pass.

## 17.3 Design rule

Indexing is an optimization layer, not a source of truth. If index state is stale or missing, the editor must still function.

---

## 18. Templates

Templates should be first-class architecture, not just starter files.

## 18.1 v1 template types

### `qt_app`

For user-facing GUI apps. The template provides PySide2/Qt starter files but
does not set any mode-specific behavior; projects run via the standard
`python_script` execution path.

### `headless_tool`

For backend tools using headless FreeCAD-safe paths.

### `utility_script`

For lightweight scripts and automation.

## 18.2 Template requirements

Each template should include:

* working entrypoint
* example logging
* example error handling
* example project metadata
* README with how to run
* minimal consistent folder layout

## 18.3 Template versioning

Templates should have their own version marker so support and upgrades can reason about what a project was created from.

---

## 19. Capability Probe

At editor startup, run a lightweight compatibility probe.

Suggested checks:

* AppRun available
* PySide2 importable
* FreeCAD importable
* QtUiTools available
* writable global settings path
* writable temp path
* optional vendored package availability

The probe should generate a user-visible compatibility summary.

This is especially important because environment assumptions are fragile in constrained systems.

---

## 20. Safety Model

## 20.1 Default scope

Default file pickers and open dialogs should anchor to user-home-friendly locations.

## 20.2 Supportability over total lockdown

The architecture should prefer transparent behavior and strong warnings over brittle pseudo-security mechanisms that are hard to support.

---

## 21. Performance and Responsiveness

## 21.1 Editor responsiveness rule

No expensive operation should block the Qt UI thread for noticeable periods.

## 21.2 Candidate background tasks

* find in files
* indexing
* support bundle creation
* project health check
* large file loading

Current implementation explicitly offloads:

* find-in-files
* symbol indexing
* go-to-definition cache refresh path
* unresolved import analysis
* project health checks
* support bundle generation
* semantic token extraction

to background workers/tasks to avoid blocking the UI thread.

## 21.3 Highlight pipeline performance gates

The editor highlighting contract is performance-gated with integration tests:

* Python lexical full rehighlight at ~2,000 LOC: p95 <= 300ms (single-run target <= 250ms)
* Python semantic extraction at ~2,000 LOC: p95 <= 120ms
* semantic extraction under typing-burst variants: p95 <= 140ms
* theme-switch apply cost across 10 open editors: p95 <= 150ms per editor
* large-file mode must keep overlay volume bounded (viewport-capped non-cursor selections)
* bracket-match path must remain bounded on large files (no unbounded cursor-move scans)

These gates are part of release validation and should be updated only with explicit evidence.

## 21.4 Process-first for risky work

If work is expensive or failure-prone, prefer process boundaries over thread complexity.

That is especially consistent with the overall crash-isolation design.

---

## 22. Testing Strategy

## 22.1 Test pyramid for this project

### Unit tests

For:

* manifest creation
* settings parsing
* project metadata
* problem parsing
* capability probe helpers

### Integration tests

For:

* opening a project
* saving a file
* creating a run manifest
* launching runner
* capturing stdout/stderr
* handling traceback
* stopping a process

### Manual acceptance tests

For:

* full MVP workflow on actual ChoreBoy environment
* template creation
* headless-safe execution
* log preservation
* support bundle export

## 22.2 Architecture rule

Critical contracts should be testable without bringing up the full editor UI when possible.

---

## 23. Versioning and Compatibility

## 23.1 Schema versioning

The following should have explicit version numbers:

* `.cbcs/project.json`
* run manifest
* support bundle format
* template format

## 23.2 Migration policy

If schema changes, the app should migrate old project metadata in a controlled and logged way.

## 23.3 Compatibility target

The architecture should tolerate partial feature degradation better than hard refusal, as long as the core editor-runner path remains safe and understandable.

---

## 24. Extensibility Strategy

## 24.1 What we will not do in v1

No general plugin framework.

A plugin system adds discovery, isolation, versioning, UI extension APIs, and support burden. That is not the right first move.

## 24.2 What we will do instead

Use **internal extension seams**:

* new template types
* new run modes
* new problem parsers
* new diagnostics
* optional vendored tool integrations

This gives future flexibility without premature architecture complexity.
Vendored tooling (when used) should remain pure-Python, live behind internal interfaces, and pass explicit quality/performance gates before cutover.

---

## 25. Recommended MVP Vertical Slice

The first end-to-end slice should prove the core value of the product:

1. Open a project folder
2. Open and edit `main.py`
3. Save changes
4. Press Run
5. Launch separate runner process
6. Show stdout in console
7. Show traceback on failure
8. Write per-run log
9. Stop run if needed

If this slice works well, the platform is real.

Everything else should build on top of this slice.

---

## 26. Out of Scope for v1

The architecture explicitly does **not** require v1 support for:

* advanced debugger parity beyond baseline line breakpoints/stepping/inspection
* LSP and language servers
* Git integration
* package management
* marketplace/plugins
* collaborative editing
* background code intelligence daemons
* generalized sandboxing
* GUI-dependent FreeCAD export workflows

These may come later, but they must not distort v1.

---

## 27. Architecture Decisions

## AD-001: Separate editor and runner processes

**Decision:** User code always runs outside the editor process.
**Why:** crash isolation, responsiveness, simpler supervision.

## AD-002: Filesystem-first project model

**Decision:** Projects are plain folders with human-readable metadata.
**Why:** easy backup, support, inspection, and AI friendliness.

## AD-003: JSON manifest for runs

**Decision:** Runner launches from a manifest file, not complex command strings.
**Why:** robustness, debuggability, deterministic boot.

## AD-004: JSON for canonical project metadata; SQLite only for caches

**Decision:** `project.json` is canonical.
**Why:** transparency and portability.

## AD-005: No plugin system in v1

**Decision:** internal seams only.
**Why:** complexity budget must stay focused on core stability.

## AD-006: Capability probe on startup

**Decision:** never assume runtime features without checking.
**Why:** constrained environment and supportability.

---

## 28. Suggested Implementation Order

1. bootstrap + logging
2. project open/save model
3. basic tabbed editor
4. run manifest creation
5. runner bootstrap
6. stdout/stderr capture
7. traceback + log handling
8. stop/terminate flow
9. templates
10. search/quick open
11. support bundle
12. optional indexing/linting

---

## 29. Canonical File Ownership

To reduce ambiguity for humans and AI agents:

* `PRD.md` defines **what** the product must do
* `DISCOVERY.md` defines **what the environment supports**
* `ARCHITECTURE.md` defines **how the system is structured**
* `ACCEPTANCE_TESTS.md` defines **how success is validated**
* `TASKS.md` defines **implementation slices**
* `AGENTS.md` defines **how AI agents should work in this repo**

If a change affects system structure, update `ARCHITECTURE.md`.

---

## 30. Bottom Line

The optimal architecture for ChoreBoy Code Studio is:

* a **Qt editor shell**
* running inside **FreeCAD AppRun**
* with a **strictly separate runner process**
* using a **filesystem-first project model**
* driven by **JSON manifests and logs**
* with **SQLite only as an optional acceleration layer**
* and designed for **thin-slice AI-assisted implementation**

This is the highest-leverage architecture because it matches the environment, contains risk, stays supportable, and gives AI agents clean boundaries to work within.
