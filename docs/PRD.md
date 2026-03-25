# ChoreBoy Code Studio — PRD (v1)

## 1) Problem Statement

ChoreBoy users can’t install their own applications (“User modifications…not possible”), yet there is growing demand for building *real* software/projects on the machine—not just editing text or writing small macros. 

You’ve discovered a new capability: launch standalone Qt (PySide2) apps using FreeCAD’s packaged Python runtime via `/opt/freecad/AppRun -c ...` with filesystem write access, SQLite, subprocess, and a reliable debugging/log model.  

**We want to turn that into a “developer workstation experience” inside ChoreBoy’s constraints.**

---

## 2) Goals (What success looks like)

### Primary goals

1. **Create/edit/run Python projects** that execute inside the FreeCAD AppRun runtime (pure python, PySide2 UI available). 
2. **Project-first workflow**: folders, multiple files, templates, “Run”, console output, tracebacks, logs.
3. **Robust debugging experience** without external tools:

   * persistent log file
   * crash popup with full traceback
   * breakpoint-driven debug flow with stack, variable, watch, and exception inspection inside the app
     The log/traceback model is still the fallback safety net and must remain first-class.
4. **Safe + predictable** on ChoreBoy: no system installs required; everything ships as a folder under Home and runs reliably.

### Secondary goals

* Lightweight “IDE” features: search, go-to line, basic linting, format-on-save (optional).
* Easy backup/export to USB (fits how ChoreBoy users already manage data).  
* Modular plugin model so advanced users can extend behavior without bloating core workflows.

---

## 3) Non-goals (v1)

* Full VSCode/IntelliJ parity (LSP breadth, advanced refactors, remote debugging, git integrations).
* Installing packages system-wide, or depending on OS packages not shipped with FreeCAD.
* Internet-based workflows (ChoreBoy is LAN-only; no general internet). 
* Internet marketplace and publisher-signing dependency for plugin installation.

---

## 4) Constraints & Realities (Design must respect these)

1. **Locked down system**: users cannot install editors/IDEs. 
2. **Runtime**: Python is the FreeCAD embedded runtime (confirmed path + version in discovery), and PySide2 exists there. 
3. **Launching model**: most reliable is spawning AppRun detached (`start_new_session=True`). 
4. **GUI vs headless**: some FreeCAD exports fail in console mode (“Cannot load Gui module…”). Code Studio must treat that as a known limitation and guide users to headless-safe paths. 
5. **Persistence**: SQLite works and is ideal for local settings/indexing; Postgres drivers aren’t present but vendoring `pg8000` is proven and fast.  

---

## 5) Target Users & Use Cases

### Personas

* **Builder (power user)**: wants to create reusable ChoreBoy tools (reports, data entry, geometry generators).
* **Tinkerer (intermediate)**: wants to adjust scripts safely, run them, see output/errors.
* **Dealer/Integrator**: ships curated apps/projects to customers via USB.

### Core use cases (v1)

1. Open an existing project folder from Home/USB → browse files → edit → run.
2. Create a new project from template (Qt app, headless FreeCAD tool, CLI-style script).
3. Run script and see console output + traceback + open log file location.
4. Export/share project to USB as a single zip/folder.

---

# 6) Product Approach (Optimal path)

## Key architectural decision: “Editor process” vs “Runner process”

**Optimal approach:** Code Studio UI runs as one AppRun-launched Qt app, and **all user code executes in a separate AppRun-launched runner process**.

Why this is optimal on ChoreBoy:

* User code crashes won’t kill the editor.
* Long jobs won’t freeze the editor (runner can be supervised).
* Output capture is clean (stdout/stderr).
* It matches the launch method you already validated. 

### Execution pipeline

* Code Studio spawns:
  `['/opt/freecad/AppRun', '-c', 'import os,runpy,sys; ...; runpy.run_path(".../run_runner.py", run_name="__main__")']`
* Runner receives:

  * project root
  * entry script
  * args
  * run mode (normal / headless FreeCAD / Qt app)
* Runner streams stdout/stderr back to Code Studio (pipe or file tail).
* Runner streams stdout/stderr back to Code Studio via pipes.

### Plugin execution pipeline (v1)

* Plugins are discovered from local filesystem packages.
* Declarative plugin contributions are validated before activation.
* Runtime plugin code executes in a dedicated plugin host process.
* The editor communicates with runtime plugins through explicit IPC contracts.
* Plugin host failures do not terminate the editor process.

---

# 7) Information Architecture & UI Layout

## Main window layout (default)

A familiar “IDE tri-pane” that works well even for non-developers:

### Left sidebar: Project

**Tabs:**

* **Files** (default): tree view of project folder
* **Search**: “Find in files”
* **Outline**: symbols in current file (simple parsing)

**Files pane features**

* Open folder
* New file / New folder
* Rename / Move to Trash (with confirmations)
* “Reveal in File Manager” (important for ChoreBoy habits)

### Center: Editor

* Tabbed editor (`.py`, `.json`, `.md`, `.ui`, `.txt`)
* Status bar: line/col, file encoding, modified, active interpreter (“FreeCAD AppRun Python”)
* Basic code features:

  * syntax highlight (Python v1)
  * indent/outdent
  * comment/uncomment
  * go-to line

### Bottom: Output + Problems

**Tabs:**

* **Console** (stdout/stderr)
* **Problems** (lint results, parse errors)
* **Tasks** (background ops: indexing, search, etc.)

### Right sidebar (optional, collapsible)

* **Properties / Run Config** panel:

  * Entry point
  * Arguments
  * Working directory
  * “Run with FreeCAD headless backend” toggle
  * Environment variables (limited, stored per project)

---

## Menus & Commands (concrete)

### File

* New Project…
* Open Project…
* Open Recent ▶
* Quick Open…
* Save / Save As / Save All
* Export Project to USB…
* Zip Project…
* Settings…

### Edit

* Undo/Redo
* Cut/Copy/Paste
* Quick Open…
* Find / Replace
* Find in Files
* Go to Line
* Toggle Comment
* Indent / Outdent

### Run

* Run (F5)
* Run With Arguments…
* Stop (kills runner process)
* Clear Console
* Run Configurations…

### Tools

* Lint Current File
* Format File (optional; only if black is shipped)
* Project Health Check (verifies folder structure + runner availability)
* “FreeCAD Headless Notes” (quick guide for console-vs-gui pitfalls) 

### Help

* Load Example Project... (copies CRUD showcase into user-chosen folder)
* Getting Started (built-in)
* Keyboard Shortcuts
* About / Version

---

## Keyboard shortcuts (must-have)

* F5 Run
* Shift+F5 Stop
* Ctrl+S Save
* Ctrl+Shift+S Save All
* Ctrl+P Quick Open
* Ctrl+F Find
* Ctrl+Shift+F Find in Files
* Ctrl+G Go to Line
* Ctrl+` Console toggle

(ChoreBoy users already value shortcut keys; make them visible and printable.) 

---

# 8) Project Model & Templates

## Standard project template (aligned with your discovery doc)

Ship and encourage a default structure like: 

```
myapp/
  main.py
  launcher.py
  vendor/
  app/
    __init__.py
    backend.py
    main_window.py
```

### Templates (v1)

1. **Qt App Template**

   * `app/main_window.py` shows basic UI
   * includes crash popup + logging
2. **Headless FreeCAD Tool Template**

   * `app/backend.py` uses `import FreeCAD` without GUI modules
3. **Utility Script Template**

   * simple CLI-like script that prints output

### “Run target” conventions

* Project declares entry point in `project.json` (simple, human-editable).
* If missing, default to `main.py`.

---

# 9) Settings & Persistence

## Where settings live

* Global settings: `~/choreboy_code_studio_state/settings.json` (or under Home)
* Per-project settings overrides: `<project>/cbcs/settings.json`
* Per-project metadata: `<project>/cbcs/project.json`

## What settings include

* recent projects list
* editor preferences (font size, tab width)
* run configs
* scoped settings layering:
  * `defaults -> global settings.json -> project cbcs/settings.json`
  * global-only settings stay machine/user specific (`theme`, `syntax_colors`, `keybindings`, `ui_layout`, `last_project_path`, import-update policy)
  * project-overridable settings include editor/intelligence/linter/file-excludes/output preferences
* optional: file index cache (SQLite)

SQLite is available and proven; use it for indexing/search speed if needed. 

---

# 10) Error Handling & Observability (critical on ChoreBoy)

This is not optional—it’s the difference between “usable” and “mystery failures.”

**Must ship:**

1. `logs/app.log` always written (editor app)
2. Console output captures full stdout/stderr from each run
3. Crash popup window that shows full traceback and “Copy to Clipboard” 
4. A “Report” button that packages:

   * app log
   * project.json
     into a zip for USB transfer (support workflow)

Also: never lose user work—autosave drafts and warn loudly on exit if unsaved (power outage risk is real). 

---

# 11) Security / Safety

* Don’t encourage system browsing outside Home by default; start users in Home folder concepts (matches ChoreBoy File Manager mental model). 
* Clear messaging that projects are “user files” and should be backed up to USB. 

---

# 12) Milestones (practical build plan)

## Milestone 1 — MVP Editor + Runner (highest value fastest)

* Project open (folder tree)
* Multi-tab editing + save
* Run/Stop with external runner process
* Console output streaming
* Logging + crash popup

## Milestone 2 — Developer Comfort

* Find/Replace + Find in files
* Quick Open (Ctrl+P)
* Problems pane (pyflakes optional)
* Project templates + New Project wizard

## Milestone 3 — “ChoreBoy-native” workflows

* Export project to USB / Zip project
* “Support bundle” generator
* Help pages tailored to headless FreeCAD constraints 

## Milestone 4 — Plugin Platform (v1 + phase 2)

* Plugin manifest schema and compatibility validation
* Plugin manager UI (install/enable/disable/remove)
* Runtime plugin host process with crash isolation
* Declarative contribution points (commands/menus/keybindings/hooks)
* Safe-mode startup and plugin failure quarantine
* Phase 2: per-project plugin overrides and pinning

---

# 13) Risks & Mitigations

1. **FreeCAD GUI-only modules fail in console mode**
   Mitigation: headless template defaults + inline guidance; optionally provide “Run with FreeCAD GUI” mode later (separate roadmap). 

2. **Performance on large projects**
   Mitigation: keep indexing optional; add SQLite-backed index if needed (already proven). 

3. **Dependency drift across ChoreBoy versions**
   Mitigation: capability probe at startup (confirm PySide2, QtUiTools availability) and show a clear compatibility report. 

---

# UI Mock Layout (text blueprint)

```
+---------------------------------------------------------------+
| Menu: File Edit Run Tools Help                                |
+-------------------+-----------------------------+-------------+
| Project (Files)   |  Editor Tabs                | Run Config    |
| - myapp/          |  [main_window.py] [backend] | Entry: main.py|
|   - app/          |  -------------------------  | Args:        |
|   - vendor/       |  |                       | | CWD: project |
|   - main.py       |  -------------------------  | [Run] [Stop] |
+-------------------+-----------------------------+-------------+
| Bottom Tabs:  Console | Problems | Tasks                    |
| > output...                                                   |
+---------------------------------------------------------------+
| Status: project | line:col | modified | FreeCAD AppRun Py 3.9 |
+---------------------------------------------------------------+
```