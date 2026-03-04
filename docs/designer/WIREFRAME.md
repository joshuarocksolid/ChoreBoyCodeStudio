# ChoreBoy Designer — UI Wireframe Specification

## 1) Purpose

This document defines the **exact UI shell, command model, and shortcut map** for the Qt Designer-like form builder inside ChoreBoy Code Studio.

Behavior is modeled after Qt Widgets Designer concepts:

- Widget Editing Mode
- Signals/Slots Editing Mode
- Buddy Editing Mode
- Tab Order Editing Mode

References:

- Qt Widgets Designer Manual: <https://doc.qt.io/qt-6/qtdesigner-manual.html>
- Editing Modes: <https://doc.qt.io/qt-6/designer-editing-mode.html>
- Widget Editing Mode: <https://doc.qt.io/qt-6/designer-widget-mode.html>
- UI XML format: <https://doc.qt.io/qt-6/designer-ui-file-format.html>
- Qt for Python `QUiLoader`: <https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html>

---

## 2) Window composition (exact pane layout)

## 2.1 Base shell

- Designer opens as a dedicated editor surface for `.ui` files inside the existing main window.
- Top menu + command bar remain in the existing app shell pattern.
- The designer surface occupies the center region currently used by text editor tabs.

## 2.2 Dock regions

```
+----------------------------------------------------------------------------------+
| Menu Bar: File  Edit  Form  Layout  View  Tools  Help                           |
| Mode Bar: [Widget F3] [Signals/Slots F4] [Buddy] [Tab Order]  [Preview Ctrl+R] |
+--------------------------+----------------------------------+--------------------+
| Left Dock                | Center Canvas                    | Right Dock          |
| Widget Box / Palette     | Form Canvas                      | Inspector Tabs      |
| - Containers             | - Design surface                 | [Object Inspector]  |
| - Input Widgets          | - Selection overlays             | [Property Editor]   |
| - Display Widgets        | - Resize handles                 |                    |
| - Spacers/Layout items   | - Drop guides                    |                    |
+--------------------------+----------------------------------+--------------------+
| Bottom Dock: Validation + Messages                                               |
| [Validation] [Messages] [Compatibility Report]                                   |
+----------------------------------------------------------------------------------+
| Status Bar: form class/object | mode | selection count | validation summary      |
+----------------------------------------------------------------------------------+
```

## 2.3 Default size policy and splitter ratios

- Left Dock: `22%`
- Center Canvas: `56%`
- Right Dock: `22%`
- Bottom Dock collapsed by default to ~`20%` height, auto-expand when errors occur.

## 2.4 Dock behavior

- Left/Right/Bottom docks are hideable via View menu toggles.
- Object Inspector + Property Editor are tabbed in one right dock to minimize clutter.
- Bottom tabs default to Validation tab when any blocking issue exists.

---

## 3) Panel specifications

## 3.1 Left Dock — Widget Box (Palette)

### Sections (MVP)

1. **Containers**
   - QWidget (Form root)
   - QFrame
   - QGroupBox
   - QTabWidget (optional MVP-on)
   - QScrollArea (optional MVP-on)
2. **Inputs**
   - QLineEdit
   - QTextEdit
   - QComboBox
   - QCheckBox
   - QRadioButton
3. **Display**
   - QLabel
4. **Buttons/Actions**
   - QPushButton
5. **Layout Items**
   - QSpacerItem

### Interaction

- Drag widget from palette and drop on canvas target.
- Hover target highlights valid drop zones.
- Invalid parent targets display “not allowed” cursor and status hint.

## 3.2 Center — Form Canvas

### Canvas responsibilities

- Render live editable form from internal `UIModel`.
- Show selection rectangle and resize handles (where layout allows).
- Display layout boundaries and spacing guides.
- Switch behavior by active editing mode.

### Core interactions

- Single-click = select widget
- Double-click text-capable widget = quick-edit text/title
- Drag = move (absolute mode or valid layout operation)
- Ctrl+drag = clone (parity target phase)
- Delete = remove selected widget(s)

## 3.3 Right Dock — Object Inspector tab

### Content

- Tree of form object hierarchy (widgets + layouts + spacers)
- Node label format: `<objectName> : <class>`

### Interaction

- Clicking tree node selects widget on canvas.
- Rename `objectName` inline.
- Drag/reparent where legal.

## 3.4 Right Dock — Property Editor tab

### Layout

- Search box at top (`Filter properties…`)
- Grouped sections:
  - Geometry
  - Appearance
  - Behavior
  - Layout
  - Metadata

### Property controls

- bool -> checkbox
- enum -> combo
- int/float -> spinbox
- string -> line edit / text edit
- color/font/icon -> specialized pickers (phase-based)

## 3.5 Bottom Dock — Validation/Messages/Compatibility

### Tabs

1. **Validation**
   - duplicate `objectName`
   - invalid hierarchy
   - missing top-level layout warning
2. **Messages**
   - non-blocking informational events
3. **Compatibility Report**
   - `QUiLoader` load result summary
   - unsupported node/property warnings

---

## 4) Editing modes (mode bar behavior)

## 4.1 Widget Editing Mode (default)

- Primary mode for adding/selecting/moving/resizing/layout operations.
- Mirrors Qt Designer Widget Editing Mode behavior where feasible.
- Shortcut: `F3`

## 4.2 Signals/Slots Mode

- Connection gesture:
  - choose source widget -> signal
  - choose target widget -> slot
- Writes to `.ui` `<connections>`.
- Shortcut: `F4`

## 4.3 Buddy Mode

- Label-to-control buddy linking.
- Visual line from label to target buddy widget.
- Shortcut: `F5` (proposed in ChoreBoy Designer)

## 4.4 Tab Order Mode

- Numbered focus chain overlays.
- Click sequence defines next tab stop.
- Shortcut: `F6` (proposed in ChoreBoy Designer)

---

## 5) Command specification (menu + command IDs)

## 5.1 File menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.file.new_form` | New Form… | `Ctrl+Shift+N` | Avoid conflict with global project New |
| `designer.file.open_ui` | Open UI File… | `Ctrl+Shift+O` | Opens `.ui` in designer surface |
| `designer.file.save` | Save | `Ctrl+S` | Reuses shell save |
| `designer.file.save_as` | Save As… | `Ctrl+Shift+S` | For `.ui` |
| `designer.file.revert` | Revert to Saved | `Ctrl+Alt+R` | Discard unsaved form edits |

## 5.2 Edit menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.edit.undo` | Undo | `Ctrl+Z` | Command stack-backed |
| `designer.edit.redo` | Redo | `Ctrl+Shift+Z` | Command stack-backed |
| `designer.edit.cut` | Cut | `Ctrl+X` | Selected widget subtree |
| `designer.edit.copy` | Copy | `Ctrl+C` | Selected widget subtree |
| `designer.edit.paste` | Paste | `Ctrl+V` | Into valid container |
| `designer.edit.delete` | Delete | `Del` | Remove selection |
| `designer.edit.select_all` | Select All | `Ctrl+A` | Canvas selection |

## 5.3 Form menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.form.preview` | Preview Form | `Ctrl+R` | `QUiLoader` preview parity |
| `designer.form.form_settings` | Form Settings… | `Alt+Return` | class/name/base size/margins |
| `designer.form.check_compat` | Run Compatibility Check | `Ctrl+Shift+R` | load-check and report |

## 5.4 Layout menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.layout.horizontal` | Lay Out Horizontally | `Ctrl+1` | Qt Designer convention |
| `designer.layout.vertical` | Lay Out Vertically | `Ctrl+2` | Qt Designer convention |
| `designer.layout.grid` | Lay Out in a Grid | `Ctrl+3` | Qt Designer convention |
| `designer.layout.break` | Break Layout | `Ctrl+0` | Qt Designer convention |
| `designer.layout.adjust_size` | Adjust Size | `Ctrl+J` | Fit to content |
| `designer.layout.spacer_h` | Insert Horizontal Spacer | `Ctrl+Shift+H` | |
| `designer.layout.spacer_v` | Insert Vertical Spacer | `Ctrl+Shift+V` | |

## 5.5 Mode menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.mode.widget` | Widget Editing Mode | `F3` | default mode |
| `designer.mode.signals_slots` | Signals/Slots Mode | `F4` | |
| `designer.mode.buddy` | Buddy Mode | `F5` | ChoreBoy proposed |
| `designer.mode.tab_order` | Tab Order Mode | `F6` | ChoreBoy proposed |

## 5.6 View menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.view.toggle_palette` | Widget Box | `Ctrl+Alt+1` | dock toggle |
| `designer.view.toggle_inspector` | Object Inspector | `Ctrl+Alt+2` | dock tab focus |
| `designer.view.toggle_properties` | Property Editor | `Ctrl+Alt+3` | dock tab focus |
| `designer.view.toggle_validation` | Validation Panel | `Ctrl+Alt+4` | bottom dock |
| `designer.view.snap_to_grid` | Snap to Grid | `Ctrl+Shift+G` | checkable |
| `designer.view.show_guides` | Show Guides | `Ctrl+;` | checkable |

## 5.7 Tools menu

| Command ID | Label | Shortcut | Notes |
|---|---|---:|---|
| `designer.tools.resource_manager` | Resource Manager… | `Ctrl+Shift+I` | phase 4 |
| `designer.tools.promote_widget` | Promote to… | `Ctrl+Shift+P` | phase 4 |
| `designer.tools.format_ui` | Format `.ui` | `Ctrl+Alt+F` | phase 5 |

---

## 6) Shortcut conflict policy

Some Qt Designer-conventional shortcuts overlap existing Code Studio behavior. Policy:

1. **When designer surface is focused**, Designer command binding wins.
2. **Global shell bindings** remain default outside designer surface.
3. Any unresolved conflict is surfaced in keybinding settings as a scope conflict.

Scope-aware binding is required to preserve existing editor ergonomics.

---

## 7) Selection, drag, and layout interaction rules

1. Selection outline always visible on active selection.
2. Invalid drop targets always show explicit rejection state.
3. Layout-applied containers do not allow free absolute move/resize of children unless layout is broken.
4. `objectName` is always editable and validated for uniqueness.
5. Property edits are non-destructive and undoable.

---

## 8) Light/Dark mode requirements

The Designer surface must remain usable in both themes:

- Selection outlines, guides, and validation highlights must meet contrast targets.
- Icons and badges must remain recognizable on dark panels.
- Error/warn/info states in validation panel must be theme-safe.

Validation expectation:

- Manual visual check in both light and dark mode before feature completion.

---

## 9) MVP checklist mapping (designer-specific)

This wireframe supports the following MVP behaviors:

- create new form and set class/name
- drag/drop label + line edit + button
- apply VBox layout
- edit objectName/text
- save/open `.ui` round-trip
- preview through `QUiLoader`
- no crash on invalid `.ui` (show validation/message)

