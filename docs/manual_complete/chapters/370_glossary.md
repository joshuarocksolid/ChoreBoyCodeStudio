# Glossary

Definitions of terms used throughout this manual.

**Active run target** — The run configuration that **Run Project** will use, shown on the
right of the status bar (`Default` or a configuration name).

**AppRun** — The launcher for FreeCAD's bundled Python runtime, which ChoreBoy Code Studio
runs inside.

**Autosave draft** — A debounced, automatically saved copy of your *unsaved* edits, used
for crash recovery. It never overwrites your file on disk.

**Breakpoint** — A marker on a line that tells the debugger to pause there.

**Capability check** — The startup probe that confirms the runtime is healthy; its result
appears in the status bar ("Runtime ready").

**`cbcs/`** — The visible per-project metadata folder (project settings, logs, runs).

**Checkpoint** — A durable Local History snapshot of a saved file version.

**Code intelligence** — Static analysis providing completion, hover, signature help,
go-to-definition, find-references, and rename.

**Dependency** — A third-party Python package added to your project's `vendor/` folder and
recorded in `cbcs/dependencies.json`.

**Diagnostics** — Problems (errors/warnings) found by linting or runs, shown in the
Problems panel and as squiggles in the editor.

**Editor process** — The application window you work in. Distinct from the runner.

**Entry file** — The file run by **Run Project** (`default_entry` in `cbcs/project.json`).

**Headless** — Running without a graphical FreeCAD GUI or active document. Code Studio
runs are headless.

**High Contrast** — Two theme modes (Light/Dark) with maximum contrast (WCAG AAA) for
legibility.

**Linter** — The tool that checks your code for problems. Providers include the built-in
checker and Pyflakes.

**Local History** — A built-in, Git-independent timeline of saved file versions you can
compare and restore.

**Manifest (run)** — A JSON file describing exactly how a run is launched; makes runs
reproducible.

**Manifest (plugin)** — `plugin.json`, the file describing a plugin's id, capabilities,
and contributions.

**Plugin** — An add-on that extends the editor with commands or workflow providers.

**Plugin host process** — The separate process where runtime plugin code executes,
isolated from the editor.

**Preview tab** — A temporary editor tab opened by a single click; replaced by the next
preview unless promoted to a permanent tab.

**Project** — A folder you work in. The unit of organization in Code Studio.

**Provider (workflow)** — A plugin component that handles an editor-owned workflow
(formatter, test, diagnostics, and so on) over the query or job lane.

**Quick Open** — Fast file finder opened with `Ctrl+P`.

**REPL** — "Read–eval–print loop"; the interactive Python Console.

**Runner process** — The separate process where your program executes when you press Run.

**Runtime Center** — The surface that explains runtime and project health in plain
language.

**Safe mode** — Starting the editor with all plugins disabled, for recovery.

**Scope (settings)** — Whether a setting is **global** (all projects) or **project**
(this project only).

**Sources Root** — A folder (such as `src/`) marked so imports beneath it resolve.

**Support Bundle** — A diagnostic archive of logs and metadata for offline support.

**Test Explorer** — The sidebar view that discovers and runs pytest tests.

**Workflow provider** — See *Provider (workflow)*.
