# Qt Designer 6.8 feature inventory

Parity checklist for a ChoreBoy Code Studio form builder whose saved file is a normal Qt `.ui` document. The target runtime is FreeCAD 1.1 only. That stack is PySide6 6.8.x, Python 3.11, and Qt 6.8. This inventory is the list a builder can be planned and tested against.

The person who uses the builder is a shop user laying out a window that will run under FreeCAD AppRun. The next engineer inherits a checklist, a file format, and a set of Designer behaviors that are easy to miss because they live in context menus rather than in the widget box.

## Scope and how this was measured

Two document versions are in play, and they are not the same thing.

The behavior source for FreeCAD 1.1.3 is Qt 6.8.3. On this Mac, `/Applications/FreeCAD.app` reports PySide 6.8.3. `libQt6DesignerComponents.6.8.3.dylib` and `libQt6Designer.6.8.3.dylib` are present. `Designer.app` is at `/Applications/FreeCAD.app/Contents/Resources/lib/qt6/bin/Designer.app`. Designer was not launched. The widget box resource inside `libQt6DesignerComponents.6.8.3.dylib` is zstd-compressed. Decompressing it with FreeCAD's `backports.zstd` yields 34,085 bytes. SHA-256 is `9383517de8494cb216f23102a2c02d2e2a8f34c2edf49022fdc0265689b950e4`. That hash matches `widgetbox.xml` from the `qttools` tag `6.8.3`. Command names were also taken from strings in the same library, and several save paths were read in `qdesigner_resource.cpp` from that tag.

The public manual at `https://doc.qt.io/qt-6/qtdesigner-manual.html` was fetched on 2026-10-20. Every page's chrome says Qt 6.12. Where the 6.8 source and the current manual disagree, both are quoted. A claim that was not opened in a file, a string dump, or a fetched page is marked unverified.

Primary files, all from the `qttools` git branch `6.8`:

- Schema: `https://raw.githubusercontent.com/qt/qttools/6.8/src/designer/data/ui4.xsd`. The path the brief named, `src/designer/src/lib/uilib/ui4.xsd`, returns 404 on that branch. The schema lives at `src/designer/data/ui4.xsd`. The downloaded file is 27,742 bytes and 558 lines.
- Widget box: `https://raw.githubusercontent.com/qt/qttools/6.8/src/designer/src/components/widgetbox/widgetbox.xml`. The root element is `widgetbox` version `4.2`. That version is the catalog version, not the `.ui` version.
- Form templates: `src/designer/src/lib/shared/templates/forms/` on the same branch.
- Actions: `src/designer/src/designer/qdesigner_actions.cpp` and `qdesigner_actions.h` on the same branch.
- Morph rules: `src/designer/src/lib/shared/morphmenu.cpp` on the same branch.
- Form Settings dialog: `src/designer/src/components/formeditor/formwindowsettings.ui`.
- Grid panel: `src/designer/src/lib/shared/gridpanel.ui`.
- Device profile dialog: `src/designer/src/components/formeditor/deviceprofiledialog.ui`.

Local commands and the results that matter:

```text
/Applications/FreeCAD.app/Contents/Resources/bin/python -c 'import PySide6, PySide6.QtDesigner; print(PySide6.__version__)'
6.8.3

strings in libQt6DesignerComponents.6.8.3.dylib include
Edit Widgets, Edit Signals/Slots, Edit Buddies, Edit Tab Order,
Lay Out Horizontally, Lay Out Vertically, Lay Out in a Form Layout,
Lay Out in a Grid, Lay Out Horizontally in Splitter,
Lay Out Vertically in Splitter, Break Layout, Adjust Size,
Si&mplify Grid Layout, Form Settings, Preview, View C++ Code, View Python Code

PySide6.QtDesigner public Q* names, 31 of them, include
QFormBuilder, QDesignerFormEditorInterface, QDesignerWidgetBoxInterface,
QPyDesignerCustomWidgetCollection, QPyDesignerContainerExtension,
QPyDesignerPropertySheetExtension, QPyDesignerTaskMenuExtension,
QPyDesignerMemberSheetExtension
```

`ls` of `.../lib/qt6/plugins/designer` shows `libPySidePlugin.dylib` and `libqquickwidget.dylib`. The default widget box XML does not list `QQuickWidget`. That class appears only if the plugin loads.

Research already on disk was read for fit, not as a substitute for the Qt sources. `docs/form_builder/research/B_qt_runtime_platform.md` records that FreeCAD.app 1.1.3 has `QUiLoader` and `loadUiType`, and that `loadUi` is absent. `docs/form_builder/research/D_first_principles_architecture.md` argued for a JSON layout file. The decision for this inventory is the opposite. The saved file is `.ui`. This document does not reopen that decision.

## How to read a checklist row

Each numbered row is one testable behavior.

The storage column names the `.ui` element or says that Designer keeps the fact outside the file. The surface column names the menu, mode, toolbar, or dialog. Complexity is S, M, or L.

S is one command or one property. M is a mode or a dialog with several rules. L is a subsystem that interacts with layout, selection, and the file format together.

Numbers are stable references for the weakness section at the end.

## Editing modes

Designer is always in one of four modes. The manual page is `https://doc.qt.io/qt-6/designer-editing-mode.html`. The 6.8.3 library contains the four command strings `Edit Widgets`, `Edit Signals/Slots`, `Edit Buddies`, and `Edit Tab Order`.

### 1. Widget editing mode

This is the default. The user adds widgets, moves them, resizes them, and edits properties. Switch with Edit, Edit Widgets, or F3. The 6.8.3 action also accepts Escape. `qdesigner_actions.cpp` appends both `Qt::Key_F3` and `Qt::Key_Escape` to that action. Storage is the whole widget tree under `ui/widget`. Surface is the canvas. Complexity L.

### 2. Signals and slots editing mode

The user drags from a sender to a receiver and picks a signal and a slot. Switch with Edit, Edit Signals/Slots, or F4. The manual is `https://doc.qt.io/qt-6/designer-connection-mode.html`. Spacers cannot be connected. Layouts can. A drag to the form background connects to the form itself, drawn with a ground symbol. Escape cancels the drag. Storage is `connections/connection` with `sender`, `signal`, `receiver`, `slot`, and optional `hints`. Complexity L.

### 3. Configure Connection dialog

After the drag, Designer lists signals of the source and slots of the destination. The checkbox Show all signals and slots reveals members inherited from `QWidget`. Otherwise those inherited members stay hidden. Double-clicking an existing connection path opens the same dialog. The path's red squares can be dragged. Those positions are the `hint` elements, with `type` `sourcelabel` or `destinationlabel`, and integer `x` and `y`. The Dialog with Buttons Bottom template stores two of these hints for `accepted()` to `accept()` and `rejected()` to `reject()`. Complexity M.

### 4. Delete a connection

Click any segment of the path and press Delete. The `connection` element is removed. The widgets stay. Complexity S.

### 5. Signal and slot editor table

Tools, Signal/Slot Editor shows the same connections as a table. The 6.8.3 string is `Signal/Slot Editor`. The manual says a configured connection becomes visible there and can be edited further. A missing sender or receiver is reported by the strings `SignalSlotEditor::fromUi(): no source widget called "%s"` and the matching destination message. Storage is the same `connection` element as mode 2. Complexity M.

### 6. Slots declared on the form

The schema allows `ui/slots/slot` and `ui/slots/signal` so a connection can target a slot that belongs to the form class rather than to a child widget. The connection's `receiver` is then the form object name. The 6.8 source of the dialog that adds a slot was not opened line by line. The element is in `ui4.xsd`. Complexity M.

### 7. Connect slots by name

Form Settings has a checkbox whose object name is `connectSlotsByNameCheckBox` and whose label is `Connect slots by name`. The schema attribute on `ui` is `connectslotsbyname`. In `qdesigner_resource.cpp` from tag 6.8.3, the attribute is written only when the flag is false. On load, a missing attribute means true. `uic` option `-a` or `--no-autoconnection` suppresses the generated `QObject::connectSlotsByName()` call. See `https://doc.qt.io/qt-6/uic.html`. This is separate from connections the user drew. Complexity M.

### 8. Buddy editing mode

Edit, Edit Buddies. The drag must start on a `QLabel`. The 6.8.3 library contains `BuddyEditor::endConnection(): not a label`. The link means the label's mnemonic moves focus to the buddy. Only one buddy per label. Delete the link with Delete. Test it in preview. Manual: `https://doc.qt.io/qt-6/designer-buddy-mode.html`. Storage is the label property `buddy` whose child is `cstring` with the buddy object name. The Form Settings dialog itself uses that shape for its own labels. Complexity M.

### 9. Buddy and the model view framework

The buddy manual says the buddy concept is also used by Qt's model view framework. That sentence is about Qt, not about an extra Designer mode. No second buddy tool was found in the command strings. Complexity S.

### 10. Tab order editing mode

Edit, Edit Tab Order. Each input widget shows a number. Click numbers in the desired order. The first click turns red. Finished numbers turn green. Unclicked numbers stay blue. Stop early if the tail of the chain is already right. Double-click outside a number, or choose Restart, to start over. Ctrl-click a number, or choose Start from Here, to edit from the middle. Manual: `https://doc.qt.io/qt-6/designer-tab-order.html`. The default order is construction order when this list is absent. Complexity M.

### 11. Tab order list dialog

The 6.8.3 library contains the strings `Tab Order List...` and `Tab Order List`. A list editor exists beside the click-on-numbers canvas. The manual page fetched this session describes only the canvas click method. The list dialog's exact columns were not opened. Complexity M. The list dialog's widget layout is unverified beyond the string.

### 12. Where tab order is stored

`ui/tabstops/tabstop` text is an object name, in click order. The schema type is `TabStops`. Widgets that are not input widgets are not numbered. The manual says "each input widget". The exact `focusPolicy` filter inside 6.8.3 was not read. Complexity M.

## Canvas editing

Manual: `https://doc.qt.io/qt-6/designer-widget-mode.html`.

### 13. New form

File, New Form, or Ctrl+N. `QKeySequence::New` in `qdesigner_actions.cpp`. Opens the template picker. Complexity S.

### 14. Open form

File, Open, or Ctrl+O. The filter string in that file is `Designer UI files (*.ui);;All Files (*)`, with the extension inserted. If a saved path is missing, Designer offers Update or New Form. Complexity S.

### 15. Save, Save As, and Save All

Save is Ctrl+S. Save All is bound twice in the 6.8 source. One line uses `ALT+CTRL+S`. The next line uses `CTRL+SHIFT+S` and the comment says that chord is commonly Save As on Mac. A backup-directory failure has its own warning string. Complexity S.

### 16. Close and quit

Close uses `QKeySequence::Close`. Quit uses `QKeySequence::Quit`. While a preview is open, the Close action text becomes `Close Preview`. Complexity S.

### 17. Drag from the widget box

In widget mode, drag a catalog entry onto the form. Containers highlight when the cursor is over them, so a near miss does not silently parent to the form. Manual: `https://doc.qt.io/qt-6/designer-using-containers.html`. Dropping onto the Object Inspector is also documented, for nested layouts. Complexity M.

### 18. Move, resize, and grid snap

Drag moves a selected widget. Arrow keys snap to the grid. Ctrl plus an arrow moves one pixel. Resize handles sit on corners and side midpoints. The current object in a multi-selection uses a different handle color. Complexity M.

### 19. Multi-selection

Ctrl-click adds to the selection. The property editor writes a changed property onto every selected object that has that property. Manual, widget editing mode. Complexity M.

### 20. Select the parent layout

Shift-click a child layout to select its parent layout. The layout frame is easy to miss. The manual states this under Using Layouts. Complexity S.

### 21. Move a widget that is already in a layout

Shift and Control together while dragging extends the selection to the parent layout so the widget can move inside it. A blue insertion cursor shows the drop index. Complexity M.

### 22. Tab key selects the next object

In widget mode, Tab changes the selection. This is not tab-order editing. Tab-order editing is mode 10. Complexity S.

### 23. Cut, copy, paste, and delete

Ctrl+X, Ctrl+C, Ctrl+V, and Delete. Also on the Edit menu and the form context menu. The 6.8.3 strings include `Paste %n widget(s)` and `Paste (%1 widgets, %2 actions)`. Paste into a laid-out container fails with a message that a container without a layout could not be found. That failure is a user-reported behavior, cited in the weakness section, and it matches the layout rule that a layout owns geometry. Complexity M.

### 24. Select all

The widget-mode manual says the Edit menu and the context menu provide Select All. Complexity S.

### 25. Clone with Ctrl-drag

Hold Ctrl and drag with the left button. Designer copies the selection and lets you drop the copy. The manual calls this cloning and distinguishes it from clipboard paste. Complexity S.

### 26. Copy between forms

Selections can be copied, pasted, and dragged from one form window to another. Documented on the widget-mode page. The copied fragment is still `.ui` widget XML. Complexity M.

### 27. Scratch pad

Drag a widget from the form onto the widget box. Designer creates a Scratchpad category. The copy can include children. A context menu renames or removes the scratch item. The 6.8.3 library contains `Scratchpad` and `slotScratchPadItemDeleted`. The scratch pad is an editor preference, not an element in `ui4.xsd`. Complexity M.

### 28. Object inspector

Tools window. A tree of every object. Expand a container or a layout to see children. Click to select. Right-click opens the form context menu. Ctrl+F locates an object by name. Since Qt 4.4, double-click the name to rename in place. Since Qt 4.5, a broken-layout icon marks a container whose layout is missing or wrong. Manual, widget editing mode. The tree is a view of the widget XML. Renaming writes the `name` attribute and the `objectName` property. Complexity M.

### 29. Object name rules

`objectName` is the property the editor shows. The file stores it as `widget name="..."` and often also as a property. Suggested names in the widget box are class-based and marked `notr="true"`, for example `pushButton` and `tabWidget`. Duplicate names in a template, such as two pages both called `page`, are rewritten when the widget is created so each object name is unique. The exact character filter Designer applies on rename was not executed in the app this session. `uic` generates Python or C++ identifiers from these names, so a name that is not an identifier will fail later in code generation. Complexity M.

### 30. In-place text edit

Double-click a label or a button, or press F2, to edit its text. Backslash-n becomes a newline. A doubled backslash becomes one backslash. A context menu can insert those characters. Documented on the widget-mode page for `QLabel` and for the Buttons category. Complexity S.

### 31. Change text command

The 6.8.3 library contains `Change text...`. That is a context command for the same string property as item 30. Complexity S.

### 32. Z-order commands

The library contains `Raise widgets`, `Lower widgets`, `Bring to &Front`, and `Send to &Back`. The schema allows repeated `widget/zorder` children whose text is a child object name. Stacking is otherwise the document order of child `widget` elements. Whether every raise writes a `zorder` element was not checked by saving a form. Complexity M.

### 33. Undo and redo

Standard undo and redo key sequences, wired in `qdesigner_actions.cpp`. The command stack lives in the designer shared library. `qdesigner_command.cpp` and `qdesigner_command2.cpp` are the 6.8 sources. Granularity is one designer command per structural edit. A property tweak and a layout change are separate commands. The exact grouping of a multi-widget paste was not stepped in the app. Complexity M.

### 34. Broken layout marker

If the top-level widget has no layout, the object inspector shows a broken-layout icon. The quick-start manual tells the user to resize the form. Widgets that resize with the window have a top-level layout. Widgets that stay at their `geometry` rect do not. Complexity S.

## Layouts

Manual: `https://doc.qt.io/qt-6/designer-layouts.html`.

A layout owns child geometry. After a widget is inserted, individual dragging and resizing stop. Spacers influence the leftover space. Layouts nest. The top-level layout is applied with an empty selection, by clicking the form background first. The same gesture lays out a selected container or a page of a page container. A top-level layout does not appear as its own row in the object inspector. Its properties show under the widget in the property editor. A nested layout does appear, with a red frame on the canvas.

### 35. Lay out horizontally

Form menu, toolbar, context menu, or Ctrl+1. Class `QHBoxLayout`. Complexity S.

### 36. Lay out vertically

Ctrl+2. Class `QVBoxLayout`. Complexity S.

### 37. Lay out in a grid

Ctrl+5. Class `QGridLayout`. Complexity M, because rows, columns, spans, and stretches are part of the same object.

### 38. Lay out in a form

Ctrl+6. Class `QFormLayout`. Two columns. Labels on the left, fields on the right. The class wraps long rows according to its policies. Complexity M.

### 39. Horizontal splitter

Ctrl+3. The manual says Designer treats `QSplitter` as a layout applied to existing widgets, even though `QSplitter` is a widget. The widget box XML has no splitter entry. Storage is a `widget class="QSplitter"` with children, not a `layout` element. Complexity M.

### 40. Vertical splitter

Ctrl+4. Same storage as item 39, with vertical orientation. Complexity M.

### 41. Break layout

Ctrl+0, or Break Layout on the Form menu, the toolbar, or the context menu. Children return to absolute `geometry`. Nested layouts can change size when a sibling layout is broken. That side effect is a reported complaint, cited later. Complexity M.

### 42. Adjust size

Ctrl+J. Calls the equivalent of `QWidget::adjustSize()` so each child has room for its contents. Complexity S.

### 43. Simplify grid layout

The 6.8.3 string is `Si&mplify Grid Layout`, and the slot is `slotActionSimplifyLayoutActivated`. It removes empty rows and columns from a grid. Storage is the remaining `item` row and column indexes. Complexity M.

### 44. Box and grid layout widgets in the widget box

The Layouts category does not drop a bare `QLayout`. Each entry drops a `QWidget` that already owns a layout, with object names `verticalLayoutWidget`, `horizontalLayoutWidget`, `gridLayoutWidget`, and `formLayoutWidget`. The layout classes inside are `QVBoxLayout`, `QHBoxLayout`, `QGridLayout`, and `QFormLayout`. Use these when the parent is not being laid out and you need a layout island. Complexity M.

### 45. Horizontal and vertical spacers

Widget box category Spacers. The catalog XML class is `Spacer`, not `QSpacerItem`. The catalog sets `orientation` (`Qt::Horizontal` or `Qt::Vertical`), an `objectName` string (`horizontalSpacer` or `verticalSpacer`), and `sizeHint`. A saved form stores a `spacer` element inside a `layout/item`. The name is the `name` attribute on `spacer`. Spacers cannot be signal senders. Complexity S.

### 46. Spacer size type

`sizeType` is a property of type `enum`, for example `QSizePolicy::Expanding` or `QSizePolicy::Fixed`. The New Form dialog's own `.ui` uses `sizeType` of `QSizePolicy::Fixed` on one internal spacer, with `stdset="0"` on `sizeHint`. The widget box templates do not set `sizeType`. Designer supplies a default when the spacer is dropped. The default value was not captured from a live drop. Complexity S.

### 47. Layout margins

The property editor exposes `layoutLeftMargin`, `layoutTopMargin`, `layoutRightMargin`, and `layoutBottomMargin`. Those names are strings in the 6.8.3 library. In the file they are `property` children of `layout`. Older files use a single `margin` property. The New Form widget UI still has `property name="margin"`. `uic` accepts both. Complexity M.

### 48. Layout spacing

`layoutSpacing` is the single spacing. `horizontalSpacing` and `verticalSpacing` exist as separate strings in the library, and as properties when the horizontal and vertical values differ. `QFormLayout` uses the pair. Complexity S.

### 49. Size constraint

`sizeConstraint` is an enum on the layout. Values are the `QLayout::SizeConstraint` enumerators, including `SetDefaultConstraint`, `SetNoConstraint`, `SetMinimumSize`, `SetFixedSize`, `SetMaximumSize`, and `SetMinAndMaxSize`. The property editor shows this on the layout. A top-level layout's constraint is edited on the form widget's layout section. Complexity S.

### 50. Box stretch

The schema attribute `layout stretch` is a comma-separated list, one integer per item. The property editor calls the matching concept layout stretch. Example shape from a forum post that quotes real XML: `stretch="1,0"` on a `QVBoxLayout`. Complexity S.

### 51. Grid row and column stretch, and minimums

Schema attributes on `layout`: `rowstretch`, `columnstretch`, `rowminimumheight`, `columnminimumwidth`. Each is a comma-separated string. They apply to `QGridLayout`. Complexity M.

### 52. Grid indexes and spans

`layout/item` attributes `row`, `column`, `rowspan`, `colspan`, and `alignment`. Alignment is a string of `Qt::` flags. A form layout uses row and column the same way, with labels in column 0 and fields in column 1, and a buddy stored on the label rather than on the item. Complexity M.

### 53. Form layout field growth, wrap, and alignment

The property sheet on tag 6.8.3 names `layoutFieldGrowthPolicy`, `layoutRowWrapPolicy`, `layoutLabelAlignment`, and `layoutFormAlignment`. The growth policy enumerators are `QFormLayout::FieldsStayAtSizeHint`, `QFormLayout::ExpandingFieldsGrow`, and `QFormLayout::AllNonFixedFieldsGrow`. The wrap policy enumerators are `QFormLayout::DontWrapRows`, `WrapLongRows`, and `WrapAllRows`. These are fake properties shown on the widget that owns the layout. Save writes them onto the `layout` element. Complexity M.

### 54. Morph a layout

Morphing widgets is item 55. Layout morph, in the sense of turning a horizontal box into a grid, is the set of Lay Out commands applied again, plus Simplify Grid Layout. A dedicated "morph layout" command string was not found. Re-applying a layout is the supported conversion. Complexity M.

### 55. Morph a widget

Context menu built by `morphmenu.cpp` on the 6.8 branch. Morphing is limited to known Qt classes. Custom widgets are excluded because they may own a layout Designer does not manage. The widget must sit on a parent Designer manages. Child widgets must be unlaid-out or in a Designer-managed layout.

Categories and the classes they morph among:

- Simple containers: `QWidget`, `QFrame`, `QGroupBox`. The code comment says morphing into a layout widget is intentionally not offered.
- Page containers: `QTabWidget`, `QStackedWidget`, `QToolBox`. A page container morphs to another page container, or to a simple container if it has one page.
- Item views: `QListView`, `QListWidget`, `QTreeView`, `QTreeWidget`, `QTableView`, `QTableWidget`, `QColumnView`.
- Buttons: `QCheckBox`, `QRadioButton`, `QPushButton`, `QToolButton`, `QCommandLinkButton`.
- Spin boxes: `QDateTimeEdit`, `QDateEdit`, `QTimeEdit`, `QSpinBox`, `QDoubleSpinBox`.
- Text: `QTextEdit`, `QPlainTextEdit`, `QTextBrowser`.

Properties that exist on the target are copied. Pages are created to match. Child widgets move with the page. The object name is rewritten by substituting the class stem, so `frame` can become `groupBox`. Storage is the new `class` attribute. Complexity L.

### 56. Size constraints from the context menu

The getting-started manual says a widget context menu can set a size constraint from the current size, which writes minimum and maximum size. The layout then respects those limits. Setting minimum and maximum to the same value overrides `sizeHint()`. Complexity S.

## Widget box

Source: `widgetbox.xml` on `qttools` branch `6.8`, version 4.2. Fifty-four entries. Nine categories. The local 6.8.3 binary contains the catalog marker string `widgetbox` and the format string `<widget class="`. The XML blob itself is compiled into a resource, so it was not extracted as text from the dylib. The source file is the catalog Designer ships.

Every entry below is complexity S unless the notes say otherwise. The surface is the named widget-box category. The stored class is the `widget class` attribute, except for layouts and spacers, which use the shapes in items 44 and 45.

### Layouts category

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 57 | Vertical Layout | `QWidget` plus `QVBoxLayout` | Object name `verticalLayoutWidget`. |
| 58 | Horizontal Layout | `QWidget` plus `QHBoxLayout` | Object name `horizontalLayoutWidget`. |
| 59 | Grid Layout | `QWidget` plus `QGridLayout` | Object name `gridLayoutWidget`. |
| 60 | Form Layout | `QWidget` plus `QFormLayout` | Object name `formLayoutWidget`. |

### Spacers category

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 61 | Horizontal Spacer | `Spacer` | `orientation` is `Qt::Horizontal`. |
| 62 | Vertical Spacer | `Spacer` | `orientation` is `Qt::Vertical`. |

### Buttons category

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 63 | Push Button | `QPushButton` | Default text `PushButton`. |
| 64 | Tool Button | `QToolButton` | Default text `...`. |
| 65 | Radio Button | `QRadioButton` | Default text `RadioButton`. |
| 66 | Check Box | `QCheckBox` | Default text `CheckBox`. |
| 67 | Command Link Button | `QCommandLinkButton` | Default text `CommandLinkButton`. |
| 68 | Dialog Button Box | `QDialogButtonBox` | `standardButtons` is `Ok` and `Cancel`. Complexity M because the box owns roles, orientation, and center buttons. |

### Item Views category, labeled Item Views Model-Based

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 69 | List View | `QListView` | Empty view. A model is attached in code. |
| 70 | Tree View | `QTreeView` | Empty view. |
| 71 | Table View | `QTableView` | Empty view. |
| 72 | Column View | `QColumnView` | Empty view. |
| 73 | Undo View | `QUndoView` | Shows a `QUndoStack` supplied in code. |

### Item Widgets category, labeled Item Widgets Item-Based

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 74 | List Widget | `QListWidget` | Items are editable in Designer. See item 168. |
| 75 | Tree Widget | `QTreeWidget` | Columns and items. See item 169. |
| 76 | Table Widget | `QTableWidget` | Rows, columns, and cells. See item 170. |

### Containers category

| ID | Entry | Class stored | Default XML this catalog ships |
| --- | --- | --- | --- |
| 77 | Group Box | `QGroupBox` | `title` is `GroupBox`. Geometry 120 by 80. |
| 78 | Scroll Area | `QScrollArea` | `widgetResizable` true. Child `QWidget` named `scrollAreaWidgetContents`. Geometry 120 by 80. |
| 79 | Tool Box | `QToolBox` | `currentIndex` 0. Two pages, both named `page`, attribute `label` `Page 1` and `Page 2`. |
| 80 | Tab Widget | `QTabWidget` | Two pages, both named `tab`, attribute `title` `Tab 1` and `Tab 2`. Geometry 120 by 80. |
| 81 | Stacked Widget | `QStackedWidget` | Two empty pages, both named `page`. No title attribute. |
| 82 | Frame | `QFrame` | `frameShape` `QFrame::StyledPanel`, `frameShadow` `QFrame::Raised`. |
| 83 | Widget | `QWidget` | Plain container. Geometry 120 by 80. |
| 84 | MDI Area | `QMdiArea` | No child subwindows in the template. Geometry 200 by 160. |
| 85 | Dock Widget | `QDockWidget` | Child `QWidget` named `dockWidgetContents`. |

### Input Widgets category

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 86 | Combo Box | `QComboBox` | Items are added later. See item 171. |
| 87 | Font Combo Box | `QFontComboBox` | Fills from the font database at runtime. |
| 88 | Line Edit | `QLineEdit` | Single-line string. |
| 89 | Text Edit | `QTextEdit` | Rich text capable. |
| 90 | Plain Text Edit | `QPlainTextEdit` | Plain text. |
| 91 | Spin Box | `QSpinBox` | Integer. |
| 92 | Double Spin Box | `QDoubleSpinBox` | Double. |
| 93 | Time Edit | `QTimeEdit` | `QTime`. |
| 94 | Date Edit | `QDateEdit` | `QDate`. |
| 95 | Date/Time Edit | `QDateTimeEdit` | `QDateTime`. |
| 96 | Dial | `QDial` | Integer dial. |
| 97 | Horizontal Scroll Bar | `QScrollBar` | `orientation` `Qt::Horizontal`. |
| 98 | Vertical Scroll Bar | `QScrollBar` | `orientation` `Qt::Vertical`. |
| 99 | Horizontal Slider | `QSlider` | `orientation` `Qt::Horizontal`. |
| 100 | Vertical Slider | `QSlider` | `orientation` `Qt::Vertical`. |
| 101 | Key Sequence Edit | `QKeySequenceEdit` | Edits a `QKeySequence`. |

### Display Widgets category

| ID | Entry | Class stored | Notes |
| --- | --- | --- | --- |
| 102 | Label | `QLabel` | Default text `TextLabel`. Buddy target. |
| 103 | Text Browser | `QTextBrowser` | Read-only rich text with links. |
| 104 | Graphics View | `QGraphicsView` | Scene is attached in code. |
| 105 | Calendar Widget | `QCalendarWidget` | Date grid. |
| 106 | LCD Number | `QLCDNumber` | Digit display. |
| 107 | Progress Bar | `QProgressBar` | Catalog sets `value` to 24. |
| 108 | Horizontal Line | `Line` | `orientation` `Qt::Horizontal`. Saved class stays `Line`. It is a `QFrame` with a horizontal line shape. |
| 109 | Vertical Line | `Line` | `orientation` `Qt::Vertical`. Same class, vertical line shape. |
| 110 | OpenGL Widget | `QOpenGLWidget` | Present in the 6.8 catalog. A ChoreBoy appliance may not expose a usable GL context. That runtime limit was not measured here. |

### Classes the default box does not list

These still matter for parity because Designer can create them, load them, or morph toward them.

| ID | Class | How the user gets it | Storage |
| --- | --- | --- | --- |
| 111 | `QMainWindow` | Main Window template | Root `widget`. |
| 112 | `QDialog` | Dialog templates | Root `widget`. |
| 113 | `QMenuBar` | Part of the main window template, or Create Menu Bar | Child widget. |
| 114 | `QMenu` | Typed into the menu bar | Child of the menu bar, or an `action` with a `menu` attribute. |
| 115 | `QToolBar` | Context menu Add Tool Bar | Child widget of the main window. |
| 116 | `QStatusBar` | Part of the main window template | Child widget named `statusbar` in the 6.8 template. |
| 117 | `QAction` | Action editor | `action` under the main window, referenced by `addaction`. |
| 118 | `QActionGroup` | Action editor grouping | `actiongroup` element. |
| 119 | `QButtonGroup` | Create button group | `buttongroups/buttongroup`, plus a `buttonGroup` attribute on each button. |
| 120 | `QSplitter` | Ctrl+3 or Ctrl+4 | `widget class="QSplitter"`. |
| 121 | `QWizard` and `QWizardPage` | Not in `widgetbox.xml`. `containerwidget_taskmenu.cpp` on tag 6.8.3 builds a wizard task menu with Back and Next. `qwizard_container.cpp` only accepts `QWizardPage` children. `pageId` is written as an attribute only when that property is marked changed, with `notr="true"`. | Wizard page widgets. Complexity L. |
| 122 | `QQuickWidget` | Plugin `libqquickwidget.dylib` in this FreeCAD build | Custom or stock widget XML. Not in the default catalog. |
| 123 | Promoted class | Promote to | `customwidgets/customwidget`, and the widget `class` becomes the promoted name while `extends` keeps the placeholder. |

`QAxWidget` is not in the 6.8 widget box. It is a Windows ActiveQt class. It is out of scope for a Linux appliance.

## Container editing

Manual: `https://doc.qt.io/qt-6/designer-using-containers.html`. The fetched page documents frames, group boxes, stacked widgets, tab widgets, tool boxes, and dock widgets. It does not walk through scroll areas, MDI areas, or wizards. Those three are in the widget box or the library, so their editing model is partly inferred from the XML.

### 124. Frame

Decorative or grouping container. Properties the manual names: `frameShape`, `frameShadow`, `lineWidth`, `midLineWidth`. The catalog default is a raised styled panel. Complexity S.

### 125. Group box

Properties the manual names: `title`, `flat`, `checkable`, `checked`. A group box that contains widgets needs its own layout. Click inside it and apply a layout. Complexity M.

### 126. Stacked widget pages

Designer shows corner arrows that exist only at design time. Context menu: Next Page, Previous Page, Insert Page, Delete Page. The 6.8.3 strings include `Insert Page After Current Page` and `Insert Page Before Current Page`. Pages are child `widget` elements. `currentIndex` is a property. Pages have no title attribute in the catalog. Complexity M.

### 127. Tab widget pages

The catalog starts with two tabs. Insert Page adds before or after the current page. The property editor exposes `currentTabText` for the current page. The file stores that text as `attribute name="title"` on the page widget, which is what the catalog writes. The library also contains `currentTabIcon` and `currentTabToolTip`. Those become attributes on the page. In `qdesigner_tabwidget.cpp` from tag 6.8.3, dropping a tab on another tab pushes `MoveTabPageCommand` and shows a red indicator 3 pixels wide. A 2015 forum post said that drag did nothing. The 6.8.3 source does implement it. Complexity M.

### 128. Tool box pages

Same insert and delete commands. The manual says the visible title is the property `currentItemText`. The catalog stores `attribute name="label"` on the page, not `title`. A builder that only copies the tab-widget attribute name will drop tool box titles. Complexity M.

### 129. Scroll area

The catalog sets `widgetResizable` to true and inserts `scrollAreaWidgetContents`. Further widgets go on that inner widget, which then needs a layout if they should resize. The containers chapter does not spell this out. The XML does. Complexity M.

### 130. MDI area

The catalog drops an empty `QMdiArea`. `MdiContainerWidgetTaskMenu` in `containerwidget_taskmenu.cpp` on tag 6.8.3 adds Next Subwindow, Previous Subwindow, Tile, Cascade, and Add Subwindow. Add Subwindow is the insert action with no before or after choice. The saved child is the inner widget. A `QMdiSubWindow` wrapper is not the class written in the file. Complexity L.

### 131. Dock widget

Drag from Containers. The manual says not to put it inside an existing layout. Enable the `docked` property to attach it to a dock area. When the parent is a `QMainWindow`, `QDesignerResource::saveWidget` writes `attribute name="dockWidgetArea"` as a `number`, the integer value of `Qt::DockWidgetArea`. `allowedAreas` and `features` remain ordinary properties. The catalog includes `dockWidgetContents` as the inner widget. Complexity M.

### 132. Page container layout

Select the container, or the page, then apply a layout. The manual lists `QGroupBox`, `QTabWidget`, `QToolBox`, and `QStackedWidget` as containers whose page or body can take a top-level layout. Complexity M.

### 133. Widget box filter and view

The library contains `WidgetBoxFilterLineEdit`, `Expand all`, `Collapse all`, `List View`, and `Icon View`. The box can be filtered and switched between list and icon view. This state is not stored in the `.ui` file. Complexity S.

## Main windows, menus, toolbars, and actions

Manual: `https://doc.qt.io/qt-6/designer-creating-mainwindows.html`.

### 134. Main window template contents

The 6.8 file `Main_Window.ui` is a `QMainWindow` named `MainWindow`, geometry 800 by 600, window title `MainWindow`. Children are `QMenuBar` named `menubar`, `QWidget` named `centralwidget`, and `QStatusBar` named `statusbar`. There is no `QToolBar` in that file. The Qt 6.12 manual says the template contains a menu bar and a toolbar. The 6.8 template does not contain a toolbar. Complexity M.

### 135. Create a menu bar

If the menu bar was removed, the context menu offers Create Menu Bar. One menu bar only. Complexity S.

### 136. Type Here menus

A placeholder labeled Type Here is always present while editing and is absent from preview and from the running window. Double-click, type, Enter accepts, Escape rejects. An ampersand marks the mnemonic. Drag menus along the bar. A red line shows the insert point. Remove Menu, with the menu name, deletes one. Complexity M.

### 137. Menu entries and separators

Double-click Type Here inside a menu, or double-click Add Separator. Entries drag to a new index. Dragging onto a closed menu opens it. An entry is a `QAction`. The same action can be dropped on a toolbar. Storage is `action` plus `addaction` children in visual order. A separator is an `addaction` whose name is `separator`. `QDesignerResource` on tag 6.8.3 treats that name as a separator action when it loads a menu or toolbar. Complexity M.

### 138. Add and remove a toolbar

Context menu Add Tool Bar. The manual also says the arrow at the right end of an existing toolbar creates another. Removal is on the toolbar context menu. Several toolbars are allowed. When the parent is a `QMainWindow`, save writes `attribute name="toolBarArea"` as an enum key from the toolbar-area meta-enum, and `attribute name="toolBarBreak"` as a bool. A separator on the bar is still `addaction name="separator"`. Complexity M.

### 139. Action editor

Tools, Action Editor. The 6.8.3 string confirms the tool. New opens a dialog for Text, which also builds the object name with an `action` prefix, and for an icon. Delete removes the action. Filter searches by text. Icon View and Detailed View are both described in the manual. Copy and paste of actions across forms is documented. Drag from the editor onto a menu or toolbar. Guide lines show the landing spot. Complexity L.

### 140. Action properties

An action stores `property` children. The usual set is `text`, `icon` as `iconset`, `shortcut` as a key sequence string, `checkable`, `checked`, `toolTip`, `statusTip`, `whatsThis`, `enabled`, and `visible`. The shortcut is edited in the action editor or the property editor after creation. The manual says the shortcut is set in the action editor. Complexity M.

### 141. Action groups

`actiongroup` has a `name` and may contain `action`, nested `actiongroup`, `property`, and `attribute`. The `menu` attribute on `action` names a menu that action opens. Complexity M.

### 142. Button groups

Commands present as strings: `Create button group`, `New button group`, `Assign to button group`, `Break button group`, and `Break button group '%1'`. Storage is `ui/buttongroups/buttongroup` with properties such as `exclusive`, and an attribute on each member button. The library contains `buttonGroup` and `buttonGroupId`. Complexity M.

### 143. Central widget

The template's `centralwidget` is an empty `QWidget`. It needs a layout of its own. Dock widgets and toolbars are siblings of the central widget, not children of it. Complexity S.

### 144. Status bar

The template includes an empty `QStatusBar`. Temporary messages are a runtime call. Designer does not edit a list of status-bar widgets in a dedicated editor beyond dropping widgets if the bar accepts them. A dedicated status-bar item editor was not found in the manual. Complexity S.

## Property editor

Manual section on `https://doc.qt.io/qt-6/designer-widget-mode.html`. The editor shows the properties of the current selection. The set depends on the class. `objectName` and `enabled` exist on every stock widget.

### 145. Editor widgets by type

Text uses a line edit. Integers use a spin box. Booleans use a check box. Compound values use a drop-down of nested editors. Enums and flag sets use a combo box. Flag items are checkable. Rich values such as `QPalette` open a dialog. Complexity M.

### 146. Changed-state marker and reset

Modified properties use a bold label. A reset arrow on the right returns the property to its default and removes the `property` element from the file. The 6.8.3 library contains `ResetDecorator` and `slotResetProperty`. Complexity S.

### 147. Multi-selection edit

A change applies to every selected object that has the same property. Objects that lack the property are skipped. Complexity M.

### 148. Sort and color groups

The property editor toolbar's Configure button sorts properties alphabetically and changes color groups. The manual says that. `propertyeditor.cpp` on tag 6.8.3 also has a line edit whose placeholder is Filter. The match is a case-insensitive substring of the property name. A group stays if any child matches. The action editor and the widget box have their own filters. Complexity S.

### 149. Dynamic properties

Since Qt 4.4, Add and Remove on the property editor toolbar create and delete a dynamic property. The 6.8.3 strings are `Add Dynamic Property...` and `Remove Dynamic Property`. The dialog UI `newdynamicpropertydialog.ui` exists on the 6.8 branch. Storage is a normal `property` element. `uic` emits `setProperty` when `stdset="0"`. The schema attribute is `stdset`. Complexity M.

### 150. Property versus attribute

`property` is a Qt property, written with a setter. `attribute` uses the same value grammar and stores Designer or container metadata that is not a normal property, such as a tab title or a button-group id. Both appear in the schema as type `Property`. Complexity M.

### 151. Bool

Element `bool`, text `true` or `false`. The schema types it as a string. Complexity S.

### 152. Number, float, double, long, and unsigned

Elements `number` for a signed integer, `float`, `double`, `longlong`, `uint`, and `ulonglong`. Spin boxes and sliders use `number`. Double spin boxes use `double`. Complexity S.

### 153. Enum

Element `enum`, text such as `Qt::Horizontal` or `QFrame::Raised`. The editor is a combo box. Complexity S.

### 154. Flags

Element `set`, text of enumerator names joined by `|`. Examples from templates: `QDialogButtonBox::Cancel|QDialogButtonBox::Ok` and `Qt::AlignCenter`. The editor is a checkable combo. Complexity S.

### 155. String

Element `string`. Attributes from the schema: `notr`, `comment`, `extracomment`, and `id`. There is no attribute named `disambiguation`. In `qdesigner_resource.cpp` on tag 6.8.3, `comment` is written from the disambiguation field, and `extracomment` is written from the translator comment field. `notr="true"` means the string is not translated. `id` is the id-based translation id. The widget box uses `notr="true"` on object names. User-visible text usually omits `notr`. Complexity M.

### 156. String list

Element `stringlist` with the same four attributes, then child `string` items. Used by properties such as combo-box inserts in some versions, and by custom list properties. Item widgets more often use `item` children. Complexity M.

### 157. C string

Element `cstring`. Used for object-name references such as `buddy`, where the value must not be translated. Complexity S.

### 158. Char

Element `char` containing `unicode` as an integer code point. Complexity S.

### 159. Font

Element `font`. Children present in the schema: `family`, `pointsize`, `weight` as a legacy integer, `italic`, `bold`, `underline`, `strikeout`, `antialiasing`, `stylestrategy`, `kerning`, `hintingpreference`, and `fontweight` as a Qt 5 and Qt 6 enum string. The editor is a font dialog. Complexity M.

### 160. Color

Element `color` with `red`, `green`, `blue`, and optional attribute `alpha`. Complexity S.

### 161. Brush and gradient

Element `brush` with attribute `brushstyle`, and one of `color`, `texture`, or `gradient`. A gradient has `gradientStop` children, each with a `position` and a `color`. Attributes include start, end, center, focal point, `radius`, `angle`, `type`, `spread`, and `coordinatemode`. Palette roles and some widget brushes use this. Complexity L.

### 162. Palette

Element `palette` with required groups `active`, `inactive`, and `disabled`. Each group contains `colorrole` elements with a `role` attribute and a `brush`, or legacy `color` children. The editor is the palette dialog. `paletteeditor.ui` is on the 6.8 branch. The 6.8.3 string `Edit Palette` is the command. Complexity L.

### 163. Cursor

Legacy element `cursor` as an integer, and current element `cursorshape` as a string such as `ArrowCursor`. The library contains `QtCursorDatabase` and `Select Font` nearby in the same string table, which is the property-editor cluster. Complexity S.

### 164. Pixmap

Element `pixmap`, type `ResourcePixmap`. Attributes `resource` and `alias`. The text is a file path when no resource is selected. The property editor offers Choose Resource and a file picker. Manual: `https://doc.qt.io/qt-6/designer-resources.html`. Complexity M.

### 165. Icon set

Element `iconset`. Optional child pixmaps for the eight states `normaloff`, `normalon`, `disabledoff`, `disabledon`, `activeoff`, `activeon`, `selectedoff`, and `selectedon`. Attribute `theme` names a theme icon. Attribute `resource` is the pre-4.4 legacy form. Complexity L.

### 166. Size, point, and rect

`size` has `width` and `height`. `point` has `x` and `y`. `rect` has `x`, `y`, `width`, and `height`. `sizef`, `pointf`, and `rectf` use doubles. `geometry`, `minimumSize`, `maximumSize`, `sizeHint`, `pos`, and icon sizes use these. Absolute geometry is what you get when a widget is not inside a layout. Complexity M.

### 167. Size policy

Element `sizepolicy` with attributes `hsizetype` and `vsizetype`, and children `horstretch` and `verstretch`. The schema also allows legacy child elements `hsizetype` and `vsizetype` as integers. The editor is a compound property. Complexity M.

### 168. Key sequence

Stored as a string property. The action `shortcut` property and `QKeySequenceEdit` use it. The schema does not have a distinct key-sequence element. The string is the sequence text. Complexity S.

### 169. Date, time, and date-time

`date` has `year`, `month`, `day`. `time` has `hour`, `minute`, `second`. `datetime` has all six. Used by the date and time editors. Complexity S.

### 170. Url

Element `url` containing a `string`, so translation attributes still apply. Complexity S.

### 171. Locale

Element `locale` with attributes `language` and `country`. Complexity S.

### 172. String list editor and text editor dialogs

`stringlisteditor.ui` and `texteditor.cpp` are on the 6.8 branch. The library contains `Edit Text` and `Edit HTML`. Rich text is stored as the `string` or as HTML inside that string. Complexity M.

### 173. List, tree, table, and combo item editors

Library strings: `Edit Items...`, `Edit List Widget`, `Edit Combobox`, `Edit Tree Widget`, `Edit Table Widget`. Schema support:

- `item` with nested `item` for trees and lists, and optional `row` and `column` attributes for table cells.
- `row` and `column` with properties for headers.
- Combo box items are `item` children whose `text` property is a string.

Complexity L for tree and table, M for list and combo.

## Resources, style sheets, and preview

### 174. Resource browser

Tools, Resource Browser. Each form can point at its own `.qrc`. Edit Resources, Reload, Add Files, and Remove Files are the manual's commands. Files must live in the `.qrc` directory or a subdirectory. Storage in the `.ui` is `resources/include location="..."`. The `.qrc` file is separate. Manual: `https://doc.qt.io/qt-6/designer-resources.html`. Complexity L.

### 175. Resource compiler and Python imports

`uic -g python` emits `import resources_rc` for a sibling `resources.qrc`. `--rc-prefix` emits `import rc_resources`. `--from-imports` emits a relative import. `--absolute-imports` and `--python-paths` handle a tree where the `.qrc` is not beside the `.ui`. Manual: `https://doc.qt.io/qt-6/designer-using-a-ui-file-python.html`. ChoreBoy's AppArmor profile, as recorded in research D, limits subprocess execution. Calling `uic` or `rcc` from the editor is a product decision, not a Designer feature. `QUiLoader` can load a `.ui` without `uic`. Complexity M.

### 176. Style sheet editor

Right-click a widget and choose Change styleSheet. The command has existed since Qt 4.2. Manual: `https://doc.qt.io/qt-6/designer-stylesheet.html`. The page is short. `stylesheeteditor.cpp` on tag 6.8.3 opens Edit Style Sheet. The body is a text edit with a CSS highlighter and a find bar. Actions are Add Resource, Add Gradient, Add Color, and Add Font. A label reads Valid Style Sheet or Invalid Style Sheet. OK is disabled while the sheet fails `QCss::Parser`. Apply is added on the property-editor dialog and follows the same rule. Storage is the `styleSheet` string property on that widget, including the form widget. Complexity M. The sheet is still text. The dialog does not list which widgets a selector hits.

### 177. Preview

Form, Preview, or Ctrl+R. `qdesigner_actions.cpp` sets the shortcut to `CTRL+R`. The preview is a real widget tree, not a drawing. Manual: `https://doc.qt.io/qt-6/designer-preview.html`. Complexity M.

### 178. Preview in a style or a skin

Edit, Preferences, then the print and preview configuration. The manual says the Print/Preview Configuration checkbox must be checked. A style combo lists Qt styles. A style sheet box applies the equivalent of `QApplication::setStyleSheet`. Device skins include a built-in list and a Browse button for QVFB skins. The 6.8.3 library contains `Preview in` and `slotActionGroupPreviewInStyle`. These choices are not stored in the `.ui`. Complexity M.

### 179. Device profiles

Form Settings embeds a device-profile label. The New Form dialog has Device and Screen Size combos. The profile dialog edits Name, Family, Point Size, Style, and Device DPI. `deviceprofiledialog.ui` on the 6.8 branch is that form. Profiles are editor configuration. `ui4.xsd` has no device element. Screen-size template copies exist for 240 by 320, 320 by 240, 480 by 640, and 640 by 480, beside the default templates. Complexity M.

### 180. Save image and print

File actions `Save Image...` and `Print...`. The image is PNG. Print uses the print key sequence. Neither writes the `.ui`. Complexity S.

### 181. View code

The 6.8 source creates two actions, `View &C++ Code...` and `View &Python Code...`. The current manual still says a single View Code command that shows `uic` output. Both generators are real `uic` modes: `-g cpp` and `-g python`. Failure raises `Code generation failed`. Complexity M.

### 182. Preferences shell

`preferencesdialog.ui` is a tab widget plus Ok, Cancel, and Apply. The pages are added in code. The getting-started manual says the user can switch multi-window mode and docked mode there. Integrated Qt Creator offers only the multi-window arrangement. Additional Fonts is a separate action, and its tooltip says it stays disabled until every form is closed. Complexity M.

## Form templates and form settings

### 183. Built-in templates

On the 6.8 branch, `src/designer/src/lib/shared/templates/forms/` contains:

- `Dialog_with_Buttons_Bottom.ui`, a `QDialog` 400 by 300 with a `QDialogButtonBox` at geometry x 30, y 240, size 341 by 32, buttons Cancel and Ok, already connected to `accept()` and `reject()`.
- `Dialog_with_Buttons_Right.ui`. The file is in the tree listing. Its bytes were not opened this session.
- `Dialog_without_Buttons.ui`, an empty `QDialog` 400 by 300.
- `Main_Window.ui`, described in item 134.
- `Widget.ui`, a `QWidget` named `Form`, class name `Form`, 400 by 300.

None of these templates installs a layout. Geometry is absolute until the user lays the form out. Complexity M.

### 184. Save as template

The action text is `Save As &Template...`. `saveformastemplate.ui` is the dialog. Saved templates show up in the New Form list. They are files Designer keeps beside its built-in templates, not a section of the current `.ui`. The destination directory was not listed on disk. Complexity S.

### 185. Form settings, author

Form, Form Settings. The dialog title is Form Settings. The Author field writes `ui/author`. Complexity S.

### 186. Layout default

A checkable group. Margin and spacing spin boxes. Storage is `layoutdefault` with attributes `spacing` and `margin`. `uic` uses these when a layout does not set its own values. Complexity S.

### 187. Layout function

A checkable group with two line edits, margin and spacing function names. Storage is `layoutfunction` with attributes `margin` and `spacing` holding the function names. When set, generated code calls those functions instead of the numeric default. Complexity M.

### 188. Pixmap function

A checkable group. Storage is `pixmapfunction` text, the name of a function `uic` should call to load pixmaps. Empty in the stock templates. Complexity S.

### 189. Include hints

A text box. Each line becomes `includes/include`. Attribute `location` is `local` or `global`. Global hints are written with angle brackets in the generated include. Local hints are quoted paths. The schema element `header` on a custom widget uses the same location idea. Complexity M.

### 190. Export macro and comment

The schema requires neither. `exportmacro` is a string `uic` uses on the generated class. `comment` is a free string. Both appear empty in `Main_Window.ui` and in the bottom-button dialog. The Form Settings dialog that was read has no comment field and no export-macro field. Those elements can still be in a file. Complexity S.

### 191. ID-based translation

The Form Settings checkbox label is `ID-based`. The schema attribute is `idbasedtr`. When it is true, `uic --idbased` and the string `id` attributes drive translation. Per-string `id` still exists when the form attribute is absent. Complexity M.

### 192. Language and display name

Schema attributes `language` and `displayname` on `ui`. None of the four templates that were opened set them. `uic` can still read them. Complexity S.

### 193. Legacy stdset defaults

Attributes `stdsetdef` and `stdSetDef` on `ui`. The schema comments say the first is legacy from `uic3` and the second is legacy from the Visual Studio integration. A new builder should read them and should not write them. Complexity S.

## Custom widgets and plugins

Manual: `https://doc.qt.io/qt-6/designer-using-custom-widgets.html`, `https://doc.qt.io/qt-6/designer-creating-custom-widgets.html`, and `https://doc.qt.io/qt-6/designer-creating-custom-widgets-extensions.html`.

### 194. Promote to

Context menu Promote to. The dialog takes a class name and a header. Add puts the class in the promotion list. Promote applies it to the selected widget. Later widgets of the same base class can be promoted from a submenu. Demote to restores the base class. The placeholder should be the closest stock base, or `QWidget` if nothing is close. Storage:

```xml
<customwidgets>
  <customwidget>
    <class>MyPushButton</class>
    <extends>QPushButton</extends>
    <header>mypushbutton.h</header>
  </customwidget>
</customwidgets>
```

The widget's `class` attribute becomes `MyPushButton`. `header location` is `local` or `global`. Complexity M.

### 195. Custom widget record, full schema

`customwidget` also allows `sizehint`, `addpagemethod`, `container` as an integer, `pixmap`, `slots`, and `propertyspecifications`. Deprecated children are `sizepolicy`, `script`, and `properties`. `propertyspecifications` holds `tooltip` and `stringpropertyspecification` with `name`, `type`, and `notr`. `addpagemethod` names the method a container plugin uses to add a page. Complexity L.

### 196. Plugin interface

A plugin subclasses `QDesignerCustomWidgetInterface`. The manual's table of functions:

- `name`, the class name.
- `group`, the widget-box category.
- `toolTip` and `whatsThis`, the box descriptions.
- `includeFile`, written into the `.ui` and emitted by `uic`.
- `icon`, the box icon.
- `isContainer`.
- `createWidget`, a factory. Properties are not ready until load returns.
- `domXml`, a `.ui` snippet. Since Qt 4.4 it may be a full `ui` document. An empty string hides the widget from the box but still allows other widgets to use the class.
- `codeTemplate`, reserved and unused.
- `initialize` and `isInitialized`, where extensions are registered.

`QDesignerCustomWidgetCollectionInterface` groups several widgets. PySide exposes `QPyDesignerCustomWidgetCollection`. This session's `dir(PySide6.QtDesigner)` includes that class. Complexity L.

### 197. Extensions

Registered through `QExtensionFactory` and `QExtensionManager` during `initialize`. The extensions page lists:

- `QDesignerContainerExtension`, add and delete pages.
- `QDesignerTaskMenuExtension`, extra context-menu commands.
- `QDesignerMemberSheetExtension`, which signals and slots the connection editor shows.
- `QDesignerPropertySheetExtension` and `QDesignerDynamicPropertySheetExtension`. A custom sheet replaces the default sheet.

PySide 6.8.3 exposes Python helpers `QPyDesignerContainerExtension`, `QPyDesignerMemberSheetExtension`, `QPyDesignerPropertySheetExtension`, and `QPyDesignerTaskMenuExtension`. A compiled plugin in `plugins/designer` is how Designer loads this. FreeCAD.app already has `libPySidePlugin.dylib` there. A user project on a noexec mount cannot add another compiled plugin. Research D states that mount rule. It was not re-tested here. Promotion of a pure Python class is the path that still fits. Complexity L.

### 198. Security

`https://doc.qt.io/qt-6/qt-widgets-designer-security-considerations.html` says Designer treats input as trusted. Plugins can run arbitrary code. A `.ui` file can contain absolute and relative paths, so Designer may read those files. The page tells developers to open only files and plugins they trust. A form builder that loads third-party `.ui` files inherits this. Complexity M.

## Keyboard shortcut index

Shortcuts below are from the fetched manual or from `qdesigner_actions.cpp` on branch 6.8. Buddy mode and tab-order mode are menu commands. A dedicated shortcut for those two was not found.

| ID | Shortcut | Action |
| --- | --- | --- |
| 199 | Ctrl+N | New form |
| 200 | Ctrl+O | Open form |
| 201 | Ctrl+S | Save |
| 202 | Ctrl+Shift+S, and also Alt+Ctrl+S in the source | Save all. Platform `#if` selects one. |
| 203 | Ctrl+W or the platform close sequence | Close form, or close preview |
| 204 | Quit sequence | Quit |
| 205 | Ctrl+Z and the redo sequence | Undo and redo |
| 206 | Ctrl+X, Ctrl+C, Ctrl+V, Delete | Clipboard and delete |
| 207 | Ctrl+R | Preview |
| 208 | Ctrl+P | Print |
| 209 | F1 | Help for the current widget |
| 210 | Ctrl+? | Designer help |
| 211 | F3 or Escape | Widget editing mode |
| 212 | F4 | Signals and slots mode |
| 213 | F2 | Edit the selected label or button text |
| 214 | Ctrl+F | Find in the object inspector |
| 215 | Ctrl+1 through Ctrl+6 | Horizontal, vertical, horizontal splitter, vertical splitter, grid, form |
| 216 | Ctrl+0 | Break layout |
| 217 | Ctrl+J | Adjust size |
| 218 | Ctrl-drag | Clone |
| 219 | Arrow keys, and Ctrl plus arrow | Snap to grid, or move one pixel |
| 220 | Shift-click | Select the parent layout |
| 221 | Shift+Ctrl+drag | Move a widget inside its layout |

### 222. Grid settings

Form Settings includes the grid panel. Visible, Grid X, Grid Y, Snap for each axis, and Reset. Spin boxes run from 2 to 100. `grid.cpp` on tag 6.8.3 serializes `gridVisible`, `gridSnapX`, `gridSnapY`, `gridDeltaX`, and `gridDeltaY`. `FormWindowBase::formData` adds that map when the form has its own grid, and it forces every key. `QDesignerResource` writes a non-empty `formData` map into `designerdata`. A default grid is not written. Device profiles stay in application settings, not in the `.ui`. Complexity M.

## The ui4 element catalog

Source: `ui4.xsd` on `qttools` branch `6.8`, fetched this session. Every `xs:element` and `xs:complexType` name in that file is listed. The root element of a form is `ui`. Every template opened this session has `version="4.0"`.

What produces an element means the Designer action that writes it, when that action was identified. `uic` and `QFormBuilder` also read elements a user can type by hand.

### Document root

| ID | Name | Parent | What writes it | Complexity |
| --- | --- | --- | --- | --- |
| 223 | `ui` | document | Any save. Attributes: `version`, `language`, `displayname`, `idbasedtr`, `connectslotsbyname`, legacy `stdsetdef`, legacy `stdSetDef`. | L |
| 224 | `author` | `ui` | Form Settings, Author. | S |
| 225 | `comment` | `ui` | Present in stock templates as an empty element. No field in the Form Settings UI that was read. | S |
| 226 | `exportmacro` | `ui` | Empty in stock templates. Consumed by `uic` for the class export macro. | S |
| 227 | `class` | `ui` | The generated class name, such as `MainWindow`, `Dialog`, or `Form`. | S |
| 228 | `widget` | `ui` and nested | The form root and every child widget. | L |
| 229 | `layoutdefault` | `ui` | Form Settings, Layout Default. Attributes `spacing`, `margin`. | S |
| 230 | `layoutfunction` | `ui` | Form Settings, Layout Function. Attributes are function names. | S |
| 231 | `pixmapfunction` | `ui` | Form Settings, Pixmap Function. | S |
| 232 | `customwidgets` | `ui` | Promote, or a plugin save. | M |
| 233 | `tabstops` | `ui` | Tab order mode. | M |
| 234 | `images` | `ui` | Deprecated. The schema gives it no type. Do not write it. | S |
| 235 | `includes` | `ui` | Include hints, and headers `uic` must emit. | M |
| 236 | `resources` | `ui` | Resource browser. Attribute `name` optional. | M |
| 237 | `connections` | `ui` | Signals and slots mode, and the connection table. | L |
| 238 | `designerdata` | `ui` | Editor state such as the grid. Properties use the normal property grammar. | M |
| 239 | `slots` | `ui` and `customwidget` | Slots and signals declared for the form or the custom class. | M |
| 240 | `buttongroups` | `ui` | Button group commands. | M |

### Includes, resources, and custom widgets

| ID | Name | Parent | Role |
| --- | --- | --- | --- |
| 241 | `include` | `includes` | One hint. Attributes `location`, `impldecl`. Mixed text is the header. |
| 242 | `include` | `resources` | One `.qrc`. Attribute `location`. Same local name as item 241, different parent. |
| 243 | `customwidget` | `customwidgets` | One promoted or plugin class. |
| 244 | `class` | `customwidget` | Promoted class name. |
| 245 | `extends` | `customwidget` | Base class Designer actually instantiates. |
| 246 | `header` | `customwidget` | Header text plus `location`. |
| 247 | `sizehint` | `customwidget` | Optional default size. |
| 248 | `addpagemethod` | `customwidget` | Optional page-factory method name. |
| 249 | `container` | `customwidget` | Optional integer flag. |
| 250 | `pixmap` | `customwidget` | Optional icon path for the widget box. |
| 251 | `script` | `customwidget` | Deprecated. |
| 252 | `sizepolicy` | `customwidget` | Deprecated in this position. |
| 253 | `properties` | `customwidget` | Deprecated. |
| 254 | `propertyspecifications` | `customwidget` | Tool tips and string-property specs. |
| 255 | `tooltip` | `propertyspecifications` | Attribute `name`. |
| 256 | `stringpropertyspecification` | `propertyspecifications` | Attributes `name`, `type`, `notr`. |

### Widgets, layouts, items, spacers

| ID | Name | Parent | Role |
| --- | --- | --- | --- |
| 257 | `class` | `widget` | Optional child, unbounded for compatibility. The real class is the attribute. |
| 258 | `property` | widget, layout, spacer, action, item, row, column | One stored property. Attributes `name` and `stdset`. |
| 259 | `attribute` | widget, action, action group, button group | Same grammar as `property`, different meaning. See item 150. |
| 260 | `script` | `widget` | Deprecated. |
| 261 | `widgetdata` | `widget` | Deprecated. |
| 262 | `row` | `widget` | Table or tree header row properties. |
| 263 | `column` | `widget` | Header column properties. |
| 264 | `item` | `widget` or `item` | List, combo, tree, or table item. Attributes `row` and `column` for cells. |
| 265 | `layout` | `widget` or `item` | A layout. Unbounded in the schema for compatibility. One is normal. |
| 266 | `widget` | `widget` | A child widget. Document order is creation order and the default tab order. |
| 267 | `action` | `widget` or `actiongroup` | An action definition. |
| 268 | `actiongroup` | `widget` or `actiongroup` | A group. Attribute `name`. |
| 269 | `addaction` | `widget` | A reference. Attribute `name`. Order is the visual order in a menu or toolbar. |
| 270 | `zorder` | `widget` | Text is a child name. Repeated elements define stacking. |
| 271 | `layout` attributes | `layout` | `class`, `name`, `stretch`, `rowstretch`, `columnstretch`, `rowminimumheight`, `columnminimumwidth`. |
| 272 | `item` | `layout` | One cell. Attributes `row`, `column`, `rowspan`, `colspan`, `alignment`. |
| 273 | `spacer` | `item` | A spacer. Attribute `name`. Properties are required by the schema, one or more. |
| 274 | Widget attributes | `widget` | `class`, `name`, and `native`. `native="true"` marks a native embed such as an ActiveX or a custom native widget. |

### Actions, button groups, connections, and tab stops

| ID | Name | Parent | Role |
| --- | --- | --- | --- |
| 275 | `buttongroup` | `buttongroups` | Attribute `name`. Properties and attributes inside. |
| 276 | `tabstop` | `tabstops` | Text is an object name. |
| 277 | `connection` | `connections` | `sender`, `signal`, `receiver`, `slot`, optional `hints`. |
| 278 | `hints` | `connection` | Wrapper for hint points. |
| 279 | `hint` | `hints` | `x`, `y`, and attribute `type`. Templates use `sourcelabel` and `destinationlabel`. |
| 280 | `signal` | `slots` | A signal signature declared on the form or custom widget. |
| 281 | `slot` | `slots` | A slot signature. |
| 282 | Action `menu` attribute | `action` | Names the menu this action opens. |

### Property value elements

Each is a child of `property` or `attribute`. The schema puts them in an `xs:choice`, so exactly one value element is legal.

| ID | Element | Shape |
| --- | --- | --- |
| 283 | `bool` | Text `true` or `false`. |
| 284 | `color` | `red`, `green`, `blue`, attribute `alpha`. |
| 285 | `cstring` | Untranslated byte string, used for buddy names. |
| 286 | `cursor` | Legacy integer shape id. |
| 287 | `cursorshape` | Current shape name. |
| 288 | `enum` | Enumerator text. |
| 289 | `font` | See item 159. |
| 290 | `iconset` | See item 165. |
| 291 | `pixmap` | See item 164. |
| 292 | `palette` | See item 162. |
| 293 | `point` | Integer `x`, `y`. |
| 294 | `rect` | Integer `x`, `y`, `width`, `height`. |
| 295 | `set` | Flag string joined with `\|`. |
| 296 | `locale` | Attributes `language`, `country`. |
| 297 | `sizepolicy` | See item 167. |
| 298 | `size` | Integer `width`, `height`. |
| 299 | `string` | Text plus `notr`, `comment` for disambiguation, `extracomment` for the translator comment, and `id`. |
| 300 | `stringlist` | Same attributes, then `string` children. |
| 301 | `number` | Signed integer. |
| 302 | `float` | Float. |
| 303 | `double` | Double. |
| 304 | `date` | `year`, `month`, `day`. |
| 305 | `time` | `hour`, `minute`, `second`. |
| 306 | `datetime` | All six fields. |
| 307 | `pointf` | Double `x`, `y`. |
| 308 | `rectf` | Double rect. |
| 309 | `sizef` | Double size. |
| 310 | `longlong` | 64-bit signed. |
| 311 | `char` | `unicode` code point. |
| 312 | `url` | Wraps `string`. |
| 313 | `uint` | Unsigned 32-bit. |
| 314 | `ulonglong` | Unsigned 64-bit. |
| 315 | `brush` | See item 161. |

### Gradient and palette details

| ID | Name | Role |
| --- | --- | --- |
| 316 | `gradient` | Stops plus geometry attributes listed in item 161. |
| 317 | `gradientStop` | `position` and `color`. |
| 318 | `colorrole` | `role` plus `brush`. |
| 319 | `active`, `inactive`, `disabled` | The three palette groups. All three are required by the schema when a palette is written. |
| 320 | `normaloff` through `selectedon` | The eight icon states. All optional. |
| 321 | Icon `theme` | Theme-icon name on `iconset`. |

### A minimal file and a connection file

A widget template is `class`, one root `widget` with `geometry` and `windowTitle`, an empty `pixmapfunction`, and an empty `connections`. A dialog with buttons adds a child `QDialogButtonBox` and two `connection` elements. A main window adds `menubar`, `centralwidget`, and `statusbar` as child widgets, with no layout. Those three shapes are the 6.8 templates that were opened.

`QFormBuilder` and `QUiLoader` read this grammar. Both are present on FreeCAD.app 1.1.3, `QFormBuilder` in `QtDesigner` and `QUiLoader` in `QtUiTools`, the latter recorded in research B and not re-imported in this session.

## uic options that change the meaning of a form

From `https://doc.qt.io/qt-6/uic.html`, fetched 2026-10-20. The page chrome says Qt 6.12. The flags are the contract a saved `.ui` has with code generation.

| ID | Option | Effect |
| --- | --- | --- |
| 322 | `-g python` or `-g cpp` | Selects the generator. View Python Code and View C++ Code in 6.8 call these. |
| 323 | `-a`, `--no-autoconnection` | Skips `connectSlotsByName`. |
| 324 | `--tr` | Replaces the translation function. |
| 325 | `--idbased` | Uses id-based translation calls. Pairs with item 191. |
| 326 | `-c pmf` or `-c string` | Connection syntax in C++. Python ignores the pointer-to-member form. |
| 327 | `--from-imports`, `--absolute-imports`, `--rc-prefix`, `--star-imports`, `--python-paths` | How resource and package imports are spelled. |
| 328 | `-d` | Print dependencies and do not emit a class. |
| 329 | `-p` and `-n` | Skip include guards, or skip implicit includes. C++ only. |
| 330 | `--postfix` and `--include` | Class-name postfix and an extra include. |

The generated Python class is `Ui_` plus the `class` element, with `setupUi` and `retranslateUi`. `retranslateUi` runs again on a language change. That split is the i18n surface of a `.ui` file.

## Where Designer's UX is weak

Each complaint is a published report. The modern-builder line is a recommendation for CBCS, mapped to checklist ids. Dates are the dates visible on the thread or the post, not a claim about when the bug was introduced.

### Paste into a layout is refused

Qt Forum, "Qt Creator: copy and paste widgets why is it so hard", `https://forum.qt.io/topic/130936/qt-creator-copy-and-paste-widgets-why-is-it-so-hard`. The reported error is "Cannot paste widgets. Designer could not find a container without a layout to paste into." The workaround in the thread is to break the layout, paste, then restore the layout, and the object inspector jumps back to the top. Another reply points at the scratch pad, which the poster had not discovered.

Maps to items 23, 27, and 41. A modern builder pastes into the layout at a chosen index, or as the last item, and keeps the inspector selection on the new widget.

### Break layout resizes the siblings

Qt Forum, "Break Layout broken ?", `https://forum.qt.io/topic/86561/break-layout-broken`, about Qt 5.10. Breaking one horizontal layout made the other horizontal layouts shrink to their content width. A Qt engineer replied that adding a widget does not require breaking the layout. Drag the widget onto the layout. The original poster still called the break step frustrating, and the resize surprising.

Maps to items 21, 41, and 34. A modern builder inserts into a layout directly and does not require a break. If a break exists, it preserves the previous visual sizes as an explicit undo step.

### Nested layout edits are thin hit targets

Qt Forum, "Adding a layout inside an existing layout", `https://forum.qt.io/topic/162687/adding-a-layout-inside-an-existing-layout`. The poster could not drop into a layout that had collapsed to a line, and did not see a way to reorder in the object inspector at first. Replies say to raise the layout minimum size while editing, or to drag in the inspector. One reply says Designer is weaker than Visual Studio was twenty years ago, and that copy and paste feels hidden.

Maps to items 20, 21, 28, and 44. A modern builder gives layouts a visible, hittable row and column structure, and reorders by dragging in the tree with a clear index.

### Splitter stretch is not in the property editor

Qt Forum, "Stretch factor property missing from QSplitter", `https://forum.qt.io/topic/128618/stretch-factor-property-missing-from-qsplitter-in-qt-designer-property-editor-bug-feature-req-by-design`. The poster shows `stretch="1,0"` on a `QVBoxLayout` and wants the same for `QSplitter`. The reply says to set the stretch on the splitter layout. The poster still had to discover that indirection.

Maps to items 39, 40, and 50. A modern builder shows stretch on the splitter beside the box-layout stretch, in the same control.

### Tab page order is easy to miss

Qt Forum, "QtCreator Designer change tab order", `https://forum.qt.io/topic/57582/qtcreator-designer-change-tab-order`. Despite the title, the question is how to move a page inside a `QTabWidget`. The poster said dragging the tab changed the cursor and did nothing. A reply said they also never found a reorder gesture. That thread is old. `qdesigner_tabwidget.cpp` on tag 6.8.3 does accept the drop and pushes `MoveTabPageCommand`, with a red bar 3 pixels wide. The gesture is still obscure.

Maps to item 127. A modern builder reorders pages from the inspector as well as from the tab bar, and shows the drop index in a target larger than 3 pixels.

### Tab order mode does not follow insert position

Qt Forum, "Struggling with setting the right focus tab order", `https://forum.qt.io/topic/121441/struggling-with-setting-the-right-focus-tab-order`. Inserting a widget into a layout appends it to the focus chain instead of placing it between its new neighbors. The poster built a custom focus manager. A Qt maintainer replied that a newly added widget has no reason to splice itself into an existing chain.

Maps to items 10 and 12. A modern builder recomputes tab order from visual reading order, and offers the explicit list as an override rather than as the only tool.

### Promoted widgets collapse to a line

Qt Forum, "working with promoted widgets in .ui file", `https://forum.qt.io/topic/38075/qt-creator-working-with-promoted-widgets-in-ui-file`. A promoted `QWidget` whose children exist only at runtime draws as a horizontal line, so placing a grid above it becomes pixel hunting. The reply is to set a minimum size and remember to remove it.

Maps to items 194 and 166. A modern builder shows a sized placeholder with the promoted class name, and does not require a fake minimum size to hit the widget.

### Child order in the file can disagree with the picture

Stack Overflow, "QtDesigner reordering radiobuttons on saving to ui file", `https://stackoverflow.com/questions/50915351/qtdesigner-reordering-radiobuttons-on-saving-to-ui-file`, asked in 2018. The radio buttons' `geometry()` values were correct, and the saved child order was not the visual order. The layout looked wrong until the `.ui` was hand-reordered. The buttons were in a button group.

Maps to items 32, 119, and 266. A modern builder writes child order to match visual order, and treats button-group membership as data that does not reshuffle the layout.

### Custom widgets and wizards fall out of the tool

Stack Overflow, "Qt Designer vs Handcoding", `https://stackoverflow.com/questions/4114389/qt-designer-vs-handcoding`. The answer says a custom widget has no real preview unless it is a separate plugin project, that Designer cannot construct a widget whose constructor takes more than the parent argument, and that a `QWizard` is awkward enough that the author uses one `.ui` file per page. The same answer says the naming-convention auto-connect often runs at the wrong time.

Maps to items 7, 121, 194, and 196. A modern builder previews a Python widget in-process when it is safe, and in a subprocess when it is not. It should not pretend a plugin project is required for a placeholder. Wizard pages should be first-class, because the stock box omits `QWizard`.

### Renaming steals focus in the object tree

Reddit, r/QtFramework, "Is Qt Designer really useful?", `https://www.reddit.com/r/QtFramework/comments/14muquu/is_qt_designer_really_useful/`. A comment dated 6 May 2025 says the widget tree steals focus when objects are renamed, because a refactor and a status-bar update take the keyboard. The same thread's earlier comment, 30 June 2023, treats Designer as the fast path and warns never to hand-edit the generated Python.

Maps to item 28. A modern builder renames in the inspector or on the canvas without moving focus to a status message.

### The style sheet editor is a text field

The manual page `https://doc.qt.io/qt-6/designer-stylesheet.html` only says to right-click and choose Change styleSheet. The 6.8.3 dialog does more than that page. It highlights CSS, inserts colors, fonts, gradients, and resources, and blocks OK when `QCss::Parser` fails. It still does not show which widgets on the form a selector matches.

Maps to item 176. A modern builder checks the selector against the form's object names and shows the matches before the user commits the sheet.

### What a modern builder should change first

The complaints cluster on layout editing, not on the widget catalog. The catalog is fifty-four entries and it is stable. The pain is inserting, reordering, pasting, and seeing a true picture of nested layouts and promoted classes.

For CBCS, the parity work that removes the reported pain first is items 21, 23, 28, 35 through 43, 127, and 194. Full property-type coverage, items 151 through 173, is the long tail that makes a saved file round-trip through `QUiLoader`. Menu and action editing, items 134 through 142, is a second product surface. It is real Designer parity, and shop windows described in research D are mostly nested boxes and a stack, not main-window menus.

## Gaps that remain unverified

- Designer.app was not started. The default widget box was checked by decompressing the resource in the 6.8.3 library and hashing it against tag `6.8.3`. A screenshot of the running box, including the PySide and Qt Quick plugins, was not taken.
- `Dialog_with_Buttons_Right.ui` was listed in the git tree and not opened.
- The tab-order list dialog was identified by the string `Tab Order List...`. Its columns were not opened.
- A form with its own grid writes `gridVisible`, `gridSnapX`, `gridSnapY`, `gridDeltaX`, and `gridDeltaY` through `formData` into `designerdata`. That path was read in source. A sample `.ui` was not saved from Designer.app. Device profiles are not part of that map.
- The Qt 6.12 manual and the 6.8 template disagree about a default toolbar. Trust the template file for 6.8.
- Rubber-band selection is not described on the widget-mode page. It was not confirmed in source during this pass.
- Forum posts describe Qt Creator's design mode as well as standalone Designer. The behaviors cited are the design surface both share. A difference limited to Creator's editor shell was not used as a Designer defect.

## Checklist coverage

| Area | IDs |
| --- | --- |
| Modes and connections | 1 to 12 |
| Canvas, clipboard, inspector, z-order, undo | 13 to 34 |
| Layouts, spacers, morph | 35 to 56 |
| Widget box | 57 to 110 |
| Classes outside the box | 111 to 123 |
| Containers | 124 to 133 |
| Main window, actions, button groups | 134 to 144 |
| Property types and item editors | 145 to 173 |
| Resources, style, preview, templates, translation | 174 to 193 |
| Plugins and security | 194 to 198 |
| Shortcuts and grid | 199 to 222 |
| Schema elements | 223 to 321 |
| uic flags | 322 to 330 |
