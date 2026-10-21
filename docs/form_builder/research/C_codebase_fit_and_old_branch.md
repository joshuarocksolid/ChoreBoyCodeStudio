# Where a visual GUI builder fits in ChoreBoy Code Studio

Read-only investigation of `/Users/local/Projects/ChoreBoyCodeStudio` and branch `origin/cursor/qt-ui-designer-implementation-3f01`. Nothing in that repo was checked out, edited, committed, or deleted.

Baseline. Local `main` is `791bbf0a35582cffe63f2f98874429e5b5277fa7`, two commits ahead of `origin/main` and fifteen behind. `origin/main` is `024b30a`. Files under `app/run` were read from the working tree. The run explorer reported those files match `origin/main`. Settings location, product version, and feature specs were read with `git show origin/main:<path>` because the working tree is behind. The designer branch was read only with `git show` and `git grep`. Tip `62da66aa153c208793059d07d53cacf30c8ecca6`. Merge-base with local `main` is `0d5cbca60549e75f891097ba62a9e5b85252de45`.

throughput checkpoint: n/a, read-only investigation.

## Overview

ChoreBoy Code Studio is a Qt shell that runs inside FreeCAD AppRun. User programs run in a second AppRun process. A `.ui` file today is a text tab with XML highlighting. There is no visual builder in the tree. `app/designer` is not on disk and not in git.

The place a builder fits is the same split Markdown already uses. A feature package owns the surface. `EditorTabFactory` in the shell decides when to show it. Save and dirty state stay on `EditorTabState`. A preview of a generated app is a normal Run of a `.py` entry through `RunService`. There is no second runner and no in-editor preview window.

The prior branch built a Qt Designer-shaped package that never drew a form. Its canvas is a `QTreeWidget`. Real widgets appear only when preview loads XML with `QUiLoader`. Its own audit said repeated drops and Preview Form failed, then later notes marked many of those items resolved without rewriting the failure table. The report still says resize handles are missing because the canvas is a tree.

## Key concepts

`EditorTabState` in `app/editors/editor_tab.py` is the buffer. Dirty means `current_content` differs from `original_content`. `EditorManager` owns the map of open files and writes them with `atomic_write_text`.

`EditorTabFactory` in `app/shell/editor_tab_factory.py` is the only tab factory. Every open builds a `CodeEditorWidget`. Markdown is the only later wrap.

`FeatureSpec` in `app/features/spec.py` is how a product surface is added without a new `install_*` phase. On `origin/main` the specs are `markdown`, `shop-lan-state`, and `hidden-path-policy`. The working tree at `791bbf0` lists only `markdown`.

`RunService.start_run` writes a manifest and starts one child. If the executable is AppRun, the command is `AppRun -c` plus a `runpy` payload. The child then runs the project entry with `runpy.run_path`.

`UIModel` is the name on the designer branch for the in-memory form. The on-disk file in that plan, and in the branch code, is Qt `.ui` XML.

## How a file becomes a tab

1. Open goes through `EditorTabFactory.open_file_in_editor` at lines 37 to 53 of `app/shell/editor_tab_factory.py`. The project tree, File, Open, and file drop all land there.
2. `EditorManager.open_file` reads UTF-8. A non-UTF-8 file raises `ValueError` and becomes a warning dialog.
3. `_materialize_opened_editor_tab` builds `CodeEditorWidget`, sets object name `shell.editorTabs.textEditor` at line 92, copies `tab.current_content` into the widget, and calls `set_language_for_path`.
4. Language is an extension lookup. `app/treesitter/language_specs.py` lines 58 to 66 put `.ui` on the XML grammar, next to `.xml`, `.jrxml`, `.svg`, `.xsl`, and `.qrc`.
5. `wrap_tab_content_if_markdown` runs at lines 117 to 123. Any other extension, including `.ui`, is added as the raw text widget. The tab tooltip is the file path.
6. `textChanged` copies the widget text back into `EditorManager.update_tab_content`. Save writes `tab.current_content`.

`docs/designer/ARCHITECTURE_PLAN.md` lines 167 to 173 still say `MainWindow._open_file_in_editor()` always opens `CodeEditorWidget`, and that a future router should send `.ui` to `DesignerEditorSurface`. That method name is stale. The factory is the seam. Markdown already proved a second surface can exist beside the text widget.

## Where things live

| Area | Path |
| --- | --- |
| Tab factory | `app/shell/editor_tab_factory.py` |
| Buffer | `app/editors/editor_manager.py`, `app/editors/editor_tab.py` |
| Markdown pattern | `app/features/markdown/`, `app/features/spec.py` |
| Feature law | `dune.yaml`, `tools/dune/composition.py`, `tools/dune/file_roles.py`, `tools/dune/handles.py` |
| Plugins | `app/plugins/contributions.py`, `docs/plugins/SDK.md` |
| Run | `app/run/run_service.py`, `app/run/runner_command_builder.py`, `app/run/runtime_launch.py`, `app/runner/runner_main.py` |
| Run click path | `app/shell/run_launch/active_file_launch.py` |
| Qt app template | `templates/qt_app/main.py` |
| Project file | `cbcs/project.json`, parsed by `app/project/project_manifest.py` |
| Packaging | `app/packaging/packager.py`, `app/packaging/dependency_audit.py`, `package.py` |
| Settings | `app/persistence/settings_store.py`, `app/core/constants.py` |
| Theme | `app/shell/shell_theme_workflow.py`, `app/shell/style_sheet.py` |
| Tests | `tests/conftest.py`, `run_tests.py` |
| Designer plan on main | `docs/designer/ARCHITECTURE_PLAN.md`, `TASKS.md`, `WIREFRAME.md` |
| Prior implementation | branch `origin/cursor/qt-ui-designer-implementation-3f01`, package `app/designer/` |

`docs/TASKS.md` lines 15 to 19 only point at the designer docs. `docs/PRD.md` milestones do not include a visual builder. `docs/manual_complete/style_guide.md` line 66 says the Designer subsystem is unreleased and must not be documented as available.

## Integration map

| Concern | Hook | Path | What a new builder does |
| --- | --- | --- | --- |
| Open a `.ui` | `EditorTabFactory._materialize_opened_editor_tab` | `app/shell/editor_tab_factory.py` lines 91 to 123 | Choose the visual surface for `.ui` here, the same place Markdown wraps the text widget. |
| Dirty and save | `EditorTabState.current_content` | `app/editors/editor_tab.py` lines 39 to 42, `EditorManager.save_tab` | The canvas writes the serialized `.ui` into `current_content` on each edit. Save already persists that string. |
| Feature ownership | `FEATURE_SPECS` and `dune.yaml` | `app/features/spec.py`, `dune.yaml` lines 15 to 19 | Add a feature package under `app/features/<id>/` with its own owner. `scripts/new_feature.py` is the scaffold. The generated verify note still needs a `dune-owners` comment or the feature-map check fails. |
| Window wiring | feature `install` hook | `app/shell/main_window_composition.py` lines 42 to 44 | Bind window fields from the feature package. Do not add an eighth `install_*` function. `tools/dune/composition.py` line 15 sets `_COMMITTED_INSTALL_COUNT` to 7. |
| Object names | handle law | `tools/dune/handles.py` lines 15 to 28 | Every `setObjectName("shell....")` must be listed in `.cursor/skills/verify-cbcs/references/handles.md`. `shell.editorTabs.textEditor` may be assigned once. A canvas needs its own names. |
| Import law | file roles | `tools/dune/file_roles.py` lines 35 to 54 | `app.plugins` cannot import PySide2. `app.shell` and `app.editors` cannot import `app.runner` or `app.packaging`. `app.features` has no such ban, which is why Markdown can import PySide2. |
| Menus and shortcuts | menu builders | `app/shell/view_menu_builder.py`, `app/shell/run_menu_builder.py`, `app/shell/shortcut_preferences.py` | Markdown's view commands are hardcoded in the shell, not contributed by the feature. Designer commands belong there too. F5 is already Run Active File. |
| Plugins | commands, events, workflows | `app/plugins/contributions.py`, `app/plugins/events.py` | A plugin can add a Tools command. It cannot register a Qt editor or panel. `docs/plugins/SDK.md` excludes editor-process UI mutation. This is the wrong host. |
| Problems | `ProblemsController` | `app/shell/problems_controller.py` | Diagnostics are pushed onto `CodeEditorWidget.set_diagnostics`. A canvas that wants the Problems panel needs that method or a parallel path. |
| Run and preview | `RunService.start_run` | `app/run/run_service.py`, `app/run/runner_command_builder.py` lines 14 to 20 | Preview by running a generated `.py` entry. Do not start a second supervisor. |
| Active file rule | suffix check | `app/shell/run_launch/active_file_launch.py` lines 59 to 61 | F5 refuses anything that is not `.py`. A `.ui` tab cannot be the run entry. |
| Project entry | `default_entry` | `templates/qt_app/template.json`, `app/templates/template_service.py` | Point `cbcs/project.json` at a `main.py` that builds or loads the window. |
| Packaging | `package_project` | `app/packaging/dependency_audit.py` lines 77 to 100, `app/packaging/layout.py` line 12 | A syntax error is recorded as degraded and the audit continues. Native extensions in the user payload are blocking because writable mounts are `noexec`. Install slot is `~/.local/share/FreeCAD/Macro/Apps`. |
| Settings | JSON merge, no registry | `app/persistence/settings_store.py`, `origin/main` `app/core/constants.py` lines 278 to 296 | Add a key in `constants.py`, parse it in `app/shell/settings_models.py`, and add a control in the settings dialog. Theme and keybindings are global-only. Project files may override `editor`, `intelligence`, `linter`, `file_excludes`, `local_history`, and `output`. |
| Theme | explicit callbacks | `app/shell/shell_theme_workflow.py` | QSS is built in Python. A new surface is themed only if a callback or a matching selector is added. |
| Capability probe | PySide2 import | `app/bootstrap/capability_probe.py` | `docs/PRD.md` lines 349 to 350 ask the probe to confirm PySide2 and QtUiTools. Designer task D0.S1.T1 is still `TODO` in `docs/designer/TASKS.md` lines 74 to 82. The probe does not check `QUiLoader`. |
| Highlight only | XML grammar | `app/treesitter/language_specs.py` lines 58 to 66 | Keep XML highlighting if a text view of `.ui` remains. Jedi, Rope, outline, and lint are Python-only. |

## Constraints the builder must respect

**Python 3.9.2 is the documented ChoreBoy runtime.** `docs/DISCOVERY.md` lines 37 to 43 say FreeCAD AppRun ships Python 3.9.2 and that application code, vendored libraries, and tests must stay on 3.9. Banned examples named there are `match` and `case`, `ExceptionGroup`, and `type` aliases. `app/packaging/tree_sitter_cp39.py` lines 3 to 6 say the shipped product runs on that 3.9.2 AppRun and that developers often fill `vendor_py311` while packaging reads `vendor_py39`. `tests/conftest.py` line 40 tells a developer to install pytest-timeout into `/opt/freecad/usr/lib/python3.11/site-packages/`. That line shows a 3.11 AppRun on at least one dev machine. It does not change the written product target.

**Public FreeCAD 1.1 is Python 3.11 and Qt 6.** FreeCAD 1.1.0 was published on 2026-03-25. Linux assets are named `py311`. The release page is https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.0. The wiki says the release date is 24 March 2026. That page is https://wiki.freecad.org/Release_notes_1.1. A user-pasted About box in a Windows bug report reads `Python 3.11.15, Qt 6.8.3, Coin 4.0.3` and `PySide 6.8.3`. That report is https://github.com/FreeCAD/FreeCAD/issues/28993. The developer handbook says current FreeCAD development wants Python 3.11 or later and Qt 6.4 or later, and that Python code should `import PySide` with no numeric suffix because the build generates the binding. That page is https://freecad.github.io/DevelopersHandbook/gettingstarted/dependencies.html.

**The ChoreBoy 1.1 image is not verified here.** The brief says a FreeCAD 1.1 test update reached ChoreBoy around 2026-09-29 and reportedly includes PySide6, Python 3.11, bundled psycopg, pg8000, tree-sitter, and wider permission to launch desktop apps. Public release notes searched for this report do not list psycopg, pg8000, or tree-sitter as FreeCAD 1.1 bundles, and they do not describe ChoreBoy. Treat that image as an unverified report. CBCS already vendors psycopg for its own editor. `docs/DISCOVERY.md` line 31 says Postgres goes through vendored psycopg 3 or pg8000. `docs/CHOREBOY_RUNTIME_PITFALLS.md` lines 33 to 39 still describe production as Python 3.9.2 and PySide2.

**AppRun is the process.** `docs/ARCHITECTURE.md` lines 66 to 67 say the guaranteed runtime is FreeCAD's embedded Python through `/opt/freecad/AppRun`, and that PySide2 is available inside it. `app/core/constants.py` line 5 sets `APP_RUN_PATH` to `/opt/freecad/AppRun` on both the working tree and `origin/main`. `docs/PRD.md` lines 72 to 74 say the editor is one AppRun Qt process and all user code runs in a separate AppRun process.

**Subprocess is mostly `/bin/sh`.** `docs/DISCOVERY.md` lines 204 to 206 say `/bin/sh` is the only binary a confined script can execute. AppArmor blocks `/bin/bash`, `/usr/bin/python3`, and `/usr/bin/env`. A builder must not grow its own launcher. It has to call `RunService`, which already builds the AppRun command.

**No general internet.** `docs/PRD.md` line 38 lists internet workflows as a non-goal because ChoreBoy is LAN-only.

**Qt widgets stay on the GUI thread.** `docs/CHOREBOY_RUNTIME_PITFALLS.md` lines 195 to 202 say a widget change from a worker thread segfaults, often inside `QBoxLayout::setGeometry`. `docs/ARCHITECTURE.md` line 1637 says no expensive operation should block the Qt UI thread for a noticeable period. Highlight gates at lines 1664 to 1666 are p95 at or under 300 ms for a full Python rehighlight of about 2,000 lines, p95 at or under 140 ms for an incremental refresh, and p95 at or under 150 ms per editor for a theme switch across 10 editors. A live canvas of real widgets has to stay inside those bounds on low-end hardware. The docs do not give a CPU model for that hardware.

**Tests are offscreen.** `tests/conftest.py` line 27 sets `QT_QPA_PLATFORM` to `offscreen` before the session `qapp` fixture. `docs/TESTS.md` says the same default in `run_tests.py`, so tests do not need a display. A canvas test that requires a visible window will not match this harness.

**Packaging does not hard-fail on 3.10 syntax.** `ast.parse` failure becomes a degraded issue and the audit continues. `app/packaging/dependency_audit.py` lines 77 to 100. Generated code can still be unusable on Python 3.9 if a developer packages from a newer interpreter. The safe generator target is 3.9 and `PySide2`, matching `templates/qt_app/main.py`, which calls `app.exec_()`.

**`.ui` load on device is already proven for PySide2.** `docs/DISCOVERY.md` lines 210 to 217 say `PySide2.QtUiTools` works with a real `.ui` file, and the proven path is to design the file on another machine, copy it, and load it with `QUiLoader`. The current app never calls `QUiLoader`. The only `app/` hit is a completion label in `app/intelligence/api_index.py` line 65.

**The designer plan cites Qt 6 docs while the product imports PySide2.** `docs/designer/ARCHITECTURE_PLAN.md` lines 16 to 18 link `doc.qt.io/qt-6` and Qt for Python 6. A `.ui` file is shared. Widget class names and `exec_` versus `exec` are not.

## How a generated app is run and previewed

Run Active File is F5. `app/shell/run_menu_builder.py` registers it. The handler requires the active tab to end in `.py`. A dirty buffer is written to a temp `cbcs_<stem>_*.py` and run with `skip_save`. Run Project uses `default_entry` from `cbcs/project.json`, which the Qt template sets to `main.py`.

`build_runner_command` in `app/run/runner_command_builder.py` lines 14 to 20 returns `[AppRun, "-c", payload]` when the executable name is `AppRun`, `freecad`, `FreeCAD`, or the suffix is `.AppImage`. The payload is built in `app/run/runtime_launch.py` lines 38 to 59. It inserts the repo on `sys.path`, sets `sys.argv` to `run_runner.py --manifest <path>`, and calls `runpy.run_path`. `app/runner/runner_main.py` lines 104 to 105 run the entry the same way with `run_name="__main__"`, so `if __name__ == "__main__"` is true.

`templates/qt_app/main.py` lines 7 to 14 are the window pattern. Create `QApplication` if needed, construct `MainWindow`, call `show`, return `app.exec_()`. The runner deletes already-imported `app` and `app.*` modules before user code so Code Studio's package does not shadow a user package also named `app`.

The child environment is a copy of the parent environment, minus `VIRTUAL_ENV` and `VIRTUAL_ENV_PROMPT`. `QT_QPA_PLATFORM` is inherited. An offscreen test editor would preview offscreen. A desktop editor would show a real top-level window. Nothing in `app/run` creates an embedded preview surface. Supervisor events are output, exit, state, and debug.

A phase-1 preview is therefore a generated `main.py` that builds the layout in Python, or that loads the saved `.ui` with `QUiLoader` inside the user process, with `default_entry` pointed at that file. F5 on that file, or Run Project, is the preview. The window belongs to the child process. A crash there does not kill the editor, which is the reason `docs/PRD.md` lines 72 to 74 split the processes.

The architecture plan at lines 190 to 195 allows `QUiLoader` of a pure `.ui` inside the editor process, and an isolated runner only when promoted widgets import project code. The prior branch implemented that split and the manual smoke still could not see a preview window. This report's recommendation is to use the existing run path as the only preview until a separate in-editor load is shown to put a window on screen. The operator could still follow the plan and keep an in-editor `QUiLoader` for forms that contain no project code.

## Prior branch post-mortem

**What was measured.** `git rev-list --count` from the merge-base to the branch tip is 212 commits. `git log` limited to `app/designer` and `docs/designer` in that range is 50 commits. The brief's figure of about 285 commits was not reproduced. `app/designer` at the tip is 58 files and 287,241 bytes. `editor_surface.py` is 2,120 lines. `widget_registry.py` contains 29 lines that call `PaletteWidgetDefinition`. `git grep` of `app/designer` for `paintEvent` and `QGraphics` returned no hits.

**Who wrote it.** Planning commit `fdb9e10` is reported by the source-control pass as joshuarocksolid, subject `Add dedicated designer planning docs folder (#11)`, co-authored by Cursor Agent. This investigation did not re-open that commit. Implementation commits on 2026-03-05 are authored by Cursor Agent. UX commit `71e1982` is `Qt UI/UX audit (#39)`. Audit commit `7a9ef054688a5e0d9c47385f83e88b580cce9d07` is `Add designer parity audit report and follow-up backlog`, Cursor Agent, 2026-03-26. Tip `62da66a` is `Designer audit plan (#41)`, joshuarocksolid, 2026-03-27. The `#41` message lists seventeen follow-up commits, including snapshot insertion, preview retention, an isolated-preview timeout, grid item attributes, F5 and F6 arbitration, and palette tranches. `gh pr view` was run by the source-control pass and was not repeated here. That pass said PR bodies for 39, 40, and 41 are Cursor's generated-PR boilerplate.

**File format.** Direct from the plan, which is identical on `main` and on the branch. `docs/designer/ARCHITECTURE_PLAN.md` lines 25 to 30 say the internal `UIModel` is canonical, the reader and writer follow Qt `.ui` for a supported subset, and every save is checked by loading through `QUiLoader`. Early tags are `ui`, `class`, `widget`, `layout`, `item`, and `property`. Later tags include connections, tab stops, resources, and custom widgets.

**Canvas.** Direct from the tip. `FormCanvas` in `app/designer/canvas/form_canvas.py` lines 30 to 57 is a `QWidget` whose body is a `QLabel` reading `FORM STRUCTURE` and a `QTreeWidget` named `designer.canvas.tree`. `_build_tree_item` at line 299 sets the row text to `objectName : class`. Dropping from the palette mutates `UIModel` and rebuilds the tree. The class docstring calls this a canvas. The pixels are a tree.

**Undo.** Direct. `app/designer/commands/command_stack.py` lines 1 to 18 store `before_xml` and `after_xml` and replay those strings. The architecture plan names per-operation command modules. The tip has only `command_stack.py` under `app/designer/commands/`. No commit message located by the source-control pass says the snapshot stack replaced those modules. That absence is a gap.

**Preview.** Direct. `app/designer/preview/preview_service.py` lines 32 to 37 load a widget with `PySide2.QtUiTools.QUiLoader`. `editor_surface.py` lines 200 to 210, if `requires_isolated_preview` is true, run a subprocess probe and return after a status line. That branch does not call `load_widget_from_ui_xml` and does not show a window. Other forms load a widget, keep it on `_active_preview_widget`, and show it.

**What the audit said, in its own words.** `docs/designer/AUDIT_REPORT.md` on the tip, first written in `7a9ef05`.

The automated block at line 12 says `python3 run_tests.py -v tests/unit/designer` had 104 passed. Those tests were not re-run for this report.

The subsystem table still says Canvas is `ISSUE` because the first drop works and later drops fail when selection lands on a non-container, and because the drop path skipped the command stack. Preview is `ISSUE` because a manual smoke invoked the menu and did not observe a window, and because the isolated subprocess could hang. Phase 2 row 9 is `Preview Form` with status `FAIL`. Row 3 is drag and drop of `QPushButton` with status `FAIL` after the first drop.

Line 267 still says resize handles are not implemented, and it names the cause as a tree-structured canvas.

The same file later stamps PR-01 through PR-07 and several later items `RESOLVED` on 2026-03-26. The Phase 1 table and the Phase 2 `FAIL` rows were not rewritten. Grid attributes are still `Missing` in the gap table at line 221 while a later note says that round-trip was added. Section E still says there is no action editor. The tip contains `app/designer/actions/action_editor_panel.py`. These contradictions are in the file. This investigation did not decide which stamp is true by running the suite.

**Why the canvas is a tree.** Unknown. No commit message or doc located in this pass states a reason. The wireframe at `docs/designer/WIREFRAME.md` asks for a live editable form. The audit records the shape. The commits and docs that were searched do not record a reason.

**Tests on that branch.** The audit names unit, integration, and one runtime-parity file, `tests/runtime_parity/test_designer_quiloader_runtime.py`. The source-control pass quoted that file setting `QT_QPA_PLATFORM` to `offscreen` and skipping when AppRun is missing. Model tests construct a `UIModel` without Qt. Canvas tests construct `QApplication` if none exists. This report did not re-execute them.

`docs/designer` diff from `main` to the branch, measured here. `ARCHITECTURE_PLAN.md` is unchanged. `WIREFRAME.md` and `TASKS.md` change. `AUDIT_REPORT.md` exists only on the branch, 438 lines. On the branch, `TASKS.md` marks the original cards done and adds later cards also marked done. Main's `docs/ACCEPTANCE_TESTS.md` has no designer section 10A. The branch text that points at 10A does not match main.

## What to keep

These are contracts the plan states and that the audit did not reject as ideas. They also match the current editor.

- Keep `UIModel` as the in-memory document and Qt `.ui` XML as the file. Users can still open the file in another Qt tool, which is the path `docs/DISCOVERY.md` lines 214 to 217 already proved.
- Keep unknown XML on round-trip so a file edited outside Code Studio does not lose nodes the builder does not understand yet.
- Keep `QUiLoader` as a separate check that the bytes are a form Qt can load. Discovery already showed that loader works on ChoreBoy under PySide2.
- Keep project Python out of the editor process. `docs/PRD.md` lines 72 to 74 and `docs/designer/ARCHITECTURE_PLAN.md` line 9 both say this.
- Keep one undo log, and send every mutation through it. The audit's drop bug was a path that skipped `CommandStack`. The snapshot stack itself is what the later fixes routed drops through. Full-document XML snapshots are a reasonable phase-1 mechanism for layout edits. The plan's per-command classes were never added.
- Keep a data-driven palette registry, separate from the widget that displays it.
- Keep the test split. Pure model tests with no `QApplication`. Offscreen widget tests. One AppRun runtime-parity smoke that loads a fixture through `QUiLoader`.
- Keep diagnostics in the existing Problems panel once the canvas can accept them.
- Keep F5 as Run. The `#41` work added focus-scoped shortcut arbitration because designer modes had collided with Run.

## What to discard

- Discard the tree as the editing surface. `FormCanvas` shows `objectName : class`. The wireframe asked for a form with resize handles. The audit at line 267 still says those handles are missing. A layout builder that does not show the layout will teach the wrong model, and the first-drop failure came from selection landing on the inserted leaf.
- Discard `editor_surface.py` as the place where insertion, preview, clipboard, layout, modes, and actions all live. It is 2,120 lines at the tip.
- Discard Qt Designer parity as the phase-1 scope. Signals and slots, buddy mode, tab order, action editors, and a 29-entry palette landed while the form itself was still a tree. Phase 1 in the product brief is layouts. The branch inverted that order.
- Discard an audit file that leaves `FAIL` and `Missing` in the summary after later notes say resolved. The next design needs one status per behavior.
- Discard the isolated preview that returns success without showing a window. `editor_surface.py` lines 200 to 210 do that.
- Discard a hard cutover that removes the XML text tab before the visual surface is trustworthy. `docs/ACCEPTANCE_TESTS.md` AT-32 requires opening a `.ui` and seeing XML highlighting. `docs/PRD.md` line 128 lists `.ui` as a text-editor type. A text view remains the escape hatch.
- Discard designer shortcuts that reuse F5, F6, Ctrl+R, or Ctrl+Shift+S. Those keys already belong to Run, debug continue, go to symbol, and Save All in the shell shortcut table.
- Discard a plugin as the host. The plugin API has no editor contribution, and `app.plugins` cannot import PySide2.
- Discard a new top-level `install_*` phase. The composition check fails above 7.
- Discard generating Python 3.10 or PySide6-only code while `docs/DISCOVERY.md` and `templates/qt_app/main.py` still target 3.9 and PySide2. Switch the generator when the product drops FreeCAD 1.0, not before that sentence is true in the docs.

## Gotchas

The open-file seam in `docs/designer/ARCHITECTURE_PLAN.md` names `MainWindow._open_file_in_editor` and `app/shell/menus.py`. Both are stale. Route `.ui` in `EditorTabFactory`.

`shell.editorTabs.textEditor` is one shared object name for every text tab. A second assignment fails `tools/dune/handles.py`. A canvas must not reuse it.

Feature `install` runs before `install_editor_project_wiring` creates `EditorTabWorkflow`. The feature can bind fields. It cannot call the tab workflow during `install`.

Completion is attached to every `CodeEditorWidget`, including non-Python files, from `editor_tab_factory.py` lines 102 to 106. Outline and lint refuse non-Python. A `.ui` text view can still ask Jedi for Python completions. A canvas that skips `CodeEditorWidget` also skips those text bindings.

`system` theme detection runs `gsettings`. Discovery says confined subprocesses are limited to `/bin/sh`. On failure the theme code treats the desktop as not dark. A builder should follow the shell tokens it is given and not start its own settings process.

Local history restore calls `setPlainText` on the text widget. A canvas that does not implement that path will drop draft restore unless save keeps the XML in `EditorTabState` and the canvas reloads from it.

`origin/main` moves global state to `/home/default/FreeCAD/CBCS/state` at `app/core/constants.py` line 12 of that commit. The working tree at `791bbf0` is still version `0.4.10` and still uses the older state dirname. A builder that writes settings must use `SettingsService`.

The designer docs on `main` are a plan with every task card `TODO`. The branch's `DONE` stamps are not on `main`. Do not treat the branch task list as the current backlog.

## Sources consulted

- Working tree and `git show origin/main` for the editor, run, settings, and docs cited above.
- `git show`, `git grep`, `git diff --stat`, and `git ls-tree` on `origin/cursor/qt-ui-designer-implementation-3f01`.
- Web pages cited in the constraints section. Fetched 2026-10-20.
- Source control pass also ran `gh pr view` for PRs 11, 39, 40, and 41. Those bodies were not re-fetched in the parent.
- Issue tracker, team chat, observability, error tracking, and product analytics were not searched. No MCP in this session maps to the ChoreBoy Code Studio project for those categories. `rocksolid-ops` is a different product and was not queried.

## Outcome

done

## What changed

Created `report_C.md` in the scratchpad. No repo file was modified.

## Verification

Commands run from `/Users/local/Projects/ChoreBoyCodeStudio`.

- `git rev-parse` of local `main` is `791bbf0`. The branch tip is `62da66a`. Merge-base is `0d5cbca`.
- `git rev-list --count` from the merge-base to the tip is 212. Commits in that range touching `app/designer` or `docs/designer` number 50.
- `git ls-files app/designer` is empty. `ls app/designer` fails with no such directory.
- `git diff --stat main origin/cursor/qt-ui-designer-implementation-3f01 -- docs/designer` shows `AUDIT_REPORT.md` added, `TASKS.md` and `WIREFRAME.md` changed, and `ARCHITECTURE_PLAN.md` absent from the diff.
- `git show` of `form_canvas.py` at the tip shows `QTreeWidget` and the label `FORM STRUCTURE`. `git grep` finds no `paintEvent` or `QGraphics` under `app/designer` on that commit.
- `command_stack.py` at the tip stores `before_xml` and `after_xml`.
- `editor_surface.py` at the tip is 2,120 lines. Lines 200 to 210 return after an isolated probe without loading a widget.
- `preview_service.py` imports `QUiLoader`.
- `git grep -c PaletteWidgetDefinition` on that file is 29. `git ls-tree -l` sums to 58 files and 287,241 bytes.
- `AUDIT_REPORT.md` at the tip contains both the `ISSUE` and `FAIL` rows and later `RESOLVED` stamps, including line 267 on the tree canvas.
- Working-tree reads confirm `EditorTabFactory` lines 91 to 123, `.ui` on the XML grammar, F5's `.py` check, `build_runner_command`, `runpy.run_path`, `templates/qt_app/main.py`, offscreen tests, degraded syntax audit, Python 3.9.2 in `docs/DISCOVERY.md`, and `_COMMITTED_INSTALL_COUNT = 7`.
- `git show origin/main:app/features/spec.py` lists markdown, shop-lan-state, and hidden-path-policy. `git show origin/main:app/core/constants.py` shows version `0.4.14` and state root `/home/default/FreeCAD/CBCS/state`.
- The designer unit suite was not re-run. The 104 passed figure is a quote from the audit file.

## Decisions made

The integration baseline is `origin/main` for settings and feature specs, and the working tree for `app/run`, because those run files were reported identical and the launch functions were re-read locally. The operator could instead require every citation to be re-read from `git show origin/main` after a fast-forward.

The builder should be a feature package plus a small route in `EditorTabFactory`, following Markdown. The operator could instead revive `app/designer/` as its own `dune.yaml` owner, which is what `docs/designer/ARCHITECTURE_PLAN.md` still sketches.

Preview should be a generated `.py` entry through `RunService`. The operator could instead implement the plan's in-editor `QUiLoader` for forms that do not import project code.

Generated code should stay on Python 3.9 and PySide2 until the docs say FreeCAD 1.0 is unsupported. The operator could dual-target PySide2 and PySide6 now.

The how explainer and the why synthesizer were not spawned. Explorers ran on `grok-4.7-high` because `grok-4.7-xhigh-fast` is not an allowed slug. The parent wrote this report after checking the load-bearing lines. The operator could ask for a second-model rewrite.

## Open issues and risks

The ChoreBoy FreeCAD 1.1 image, its Python version, its PySide binding, and any AppArmor change are unverified outside the brief.

The branch audit contradicts itself. Resolved notes and `Missing` rows describe the same behaviors. A fresh test run on `62da66a` was not done, and checking out that branch was out of scope.

`docs/ACCEPTANCE_TESTS.md` AT-32 and a visual `.ui` surface disagree. The product has to say whether the text tab stays.

No author text explains why the canvas became a tree. The next design should not inherit that shape without a new reason.

Local `main` is fifteen commits behind `origin/main` and the worktree is dirty in `.cursor`, `.agents`, and `vendor`. Those dirty files were not part of this research.
