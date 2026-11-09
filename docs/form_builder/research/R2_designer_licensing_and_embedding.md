# How to reach Qt Designer parity inside Code Studio

Throughput checkpoint: n/a, read-only investigation.

This is not legal advice. It is a reading of Qt 6.8.3 source headers, Qt's own license maps, and runtime checks on FreeCAD 1.1.3. A lawyer has to answer the questions in "Where a lawyer is needed" before anyone ships an embed or a close port.

## Overview

Build the form builder in Python. Save standard `.ui` XML. Use `PySide6.QtUiTools.QUiLoader` as the load oracle. Study Designer for behavior, and do not copy its source.

Do not embed `libQt6DesignerComponents` in the MIT app. The factory that creates the real form window, widget box, property editor, object inspector, action editor, signal slot editor, and resource editor is GPL-headed, and PySide does not wrap it. A ctypes call can construct the side panels. Creating the form window crashed. Even a finished embed would ship Designer's interface, which misses the UX this feature is supposed to have.

The prior architecture note in `docs/form_builder/research/D_first_principles_architecture.md` argued against Designer parity as the product. This brief fixes parity as the goal and fixes the file format as `.ui`. The recommendation keeps both, and refuses the shortcut that links the GPL editor in.

## Key concepts

Three different Qt pieces get called "Designer". They are not one license and not one library.

The application is `qttools/src/designer/src/designer`, plus the component widgets under `src/designer/src/components`. On disk that is the `designer` executable and `libQt6DesignerComponents`.

The Designer module is `libQt6Designer`. PySide exposes it as `PySide6.QtDesigner`. It contains the abstract plugin interfaces, and it also compiles in the shared editor implementation under `src/designer/src/lib/shared`.

The loader is `libQt6UiTools`. PySide exposes it as `PySide6.QtUiTools.QUiLoader`. Its CMake target compiles the uilib sources and `quiloader.cpp` only. It does not link `libQt6Designer`.

`QFormBuilder` is declared in uilib and is compiled into both libraries. Calling it from `PySide6.QtDesigner` loads `libQt6Designer`. Calling `QUiLoader` loads `libQt6UiTools`.

The `.ui` document is an XML format. Writing a file in that format is not the same act as copying `ui4.cpp`.

## Licensing

Citations below are the Qt 6.8.3 tag `v6.8.3`, commit `2649ea1aa5cc1c23bd920ae94dd50071315ea30f`, unless a URL says otherwise. `git describe --exact-match` printed `v6.8.3`. The tag is annotated. `git rev-parse v6.8.3^{}` printed that commit.

### What each piece says in tree

`qttools/licenseRule.json` at that commit is the module map.

`src/designer/` is file type "tools", SPDX `LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0`, except two carve-outs. `src/designer/src/lib/uilib` is "code used in src/uitools" and is `LicenseRef-Qt-Commercial OR LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`. `src/designer/src/plugins/` is the same LGPL set. `src/uitools/` is "code for the Qt Ui Tools library" and is the same LGPL set.

`qttools/REUSE.toml` at that commit disagrees with the file headers for part of the Designer module. It marks `src/designer/src/designer/**`, `src/designer/src/components/**`, and `src/designer/data/**` as GPL-3.0-only with the Qt GPL exception. It marks `src/designer/src/lib/**` and `src/designer/src/plugins/**` as the LGPL set, with the comment "module and plugin".

In-file SPDX is closer than that directory annotation. Counted by reading the first 1800 bytes of each `.h`, `.cpp`, `.c`, `.ui`, and `.py` file.

| Tree | In-file SPDX |
| --- | --- |
| `designer/src/components` | 178 files GPL-3.0-only with the Qt GPL exception. 4 files had no SPDX in the first 1800 bytes. |
| `designer/src/lib/shared` | 158 GPL-3.0-only with the exception. 20 with no SPDX in that window. |
| `designer/src/lib/sdk` | 52 GPL-3.0-only with the exception. |
| `designer/src/lib/extension` | 7 GPL-3.0-only with the exception. |
| `designer/src/lib/components` | 2 GPL-3.0-only with the exception. This is the factory header. |
| `designer/src/lib/uilib` | 15 files, all `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only` plus commercial. |
| `designer/src/plugins` | 21 files, same LGPL set. |
| `designer/src/designer` | 34 GPL-3.0-only with the exception. 26 BSD-3-Clause. 8 with no SPDX in that window. The BSD hits are doc snippets. |
| `uitools` | 4 LGPL-set sources, 3 BSD snippets, 1 file with no SPDX in that window. |

Quoted headers from that tree.

`src/designer/src/lib/components/qdesigner_components.h` begins `LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0`. The class comment says the factory is for a standalone form editing environment or for integrating the components into an IDE. `\internal` is on the class.

`src/designer/src/lib/shared/layout.cpp` has the same GPL header. `src/designer/src/lib/CMakeLists.txt` lists `shared/layout.cpp` in the `Designer` module sources. Those GPL-headed shared files are compiled into `libQt6Designer`.

`src/designer/src/lib/uilib/abstractformbuilder.h` and `src/uitools/quiloader.h` use the LGPL set. `src/designer/src/lib/uilib/ui4.cpp` uses the LGPL set and its fourth line is `THIS FILE IS AUTOMATICALLY GENERATED. DO NOT EDIT!`

`src/designer/src/components/lib/CMakeLists.txt` builds `DesignerComponentsPrivate` as `INTERNAL_MODULE`. Its public link line is `Qt::DesignerPrivate`, `Qt::GuiPrivate`, `Qt::WidgetsPrivate`, and `Qt::Xml`.

### uic and the exception

`uic` is not in qttools. At `qtbase` tag `v6.8.3`, `src/tools/uic/main.cpp` begins `LicenseRef-Qt-Commercial OR GPL-3.0-only WITH Qt-GPL-exception-1.0`.

https://github.com/qt/qtbase/blob/v6.8.3/src/tools/uic/main.cpp

The exception text at that tag is `LICENSES/Qt-GPL-exception-1.0.txt`.

https://github.com/qt/qtbase/blob/v6.8.3/LICENSES/Qt-GPL-exception-1.0.txt

Exception 1. You may create a larger work which contains the output of this application and distribute that work under terms of your choice, so long as the work is not otherwise derived from or based on this application and so long as the work does not in itself generate output that contains the output from this application in its original or modified form.

Exception 2. You may combine this application with plugins under terms you choose, if the executable offers users the source of this application, excluding independent modules, and including your changes to this application.

https://doc.qt.io/qt-6.8/qt-gpl-exception-1-0.html returned HTTP 404 on 2026-10-20. The Qt 6.12 page has the same two paragraphs.

https://doc.qt.io/qt-6/qt-gpl-exception-1-0.html

The Qt 6.8 licensing page lists modules that ship as GPL only. Qt Designer is absent from that list. The page fetched here also does not contain the later "tools are GPL" sentence that the Qt 6.12 licensing page has. The 6.8.3 source map above is the evidence for the tools.

https://doc.qt.io/qt-6.8/licensing.html

https://doc.qt.io/qt-6/licensing.html

The public class list for the Designer module does not include `QDesignerComponents`.

https://doc.qt.io/qt-6.8/qtdesigner-module.html

### The `.ui` format

Qt documents the XML schema as "Qt Widgets Designer's UI File Format" and says the format may change. The top-level `ui` element carries `class`, `widget`, optional `layoutdefault`, `customwidgets`, `tabstops`, `resources`, `connections`, `slots`, and `buttongroups`.

https://doc.qt.io/qt-6.8/designer-ui-file-format.html

That page is documentation. The parser implementation in `ui4.cpp` is LGPL-set source inside uilib. The format is the contract. The generator source is not something to paste into an MIT file.

### What an MIT project can do

(a) Read the source to learn behavior and reimplement in Python.

Copyright covers expression. The behavior of a layout editor, and the XML format, sit outside that. A clean room is a way to lower the risk of copying expression. One group writes a behavior spec. Another group implements the spec without the GPL sources open. The same author reading `formwindow.cpp` and typing the Python is not that split. It can still be lawful if the new code does not copy expression, and the risk of copying structure is higher. Do not translate line by line. Do not keep Designer's class breakdown, comments, or control flow as the Python shape.

(b) Link or load the libraries that ship inside FreeCAD.

`libQt6UiTools` is the LGPL loader. Dynamic linking from an MIT app is the ordinary LGPL case. Ship the LGPL notice, and do not static-link it in a way that blocks relinking. Code Studio already depends on PySide6, which is the same kind of LGPL dependency. `QUiLoader` does not add a GPL dependency. Measured with `otool -L` on the Mac module. It links `libQt6UiTools.6.dylib` and does not link `libQt6Designer`.

`libQt6Designer` is the conflict. `licenseRule.json` calls most of `src/designer` a GPL tool. `REUSE.toml` calls `src/designer/src/lib/**` an LGPL module. The shared and sdk files that the Designer module compiles carry GPL headers. The Qt 6.8 module list does not name Designer as GPL-only. Those three facts cannot all be the shipping license. Until a lawyer picks one, do not treat `import PySide6.QtDesigner` as a clean LGPL use. `QFormBuilder` from that module worked in the probe, and it loads the disputed library.

`libQt6DesignerComponents` is the consistent GPL case. The factory header, the component sources, `licenseRule.json`, and `REUSE.toml` agree. Loading it with ctypes, a shim, or the linker pulls GPL code into the process. Exception 2 lets Designer load plugins. It does not let an MIT app absorb Designer.

(c) Copy code.

Copying GPL or LGPL source into an MIT file is not allowed by either license. The GPL would require the copy to stay under GPL. Dropping it into an MIT tree drops the license terms. Do not do it.

The GPL exception does not relicense Designer. It covers output of the GPL application. If Code Studio embeds Designer and Designer's save writes the `.ui`, that file is Designer's output. An app that then generates more output containing that `.ui` or `uic` output hits the second half of exception 1. Research note A already flagged this sentence. A lawyer should read it against the generator you actually ship. A Python editor that writes `.ui` itself is not "this application", so the exception is the wrong tool for that path. The `.ui` is your output.

A commercial Qt contract is a different grant. The 6.8 licensing page says commercial licensees get the modules under the commercial license, and that tools are available under commercial licenses. This report did not read a commercial contract. Treat that route as unverified until counsel and Qt's license text say the embed is covered. It also fights an MIT project, because the commercial grant is usually not a right you can pass to downstream MIT users.

### Where a lawyer is needed

Is `libQt6Designer` LGPL, because of `REUSE.toml` and the public module list, or GPL, because of the file headers and `licenseRule.json`?

Does `dlopen` of `libQt6DesignerComponents` plus `shiboken6.wrapInstance` make the MIT process a combined GPL work when you distribute Code Studio to run inside FreeCAD?

If the people who read the GPL sources are the people who write the Python, is that an acceptable clean-room record, or do you want a written spec and a second implementer?

If an embed ships, does exception 1 let user apps keep their own license when Code Studio emits code from Designer's `.ui`?

What LGPL notices and relink offers does Code Studio already owe for PySide6, and what does adding `QtUiTools` add?

## How the editor is built

Tag `v6.8.3`. Sparse clone of `src/designer` and `src/uitools` was 13 MB. Counts are physical lines in `.h`, `.cpp`, `.c`, and `.ui` files, and the same files with blank lines removed. This measures source size. It does not measure how long a port takes. `ui4.cpp` is generated and inflates uilib.

| Tree | Files | Physical lines | Nonblank lines |
| --- | --- | --- | --- |
| `src/designer` | 526 | 122870 | 102597 |
| `src/designer/src/components` | 182 | 36355 | 30421 |
| `src/designer/src/lib` | 255 | 74505 | 61910 |
| `src/designer/src/lib/shared` | 178 | 52095 | 43835 |
| `src/designer/src/lib/uilib` | 15 | 14761 | 12423 |
| `src/designer/src/lib/sdk` | 52 | 6982 | 5145 |
| `src/designer/src/designer` | 68 | 9950 | 8609 |
| `src/designer/src/plugins` | 21 | 2060 | 1657 |
| `src/uitools` | 8 | 1295 | 1088 |

`QDesignerComponents::createFormEditor` constructs `qdesigner_internal::FormEditor`. The constructor installs introspection, a plugin manager, `WidgetDataBase`, `MetaDataBase`, `WidgetFactory`, `FormWindowManager`, and a `QExtensionManager`. The extension manager registers container factories for stacked widgets, tab widgets, toolbox, dock widgets, MDI, wizard, and main window. That is `formeditor.cpp`.

`createWidgetBox`, `createPropertyEditor`, `createObjectInspector`, `createActionEditor`, `createResourceEditor`, and `createSignalSlotEditor` return the component widgets. `createWidgetBox` does not register itself. The workbench does that with `core->setWidgetBox`. See `qdesigner_toolwindow.cpp` and `QDesignerWorkbench` in `qdesigner_workbench.cpp`. The workbench calls `initializePlugins`, builds the tool windows, then creates `QDesignerIntegration`.

The form surface is `qdesigner_internal::FormWindow` in `formwindow.cpp`, 2943 physical lines. It owns selection, a tool stack, drag and drop, and an undo stack. `FormWindowManager::createFormWindow` allocates that class.

Layout behavior is not in the form window file alone. `lib/shared/layout.cpp` is 1219 lines. `qlayout_widget.cpp` is 2048. `formlayoutmenu.cpp` is 491. Invisible layout widgets, grid span, break layout, and morph layout live there. The undo record is a command hierarchy. A search for `class` declarations whose names contain `Command` hit 52 lines in `qdesigner_command_p.h` and 4 in `qdesigner_command2_p.h`. `qdesigner_command.cpp` is 2872 lines. Commands cover insert, delete, reparent, z-order, layout, break layout, tab order, promotion, toolbox pages, tab pages, stacked pages, menus, toolbars, docks, actions, and table, tree, and list contents. Property changes are a further file, `qdesigner_propertycommand`.

The widget box XML is a resource, `widgetbox/widgetbox.xml`, loaded by `createWidgetBox`. Custom widgets enter through designer plugins and the widget database, `widgetdatabase.cpp`, 848 lines.

Property editing is `propertyeditor.cpp`, 1254 lines, plus property sheets in the shared library and per-widget sheets in the form editor. Dynamic properties, palettes, brushes, and icons are their own editors.

Signal and slot editing is `connectionedit.cpp`, 1572 lines, plus the signal slot editor component. Buddy mode and tab order are separate tools under `components/buddyeditor` and `components/tabordereditor`.

Actions, menus, and toolbars are `actioneditor.cpp`, 895 lines, plus `qdesigner_menu` and `qdesigner_toolbar` in shared. Promotion is `qdesigner_promotion.cpp`. The resource browser dialog is `qtresourceeditordialog.cpp`, 2175 lines.

The `.ui` DOM is `ui4.cpp`, 6218 lines, and `ui4_p.h`, 2933 lines. A search for `class Dom` in the header hit 58 lines. `abstractformbuilder.cpp`, 2583 lines, turns that DOM into widgets. Both are LGPL-set uilib, and `src/uitools/CMakeLists.txt` compiles them into `UiTools` under `QFORMINTERNAL_NAMESPACE`. The editor's save path that preserves Designer metadata is `qdesigner_resource.cpp`, 2282 lines, and that file is GPL-headed.

### Hardest behavior to recreate

These are the files that define the behavior, in the order they will hurt a port.

Layout editing. `layout.cpp`, `qlayout_widget.cpp`, `formlayoutmenu.cpp`, and the layout commands. Drop indicators, grid spans, spacers, and break layout are one system.

The undo catalog. `qdesigner_command.cpp` and the property command. Parity means every structural edit reverses as one user action.

Save and load that `QUiLoader` accepts, including promoted widgets, buddies, tab order, button groups, connections, and resources. The oracle is the LGPL loader. Study `qdesigner_resource.cpp` as the behavior of the GPL writer. Leave the file in the Qt tree.

Container pages. Tabs, toolboxes, stacked widgets, docks, MDI, and wizards go through the extension manager. A flat parent-child tree will not represent them.

Connection mode. `connectionedit.cpp` draws the signal and slot links and writes `<connections>`.

The property sheet. Defaults, resets, flags, enums, and resource-valued properties are why Designer files round-trip.

## Embedding

### What PySide exposes

FreeCAD 1.1.3 on this Mac is `/Applications/FreeCAD.app`. Its Python is `Contents/Resources/bin/python`, version 3.11.14. `PySide6.__version__` is 6.8.3.

`PySide6.QtDesigner` imports. `QDesignerComponents` is absent. `dir` has 31 public names. They are the abstract interfaces, `QFormBuilder`, `QAbstractFormBuilder`, the extension types, and the `QPyDesigner*` plugin bases. `share/PySide6/typesystems/typesystem_designer.xml` lists those types and does not list `QDesignerComponents`.

Constructing the abstract widget interfaces raises `NotImplementedError`. Constructing `QDesignerFormEditorInterface()` succeeds and returns an empty object. `metaObject().className()` is `QDesignerFormEditorInterface`. `formWindowManager()`, `widgetBox()`, `propertyEditor()`, `objectInspector()`, and `actionEditor()` return `None`. That object is not an editor.

`QFormBuilder.load` on a one-button `.ui` returned a `QWidget` named `Form`, with a `QPushButton` whose text is `Go`, inside a `QVBoxLayout` of count 1.

`PySide6.QtUiTools.QUiLoader` exists. The same file loaded to the same shape. `otool -L` on `QtUiTools.cpython-311-darwin.so` shows `libQt6UiTools` and not `libQt6Designer`. `otool -L` on `QtDesigner.cpython-311-darwin.so` shows `libQt6Designer`.

### The real factory is in the components library

`nm` on `libQt6DesignerComponents.dylib` exports `QDesignerComponents::createFormEditor(QObject*)`, `createWidgetBox`, `createPropertyEditor`, `createObjectInspector`, `createActionEditor`, `createSignalSlotEditor`, `createResourceEditor`, and `createFormEditorWithPluginPaths`. `c++filt` confirmed those names.

ctypes lookup with the extra Mach-O underscore failed. Lookup of `_ZN19QDesignerComponents16createFormEditorEP7QObject` succeeded. `createFormEditor(nullptr)` returned a pointer. `shiboken6.Shiboken.wrapInstance` produced `qdesigner_internal::FormEditor`. `formWindowManager()` was `qdesigner_internal::FormWindowManager`.

The same pattern constructed `qdesigner_internal::WidgetBox`, `PropertyEditor`, `ObjectInspector`, `ActionEditor`, `SignalSlotEditorWindow`, and `QtResourceView`. `core.widgetBox()` stayed `None` until something calls `setWidgetBox`. That matches the source.

`formWindowManager().createFormWindow(parent)` then segfaulted. `faulthandler` reported the fault on that line. Exit code 139. Platform was `QT_QPA_PLATFORM=offscreen`. `initializeResources()` had already returned. This probe did not install `QDesignerIntegration` or call `initializePlugins` before creating the form. The workbench does both before it has a usable form. The ctypes path can build the panels. It did not produce a form window.

A C++ shim would follow `QDesignerWorkbench`, not this ctypes sequence. It would call `createFormEditor`, `initializePlugins`, create and register each tool, construct `QDesignerIntegration`, then `createFormWindow`. That shim includes `qdesigner_components.h`, which is GPL. The shim is GPL. FreeCAD's Mac `Designer.json` says the library was built with Clang 18.1.8 for Darwin arm64. A shim built there does not run on ChoreBoy.

The Linux library exports the same factory with symbol version `@@Qt_6`. Measured on the extracted `libQt6DesignerComponents.so.6.8.3` from the 1.1.3 AppImage. `DesignerComponentsPrivate` is an `INTERNAL_MODULE`. Qt does not promise that private module's ABI across patch releases. A shim pinned to 6.8.3 can break when the appliance Qt moves.

The AppImage does not ship the headers. `create_bundle.sh` deletes `*.h` and `*.cmake`, and replaces `usr/bin` with a whitelist that does not include `designer`.

https://github.com/FreeCAD/FreeCAD-Bundle/blob/main/conda/linux/create_bundle.sh

A listing of the 1.1.3 x86_64 AppImage had `usr/lib/qt6/bin/designer` and the two Designer libraries, and the header grep did not show `qdesigner_components.h` or `include/qt6/QtDesigner/`. The shim has to be compiled against the qttools headers and the conda Qt 6.8.3 headers, on Linux x86_64, with the compiler ABI of that Qt. This session did not read the Linux `Designer.json` compiler id. The Mac one is Clang. Do not assume the Linux conda build is Clang.

### What the 1.1.3 Linux AppImage ships

Downloaded `FreeCAD_1.1.3-Linux-x86_64-py311.AppImage` from the GitHub 1.1.3 release onto `ssh debian`. Size 782 MiB, 820795896 bytes as reported by the release API. `unsquashfs -l` showed all of the following.

`usr/lib/libQt6Designer.so.6.8.3`

`usr/lib/libQt6DesignerComponents.so.6.8.3`

`usr/lib/libQt6UiTools.so.6.8.3`

`usr/lib/python3.11/site-packages/PySide6/QtDesigner.cpython-311-x86_64-linux-gnu.so`

`usr/lib/python3.11/site-packages/PySide6/QtUiTools.cpython-311-x86_64-linux-gnu.so`

`usr/lib/qt6/bin/designer`

`usr/lib/qt6/plugins/designer/libPySidePlugin.so`

`usr/lib/qt6/plugins/designer/libqquickwidget.so`

The extracted designer binary is a 796728 byte ELF x86-64 pie executable. `readelf -d` shows it needs `libQt6DesignerComponents.so.6`. The PySide `QtDesigner` module on Linux contains the bytes `QFormBuilder` and does not contain `QDesignerComponents` or `createFormEditor`.

`/opt/freecad` already mounted on that lab host is a different tree. `ls` of `libQt6Designer*` failed. `packages.txt` contains `noqt6 1.0`. It is not the 1.1.3 image.

### Launching the designer binary on ChoreBoy

`docs/DISCOVERY.md` section 4, from a probe on the appliance, says `/bin/sh` is the only binary a confined script executed, and that AppArmor blocked the other binaries in that probe. Research D records the same 2026-03-06 result, and records that the profile still allows another `/opt/freecad/AppRun`. The fourteen-binary probe did not execute `usr/lib/qt6/bin/designer`. Whether that path is denied is unverified. The binary exists in the 1.1.3 image, under `lib/qt6/bin`, so the bundle script's `usr/bin` whitelist does not remove it.

In-process use of `libQt6DesignerComponents` does not exec that binary. AppArmor's exec rule does not answer the dlopen question. This session did not load the library on Linux and did not read the production AppArmor profile.

## Where things live

| Piece | Source | Runtime in FreeCAD 1.1.3 |
| --- | --- | --- |
| Factory and panels | `src/designer/src/components`, GPL | `libQt6DesignerComponents`, Mac and the Linux AppImage |
| Abstract interfaces and shared editor code | `src/designer/src/lib`, mixed headers | `libQt6Designer`, loaded by `PySide6.QtDesigner` |
| `.ui` DOM and `QFormBuilder` | `src/designer/src/lib/uilib`, LGPL set | Inside both `libQt6Designer` and `libQt6UiTools` |
| `QUiLoader` | `src/uitools`, LGPL set | `PySide6.QtUiTools`, links `libQt6UiTools` only |
| `uic` | `qtbase/src/tools/uic`, GPL with exception | Not required at runtime if Code Studio writes `.ui` and Python |
| `.ui` schema | Qt 6.8 designer UI file format page | The file you save |

## Gotchas

`QDesignerFormEditorInterface()` looking constructible is a PySide hollow base. The real class name is `qdesigner_internal::FormEditor`, and only the components factory returns one.

`createWidgetBox` does not attach the box. Forgetting `setWidgetBox` leaves `core.widgetBox()` null.

The form window crash was real under offscreen ctypes use. Do not describe that probe as a working embedded designer.

`libQt6Designer` contains GPL-headed objects. Prefer `QUiLoader` when the goal is an LGPL oracle.

The lab host's `/opt/freecad` is not the 1.1.3 AppImage. The AppImage does contain the libraries.

Research D's product shape, a JSON layout and generated `setup_ui`, is a different file format from the `.ui` decision in this brief. Do not merge those recommendations silently.

## Recommendation

Ship a Python editor that writes `.ui`, and prove each behavior by loading the file with `QUiLoader` on FreeCAD 1.1.3. Study the GPL sources as a behavior list. Keep the notes. Leave the Qt code where it is. Use a written spec if counsel wants a clean-room record.

Experience first is why the recommendation is a Python editor. The brief asks for a modern, fast editor. The embedded widgets are Designer's panels, including its property browser and widget box. You would spend the license and the shim to inherit that interface.

Model the domain is why the hybrid is three pieces and not one port. The GPL editor implementation stays unread as code to copy. The LGPL loader is the oracle. The MIT editor owns the document and the canvas.

| Option | Effort | Risk | UX ceiling | Performance | Licence |
| --- | --- | --- | --- | --- | --- |
| Reimplement in Python, no reading of GPL sources beyond the public `.ui` schema and Qt docs | Longest. Guess, several quarters for full parity. The shared and component trees are about 74k nonblank lines, and `ui4.cpp` is not most of that. | Missed behavior until a golden file catches it. Lowest copyright risk if the public schema and loader are the spec. | The new editor. This is the only option whose ceiling is the UX you design. | Unmeasured. A canvas of real Qt widgets keeps layout in C++. A Python handler on every mouse move is the path that gets slow. | MIT code plus the LGPL `QtUiTools` dependency you can already carry beside PySide6. |
| Embed `QDesignerComponents` | Shortest path to panels. Guess, weeks for a Linux shim and workbench setup, then a long tail of focus, parenting, and plugin bugs. The ctypes form window already crashes. | ABI tied to an internal module. AppArmor exec of `designer` is unverified. The form window is not proven. | Designer's 6.8 interface. | Native, because it is Designer. Unmeasured here. | GPL combination. A lawyer has to bless distribution. A commercial Qt contract is the other grant, and it was not read. |
| Hybrid. Python editor, Designer studied as behavior, `QUiLoader` as the golden loader | Same order as a full reimplementation, with a tighter test loop. Guess, still quarters for menus, connections, resources, and promotion. Layouts and properties can land first. | Clean-room risk if the same person reads GPL implementation and writes Python. File-format drift if tests only check the happy path. | The new editor. Parity is a test result, not a widget you embedded. | Same as reimplement. The loader cost is one `QUiLoader.load` per check, which the probe did for a tiny file. | Does not link `libQt6DesignerComponents`. Uses LGPL `QtUiTools`. Leaves the `libQt6Designer` header conflict alone. |

Choose the hybrid.

The operator could instead tell you to embed, and to send the GPL and commercial questions to counsel before any shim is written. The operator could also tell you to reimplement from the public schema only, with nobody on the implementation reading `formwindow.cpp` or `qdesigner_command.cpp`.

## Principles that changed a choice

Experience first. Embedding was the short path to parity and was rejected as the product path because the panels are Designer's.

Model the domain. The work is three pieces. The GPL editor, the LGPL loader, and the MIT document.

Prove it works. The recommendation uses the loader that actually loaded a `.ui`, and it does not treat the hollow `QDesignerFormEditorInterface` or the crashed `createFormWindow` as success.

Explain the number. The line counts are physical lines and nonblank lines in the named suffixes. They bound source size. They do not bound a schedule. Generated `ui4.cpp` is inside the uilib total.

Never block on the human. The hybrid is the decision. The operator can pick embed or a stricter clean room instead.

Guard the context window. The how-skill explorer slug `grok-4.7-xhigh-fast` and the explainer slug `claude-opus-5-5-xhigh` are not in this session's model list. The measurements stayed in this thread so the command output is the evidence.

## Outcome

done

## What changed

`report_R2.md` is this file. It is the research deliverable.

No Code Studio repo files were edited. The qttools clone and the FreeCAD 1.1.3 AppImage were deleted after the notes above were taken.

## Verification

Commands and the results they produced.

Clone.

```
git clone --depth 1 --branch v6.8.3 --filter=blob:none --sparse https://github.com/qt/qttools.git qttools-v6.8.3
git sparse-checkout set src/designer src/uitools
git rev-parse HEAD
git describe --tags --exact-match
```

Output included `2649ea1aa5cc1c23bd920ae94dd50071315ea30f`, `v6.8.3`, and `du` of 13M for the checkout, 8.9M for `src/designer`, 184K for `src/uitools`.

Mac import.

`PySide6 6.8.3`. `QtDesigner` public count 31. `HAS_QDesignerComponents False`. `QFormBuilder` constructed. Abstract widget interfaces raised `NotImplementedError`. Empty `QDesignerFormEditorInterface` returned `None` from `formWindowManager`.

`QFormBuilder.load` printed `loaded QWidget Form`, `button Go`, `layout QVBoxLayout count 1`.

`QUiLoader` printed `QUiLoader QWidget Form Go QVBoxLayout`.

Factory.

`createFormEditor` pointer wrapped as `qdesigner_internal::FormEditor`. Widget box class `qdesigner_internal::WidgetBox`. Property editor, object inspector, action editor, signal slot window, and `QtResourceView` constructed. `createFormWindow` then printed `Fatal Python error: Segmentation fault` and the process exited 139.

Linux AppImage.

`curl` of `https://github.com/FreeCAD/FreeCAD/releases/download/1.1.3/FreeCAD_1.1.3-Linux-x86_64-py311.AppImage` finished at 782M. `unsquashfs -l` listed `libQt6Designer.so.6.8.3`, `libQt6DesignerComponents.so.6.8.3`, `libQt6UiTools.so.6.8.3`, both PySide modules, and `usr/lib/qt6/bin/designer`. `nm -D` after `c++filt` listed `QDesignerComponents::createFormEditor(QObject*)@@Qt_6` and the other `create*` factories. `file` said the designer binary is ELF 64-bit x86-64. The download directory `/tmp/r2-freecad-appimage` was removed. A later `ls` of that path failed with `No such file or directory`.

`/opt/freecad` on the same host does not contain `libQt6Designer*`.

## Decisions made

The product path is the hybrid. Python editor, standard `.ui`, `QUiLoader` as the golden loader, Designer source as a behavior spec, no copy, no embed.

The operator could choose a lawyer-reviewed embed instead, or a reimplementation whose authors do not read the GPL implementation files.

The how-skill explorer slug and explainer slug are absent from this session's model list. This thread ran the measurements.

## Open issues and risks

A lawyer has not resolved the `libQt6Designer` header conflict or the combined-work question for a future embed.

`createFormWindow` crashes in the offscreen ctypes setup. A careful C++ shim might get further. That was not built, on purpose.

The production AppArmor profile was not re-read, and `usr/lib/qt6/bin/designer` was not executed on an appliance. The 2026-03-06 probe did not include that binary.

The Linux Qt compiler id inside the 1.1.3 AppImage was not recorded. A shim would need it.

Line counts are not a schedule. Full parity is still the large project the component and shared trees imply.

The qttools checkout was removed after this report was written. Repeating the file citations means cloning tag `v6.8.3` again.
