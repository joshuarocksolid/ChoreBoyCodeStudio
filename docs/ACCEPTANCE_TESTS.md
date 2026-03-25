# ChoreBoy Code Studio — Acceptance Tests (v1)

## 1. Purpose

This document defines the acceptance tests for ChoreBoy Code Studio v1.

These tests answer the question:

**What must work on a real ChoreBoy environment before we consider the MVP successful?**

These are not low-level unit tests.  
They are **human-verifiable end-to-end checks** that validate the product’s core workflows.

This file is the canonical definition of MVP validation.

---

## 2. Scope

These acceptance tests focus on the first high-value vertical slice:

1. launch the editor
2. open a project
3. open and edit `main.py`
4. save changes
5. run user code in a separate runner process
6. view stdout/stderr
7. view traceback on failure
8. stop a running script safely

These tests are intentionally biased toward:
- real user workflows
- supportability
- stability under ChoreBoy constraints
- architecture-critical behavior

---

## 3. Test Environment

Acceptance tests should be performed on the **real target runtime** or the closest possible equivalent:

- ChoreBoy system
- FreeCAD AppRun runtime
- actual filesystem/project folders
- actual Qt UI behavior
- actual process launch behavior

Where possible, testing should avoid relying only on a normal development Python environment.

---

## 4. Definition of MVP Success

MVP is considered achieved when all of the following are true on the real target environment:

- the editor launches successfully
- a valid project can be opened
- a project file can be opened in the editor
- edits can be saved to disk
- user code runs in a separate runner process
- stdout and stderr are visible in the UI
- failed runs produce usable traceback information
- per-run logs are written to disk
- the user can stop a running process safely
- the editor remains stable when user code fails

If any of the above are missing, MVP is not complete.

---

## 5. Test Data / Sample Projects

The following sample projects should exist for acceptance testing:

### A. Simple Success Project
A minimal project whose `main.py` prints output and exits successfully.

Example behavior:
- prints `START`
- prints a few lines
- exits with success

### B. Failure Project
A minimal project whose `main.py` raises an exception.

Example behavior:
- prints one line
- raises an exception with traceback

### C. Long-Running Project
A minimal project whose `main.py` keeps running until stopped.

Example behavior:
- prints `tick` repeatedly
- remains active long enough to test Stop behavior

### D. Invalid / Non-importable Project
A folder that cannot be treated as a Python project, such as:
- no `cbcs/project.json` and no `.py` files
- corrupted/invalid `cbcs/project.json`

Used to verify project validation and actionable errors.

### E. Importable Existing Python Folder
A plain Python folder without `cbcs/project.json` that includes runnable `.py` files.

Used to verify first-open metadata initialization and import-friendly open behavior.

---

## 6. Acceptance Test Format

Each acceptance test includes:

- **ID**
- **Title**
- **Purpose**
- **Preconditions**
- **Steps**
- **Expected Result**

A test passes only if the expected result is achieved without hand-waving.

---

## 7. Core Acceptance Tests

## AT-01 — Editor launches successfully

**Purpose:**  
Verify that the application can start in the supported runtime.

**Preconditions:**  
- target runtime is available
- launch path is correctly configured

**Steps:**  
1. Launch ChoreBoy Code Studio using the intended startup path.
2. Wait for the main window to appear.

**Expected Result:**  
- the editor window opens successfully
- the application does not crash on startup
- the UI is responsive
- startup failures, if any, are logged visibly rather than failing silently

---

## AT-02 — Capability probe runs at startup

**Purpose:**  
Verify that runtime assumptions are checked explicitly.

**Preconditions:**  
- editor can launch

**Steps:**  
1. Start the editor.
2. Observe startup behavior and any capability status output.

**Expected Result:**  
- capability checks run during startup or are available immediately after startup
- missing capabilities are reported clearly
- the app does not rely on silent assumptions about runtime features

---

## AT-03 — Valid project opens successfully

**Purpose:**  
Verify that a normal project can be opened from disk.

**Preconditions:**  
- a valid test project exists, either:
  - already containing `cbcs/project.json`, or
  - a plain Python folder that can be imported on first open

**Steps:**  
1. Launch the editor.
2. Choose **Open Project**.
3. Select a valid test project folder.

**Expected Result:**  
- the project loads without restarting the app
- project metadata is recognized
- the project name or equivalent project state is visible in the UI
- the project tree populates with project files
- if metadata was missing but the folder is importable, `cbcs/project.json` is initialized automatically

---

## AT-04 — Invalid project fails with actionable error

**Purpose:**  
Verify that broken or non-importable folders fail safely and clearly.

**Preconditions:**  
- an invalid/non-importable test folder exists

**Steps:**  
1. Launch the editor.
2. Choose **Open Project**.
3. Select an invalid project folder.

**Expected Result:**  
- the project is not opened as if it were valid
- the user receives a clear, actionable error
- the editor remains stable
- the error is diagnosable through UI messaging and/or logs

---

## AT-24 — Existing Python folder imports on first open

**Purpose:**  
Verify that users can open normal Python folders that were not created by Code Studio.

**Preconditions:**  
- an importable existing Python folder exists
- folder does not contain `cbcs/project.json`

**Steps:**  
1. Launch the editor.
2. Choose **Open Project**.
3. Select the importable Python folder.

**Expected Result:**  
- the folder opens as a project without manual metadata setup
- `cbcs/project.json` is created with canonical defaults
- inferred entrypoint is usable for Run
- project tree and editor flows work as normal

---

## AT-05 — Project tree displays project contents

**Purpose:**  
Verify that users can browse project files.

**Preconditions:**  
- a valid project is open

**Steps:**  
1. Open a valid project.
2. Inspect the project tree/sidebar.

**Expected Result:**  
- project folders/files are visible
- the tree reflects the expected project structure
- selecting a file is possible
- the UI remains responsive while browsing

---

## AT-06 — File opens in editor tab

**Purpose:**  
Verify that a selected file can be opened for editing.

**Preconditions:**  
- a valid project is open
- project contains `main.py`

**Steps:**  
1. In the project tree, click `main.py`.

**Expected Result:**  
- `main.py` opens in an editor tab
- file contents are visible
- the current active file is clear in the UI
- opening the same file again does not create unnecessary duplicate tabs

---

## AT-07 — File can be edited and marked dirty

**Purpose:**  
Verify editable state and unsaved-change tracking.

**Preconditions:**  
- `main.py` is open in an editor tab

**Steps:**  
1. Modify the contents of `main.py`.
2. Observe the tab/editor state.

**Expected Result:**  
- the file contents change in the editor
- the file is marked as modified/dirty in the UI
- the modified state remains until the file is saved or reverted

---

## AT-08 — Save writes file changes to disk

**Purpose:**  
Verify that edits are persisted correctly.

**Preconditions:**  
- `main.py` is open and modified

**Steps:**  
1. Save the file.
2. Confirm the file on disk reflects the new content.

**Expected Result:**  
- changes are written successfully to disk
- dirty state clears after save
- save failures are surfaced clearly if they occur
- no silent data loss occurs

---

## AT-09 — Save All writes multiple modified files

**Purpose:**  
Verify multi-file save behavior.

**Preconditions:**  
- at least two project files are open and modified

**Steps:**  
1. Modify two files.
2. Use **Save All**.

**Expected Result:**  
- all modified files are saved
- dirty indicators clear appropriately
- failures are reported clearly if any file cannot be saved

---

## AT-10 — Run launches user code in a separate runner process

**Purpose:**  
Verify the most important process boundary in the architecture.

**Preconditions:**  
- a valid project is open
- `main.py` is runnable

**Steps:**  
1. Open the success test project.
2. Press **Run**.

**Expected Result:**  
- user code is launched through a separate runner process
- the editor process remains responsive while the run is active
- a failure in user code would not terminate the editor process
- the run state is visible in the UI

---

## AT-11 — Successful run shows stdout in console

**Purpose:**  
Verify that normal output is visible to the user.

**Preconditions:**  
- success test project is open

**Steps:**  
1. Press **Run**.
2. Observe the console/output area.

**Expected Result:**  
- stdout appears in the console/output panel
- output is readable and associated with the current run
- run completion is visible to the user
- the editor remains responsive throughout

---

## AT-12 — Failed run shows traceback information

**Purpose:**  
Verify that failures are visible and diagnosable.

**Preconditions:**  
- failure test project is open

**Steps:**  
1. Press **Run**.
2. Observe the console and any problems/error UI.

**Expected Result:**  
- the failure is visible in the UI
- traceback information is preserved and accessible
- if file/line information is available, it is surfaced clearly
- the editor itself remains running after the failure

---

## AT-13 — stderr is visible to the user

**Purpose:**  
Verify that error output is not lost.

**Preconditions:**  
- test project produces stderr output or exception output

**Steps:**  
1. Run a project that writes to stderr or raises an exception.

**Expected Result:**  
- stderr is visible in the output UI
- stderr is distinguishable enough from stdout to aid debugging
- important failure details are not hidden

---

## AT-14 — Per-run log file is written to disk

**Purpose:**  
Verify durable diagnostic logging.

**Preconditions:**  
- a project has been run at least once

**Steps:**  
1. Run a test project.
2. Locate the project log directory.
3. Inspect the newest run log.

**Expected Result:**  
- a per-run log file exists
- the log file contains run output
- failed runs preserve full traceback information
- the log can be used for support/debugging even after the UI is closed

---

## AT-15 — Stop terminates a long-running script safely

**Purpose:**  
Verify run control for long-running user code.

**Preconditions:**  
- long-running test project is open

**Steps:**  
1. Press **Run** on the long-running project.
2. Wait until output confirms it is still running.
3. Press **Stop**.

**Expected Result:**  
- the running process is terminated or stopped cleanly
- the UI reflects that the run is no longer active
- the editor remains stable and responsive
- the final run state is understandable to the user

---

## AT-16 — Editor survives user-code failure

**Purpose:**  
Verify crash isolation between editor and runner.

**Preconditions:**  
- failure test project is open

**Steps:**  
1. Run code that raises an exception or otherwise fails.
2. After the run fails, continue using the editor.

**Expected Result:**  
- the editor stays open
- the user can still open files, edit, and save after the failure
- the failure is isolated to the run, not the whole app

---

## AT-17 — Recent projects persist between sessions

**Purpose:**  
Verify basic app persistence for project-first workflow.

**Preconditions:**  
- at least one project has been opened successfully

**Steps:**  
1. Open a valid project.
2. Close the editor.
3. Relaunch the editor.
4. Inspect the recent-projects UI or equivalent state.

**Expected Result:**  
- the recent project is remembered
- invalid/missing project paths do not crash the editor
- recent-project behavior is stable and predictable

---

## AT-18 — Recovery drafts protect unsaved work

**Purpose:**  
Verify that unsaved edits are recoverable after abnormal exit.

**Preconditions:**  
- recovery/autosave draft feature is implemented

**Steps:**  
1. Open and modify a file without saving.
2. Simulate abnormal exit or crash.
3. Relaunch the editor.

**Expected Result:**  
- unsaved draft content is recoverable
- recovery does not silently overwrite the original source file
- the recovery flow is understandable to the user

**Note:**  
This test is required for MVP only if draft recovery is included in the MVP implementation scope.

---

## 8. Template / New Project Acceptance Tests

These may be executed after the core MVP slice is stable.

## AT-19 — New utility_script project can be created

**Purpose:**  
Verify the simplest project creation flow.

**Preconditions:**  
- template system is implemented

**Steps:**  
1. Choose **New Project**.
2. Select the `utility_script` template.
3. Choose a destination.
4. Create the project.
5. Open and run it.

**Expected Result:**  
- the project is created successfully
- required files exist
- project metadata is valid
- the generated project runs successfully

---

## AT-20 — New qt_app project can be created

**Purpose:**  
Verify GUI-template project creation.

**Preconditions:**  
- Qt template system is implemented

**Steps:**  
1. Create a new `qt_app` project from the template.
2. Open the project.
3. Run it using the intended execution path.

**Expected Result:**  
- the project is created successfully
- project structure matches expectations
- the Qt app launches using the supported runtime model

---

## AT-21 — New headless_tool project can be created

**Purpose:**  
Verify headless-safe template project creation.

**Preconditions:**  
- headless template system is implemented

**Steps:**  
1. Create a new `headless_tool` project.
2. Open the project.
3. Run it.

**Expected Result:**  
- the project is created successfully
- it follows documented headless-safe patterns
- it does not rely on GUI-only FreeCAD behavior

---

## 9. Diagnostics and Support Acceptance Tests

## AT-22 — Project health check identifies actionable problems

**Purpose:**  
Verify pre-run diagnostics.

**Preconditions:**  
- health check feature is implemented

**Steps:**  
1. Open a valid project and run the health check.
2. Open an invalid/broken project and run the health check.

**Expected Result:**  
- the health check identifies real issues
- the results are understandable
- users receive actionable next steps where possible

---

## AT-23 — Support bundle can be generated

**Purpose:**  
Verify field-support workflow.

**Preconditions:**  
- support bundle feature is implemented
- at least one run log exists

**Steps:**  
1. Generate a support bundle from the app.
2. Inspect the output artifact.

**Expected Result:**  
- the support bundle is created successfully
- expected diagnostic artifacts (app log, project metadata, latest run log when available) are included
- the bundle is suitable for transfer and support review

---

## 10. Post-MVP UX and Debug Acceptance Tests

## AT-25 — Split layout defaults and persistence

**Purpose:**  
Verify editor/tree/output pane proportions are practical on first launch and persist after user adjustment.

**Preconditions:**  
- editor can launch with a writable settings path

**Steps:**  
1. Launch editor on a clean settings profile.
2. Verify initial tree/editor split is editor-favoring.
3. Adjust splitter positions.
4. Close and relaunch editor.

**Expected Result:**  
- initial default layout is productive (tree not oversized)
- adjusted layout is restored on relaunch
- reset-layout action restores known-good defaults

---

## AT-26 — Interactive Python console input/output

**Purpose:**  
Verify users can execute interactive Python commands in a dedicated console session.

**Preconditions:**  
- editor is running (no project required)

**Steps:**  
1. Start Python Console mode.
2. Submit single-line commands (e.g., `x = 2`, `print(x + 3)`).
3. Submit a multiline block (e.g., `for` loop) and complete it with continuation semantics.
4. Exit console session.

**Expected Result:**  
- Python Console is available whether or not a project is open
- submitted commands are accepted via stdin bridge
- multiline continuation prompt behavior matches normal REPL (`>>>` / `...`)
- output appears in console transcript
- session terminates cleanly on exit/stop

---

## AT-27 — Project tree file operations parity

**Purpose:**  
Verify modern explorer actions are available and reliable from the project tree.

**Preconditions:**  
- project with nested files/folders is open

**Steps:**  
1. Use tree context menu for create/rename/move-to-trash/duplicate.
2. Use cut/copy/paste and drag-drop move.
3. Use copy path / copy relative path / reveal in file manager.

**Expected Result:**  
- filesystem operations complete successfully with clear confirmations on move-to-trash actions
- deleted items are moved to trash (not permanently removed immediately)
- tree refreshes to reflect resulting state
- path copy actions return correct values

---

## AT-28 — Move/rename import rewrite policy behavior

**Purpose:**  
Verify Python import update workflow and policy controls for file move/rename.

**Preconditions:**  
- project has at least two Python modules with imports between them

**Steps:**  
1. Move/rename an imported module.
2. Validate policy prompt default is **Ask every time**.
3. Select Always and verify persistence on next move.
4. Select Never and verify rewrites are skipped.

**Expected Result:**  
- Ask/Always/Never policy works as documented
- import rewrites are previewed and applied only when permitted
- no silent overwrite or hidden partial refactor behavior

---

## AT-29 — Run/Debug top toolbar usability

**Purpose:**  
Verify top-of-window Run/Debug controls are discoverable and state-coherent.

**Preconditions:**  
- project is open

**Steps:**  
1. Use toolbar to run and stop a normal script.
2. Start debug session.
3. Verify stepping/continue controls enable only when paused.
4. Verify Pause control is enabled only while actively debugging/running.

**Expected Result:**  
- run/debug controls are visible and functional
- invalid actions are disabled by state
- toolbar behavior matches menu shortcuts

---

## AT-30 — Breakpoints and stepping workflow

**Purpose:**  
Verify practical debugging via gutter breakpoints and step controls.

**Preconditions:**  
- debug-eligible Python project open

**Steps:**  
1. Toggle breakpoint from editor gutter.
2. Start Debug.
3. Confirm execution pauses at breakpoint.
4. Use continue/step commands and observe progress.

**Expected Result:**  
- breakpoints are honored by runner debug mode
- paused/running transitions are visible
- stepping commands function without crashing editor

---

## AT-31 — Debug inspection and watch evaluation

**Purpose:**  
Verify variable/stack inspection affordances in debug workflows.

**Preconditions:**  
- active paused debug session

**Steps:**  
1. Use debug inspector actions to request stack and locals.
2. Add watch expressions and evaluate.
3. Continue and stop debug session.

**Expected Result:**  
- inspector output updates with stack/locals command results
- watch expressions can be evaluated in paused context
- debug session exits cleanly and editor remains stable

---

## AT-59 — Conditional breakpoints and hit-count thresholds

**Purpose:**  
Verify that breakpoint properties are practical for real debugging workflows.

**Preconditions:**  
- debug-eligible Python project open
- file contains a loop or repeated call site

**Steps:**  
1. Add a breakpoint from the gutter.
2. Open breakpoint properties and set a condition.
3. Run Debug and verify the breakpoint only pauses when the condition is true.
4. Change the breakpoint to use a hit-count threshold.
5. Run Debug again and verify the breakpoint does not stop before the threshold.

**Expected Result:**  
- conditional breakpoints are evaluated in runner context without crashing the editor
- hit-count thresholds are honored deterministically
- breakpoint verification failures are visible and actionable

---

## AT-60 — Threads, frames, scopes, and lazy variable expansion

**Purpose:**  
Verify the runtime inspector presents paused state as navigable structured data.

**Preconditions:**  
- active paused debug session
- sample program exposes at least one nested object and more than one stack frame

**Steps:**  
1. Pause at a breakpoint with a non-trivial call stack.
2. Switch between available frames in the Debug panel.
3. Inspect locals and globals by scope.
4. Expand nested variables such as dicts, lists, and custom objects.
5. Confirm large values are truncated rather than freezing the UI.

**Expected Result:**  
- the panel shows threads, frames, and scopes separately
- selecting a frame updates the editor highlight and variable view coherently
- nested variables load on demand instead of materializing the full object graph at once
- object previews stay readable and bounded

---

## AT-61 — Exception pause behavior and exception-stop settings

**Purpose:**  
Verify uncaught exception stops are visible and configurable.

**Preconditions:**  
- debug-eligible Python project open
- project contains one script that raises an uncaught exception and one that raises then catches an exception

**Steps:**  
1. Enable stop on uncaught exceptions and debug the uncaught-exception script.
2. Confirm the session pauses with exception details before exit.
3. Disable stop on raised exceptions and debug the caught-exception script.
4. Enable stop on raised exceptions and debug the caught-exception script again.

**Expected Result:**  
- uncaught exceptions surface as a clear stop reason with traceback details
- raised-exception behavior follows the configured policy
- continuing after an exception stop behaves predictably and the session can still terminate cleanly

---

## AT-62 — Debug current test and rerun last debug target

**Purpose:**  
Verify debug workflows cover both scripts and pytest targets without requiring manual command recreation.

**Preconditions:**  
- project contains at least one passing test file
- an editor tab is open on that test file

**Steps:**  
1. Trigger **Debug Current Test** from the active test file.
2. Pause on a breakpoint inside the test or code under test.
3. Stop the session.
4. Trigger **Rerun Last Debug Target**.

**Expected Result:**  
- current-file pytest debugging launches the intended target
- breakpoint and inspector behavior matches normal debug sessions
- rerun uses the last debug target without requiring the user to rebuild the launch intent

---

## AT-63 — Dirty-buffer debug source remap

**Purpose:**  
Verify debugging unsaved editor changes still navigates back to the real editor file rather than a transient runtime copy.

**Preconditions:**  
- project is open
- active Python file has unsaved edits

**Steps:**  
1. Add a breakpoint in the dirty active file.
2. Start **Debug Active File** without manually saving first.
3. Pause at the breakpoint and inspect the current frame.
4. Navigate between stack frames from the Debug panel.

**Expected Result:**  
- the runner executes the dirty-buffer snapshot
- editor navigation and current-line highlighting point at the real project file
- breakpoint mapping remains coherent even though the runtime used a transient copy

---

## AT-64 — Debug transport reliability, theme safety, and responsiveness

**Purpose:**  
Verify the structured debug transport remains supportable under normal runtime pressure.

**Preconditions:**  
- debug rollout enabled
- editor can switch between light and dark mode
- medium-size Python debug fixture is available

**Steps:**  
1. Start a debug session on the fixture and pause several times.
2. Expand nested variables and evaluate watches while stdout/stderr continues to produce output.
3. Switch between light and dark mode while the Debug panel is populated.
4. Restart the debug target and stop it again.

**Expected Result:**  
- debugger state remains synchronized even while the program emits console output
- pause-to-inspector updates feel responsive and do not stall the UI thread
- debug controls, highlights, badges, and tree states remain readable in both themes
- restart/stop leaves the session in a clean state with actionable logs if failure occurs

---

## AT-32 — Syntax highlighting modernization and adaptive performance

**Purpose:**  
Verify the tree-sitter highlighting pipeline delivers rich lexical/locals/injection coverage while preserving responsiveness under sustained edits and large files.

**Preconditions:**  
- project contains at least one medium Python file (~2,000 LOC) and one very large file (>250k chars)
- project contains representative `.ui`, `pyproject.toml`, `.desktop`, HTML, and Markdown files
- editor can switch between light and dark themes

**Steps:**  
1. Open the medium Python file and verify role-based highlighting for imports, decorators, async/await, annotations, constructor/type references, parameters, and local variable references.
2. Open representative HTML and Markdown fixtures and verify embedded `<script>`, `<style>`, and fenced code blocks render with the injected language colors rather than a single markdown/html fallback color.
3. Open `.ui`, `pyproject.toml`, and `.desktop` files and confirm they attach the expected XML, TOML, and INI/desktop highlighting modes.
4. Use `Tools -> Inspect Token Under Cursor` on a highlighted symbol and confirm the dialog reports the language, node, capture, resolved token, and applied color. Then use `Tools -> Set Language Mode...` on a misdetected/unsupported file and confirm the override reattaches highlighting immediately.
5. Type a short burst of edits and confirm role colors update without visible jitter/freeze.
6. Open the large file and confirm adaptive mode limits query work while keeping editing responsive.
7. Switch light/dark theme with multiple editor tabs open and verify syntax readability remains consistent in both themes.

**Expected Result:**  
- lexical tokens are stateful/consistent (including multiline constructs and modern Python syntax)
- locals-aware semantic roles stay stable while typing because they are rendered through the same tree-sitter highlighter path, not a delayed overlay
- injection regions inherit the embedded language grammar without breaking outer-document highlighting
- unsupported config formats such as `.desktop` still receive the intended fallback highlighter instead of silently attaching a wrong grammar
- large-file adaptive behavior keeps interaction smooth (no sustained UI stalls from highlighting queries)
- light/dark themes both preserve readable contrast for lexical and semantic token categories

---

## AT-33 — Example project loads from Help menu

**Purpose:**  
Verify the Help > Load Example Project... flow creates a valid, runnable CRUD showcase project.

**Preconditions:**  
- editor is running

**Steps:**  
1. Choose **Help > Load Example Project...**
2. Enter a project name (e.g. "My Example").
3. Choose a destination folder.
4. Confirm the project opens automatically in the editor.
5. Verify the project tree shows `main.py`, `app/`, `README.md`.
6. Open `app/repository.py` and confirm it contains SQLite CRUD logic.
7. Open `app/main_window.py` and confirm it uses PySide2 widgets.
8. Press **F5** to run the project (on systems with PySide2 available via AppRun).

**Expected Result:**  
- the project is created with valid `cbcs/project.json` metadata (template = `crud_showcase`)
- all expected files are present
- the project opens and displays correctly in the editor
- the example does NOT appear in the New Project template picker

---

## AT-34 — Keyboard shortcut customization persists and applies live

**Purpose:**  
Verify users can customize command shortcuts from Settings and observe immediate effect.

**Preconditions:**  
- editor is running

**Steps:**  
1. Open **File > Settings...** and set scope to **Global**.
2. Open **Keybindings** tab.
3. Change the **Run** shortcut from `F5` to another valid binding (e.g. `Ctrl+R`).
4. Save settings.
5. Open the **Run** menu and verify displayed shortcut updated.
6. Reopen settings and verify the custom value persisted.

**Expected Result:**  
- updated shortcut appears in menu/action surfaces after save
- keybinding value persists across settings reopen and app restart
- conflicting assignments are prevented or explicitly resolved in-UI

---

## AT-35 — Syntax color customization (light + dark) persists

**Purpose:**  
Verify syntax token colors can be customized per theme and remain readable.

**Preconditions:**  
- editor is running

**Steps:**  
1. Open **File > Settings...** and set scope to **Global**.
2. Open **Syntax Colors** tab.
3. Select **Light Theme**, change one lexical token color (e.g. `keyword`), save.
4. Reopen settings and confirm value persisted.
5. Select **Dark Theme**, change one token color, save.
6. Switch themes from **View > Theme** and verify editor remains readable in both modes.

**Expected Result:**  
- light and dark overrides are independently persisted
- active editor theme reflects configured syntax colors
- both themes preserve usable contrast and readability

---

## AT-36 — Linter profile customization changes diagnostics behavior

**Purpose:**  
Verify linter runtime controls (enable/disable + provider selection) and rule-level settings affect diagnostics output.

**Preconditions:**  
- project with Python file producing at least one `PY220` and one `PY230` diagnostic
- project with Python file that triggers at least one Pyflakes-only diagnostic (for example undefined name)

**Steps:**  
1. Open **File > Settings...**.
2. Set scope to **Project**.
3. Open **Linter** tab.
4. Turn **Enable Python linting** off and verify provider + rule controls become disabled.
5. Turn linting back on, set provider to **Pyflakes**, save settings, and lint an affected file.
6. Confirm a Pyflakes-only diagnostic appears.
7. Reopen settings and verify provider persisted as **Pyflakes**.
8. Change provider back to **Default (built-in)**.
9. Disable `PY220` (Unused import), set `PY230` (Unreachable statement) severity to `WARNING`.
10. Save settings and re-run linting for affected file.
11. Reopen settings and verify changes persisted in project scope.
12. Use "Reset ... to Global" and verify baseline values are restored.

**Expected Result:**  
- linter enable toggle suppresses diagnostics when off and re-enables them when on
- provider selection switches active lint backend between `default` and `pyflakes`
- selected provider persists across settings reopen and app restart
- disabled rule diagnostics are suppressed
- severity override is reflected in problems/editor indicators
- lint profile persists across settings reopen and app restart
- reset-to-global clears project override values

---

## AT-43 — Settings scope layering and status indicator

**Purpose:**  
Verify global vs project scope controls, layered effective settings, and project-override status indication.

**Preconditions:**  
- editor is running
- one project is open

**Steps:**  
1. Open **File > Settings...** with no project open and confirm **Project** scope is unavailable.
2. Open a project and reopen **Settings**.
3. Set scope to **Project** and change one project-overridable value (for example `editor.tab_width`).
4. Save settings.
5. Confirm `<project>/cbcs/settings.json` exists and contains project override sections.
6. Verify status bar shows project override indicator.
7. Switch scope to **Global** and confirm global-only tabs (`Keybindings`, `Syntax Colors`) are available.
8. Switch back to **Project** and confirm global-only controls are hidden.
9. Reset project overrides to global and save.
10. Verify status bar indicator clears.

**Expected Result:**  
- scope selector correctly gates editable controls by scope
- effective runtime settings follow layered precedence (`defaults -> global -> project`)
- project settings persist in `<project>/cbcs/settings.json`
- status bar clearly indicates when project overrides are active
- reset-to-global removes active project overrides

---

## AT-37 — Plugin install from local package

**Purpose:**  
Verify offline plugin installation flow using local filesystem artifacts.

**Preconditions:**  
- editor is running
- a valid local plugin package exists

**Steps:**  
1. Open Plugin Manager.
2. Choose install from local package/folder.
3. Select the plugin package.

**Expected Result:**  
- plugin manifest is validated before install
- plugin appears in installed list with version and compatibility status
- install errors are actionable when validation fails

---

## AT-38 — Runtime plugin host isolation

**Purpose:**  
Verify runtime plugin code executes outside the editor process.

**Preconditions:**  
- a runtime plugin is installed and enabled

**Steps:**  
1. Trigger a plugin command backed by runtime code.
2. Observe command result in UI.
3. Force plugin runtime failure (controlled exception/crash path).

**Expected Result:**  
- plugin command executes successfully through plugin host process
- editor remains responsive when plugin runtime fails
- failure is surfaced in plugin status/log diagnostics

---

## AT-39 — Plugin enable/disable lifecycle

**Purpose:**  
Verify plugin lifecycle controls are deterministic and persistent.

**Preconditions:**  
- at least one installed plugin exists

**Steps:**  
1. Disable plugin in Plugin Manager.
2. Confirm plugin contributions are removed.
3. Re-enable plugin.
4. Restart editor and verify state persistence.

**Expected Result:**  
- disable removes contributions without restart when supported
- enable restores contributions
- enabled/disabled state persists across restart

---

## AT-40 — Safe mode and failure quarantine

**Purpose:**  
Verify recovery path for bad plugins.

**Preconditions:**  
- at least one plugin capable of repeated startup/runtime failure

**Steps:**  
1. Start editor in safe mode.
2. Verify plugins are not activated.
3. Start normal mode and trigger repeated plugin failure threshold.

**Expected Result:**  
- safe mode launches editor with plugins disabled
- repeated plugin failures auto-disable/quarantine offending plugin
- user can re-enable explicitly after diagnosis

---

## AT-41 — Declarative plugin contribution points

**Purpose:**  
Verify declarative plugin contributions are validated and wired.

**Preconditions:**  
- plugin with declarative contributions (command/menu/keybinding) is installed

**Steps:**  
1. Enable declarative plugin.
2. Verify contributed menu item appears.
3. Execute contributed command via menu and keybinding.

**Expected Result:**  
- declarative contributions are visible and functional
- invalid contribution payloads are rejected with clear diagnostics

---

## AT-42 — Plugin compatibility enforcement

**Purpose:**  
Verify manifest compatibility guards prevent invalid activation.

**Preconditions:**  
- plugin package with incompatible app/api version constraints

**Steps:**  
1. Attempt install/enable incompatible plugin.
2. Review compatibility details in Plugin Manager.

**Expected Result:**  
- incompatible plugin does not activate
- compatibility reason is clearly displayed
- compatible plugins remain unaffected

---

## AT-44 — Preview tab mode across explorer/navigation surfaces

**Purpose:**  
Verify single-preview semantics, promotion behavior, and preview toggle across all supported file-open surfaces.

**Preconditions:**  
- project with multiple Python files is open
- `editor.enable_preview` initially enabled

**Steps:**  
1. In Project Tree, single-click file A then single-click file B.
2. In Project Tree, double-click file C.
3. In Quick Open, single-click file D in results list, then press Enter.
4. In Search results, single-click one result then double-click another.
5. In Problems panel, single-click one item then activate another.
6. In Debug panel (stack/breakpoint list), single-click an item then double-click an item.
7. Use Run Log “Open Log” action.
8. Open a preview tab and promote it via:
   - tab-header double-click,
   - first content edit,
   - keep-preview-open shortcut.
9. Disable `editor.enable_preview` in Settings and repeat representative opens from tree/search/quick-open.

**Expected Result:**  
- only one preview tab exists at a time
- each new preview replaces the previous preview tab
- activation/double-click/Enter opens permanent tab for that source
- all three promotion mechanisms convert preview to permanent
- disabling preview makes all opens permanent and promotes any existing preview immediately

---

## 11. Trusted Python Semantics Acceptance Tests

## AT-45 — Imported-symbol semantics resolve correctly while editing

**Purpose:**  
Verify that the semantic engine resolves imported symbols reliably, including unsaved current-buffer edits.

**Preconditions:**  
- project with at least two Python modules and cross-file imports is open
- semantic engine rollout is enabled

**Steps:**  
1. Open a file that imports a symbol from another project module.
2. Invoke go-to-definition on the imported symbol.
3. Request hover info for the same symbol.
4. Trigger signature help on a call to that symbol.
5. Modify the current buffer without saving and repeat hover/signature where the edit changes the result.

**Expected Result:**  
- go-to-definition lands on the correct imported definition
- hover and signature help reflect the imported symbol, not merely a same-name local/global match
- unsaved current-buffer edits are respected for read-only semantic actions
- the UI identifies semantic results clearly

---

## AT-46 — Shadowed and ambiguous symbols are handled explicitly

**Purpose:**  
Verify that same-name symbols in different scopes/modules do not silently collapse into one result.

**Preconditions:**  
- project fixture contains shadowed names and duplicate symbol names across files
- semantic engine rollout is enabled

**Steps:**  
1. Open a fixture with a local symbol shadowing an imported or module-level symbol.
2. Invoke go-to-definition and find-references on both occurrences.
3. Invoke go-to-definition on a symbol with multiple valid targets.

**Expected Result:**  
- navigation and references respect binding identity rather than same-spelling token matches
- unrelated homonyms are excluded from the semantic result set
- when multiple valid targets exist, the user is prompted to choose instead of the editor silently opening the first match

---

## AT-47 — Semantic completion surfaces trustworthy detail and confidence

**Purpose:**  
Verify that completion behavior is semantic, cancellable, and clear about result provenance.

**Preconditions:**  
- project with cross-module imports and member accesses is open
- semantic completion is enabled

**Steps:**  
1. Trigger completion on an imported module member.
2. Trigger completion while rapidly typing to force stale requests.
3. Inspect completion rows for detail/source/confidence metadata.

**Expected Result:**  
- imported/member completions are project-aware and relevant
- stale completion responses are discarded rather than flashing outdated items
- completion rows show useful semantic metadata such as kind, source, or confidence state
- approximate/fallback results, if shown, are clearly labeled as such

---

## AT-48 — Dynamic-code degradation is explicit and recoverable

**Purpose:**  
Verify that unsupported dynamic patterns degrade safely instead of pretending to be exact.

**Preconditions:**  
- project fixture includes deliberately dynamic code that the semantic engine cannot prove precisely
- semantic engine rollout is enabled

**Steps:**  
1. Invoke definition/references on a symbol produced through dynamic behavior.
2. Inspect the UI response.
3. Follow the offered text-search or manual-search escape hatch.

**Expected Result:**  
- the editor does not silently present lexical/text results as semantic truth
- the user sees an explicit unsupported or degraded message
- the fallback path to text search is available and understandable

---

## AT-49 — Semantic rename preview, apply, and rollback

**Purpose:**  
Verify that project-wide rename is planned semantically, previewed clearly, and rolled back safely on failure.

**Preconditions:**  
- project fixture contains a renameable symbol used across multiple files
- semantic rename is enabled

**Steps:**  
1. Invoke rename on the target symbol.
2. Review the preview UI before applying.
3. Apply the rename and inspect the touched files.
4. Repeat with a simulated write failure or blocked unsafe rename case.

**Expected Result:**  
- the preview is grouped by file with patch-style changes rather than only filename/line lists
- only semantically related occurrences are renamed
- unsafe/ambiguous rename operations are blocked with a clear explanation
- mid-apply failure triggers deterministic rollback rather than partial project corruption

---

## AT-50 — Semantic engine runtime behavior respects ChoreBoy constraints

**Purpose:**  
Verify that the chosen semantic/refactor engines operate safely under the real AppRun runtime and filesystem rules.

**Preconditions:**  
- test executed in the AppRun-based target or target-like runtime
- semantic engine dependencies are present

**Steps:**  
1. Start the editor and open a semantic fixture project.
2. Exercise completion, definition, references, and rename preview.
3. Inspect project/global state directories after use.

**Expected Result:**  
- semantic features work without spawning unsupported sidecar binaries
- no hidden engine metadata directories such as `.jedi` or `.ropeproject` are created
- any semantic cache/state paths are visible and supportable
- read-only semantic queries do not rely on unsafe extension loading or interpreter-style execution of project code

---

## AT-51 — Semantic UI states remain usable in both themes and within latency targets

**Purpose:**  
Verify that semantic UI surfaces are legible in light/dark mode and remain responsive enough for real editing.

**Preconditions:**  
- semantic engine rollout is enabled
- editor can switch between light and dark themes
- medium-size fixture project is available

**Steps:**  
1. Trigger semantic completion, hover, signature help, references, and rename preview in light mode.
2. Repeat in dark mode.
3. Measure warm completion/navigation behavior on the medium fixture.

**Expected Result:**  
- all semantic labels, badges, lists, popups, and previews remain readable in both themes
- semantic completion and navigation feel responsive enough for normal editing workflows
- performance regressions are measurable and within the documented rollout targets

---

## AT-52 — Python format command performs real formatting

**Purpose:**  
Verify that formatting a Python file performs recognizable Python formatting rather than only whitespace cleanup.

**Preconditions:**  
- formatter dependencies are available
- a Python file with import/order/wrapping style issues is open in the editor

**Steps:**  
1. Open a Python file that needs more than trailing-whitespace cleanup.
2. Invoke **Format Current File**.
3. Inspect the updated buffer and save state.

**Expected Result:**  
- the resulting Python code matches the shipped Black-style formatting behavior
- the editor does not claim success when only whitespace cleanup would have occurred
- unchanged files report a no-op result instead of mutating the buffer
- non-Python files continue using the generic hygiene formatter path

---

## AT-53 — Organize imports is explicit, Black-compatible, and non-destructive

**Purpose:**  
Verify that organize-imports is a separate trusted command that sorts imports without pretending to be a structural refactor engine.

**Preconditions:**  
- formatter/import dependencies are available
- a Python file containing unsorted imports, comments, and `__future__` imports is open

**Steps:**  
1. Invoke **Organize Imports** on the file.
2. Inspect the resulting import block.
3. Repeat on a file with comments and multi-line imports.

**Expected Result:**  
- organize-imports is a separate command from format
- imports are grouped and ordered in a Black-compatible way
- `__future__` imports stay correctly ordered
- surrounding comments are preserved
- the command does not silently remove unused imports or perform broader refactors

---

## AT-54 — Project-local pyproject configuration drives Python style behavior

**Purpose:**  
Verify that Python formatting/import behavior comes from project-local `pyproject.toml` settings instead of hidden global tool state.

**Preconditions:**  
- project contains a `pyproject.toml` with `[tool.black]`, `[tool.isort]`, or `[project.requires-python]`
- formatter/import dependencies are available

**Steps:**  
1. Open the project and a Python file that exercises the configured style.
2. Trigger **Format Current File** and **Organize Imports**.
3. Inspect settings/status surfaces for detected formatter/import configuration.

**Expected Result:**  
- project-local `pyproject.toml` settings are honored for the supported formatter/import options
- Python target-version-sensitive import grouping matches the declared project/runtime intent
- the UI makes it clear that project-local config was detected
- hidden global formatter/import config does not silently override project behavior

---

## AT-55 — Save succeeds even when organize/format fails

**Purpose:**  
Verify that save reliability outranks style automation when a formatter/import step fails.

**Preconditions:**  
- save-time format or organize-imports automation is enabled
- a Python file is open
- create either a syntax-broken buffer or a deliberate formatter/import configuration failure

**Steps:**  
1. Edit the Python file into a state that causes organize-imports or format to fail.
2. Save the file.
3. Inspect the saved on-disk contents and the UI feedback.

**Expected Result:**  
- the current buffer contents are still written to disk
- the editor remains stable and the file is not lost
- the user sees a clear warning describing the formatting/import failure
- save does not silently pretend the style action succeeded

---

## AT-56 — Python formatter/import tooling respects ChoreBoy runtime constraints

**Purpose:**  
Verify that the shipped Python formatter/import stack works under the AppRun runtime without violating ChoreBoy filesystem and subprocess constraints.

**Preconditions:**  
- test executed in the AppRun-based target or target-like runtime
- formatter/import dependencies are present

**Steps:**  
1. Open a project with Python files and `pyproject.toml`.
2. Run **Format Current File** and **Organize Imports**.
3. Inspect project/global state directories and runtime behavior.

**Expected Result:**  
- formatting/import commands work without spawning unsupported formatter sidecar binaries
- no hidden cache or metadata directories are created for the shipped formatter/import path
- any formatter/import readiness status is reported clearly
- the shipped dependency set remains supportable for the real runtime and packaging contract

---

## AT-57 — Formatting/import actions preserve editor trust and theme readability

**Purpose:**  
Verify that formatting/import actions preserve practical editor state and remain understandable in both light and dark themes.

**Preconditions:**  
- formatter/import rollout is enabled
- editor can switch between light and dark mode
- a Python file with selection/cursor state is open

**Steps:**  
1. Place the caret and selection inside a Python file.
2. Trigger **Format Current File** and **Organize Imports**.
3. Repeat in both light and dark modes while observing status/error surfaces.

**Expected Result:**  
- formatting/import actions preserve practical cursor, selection, scroll, and undo behavior
- success, no-op, and failure states remain readable in both themes
- the editor does not feel like it discarded the user’s working context after applying a full-buffer transform

---

## AT-58 — Python formatting/import latency stays within rollout targets

**Purpose:**  
Verify that the shipped Python formatting/import path remains responsive enough for normal editing workflows.

**Preconditions:**  
- formatter/import rollout is enabled
- medium-size Python fixture file is available

**Steps:**  
1. Warm the formatter/import path on the medium fixture.
2. Measure **Format Current File** latency.
3. Measure **Organize Imports** latency.
4. Measure save-time organize+format latency with both toggles enabled.

**Expected Result:**  
- manual format stays within the documented rollout target
- organize-imports stays within the documented rollout target
- combined save-time automation remains responsive enough for day-to-day editing
- any guardrail-triggered skips are explicit rather than manifesting as UI freezes

---

## 12. Local History, Diffs, and Recovery Acceptance Tests

## AT-65 — Saves create local history checkpoints with compareable revisions

**Purpose:**  
Verify that successful saves create durable local-history checkpoints that users can inspect and compare.

**Preconditions:**  
- local history is enabled
- a project is open
- an editable text file is open in the editor

**Steps:**  
1. Save the file once in a known baseline state.
2. Make and save a second meaningful change.
3. Open **Local History** for the active file.
4. Compare the latest entry with the current file and with the previous entry.

**Expected Result:**  
- the file shows durable local-history checkpoints representing the saved states
- the revision list includes timestamps and any relevant labels/source metadata
- the UI can compare a selected entry with the current file and a previous entry
- opening local history does not mutate the file on disk

---

## AT-66 — Crash recovery offers compare-and-restore without silent overwrite

**Purpose:**  
Verify that draft recovery uses a reviewable recovery flow instead of blindly replacing the file.

**Preconditions:**  
- draft recovery and local history are enabled
- a project file has unsaved edits

**Steps:**  
1. Modify a file without saving.
2. Simulate abnormal exit or crash.
3. Relaunch the editor and reopen the file.
4. Use the recovery UI to compare the draft against the saved file.
5. Choose **Restore Draft to Buffer**.

**Expected Result:**  
- the recovery flow offers clear choices such as compare, restore to buffer, or keep disk version
- the user can review the draft-versus-saved diff before restoring
- restoring places the recovered contents into the editor buffer first
- the source file on disk is not silently overwritten until the user saves explicitly

---

## AT-67 — Local history restore returns older content to the buffer safely

**Purpose:**  
Verify that users can restore an older revision from local history without losing control of the current session.

**Preconditions:**  
- a file has at least two local-history checkpoints
- the file is open in the editor

**Steps:**  
1. Open **Local History** for the file.
2. Select an older revision and inspect the diff.
3. Choose **Restore to Buffer** for that revision.
4. Review the restored editor state before saving.

**Expected Result:**  
- the selected revision is restored into the active buffer rather than directly replacing the file on disk
- cursor/scroll/undo behavior remains practical after the restore
- the user can decide whether to save or discard the restored content
- the restore result is understandable and does not silently destroy newer history entries

---

## AT-68 — Moved, renamed, and deleted files remain recoverable from history

**Purpose:**  
Verify that local history follows logical files across path changes and can recover deleted files.

**Preconditions:**  
- a project contains a file with at least one saved local-history checkpoint

**Steps:**  
1. Rename or move the file from the project tree.
2. Confirm the file still shows its earlier local-history entries.
3. Delete the file.
4. Use the global history restore flow to find an entry for the deleted file.
5. Restore the deleted file through the explicit recovery workflow.

**Expected Result:**  
- local history follows the file across app-driven move/rename operations
- the deleted file remains discoverable through global history search/picker UI
- the restore workflow recreates or reopens the deleted content explicitly and safely
- path changes do not orphan earlier history entries

---

## AT-69 — Multi-file history transactions are grouped and labeled

**Purpose:**  
Verify that high-risk multi-file edits appear as one understandable history event.

**Preconditions:**  
- a project fixture supports a semantic rename, import rewrite, or safe multi-file fix
- local history is enabled

**Steps:**  
1. Perform a multi-file operation such as semantic rename or grouped import rewrite.
2. Open local history for one affected file and inspect the relevant entry.
3. Inspect the grouped transaction metadata and affected-file list.
4. Restore the grouped change through the provided workflow.

**Expected Result:**  
- the multi-file change is represented as one labeled transaction rather than unrelated per-file mystery entries
- the UI shows which files were affected by the grouped change
- restoring the grouped transaction behaves deterministically and leaves the project in a coherent state
- users can understand why the entry exists and what action created it

---

## AT-70 — Retention, exclusions, and large-file guardrails behave predictably

**Purpose:**  
Verify that local history storage remains bounded and supportable on constrained systems.

**Preconditions:**  
- local history settings are available
- the project includes at least one excluded file pattern target and one oversized file fixture

**Steps:**  
1. Configure retention limits such as max entries per file or retention days.
2. Save repeated revisions of one tracked file until pruning should occur.
3. Save changes to an excluded file.
4. Attempt to create local history entries for an oversized file.

**Expected Result:**  
- older entries are pruned according to the configured retention policy
- excluded files do not generate local-history entries
- oversized files are skipped or degraded according to the documented guardrails
- the user receives clear, supportable feedback when history is intentionally not recorded

---

## AT-71 — Local history diff and recovery UI stays readable and responsive

**Purpose:**  
Verify that local-history workflows are usable in both themes and do not introduce unacceptable UI stalls.

**Preconditions:**  
- local history UI is implemented
- editor can switch between light and dark mode
- a medium-size file with multiple revisions is available

**Steps:**  
1. Open local history in light mode and inspect add/remove diff styling.
2. Repeat in dark mode.
3. Select several revisions in sequence and observe diff-loading responsiveness.
4. Trigger a recovery compare flow from a draft or older checkpoint.

**Expected Result:**  
- diff colors, labels, buttons, and selection states are readable in both light and dark themes
- revision switching and diff generation feel responsive for normal editing workflows
- the history UI uses lazy loading or equivalent safeguards rather than freezing the editor on open
- success, warning, and recovery states remain understandable in both themes

---

## 13. Minimum MVP Gate

The following tests are the minimum gate for MVP:

- AT-01 — Editor launches successfully
- AT-03 — Valid project opens successfully
- AT-24 — Existing Python folder imports on first open
- AT-05 — Project tree displays project contents
- AT-06 — File opens in editor tab
- AT-07 — File can be edited and marked dirty
- AT-08 — Save writes file changes to disk
- AT-10 — Run launches user code in a separate runner process
- AT-11 — Successful run shows stdout in console
- AT-12 — Failed run shows traceback information
- AT-13 — stderr is visible to the user
- AT-14 — Per-run log file is written to disk
- AT-15 — Stop terminates a long-running script safely
- AT-16 — Editor survives user-code failure

MVP is **not complete** until all minimum-gate tests pass on the real target runtime.

---

## 14. Completion Rule

A feature is not considered complete merely because code exists.

A feature is complete only when:

1. the implementation exists
2. the expected behavior is observable
3. the behavior works in the real target runtime
4. failure cases are understandable and diagnosable
5. the relevant acceptance tests pass

---

## 15. Maintenance Rules

Update this file when:

- a new MVP workflow is added
- the required validation behavior changes
- a feature moves into or out of MVP scope
- a test is split because it became too broad
- implementation reveals a more accurate pass/fail condition

Keep this file focused on:
- user-visible behavior
- runtime validation
- end-to-end success criteria

Do not turn this file into a unit test inventory.