# How a .ui form reaches the running app

Explanation of the runtime path for ChoreBoy Code Studio forms. The `.ui` file stays the source of truth. FreeCAD 1.1 only, PySide6 6.8, Python 3.11. Research date 2026-10-20. Nothing in the ChoreBoy Code Studio repo was modified.

## Recommendation

Generate Python on every save of the `.ui` file, inside the editor process, and have the shop app import that module.

The generated module matches the shape `uic -g python` already emits. A class `Ui_<Name>` has `setupUi` and `retranslateUi`. The user owns a second file, the window class, and calls `setupUi(self)` from it. The editor rewrites only the generated file. Hand edits in that file are replaced on the next save. The header `uic` writes already says that.

`QUiLoader` is the optional preview for a stock form that has not been saved yet. Call `clearPluginPaths()` before that preview. Do not ship `QUiLoader` as the way the shop app builds its windows.

This split follows two choices.

The object the app holds is a window the user wrote, filled by `setupUi`. A loader return value cannot be that window. `QUiLoader.load` constructs the `QMainWindow` itself. `FreeCADGui.PySideUic.loadUi(path, existing)` does the same. The widget you pass is ignored, and the return value is a new parentless widget. The user's subclass never becomes the form. That is the wrong data shape for menus, toolbars, and methods that live on the window.

The person who reads the shop app is a hobbyist on a small machine, often offline. They already write layout code by hand. Four trees checked on this machine contain zero `.ui` files (`app/` in Code Studio, the template `packages/`, `FCC_QT/packages`, Apex `packages/`). A generated `self.ui.edit0` is a name Jedi can see. A name that appears only after `load()` is not.

The 2 ms gap between the loader and `setupUi` did not decide this. Both are a small slice of importing `QtWidgets`.

The operator could ship `QUiLoader` as the only runtime and skip the generator. That is less code, and the loader already builds this form. It gives up static names, real promoted classes, and `retranslateUi`. The operator could also shell out to `lib/qt6/uic` on a machine whose profile allows it. The last AppArmor probe on this product does not.

## What was measured

Host. Mac, 16 cores, 48 GB. `/Applications/FreeCAD.app` is FreeCAD 1.1.3, Python 3.11.14, PySide6 6.8.3, Qt 6.8.3. The interpreter is `/Applications/FreeCAD.app/Contents/Resources/bin/python`. `QT_QPA_PLATFORM=offscreen`.

Load during the 20-run timing was `10.48, 11.54, 18.80` at start and the same triple at the end (`os.getloadavg`). Earlier in the session the 1-minute load was above 30, so other work was on the box. The timed samples below are interleaved inside one process so they share that noise. One `setupUi` sample spiked to 7.4 ms. The medians did not.

The form is a `QMainWindow` written for this run. It has a File menu, a toolbar, a status bar, a Quit action whose `triggered` signal calls `close`, 45 label and line-edit rows with buddies and tab stops, 20 check boxes, 12 combo boxes, 10 push buttons, and a tab widget with two pages. `QUiLoader` reported 152 `QWidget` objects (`1 + len(findChildren(QWidget))`). `setupUi` on a `QMainWindow` subclass reported 154. Both showed the title `Bench`, both resolved the buddy of `label0` to `edit0`, and both closed when Quit was triggered. The two-widget difference was not explained.

`uic` was `/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic` 6.8.3, invoked as `uic -g python`. There is no `pyside6-uic` under that app's `bin`. The file `bin/pyside6-rcc` exists and does not run. Its shebang is `#!/home/runner/work/FreeCAD/FreeCAD/package/rattler-build/.pixi/envs/default/bin/python`. `lib/qt6/rcc -g python` does run, and it wrote a resource module Qt could see (`QFile.exists(":/icons/dot.png")` was true).

Linux image. `FreeCAD_1.1.0-Linux-x86_64-py311.AppImage` (820,722,168 bytes) was downloaded on `ssh debian` to `/tmp/freecad-r1`, extracted, inspected, and deleted. `packages.txt` lists `freecad 1.1.0`, `pyside6 6.8.3`, and `qt6-main 6.8.3`. `usr/lib/qt6/uic -v` printed `uic 6.8.3`. `usr/bin` contains `pyside6-rcc` and does not contain `uic` or `pyside6-uic`. The only `uic` in the image is `usr/lib/qt6/uic`. `AppRun python` imported `PySide6.QtUiTools.QUiLoader`, `loadUiType`, and `PySide6.QtDesigner.QFormBuilder`. `importlib.util.find_spec("pyside2uic")` was `None`. `import FreeCADGui` from that same `AppRun python` raised `ModuleNotFoundError`. The GUI binary was not started. `strings` on the Mac `libFreeCADGui.dylib` and on the image `libFreeCADGui.so` both contain `import pyside2uic` and `pyside2uic.compileUi`.

The bundle script that matches this `usr/bin` whitelist is [conda/linux/create_bundle.sh](https://github.com/FreeCAD/FreeCAD-Bundle/blob/main/conda/linux/create_bundle.sh) on `main`. It copies `pyside6-rcc` and does not copy `uic` or `pyside6-uic`, then deletes the rest of `bin`. It does not delete `lib/qt6`. That is why the image still has `usr/lib/qt6/uic`. The script on `main` was read as the current whitelist. The image is the 1.1.0 ground truth. They agree on `usr/bin`.

## Timings

All form timings are after `QApplication` exists, inside one process, with 3 untimed warmups and then 20 interleaved runs. The timer wraps only the named call. Widget count, window title, and the Quit action were checked on every `QUiLoader` and `setupUi` sample. Error count was 0.

| Call | n | Median | Min | Max |
| --- | ---: | ---: | ---: | ---: |
| `QUiLoader.load` of the 152-widget form | 20 | 2.329 ms | 2.087 | 2.895 |
| import of the generated module, after removing it from `sys.modules` | 20 | 2.968 ms | 2.613 | 3.978 |
| `setupUi` on a new `QMainWindow` | 20 | 2.524 ms | 2.155 | 7.363 |
| `QFormBuilder.load` of the same file | 20 | 1.393 ms | 1.113 | 1.635 |

`QUiLoader.load` and `setupUi` overlap. The median gap is 0.2 ms, and one `setupUi` sample reached 7.4 ms. That is no measurable difference on this box.

`QFormBuilder.load` does not overlap `QUiLoader.load` in that run. It is faster. A follow-up at load `13.81, 12.37, 18.38` cleared plugin paths and did not remove the gap. Default loader median 2.642 ms (2.018 to 4.393). Cleared loader median 2.480 ms (2.129 to 4.023). The plugin path list is not the limiter.

A 2-widget form (`QWidget` plus one button) loaded in 0.114 ms median (0.089 to 0.338, n=20), against 2.642 ms for the 152-widget form in the same follow-up. A separate `cProfile` of one `QUiLoader.load` spent the time inside the C++ `load` method (0.002 s of 0.002 s). That profile is outside the 20-run medians. `setupUi` was 553 Python calls and 0.003 s, almost all inside `setupUi` itself. The form step is widget construction in C++, reached either by the loader or by the generated calls. A profile of the C++ frames inside `QUiLoader.load` was not taken, so the extra millisecond versus `QFormBuilder` stays inside that C++ call and is otherwise unidentified.

Importing `QtWidgets` in a fresh process is the startup cost that dwarfs the form. Ten processes, alternating with a `QtDesigner` import, printed these `QtWidgets` times on the `QtUiTools` side, in ms: 107.15, 75.56, 75.97, 78.27, 88.65, 141.95, 82.56, 166.00, 75.57, 76.48. Median 80.4 ms, range 75.6 to 166.0, load about 15. The following `QtUiTools` import in those same processes, in ms: 4.23, 2.37, 2.68, 2.31, 2.71, 5.09, 2.39, 3.26, 2.44, 2.42. Median 2.56 ms. The `QtDesigner` import, in ms: 20.79, 4.71, 4.49, 4.52, 4.76, 4.60, 5.07, 4.24, 4.48, 4.71. Median 4.66 ms. The first sample is an outlier.

A 2.3 ms form build is about 3 percent of an 80 ms `QtWidgets` import, on a noisy baseline. It is not the thing the user waits on. AppRun startup was not re-timed in this session. Earlier notes in `docs/form_builder/research/D_first_principles_architecture.md` say AppRun plus the offscreen plugin dominate test time. That claim was not re-measured here.

`loadUiType` is a different order of cost, and only when a `pyside6-uic` happens to be on `PATH`. With this machine's `PATH`, five calls had median 218 ms (196 to 289). `shutil.which("pyside6-uic")` was `/Users/local/.pyenv/shims/pyside6-uic`, a Python 3.14 shim. FreeCAD's `lib/qt6/uic` was a different file and was not the one `loadUiType` executed. With `PATH` set to `/usr/bin:/bin`, `loadUiType` returned `None` and Qt printed `Cannot run ' pyside6-uic ': Child process set up failed: execve: No such file or directory`. On the Linux image, `which uic` inside `AppRun python` was the host `/usr/bin/uic`, and that binary is uic 5.15.8. `which pyside6-uic` was `None`.

A one-time font warning, `Populating font family aliases took 49 ms`, was printed before the timed loop. It is not inside the medians.

## Comparison

| Path | On the 1.1.0 image | What the app runs | Static widget names | Promoted Python class | `retranslateUi` | Needs an executable |
| --- | --- | --- | --- | --- | --- | --- |
| `QUiLoader` | `QtUiTools` imports | `loader.load(path)` | No. Attributes appear at runtime. `hasattr(window, "edit0")` was true on this build | No. `PromoEdit` became a `QLineEdit`. `errorString()` was empty | No. `hasattr` was false | No |
| `pyside6-uic` or `uic -g python` at save | `lib/qt6/uic` is on disk. `pyside6-uic` is not in `usr/bin`. Last AppArmor probe blocks exec | `setupUi(self)` | Yes | Yes. Generated `from promo_edit import PromoEdit`. Instance type was `PromoEdit` | Yes | Yes. Blocked on the appliance if the 2026-03-06 profile still holds |
| `loadUiType` | Function exists. It execs `pyside6-uic` | Same `setupUi`, class built in memory | No. The class does not exist until the call | Same as `uic`, if the exec works | Yes, if codegen runs | Yes. Failed closed when `PATH` had no `pyside6-uic` |
| `FreeCADGui.PySideUic.loadUi` | Present only after the GUI starts. `freecadcmd` before `showMainWindow()` has no `PySideUic`. The 1.1 image's `AppRun python` cannot import `FreeCADGui` | `UiLoader.load`. A second argument is ignored. The returned widget is new and parentless | Runtime names on the wrapper | `Gui::InputField` kept its Qt class and `unit` of `mm` on `InvoluteGearFeature.ui`. Plain `QUiLoader` substituted `QLineEdit` | No. [Issue 8274](https://github.com/FreeCAD/FreeCAD/issues/8274) | No for `loadUi`. `loadUiType` raised `ModuleNotFoundError: No module named 'pyside2uic'` |
| In-process generator | No extra binary | `setupUi(self)` | Yes, if the emitter matches `uic` | Yes, if it emits the import | Yes, if it emits the method | No |
| `QFormBuilder` | `QtDesigner` imports. `libQt6Designer.so.6` is in the image | `builder.load(device)` | Same runtime attributes as the loader | Same fallback warning, because `QUiLoader` is built on it | No | No |

## How each path behaves

### QUiLoader

`PySide6.QtUiTools` on this build exposes `QUiLoader` and `loadUiType` only. There is no `loadUi`. The tutorial calls codegen option A, the standard way, and the loader option B. [Using .ui files](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html). The same split is in the Designer manual for Python. [Using a .ui file](https://doc.qt.io/qt-6/designer-using-a-ui-file-python.html).

Measured on the bench form. The loader returned a `QMainWindow`. Menu, toolbar, buddy, and the Quit connection worked. Triggering the action closed the window. `edit0` and `actionQuit` were attributes after load. Jedi still cannot see them, because the source type is `QMainWindow` and the names are created when the file loads. Code Studio's completion index is for Python source.

`connectSlotsByName` is the wrong tool on a loader window. The loader builds the instance. A method defined on the user's subclass is not on that instance. An explicit connection stored in the `.ui` file does run. Quit called `close`.

Promoted widgets are a silent downgrade. stderr said `QFormBuilder was unable to create a custom widget of the class 'PromoEdit'; defaulting to base class 'QLineEdit'.` The child type was `QLineEdit`. `errorString()` was empty.

Unknown class `NotAWidget` raised `RuntimeError: Unable to open/read ui device` and `errorString()` was `Invalid UI file`. A missing file raised `RuntimeError` as well. `errorString()` reported a premature end of document. This binding does not follow the older pattern of returning `None` for every failure. Callers have to catch `RuntimeError`.

Plugin paths on this app were the Designer plugin directory and `bin/designer`. The [QUiLoader page](https://doc.qt.io/qtforpython-6/PySide6/QtUiTools/QUiLoader.html) says to load forms only from trusted sources. The risks it names are denial of service, a misleading UI, and unexpected plugins. Clearing the paths is one line and did not change the load time enough to measure.

A label that has both a pixmap and a text property kept its pixmap under the loader. The `uic` output set the pixmap and then `retranslateUi` called `setText`. After `setupUi` the pixmap was null, while `QFile.exists(":/icons/dot.png")` was true. The inference is that `setText` cleared the pixmap. That order was read from `ui_resource.py`. A probe that sampled the pixmap between the two calls was not run.

### pyside6-uic and uic -g python

`PySide6.scripts.pyside_tool.uic` prepends `-g python` and runs `lib/qt6/<uic>`. The tool page says the wrapper exists so the `uic` version matches PySide, and it says not to edit the generated file. [pyside6-uic](https://doc.qt.io/qtforpython-6/tools/pyside-uic.html).

The generated bench module is 917 lines and 34,212 bytes, from a `.ui` file of 28,613 bytes. It contains `connectSlotsByName`, `retranslateUi`, `setBuddy`, `setTabOrder`, `actionQuit.triggered.connect(MainWindow.close)`, `QMenuBar`, and `QToolBar`. Imports name the `PySide6` classes they use.

`connectSlotsByName` saw a method decorated with `@Slot(str)` and did not see a plain method. `on_edit0_textChanged` without the decorator got 0 hits after `setText`. The decorated method got 1 hit. The generated call is real. The slot still has to be a Qt slot on the object passed to `setupUi`.

The focus chain walked from `edit0` was `edit0`, `label1`, `edit1`, `label2`. The generated file does call `setTabOrder` from `edit0` through `edit44`. The chain walk is not a clean reading of tab order, because buddy labels sit in the focus chain. Tab order was not scored beyond the presence of those calls.

This path is the right app contract and the wrong emitter on the appliance. `docs/DISCOVERY.md` section 4G, probed 2026-03-06, says `/bin/sh` is the only binary a confined FreeCAD process may exec, and that `/bin/sh -c` of another binary still gets `EACCES`. That probe was not repeated on the 1.1 image in this session. If a 1.1 profile still says that, the editor cannot run `lib/qt6/uic` even though the file is in the image.

Stale output is an editor bug if save always regenerates the module in the same write as the `.ui` file. It is a user-visible bug if someone edits the `.ui` file outside the editor, or if the generated file is hand-edited. The second file, the window class, is never rewritten. Qt's own warning is the comment to keep at the top.

### loadUiType

The Qt for Python page says not to use it. The implementation runs `pyside6-uic` and then execs the generated Python. [loadUiType](https://doc.qt.io/qtforpython-6/PySide6/QtUiTools/QtUiTools_globals.html). On a full `PATH` it returned `(Ui_MainWindow, QMainWindow)` and cost about 218 ms. On a stripped `PATH` it returned `None`. On the Linux image the `uic` it would find first, if `path_search` were turned on, is the host Qt 5.15.8 `uic`. The docs say to leave `path_search` false. Either setting is a bad fit for an offline appliance.

### FreeCADGui.PySideUic

Workbenches call `FreeCADGui.PySideUic.loadUi` after the GUI is up. On the Mac 1.1.3 app, `freecadcmd` in console mode has `FreeCAD.GuiUp == 0` and no `PySideUic`. `showMainWindow()` under `QT_QPA_PLATFORM=offscreen` is what attached `PySideUic`. A shop app launched as plain Python does not get that module.

The calls in the installed workbenches are runtime loads. Assembly does `Gui.PySideUic.loadUi(":/panels/TaskAssemblyInsertLink.ui")` after `import Assembly_rc`. That resource module was generated by rcc 6.8.3 and registers the form bytes. Draft loads `:/ui/TaskShapeString.ui` the same way. PartDesign's gear panel loads a real file beside the Python with `Path(__file__).with_suffix(".ui")`. The panels that were read connect signals in Python after the load. Whether `<connections>` inside those files are applied was not tried. The FEM source on GitHub does the same `loadUi` for `ElementGeometry1D.ui`. [task_element_geometry1D.py](https://github.com/FreeCAD/FreeCAD/blob/master/src/Mod/Fem/femtaskpanels/task_element_geometry1D.py).

`loadUi` builds `FreeCADGui.UiLoader` and calls `load`. In the 1.1 source, `UiLoader::newInstance` clears Qt library paths so plugins stay out, and `createWidget` falls through to FreeCAD's widget factory. [UiLoader.cpp](https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/UiLoader.cpp). On `InvoluteGearFeature.ui`, `PySideUic.loadUi` returned a form whose `Quantity_Modules` Qt class was `Gui::InputField` and whose `unit` was `mm`. The same file through `PySide6.QtUiTools.QUiLoader` printed the fallback warning and substituted `QLineEdit`. `createCustomWidget("Gui::InputField")` returned an object whose Python type is `QLineEdit` and whose Qt class name stays `Gui::InputField`.

`loadUi(path, some_widget)` does not fill `some_widget`. The return value was a new widget, `parent()` was `None`, and the passed widget had no children. `loadUi(path, 1)` also returned a widget. `UiLoader().load(path, base)` does parent the form. Workbench code that looks like PyQt's `loadUi(path, self)` is not doing that. `JointObject.py` passes a widget in and then parents for real with `layout.addWidget`.

`loadUiType` on this app raised `ModuleNotFoundError: No module named 'pyside2uic'`. The 1.1 source still runs `import pyside2uic` and `pyside2uic.compileUi`. Both FreeCADGui binaries contain those strings. `pyside2uic` is absent from the Mac app and from the 1.1.0 image.

`freecad/UiTools.py` subclasses `QUiLoader` and asks `Gui.PySideUic.createCustomWidget` first. Addon Manager binds `PySideUic.loadUi` when the GUI is up, and otherwise uses `QUiLoader`. A shop app that imported either hook would import FreeCAD's GUI. Code Studio launches user code with AppRun and `runpy`. That process is a plain Python program. The FreeCAD GUI dependency does not belong in it. On `/Users/local/opt/freecad`, `AppRun -c` is `bin/python` and `FreeCADGui` is not on `sys.path`. ChoreBoy's `/opt/freecad/AppRun -c` is a different launcher. It was not the one used for this GUI start.

### In-process generator

This is the default. No pure-Python Qt 6 compiler is in the FreeCAD 1.1.3 `PySide6` tree. `site-packages/PySide6/scripts/pyside_tool.py` only wraps the binary. A web search for an in-process Qt 6 compiler returned the official `uic` and `QUiLoader` pages. PyPI was not surveyed.

The generator's spec is the Python that `lib/qt6/uic -g python` writes on this Mac. Tests on a developer machine can diff against that oracle. The appliance never runs the oracle. The same save step should emit a resource module when the form includes a `.qrc`. The oracle for that file is `lib/qt6/rcc -g python`, which worked here. The installed `pyside6-rcc` script did not.

The generator's own runtime was not timed. It runs when the editor saves. A slow generator shows up as save latency. The 2 ms figure above is the later `setupUi` call.

### QFormBuilder

`QFormBuilder` lives on `PySide6.QtDesigner`, next to the designer plugin interfaces. It loaded the bench form in 1.393 ms median and returned a `QMainWindow` with the same 152-widget count and no `retranslateUi`. Importing `QtDesigner` cost about 4.7 ms median in a fresh process, against about 2.6 ms for `QtUiTools`. The faster load does not pay for pulling the Designer library into every shop app, and it does not give static names or real promoted classes.

Use `QFormBuilder` or the designer interfaces inside the editor if the canvas needs them. The running app does not.

## Where the pieces live

| Piece | Path on FreeCAD 1.1.3 Mac | On the 1.1.0 Linux image |
| --- | --- | --- |
| Python | `Contents/Resources/bin/python` | `usr/bin/python` |
| `uic` 6.8.3 | `Contents/Resources/lib/qt6/uic` | `usr/lib/qt6/uic` |
| `pyside6-uic` | Absent from `bin` | Absent from `usr/bin` |
| `rcc` | `lib/qt6/rcc` works. `bin/pyside6-rcc` shebang is a CI path | `usr/lib/qt6` was not executed. `usr/bin/pyside6-rcc` has the same CI shebang |
| `QtUiTools` | imports | imports, and `libQt6UiTools.so.6.8.3` is present |
| `QtDesigner` | imports, including `QFormBuilder` | imports, and `libQt6Designer.so.6` is present |
| `pyside2uic` | absent | `find_spec` is `None` |

Code Studio today opens a `.ui` file as XML text. The current tree has no `app/designer/` package, and no Python under `app/` calls `QUiLoader`, `loadUiType`, `uic`, or `QFormBuilder`. The prior designer branch previewed with `QUiLoader`. Launch is two `runpy` hops. `AppRun -c` starts `run_runner.py`, and that process `runpy.run_path`s the user's entry. F5 refuses a tab whose suffix is not `.py`, so the generated module is the file that runs. A `.ui` file rides along in a packaged payload only as a copied data file.

## Gotchas

AppArmor on a 1.1 shop image was not re-probed. The recommendation assumes the 2026-03-06 whitelist still applies. If a newer profile allows `lib/qt6/uic`, the emitter can become that binary and the app contract stays `setupUi`. Confirm the profile before writing a shell-out.

`loadUiType` will silently use whatever `pyside6-uic` is on `PATH`. On a developer Mac that was Python 3.14. On the debian host the visible `uic` was Qt 5.15.8.

`QUiLoader` plugin paths point at Designer plugins. A preview of an untrusted `.ui` file should clear them. Promoted widgets in a preview still need a `createWidget` override, or they become the base class with no error string.

`connectSlotsByName` ignores an undecorated Python method. The generator, or the window template, has to show `@Slot`.

A label with both text and a pixmap lost the pixmap in `uic` output because `retranslateUi` sets the text afterward. The loader kept the pixmap. A generator that copies `uic` line for line will copy this. Worth a test if the builder supports icons on labels.

The 152 versus 154 widget count is unexplained. Behavior that was checked matched. A later test should name the two extra objects.

`FreeCADGui.PySideUic.loadUiType` on the Mac 1.1.3 app raised `ModuleNotFoundError: No module named 'pyside2uic'`. `PySideUic.loadUi` ignores its second argument, so it cannot fill the user's window the way `setupUi(self)` can.

## Sources

Measured in this session, as cited above.

- Qt for Python, [Using .ui files](https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html). Codegen is the standard way. The loader cannot connect Python types such as `str` or `list` on custom widgets.
- Qt for Python, [pyside6-uic](https://doc.qt.io/qtforpython-6/tools/pyside-uic.html). Do not edit the generated file.
- Qt for Python, [loadUiType](https://doc.qt.io/qtforpython-6/PySide6/QtUiTools/QtUiTools_globals.html). Do not use it. It execs `pyside6-uic`.
- Qt for Python, [QUiLoader](https://doc.qt.io/qtforpython-6/PySide6/QtUiTools/QUiLoader.html). Trusted sources only.
- Qt, [Using a .ui file in Python](https://doc.qt.io/qt-6/designer-using-a-ui-file-python.html). `retranslateUi` on `LanguageChange`, and `rcc -g python` for `import *_rc`.
- [FreeCAD-Bundle create_bundle.sh](https://github.com/FreeCAD/FreeCAD-Bundle/blob/main/conda/linux/create_bundle.sh). `bin` whitelist.
- [FreeCAD UiLoader.cpp at the 1.1 release branch](https://github.com/FreeCAD/FreeCAD/blob/releases/FreeCAD-1-1/src/Gui/UiLoader.cpp).
- [FreeCAD issue 8274](https://github.com/FreeCAD/FreeCAD/issues/8274). `loadUi` widgets have no `retranslateUi`.
- Stack Overflow, [converting a ui file versus loading it](https://stackoverflow.com/questions/70065307/what-is-the-advantage-of-converting-a-ui-file-to-python-code-vs-loading-it-direc). Subclassing and completion are the reasons people give. The loading-time difference is described as theoretical on that page. The numbers in this report are the measured ones.
- Qt Forum, [generating a Python class versus loading the file](https://forum.qt.io/topic/125982/using-ui-files-switching-from-generating-python-class-to-loading-ui-directly), and [QUiLoader before QApplication](https://forum.qt.io/topic/155667/create-quiloader-before-quiapplication). The replies prefer generated classes so the editor can see the widgets.
- A search that included `reddit.com/r/QtFramework` returned those Forum and Stack Overflow threads. No Reddit thread was in the result set that was read.
- `docs/DISCOVERY.md` section 4G for the AppArmor whitelist. Not re-run here.
- `docs/form_builder/research/D_first_principles_architecture.md` for the earlier recommendation to keep `QtUiTools` out of the shipped app. That paper assumed a PySide2 appliance and a JSON document. The decision since then is PySide6 only and a `.ui` source file. The part that still holds is the app contract. The running process imports Python and calls `setupUi`. It does not parse the document.
