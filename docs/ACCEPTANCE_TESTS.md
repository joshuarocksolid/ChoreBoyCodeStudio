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

## AT-43 — Preview tab mode across explorer/navigation surfaces

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

## 11. Minimum MVP Gate

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

## 12. Completion Rule

A feature is not considered complete merely because code exists.

A feature is complete only when:

1. the implementation exists
2. the expected behavior is observable
3. the behavior works in the real target runtime
4. failure cases are understandable and diagnosable
5. the relevant acceptance tests pass

---

## 13. Maintenance Rules

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