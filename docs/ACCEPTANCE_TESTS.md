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
3. open and edit `run.py`
4. save changes
5. run user code in a separate runner process
6. view stdout/stderr
7. view traceback on failure
8. write per-run logs
9. stop a running script safely

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
A minimal project whose `run.py` prints output and exits successfully.

Example behavior:
- prints `START`
- prints a few lines
- exits with success

### B. Failure Project
A minimal project whose `run.py` raises an exception.

Example behavior:
- prints one line
- raises an exception with traceback

### C. Long-Running Project
A minimal project whose `run.py` keeps running until stopped.

Example behavior:
- prints `tick` repeatedly
- remains active long enough to test Stop behavior

### D. Invalid / Non-importable Project
A folder that cannot be treated as a Python project, such as:
- no `.cbcs/project.json` and no `.py` files
- corrupted/invalid `.cbcs/project.json`

Used to verify project validation and actionable errors.

### E. Importable Existing Python Folder
A plain Python folder without `.cbcs/project.json` that includes runnable `.py` files.

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
  - already containing `.cbcs/project.json`, or
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
- if metadata was missing but the folder is importable, `.cbcs/project.json` is initialized automatically

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
- folder does not contain `.cbcs/project.json`

**Steps:**  
1. Launch the editor.
2. Choose **Open Project**.
3. Select the importable Python folder.

**Expected Result:**  
- the folder opens as a project without manual metadata setup
- `.cbcs/project.json` is created with canonical defaults
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
- project contains `run.py`

**Steps:**  
1. In the project tree, click `run.py`.

**Expected Result:**  
- `run.py` opens in an editor tab
- file contents are visible
- the current active file is clear in the UI
- opening the same file again does not create unnecessary duplicate tabs

---

## AT-07 — File can be edited and marked dirty

**Purpose:**  
Verify editable state and unsaved-change tracking.

**Preconditions:**  
- `run.py` is open in an editor tab

**Steps:**  
1. Modify the contents of `run.py`.
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
- `run.py` is open and modified

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
- `run.py` is runnable

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
- expected diagnostic artifacts are included
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
- valid project is open

**Steps:**  
1. Start Python Console mode.
2. Submit commands (e.g., `x = 2`, `print(x + 3)`).
3. Exit console session.

**Expected Result:**  
- submitted commands are accepted via stdin bridge
- output appears in console transcript
- session terminates cleanly on exit/stop

---

## AT-27 — Project tree file operations parity

**Purpose:**  
Verify modern explorer actions are available and reliable from the project tree.

**Preconditions:**  
- project with nested files/folders is open

**Steps:**  
1. Use tree context menu for create/rename/delete/duplicate.
2. Use cut/copy/paste and drag-drop move.
3. Use copy path / copy relative path / reveal in file manager.

**Expected Result:**  
- filesystem operations complete successfully with clear confirmations on destructive actions
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