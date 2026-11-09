# What users say about GUI builders

20 October 2026. Research only. No product repository was modified. The notes behind this report are in `notes/` next to this file.

This report is for the owner of the ChoreBoy Code Studio form builder, who has not used Qt Designer. It teaches the tools through short quotations. The builder under design saves a standard Qt `.ui` file, can generate `ui_*.py`, does not add a data-binding layer, and is meant to cover Designer feature parity for PySide6 on an offline Linux appliance.

The earlier checklist in `docs/form_builder/research/R3_designer_parity_checklist.md`, section "Where Designer's UX is weak", already records eleven Designer complaints. The market survey in `A_market_survey.md` already records which file each other tool saves. This report does not retell those documents. It adds user sentences fetched for this pass, then turns the repeated pains into interaction designs.

## Overview

A visual GUI builder lets a person place buttons and fields on a window, then saves a file the program can open later. Qt Designer is that tool for Qt Widgets. It is a separate window from the code editor. The window has four areas. A widget box lists buttons, labels, and layouts. A canvas shows the form. An object tree lists every widget. A property editor lists the selected widget's settings.

The file Designer saves is XML, named with a `.ui` suffix. PySide can load that file at runtime. A second tool, `pyside6-uic`, can also turn the file into a Python module. That module is generated. The next run of the tool replaces it. People who type inside the generated module lose that typing.

Designer does not start with a resizing layout. A new form is a blank rectangle. You drop widgets at pixel positions. Nothing follows the window edge until you run a layout command. That command is the moment most first-time complaints begin. The widgets jump. After that, drag handles often stop working, because the layout now owns the size.

Other builders that people still miss, especially Delphi, Visual Basic 6, and Windows Forms, start from the opposite habit. You drop a control and it is there. A double-click opens the click handler. Those tools also taught a bad habit. The position is often a pixel number, so the window fits the author's screen and then fails on another font or another monitor.

The Code Studio builder can keep Designer's file and refuse Designer's first gesture. The first drop should already be inside a layout. The Python file the person edits should be a different file from the generated module.

## Key concepts

**The form file.** `name.ui` is the file you reopen. It holds the widget tree, the layouts, the property values that differ from Qt's defaults, and the signal names.

**The generated module.** `ui_name.py` is a projection of the form file. `pyside6-uic` writes it. It has a class named `Ui_` plus the form class, with `setupUi` and `retranslateUi`. Editing it by hand fights the next generation.

**The logic module.** A separate Python file owns the methods. Designer does not write that file. Code Studio should follow the same split. A connection in the `.ui` file stores a signal name and a slot name. It does not store a method body.

**A layout.** `QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, and `QFormLayout` are the four layout classes a Widgets form actually uses. A layout sets each child's position and size. Pixel geometry on that child is then ignored at runtime.

**Size policy, stretch, and spacers.** These three are one system, shown as three different controls. The size policy says whether a widget wants to grow. Stretch is a number on a layout slot that divides extra space. A spacer is an empty item that eats space. Newcomers meet them as separate mysteries.

**Promotion.** A stock widget on the canvas stands in for a Python subclass. The `.ui` file stores the class name, the base class, and a header string. In C++ that header is a real header. In Python the same string is a module path with `.py` written as `.h`. Designer keeps drawing the base class.

**Preview.** Designer's preview (Ctrl+R) builds the form, not the application. A stylesheet, a file-path icon, or a promoted class can look right there and wrong in the app, or the reverse.

## How a person builds a form today

1. They open Designer or Qt Creator's Design mode and pick a main window or a dialog.
2. They drag buttons onto the canvas. The buttons stay where they were dropped.
3. They preview, enlarge the window, and watch the buttons sit in the corner.
4. Someone tells them to select the form and use Lay out vertically, or Ctrl+1.
5. The buttons jump. The drag handles stop resizing them.
6. They copy a button to make a second one. Designer says it cannot paste into a container that already has a layout.
7. The usual advice is to break the layout, paste, and lay the form out again. Sibling layouts can change size during the break.
8. Nested rows collapse into lines that are hard to hit. The object tree becomes the only reliable way to select them.
9. They set a minimum size to force a row to be visible. Setting it back to `0x0` does not mean "remove this setting."
10. They save, run `pyside6-uic`, and then either edit the generated Python or forget to regenerate it.
11. The editor offers no completion on the widgets if they used `loadUi` instead.
12. A custom widget needs Promote to, and the header field is filled in as if the project were C++.

That sequence is the product. Each step below is a complaint fetched from a person who was on one of those steps.

## Where the files live

| Need | File | Who writes it |
| --- | --- | --- |
| Widget tree and layouts | `forms/name.ui` | The form builder |
| Generated setup class | `ui_name.py` | `pyside6-uic`, on demand |
| Methods and application code | `forms/name.py` | The person, in the code editor |
| Icons compiled into the app | a `.qrc` file, then a Python resource module | The resource tool, not a free file path on a pixmap |

Checklist ids for this split are R3 items 15, 175, 181, 194, and 195.

## Gotchas

A `.ui` file from an untrusted folder is input. Preview it in another process. Qt's own Qt 6 UI Tools page says a hostile file can hang the process or load a plugin. That warning is in the market survey. This pass did not re-fetch that page.

`QUiLoader` connects signals by string names. A Python type on a custom signal is outside that mechanism. Phase 1 connections should use stock Qt signals such as `clicked`.

Reddit.com returned 403 to the research passes. Classic IDE quotations marked archive were copied from the PullPush archive of the comment body. They were not opened on reddit.com in the parent session. Four further Reddit lines in `notes/03_python_workflow.md` (P21 through P24) exist only as search snippets. They are unverified and are not used as evidence below.

Qt Creator's Quick Designer and Qt Design Studio edit QML, not Widgets `.ui` files. Crashes in those tools are labeled when they appear. They are not counted as Widgets Designer defects.

## How the rank number was made

The count below is a corpus count, produced by a script over `notes/*.md`. It is the number of distinct URLs from which a quotation was copied after a page fetch. It is not a percentage of Qt users, and it is not a count of bug-tracker votes.

The script found 187 quotations, all 25 words or fewer, across 146 distinct URLs, plus 4 snippet-only URLs that the script's quote pattern did not include because they are marked unverified. One URL, Hacker News item 20634100, appears in two note files. Per-file URL counts are 20, 23, 22, 26, 21, 16, and 21 before that duplicate is removed. The parent re-opened two of those pages and checked the words against the notes. Stack Overflow question 70736140 contains "Why does it need so much space to just have small buttons?" The Jira record QTBUG-113388 contains "Mode stays on Normal" for every enum, created 2023-05-04, status Closed. The other quotations are as the workers copied them from fetched pages. They were not each re-opened by the parent.

Rank uses two small integers, then a judgment.

- Band 1 means 1 or 2 distinct URLs in this corpus. Band 2 means 3 to 5. Band 3 means 6 or more. A thread already quoted in R3 can move a band up by one step, and the row says so.
- Severity 3 means the form is wrong, work is deleted, or the tool crashes. Severity 2 means a workaround exists and it is slow. Severity 1 means the step is annoying after you know the trick.
- Score is band times severity. Ties break toward the pain a person hits on the first form.

The limiter on these numbers is the search itself. English pages that loaded outrank Chinese, Korean, and closed-forum threads. Reddit was mostly blocked. A pain with one vivid bug report can still be severe. The score does not pretend otherwise.

## Layout

People place widgets, apply a layout, and lose the picture they just made. They also cannot put a widget back into a layout that already exists.

Frequency in this corpus is high. Twenty layout URLs are in `notes/01_qt_layouts.md`, and the beginner file adds more. Severity is high. The window does not resize, or the layout refuses the edit.

Bug records fetched for layout behavior are QTBUG-61439 (a tab widget refuses a grid span, Closed), QTBUG-62049 (undo writes a bad z-order, Closed, fixed in 5.9.3), QTBUG-3109 (custom layout plugins, still Reported since 2008), QTBUG-38288 (splitter handle invisible), and QTCREATORBUG-24876 (cannot drag widgets in design mode). No fetched bug covers the paste dialog. A snippet named QTBUG-35634 and was not opened. That id is unverified and is not used.

"to have them move a seemingly random amount when applying a layout is hugely frustrating." ChrisW, 2014-03-06, https://stackoverflow.com/questions/22231057/qt-designer-layouts-dont-respect-pre-defined-geometry

"especially when using the grid layout it puts the widgets in the most improbable places." Marco Martin, 2006-10-27, https://notmart.org/blog/2006/10/fighting_against_qt_designer_gri/

"Buttons that were in the corner will be left stranded in a sea of blank space." Murray Cumming, 2010-11-10, https://www.murrayc.com/permalink/2010/11/10/non-automatic-layout-is-useless/

"When using layouts, I also can't drag the edges of an individual widget to resize it within the window." Gnumbertester, 2021-09-12, https://stackoverflow.com/questions/69155079/qt-designer-moving-resizing-widgets-while-respecting-window-rescaling-pyqt5

"I cannot drag the line edit and button into the horizontal layout." Asperamanca, 2016-03-23, https://forum.qt.io/topic/65387/qt-forms-designer-baffled

"I cannot drag my Import Progress label widget or my progress bar widget into the new horizontal layout widget." Dan Nissenbaum, 2014-03-23, https://stackoverflow.com/questions/22597084/qt-designer-how-to-add-widget-to-a-layout-in-the-designer-when-the-layout-appea

"i do not want to break the layout. that's not a helpful suggestion." davecotter, 2019-05-18, https://forum.qt.io/topic/102942/qt-designer-copy-and-paste-drag-and-drop-with-option-key-for-duplicate

"Is there a way to get around breaking the entire page layout so I can past the box into one of the gird layout cells?" WhatIf, 2016-07-21, https://forum.qt.io/topic/69525/copying-combo-box-items-in-qt-designer

R3 already quotes the same paste error from a 2022 Qt Forum thread, and the break-layout resize from a 2018 thread. Those two are the third and fourth witnesses. They are not copied again here.

Maps to R3 items 18, 20, 21, 23, 34, 35, 36, 37, 38, 41, 44, and 52.

## Size policy, stretch, and spacers

This is the beginner wall. The form looks finished, the window grows, and the fields stay put or explode into empty space. The answers say "set a size policy" or "add a spacer." Those words are not on the canvas.

Frequency is high. Severity is high for a first form, because the person cannot tell a finished screen from a broken one.

No fetched bug is only about teaching size policy. Item 167 in the checklist is the property. Items 45, 46, 49, 50, and 51 are the controls.

"Why does it need so much space to just have small buttons?" Ryan Glenn, 2022-01-17, https://stackoverflow.com/questions/70736140/why-does-qt-designer-add-so-much-space

"when I enlarge the window, all items (lineedit, radiobutton, pushbutton) are on the fix position." sven, 2014-10-07, https://stackoverflow.com/questions/26231319/qt-designer-enlarging-the-window-does-not-replace-my-items

"the QFormLayout always stays at the size I set in Qt Designer." bastibe, 2011-05-18, https://stackoverflow.com/questions/6044836/how-to-make-a-qt-widget-grow-with-the-window-size

"But it is so flexible, that it nearly cannot be understood." Maxim Popravko, 2010-12-29, https://stackoverflow.com/questions/4553304/understanding-form-layout-mechanisms-in-qt

"But now I want to see difference between MinimumExpanding and Expanding policy." van9petryk, date not shown, https://forum.qt.io/topic/68415/how-qsizepolicy-work

"I didn't know setting the minimum size back to 0x0 was not the same as resetting it." William Hofsøy, 2021-09-23, https://stackoverflow.com/questions/69302139/designer-overlapping-issue

"I first thought that using the stretch settings would take care of this, but that doesn't seem to be the case." mzimmers, date not shown, https://forum.qt.io/topic/84199/adding-an-object-to-a-designer-made-ui

"I tried changing the spacer's settings and policies, but it doesn't do what I want." neuviemeporte, 2012-03-12, https://stackoverflow.com/questions/9670687/how-do-i-make-sense-of-all-the-widget-sizes-and-size-policies-while-designing-a

"When using fixed spacers in a layout, alignment is inconsistent." rdowell, 2023-07-21, https://forum.qt.io/topic/146883/layout-alignment-with-fixed-spacers-is-inconsistent-qt-5-15

"I cant do that by simply moving the spacer as it permamently stuck to the position." lukutis222, 2022-09-09, https://forum.qt.io/topic/139183/widgets-alignment-within-layout

The last quotation in the notes includes quote marks around the word stuck. The line above drops those marks so the sentence stays readable. The notes file has the verbatim line.

"However, I keep getting this error when I try to save." DouglinhasZN, 2020-03-17, https://forum.qt.io/topic/112653/qt-designer-this-file-contains-top-level-spacers

The error in that thread title is that the file contains top-level spacers.

## Splitters

Three fetched posts say a splitter cannot be nested, cannot be applied, or cannot be dragged. QTBUG-38288 says the handle can be invisible even in preview. R3 already notes that splitter stretch is a different control from box-layout stretch. Frequency is moderate. Severity is moderate. A workaround is to set sizes in code.

"I can't then add that layout to any other larger layouts." MattyZ, 2012-01-06, https://stackoverflow.com/questions/8758109/qtdesigner-adding-splitter-layouts-to-larger-layouts

"I cannot set Lay Out in a vertical/horizontal in Splitter." Mujo Osmanovic, 2012-05-08, https://stackoverflow.com/questions/10499942/disabled-splitter-in-qt-designer

"i cannot change the splitter position from within the form editor." Crinus, 2019-08-07, https://news.ycombinator.com/item?id=20634100

Maps to R3 items 39, 40, and 50.

## Discoverability and the look of the tool

Designer hides ordinary edits behind modes. Connecting a click is a different mode, reached with a function key. People who have used Visual Basic describe that as a step backward. Frequency is moderate across essays, and the tone is strong. Severity is moderate. The tool still works after someone teaches you the mode.

"Why for example do I need to toogle to a different mode (using a function key!) in order to add events????" Anonymous comment, 2005-06-01, https://www.osnews.com/story/10722/qt-4-designer-reviewed/

"Sadly QT designer is still a complete trainwreck that doesn't seem to have been updated in a decade." mardifoufs, 2023-11-23, https://news.ycombinator.com/item?id=38394156

"Qt's GUI designer is barely there and even something like wxFormBuilder for wxWidgets." badsectoracula, 2022-05-19, https://news.ycombinator.com/item?id=31421959

"I hope they fix QtDesigner to not be hot garbage." Crinus, 2019-08-07, https://news.ycombinator.com/item?id=20634100

Love sits next to that hate, often from the same years. The owner should hear both.

"Qt Designer is a great GUI tool that you can quickly prototype a GUI app." kbumsik, 2018-09-25, https://news.ycombinator.com/item?id=18067684

"Especially as layouts become nested, this is so much easier." Dave Mateer, 2010-11-06, https://stackoverflow.com/questions/4114389/qt-designer-vs-handcoding

"Writing all the code to draw a not very complicated window with tooltips, menu etc by hand is long and boring work." Mara, 2005-04-19, https://www.linuxquestions.org/questions/programming-9/do-you-use-qt-designer-315010/

The Mateer answer is the same Stack Overflow page R3 already used for custom widgets. The sentence here is the layout sentence, which R3 did not quote.

Maps to R3 items 1, 2, and 8. Buddy mode (items 8 and 9) had no fetched complaint in this pass.

## Property editing

The property editor is famous inside Qt for marking changed values in bold and for editing many selected widgets at once. This pass did not find a complaint about search, multi-select, or reset as a missing feature. It found the editor failing to commit enums, failing to show custom types, and treating `0x0` as a real minimum size.

Frequency is moderate. Severity is moderate for stock properties, and high when a plugin enum cannot be set at all.

Fetched bugs are QTBUG-113388 (enum stays on Normal, Closed), QTBUG-112682 (horizontal alignment has no effect, 2023), QTBUG-12889 (a header checkbox does not restore, 2010), and QTBUG-15497 (column widths in the property editor are not remembered, 2010).

"Mode stays on Normal. This is true for any enum property." QTBUG-113388, 2023-05-04, https://bugreports.qt.io/browse/QTBUG-113388

"Qt Designer has only editors for property types it knows." Qt Forum, date not shown, https://forum.qt.io/topic/3942/custom-q_property-not-showing-in-qt-designer

"I just can't seem to figure out how to make QtDesigner present the User with a Dropdown in the Property-Editor for Enumeration Properties." t0bias, 2020-05-18, https://stackoverflow.com/questions/61860564/how-to-make-qtdesigner-offer-enumeration-for-plugin-property

"Change text alignment to HRIght. Observe: No effect." QTBUG-112682, 2023-04-06, https://bugreports.qt.io/browse/QTBUG-112682

Maps to R3 items 146, 147, 149, 153, and 167.

## Custom widgets and promotion

A Python shop hits this as soon as a form needs one home-grown widget. Designer stores a C++ header. The canvas draws the base class. A real plugin must match the Designer build, and plugins abort the process.

Frequency is moderate. Severity is high. The canvas lies, or the tool does not start.

Fetched bugs are QTBUG-102028 (cannot place `QAbstractItemView`), QTBUG-14537 (morph `QTextEdit` to `QTextBrowser` by editing the file), QTBUG-67852 (promoted web view), and QTBUG-3109 (custom layouts).

"this is intended to work with C++ projects rather than Python ones." ekhumoro, 2022-05-30, https://stackoverflow.com/questions/72429693/pyqt5-using-loadui-with-promoted-widgets-from-qt-designer

"The loadUi implementation for PySide in qtpy doesn't appear to support this behavior." bpabel, 2017-04-25, https://github.com/spyder-ide/qtpy/issues/104

"ModuleNotFoundError: No module named 'QtWebEngineWidgets/QWebEngineView'." owillebo, 2023-03-10, https://github.com/spyder-ide/qtpy/issues/411

"right-clicking a custom widget does not show the promote to menu item." Tony Rietwyk, 2010-05-14, https://lists.qt-project.org/pipermail/qt-interest-old/2010-May/023250.html

"Qt designer started to crash on start with my plugin." Aleksey Kontsevich, 2016-03-12, https://stackoverflow.com/questions/35961043/qt-designer-crashes-with-custom-plugin

R3 already records that a promoted widget with runtime-only children collapses to a line. That complaint is not quoted again.

Maps to R3 items 55, 194, 195, 196, and 198.

## Python workflow

This is the part Designer never sees, and the part Code Studio's users will hit every save.

### Regenerating and editing the generated file

The generated file says not to edit it. People edit it anyway, because it is the only Python they were shown. The next generation deletes the edit. Forgetting to regenerate leaves the running app on the old form.

Frequency is high among Python posts. Severity is high. The loss is silent.

"That's a polite way of saying: you must never edit those files." musicamante, 2021-03-09, https://stackoverflow.com/questions/66544701/qmainwindow-object-has-no-attribute-addwidget

"pyuic generated files are not intended to be executed, and should not ever be manually modified." musicamante, 2021-09-06, https://stackoverflow.com/questions/69077280/converting-ui-file-into-py-using-pyside6

"you always must remember to regenerate the python files everytime you update an ui." musicamante, 2020-04-16, https://stackoverflow.com/questions/61257936/benefits-of-using-pyuic-vs-uic-loadui

An unverified Reddit snippet (P21, 2020-06-08) says the same thing about losing edits on regenerate. It is not evidence until the page is fetched.

### loadUi, uic, and QUiLoader

`loadUi` avoids the regenerate step and then hides the widget names from the type checker. `loadUiType` in a frozen app shells out to `pyside6-uic`. `QUiLoader` is the runtime loader and has its own promotion rules.

"I'm using loadUi, because I don't want to have to keep recreating the Python commands corresponding whenever I change my forms." Andy Brown, 2019-11-08, https://stackoverflow.com/questions/58770646/autocomplete-from-ui

"There is no autocompletion on this XXX." PyThagoras, 2020-02-20, https://stackoverflow.com/questions/60321203/get-autocompletion-with-pycharm-on-widgets-created-with-qtdesigner

"But no autocomplete is provided for it." Buzz, 2021-04-24, https://stackoverflow.com/questions/67242228/vscode-pylance-class-attributes-recognized-but-no-autocomplete-available

"I have tried several ways to exclude all auto-generated files from the mypy search." sebwr, 2023-07-14, https://stackoverflow.com/questions/76687462/is-there-a-way-to-ignore-mypy-call-to-untyped-function-setupui-in-typed-cont

"So the PySide functionality that involves spawning its entry-point scripts is inherently incompatible with PyInstaller and non portable." rokm, 2023-12-06, https://github.com/pyinstaller/pyinstaller/issues/8151

### Packaging the .ui file

People who keep the `.ui` and load it at runtime then discover the freezer did not bring the file.

"it is not feasible for me to keep converting them." giran, 2016-06-17, https://stackoverflow.com/questions/37888581/pyinstaller-ui-files-filenotfounderror-errno-2-no-such-file-or-directory

"FileNotFoundError: [Errno 2] No such file or directory: 'gui.ui'." pohmelie, 2016-02-16, https://github.com/pyinstaller/pyinstaller/issues/1826

"Everything works fine after manually adding the ui files, icons and the sqldrivers to the _main.dist and PySide6 dirs." kwiechen, 2022-01-02, https://github.com/Nuitka/Nuitka/issues/1351

### connectSlotsByName

`setupUi` connects slots whose names look like `on_objectName_signal`. A near miss prints a warning and connects nothing.

"QMetaObject::connectSlotsByName: No matching signal for on_modelosView_currentChanged(QModelIndex,QModelIndex)." Leandro M Barbosa, 2013-02-13, https://stackoverflow.com/questions/14856020/qt-4-8-4-cannot-connect-slot-to-qlistviewcurrentchanged-signal

That quotation is six tokens if the warning is one token, and the notes count it as 6 words. The warning string is the whole sentence the user sees.

### pyside6-designer itself

The standalone launcher is missing, or a plugin path stops it from starting. Code Studio should not depend on that binary. The appliance cannot usefully exec it. The quotations still matter, because they show where "use Designer for custom widgets" ends.

"bash: pyside6-designer: command not found." StarterKit, date not shown, https://forum.qt.io/topic/141554/pyside6-designer-launcher-is-absent

"but now designer can't start." Tim Tu, date not shown, https://forum.qt.io/topic/155021/how-to-add-plugins-to-pyside6-designer

"main.py crashes upon exit when the custom widget mechanism is used." Okko Willeboordse, date not shown, https://forum.qt.io/topic/142739/pyside6-crash-upon-exit-after-quiloader-load-with-custom-widgets

"I cannot run the executables contained in the packages, for example pyside6-designer." ZeeD, 2025-10-16, https://github.com/pdm-project/pdm/issues/3651

The notes have "for example pyside6-designer" without a comma. The line above adds a comma and is the worse copy. Use the notes line as the verbatim quote. Verbatim: "I cannot run the executables contained in the packages - for example pyside6-designer."

Maps to R3 items 7, 175, 181, 194, and 196.

## Styling

The style sheet editor is a text box with some helpers. It does not show which widgets a selector hits. A rule can look right in preview and fail in the app, or restyle children the author did not mean. QTBUG-66213 is a paint bug seen inside Designer, not a bug in the editor dialog. No fetched bug is about the editor itself.

Frequency is moderate. Severity is high when preview and the app disagree, because the person debugs the wrong layer.

"After changing and saving the sheet QT Designer fails to update the GUI." AlexanderAlexander, date not shown, https://forum.qt.io/topic/108792/qt-designer-failing-to-update-gui

"The current behaviour seems to make the Change styleSheet feature in Qt Designer useless." mjsmithers, date not shown, https://forum.qt.io/topic/105256/best-way-to-use-change-stylesheet-in-qt-designer

"Only the last part does not work in python app, but it works perfectly in the qt Designer preview mode." Arash Heidari, 2021-01-02, https://stackoverflow.com/questions/65539775/stylesheet-does-not-work-properly-in-pyqt

Maps to R3 item 176.

## Menus, toolbars, and actions

Actions have their own editor. The canvas will not take a normal widget on a toolbar, and signal mode does not stick a connection onto a menu action. Frequency is moderate. Severity is moderate. The workaround is to build the menu in Python, which splits one window across two tools.

"Toolbar support in Qt Designer seems to be a little unintuitive and limited." moodboom, 2011-07-18, https://stackoverflow.com/questions/6740770/is-there-a-way-to-define-a-qtoolbar-with-buttons-and-popup-menus-using-qt-design

"You cannot add widgets to the tool bar in Qt Designer, I'm afraid you'll have to do this from your code." Ivo, 2010-09-01, https://stackoverflow.com/questions/3618090/qtoolbar-is-there-a-way-to-add-qaction-to-a-qtoolbar-in-qtdesigner

"Designer doesn't allow to add basic actions to a QMenuBar." musicamante, 2022-10-14, https://stackoverflow.com/questions/74075435/linking-actions-to-menu-bar-in-pyqt-from-qt-designer

Fetched bugs are QTCREATORBUG-12243 (Mac cannot add menu items, 2014) and QTBUG-1267 (widgets on a toolbar, 2007). The second is old enough that the file format may have moved. Treat it as a historical complaint, and re-check the schema before promising toolbar widgets.

Maps to R3 items 134 through 141.

## Signals and slots

The connection editor is easy to miss, and a new row is easy to scroll past. One author tells readers to avoid Designer connections and call `connect` in code. Frequency is moderate. Severity is moderate.

"I am not sure what is the difference between these 2 options." ranshalit, date not shown, https://forum.qt.io/topic/78021/how-to-connect-signal-to-slot-in-qt-designer

"The icon seems a bit temperamental, so if it isn't activated for you, try clicking on various bits." Mithat Konar, date not shown, https://mithatkonar.com/wiki/doku.php/qt/wiring_up_signals_and_slots

The notes quote starts "The – icon". The dash there is the writer's mark for the delete icon. The sentence is about that button staying disabled.

"You added new connection in editor? You will not see it, it is somewhere on top or bottom, you must yet scroll to it." Serge K, 2017-01-02, https://lists.qt-project.org/pipermail/interest/2017-January/025592.html

QTCREATORBUG-6494 (2011, Closed) says dialog `accepted()` slots fire at the wrong time. That is a connection-semantics bug, not only an editor bug.

Maps to R3 items 2, 3, 4, 5, 6, and 7.

## Resources

An icon chosen as a file path can show on the canvas and vanish in the app, because `uic` stores a short path. A `.qrc` URL in a style sheet can also fail to paint. PyQt6 removed `pyrcc6`, so the Python resource step became a PySide tool plus a hand edit. Frequency is moderate. Severity is high. The screen is missing its icons.

"but search_icon.svg hadn't been displayed on QLineEdit." Tymofii Koval, 2020-04-29, https://stackoverflow.com/questions/61501595/how-to-use-qrc-resources-in-qss-in-qtdesigner

"don't trust Qt Designer, just add everything to .qrc." Max Cury, 2023-11-05, https://stackoverflow.com/questions/77427096/qpixmap-is-not-shown-when-run-application-in-qt

"Someone decided pyrcc6 wasn't useful and no longer provide it." panofish, 2021-02-08, https://stackoverflow.com/questions/66099225/how-can-resources-be-provided-in-pyqt6-which-has-no-pyrcc

No fetched Designer bug is about the resource browser. Nearby hits were build-system bugs and were not opened.

Maps to R3 items 164, 165, 174, and 175.

## High DPI

Sizes in Designer are pixels. A form laid out on a scaled display becomes huge, or overlaps, on another scale. Frequency is moderate. Severity is high on multi-monitor Windows. On a single appliance display the same mechanism still matters when the font size changes. Delphi's fans describe that older version of the same trap below.

"But once you launch it, the app appears 4-times as big." regs, date not shown, https://forum.qt.io/topic/77740/qt-designer-on-high-dpi-screens

"when you change size of the window in Qt Designer, or of any element, it is using absolute pixels." michnovka, 2016-02-27, https://stackoverflow.com/questions/35664684/how-to-work-in-qtdesigner-on-high-dpi-display

"I'm nearly certain that this is an issue caused by Windows display scaling." ArduinoBen, 2022-04-13, https://stackoverflow.com/questions/71852282/qt-designer-not-playing-nicely-with-windows-display-scaling

"Qt Designer, Creator and Assistant show the same problems becoming unusable when moving to a high DPI screen." QTBUG-48242, 2015-09-12, https://bugreports.qt.io/browse/QTBUG-48242

QTCREATORBUG-15600 (2016) says different parts of Creator scale differently. That one is the IDE shell, not only the form.

Maps to R3 items 18, 166, and 179.

## Crashes and large forms

Custom plugins and a few property edits abort the process. One Widgets form of more than 15,000 lines freezes for a second or two inside `setupUi`. That second report is runtime cost, not the editor feeling slow. A Design Studio report of five seconds per edit is QML and is listed so it is not confused with Widgets Designer. No fetched bug says a large `.ui` makes Designer itself unusable. QTBUG-118317 is a plugin startup hang.

Frequency of hard crashes in this corpus is moderate. Severity is high, because the form can be unsaved.

"every time I try to change my cursor style or define the frame shape of my frame, the app just crashes." João Amgarten, 2024-04-04, https://stackoverflow.com/questions/78276569/qt-designer-crashing-when-trying-to-change-cursor-style-on-macos

"I am experiencing crashes of the QT Creator after clicking on the design mode button." QTCREATORBUG-29700, 2023-10-04, https://bugreports.qt.io/browse/QTCREATORBUG-29700

"When calling setupUi function in my code, my application freezes for 1-2 sec." Quew, date not shown, https://forum.qt.io/topic/160228/fast-loading-of-complex-interfaces

QTCREATORBUG-7289 and QTCREATORBUG-11323 are Quick Designer crashes from 2012 and 2014. They are QML. KDE bug 345349 is an Oxygen rendering glitch, not the Qt tracker.

Maps to R3 items 33, 177, and 196.

## Tab order

One new post says the numbered overlay will not go away, because the menu checkmark is not the way out. R3 already records that a newly inserted widget is appended to the tab chain, and that reordering tab pages depends on a three-pixel drop bar. Frequency of new fetches is low. Severity is moderate.

"I cant find a way to hide the green numbers. Unchecking Edit Edit Tab Order does not work." Guglie, 2018-07-24, https://stackoverflow.com/questions/51502525/how-to-hide-tab-order-after-edit-in-qt-designer

No fetched bug is the tab-order tool. A snippet named QTBUG-69619 and was not opened.

Maps to R3 items 10, 11, 12, and 127.

## What people love, and what they warn us not to copy

### Delphi, Lazarus, and Visual Basic 6

The praise is the feeling that the form is the program. You drop controls. You double-click. You are in the handler. The warning, from the same thread, is pixel layout and a font size baked into the form.

"I feel like Delphi, along with maybe VB6 and WinForms, have been the pinnacle of easy UI development." FeistySkink, 2025-03-24, https://news.ycombinator.com/item?id=43462299

"Agree, Delphi was extremely nice way to do UI development." theamk, 2025-03-24, same thread.

"Maybe, but Delphi had anchor fields that you could use to make everything resize nicely." lelanthran, 2025-03-25, same thread.

"by default forms were specified in pixels, and were hard-coded to specific font sizes." theamk, 2025-03-24, same thread.

"Nobody else comes close to Delphi's visual form designer." JoseJimeniz, 2018-07-28, archive of https://www.reddit.com/r/delphi/comments/92d77o/why_i_used_still_use_delphi/

"I personally find the form designer and the anchoring is one of the best inventions since the invention of sliced bread." Bernd Kreuss, 2010-08-21, https://lists.lazarus-ide.org/pipermail/lazarus/2010-August/184926.html

"Anchors to me are same as (if not even more) confusing as the align method." Martin, 2010-08-21, same list thread.

"when dragging things around it hitches and lags, instead of a smooth drag action." phendrenad2, 2025-03-25, https://news.ycombinator.com/item?id=43462299

The VB6-specific fetch in this pass is a speed complaint, not a love letter. "The forms designer is very slow especially when moving form controls (textboxes, buttons etc.) to different areas of the screen." user1400158, 2012-07-12, https://stackoverflow.com/questions/11444646/vb6-ide-performs-too-slowly-on-windows-7-machine

The interaction to copy is the anchor picture and the double-click into a handler that lives in another file. The interaction to leave behind is pixel placement as the saved form.

### Windows Forms and the Visual Studio designer

Drag and drop, and double-click to the primary event, are the gestures people name. They also describe generated `InitializeComponent` as a file that must not be touched, a slow selection on a large form, and blue alignment lines one person wanted gone. This pass did not fetch a praise sentence for snaplines. The one sentence about those lines is hostile. Snaplines stay unverified as a delighter.

"You don't need to write any code, just drag&drop." Cbrt74088, 2021-01-18, archive of https://www.reddit.com/r/csharp/comments/kz9p41/what_do_you_think_of_winforms/

"The drag and drop interface makes ramping up easy." merklegroot, 2021-01-17, same thread, archive.

"I just double click on a button in the design view, which brings me straight to the code for that control's primary event." PaulOTron2000, 2014-07-28, https://stackoverflow.com/questions/25003852/very-slow-design-view-on-a-complex-form-with-a-lot-of-controls

"Creating events handlers double clicking is way worth the one in a while accidental double click." ManuelVene, 2024-06-01, archive of https://www.reddit.com/r/csharp/comments/1d4jr87/is_winforms_designer_a_mess_or_am_i_crazy/

"Double clicking UI controls and it automatically goes to the code behind is annoying." slightly_drifting, 2024-05-31, same thread, archive.

"you can set the handler to nothing, and if the handler was just created it will also remove the handler. Pretty handy." w0ut, 2024-05-31, same thread, archive.

"You should never modify .designer.cs. Period. Your changes will be overwritten without mercy." dahlbyk, 2013-04-23, https://stackoverflow.com/questions/16161994/manual-editing-of-designer-cs-file

"the act of selecting any control in the design view takes around 10 seconds before I can view its properties." PaulOTron2000, 2014-07-28, https://stackoverflow.com/questions/25003852/very-slow-design-view-on-a-complex-form-with-a-lot-of-controls

"this is one of the worst features I've ever seen any program have." GenoIsDead, 2022-03-04, archive of https://www.reddit.com/r/VisualStudio/comments/t6v5fa/removing_the_blue_lines_in_designer/

"In my opinion it's slightly better when it comes to auto-positioning controls in rows/columns." MaximumOctopus, 2018-07-29, archive of the Delphi thread above.

### WPF and Blend

Hand-edited XAML reopens. The drag gesture writes margins. Live editing is the part people praise. Blend is praised in one short line and blamed for crashes in others. Copy the live canvas. Do not copy a drag that stores a margin.

"However, live editing is absolutely awesome." chucara, 2021-03-23, archive of https://www.reddit.com/r/dotnet/comments/mbh77t/designing_layout_in_designer_vs_xaml/

"While the designer still adds hard-coded margins if you drag-and-drop." Ryan Lundy, 2009-01-30, https://stackoverflow.com/questions/497125/how-can-i-prevent-the-vs-wpf-designer-putting-margins-on-every-object-from-the-t

"It will add hard coded margins to everything." chucara, 2021-03-23, same dotnet thread, archive.

"the designer sets crazy margins, wrong rows or columns in grids." StackedLasagna, 2019-02-06, archive of https://www.reddit.com/r/dotnet/comments/ank70l/visual_c_wpf_what_do_the_lines_and_handles_do/

"Way better than the vs designer." scherlock79, 2017-08-23, archive of https://www.reddit.com/r/dotnet/comments/6vjozo/ive_reverted_from_wpf_to_winforms_because_the/

"If I try to add a DataGrid, the Blend 4 crashes." Kovács Gábor, 2011-10-03, https://stackoverflow.com/questions/7640976/datagrid-crushes-expressionblend-4

### Godot 4

A container parent owns the child. People call that a relief, and they also say a child of a container cannot be moved. Size flags are the same idea as Qt size policy, and beginners do not know them either. The theme object is loved. The theme editor is not.

"The 2D framework, especially for UI, is pretty awesome." numlock86, 2023-07-06, https://news.ycombinator.com/item?id=36614529

"Between those two nodes you can create 90% of UIs you'd want to." nkrisc, 2024-09-08, https://news.ycombinator.com/item?id=41483661

"Godot's visual editor is very intuitive: Anchoring, creating containers, rapid prototyping becomes a breeze." Popcar, 2024-03-13, https://popcar.bearblog.dev/using-godot-for-gui-app-development/

"Direct children of containers can't be moved or animated." Popcar, same page.

"One really good thing about Godot Ui is the StyleBox which simply allows coders to make rounded rectangles." nightowl_games, 2023-07-06, https://news.ycombinator.com/item?id=36614529

"The biggest issue, I think, is that the theme editor is awkward to use and definitely not as powerful as something like CSS." Popcar, same blog.

"It seems I could need some help to understand what SizeFlags is actually suppose to do." alex_sand, 2021-05-21, https://godotforums.org/d/26335-some-help-to-understand-sizeflags

"Every time I run the app, I see something different from what I can see in the editor." Sherlock Holmes, 2021-01-26, https://stackoverflow.com/questions/65903039/gui-elements-wont-keep-size-and-position

### Figma auto layout

Hug, fill, and a gap you can select are the interactions to copy, under Qt's names. Absolute position inside an auto-layout frame is also praised. That second geometry is how Designer produces a picture that runtime will ignore. Do not add it.

"Each item can either hug its contents, have a fixed width, or grow." bbx, 2025-07-07, https://news.ycombinator.com/item?id=44479502

"The gap between them was also not a value: it was just space that wasn't used, so you couldn't interact with this gap." bbx, same thread.

"Things like auto layout, component variants, nested instances, global variables are just fantastic to use." bbx, 2024-05-01, https://news.ycombinator.com/item?id=40218463

The notes include an ellipsis inside that sentence. Verbatim: "Things like auto layout, component variants, nested instances, global variables… are just fantastic to use."

### Android Studio and ConstraintLayout

This pass fetched complaints, not praise. Infer-constraints moves the views you placed. `0dp` does not mean "take the free space" to a beginner. The editor stops accepting constraint handles. Do not make constraints the Qt form model.

"It is supposed 0dp mean all available space." lm2a, 2022-12-30, https://stackoverflow.com/questions/74960662/constraint-layout-0dp-match-constraint

"But when I did it, those views in my program changed badly." Aiming for Moonshot, 2017-07-08, https://stackoverflow.com/questions/44983456/strange-consequence-when-use-constraint-layout-in-android-studio

"The editor is not letting me move views around, connect views with chains/constraints ..etc." Snake, 2019-04-17, https://stackoverflow.com/questions/55718820/androidx-constraintlayout-is-unresponsive-with-android-studio

### Xcode Interface Builder and SwiftUI previews

People miss a design surface that is separate from the code, and they mention a preview that instantiates views in another process. They also say Interface Builder previews were abandoned, and that SwiftUI previews get turned off.

"I miss the days when Apple actually cared about Interface Builder." ObjC4Life, 2023-08-05, https://mjtsai.com/blog/2023/08/03/building-testing-and-scaling-with-swiftui/

"and that too compiles, instantiates and renders off-process the views, before displaying them in IB." Leo, 2023-08-05, same page.

"So instead of repairing a quite useful feature, it was just abandoned by Apple." Lego Esprit, 2023-02-17, https://stackoverflow.com/questions/75486264/ibdesignable-preview-in-ib-again-broken-under-xcode-14-2-on-m2

"Even when I'm working with SwiftUI, I have to turn previews off." Steve Troughton-Smith, 2023-08-03, https://mjtsai.com/blog/2023/08/03/building-testing-and-scaling-with-swiftui/

### Glade and Cambalache

Glade is remembered as the right workflow and as a crashy, abandoned editor that rewrites files. Cambalache's author built preview in another process on purpose. Users also report a minute-long freeze, a grid that would not accept a widget, and a file that cannot come back after a hand edit.

"It was the workflow I dreamed." marcodiego, 2023-04-19, https://news.ycombinator.com/item?id=35630681

"Glade became something of a monstrosity of technical debt, slow, crash-prone and buggy but it worked." marcodiego, same thread.

"one of the main design goals was to create all the preview widgets in a separate process." Juan Pablo Ugarte, 2025-09-15, https://blogs.gnome.org/gtk/2025/09/15/casilda-1-0-released/

"Cambalache has been pretty bug-free for me." Dan Kasak, 2023-04-21, https://discourse.gnome.org/t/gtk3-to-gtk4-ui-migration/14998

"when I add widget or change anything it freezes for a minute to apply the operation." konceptosociala, 2023-04-19, same thread.

"if you make changes to the UI file it's very difficult or even impossible to use those changes in Cambalache again." zorr, 2023-04-19, https://news.ycombinator.com/item?id=35630681

### Anvil

Placement inside nested containers is the pain. The repairs people ask for are specific. Drag the row in the component tree. Edit column sizes as numbers. A modifier key makes resize usable.

"My principle issue is imprecise widget placement, especially inside containers." david.wylie, 2022-02-16, https://anvil.works/forum/t/make-the-form-designer-slightly-less-wysiwyg/11555

"Trying to get components inside the right container is super annoying!" jshaffstall, 2022-02-16, same thread.

"More than once I've wanted to be able to drag components inside the dropdown that shows the hierarchy." jshaffstall, same thread.

"The control + really makes a huge difference as did the column panel!" t.trindade.mendes, 2022-04-10, https://anvil.works/forum/t/am-i-doing-this-wrong-form-design-alignment/12202

"I would love to be able to set the column sizes from the property panel, but it's impossible." stefano.menci, 2022-04-10, same thread.

## Beginner pain, across layout tools

The same confusion shows up under different names. Qt calls it size policy and stretch. Godot calls it size flags. Android calls it `0dp`. WPF starts one step earlier. A window has one child, and a newcomer stacks a grid and a stack panel as if both were the window.

"i try to understand the play between layouts and widgets." andy72, date not shown, https://forum.qt.io/topic/54523/understand-layouts-and-widgets

"I am new to WPF and i can not figure some things out." The_Monster, 2013-10-28, https://stackoverflow.com/questions/19629643/wpf-issues-with-stackpanel

The Qt beginner quotations are in the size-policy section above. The practical reading for the owner is this. A first session needs words on the canvas, not three property names. Hug, fill, and fixed can be the words. The file can still store a `QSizePolicy` and a stretch integer.

Essays that tell beginners to skip Designer are real, and so are essays that call hand layout boring. Rob Galanakis, 2014-08-25, wrote "I absolutely discourage the use of the Qt Designer for creating production GUIs with Python." https://www.robg3d.com/2014/08/geocities-and-the-qt-designer/ Kustaa Nyholm, 2010-09-06, wrote "it is more bother and than it is worth." https://lists.qt-project.org/pipermail/qt-interest-old/2010-September/027285.html Ankur Sethi, 2008-12-22, wrote "writing the code by hand was conceptually simpler than using Qt Designer." https://stackoverflow.com/questions/387092/hand-coded-gui-versus-qt-designer-gui

Those authors are describing the gesture and the generated file, not the `.ui` format. A builder that applies a layout on drop, and that never asks the person to edit `ui_*.py`, is aimed at the sentence they wrote.

## Ranked pains and the fix

Score is band times severity, defined above. The design line is the interaction. The test is what a reviewer can watch. Checklist ids are from R3.

| Rank | Score | Pain |
| --- | --- | --- |
| 1 | 9 | Widgets sit still until a layout command, and that command jumps them. |
| 2 | 9 | Size policy, minimum size, and stretch read as three mysteries. |
| 3 | 9 | Paste is refused inside a layout. Band raised by the R3 thread. |
| 4 | 6 | Nested layouts shrink to a line you cannot drop on. |
| 5 | 6 | Break layout is the documented way to edit, and it resizes siblings. |
| 6 | 6 | Edits in `ui_*.py` disappear on the next generation. |
| 7 | 6 | Promotion stores a C++ header and draws the base class. |
| 8 | 6 | The style sheet on the canvas is not the style sheet in the app. |
| 9 | 6 | An icon shows in Designer and is gone at runtime. |
| 10 | 6 | A packaged app cannot find the `.ui` file. |
| 11 | 6 | A custom-widget plugin aborts Designer or the loader. |
| 12 | 6 | Sizes are raw pixels, so a font or a scale change blows the form up. |
| 13 | 6 | Modes and a dated canvas make people leave the tool. |
| 14 | 4 | Spacers stick, disagree with preview, or forbid a save. |
| 15 | 4 | The code editor cannot complete widget names. |
| 16 | 4 | Signal mode hides new connections. |
| 17 | 4 | Menus and toolbars do not take the control you dragged. |
| 18 | 4 | Enum properties do not commit. |
| 19 | 4 | A splitter cannot be nested, and its handle does not move. |
| 20 | 4 | Tab order sticks on screen, and new widgets join at the end. Band uses R3. |
| 21 | 4 | One grid drag moves cells you did not touch. |
| 22 | 2 | `connectSlotsByName` misses a slot that looks right. |
| 23 | 2 | A huge form freezes inside `setupUi`. |
| 24 | 2 | Undo writes a z-order entry that is not a widget. |
| 25 | 2 | Rename in the object tree steals the keyboard. Evidence is R3 only. |

**1. Layout on drop.** Dropping the first widget onto an empty form creates a vertical layout and puts the widget in it. The canvas frame can be dragged wider, and the widget follows. While a layout owns a child, the inspector hides x and y. R3 items 18, 35, 36, 37, 38, and 186. Test. New form, drop one button, drag the form wider, save. The XML has a layout and no `geometry` on the button. Undo returns to an empty form.

**2. Three size words.** Each child shows Hug, Fill, or Fixed. Stretch is a number on the layout slot, drawn on the gap. Reset on minimum size deletes the property. It does not write `0`. R3 items 45, 49, 50, 51, 146, and 167. Test. Set a minimum size, press Reset, save. The XML has no `minimumSize`. Two buttons in a column, Fill and stretch 1 on the second. Widen the form. The second button grows. The first stays at its text width.

**3. Paste into the layout.** Copy a widget. Select a neighbor or the layout. Paste inserts at that index, or at the end if the layout itself is selected. There is no error dialog. The object tree keeps the new widget selected. R3 items 23, 27, and 41. Test. A vertical layout of three buttons. Copy the middle one and paste. Four buttons. The new one is selected. Undo restores three. The scratch pad can stay for people who want a reusable copy. It is not the only paste path.

**4. Rows you can hit.** A layout draws every row and column at least 24 pixels tall, including an empty cell. The drop highlight names the index. Dragging a row in the object tree reorders that index. R3 items 20, 21, 28, and 44. Test. A horizontal layout nested in a vertical layout accepts a dropped line edit. Neither layout is broken. The tree order matches the visual order.

**5. Break layout asks first.** The command is present, because parity includes it. It confirms. Sibling layouts keep their sizes. Undo restores the broken layout in one step. R3 items 34 and 41. Test. Two horizontal layouts. Break the first. The second keeps its width. Undo puts the first layout back.

**6. Generation never owns the logic file.** The builder saves `.ui`. Generate writes `ui_*.py` into a generated folder and refuses to run if that file has unsaved user edits. Double-click a button opens `forms/name.py`. If the slot function is missing, the builder may insert a `def` and an empty body, once. It does not rewrite a body that already has lines. R3 items 7 and 181. Test. Put a comment in `forms/name.py`. Change the form. Generate again. The comment is still there. Put a comment in `ui_*.py`, leave it dirty, and generate. The command stops and names the file.

**7. Promotion is a Python module.** The dialog asks for class, base, and module. The canvas draws a box at least 80 by 24 pixels with the class name on it. No plugin project is required. A failed import in the preview process shows the box and an error. The editor stays up. R3 items 166, 194, 195, and 196. Test. Promote a `QWidget` to `myapp.widgets.Meter`. The saved header is the module path Designer already expects, with `.py` written as `.h`. A preview process imports it. A class that raises in `__init__` shows the error and does not kill the editor.

**8. Style sheet matches the form.** The editor lists object names the selector hits before OK. Apply repaints the canvas without a restart. Preview uses the same loader as the app. R3 item 176. Test. A rule for `QPushButton#okButton` colors that button. A selector that matches nothing is marked "no match" and can still be saved. Reopen the form. The color is still on that button.

**9. Icons come from the resource file.** A pixmap property offers resource aliases. A bare filesystem path is rejected at save, with the path still visible so the person can fix it. R3 items 164, 165, 174, and 175. Test. Save is blocked while a pixmap is a raw path. After the icon is in the `.qrc`, the canvas and a `QUiLoader` preview both show it.

**10. The package list includes the form.** The project screen that builds the app lists every `forms/*.ui` the code loads. A missing file fails that build. R3 item 175 is the resource cousin. There is no checklist id for PyInstaller. Test. A fixture project loads `forms/login.ui`. The package step fails when that file is removed from the manifest, and passes when it is present. This test needs a packager fixture. It is not a canvas test.

**11. Preview is another process.** Custom widget code runs there. A crash or a raised exception becomes a row in the problems list and a placeholder on the canvas. R3 items 177, 196, and 198. Test. Kill the preview process. The editor still accepts a rename. Restart preview. The form returns.

**12. Font preview, not pixel geometry.** A control on the canvas sets the preview font size. Laid-out children store no pixel geometry. R3 items 18, 166, and 179. Test. Toggle the preview between 10 point and 16 point. The layout reflows. The saved XML for those children has no `x` or `y`.

**13. One editing mode for ordinary work.** Connections, buddies, and tab order are lists in the inspector, available without a mode key. The canvas stays in widget mode. R3 items 1, 2, 8, and 10. Test. Add a `clicked` connection while a button is selected. The canvas tool does not change. The new row is selected.

**14. Gap is a number.** Layout spacing is a handle between children, and a number in the inspector. The "content size" command on a group sets stretch to 0 and alignment to the visual center, which is the spacer-free way to stop a login form from growing. Spacers remain available. R3 items 45, 46, 47, and 48. Test. Two fields and a button. Run content size. Preview the form at 800 pixels tall. The group stays near its text height. Save and reload. The spacing number is unchanged.

**15. Names complete in the logic file.** Saving the form writes a stub the type checker reads, listing each object name and its class. The person does not edit the stub. Rename updates it. R3 items 28 and 29. Test. A button named `okButton` completes as `self.okButton` in `forms/name.py`. Rename it to `saveButton`. The old name is gone from the stub. This test needs the editor's language server, or a generated `.pyi` opened by the same checker the team uses.

**16. Connections are a normal list.** Add, and the new row is selected. Delete removes it. Inherited slots are shown. The signature is checked before save. R3 items 3, 4, 5, and 6. Test. Add a connection. It is visible without scrolling past it on purpose. Delete it. The `<connection>` element is gone. A slot whose arguments do not match the signal is listed in problems.

**17. Actions drag onto menus and toolbars.** Type Here stays, because people already know it from Designer. An action in the action list drops onto a menu and onto a toolbar. A connection uses the same inspector row as a button. R3 items 135 through 141. Test. Create Open. Drop it on File and on the toolbar. Save. Both references are in the XML. Reload. The action is in both places. Toolbar widgets that the `.ui` schema cannot store are refused with a sentence, not a silent drop.

**18. Enums commit or stay dirty.** An enum is a dropdown. If the control does not accept the value, the row stays marked and Save explains why. Unknown property types are shown read-only. They are not omitted. R3 items 146, 149, and 153. Test. Set `echoMode` to Password. Save. Reload. It is Password. A property type the editor cannot change is still present in the XML after save.

**19. Splitter handle and stretch.** The handle is an 8 pixel target. Stretch uses the same slot control as a box layout. A splitter can sit inside another layout. R3 items 39, 40, and 50. Test. Two lists in a vertical splitter inside a horizontal layout. Drag the handle. Save. Reload. The sizes match the drop.

**20. Tab order follows the picture.** A new widget is inserted between its neighbors in reading order. The number overlay is a mode of the list, and Escape leaves it. Page reorder uses the object tree, with a drop marker wider than a few pixels. R3 items 10, 11, 12, and 127. Test. Insert a line edit between two existing ones. The tab list matches visual order. Escape clears the numbers. Move a tab page in the tree. The page order in the XML matches.

**21. Grid drop shows the cell.** The highlight shows row, column, and span before the drop. Other items stay put until then. R3 items 51 and 52. Test. Move a button from cell 0,0 to cell 1,2. Only that item's row and column change. Undo restores 0,0.

**22. Slot names are checked.** `on_object_signal` is compared to a real signal before save. R3 item 7. Test. A misspelled signal is a problem row. `on_okButton_clicked` for a real `QPushButton` is clean.

**23. Large forms stay editable.** Opening a fixture of 400 rows paints a first screen and allows a selection. The runtime check loads the same file with `QUiLoader` in the preview process. R3 item 177. This pass has one user report of a 1 to 2 second freeze inside `setupUi`, and no measurement of Code Studio. Do not treat any millisecond budget as a result. The test records the time. It does not assert a number until a baseline exists.

**24. Z-order follows the child list.** Undo of a reparent rewrites order from the widgets that are actually children. R3 items 32 and 33. Test. Repeat the steps in QTBUG-62049. Save. No `<zorder>` entry names a spacer.

**25. Rename keeps the keyboard.** The name field holds focus until Enter or Escape. A status message does not move focus. R3 item 28. The only quotation is the May 2025 Reddit comment already in R3. This pass did not re-fetch that page. Test. Rename ten widgets from the tree with the keyboard only. Focus is in the name field for each of them.

## Fifteen interactions to adopt

These are gestures people praised, translated into a `.ui` file. Each one is a delighter on top of the ranked fixes. Where a praise would create a second geometry system, it is listed after this set and left out.

1. **Drop, and it is placed.** WinForms users praise drag and drop as the way a newcomer starts. C37, C39. In our builder the drop lands in a layout cell, not at a raw pixel.
2. **Hug, fill, and fixed.** Figma users praise those three words. bbx, 2025-07-07. Store them as size policy presets.
3. **A gap you can select.** The same Figma comment says a gap that is only leftover space cannot be edited. Store it as layout spacing.
4. **Anchors drawn on the window.** Delphi and Lazarus users praise anchor fields. lelanthran, 2025-03-25, and Bernd Kreuss, 2010-08-21. Draw the layout's attachment to the form edge. Do not add a second anchor algebra on top of Qt layouts.
5. **Double-click opens the handler, and undo removes an empty one.** PaulOTron2000 and w0ut praise this. slightly_drifting and Jon Coombs describe the accidental double-click. The click inserts a slot name and, if needed, an empty `def` in the logic file. Undo removes that `def` only when the body is still empty.
6. **The hierarchy can reparent.** Anvil users ask to drag inside the component tree because the canvas drop is unreliable. jshaffstall, 2022-02-16.
7. **Column sizes are numbers.** stefano.menci, 2022-04-10, asks for this in the property panel. Grid minimums and stretches already have a home in R3 items 51 and 52. Show them as numbers next to the column.
8. **A modifier key for small steps.** t.trindade.mendes, 2022-04-10, says the modifier made column resize usable. Use it for spacing and for splitter position.
9. **Preview in another process.** Juan Pablo Ugarte states this as a design goal. Leo praises the same shape in Interface Builder. A widget that aborts must not take the editor with it.
10. **Live canvas, same file.** chucara calls live editing awesome. The canvas writes the `.ui` file directly. There is no second markup language to reconcile.
11. **Rows and columns that receive the next control.** MaximumOctopus praises Visual Studio when it auto-positions into rows and columns. The next drop goes into the next free cell, and the cell highlight shows where.
12. **A theme object for the common shapes.** nightowl_games praises Godot's StyleBox for rounded rectangles. Offer a few named roles on the form. Do not start from a color on every label. Popcar's complaint about the theme editor is the warning. Keep the role list short.
13. **A custom component with a real size.** The inverse of the promoted-widget line. The placeholder shows the class name and a minimum hit size. Figma's component variants are the praise (bbx, 2024-05-01). The Qt version is a promoted class or a nested `.ui`, not a second variant format.
14. **Reset that deletes the line.** WinForms users praise clearing a handler that was only just created. Do the same for any property that equals the Qt default. Reset removes it from the file.
15. **Auto layout as the default, with an escape.** Godot users praise containers and also say a child cannot be moved. Keep Break layout, behind a confirm, so the escape exists. The default path never needs it.

Praised, and not adopted as a second system.

- Pixel placement as the saved form. theamk says Delphi forms were hard-coded to font sizes.
- A drag that writes margins. Ryan Lundy and chucara describe WPF doing this.
- Absolute position inside a layout frame. karaterobot praises it in Figma, on 2025-07-08, in the same thread as the hug and fill comment. In Qt that gesture is the geometry the layout will ignore.
- Snaplines. This corpus has a hostile sentence and no praise sentence. Leave them out until someone fetches a praise quote.
- In-process SwiftUI-style previews. Steve Troughton-Smith turns them off.

## What R3 already covered

These eleven are documented in the checklist section "Where Designer's UX is weak", with URLs. This report uses them as prior evidence and does not copy their quotations.

| Prior complaint | Rank here | R3 items |
| --- | --- | --- |
| Paste refused | 3 | 23, 27, 41 |
| Break layout resizes siblings | 5 | 21, 34, 41 |
| Nested layout hit target | 4 | 20, 21, 28, 44 |
| Splitter stretch hidden | 19 | 39, 40, 50 |
| Tab page reorder is a thin drop | 20 | 127 |
| New widget appends to tab order | 20 | 10, 12 |
| Promoted widget collapses | 7 | 166, 194 |
| Child order disagrees with the picture | inside rank 4's test | 32, 119, 266 |
| Custom widgets need a plugin, wizards are awkward | 7 and 11 | 7, 121, 194, 196 |
| Rename steals focus | 25 | 28 |
| Style sheet editor does not show matches | 8 | 176 |

Child order and wizards did not get a new quotation in this pass. The rank 4 test still requires tree order to match visual order. Wizard pages remain R3 item 121. No new user sentence was fetched about `QWizard`.

## Methods

Seven web research passes wrote `notes/01_qt_layouts.md` through `notes/07_beginners_blogs.md`. Each pass was told to fetch the page, copy 25 words or fewer, and mark a snippet as unverified. The parent counted URLs with a script. The parent re-opened Stack Overflow 70736140 and the Jira JSON for QTBUG-113388.

Pages that did not load are gaps, not silent agreements. Reddit.com returned 403. Classic IDE Reddit lines are archive copies. Python notes P21 through P24 are unverified snippets. YouTube comments were not accessible as stable text in this pass. No YouTube quotation is used. bugs.kde.org does not mirror the Qt Designer tracker. One KDE rendering bug was fetched and is not treated as a Designer defect.

Dates are the dates printed on the fetched page or in the notes. "Date not shown" means the worker's fetch did not include one. Those are not guesses.

A sentence in the styling and property sections was lightly punctuated when this file was drafted. The notes files hold the verbatim line. Where this file and the notes disagree, the notes win, and the known slip is the ZeeD quotation, corrected above to the hyphenated notes line.

## Source index

The index is generated from `notes/*.md` by the check script recorded in the verification section of the session. Every URL under a `## ` heading in those notes is a primary source for this report.
