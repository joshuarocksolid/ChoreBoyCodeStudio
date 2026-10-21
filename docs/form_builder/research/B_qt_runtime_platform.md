# Qt runtime for the ChoreBoy GUI builder

Research date 2026-10-20. Read-only. Nothing in any repository was modified.

The GUI builder has to edit layouts on the runtime ChoreBoy Code Studio runs today, and the apps it saves have to open again after a machine moves to PySide6. Upstream FreeCAD 1.1 already shipped on Qt 6. Every runtime probed in this session still imports PySide2. Production ChoreBoy itself was not probed. The repo documents that box as Python 3.9.2 and Qt 5.15.2. Build the editor now. Keep the document model in terms of widgets, layouts, and properties.

## Overview

Two different "1.0" and "1.1" stories are in play.

Upstream FreeCAD 1.1.0 was published on 2026-03-25. The release assets are Python 3.11 builds. There is no Qt 5 asset in that list. A local Mac app on this machine is the conda package `freecad 1.1.3`, Python 3.11.14, PySide6 6.8.3, and Qt 6.8.3. It has no `PySide2` module.

`ssh debian:/opt/freecad` is FreeCAD 1.0.2, Python 3.11.13, PySide2 5.15.15, Qt 5. `PySide6` does not import there. Those two version numbers match the Cursor Cloud column in `AGENTS.md` and `docs/LOCAL_DEV.md`, which list Cloud as Python 3.11.13 and PySide2 5.15.15, and production ChoreBoy as Python 3.9.2 and Qt 5.15.2. `docs/DISCOVERY.md` is the production measurement. It was not re-run on a shop machine in this session.

The paths `~/freecad`, `~/freecad-kp`, and `~/freecad-kp-qt5` do not exist on the debian host. The matching trees are on the Mac under `/Users/local/opt/`.

## Key concepts

**AppRun.** On the Cloud image, `/opt/freecad/AppRun` is a bash launcher that execs `usr/bin/freecad` unless the first argument is a program under `usr/bin`. `AppRun -c "..."` therefore runs FreeCAD's console with a Python snippet. That process inserts `/opt/freecad/usr/Ext` on `sys.path`.

**The PySide shim.** `Ext/PySide/` is a few modules that star-import one real binding. On the Cloud image they star-import PySide2. On the Qt 6 trees they star-import PySide6. `QtGui.py` also star-imports `QtWidgets`, and it aliases `QHeaderView.setResizeMode` to `setSectionResizeMode`.

**Which import a user app sees.** `import PySide` works inside Cloud `AppRun -c` because FreeCAD added `Ext` to the path. The Mac launcher at `/Users/local/opt/freecad/AppRun` is `exec bin/python`. The same snippet there does not see `PySide` at all. `importlib.util.find_spec("PySide")` returned `None`.

**One binding per process.** On `/Users/local/opt/freecad`, a process that loaded PySide2 and then PySide6 aborted with signal 139. macOS logged duplicate Qt 5 and Qt 6 Objective-C classes. Probe each binding in its own process.

## Module matrix

Versions below come from `import` and `qVersion()`, or from `otool` / `ldd` on `libFreeCADGui`, or from conda metadata when the Python module `FreeCAD` itself would not import. A `.so` on disk is not counted as available unless import succeeded.

| Tree | What it is | FreeCAD package | Python | GUI library links | PySide2 | PySide6 |
| --- | --- | --- | --- | --- | --- | --- |
| `ssh debian:/opt/freecad` | Cursor Cloud image. Same versions as `AGENTS.md`. Production ChoreBoy is a different, older image | 1.0.2 `py311hb204e8e_0` | 3.11.13 | Qt 5 `libQt5Core.so.5` | 5.15.15, `qVersion` 5.15.15 | import failed |
| `ssh debian:/home/joshua/opt/freecad` | Linux prefix, both bindings installed | 1.0.0 `py39h5f54016_4` | 3.9.23 | Qt 6 `libQt6Core.so.6` | 5.15.15 | 6.8.3 |
| `/Users/local/opt/freecad` | Mac prefix. AppRun execs `bin/python` | 1.0.0 `py39h63efebd_4` | 3.9.23 | Qt 6. Mach-O current version 6.7.3. On-disk dylib is `libQt6Core.6.8.3.dylib` | 5.15.15 | 6.8.3 |
| `/Users/local/opt/freecad-kp` | Mac prefix. AppRun execs `freecadcmd` | 1.0.0 `py39h63efebd_4` | 3.9.23 | Qt 6.7.3 | 5.15.15 | 6.7.3 |
| `/Users/local/opt/freecad-kp-qt5` | Older Qt 5-only prefix | 0.21.2 `py39hd081c59_1` | 3.9.22 | Qt 5.15.8 | 5.15.8 | import failed |
| `/Applications/FreeCAD.app` | Local Qt 6 app | 1.1.3 `he8ea13f_0` | 3.11.14 | Qt 6.8.3 | import failed | 6.8.3 |

`/Applications/FreeCAD.app/Contents/Resources/bin/python -c 'import FreeCAD'` raised `ModuleNotFoundError`. The 1.1.3 figure is the conda package version, not `FreeCAD.Version()`.

### Builder modules

`QUiLoader` and `loadUiType` are attributes on `QtUiTools` wherever that module imports. `loadUi` is absent on both bindings. In this table, QtDesigner is the Python module. The designer program is in the next table.

| Tree | QUiLoader | loadUiType | QtDesigner Python module | QtSvg / QSvgWidget | QtPdf Python | QtWebEngineWidgets |
| --- | --- | --- | --- | --- | --- | --- |
| debian `/opt/freecad` PySide2 | class imports | yes | no module | QtSvg ok. `QSvgWidget` lives on `QtSvg` in this binding family | no module | `.so` present, import fails, `libQt5WebEngineWidgets.so.5` missing |
| debian home PySide2 | yes | yes | no module | QtSvg ok, no `QtSvgWidgets` | no module | import fails, library missing |
| debian home PySide6 | yes | yes | yes, `QPyDesignerCustomWidgetCollection` present | `QSvgWidget` is on `QtSvgWidgets`, not on `QtSvg` | no module | no module |
| Mac `/Users/local/opt/freecad` PySide2 | yes, and `QUiLoader.load` built a `QPushButton` from a version 4.0 buffer | yes | no module | QtSvg ok | no module | import fails, `@rpath/libQt5WebEngineWidgets.5.dylib` missing |
| Mac `/Users/local/opt/freecad` PySide6 | yes, same buffer loaded | yes | yes | `QtSvgWidgets.QSvgWidget` | no module | no module |
| Mac `freecad-kp` | same pattern as the hybrid Mac prefix, PySide6 is 6.7.3 | yes | PySide6 only | same split as 6.8.3 | no module | PySide2 import fails on the missing dylib. PySide6 has no module |
| Mac `freecad-kp-qt5` | yes | yes | no module | QtSvg ok | no Python module. `libQt5Pdf` and `libQt5PdfWidgets` 5.15.8 are on disk | import ok |
| FreeCAD.app 1.1.3 | yes | yes | yes, collection class present | `QtSvgWidgets` | no module | no module |

`QPushButton.staticMetaObject.propertyCount()` is 74 on PySide2 5.15.15 and on PySide6 6.8.3. `text`, `enabled`, `visible`, `geometry`, and `styleSheet` are writable on both, except `modal`, which is not writable. That is one class. It is not a survey of every widget.

### Programs and extra packages

| Tree | designer program | uic / rcc | psycopg, pg8000, tree_sitter |
| --- | --- | --- | --- |
| debian `/opt/freecad` | not in `usr/bin`. `libQt5Designer.so.5.15.15` is on disk | `pyside2-rcc` only. No `uic`, no `pyside2-uic`, no `pyside6-uic` | all four imports failed (`psycopg`, `psycopg2`, `pg8000`, `tree_sitter`) |
| debian home | `bin/designer`, `bin/designer6`, `bin/pyside2-designer` | `uic`, `pyside2-uic`, `pyside6-uic`, both rcc tools | imports failed |
| Mac `/Users/local/opt/freecad` | `bin/pyside2-designer`, Qt 6 `Designer.app` under `lib/qt6/bin` | `bin/uic` is Qt 5.15.15. `lib/qt6/uic` is 6.8.3. Wrappers `pyside2-uic` and `pyside6-uic` exist | `psycopg` 3.2.13 and `psycopg_binary` directories are in site-packages. Import was not run. `pg8000` and `tree_sitter` were not in that directory listing |
| Mac `freecad-kp` | same wrapper layout as the hybrid prefix | `pyside2-uic` and `pyside6-uic` present | not in the site-packages name listing |
| Mac `freecad-kp-qt5` | `pyside2-designer` | `pyside2-uic` and `bin/uic`. No PySide6 tools | not in the site-packages name listing |
| FreeCAD.app 1.1.3 | `lib/qt6/bin/Designer.app` | `lib/qt6/uic` emits Python. `bin/pyside6-rcc` exists. No `pyside6-uic` in `bin` | `psycopg`, `psycopg2`, `pg8000`, and `tree_sitter` imports failed |

The claim that a ChoreBoy FreeCAD 1.1 image bundles psycopg, pg8000, and tree_sitter is unverified. None of those modules imported on the 1.1.3 app or on the Cloud 1.0.2 image. The current FreeCAD bundle script on `main` copies `pyside6-rcc` and depends on `noqt5` and Python 3.11. It does not list those three packages. That script is the weekly bundle line, not a file from the 1.1.0 tag.

## How a launched app reaches Qt

ChoreBoy Code Studio launches user code with `AppRun -c` and a `runpy` payload. `app/run/runtime_launch.py` builds that payload. The Qt modules the snippet can import depend on which AppRun it hits.

On the Cloud image this command printed `3.11.13 5.15.15 5.15.15` and the `QUiLoader` class:

```text
QT_QPA_PLATFORM=offscreen /opt/freecad/AppRun -c "import sys,PySide2; from PySide2.QtCore import qVersion; from PySide2.QtUiTools import QUiLoader; print(sys.version.split()[0], PySide2.__version__, qVersion(), QUiLoader)"
```

A second snippet imported `PySide` from `/opt/freecad/usr/Ext/PySide/__init__.py`, version 5.15.15. `QtWidgets.QAction` and `QtGui.QAction` were both true, because the Qt 5 shim's `QtGui.py` star-imports `QtWidgets`.

On the Mac dev launcher the same style of command used `bin/python` directly:

```text
/Users/local/opt/freecad/AppRun -c 'import sys; print(sys.version.split()[0]); import PySide2, PySide6; print(PySide2.__version__, PySide6.__version__)'
```

Output was `PY 3.9.23`, then `5.15.15` and `6.8.3`. `PySide` was not on the path. With `PYTHONPATH=/Users/local/opt/freecad/Ext`, the shim version was 6.8.3, `QtWidgets.QAction` was false, and `QtGui.QAction` was true.

`/Users/local/opt/freecad-kp/AppRun -c` and `/Users/local/opt/freecad-kp-qt5/AppRun -c` both exec `freecadcmd`. Short snippets exited 0 and printed PySide2 5.15.15 and 5.15.8. The `freecad-kp` AppRun comment says the GUI `freecad` binary segfaults after SoQt init. That longer path was not run.

## PySide2 to PySide6 deltas that matter

Official porting notes are at <https://doc.qt.io/qtforpython-6/faq/porting_from2.html>. The rows marked measured were checked on PySide2 5.15.15 and PySide6 6.8.3 in `/Users/local/opt/freecad`, and the PySide6 column was checked again on FreeCAD.app 1.1.3. PySide6 6.7.3 on `freecad-kp` matched the 6.8.3 column for the attributes that were probed there.

| Topic | PySide2 5.15.15 | PySide6 6.8.3 measured here | What the porting guide says |
| --- | --- | --- | --- |
| Import name | `PySide2` | `PySide6`. `PySide2` is absent on the 1.1.3 app | Rename the import |
| `QAction`, `QShortcut`, `QActionGroup` | on `QtWidgets` only | on `QtGui` only. `QtWidgets` does not re-export them | Moved to `QtGui` |
| `QApplication.exec_` / `QDialog.exec_` | `exec_` exists. `exec` does not | both exist | Renamed to `exec` |
| Enums | `Qt.AlignLeft` and `Qt.AlignmentFlag.AlignLeft` | both still exist | Scoped enums are the Qt 6 style. Whether unscoped names warn was not measured |
| `QRegExp` | exists, next to `QRegularExpression` | no `QRegExp` | Removed in favor of `QRegularExpression` |
| `QDesktopWidget` | on `QtWidgets` | absent | Use `QScreen` |
| High DPI attributes | `AA_EnableHighDpiScaling`, `AA_DisableHighDpiScaling`, `AA_UseHighDpiPixmaps` exist | attributes still exist. Reading and `setAttribute` of `AA_EnableHighDpiScaling` printed a `DeprecationWarning`. `setAttribute(..., True)` returned and `testAttribute` was true | Deprecated. High DPI is on and cannot be turned off |
| `QSvgWidget` | `QtSvg.QSvgWidget` | `QtSvgWidgets.QSvgWidget`. `QtSvg.QSvgWidget` is false | `QtSvgWidgets` is the Qt 6 module for the widget |
| `QtUiTools.QUiLoader` | loads a version 4.0 buffer to a `QWidget` whose button text is `Hi` | same result | Still the runtime loader |
| `loadUiType` | attribute present | attribute present. It was not called | PySide still ships it in these builds |
| `loadUi` | absent | absent | Do not plan on the PyQt helper |
| `QtDesigner` Python module | no module | imports. `QPyDesignerCustomWidgetCollection` is true | The plugin-collection API is a PySide6 module in these builds |
| `.ui` file | `uic` 5.15.15 accepts `<ui version="4.0">` | `uic` 6.8.3 accepts the same XML | The sample form is compatible. Promoted widgets, actions, and removed properties were not tried |
| `uic` Python output | star-imports `PySide2.QtCore`, `QtGui`, and `QtWidgets` | explicit `PySide6` imports. A button form did not need `QAction` | Generated Python is binding-specific even when the XML is shared |
| `QPushButton` meta-object | 74 properties | 74 properties | Enough for a property editor to start from `QMetaObject`. Other classes were not compared |
| Removed modules in the guide | `QtXmlPatterns`, `QtScript`, `QtMacExtras` are present on PySide2 | those modules are not in the PySide6 directory listing | Guide lists them as removed |

`pyside2-uic` on the Mac prefix looks up a bare `uic` on `PATH`. With the default `PATH` it raised `FileNotFoundError`. `pyside6-uic` forwarded to `lib/qt6/uic` and rejected a `/dev/fd` path. Calling `lib/qt6/uic -g python` on that same descriptor worked. The Cloud image at `ssh debian:/opt/freecad` has neither `uic` nor `pyside2-uic`. A builder that shells out to `uic` fails on that image. Production ChoreBoy was not checked for an `uic` binary.

CBCS has no `QDesktopWidget`, `QRegExp`, or high-DPI attribute uses. A code survey counted 36 `.exec_()` calls in 29 Python files, 25 of them under `app/`. Production `QAction` and `QActionGroup` imports come from `PySide2.QtWidgets`, including `app/shell/menus.py` and `app/shell/view_menu_builder.py`. `testing/main_window_test_helpers.py` copies `QActionGroup` from `QtGui` when `QtWidgets` lacks it, and the same block is copied in 10 test modules. Production menu code does not use that helper. Unscoped names such as `Qt.AlignLeft` still exist on PySide6 6.8.3, next to `Qt.AlignmentFlag.AlignLeft`, so the 387 `Qt.<Name>` uses under `app/` are not an immediate crash on that build. Whether those names warn at runtime was not measured. `globalPos()` appears at 4 call sites in 3 application files. The porting guide marks `QMouseEvent.globalPos()` deprecated. Those four calls were not executed on PySide6.

## Where ChoreBoy Code Studio stands

There is no compatibility layer. `rg -l` finds 276 Python files that mention `PySide2`. A file-by-file import census finds 212 files that actually import it, 440 import or `import_module` sites, and 131 importing files under `app/`. Zero files mention `PySide6`. Zero files mention `qtpy`. Imports are per module. `run_editor.py` and `app/shell/menus.py` each call `importlib.import_module("PySide2.QtWidgets")`. `tools/dune/file_roles.py` forbids a PySide import in `app.core`, `app.bootstrap`, `app.run`, and several other packages, with `app/project/project_tree_widget.py` as the project exception. A new adapter has to live somewhere that rule allows.

Startup treats PySide2 as mandatory. `app/bootstrap/capability_probe.py` defines `check_pyside2_availability`, which imports the module named `PySide2`. A PySide6-only runtime fails that check. `docs/PRD.md` also asks the probe to confirm `QtUiTools`. The probe function does not import `QtUiTools`.

The new-project template `templates/qt_app/main.py` and `example_projects/crud_showcase/main.py` import `PySide2.QtWidgets` and call `app.exec_()`. On the 1.1.3 app the process dies at `import PySide2`. `exec_` still exists on PySide6 6.8.3.

`docs/DISCOVERY.md` and `docs/LOCAL_DEV.md` require Python 3.9 syntax because production AppRun is Python 3.9.2. The Cloud image measured here is Python 3.11.13 and still PySide2. Mac prefixes at `/Users/local/opt/freecad` and `freecad-kp` are Python 3.9.23. `freecad-kp-qt5` is Python 3.9.22. Code that has to run on production and on Cloud stays valid on 3.9. Python 3.9 code runs on 3.11.

`scripts/setup_freecad_dev.sh` creates `~/opt/freecad` with an unpinned `conda install freecad`, then installs PySide2 because the comment says conda FreeCAD 1.0 ships PySide6. That matches the hybrid Mac prefix, where FreeCADGui links Qt 6 and PySide2 is also installed. The script's generated AppRun is supposed to exec `freecadcmd`. The AppRun on disk at `/Users/local/opt/freecad` execs `bin/python` instead. The script and the launcher have diverged.

A full CBCS migration is a wide edit plus a smaller set of real API moves. The wide part is the 131 application files that import `PySide2` by name. The moves that fail on the measured PySide6 are `QAction` and `QActionGroup` leaving `QtWidgets`. `exec_` can stay until a PySide6 build drops the alias. That port is separate from starting the builder. The current production image and the Cloud image both still provide PySide2.

## Compatibility strategies

| Approach | What happens on the Cloud image | What happens on FreeCAD.app 1.1.3 | Fit for one codebase |
| --- | --- | --- | --- |
| Keep writing `PySide2` | Works. This is CBCS today | `import PySide2` fails | One codebase does not run in both places |
| FreeCAD `PySide` shim | `AppRun -c` exposes it and binds PySide2. `QAction` is visible from `QtGui` and from `QtWidgets` | The shim files bind PySide6. `QtWidgets.QAction` is false. The Mac `bin/python` launcher does not put `Ext` on the path unless FreeCAD itself started | Depends on the launcher. Does not hide the `QAction` move |
| qtpy | Not installed on any tree that was listed | Not installed | Would need to be vendored. Machines are often offline. It does re-export `QAction` from a stable module name. That is real, and it is a dependency to freeze and debug on the appliance |
| Thin internal adapter | A module in the app tries `PySide6` and then `PySide2`, re-exports widgets, and copies `QAction`, `QShortcut`, and `QActionGroup` onto the widgets namespace when they are missing. Calls `exec` when it exists and `exec_` otherwise | Same module | One codebase. The surface to maintain is the delta table above, which was measured |

Use the thin adapter for new builder code and for code the builder emits. Leave the existing 131 importing application files on `PySide2` until a PySide6-only appliance is the one CBCS has to start on. Vendoring qtpy is the alternative if the adapter starts growing past those moved classes.

## What generated apps should store

Store a JSON document the builder owns. Generate a view from that document when the user runs the app.

A version 4.0 `.ui` document is a useful export. The same XML loaded through `QUiLoader` on PySide2 5.15.15 and on PySide6 6.8.3, and both loaders produced a button with the text `Hi`. The Cloud image can import `QUiLoader` even though it has no `uic` binary. Runtime loading does not need `uic`.

`uic -g python` is a poor source of truth. Qt 5.15.15 emits `from PySide2.QtWidgets import *`. Qt 6.8.3 emits `from PySide6.QtWidgets import ...`. Saving that text is how a project gets stuck on one binding. `loadUiType` is present on both bindings and was not called. Prefer `QUiLoader.load` for a loader you can test without a file compiler.

Hand-written Python that imports `PySide2` will not start on the 1.1.3 app. Hand-written Python that imports `PySide.QtWidgets.QAction` will not start once the shim points at PySide6. An emitted module that imports the thin adapter avoids both.

Phase 1 is layouts. The sample that was loaded is a `QWidget`, a `QVBoxLayout`, and a `QPushButton`. Actions inside `.ui` files, promoted widgets, and properties Qt 6 removed were not loaded. Treat those as open tests before promising Designer-file compatibility.

## Recommendation

Build now. The editor UI runs on PySide2, because that is what the documented production image, the Cloud image, and the current CBCS imports provide. The document model names widgets, layouts, and properties. New builder modules, and the code emitted for user apps, import Qt through the thin adapter.

The Qt 6 API is already measurable. Upstream 1.1.0 has been out since 2026-03-25, and the 1.1.3 app on this Mac already shows the binding the builder will meet. The unknown is the day production `/opt/freecad` becomes that image. On 2026-10-20 the Cloud copy at `ssh debian:/opt/freecad` is still FreeCAD 1.0.2 and PySide2, which is what `AGENTS.md` already says Cloud is. A test update dated around 2026-09-29 was not installed on this host. Its package list is unverified. Production remains the documented Python 3.9.2 and Qt 5.15.2 image until someone probes a shop machine.

Porting all of CBCS to PySide6 before any builder work is the long way around. The editor would then run only after the 131-file import edit, and it would fail to start on production and on Cloud until those images gained PySide6.

### Tradeoffs

| Choice | User on today's appliance | User after a PySide6 appliance | Maintainer |
| --- | --- | --- | --- |
| Build now, JSON model, thin adapter, editor stays on PySide2 | Can use the builder. Saved apps keep a model that can load through `QUiLoader` or the adapter | Adapter selects PySide6. CBCS itself still needs the import rename before the editor process can start on a PySide6-only machine | One new module plus a model. The rest of CBCS stays as it is until the appliance cutover |
| Wait for the 1.1 appliance, then build only against PySide6 | No builder until the image ships and CBCS starts | Simpler imports inside the builder | Calendar risk. Cloud on this host still matches the documented PySide2 image. Production was not re-probed. Upstream 1.1 has already shipped |
| Emit only `PySide2` Python or only Qt 5 `uic` output | Runs now | Fails at import | A second rewrite of every saved project |
| Adopt the FreeCAD shim as the only import | Works for `AppRun -c` on this Cloud image | `QAction` from `QtWidgets` fails. Mac `bin/python` launchers do not see the shim | Two launch paths to keep honest |

## Gotchas

The Mac prefixes that contain both Qt 5 and Qt 6 libraries are development trees. FreeCADGui there is linked to Qt 6, while PySide2 still imports. They are useful for side-by-side probes. `ssh debian:/opt/freecad` is the documented Cloud image. Production ChoreBoy, Python 3.9.2 and Qt 5.15.2 in `docs/DISCOVERY.md`, was not mounted on that host.

`docs/designer/ARCHITECTURE_PLAN.md` links the Qt 6 Designer file format and the PySide6 `QUiLoader` tutorial. The editor runtime those docs sit next to is still PySide2. `docs/DISCOVERY.md` records that `PySide2.QtUiTools.QUiLoader` loaded `myapp/ui/probe.ui` on ChoreBoy. That note is a discovery result, not a loader shipped in the editor.

`libQt5WebEngine*.so` and the matching Mac dylibs are missing from the 1.0.x trees even when `PySide2/QtWebEngineWidgets*.so` is installed. Import fails. The 0.21.2 tree is the one place WebEngine imported. The 1.1.3 app has no `QtWebEngine` Python module. A builder preview should not plan on an embedded browser.

The 0.21.2 tree has `libQt5Pdf` on disk. `import PySide2.QtPdf` failed there. No tree had a `QtPdf` Python module.

High DPI code that sets `AA_EnableHighDpiScaling` still runs on 6.8.3 and warns. Leave high DPI at the Qt 6 default.

`exec_` is safe on the PySide6 builds measured here and is the only form on PySide2. The adapter can prefer `exec` and fall back to `exec_`.

The property editor can walk `QMetaObject` on both bindings. Python attributes that were never declared as Qt properties will not show up. That limit is the same on both versions.

## Sources

- FreeCAD 1.1.0 release, 2026-03-25, Python 3.11 assets and no Qt 5 asset name: <https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.0>
- Release announcement, 2026-03-25: <https://freecad.github.io/Website/news/freecad-version-1-1-released/>
- Release notes date the release 24 March 2026: <https://wiki.freecad.org/Release_notes_1.1>
- Qt 5 support ended for the 1.1 line. Oldest supported Qt is 6.2, with 6.8 recommended. chennes, 2026-01-06: <https://devtalk.freecad.org/t/qt5-support-eol/7141>
- Handbook, main branch aimed at 1.2, minimum Python 3.11 and Qt 6.4. The same page still says primary support includes PySide2 and Qt 5.15. The release assets and the January 2026 post are the stronger evidence that official 1.1 binaries are Qt 6: <https://freecad.github.io/DevelopersHandbook/gettingstarted/dependencies.html>
- Current Linux bundle script. `noqt5`, Python 3.11, copies `pyside6-rcc`: <https://github.com/FreeCAD/FreeCAD-Bundle/blob/main/conda/linux/create_bundle.sh>
- PySide porting guide: <https://doc.qt.io/qtforpython-6/faq/porting_from2.html>
- FreeCAD's own description of the `PySide` shim: <https://wiki.freecad.org/PySide>
- `main` pixi file pins `pyside6`, `python >=3.11,<3.12`, `qt6-main >=6.8,<6.9`, and `noqt5`. That file's workspace version is `26.3.0`, so it describes development after 1.1: <https://github.com/FreeCAD/FreeCAD/blob/main/pixi.toml>

## Commands

Cloud image on `ssh debian`, package line and AppRun import:

```text
rg -n "^  freecad " /opt/freecad/packages.txt
# 60: freecad 1.0.2 py311hb204e8e_0 freecad

QT_QPA_PLATFORM=offscreen /opt/freecad/AppRun -c "import sys,PySide2; from PySide2.QtCore import qVersion; from PySide2.QtUiTools import QUiLoader; print(sys.version.split()[0], PySide2.__version__, qVersion(), QUiLoader)"
# 3.11.13 5.15.15 5.15.15 <class 'PySide2.QtUiTools.QUiLoader'>

QT_QPA_PLATFORM=offscreen /opt/freecad/AppRun -c "import PySide; from PySide import QtWidgets, QtGui; print(PySide.__file__, PySide.__version__); print(hasattr(QtWidgets,'QAction'), hasattr(QtGui,'QAction'))"
# /opt/freecad/usr/Ext/PySide/__init__.py 5.15.15
# True True
```

The PySide2 and PySide6 attribute probes used `bin/python` or `usr/bin/python` with `QT_QPA_PLATFORM=offscreen`, one binding per process. Results are the matrix above. The dual-binding process on `/Users/local/opt/freecad` exited 139.

`QUiLoader` buffer load, each binding in its own process, on `/Users/local/opt/freecad/bin/python`:

```text
PySide2 widget QWidget text Hi err
PySide6 widget QWidget text Hi err
```

`uic` compilers, same version 4.0 XML:

```text
/Users/local/opt/freecad/bin/uic -v
# uic 5.15.15
# first import line: from PySide2.QtCore import *  # type: ignore

/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic -g python <ui>
# Qt User Interface Compiler version 6.8.3
# first import line: from PySide6.QtCore import (QCoreApplication, ...
```

Linkage:

```text
otool -L /Applications/FreeCAD.app/Contents/Resources/lib/libFreeCADGui.dylib | rg Qt6Core
# libQt6Core.6.dylib current version 6.8.3

ldd /opt/freecad/usr/lib/libFreeCADGui.so | rg Qt5Core
# libQt5Core.so.5 => /opt/freecad/usr/lib/./libQt5Core.so.5
```

CBCS import counts from `/Users/local/Projects/ChoreBoyCodeStudio`:

```text
rg -l 'PySide2' -g '*.py' | wc -l          # 276
rg -l 'PySide2' -g '*.py' app | wc -l      # 135
rg -l 'PySide2' -g '*.py' tests | wc -l    # 122
rg -l 'PySide6' -g '*.py' | wc -l          # 0
rg -l 'qtpy' -g '*.py' | wc -l             # 0
```
