# Visual GUI builders, a survey for ChoreBoy Code Studio

20 October 2026. Research only. No repository was modified except this file.

This survey is for the people who will design the visual GUI builder inside ChoreBoy Code Studio. The end user is a small-business owner who can write a Python script and wants a window that resizes. The next engineer inherits a PySide editor that must run offline, inside FreeCAD AppRun, on Python 3.9.2 today and on Python 3.11 later.

The question is which interaction and which file to copy. The answer is not "clone Qt Designer." The file Qt already loads is still the right file. The interaction around that file should come from Godot, Anvil, and Cambalache, not from Designer's absolute-then-layout dance.

Licence lines for Qt UI Tools, the Qt GPL exception, the missing .NET MAUI designer, and the current Slint Python wheel were fetched again while writing this report. Other URLs were retrieved in the research pass that produced the notes. A claim marked unverified was not on a page that pass opened. This is not legal advice.

## Overview

A visual GUI builder lets a person assemble a window by dragging, then keeps a file the program can load later. The products below disagree on three things. What file is real. Whether a human may edit that file and come back. Whether the builder also owns the click handlers.

Two families finish screens for non-specialists. Delphi, Visual Basic 6, Lazarus, Gambas, and Windows Forms put controls on a surface, list properties, and open a method when you double-click. GTK, WPF, Qt Widgets `.ui` files, and Avalonia keep a markup tree the toolkit loads, and the canvas is optional. The second family is what professionals trust when the serializer is stable. The first family is what hobbyists finish when the canvas is honest.

ChoreBoy already sits in the second family at runtime. `PySide2.QtUiTools.QUiLoader` loads a real `.ui` file. That was confirmed on the appliance and written up in `docs/DISCOVERY.md`. The editor already runs user code in a separate AppRun process, as `docs/PRD.md` and `docs/ARCHITECTURE.md` describe. AppArmor on current machines allows `/bin/sh` and little else, so a preview cannot shell out to a Designer binary. The preview has to be Python inside AppRun.

A prior designer plan in `docs/designer/ARCHITECTURE_PLAN.md` already picked an internal model, `.ui` import and export, and `QUiLoader` as the check that a save still loads. That file choice matches this survey. The interaction to copy is not Designer's. Phase 1 is layouts. Phase 2 is behavior. The tools that mix those two in one generated file are the ones users cannot reopen.

## Key concepts

**Source of truth.** The file you save, and the file a later edit reopens. It may be XML, QML, a scene text file, a form text file, generated code, or a hosted document you cannot download.

**Round-trip.** You edit the file or the generated code by hand, then open it in the visual tool, and you do not lose structure, names, or comments you meant to keep. Most builders fail this. The ones that work treat the visual tool as a projection of one file, and they leave a second file alone for logic.

**Layout model.** Absolute coordinates, anchors, boxes, grids, flex, or constraints. Qt Widgets layouts are boxes, grids, and form rows. They are not CSS flex, and they are not QML anchors. A builder that mixes two models without hiding the inactive one produces the "layout confusion" complaints below.

**Property editing.** A grid of name and value for the current selection. The good ones mark a changed value, reset it to the default, and write one edit onto every selected widget that has that property.

**Data binding.** A property shows a value from somewhere else, and updates when that value changes. Qt Designer has none. QML, Power Fx, Anvil, and XAML do.

**Event wiring.** A named signal, a generated method, a formula, a node wire, or a block. Phase 1 only needs a name stored next to the widget. Phase 2 needs a place to put the Python, and that place must survive the next layout save.

**Preview.** A picture of the form, a live widget tree in another process, or a hot reload of a running app. A preview that runs inside the editor process will take the editor down when a custom widget aborts. Cambalache and the Code Studio runner split exist for that reason.

**Component reuse.** A nested form, a promoted class, a Figma-style main component, or a copy of widgets. The nested form is the one that matches Qt.

**Theming.** A style, a palette, a few named roles, or a color on every control. Small-business screens need the roles. Per-control colors do not survive a font or a theme change.

## How a builder is put together

The tables below are the catalog. This section keeps the facts that change the Code Studio choice, and the user comments that explain them.

### Qt

Qt Widgets Designer edits an XML `.ui` file. The schema is public. <https://doc.qt.io/qt-6/designer-ui-file-format.html>. You reopen the XML. You do not reopen the Python from `pyside6-uic`. That page says not to edit the generated file, because the next run replaces it. <https://doc.qt.io/qtforpython-6/tools/pyside-uic.html>.

Widgets start at absolute positions. A form does not resize until you apply `QHBoxLayout`, `QVBoxLayout`, `QGridLayout`, or `QFormLayout`. <https://doc.qt.io/qt-6/designer-layouts.html>. The property editor marks changed values in bold and writes through a multi-selection. <https://doc.qt.io/qt-6/designer-widget-mode.html>. There is no binding expression. Signals are `<connection>` records. <https://doc.qt.io/qt-6/designer-connection-mode.html>. Preview is Ctrl+R of the form, not of your application. Custom widgets are promotions or plugins. Promotion stores class, base, and a header. In Python the header is the module path with `.py` written as `.h`. Designer keeps drawing the base class. <https://doc.qt.io/qt-6/designer-using-custom-widgets.html>.

The tools are commercial, or GPL-3.0 with the Qt GPL Exception 1.0. <https://doc.qt.io/qt-6/licensing.html>. Exception 1, fetched for this report, lets you ship a larger work that contains Designer's output, under terms you choose, if that work is not itself based on Designer and does not itself generate output that contains Designer's output. <https://doc.qt.io/qt-6/qt-gpl-exception-1-0.html>. An editor that embeds Designer and writes `.ui` files fails that sentence. An editor you write yourself, which emits `.ui` XML, is not that case.

`QUiLoader` is the runtime loader. On Qt 5.15, since Qt 5.11, Qt UI Tools is BSD-3-Clause or commercial. Fetched from <https://doc.qt.io/archives/qt-5.15/qtuitools-index.html>. On Qt 6.12, since Qt 6.0, it is LGPL-3.0 or GPL-2.0, or commercial. Fetched from <https://doc.qt.io/qt-6.12/qtuitools-index.html>. The Qt 6 page says a hostile `.ui` file can hang the process, spoof the UI, or load an unexpected plugin. Qt Widgets themselves are LGPL-3.0 or GPL-2.0, or commercial. <https://doc.qt.io/qt-6.12/qtwidgets-index.html>.

On Hacker News in March 2023, dekhn wrote "The one tool I truly love is Qt Designer." <https://news.ycombinator.com/item?id=35361163>. In December 2023, felipefar preferred it to Design Studio. <https://news.ycombinator.com/item?id=38697334>. A 2020 forum thread ends with "There is nothing you can do about designer" and tells you to edit the XML. <https://forum.qt.io/topic/114601/how-to-adapt-designer-property-for-doubles>.

Qt Creator opens the same `.ui` files. Go to Slot writes C++. Plugins must match Creator's build, or they load in standalone Designer and fail inside the IDE. <https://doc.qt.io/qtcreator/adding-plugins.html>. Distributing Creator needs a separate agreement. <https://www.qt.io/development/tools/qt-creator-licensing>.

Qt Design Studio edits `.ui.qml`, not widgets. Unsupported code must move to a `.qml` file or the 2D view stops. <https://doc.qt.io/qt-6/qtquick-bestpractices.html>. Absolute position, anchors, and Qt Quick Layouts are three systems, and mixing anchors with `x` or `width` is undefined. <https://doc.qt.io/qt-6/qtquick-positioning-anchors.html>. The same December 2023 thread calls the studio "buggy and heavyweight" and says it "doesn't produce clean .qml files." A July 2026 Reddit title says it crashes when adding a text box to a layout. The full page was not fetched. <https://www.reddit.com/r/QtFramework/comments/1upmc62/qt_design_studio_is_completely_broken_and_crashes/>.

`pyside6-designer` launches the Designer binary inside the wheel and can load Python plugins. <https://doc.qt.io/qtforpython-6/tools/pyside-designer.html>. `pyside2-designer` is the same kind of wrapper. No PySide2 page for `PYSIDE_DESIGNER_PLUGINS` was found. PySide6 is LGPL-3.0 or GPL-3.0, or commercial. <https://doc.qt.io/qtforpython-6/index.html>. A May 2022 Qt Company mail says `pyside6-uic` is the real `uic`, and `pyside2-uic` was a Python port. <https://lists.qt-project.org/pipermail/pyside/2022-May/003138.html>.

QtPy is an MIT import shim, not a designer. <https://github.com/spyder-ide/qtpy/blob/master/LICENSE.txt>. Its `loadUi` path mishandles promoted widgets. <https://github.com/spyder-ide/qtpy/issues/104>. A November 2025 note says passing a base instance can crash. <https://github.com/spyder-ide/qtpy/issues/513>.

### Desktop builders

Glade is frozen. The 10 August 2022 announcement calls 3.40.0 the last stable release. <https://glade.gnome.org/>. The file is GtkBuilder XML, which GTK loads without Glade. <https://docs.gtk.org/gtk4/class.Builder.html>. Signals are handler names, not generated methods. In November 2020, u/johnfactotum wrote that a Glade save "will completely mess up the file" and often "completely break the app." <https://www.reddit.com/r/gnome/comments/jyf4xu/glade_not_recommended/>. The README says GPL version 2 and GNU Library GPL version 2. COPYING says the package is LGPL and some files are still GPL only. <https://raw.githubusercontent.com/deepin-community/glade/master/COPYING>.

Cambalache, by the same author, reached 1.0 on 20 March 2026. <https://blogs.gnome.org/gtk/2026/03/20/cambalaches-first-major-milestone/>. It writes `.ui` directly, warns if you edit the file by hand, and the author says later saves stay stable. Preview runs in another process, so a widget that aborts does not kill the designer. The README licences the app as LGPL 2.1 and the tools as GPL version 2. "Or later" is not in that README. <https://raw.githubusercontent.com/xjuan/cambalache/main/README.md>. The 1.0 post says the audience is people who already know GtkBuilder. A 2023 comment called it laggy. <https://discourse.gnome.org/t/gtk3-to-gtk4-ui-migration/14998>.

Delphi stores a text or binary `.dfm` or `.fmx` beside a Pascal unit. Text reopens. Layout is pixels, then Align and Anchors. On Hacker News in March 2025, theamk called it "extremely nice" and also said forms were "hard-coded to specific font sizes," so many windows were not resizable "just because it was easier." <https://news.ycombinator.com/item?id=43463179>. The designer is proprietary.

Lazarus uses a text `.lfm`. The designer directory is GPLv2. The widget library is a modified LGPL. <https://gitlab.com/freepascal.org/lazarus/lazarus/-/raw/main/COPYING.txt>. Align, anchors, and child sizing can override a position you just dragged. <https://lists.lazarus-ide.org/pipermail/lazarus/2020-June/238124.html>. Anchor sides can pin any side of one control to any side of another. <https://wiki.freepascal.org/Anchor_Sides>.

Visual Basic 6 puts layout and code in one `.frm`, in twips. <https://learn.microsoft.com/en-us/previous-versions/visualstudio/visual-basic-6/aa241723(v=vs.60)>. The IDE has been unsupported since 8 April 2008. <https://learn.microsoft.com/en-us/previous-versions/visualstudio/visual-basic-6/visual-basic-6-support-policy>. Windows Forms keeps layout in generated `InitializeComponent`. There is no separate form file. <https://stackoverflow.com/questions/3786512/changing-autogenerated-code-in-a-c-windows-forms-application-project>. Delete the method and leave the subscription, and the form will not load. <https://stackoverflow.com/questions/20491653/how-do-i-delete-the-generated-function-from-accidentally-double-clicking-on-a-bu>. A 2024 Reddit thread says that "breaks everything," and a reply still calls it the fastest basic UI. <https://www.reddit.com/r/csharp/comments/1d4jr87/is_winforms_designer_a_mess_or_am_i_crazy/>. The framework is MIT. The designer is Visual Studio. <https://github.com/dotnet/winforms/blob/main/LICENSE.TXT>.

WPF's file is XAML, and hand-edited XAML reopens. The drag is the problem. In July 2024, u/binarycow wrote that the designer "tries to put things exactly where you put it, which leads to a bunch of margins." <https://www.reddit.com/r/csharp/comments/1eaoywm/wpf_do_you_guys_use_the_designer_or_code_xaml_to/>. .NET MAUI has no visual designer. The Learn page, fetched for this report, says all XAML must be hand-written, and hot reload is how you see it. <https://learn.microsoft.com/en-us/dotnet/maui/xaml/?view=net-maui-9.0>. Hot reload does not reload C#. <https://learn.microsoft.com/en-us/dotnet/maui/xaml/hot-reload?view=net-maui-10.0>.

Avalonia's framework is MIT. <https://raw.githubusercontent.com/AvaloniaUI/Avalonia/master/licence.md>. The current professional designer is paid. The company says the framework stays MIT and the licence is for the tooling. <https://avaloniaui.net/blog/building-a-sustainable-future-for-avalonia>. The migration guide says there is no drag-and-drop palette. <https://docs.avaloniaui.net/docs/migration/other/>. Gambas keeps a text `.form` separate from the class, with pixel positions plus a container arrangement. Double-click opens the method in the class file. <https://gambaswiki.org/wiki/doc/startIDE>. The wiki prints GPL version 2. The form compiler header says or later.

### Python toolkits and phone previews

PAGE saves Tcl and generates Python. Callbacks live in a support module that PAGE will extend and will not delete. Layout is Tk place only. <https://page.sourceforge.net/html/intro.html>. SourceForge says GPLv2. A December 2025 review says a project corrupted and could no longer generate code. <https://sourceforge.net/projects/page/reviews/>.

Pygubu stores XML. The designer README says GPL-3.0 for the designer and MIT for generated scripts, matching the core. <https://raw.githubusercontent.com/alejandroautalan/pygubu-designer/master/README.md>. Pack and grid cannot share a parent. <https://github.com/alejandroautalan/pygubu-designer/discussions/296>. u/Dogeek called it "borderline unusable" next to Qt Designer. <https://www.reddit.com/r/pythontips/comments/b4oj4e/a_gui_designer_for_tkinter/>.

Tkinter-Designer is BSD-3-Clause and one way, from Figma's API to Tk place. <https://github.com/ParthJadhav/Tkinter-Designer/blob/master/LICENSE>. It needs the network. Issue 42 is an empty window because coordinates were relative to the outer canvas. <https://github.com/ParthJadhav/Tkinter-Designer/issues/42>.

Dear PyGui and Dear ImGui are immediate mode. There is no form file. Both are MIT. A 2019 issue says ImGui "doesn't have a real layout engine." <https://github.com/hoffstadt/DearPyGui/issues/158>. Two drag-and-drop ImGui designers did not return a licence. Treat them as unverified.

Slint's layout language is real, and the current Python wheel is not usable here. PyPI 1.18.1b1, fetched for this report, requires Python 3.12 or newer. <https://pypi.org/project/slint/>. The royalty-free licence forbids an application that exposes Slint's APIs. <https://github.com/slint-ui/slint/blob/master/LICENSE.md>.

Flutter's rule is the clean one. Constraints go down. Sizes go up. The parent sets position. <https://docs.flutter.dev/ui/layout/constraints>. FlutterFlow is a hosted project on top of that. Export overwrites `lib/`. A 2026 thread says edited page code does not go back except through the custom-code panel. <https://www.reddit.com/r/FlutterFlow/comments/1wppzjk/any_update_on_importing_back_code_edited_in_vs/>.

SwiftUI and Compose previews render the function you wrote. There is no second design file. Users still report crashes and stale previews. <https://www.reddit.com/r/SwiftUI/comments/1oteqd3/swiftui_previews_are_still_a_mess_in_2025/> and <https://stackoverflow.com/questions/68623666/jetpack-compose-the-preview-does-not-render-in-real-time>. The lesson is the single source. The compiler is the fragile part. Neither runtime embeds in PySide.

### Design tools and game editors

Godot is the closest open widget editor to read. A container parent owns child position and size. <https://docs.godotengine.org/en/stable/tutorials/ui/gui_containers.html>. The scene file is text `.tscn`. Save drops comments and default values. <https://docs.godotengine.org/en/stable/engine_details/file_formats/tscn.html>. The engine is MIT. <https://godotengine.org/license/>. A Reddit comment calls the position lock "a blessing." <https://www.reddit.com/r/godot/comments/105ppgo/godot_4_size_flagsauto_expand_ui/>.

Unity UI Toolkit is UXML plus USS, laid out with flexbox. UI Builder strips USS comments on save. <https://docs.unity3d.com/Manual/UIB-styling-ui-using-uss-selectors.html>. Events are C# and are not stored on the widget. The editor terms keep the toolkit inside Unity. <https://unity.com/legal/editor-terms-of-service/software>.

Figma auto layout is hug and fill. Constraints apply only outside auto layout. <https://help.figma.com/hc/en-us/articles/360040451373-Guide-to-auto-layout-in-Figma>. Dev Mode is not a round-trip. A Hacker News comment says its absolute positioning is "never useful." <https://news.ycombinator.com/item?id=40220939>. Penpot is MPL-2.0 and uses CSS flex and grid names. <https://github.com/penpot/penpot/blob/master/LICENSE>. The same Reddit thread that praises that model says panning many screens is much slower than Figma. <https://www.reddit.com/r/web_design/comments/1epzrmm/has_anyone_made_the_switch_from_figma_to_penpot/>. Framer does not export the project. Webflow export is one way, and combo classes hide the base style. <https://www.reddit.com/r/webflow/comments/1amz6lz/editing_combo_classes/>.

### Low-code builders

Plasmic's JSON tree is the source. Generated React is overwritten. Your wrapper is left alone. Chung Wu wrote "You're never directly editing the code generated by Plasmic." <https://news.ycombinator.com/item?id=38699261>. Code outside `platform/` is MIT. The Studio is AGPL-3.0. <https://github.com/plasmicapp/plasmic>. Builder.io's editor is closed. The SDK and Mitosis are MIT, and the company has said you cannot self-host the editor. <https://github.com/BuilderIO/builder/issues/379>.

Retool classic apps use a 12-column grid and `{{ }}` expressions. The product is proprietary. <https://docs.retool.com/legal/customer-terms-of-service>. Appsmith Community Edition is still Apache-2.0. <https://www.appsmith.com/terms-and-conditions>. Which canvas new apps use was not settled. Budibase is GPL-3.0 overall, MPL-2.0 for the client libraries, and Business Source License for paid features. <https://github.com/Budibase/budibase/blob/master/LICENSE>. The binding drawer shows the current value on hover. Theme is one accent and one font. <https://docs.budibase.com/docs/app-theming>.

Anvil is the closest Python split. A form is a class plus `form_template.yaml`. Git has no hidden file. <https://github.com/anvil-works/anvil-runtime/blob/master/doc/app-structure.md>. The event button inserts a method. A binding is one Python expression, and a missing key renders blank. <https://anvil.works/docs/client/component-properties/data-bindings>. Layout is slots, not a free canvas. The runtime is AGPL-3.0 with an exception for apps. <https://github.com/anvil-works/anvil-runtime/blob/master/LICENSE>. The designer is not in that repo. Its licence was not found. Client Python is Skulpt, not CPython 3.9.

Power Apps uses X and Y unless you opt into a container, and a later drag overwrites a formula. <https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/create-responsive-layout>. The formula bar is the piece to copy. Power Fx is MIT. Studio is not. <https://github.com/microsoft/Power-Fx/blob/main/LICENSE>. Bubble does not export an app. <https://manual.bubble.io/account-and-marketplace/application-and-data-ownership>. A review calls responsive layout a nightmare and the workflow strip terrible. <https://www.capterra.com/p/171359/Bubble/reviews/?page=7>.

### Logic and AI

Scratch's current editor and VM are AGPL-3.0-only as of 25 November 2024. <https://github.com/scratchfoundation/scratch-gui/blob/6ccd0e98/CHANGELOG.md>. `scratch-blocks` and Blockly are Apache-2.0. Blockly generates code and does not import it back. <https://stackoverflow.com/questions/47572536/how-to-generate-blocks-from-code-in-blockly>. Node-RED core is Apache-2.0. Node coordinates are not widget layout. Dashboard 2 has a grid, and its licence was not retrieved.

Unreal's Designer tab is hierarchy, anchors, and a details panel. The graph does not round-trip to text. <https://news.ycombinator.com/item?id=37509533>. Power Fx splits value formulas, which recalculate, from behavior formulas such as `OnSelect`. <https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/working-with-formulas>.

v0, Lovable, and Figma Make turn a visual tweak into another model call. v0's docs claim two-way Git. Users report unrelated rewrites. <https://community.vercel.com/t/v0-keeps-nuking-my-codebase-when-i-ask-for-simple-changes/23798>. Lovable's current docs replaced direct visual edits with a prompt on the selected element. <https://docs.lovable.dev/features/preview-toolbar>. Figma Make's Apply spends credits. <https://help.figma.com/hc/en-us/articles/33649966245783-Edit-the-code-of-a-functional-prototype-or-web-app>.

Claude's legacy artifacts have no canvas. <https://support.claude.com/en/articles/9487310-what-are-artifacts-and-how-do-i-use-them>. Claude Design does. You drag, comment, and export. There is no sync back into a widget library. <https://support.claude.com/en/articles/14604416-get-started-with-claude-design>.


## Comparison

Forty-nine tools and formats are in the tables. QtPy is a library, not a builder, and it is included because a PySide editor will be tempted to depend on it. Dashboard 2 is listed with Node-RED because that is where the layout lives.

### Qt and the Python wrappers

| Tool | Source of truth | Round-trip | Layout | Wiring | Preview | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| Qt Designer | `.ui` XML | Reopen the XML. Generated code is one way. | Absolute, then box, grid, or form | Signal and slot records, label buddies | Ctrl+R form preview | GPL-3.0 plus Qt GPL Exception 1.0 |
| Qt Creator form editor | Same `.ui` | Same as Designer | Same | Go to Slot writes C++ | Alt+Shift+R | GPL-3.0 plus the exception. Redistribution needs a separate agreement |
| Qt Design Studio | `.ui.qml` and `.qml` | Studio rewrites UI files. Unsupported code must move to `.qml` | Anchors, positioners, and Quick Layouts. Do not mix them | Connections view or `onClicked` | Live Preview via `qml` | GPL-3.0 plus the exception, or commercial |
| `pyside6-designer` | `.ui` | Same as Designer. Python plugins only in this process | Same as Designer | Same | Designer's preview, real plugin widgets | PySide6 is LGPL-3.0 or GPL-3.0, or commercial. The binary is the GPL tool |
| `pyside2-designer` | `.ui` | Same. No Python plugin loader found | Same | Same | Same | PySide2 5.15.2.1 on PyPI is LGPL. That release requires Python below 3.11 |
| QtPy | None | Not a designer. `loadUi` reads `.ui` | None | None | None | MIT |
| `QUiLoader` and `uic` | `.ui` in, widgets or Python out | Neither writes `.ui` back | Whatever the file says | String signal names. Python types on custom slots fail in `QUiLoader` | None. They instantiate | UI Tools is BSD-3-Clause on Qt 5.15, LGPL-3.0 or GPL-2.0 on Qt 6. `uic` is GPL-3.0 plus the exception |

### Classic desktop

| Tool | Source of truth | Round-trip | Layout | Wiring | Preview | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| Glade | GtkBuilder XML | The runtime loads hand XML. Glade's save often ruins it | Boxes and grids | Handler name, connected by the app | In-tool preview for a toplevel | Mixed GPL-2.0 and LGPL. Frozen in 2022 |
| Cambalache | GtkBuilder `.ui`, plus Blueprint and CSS in 1.0 | Direct save. Warns on hand edits. Stable after the first save | Boxes, grids, placeholders | Handler names | Separate process | App LGPL-2.1. Tools GPL-2.0. "Or later" not in the README |
| Delphi VCL and FireMonkey | `.dfm` or `.fmx` plus a unit | Text form reopens. Binary does not diff | Pixels, then Align and Anchors | Double-click inserts a method | The form is live. Run compiles | Proprietary |
| Lazarus | `.lfm` plus a unit | Text reopens. The IDE rewrites on save | Align, anchors, anchor sides, child sizing | Events tab creates the method | The form is the canvas. Run compiles | Designer GPLv2. LCL modified LGPL |
| Visual Basic 6 | `.frm` text plus `.frx` binary | You can open the `.frm` in a text editor. Layout and code share the file | Twips, absolute, nested frames | Double-click opens `Name_Event` | Run in the IDE | Proprietary. IDE unsupported since 2008 |
| Windows Forms | `*.Designer.cs` | The next designer save overwrites hand edits | Absolute, Anchor, Dock | Double-click writes the method and the subscription | Design surface runs control code. .NET designer is out of process | Framework MIT. Designer is Visual Studio |
| WPF and Blend | XAML | Hand-edited XAML reopens. Drags add margins | Panels. Canvas is the absolute one | Event attributes or bindings | Artboard often disagrees with runtime. Hot reload exists | Framework MIT. Designer and Blend are Visual Studio |
| .NET MAUI | XAML | Hand-written only | Stack, grid, flex, absolute | Handlers in C#. Hot reload does not reload C# | Hot reload and a screenshot preview. No canvas | Framework MIT. Hot reload is Visual Studio |
| Avalonia | `.axaml` | Hand-edited AXAML reopens in the previewer | Stack and grid, WPF-like | Event attributes or commands | Out-of-process previewer | Framework MIT. Current pro designer is paid |
| Gambas | `.form` text, separate from the class | Text. IDE rewrite behavior was not tested | Pixels plus arrangement on the container | Double-click opens the class method | F5 runs the project | GPL-2.0 text on the wiki. Form compiler header says or later |

### Python, immediate mode, and declarative previews

| Tool | Source of truth | Round-trip | Layout | Wiring | Preview | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| PAGE | `.tcl` project | Generated Python does not reopen. Support module keeps callbacks | Tk place only | Skeletons appended to the support module | Separate run inside PAGE | SourceForge says GPLv2. Generated-code terms not found |
| Pygubu | XML `.ui` | Reopen the XML, not the generated base class | pack, grid, or place. Pack and grid cannot share a parent | `connect_callbacks` | Designer preview. High-DPI issues reported | Designer GPL-3.0. Core and generated scripts MIT |
| Tkinter-Designer | Figma file, via API | One way. Regeneration clears the build | Tk place, absolute | Button stubs you fill in | Run the generated process. Needs network | BSD-3-Clause |
| Dear PyGui | Python | No design file | Container stack. No real layout engine | `callback=` | The app is the preview | MIT. Python 3.8 and newer |
| Dear ImGui | C++ each frame | No project file | Cursor stack, tables, docking branch | The widget call returns the click | Demo window | MIT |
| Slint | `.slint` | You edit `.slint`, not generated Python | Horizontal, vertical, and grid, plus stretch | Callbacks in Slint or assigned from Python | `slint-viewer --auto-reload` | GPL-3.0-only, royalty-free, or paid. Python wheel requires 3.12 or newer |
| Flutter | Dart widgets | No design file in the framework | Constraints down, sizes up, parent sets position | Callbacks in Dart | Hot reload was not re-fetched | 3-clause BSD text, no SPDX line in the file |
| FlutterFlow | Hosted project, YAML on a paid tier | Export overwrites `lib/`. Custom code is the only push-back path | Row, Column, Stack. Nesting limit 10 | Action flow graph | Run and local device test on paid plans | Proprietary. You own the export |
| SwiftUI previews | Swift source | The preview is that source | HStack, VStack, ZStack | Closures and `@Binding` | `#Preview` in Xcode. Often crashes | Proprietary |
| Jetpack Compose previews | Kotlin `@Composable` | The preview is that function | Row, Column, Box | State down, events up | `@Preview`. Often stale until a build | Studio is proprietary. Compose library licence file was not fetched |

### Design tools and game editors

| Tool | Source of truth | Round-trip | Layout | Wiring | Preview | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| Godot | `.tscn` text | Hand-editable. Save drops comments and default values | Anchors, or a container that owns geometry | Signal dock writes a method name | 2D view, then F5 or F6 | MIT |
| Unity UI Toolkit | UXML and USS | Builder opens them and strips USS comments | Yoga flex, plus absolute | C# callbacks, not saved on the element | Builder viewport, then Play mode | Proprietary, editor only |
| Figma | Cloud file. `.fig` is not a public format | No code round-trip. Token JSON is the exchange | Auto layout, or constraints outside it | Prototype wires, not callbacks | Present the prototype | Proprietary SaaS |
| Penpot | Cloud file. Export is `.penpot` JSON zip | CSS and HTML are one way. Token JSON is two way. Hand-edited zip reimport is unverified | Flex and CSS grid, plus constraints | Prototype wires | View mode | MPL-2.0 |
| Framer | Hosted project | No layout export. Code components are React you write there | Stacks and grids, breakpoints | Overrides and component variants | Play, then publish | Proprietary |
| Webflow | Hosted project | Export and DevLink are one way | Flex and grid on a class | Interactions, not a general function call | Canvas at a breakpoint, then publish | Proprietary |

### Low-code, logic, and AI

| Tool | Source of truth | Round-trip | Layout | Wiring | Preview | Licence |
| --- | --- | --- | --- | --- | --- | --- |
| Plasmic | JSON tree. Codegen is a projection | Do not edit generated files. Wrappers are left alone | Stacks and grids | Trigger, then ordered actions | Loader preview mode. Studio play button unverified | MIT outside `platform/`. Studio AGPL-3.0 |
| Builder.io | JSON blocks | SDK renders JSON. Editor reimport of hand-written React is unverified | Columns and breakpoint styles | Actions and expression bindings | Local preview URL for custom components | SDKs and Mitosis MIT. Editor closed |
| Retool | Toolscript or, in the new builder, React | Classic files are for merge conflicts. New builder lets you edit the code tab | Classic 12-column grid. New builder has no fixed grid | Event handlers, or TypeScript on the server | Live canvas. Writes ask for approval | Proprietary |
| Appsmith | JSON DSL in git | Hand-edit of the DSL is unverified | Fixed column and row units, and a newer zoned grid. Which one new apps use is unverified | `onClick` runs a query or a JS function | Edit, preview, deploy | Apache-2.0 for Community Edition |
| Budibase | Workspace documents | Not a codegen product | Grid or flex containers | Click actions, plus workspace automations | Preview modal, then publish | Core GPL-3.0. Client MPL-2.0. Pro is BSL |
| Anvil | `form_template.yaml` plus a Python class | Git is complete. Some column ids exist only in YAML | Containers and named slots | Inserts a real method | Run in the editor. Tracebacks open the line | Runtime AGPL-3.0 plus an app exception. Editor licence not published |
| Power Apps | `.msapp`, viewed as `.pa.yaml` | YAML is documented as read-only, and a later plan says external refactor. Current behavior unverified | X and Y, or auto-layout containers. A drag can wipe a formula | `OnSelect` and other formulas | Device preview | Studio proprietary. Power Fx MIT |
| Bubble | Hosted AST | No code export | Container column, row, align, or fixed | Workflow list | Preview writes the development database | Proprietary |
| Scratch | `.sb3` zip of JSON | No code view | A stage, not a form | Hat blocks and broadcasts | In-browser VM | Editor and VM AGPL-3.0-only since November 2024. `scratch-blocks` Apache-2.0 |
| Blockly | Workspace JSON | Blocks to code only | None. `x` and `y` are block positions | Whatever blocks the host defines | Host runs the generated text | Apache-2.0 |
| Node-RED | Flow JSON | The graph is the source. Function nodes hold JavaScript inside the node | Core has none. Dashboard 2 has grid, fixed, and notebook. Dashboard licence unverified | Message wires | Deploy to the runtime | Core Apache-2.0 |
| Unreal Blueprints | Binary `.uasset` | No text round-trip | UMG anchors and slots on the Designer tab | Exec and data pins on the graph tab | Compile, then Play | Proprietary. EULA text not opened |
| v0 | Generated Next.js files | Vendor says Git is two-way. Users report unrelated rewrites | Tailwind in the files. Design Mode edits spacing and type | Prompted into React | Sandbox VM, up to 24 hours | Proprietary |
| Lovable | Generated app repo | Git sync is two-way until a force-push or a conflict | Whatever the model wrote | Prompted | Preview shares backend data with the published app | Proprietary. You own the output, per the terms |
| Figma Make | React in the Make file | You can edit files the agent created. No Git round-trip found | Preview plus a properties panel. Apply calls the model | Prompted | Agent updates the preview | Proprietary |
| Claude artifacts | One HTML or React piece, or a Design canvas | Copy out. No repo sync | Design canvas only. Legacy artifacts do not drag | Prompted, or JS inside the artifact | Sandboxed iframe for Design previews | Proprietary |

## Patterns the best builders share

These are the patterns that show up in tools people finish work in, and that survive a hand edit. They are listed in the order a Code Studio builder would meet them.

1. **Three panes, and no fourth mystery.** Hierarchy, canvas, and an inspector. Godot's Scene dock, Figma's layers, Designer's object inspector, and Anvil's component tree are the same picture. A second style language, like Webflow combo classes, hides the value the user thinks they are editing.

2. **The toolkit file is the file you edit.** GtkBuilder XML, Qt `.ui`, XAML, AXAML, Godot `.tscn`, and Anvil's `form_template.yaml` can be opened in a text editor. Windows Forms fails because the only file is generated code. Bubble fails because there is no file. FlutterFlow fails because the file you get is a projection that the next export replaces.

3. **The serializer omits defaults and then stays still.** Godot omits default properties. Cambalache's author says the first save reorders and later saves do not. Glade's save is the counterexample. It bloats the file and can break the app. A reviewable diff is part of the product for anyone who keeps projects on a USB stick.

4. **A container owns geometry, and the inspector admits it.** Godot hides the usefulness of a manual position when a container parent will overwrite it. A Reddit user called that a blessing. Qt Designer still shows x and y after you have put the widget in a layout, and it makes you break the layout to drag again. Figma is the same split done cleanly. Auto layout, or constraints, and not both at once on the same child.

5. **One layout system is the default.** For Qt Widgets that system is box, grid, and form. Absolute placement is how you sketch before the layout exists. It is not what you save for a window that must survive a font change. Delphi's own fans named that failure. PAGE and Tkinter-Designer never left absolute placement, and both show the cost.

6. **The property grid is small, honest, and multi-select.** Changed values look different. Reset restores the default and deletes the line from the file. One edit applies to every selected widget that has the property. Designer, Lazarus, and Figma all do a version of this. The rest of the properties sit behind a more control, the way Anvil collapses them. Budibase's binding drawer, which shows the current value when you hover, is the right extra for expressions later.

7. **Names in the inspector are names in Python.** Anvil shows `self.button_1`. Designer object names become attribute names after `setupUi`. A builder that shows a friendly label and stores a different id will confuse the first person who reads the code. Code Studio's users will read the code.

8. **Logic sits in a file the designer does not rewrite.** PAGE's support module, Pygubu's subclass, Plasmic's wrapper, and Anvil's form class are the same rule. The designer may append a stub. It may store a connection name. It does not own the method body. WinForms breaks the rule by writing the subscription in the generated file, so deleting the stub leaves a form that will not load.

9. **Preview is another process.** Cambalache's Merengue, Avalonia's previewer protocol, the .NET WinForms designer, and Code Studio's existing runner are the same shape. A custom widget with a bug must not kill the editor. Hot reload inside one process is what SwiftUI and Compose users already find fragile. On ChoreBoy the second process is another AppRun, because AppArmor will not let you exec a Designer binary.

10. **A component is a nested form with a few public properties.** Godot scenes, Anvil custom components, Qt promoted widgets, and Figma components all instance a definition. Overrides are explicit. Copy-paste of widgets feels faster for a day and then cannot be updated. Promotion is the Qt mechanism that needs no C++ plugin. The canvas draws the base class until you host the real Python widget yourself.

11. **Theme is a handful of roles.** Budibase's accent and font, Godot's theme types, and Power Apps' modern theme from a seed color all restyle a screen without a color property on every label. Qt already has `QStyle` and style sheets. The builder should set a role, not invite a per-widget palette edit as the normal path.

12. **A binding is visible, and a later drag does not delete it.** Power Apps is the warning. Responsive formulas are real, and a drag replaces them with constants. Anvil stores one Python expression per property and ignores a missing key so a blank record still renders. Phase 1 can skip expressions. Phase 1 must not paint itself into a corner where the only stored value is a literal that a drag is allowed to destroy.

13. **The list you repeat is a template, not a copied row.** Power Apps galleries, Anvil `RepeatingPanel`, and Budibase repeaters all edit the first row. Qt's widget layouts do not do this by themselves. A phase 1 builder can ignore it. A phase 1 data-entry screen will want it immediately after, so the file format should allow a widget that repeats a child form.

14. **Show what uses a widget before you delete it.** Bubble's element inspector lists workflows and references. WinForms does not, and the dangling subscription is the result. A tree delete in Code Studio should list signal names and buddy links that point at the widget.

15. **If a model writes the file, it writes it once.** v0, Lovable, and Figma Make turn every visual tweak into another generation, and users lose layout they did not mean to change. An assistant may create the first `.ui`. After that the canvas writes the file directly. The model does not get a second pass unless the user asks.

## Failure modes

**Round-trip breakage.** The visual tool and the hand edit disagree about which file is real. `pyside6-uic` tells you not to edit the Python it writes. FlutterFlow overwrites `lib/` on export. Plasmic overwrites `plasmic/Plasmic*.tsx`. WinForms overwrites `InitializeComponent`. v0 rewrites files you did not mention. The fix is one layout file, one logic file, and a generator that only touches the layout file.

**Serializer vandalism.** Glade rewrites hand-tuned XML into something the next open cannot trust. Unity UI Builder removes USS comments. Godot drops comments too, which is acceptable only because the docs say defaults and comments are not preserved. Power Apps documents that the JSON inside `.msapp` is not stable across save and load, which is why they grew a YAML view. A Code Studio save must be deterministic. Same form, same bytes, apart from a trailing newline.

**Qt Designer clunk.** The widget is placed in pixels. Nothing resizes until someone remembers Ctrl+1 or the layout toolbar. Break layout throws the structure away so you can drag again. Spacers are a separate object users do not understand. Promoted widgets show the base class, so the canvas lies. The property editor cannot represent every type, and the documented escape is to open the XML. Plugins must match the Designer build, which is a C++ problem a Python app should refuse. None of that is a reason to abandon `.ui`. It is a reason to apply a layout as soon as a widget is dropped into a container, and to stop showing coordinates the layout owns.

**Layout confusion.** QML anchors plus layouts is the documented undefined mix. Lazarus Align, anchors, and ChildSizing override each other. Figma constraints do nothing inside auto layout, and Dev Mode then emits the absolute numbers. WPF's designer writes margins because the drag is in pixels and the file is a panel tree. Webflow combo classes make the base style look deleted. A builder picks box, grid, and form, labels them with those words, and disables the other geometry controls while a layout is active.

**Code-behind spaghetti.** VB6 stores the procedure in the same file as the coordinates, so a button move and a bugfix are one diff. WinForms splits the files and then puts the subscription on the wrong side of the split. Bubble's workflow strip is easy until the only way to understand a screen is to open twenty popups. Blueprint graphs do logic well and cannot be merged. Phase 2 for Code Studio should be a method in the form's Python module, or a short expression on a property. It should not be a node graph until a form actually needs one. Blockly can wait.

**Two products under one name.** Widgets Designer and Design Studio do not share a file. Unity uGUI and UI Toolkit do not share a hierarchy. Avalonia's MIT framework and its paid designer do not share a licence. Anvil's AGPL runtime and its closed editor do not share a repository. Marketing pages say "Qt" or "the designer" and mean the wrong one. Code Studio docs should say "widget layout file" and mean `.ui`.

**A preview that lies or dies.** WPF's artboard misses runtime styles and data. MAUI's Live Preview is screenshots and misses off-screen content. SwiftUI and Compose previews crash or freeze when the compiler falls behind. PAGE runs a separate generated module and the canvas can still be wrong. A preview that loads the same `.ui` through `QUiLoader` in another process will match the appliance, which is the only match that matters.

**Absolute coordinates as the product.** VB6 twips, PAGE place, Tkinter-Designer place, and Power Apps X and Y all produce a window that fits the author's screen. Delphi's Hacker News thread says the quiet part. People skipped resizable layouts because pixels were easier. ChoreBoy machines are not a single DPI. Phase 1 that saves only `geometry` will be thrown away.

**No exit.** Bubble cannot export an app. Framer cannot export the project. Builder.io cannot self-host the editor. A ChoreBoy app has to open from a folder on a USB drive with no account. The layout file has to be that folder.

**Licence traps.** Embedding Designer, Creator, or Design Studio pulls in GPL-3.0, and the output exception does not allow a tool that generates Designer's output. Current Scratch is AGPL-3.0-only. Slint's royalty-free licence forbids exposing its APIs, and the Python wheel does not run on 3.9 or 3.11. Pygubu's designer is GPL-3.0 and speaks Tk. Budibase's core is GPL-3.0 if you ship the builder. Cambalache is LGPL for the app and GPL for the tools, and it is a GTK program. None of these should be vendored into Code Studio. `QUiLoader` on the Qt 5.15 already in FreeCAD is the loader you already use.

## Open-source pieces you could study or reuse

Study means read the interaction. Reuse means the licence allows copying code into a closed or weakly copyleft desktop app. Confirm the file you vendor. "Or later" is stated only where the retrieved text says it.

| Piece | Licence as retrieved | Use |
| --- | --- | --- |
| Qt UI Tools, `QUiLoader`, Qt 5.15 | BSD-3-Clause since Qt 5.11, or commercial. <https://doc.qt.io/archives/qt-5.15/qtuitools-index.html> | Load `.ui` at runtime. Already the proven ChoreBoy path. |
| Qt UI Tools, Qt 6 | LGPL-3.0 or GPL-2.0 since Qt 6.0, or commercial. <https://doc.qt.io/qt-6.12/qtuitools-index.html> | Same loader after a FreeCAD 1.1 move. Matches PySide6's LGPL. |
| PySide6 | LGPL-3.0 or GPL-3.0, or commercial. <https://doc.qt.io/qtforpython-6/index.html> | The widget set. Not a reason to ship `pyside6-designer`. |
| QtPy | MIT. <https://github.com/spyder-ide/qtpy/blob/master/LICENSE.txt> | Optional import shim for the editor's own chrome. Do not use it to load promoted widgets. |
| Godot `Control`, containers, and the inspector docks | MIT. <https://godotengine.org/license/> | Read the container ownership rules and the theme lookup. The code is C++ and a different scene model. Do not port it. |
| Penpot | MPL-2.0. <https://github.com/penpot/penpot/blob/master/LICENSE> | Read the flex and grid controls and the token JSON. File-level copyleft if you modify its files. It is a ClojureScript design tool, not a widget editor. |
| Blockly | Apache-2.0. <https://github.com/google/blockly/blob/develop/LICENSE> | Phase 2 only, if you want blocks. One-way codegen. Fine inside a closed app if notices stay. |
| Node-RED core | Apache-2.0. <https://github.com/node-red/node-red/blob/HEAD/LICENSE> | Phase 2 reference for wires and a property sheet on a node. The editor is a browser app. Dashboard 2's licence was not retrieved. |
| Power Fx | MIT. <https://github.com/microsoft/Power-Fx/blob/main/LICENSE> | Phase 2 reference for value formulas versus action formulas. Studio is not included. |
| Anvil runtime | AGPL-3.0 plus an exception for apps loaded by the server. <https://github.com/anvil-works/anvil-runtime/blob/master/LICENSE> | Read `form_template.yaml` and the form class split. Do not vendor the runtime. The designer is not in the repo. |
| Pygubu core | MIT. <https://raw.githubusercontent.com/alejandroautalan/pygubu/master/LICENSE> | A reminder that the loader can be MIT while the designer is GPL. Wrong toolkit. |
| Appsmith Community Edition | Apache-2.0. <https://github.com/appsmithorg/appsmith> | Read the property pane and the `{{ }}` binding list. It is a server product. |
| Avalonia framework and the legacy previewer | MIT. <https://raw.githubusercontent.com/AvaloniaUI/Avalonia/master/licence.md> | Read the out-of-process preview protocol. The current pro designer is not MIT. |
| Lazarus designer | Designer directory GPLv2. <https://gitlab.com/freepascal.org/lazarus/lazarus/-/raw/main/COPYING.txt> | Read anchor sides. Do not copy the designer code into Code Studio. |
| Cambalache | App LGPL-2.1, tools GPL-2.0. <https://raw.githubusercontent.com/xjuan/cambalache/main/README.md> | Read the separate preview process and the "warn if the XML changed" behavior. GTK, not Qt. |
| Plasmic outside `platform/` | MIT. Studio is AGPL-3.0. <https://github.com/plasmicapp/plasmic> | Read the rule that generated files are never the hand-edited files. Do not vendor the studio. |
| Dear ImGui and Dear PyGui | MIT | Not a layout builder. Skip for this project. |
| Scratch editor and VM, 5.0 and later | AGPL-3.0-only | Do not link. Older trees were BSD-3-Clause. Check the commit if anyone proposes it. |

Do not vendor Qt Designer, Qt Creator, Qt Design Studio, Glade, PAGE, the Pygubu designer, Slint, FlutterFlow, or any Visual Studio designer.

## What Code Studio should build

Phase 1 is a widget layout editor for Qt Widgets. It writes a `.ui` file. It loads that file with `QUiLoader` in a second AppRun process. It does not embed Designer. It does not generate Python as the source of truth.

The interaction, if this product were new, would be the following.

Dropping a widget into a window that has no layout creates a top-level layout and puts the widget in it. Dropping into a box, a grid, or a form inserts a cell. The inspector shows spacing, stretch, and alignment. It does not show x and y while the layout owns the child. A command labeled Break layout exists for the rare case, and it asks first. That is Godot's rule on Qt's widgets.

The object tree uses the same names the Python module will use. Rename in the tree and the `.ui` `name` attribute changes. A Python file next to the form, which the designer never rewrites, can hold handlers. Phase 1 stores a connection as a signal name and a method name. Phase 2 may insert `def method_name(self):` if the method is missing, and then leave the body alone. That is Anvil's split on a `.ui` file instead of YAML.

Custom widgets are a small registry of class name, base class, and module. The file stores a `<customwidget>` promotion. The canvas draws the base class unless the registry imports the real class. Import failure shows the base class and an error in the problems panel. It does not require a C++ plugin or `PYSIDE_DESIGNER_PLUGINS`.

Theme is a project palette of a few roles, written as a style sheet or as widget properties that reference those roles. A screen does not start with forty local colors.

Save writes deterministic XML. Properties that equal the Qt default are omitted. The second save of an unchanged form matches the first. If the file on disk was edited and the editor does not recognize a part of it, the editor warns and does not rewrite that part. That is Cambalache's warning, aimed at the Glade failure.

Preview is Run, using the runner Code Studio already has. The editor does not keep a live `QUiLoader` tree inside its own process as the only check. A cheap in-process canvas can still draw the tree for dragging. The oracle is the other process. `docs/designer/ARCHITECTURE_PLAN.md` already says the save path is validated by `QUiLoader`. Keep that. Do not keep a long Designer-parity toolbar.

An assistant, later, may draft a `.ui` from a sentence or from a table schema. The draft is a normal file. Further drags do not call the model. Retool's "form from the selected record" is the non-AI version of the same idea and is enough for a first data-entry template.

What this rejects, on purpose. QML and Design Studio, because existing ChoreBoy apps are widgets, and Design Studio's file split and licence do not help phase 1. Slint, because the current Python binding does not run on 3.9 or 3.11, and the licence does not want you to expose the toolkit. A WinForms-style generated `setupUi` that users edit. A VB6-style single file. A Figma-like infinite canvas with constraints as the primary model. A node graph for clicks.

The prior branch that chased Designer parity can be discarded as an interaction model. Its choice of `.ui` plus `QUiLoader` should survive. Those are different decisions, and only the first one failed.

## Where the formats live

| Need | File | Loader you already have or would write |
| --- | --- | --- |
| Widget tree | `forms/name.ui` | `QUiLoader` in the runner |
| Hand-written behavior | `forms/name.py` | Normal import. The designer does not write this file except to append a missing stub in phase 2 |
| Theme roles | a small project file, or the top widget's style sheet inside the `.ui` | Qt style sheets |
| Custom widget map | `<customwidgets>` inside the `.ui` | A Python `createWidget` registry |
| Preview | the same `.ui` | Second AppRun process |

Qt's schema page is the map of the XML. <https://doc.qt.io/qt-6/designer-ui-file-format.html>. You do not need resources, button groups, or the full connection editor on day one. You do need `widget`, `layout`, `item`, `property`, and `customwidget`.

## Gotchas

PySide6 `uic` output uses Qt 6 enum names. PySide2 code will not accept it unchanged. Generate with the matching binding, or skip codegen and load at runtime. The considerations page is <https://doc.qt.io/qtforpython-6/considerations.html>.

`QUiLoader` connects signals by string signature and does not understand Python types such as `str` on a custom widget. <https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html>. Phase 1 connections should use Qt signals that already have C++ signatures, such as `clicked`. Custom Python signals can wait.

Promoted widgets need a header element that is a module path. QtPy does not follow that rule. Call PySide's loader yourself.

A `.ui` file from an untrusted USB stick is a security input. Qt's own Qt 6 page says a hostile file can deny service, deceive the user, or load a plugin. Preview it in the runner, not in the editor process.

Python plugins for Designer exist only in the PySide6 launcher, and only if that binary can be executed. On current ChoreBoy it cannot, because subprocess execution is limited to `/bin/sh`. That constraint is in `docs/DISCOVERY.md`.

FreeCAD 1.1 is expected to bring PySide6 and Python 3.11. The builder's file can stay `.ui`. The editor chrome must be written so it runs on PySide2 and on PySide6. QtPy can help the chrome. It should not help the loader.

Design Studio's Live Preview and MAUI hot reload are attractive and they are the wrong runtime. They assume a compiler and a deploy step Code Studio does not have. Loading the file you saved is the preview.

## Gaps in this survey

These items were not on a page opened during the research pass, or two sources disagreed.

- Full text of two Qt Reddit threads. The search snippets are linked above. The pages returned 403 or timed out.
- Whether Glade's property grid exposes GtkBuilder property bindings.
- Cambalache COPYING file body, so "or later" is unconfirmed. The README was retrieved.
- Delphi's current EULA and the Florence designer page. Direct fetches were blocked.
- Lazarus modified-LGPL exception text. The COPYING summary was retrieved.
- Which Appsmith canvas a new app uses in 2026.
- Whether Power Apps Studio currently loads hand-edited `.pa.yaml`, or only shows it.
- Anvil editor licence. The runtime licence is public. The designer is not in that repo.
- Slint wheels older than 1.18.1b1. The current wheel requires Python 3.12 or newer. Older `requires_python` values were not walked.
- Compose library SPDX. The licence file was not fetched.
- ImGui Designer and ImStudio licences. The GitHub pages did not return a README.
- FlowFuse Dashboard 2.0 licence.
- Unreal EULA text.
- A dedicated negative review of the Gambas form editor.
- Framer's legal entity name, and Yoga's licence text.
- Whether a hand-edited `.penpot` zip reimports.

None of those gaps change the phase 1 choice. The choice rests on the Qt exception, the Qt 5.15 UI Tools licence, the ChoreBoy loader test, and the repeated failure of generated code as a source of truth.
