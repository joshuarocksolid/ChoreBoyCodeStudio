# ChoreBoy Code Studio — Architecture (v1)

## 1. Purpose

This document defines the target architecture for **ChoreBoy Code Studio**, a project-first editor and runner for building Python applications inside the constraints of the ChoreBoy environment.

It translates the product intent from `PRD.md` and the runtime facts from `DISCOVERY.md` into a concrete technical design that is:

- reliable on locked-down ChoreBoy systems
- friendly to AI-assisted development
- resilient to user-code crashes
- simple enough to ship and support
- extensible enough to grow beyond MVP

This architecture is the canonical source of truth for:

- process boundaries
- module boundaries
- runtime contracts
- project layout
- persistence strategy
- run lifecycle
- error handling
- extension points
- implementation sequencing

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

- small modules
- explicit contracts
- minimal hidden coupling
- strong conventions
- thin vertical slices

### 2.5 Progressive enhancement

MVP should deliver real value without requiring advanced services like LSP or heavy indexing.

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
9. Optional pure-Python vendored packages are acceptable by default. Compiled dependencies require an explicit runtime-parity spike and a supported in-process load path (for example the proven memfd strategy), and must not be introduced casually.

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

- JSON files
- JSON Lines
- plain stdout/stderr
- explicit paths
- explicit exit codes

Avoid magic imports, implicit globals, and hidden IPC complexity.

## 4.4 Bootstrapping must be deterministic

Because the AppRun launch environment is unusual, startup must be explicit:

- known entry script
- known working directory
- known path setup
- known log destination
- known run manifest

## 4.5 Capability probing over assumption

At startup, the editor should probe what the local runtime supports and adapt or warn accordingly.

## 4.6 Small replaceable modules

Subsystems should be independently swappable:

- editor shell
- project store
- runner bridge
- indexing
- linting
- templates
- support bundle generation

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
4. Editor loads `cbcs/project.json` and project files.
  If metadata is missing but the folder is a Python project, editor bootstraps canonical
   `cbcs/project.json` metadata on first open, then proceeds through normal load.
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

- main window and menus
- project tree
- tabbed editors
- save/autosave
- search and quick open
- run configuration UI
- launching and supervising runner processes
- displaying console/problems/logs
- global and per-project settings
- support bundle generation
- capability probe and compatibility reporting

The editor process must **never** execute arbitrary user project code directly.

## 6.2 Runner Process

The runner process is responsible for:

- receiving run instructions
- setting up `sys.path`
- choosing execution mode
- executing the selected entry point
- writing per-run logs
- streaming stdout/stderr
- surfacing exception tracebacks
- returning a final exit status

The runner is disposable and isolated. Each run gets a fresh process.

## 6.3 Optional Background Workers

For v1, background tasks should remain simple and in-process where possible. Examples:

- file indexing
- find-in-files
- project health check
- syntax/lint scans

If a background job proves expensive, it can later be moved to a dedicated worker process. That should be a future optimization, not an MVP requirement.

Current editor architecture uses two explicit in-process worker lanes instead of ad-hoc
threads:

- `GeneralTaskScheduler` for bounded keyed shell work such as linting and other blocking
coordination tasks
- `SemanticSession` over `SemanticWorker` for all semantic-engine ownership and request
serialization

This keeps shell work cancellable, avoids duplicated thread ownership of semantic engines,
and makes shutdown behavior explicit.

---

## 7. Launch and Bootstrap Strategy

## 7.1 Boot model

All application launch should be rooted in real Python files, not long inline strings, except for the minimal `AppRun -c` bridge required to enter the runtime.

Recommended pattern:

- `launcher.py` or equivalent host-side bootstrap triggers AppRun
- AppRun invokes a tiny stable boot file
- boot file imports the real application package

### Recommended boot style

```python
/opt/freecad/AppRun -c 'import os,runpy,sys;root="/absolute/path/to/repo";sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path("/absolute/path/to/run_editor.py", run_name="__main__")'
```

And similarly for runner:

```python
/opt/freecad/AppRun -c 'import os,runpy,sys;root="/absolute/path/to/repo";sys.path.insert(0,root) if root not in sys.path else None;os.chdir(root);runpy.run_path("/absolute/path/to/run_runner.py", run_name="__main__")'
```

## 7.2 Why this design

This keeps the unusual AppRun invocation surface extremely small and pushes real logic into normal Python files, where architecture, imports, logging, and testing are easier to reason about.

## 7.3 Path rules

Boot scripts must immediately normalize:

- absolute app root
- project root
- working directory
- log path
- `sys.path` ordering

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

For breakpoint-driven debug sessions. This mode executes user code inside the
runner process under debugger control and accepts structured debug commands from
the editor.

### `python_debug` design rules

`python_debug` must follow a stricter contract than normal run mode:

- stdout/stderr remain the user-facing output channel for program prints,
tracebacks, and run logs
- debugger control and inspector state travel over a dedicated editor<->runner
debug channel, not over ad-hoc stdout markers
- the editor process never executes debug-target project code directly
- breakpoint, watch, frame, scope, and exception data are structured, bounded,
and explicit

Because ChoreBoy production heavily restricts subprocess execution, the debugger
engine must pass a runtime-parity decision gate before cutover. The preferred
target is an AppRun-safe `debugpy`/pydevd path that avoids the normal adapter
subprocess requirement. The fallback is a custom in-runner `bdb` engine on the
same editor-side contracts. The shipped product must not carry long-lived
parallel debug engines beyond the decision gate.

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
  run_plugin_host.py
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
      background_tasks.py
      main_thread_dispatcher.py
      menus.py
      actions.py
      status_bar.py
      style_sheet.py
      style_sheet_sections.py
      settings_dialog.py
      settings_dialog_sections.py
      editor_workspace_controller.py
      editor_intelligence_controller.py
      local_history_dialog.py
      history_restore_picker.py
    editors/
      __init__.py
      code_editor_widget.py
      code_editor_semantics.py
      code_editor_search.py
      code_editor_editing.py
      code_editor_diagnostics.py
      editor_tab.py
      editor_manager.py
      ini_highlighter.py
      syntax_engine.py
      syntax_registry.py
      search_panel.py
      quick_open.py
    treesitter/
      __init__.py
      loader.py
      language_registry.py
      highlighter.py
      queries/
        python.scm
        python.locals.scm
        json.scm
        javascript.scm
        javascript.locals.scm
        html.scm
        html.injections.scm
        xml.scm
        css.scm
        bash.scm
        markdown.scm
        markdown.injections.scm
        yaml.scm
        toml.scm
        sql.scm
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
      host_process_manager.py
      process_supervisor.py
      console_model.py
      problem_parser.py
    debug/
      __init__.py
      debug_models.py
      debug_session.py
      debug_transport.py
      debug_protocol.py
      debug_breakpoints.py
    plugins/
      __init__.py
      api_broker.py
      manifest.py
      models.py
      discovery.py
      package_format.py
      registry_store.py
      installer.py
      exporter.py
      contributions.py
      security_policy.py
      trust_store.py
      rpc_protocol.py
      host_supervisor.py
      runtime_manager.py
      host_runtime.py
    runner/
      __init__.py
      runner_main.py
      execution_context.py
      traceback_formatter.py
    persistence/
      __init__.py
      settings_store.py
      sqlite_index.py
      atomic_write.py
      autosave_store.py
      history_models.py
      local_history_store.py
      history_retention.py
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

- app shell
- project logic
- run logic
- persistence
- bootstrapping
- support tooling

That makes the codebase more legible to both humans and AI agents.

---

## 10. Project-on-Disk Model

Each user project is a plain folder.

Recommended project shape:

```text
my_project/
  cbcs/
    project.json
    settings.json
    plugins.json
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
<project>/cbcs/project.json
```

If the folder is opened without existing metadata and contains Python source files, the
editor initializes this file automatically with canonical defaults and an inferred entrypoint.
The initialized file remains the single source of truth going forward.

This file should be human-readable JSON and contain:

- project name
- stable project id
- schema version
- default entry point
- default working directory
- saved run configurations
- template type
- optional env overrides
- optional project notes

### Example

```json
{
  "schema_version": 1,
  "project_id": "proj_a1b2c3d4e5f6",
  "name": "My Project",
  "default_entry": "main.py",
  "working_directory": ".",
  "template": "utility_script",
  "run_configs": []
}
```

## 10.2 Why JSON, not SQLite, for primary project metadata

- easy to inspect
- easy to copy
- easy for support
- easy for AI agents
- resilient under partial project transfer

SQLite can still be used for caches and indexes, but not for the project’s primary identity.

## 10.3 Project settings overrides

Per-project settings overrides are stored at:

```text
<project>/cbcs/settings.json
```

This file follows the same JSON shape as global settings, but only project-overridable root sections are honored:

- `editor`
- `intelligence`
- `linter`
- `file_excludes`
- `output`

Effective settings resolution is:

1. hardcoded defaults
2. global settings (`~/choreboy_code_studio_state/settings.json`)
3. project overrides (`<project>/cbcs/settings.json`)

Global-only settings (for example theme mode, keybindings, syntax color overrides, layout state, and last project path) remain in global state and are ignored when present in project settings files.

---

## 11. Global App State

Global app state should live under a single dedicated home path, for example:

```text
~/choreboy_code_studio_state/
```

Recommended contents:

```text
~/choreboy_code_studio_state/
  settings.json
  recent_projects.json
  logs/
  cache/
  history/
    index.sqlite3
    blobs/
  plugins/
    registry.json
    installed/
    logs/
  state.sqlite3
  crash_reports/
```

## 11.1 What belongs here

- recent projects
- editor preferences (global defaults)
- global shortcuts/preferences
- syntax-color customization overrides (light/dark token maps)
- linter runtime settings (global enable/disable + selected provider)
- linter rule profile overrides (enablement + severity)
- last-opened window layout
- compatibility probe results cache
- optional global search/index cache
- editor crash logs
- local history drafts, checkpoints, labels, and deleted-file tombstones
- global plugin registry, installs, and plugin host logs

## 11.2 What does not belong here

- project source files
- project logs that should travel with the project
- project-specific run configs

---

## 12. Module Responsibilities

## 12.1 `bootstrap`

Handles:

- path normalization
- environment detection
- logging setup
- capability checks

No UI logic. No project logic.

## 12.2 `core`

Shared models, enums, constants, and errors.

This layer should have minimal dependencies and be import-safe everywhere.

## 12.3 `shell`

Owns the main window and top-level composition.

It coordinates services but should not contain deep business logic.

Current implementation keeps `MainWindow` as composition root and delegates
domain orchestration to focused shell controllers:

- `project_controller` for open/recent project flows
- `run_session_controller` for run/debug/repl lifecycle control wiring
- `project_tree_controller` for tree move/delete/remap side effects
- `editor_workspace_controller` for open-editor ownership and monotonic buffer revisions
- `editor_intelligence_controller` for semantic request routing and inline result formatting
- `background_tasks` for keyed off-UI-thread task execution and replacement
- `settings_dialog_sections` and `style_sheet_sections` for decomposed UI construction and styling builders

Key shell responsibilities include:

- run/debug toolbar and action state mapping
- split-pane layout persistence and reset behavior
- project-tree context action wiring
- bottom-pane composition (console, Python console, problems, debug inspector, run log)
- runtime/onboarding presentation such as welcome surfaces, status summaries, drill-down actions, and help entry points
- owning the worker/controller graph without becoming the implementation home for each workflow

## 12.4 `editors`

Text editing behavior:

- `CodeEditorWidget` composed from focused mixins for semantics, search, editing transforms,
and diagnostics overlays
- tabs
- dirty state
- syntax highlighting
- tree-sitter-driven `QSyntaxHighlighter` pipeline with separate `highlights`, `locals`, and `injections` query layers
- language/query registry (extension + sniff based) for deterministic tree-sitter language resolution, plus manual language override from the shell
- incremental parse updates (`tree.edit` + `parser.parse(source, old_tree)`) with changed-range capture refresh
- locals-aware semantic roles for parameters, imports, variables, classes, and constructors without reintroducing generic Python identifier coloring
- embedded-language injections for HTML `<script>/<style>` blocks and Markdown fenced code / HTML blocks
- adaptive highlighting modes (`normal`, `reduced`, `lexical_only`) driven by shared document-size thresholds
- viewport-window query execution for large buffers (reduced + lexical_only modes)
- no semantic `ExtraSelection` overlay pipeline in the editor path
- token inspector action for capture/token debugging, plus `.desktop` / INI regex fallback when no practical tree-sitter wheel exists
- line numbers and breakpoint gutter markers
- search within file
- quick open support
- code-navigation affordances (go-to-definition, breadcrumbs)

## 12.5 `project`

Filesystem/project abstraction:

- open project
- enumerate files
- validate project structure
- read/write project metadata

## 12.6 `run`

Editor-side execution subsystem:

- create run manifest
- launch runner
- read output
- update run state
- stop/terminate process

## 12.7 `runner`

Runner-side subsystem:

- load manifest
- configure execution
- redirect output
- execute entrypoint
- format failures
- finalize run result

## 12.8 `persistence`

Stores:

- settings
  - keybinding overrides
  - syntax-color overrides (theme-aware)
  - linter provider selection + global lint enable state
  - linter rule overrides
- atomic text-write helpers used by editor save paths
- autosave drafts
- local history checkpoints
- content-addressed revision blobs
- history retention and pruning state
- optional indexes
- lightweight caches

## 12.9 `templates`

Creates new projects from curated starter templates.

## 12.10 `support`

Diagnostics, health checks, runtime explanation models, report bundles, preflight checks,
and other support workflows.

## 12.11 `plugins`

Owns plugin lifecycle and contracts:

- manifest validation
- discovery and compatibility checks
- install/uninstall registry persistence
- declarative contribution registration
- workflow provider catalog and broker selection
- runtime plugin host IPC across query and job lanes
- project-scoped plugin policy in `cbcs/plugins.json`
- safe mode and failure quarantine controls
- bundled first-party plugin discovery

## 12.12 `intelligence`

Owns trusted language intelligence and refactoring contracts:

- semantic facade and typed result models
- project-aware semantic sessions and worker scheduling
- read-only semantic queries (completion, definition, hover, signatures, references)
- refactor planning and preview/apply orchestration
- coarse indexing and caches as acceleration only, never semantic truth

The intelligence layer should keep semantic engines behind narrow interfaces so the
shell and editor widgets do not depend on library-specific APIs directly.

---

## 13. Runner Contract

The runner contract is one of the most important parts of the system.

## 13.1 Input to runner

The editor should generate a **run manifest** as a JSON file before launch.

Recommended manifest contents:

- manifest version
- run id
- project root
- entry file
- working directory
- execution mode
- argv
- environment overrides
- log file path
- timestamp
- optional breakpoint payloads (for `python_debug`)
- optional debug transport metadata (for `python_debug`)
- optional exception-stop policy (for `python_debug`)
- optional runtime source remap data (for dirty-buffer debug sessions)

### Example

```json
{
  "manifest_version": 1,
  "run_id": "20260228_153500_001",
  "project_root": "/home/default/projects/my_project",
  "entry_file": "main.py",
  "working_directory": "/home/default/projects/my_project",
  "mode": "python_debug",
  "argv": [],
  "env": {},
  "log_file": "/home/default/projects/my_project/cbcs/logs/run_20260228_153500.log",
  "debug_transport": {
    "protocol": "cbcs_debug_v1",
    "host": "127.0.0.1",
    "port": 47123,
    "session_token": "debug_20260228_153500_001"
  },
  "debug_options": {
    "stop_on_uncaught_exceptions": true,
    "stop_on_raised_exceptions": false
  },
  "source_maps": [
    {
      "runtime_path": "/tmp/choreboy_code_studio/debug/run_123.py",
      "source_path": "/home/default/projects/my_project/app/main.py"
    }
  ],
  "breakpoints": [
    {
      "breakpoint_id": "bp_main_42",
      "file_path": "/home/default/projects/my_project/app/main.py",
      "line_number": 42,
      "enabled": true,
      "condition": "customer_count > 10",
      "hit_condition": 3
    }
  ]
}
```

## 13.2 Why manifest files instead of giant CLI argument strings

This architecture strongly prefers a manifest file over complex shell quoting because it is:

- more robust
- easier to debug
- easier to log
- easier for AI agents to generate and inspect
- less fragile in unusual launcher environments

## 13.3 Runner launch isolation

Runner subprocesses must be launched in a separate session:

- use `subprocess.Popen(..., start_new_session=True)` for run, debug, and Python console modes
- on stop, signal the runner process group so child processes are cleaned up with the session leader
- treat negative return codes as signal termination and surface signal details in shell status output

## 13.4 Runner output protocol

For baseline run mode, standard stdout/stderr is sufficient.

For `python_debug`, stdout/stderr are reserved for user-visible program output,
warnings, and tracebacks. Debugger traffic must use a dedicated structured
channel so:

- user prints do not corrupt debugger state
- debugger requests/replies are not parsed from arbitrary text
- the run log remains readable and supportable

Transition markers on stdout are acceptable only as short-lived migration aids;
they are not the steady-state debugger contract.

### 13.4A Debug control protocol

Debug control should use a local loopback transport with explicit messages for:

- session start/ready/error
- threads
- stack frames
- scopes
- variables
- watch evaluation
- continue/pause/step/disconnect
- breakpoint verification updates
- stop reasons (`breakpoint`, `pause`, `step`, `exception`)
- exception payloads

The protocol should be versioned, bounded, and resilient to partial failure. A
broken debug transport must fail the debug session clearly without corrupting
normal run-mode output handling.

## 13.5 Exit codes

Define clear meanings:

- `0`: success
- `1`: user code failed
- `2`: runner bootstrap/config failure
- `3`: manifest invalid
- `130`: terminated by user

---

## 14. Console, Problems, and Logs

## 14.1 Console

The console pane should show near-live stdout/stderr from the current run.

For responsiveness on high-output workloads, console buffering should be bounded and trim oldest entries once the configured cap is exceeded.

Current implementation also maintains a bounded run-output tail buffer for
traceback/problem extraction so very long runs do not accumulate unbounded
in-memory output strings.

For `python_debug`, the console remains the place for stdout/stderr, while the
Debug panel is driven by structured inspector state from the dedicated debug
channel.

## 14.2 Problems

The problems pane should show:

- syntax errors
- parse failures
- optional lint results
- runner-reported tracebacks summarized into clickable entries

## 14.3 Run Log

The run log pane should show saved per-run log content from disk, not only transient pipe output.
Current implementation refreshes the Run Log tab from the active run log file after run exit.

## 14.4 Application Log

The editor must write a persistent app log for the shell itself.

## 14.5 Log paths

Editor log:

```text
~/choreboy_code_studio_state/logs/app.log
```

Project run logs:

```text
<project>/cbcs/logs/run_YYYYMMDD_HHMMSS.log
```

## 14.6 Logging requirements

All logs should include:

- timestamp
- level
- subsystem
- message

Tracebacks should always be fully preserved in logs, even if the UI shows a summarized version.

---

## 15. Error Handling and Failure Model

## 15.1 Error categories

Use clear categories:

- bootstrap errors
- project validation errors
- editor UI errors
- runner launch errors
- user code errors
- headless/GUI capability errors
- filesystem permission errors
- support bundle errors

## 15.2 User-facing failure principles

- never fail silently
- always preserve traceback somewhere
- always preserve unsaved text when possible
- surface actionable error messages
- link errors to log file or support bundle

## 15.3 Crash popup

A crash dialog should show:

- short explanation
- full traceback
- copy-to-clipboard
- open log folder
- build support bundle

---

## 16. Editor State Model

Each open tab should track:

- file path
- original contents hash
- current contents
- modified state
- last save time
- syntax mode
- cursor position
- scroll position

This allows stable reopen and recovery workflows.

## 16.1 Autosave strategy

Recommended v1 behavior:

- autosave drafts to a recovery store
- debounce draft writes to avoid per-keystroke disk churn
- do not silently overwrite source files unless autosave-to-file is explicitly enabled
- restore drafts after crash

This is safer for support and easier to reason about.

## 16.2 Local history strategy

Autosave drafts and local history solve related but different problems and should
remain distinct in the architecture:

- **drafts** protect the latest unsaved dirty-buffer state after crash or abnormal
exit
- **checkpoints** provide a bounded timeline of durable, user-reviewable restore
points across saves and high-risk multi-file edits

The shipped local-history design should follow these rules:

- store history in a visible global app-state location under
`~/choreboy_code_studio_state/history/`
- use a metadata index plus content-addressed full-text blobs rather than
fragile patch chains as the canonical source of truth
- treat diffs as a derived presentation layer, generated lazily for review UI
- create durable checkpoints for successful saves, explicit snapshots/labels,
external-file reload decisions, and multi-file refactor/import-update applies
- keep draft writes debounced and lightweight; do not turn every keystroke into a
durable history revision
- restore history revisions into the editor buffer first, not directly onto disk,
so the user can review and save explicitly
- keep restore and diff workflows independent of Git so the feature remains
understandable for ChoreBoy users who do not use version control

## 16.3 File identity and path lineage

Local history must survive app-driven move, rename, and delete operations.

That requires:

- a stable project identity in canonical project metadata
- a stable logical file key in the history index that is not just the current
absolute path
- lineage updates on move/rename so a file keeps one timeline across path
changes
- tombstones for deleted files so restore flows can recover them after the live
filesystem entry is gone

---

## 17. Search and Indexing

## 17.1 v1 approach

Start with filesystem-based search and optional in-memory indexing.

Current implementation uses cooperative-cancel search workers and line-streaming
file scans so cancellation and first-result latency remain responsive.

## 17.2 SQLite-backed index

If project size justifies it, use SQLite for:

- file inventory
- quick-open candidate cache
- symbol cache
- search acceleration

Current implementation stores per-file symbol index fingerprints
(`mtime_ns` + file size) so symbol indexing can update incrementally instead of
rebuilding every file on each pass.

## 17.3 Design rule

Indexing is an optimization layer, not a source of truth. If index state is stale or missing, the editor must still function.

## 17.4 Trusted Python semantics

Python intelligence must separate fast structural acceleration from semantic truth.

Current implementation already has a useful speed layer:

- tree-sitter for lexical/editor structure
- SQLite for project symbol cache and quick lookup
- background workers for incremental refresh

That layer should remain, but only as an optimization layer. The source of truth for
Python semantics should live in a dedicated semantic engine layer behind a facade.

### 17.4.1 Semantic facade contract

The shell and editors should talk to a focused semantic facade that returns typed
results with explicit metadata such as:

- engine
- source
- confidence
- latency
- stale/fallback state
- unsupported reason

This keeps UI policy separate from library-specific implementation details and makes
degradation states visible instead of silent.

### 17.4.2 Engine boundaries

For Python, the long-term architecture is:

- a read-only semantic engine for completion, definition, hover, signatures, and references
- a refactor engine for project-wide rename and related safe edits
- SQLite/tree-sitter acceleration beneath those engines, not beside them as competing truth sources

The editor must not silently combine lexical hits and semantic hits under the same
feature label. If a result is approximate, the UI should say so explicitly.

### 17.4.3 Worker model

Semantic queries must not block the Qt UI thread.

Because editor buffers need unsaved-text awareness and some semantic libraries have
thread-safety constraints, Python semantic work should run through a dedicated,
serialized worker/session model per project rather than ad-hoc parallel background
threads.

The concrete contract is:

- `SemanticSession` owns the semantic facade and completion service
- `SemanticWorker` is the only thread allowed to touch that owned semantic state
- async and blocking semantic helpers both flow through that same worker so hover,
signature help, completion, definition, references, and rename planning share one
ownership model

### 17.4.4 Safety rules

Read-only semantic queries must never execute arbitrary user code in the editor
process. Prefer static/project analysis APIs over interpreter-style execution.

Project-local caches created by semantic engines must respect ChoreBoy filesystem
constraints:

- no hidden dot-prefixed directories
- visible cache/state paths only
- no silent creation of engine-owned metadata directories in user projects

### 17.4.5 Refactor rule

Refactors that claim semantic safety must use a trustable planner. Token replacement
and text-search fallbacks may still exist as explicit user workflows, but not as
silent backups for semantic rename/reference operations.

### 17.4.6 Rollout sequencing

The semantic trust improvement is delivered through a sequenced slice plan:

1. **Contract lock** — architecture, acceptance, and backlog alignment (I01).
2. **Fixture corpus** — representative test projects and failing contract tests
  that expose heuristic trust gaps (I02).
3. **Runtime-parity spike** — Jedi/Rope validated under AppRun with no hidden
  engine metadata paths (I03).
4. **Facade hardening** — deterministic `sys.path`, typed confidence metadata,
  explicit degradation states (I04).
5. **Read-only cutover** — replace heuristic completion/definition/hover/signatures/
  references with project-aware semantic queries (I05).
6. **Rename cutover** — Rope-backed planner with grouped patch previews, rollback,
  no token-replace fallback (I06).
7. **Trust UX and performance** — inline confidence indicators, async/cancellable
  completion, latency gates (I07).

Each slice updates tests and documentation before proceeding. Slices may not
silently merge heuristic and semantic results under the same feature label.

### 17.4.7 Buffer revision rule

Async editor results must be tied to the buffer revision they were requested from.

That means:

- editor-owned buffer revisions advance on every meaningful document replacement/edit
- diagnostics and semantic callbacks must verify the current revision before applying UI
state
- stale results are dropped instead of overwriting newer editor state

## 17.5 Real Python formatting and import management

If the editor exposes "Format Current File" or "Format on save" for Python, the
behavior must be recognizable as real Python formatting rather than generic
whitespace cleanup.

### 17.5.1 Formatter and import-management contract

Python formatting and import management should follow a deterministic tool chain:

- generic text hygiene for universal save concerns such as trailing whitespace and
final newline handling
- import organization as a style/layout transform
- Black as the final Python formatting authority

This keeps generic editor hygiene separate from Python-specific style transforms and
ensures the final buffer matches user expectations for Black-formatted code.

### 17.5.2 Configuration source of truth

Phase-1 Python formatting/import management should honor only project-local
`pyproject.toml` configuration for advanced tool behavior:

- `[tool.black]`
- `[tool.isort]`
- `[project.requires-python]`

Code Studio settings should control workflow toggles such as:

- format on save
- organize imports on save
- status visibility

They should not become a second full style-configuration system that competes with
the Python ecosystem or silently composes with hidden per-user tool configs.

### 17.5.3 Execution and save-path rules

The shipped formatter/import stack must respect ChoreBoy runtime constraints:

- run in-process inside the editor runtime
- prefer vendored pure-Python dependencies by default
- do not depend on formatter/import CLI subprocesses
- apply explicit size/latency guardrails before introducing background complexity

Manual "Format Current File" and "Organize Imports" actions remain explicit user
commands. Save-time automation may chain them, but save reliability outranks style
automation:

- formatting/import failures must not discard user edits
- save should still write the current buffer when style tooling fails
- failure states must be understandable and visible in the UI

### 17.5.4 Boundaries with semantic and structural tooling

Import sorting is a deterministic style tool, not semantic truth.

That means:

- do not present import sorting as proof that imports are resolved correctly
- keep move/rename import rewrites separate from organize-imports behavior
- keep unsafe unused-import cleanup out of the phase-1 organize-imports path
- defer syntax-preserving structural import edits to the later semantic/refactor lane

Future structural import-management work can converge with the trusted-semantics
roadmap, but the initial formatting/import stack should stay small, predictable, and
supportable.

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

- working entrypoint
- example logging
- example error handling
- example project metadata
- README with how to run
- minimal consistent folder layout

## 18.3 Template versioning

Templates should have their own version marker so support and upgrades can reason about what a project was created from.

## 18.4 Example projects (Help-only)

Example projects are bundled under `example_projects/` at the repository root. They use the same `template.json` + source file layout as regular templates but are **not** discovered by the New Project template picker.

A dedicated `ExampleProjectService` (in `app/examples/example_project_service.py`) delegates to `TemplateService` with its own root path, keeping the boundary clean.

Example projects are only accessible through `Help > Load Example Project...`. This avoids cluttering the New Project workflow while giving users a rich, runnable starting point.

---

## 19. Capability Probe

At editor startup, run a lightweight compatibility probe.

Current startup checks should stay small, deterministic, and support-oriented. The
baseline probe covers:

- AppRun available
- PySide2 importable
- FreeCAD importable
- writable global settings path
- writable global log path
- writable temp path
- vendored Python tooling runtime availability

The probe should generate a user-visible compatibility summary.

This is especially important because environment assumptions are fragile in constrained systems.

---

## 19.1 Runtime explanation and onboarding layer

Capability data is only useful if the editor can explain it.

The shipped architecture should treat runtime explanation as a first-class layer rather
than scattered strings in status bars, message boxes, and docs.

### 19.1.1 Explanation sources of truth

Runtime/onboarding explanation should be built from structured facts, not ad-hoc UI copy:

- startup capability probe results
- project health checks
- runtime module inventory / importability probes
- run-target and run-configuration metadata
- packaging/export preflight results

### 19.1.2 Ownership boundary

Use a clear split:

- `support` owns machine-readable explanation models, issue classification, and preflight/report building
- `shell` owns summaries, drill-down presentation, quick actions, and welcome/help entry points
- `ui/help` and the printed manual own durable teaching content keyed to the same explanation topics

### 19.1.3 Progressive disclosure rule

The UX should follow three layers:

- compact status summaries for everyday awareness
- a dedicated drill-down surface for runtime/project explanation
- deeper help/manual content for concepts and workflows

This prevents the status bar from becoming noisy while still keeping supportable detail one click away.

### 19.1.4 Safety and performance rules

Runtime explanation must respect ChoreBoy constraints:

- never require terminal access in user-facing recovery steps
- never execute arbitrary user project code in the editor process to explain a problem
- keep startup probes lightweight; deeper checks run in background or on demand
- preserve structured issue IDs/evidence so support bundles and UI surfaces describe the same facts

### 19.1.5 Run/package preflight rule

For run and packaging workflows, explanation should happen before expensive or failure-prone
actions when the blocker is already knowable from editor-side state. Typical examples include:

- missing or invalid run target
- invalid run-configuration metadata
- package export path overlap
- excluded or missing packaged entry file

These checks should be treated as deterministic editor-side preflight, not delayed until
after a runner or packaging attempt fails.

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

- find in files
- indexing
- support bundle creation
- project health check
- large file loading
- local-history retention pruning
- global history search over deleted/moved entries

Current implementation explicitly offloads:

- find-in-files
- symbol indexing
- go-to-definition cache refresh path
- unresolved import analysis
- project health checks
- support bundle generation

to background workers/tasks to avoid blocking the UI thread.

## 21.3 Highlight pipeline performance gates

The editor highlighting contract is performance-gated with integration tests:

- Python tree-sitter full rehighlight at ~2,000 LOC: p95 <= 300ms (single-run target <= 250ms)
- incremental tree-sitter parse+capture refresh under typing-burst variants: p95 <= 140ms
- theme-switch apply cost across 10 open editors: p95 <= 150ms per editor
- large-file mode must keep capture-query work bounded (viewport-window query execution)
- bracket-match path must remain bounded on large files (no unbounded cursor-move scans)

These gates are part of release validation and should be updated only with explicit evidence.

## 21.4 Process-first for risky work

If work is expensive or failure-prone, prefer process boundaries over thread complexity.

That is especially consistent with the overall crash-isolation design.

---

## 22. Testing Strategy

## 22.1 Test pyramid for this project

### Unit tests

For:

- manifest creation
- settings parsing
- project metadata
- local-history index/blob helpers
- history retention and lineage rules
- problem parsing
- capability probe helpers

### Integration tests

For:

- opening a project
- saving a file
- recording local-history checkpoints on save
- draft recovery compare/restore
- deleted-file recovery and path-lineage restore
- creating a run manifest
- launching runner
- capturing stdout/stderr
- handling traceback
- stopping a process

### Manual acceptance tests

For:

- full MVP workflow on actual ChoreBoy environment
- template creation
- headless-safe execution
- log preservation
- support bundle export

## 22.2 Architecture rule

Critical contracts should be testable without bringing up the full editor UI when possible.

---

## 23. Versioning and Compatibility

## 23.1 Schema versioning

The following should have explicit version numbers:

- `cbcs/project.json`
- `cbcs/package.json`
- run manifest
- support bundle format
- template format
- distribution package manifest
- installed package marker

## 23.2 Migration policy

If schema changes, the app should migrate old project metadata in a controlled and logged way.

## 23.3 Compatibility target

The architecture should tolerate partial feature degradation better than hard refusal, as long as the core editor-runner path remains safe and understandable.

---

## 24. Extensibility Strategy

## 24.1 Plugin platform in v1

v1 includes a first-class plugin platform with two extension types:

- declarative contributions
- runtime code plugins

Runtime code plugins execute in an isolated plugin host process using explicit IPC
contracts. The editor process does not import plugin code directly.

Python workflow extensibility is provider-based rather than command-centric. Core shell
surfaces talk to a workflow broker, which resolves either built-in providers or runtime
plugin providers and keeps the shell in control of UI, buffer application, diagnostics
rendering, and supportability.

## 24.2 Plugin boundaries and contracts

Plugin contracts are explicit and versioned:

- plugin manifest schema (`plugin.json`)
- plugin API version compatibility
- declared capabilities, permissions, and activation events
- project-scoped plugin policy in `cbcs/plugins.json`
- typed workflow provider contracts for formatter/import-organizer/diagnostics/test/
template/packaging/runtime-explainer/FreeCAD-helper/dependency-audit lanes
- deterministic lifecycle (discover → validate → enable → activate → disable)

v1 distribution is offline-first through local folder or zip installation.
Publisher signing is not required in v1.
Bundled first-party plugins live in visible repo path `bundled_plugins/`.

Per-project plugin overrides and pinning are now explicit architecture, not deferred:

- projects can pin plugin versions
- projects can enable/disable plugins without changing global registry state
- projects can prefer specific workflow providers by kind/language

## 24.3 Workflow provider topology

The plugin host exposes two lanes:

- query lane for fast structured requests such as formatting, diagnostics, template
metadata, and runtime explainers
- job lane for long-running work such as pytest, packaging, dependency audit, and
FreeCAD helpers

This keeps the editor responsive while allowing richer workflow plugins than a simple
menu-command model would support.

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

## 25a. ChoreBoy-Native Dependency Management

In a no-terminal environment, dependency lifecycle must be fully GUI-driven.

### 25a.1 Project dependency manifest

Each project tracks third-party dependency decisions in a visible manifest:

```text
<project>/cbcs/dependencies.json
```

Schema fields per entry:

- `name` — package name
- `version` — declared or detected version
- `source` — ingestion source type (`wheel`, `zip`, `folder`, `runtime`)
- `classification` — `pure_python`, `native_extension`, or `runtime`
- `status` — `active` or `removed`
- `added_at` — ISO timestamp

### 25a.2 Ingestion workflow

The "Add Dependency" wizard accepts:

- `.whl` files — extracted into `vendor/`
- `.zip` files containing Python packages — extracted into `vendor/`
- folders — copied into `vendor/`

Classification runs at ingestion time, detecting compiled extensions and flagging
ChoreBoy compatibility risks.

### 25a.3 Safety rules

- all dependency paths use visible (non-dot-prefixed) directories
- ingestion never modifies system paths or global state
- native-extension packages require explicit user acknowledgment
- the manifest is the source of truth for packaging validation

### 25a.4 Packaging integration

The packaging workflow reads `cbcs/dependencies.json` to validate that vendored
dependencies are present and consistent before export.

---

## 25b. First-Class Testing Workflow

### 25b.1 Test discovery model

Test discovery uses `pytest --collect-only -q` to build a tree of test items
with file/class/function hierarchy and pytest node IDs for targeted execution.

### 25b.2 Run scopes

- **Run All Tests** — project-wide pytest execution
- **Run File Tests** — pytest execution scoped to one test file
- **Run Test at Cursor** — pytest execution for one test function using node ID
- **Rerun Failed** — re-execute only previously failed test node IDs
- **Debug Failed Test** — launch the first failed test under debug mode

### 25b.3 Test explorer panel

The test explorer is a tree view in the left sidebar showing discovered tests.
Each node shows last-run status (pass/fail/skip/not-run). Context menu provides
Run and Debug actions per node.

### 25b.4 Result persistence

Test results are persisted per project and restored on session reload.
Failures feed into the Problems pane with jump-to-source.

---

## 26. Architecture Decisions

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

## AD-005: Plugin platform with isolated host in v1

**Decision:** ship plugin support in v1 with process-isolated runtime plugins and declarative contributions.
**Why:** users need modular extensibility without core product bloat.

## AD-006: Capability probe on startup

**Decision:** never assume runtime features without checking.
**Why:** constrained environment and supportability.

## AD-007: Separate semantic truth from structural acceleration

**Decision:** SQLite and tree-sitter remain acceleration layers, while trusted Python
semantics move behind a dedicated semantic facade and engine layer.
**Why:** the current name/token heuristics are fast but not trustworthy enough for
serious Python workflows, especially across imports, shadowing, and project-wide
rename/reference operations.

## AD-008: In-process semantic engines only by default

**Decision:** the shipped Python semantic core must use in-process libraries that fit
AppRun/AppArmor constraints; server/protocol or Node-backed engines are deferred
unless a runtime-parity spike proves them safe and supportable.
**Why:** ChoreBoy heavily restricts subprocess execution, and reliability is more
important than reusing desktop-IDE architecture patterns that assume unconstrained
sidecar processes.

## AD-009: No hidden engine metadata paths

**Decision:** semantic/refactor engines must not rely on hidden directories such as
`.jedi` or `.ropeproject` in user projects or hidden cache roots under Home.
**Why:** hidden directories are unreliable on ChoreBoy and conflict with the
filesystem-first, supportable project model.

## AD-010: In-process, project-local pyproject-aware Python formatting stack

**Decision:** ship Python formatting/import management through in-process adapters
over vendored Black and isort, using project-local `pyproject.toml` as the only
advanced configuration surface in phase 1. Black remains the final formatting
authority, while organize-imports stays a deterministic style step rather than a
semantic or structural refactor engine.
**Why:** ChoreBoy's runtime heavily constrains subprocess execution, hidden/global
tool configuration is harder to support, and users need trustworthy formatting
behavior without conflating style tools with semantic truth.

## AD-011: Local history is a first-class editor safety feature

**Decision:** ship a native local-history subsystem independent of Git, with
clear draft-vs-checkpoint semantics and restore-to-buffer workflows.
**Why:** ChoreBoy users need trustworthy recovery and diff tools even when they
do not use version control or have terminal access.

## AD-012: Global visible store for local history

**Decision:** store local-history data under the visible global app-state root
instead of hidden folders or per-project-only metadata.
**Why:** this survives deleted-file accidents better, fits ChoreBoy's visible-path
constraints, and avoids inflating project folders with heavy safety data.

## AD-013: Full-text blobs are canonical; diffs are derived

**Decision:** keep canonical history entries as full-text snapshot blobs plus
metadata index rows, while generating diffs lazily for UI review.
**Why:** full-text snapshots are simpler to validate, restore, prune, and recover
from than patch-chain-first storage.

## AD-014: Restore to buffer before disk

**Decision:** local-history and draft restore flows should place restored content
into the live editor buffer first and require an explicit save to update the
source file on disk.
**Why:** this preserves user trust, keeps undo/cursor context intact, and avoids
silent destructive overwrites during recovery.

## AD-015: `MainWindow` stays a composition root

**Decision:** keep `MainWindow` responsible for wiring controllers, views, and
cross-cutting services, while moving workflow logic into focused shell/editor modules.
**Why:** section 8 of the next-level editor analysis identified shell sprawl as a
direct drag on reliability and future feature velocity.

## AD-016: Single-owner semantic session

**Decision:** semantic engines and completion orchestration live behind one
project-scoped `SemanticSession`/`SemanticWorker` ownership model.
**Why:** trusted semantic libraries need unsaved-buffer context, deterministic
serialization, and explicit shutdown without competing thread ownership.

## AD-017: Bounded keyed background scheduler

**Decision:** generic shell background work uses a reusable bounded scheduler with
keyed cancellation/replacement semantics instead of ad-hoc thread spawning.
**Why:** this keeps UI-facing background work diagnosable, cancellable, and less
likely to accumulate leaked or duplicated threads.

## AD-018: Revision-gated async UI updates

**Decision:** diagnostics and asynchronous editor-intelligence results must be
validated against the current buffer revision before mutating editor UI state.
**Why:** stale async results are a correctness bug in an editor; dropping them is
safer than racing newer buffer state.

## AD-019: Packaging is manifest-driven with installable as the default profile

**Decision:** product distribution and in-app project exports share one
manifest-driven packaging substrate. Project-side packaging metadata lives in
`cbcs/package.json`, installable packages are the supported default, and portable
packages remain a stricter profile that resolves package root from the launcher
location.
**Why:** ChoreBoy packaging has to stay AppRun-native, supportable, and explicit
about upgrade/install behavior under `noexec`, offline-first, and no-terminal
constraints. A shared manifest/installer contract is safer than letting product
and project packaging drift independently.

---

## 27. Suggested Implementation Order

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

## 28. Canonical File Ownership

To reduce ambiguity for humans and AI agents:

- `PRD.md` defines **what** the product must do
- `DISCOVERY.md` defines **what the environment supports**
- `ARCHITECTURE.md` defines **how the system is structured**
- `ACCEPTANCE_TESTS.md` defines **how success is validated**
- `TASKS.md` defines **implementation slices**
- `AGENTS.md` defines **how AI agents should work in this repo**
- `PACKAGING.md` defines the **ChoreBoy-specific distribution packaging and installer contract**
- `docs/designer/ARCHITECTURE_PLAN.md` defines the **Designer subsystem plan** (`.ui` builder module boundaries, contracts, and rollout), with companion wireframe/backlog docs in `docs/designer/`
- `docs/plugins/PRD.md` defines the **Plugin subsystem plan** (manifest, lifecycle, host process, and rollout)

If a change affects system structure, update `ARCHITECTURE.md`.

---

## 29. Bottom Line

The optimal architecture for ChoreBoy Code Studio is:

- a **Qt editor shell**
- running inside **FreeCAD AppRun**
- with a **strictly separate runner process**
- using a **filesystem-first project model**
- driven by **JSON manifests and logs**
- with **SQLite only as an optional acceleration layer**
- and designed for **thin-slice AI-assisted implementation**

This is the highest-leverage architecture because it matches the environment, contains risk, stays supportable, and gives AI agents clean boundaries to work within.