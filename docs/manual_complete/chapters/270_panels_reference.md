# Panels & UI Surfaces Reference

This chapter is a reference for every panel and surface in the window. For a guided tour,
see "A tour of the window"; for menu commands, see "Menu & command reference".

## Sidebar views (left)

The left sidebar switches between three views using the icons on its far-left edge.

### Explorer

The project file tree. Open files, and right-click for the full file-management menu
(New File/Folder, Rename, Move to Trash, Duplicate, Cut/Copy/Paste, Copy Path, Copy
Relative Path, Reveal in File Manager, Local History, Run, Run With Arguments, Set as
Entry Point). See "The project tree & file management".

### Search

Project-wide text search (Find in Files). Shows a query field with case-sensitive,
whole-word, and regular-expression toggles, and results grouped by file with counts. See
"Navigation & search".

### Test Explorer

A tree of discovered pytest tests with per-node pass/fail/skip status and Run/Debug
context actions. See "The testing workflow".

## Outline (below the sidebar)

Lists the symbols (functions, classes) in the active file. Click to jump. Collapsible.

## Editor (center)

Tabbed editor with preview tabs, syntax highlighting, code intelligence, and Markdown
view modes. See "Editing files".

## Bottom panels

Four tabbed panels:

| Panel | Contents |
| --- | --- |
| **Python Console** | Interactive REPL running in a separate process. |
| **Debug** | Threads, call stack, scopes, variables, and watches while debugging. |
| **Problems** | Linting and run errors, grouped by file, with counts and jump-to-source. |
| **Run Log** | Live program output plus saved per-run logs; an **Open Log** action. |

The application switches to the most relevant panel automatically (Run Log on output,
Problems on failure); you can disable this in **Settings > Output**.

## Run / Debug toolbar (top)

One-click access to **Run Active File**, **Debug Active File**, **Run Project**, **Debug
Project**, and **Package Project**. While running, it shows a **Stop** button. Buttons
disable when not valid for the current state.

## Status bar (bottom)

A compact dashboard, left to right:

| Segment | Meaning |
| --- | --- |
| Runtime readiness | e.g. "Runtime ready (8/8 checks)"; click to open the Runtime Center. |
| Python tooling status | Whether tools loaded; active config source (e.g. `pyproject`). |
| Run state | idle / running / finished / failed / terminated. |
| Project | Project name; `(project overrides)` when project settings exist. |
| Editor position | Indentation, active file, line/column, saved/modified. |
| Active run target | The configuration Run Project will use; click to switch. |

## Dialogs

Major dialogs you will encounter:

| Dialog | Opened from | Purpose |
| --- | --- | --- |
| New Project | File menu | Choose template, name, location. |
| Settings | File menu | Global/project preferences (tabbed). |
| Run With Arguments / Run Configurations | Run menu | One-off and saved run setups. |
| Plugin Manager | Tools menu | Manage plugins. |
| Dependency Inspector / Add Dependency | Tools menu | Manage vendored packages. |
| Runtime Center | Tools menu / status bar | Runtime and project health. |
| Local History / Recovery Center / Global History | File menu / tree | Compare and restore versions. |
| Package Project | Toolbar / Run menu | Build an installable package. |

## Where to go next

- See file formats behind these surfaces in "File & folder reference".
- Understand the runtime model in "How it works".
