# ChoreBoy Designer — File and Architecture Plan

## 1) Purpose

This document defines where the Qt Designer-like UI Builder should live in the repository and how it integrates with existing ChoreBoy Code Studio architecture.

It is intentionally implementation-oriented and aligned with these constraints:

- no user project code in editor process
- filesystem-first model
- explicit contracts over hidden behavior
- Python 3.9 compatibility

References:

- Qt Designer UI format: <https://doc.qt.io/qt-6/designer-ui-file-format.html>
- Qt Designer editing model: <https://doc.qt.io/qt-6/designer-editing-mode.html>
- Qt for Python `QUiLoader`: <https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html>
- Custom widget plugin constraints: <https://doc.qt.io/qt-6/qdesignercustomwidgetinterface.html>

---

## 2) Architectural principles for the Designer subsystem

1. **Model-first designer**  
   Internal `UIModel` is canonical for edit operations.
2. **Schema-aware `.ui` IO**  
   Reader/writer adhere to Qt `.ui` shape for supported subsets.
3. **Preview as compatibility oracle**  
   Every save path is validated by loading through `QUiLoader`.
4. **Hard cutover over legacy fallback chains**  
   Avoid long-lived dual paths once designer routing is stable.
5. **No hidden metadata dirs**  
   Any designer metadata uses visible dirs consistent with repo policy.

---

## 3) Proposed repository structure

## 3.1 New application subtree

```text
app/
  designer/
    __init__.py
    editor_surface.py
    new_form_dialog.py

    model/
      __init__.py
      ui_model.py
      widget_node.py
      layout_node.py
      property_value.py
      connection_model.py
      resource_model.py

    io/
      __init__.py
      ui_reader.py
      ui_writer.py
      ui_formatter.py
      roundtrip_cache.py

    canvas/
      __init__.py
      form_canvas.py
      selection_controller.py
      drop_rules.py
      guides.py

    palette/
      __init__.py
      widget_registry.py
      palette_panel.py

    inspector/
      __init__.py
      object_inspector.py

    properties/
      __init__.py
      property_schema.py
      property_editor.py
      icon_picker.py
      promote_dialog.py

    modes/
      __init__.py
      mode_controller.py
      widget_mode.py
      signals_slots_mode.py
      buddy_mode.py
      tab_order_mode.py

    layout/
      __init__.py
      layout_commands.py
      layout_rules.py

    validation/
      __init__.py
      validation_panel.py
      name_rules.py
      hierarchy_rules.py
      layout_rules.py
      lint_rules.py

    preview/
      __init__.py
      preview_service.py
      preview_window.py
      custom_widget_registry.py
      compatibility_report.py

    commands/
      __init__.py
      command_stack.py
      add_widget_command.py
      remove_widget_command.py
      set_property_command.py
      apply_layout_command.py
      break_layout_command.py
      reorder_tabstops_command.py
      set_buddy_command.py
      add_connection_command.py
```

## 3.2 New test subtree

```text
tests/
  unit/
    designer/
      model/
      io/
      palette/
      properties/
      validation/
      commands/
  integration/
    designer/
      test_open_ui_designer_surface.py
      test_designer_save_open_roundtrip.py
      test_designer_preview_loader.py
      test_designer_layout_actions.py
  runtime_parity/
    test_designer_quiloader_runtime.py
```

## 3.3 New docs subtree

```text
docs/
  designer/
    TASKS.md
    WIREFRAME.md
    ARCHITECTURE_PLAN.md
```

---

## 4) Integration points with existing system

## 4.1 Shell integration (`app/shell/*`)

### Current seam
- `MainWindow._open_file_in_editor()` always opens `CodeEditorWidget`.

### Planned seam
- Introduce document router:
  - `.ui` -> `DesignerEditorSurface`
  - others -> existing text path

### Touch points
- `app/shell/main_window.py`
  - add open routing logic for `.ui`
  - host designer widgets in editor tabs
- `app/shell/menus.py`
  - add Designer commands/modes
- `app/shell/toolbar.py`
  - optional mode/preview controls when designer tab active

## 4.2 Project subsystem integration (`app/project/*`)

- Reuse existing project root and file operations.
- Save/Open still operate on real files under project tree.
- No Designer-specific opaque storage for canonical form content.

## 4.3 Run subsystem integration (`app/run/*`, `app/runner/*`)

- No direct execution of project UI code in editor process.
- Standard form preview via `QUiLoader` can run in editor process for pure `.ui`.
- For promoted/custom widgets requiring project code:
  - use isolated preview launch path (runner-assisted preview mode).

---

## 5) Data model and contracts

## 5.1 Core model (`UIModel`)

Minimum contract:

- form metadata (`class`, root widget type, top-level `objectName`)
- widget tree
- layout tree
- per-node properties
- connections (signals/slots)
- tab order
- resources

## 5.2 `.ui` read/write contract

### Required early support

- `<ui>`
- `<class>`
- `<widget>`
- `<layout>`
- `<item>`
- `<property>`

### Later-phase support

- `<connections>`
- `<tabstops>`
- `<resources>`
- `<customwidgets>`
- unknown node/property preservation strategy

## 5.3 Validation contract

Validation emits structured diagnostics:

- severity (`error`/`warning`/`info`)
- code (stable identifier)
- message
- location (`objectName`/path/property)
- suggested action

---

## 6) Preview architecture

## 6.1 Standard preview path (MVP)

1. Serialize current model to temporary or saved `.ui`.
2. Load via `QtUiTools.QUiLoader`.
3. Show preview window.
4. Capture loader exceptions and surface in Compatibility tab.

## 6.2 Custom-widget preview path (phase 4+)

Because true Qt Designer plugin interfaces are compiled/binary plugin based, ChoreBoy Designer uses:

- promote metadata in `.ui`
- Python-side class registry
- isolated preview execution when project code must be imported

This keeps compatibility with architecture rule: user code isolation from editor process.

---

## 7) Settings and persistence plan

New global settings keys (under existing `settings.json` model), proposed:

- `designer`:
  - `snap_to_grid` (bool)
  - `grid_size` (int)
  - `show_guides` (bool)
  - `last_mode` (string)
  - `panel_visibility` (object)
  - `preview_auto_validate` (bool)

No hidden folders; all persisted through existing settings store contracts.

---

## 8) Performance and reliability targets

1. Medium form open/save (<200 widgets) should feel immediate.
2. Validation runs incrementally where possible.
3. Malformed `.ui` must not crash editor; show parser diagnostics.
4. Preview failures must preserve full traceback/details in logs or message panels.

---

## 9) Testing strategy by layer

## 9.1 Unit tests

- model transformations
- property coercion
- layout rule validation
- `.ui` node parse/write for supported schema
- command stack undo/redo semantics

## 9.2 Integration tests

- shell route `.ui` -> designer surface
- drag/drop + selection + property edits
- save/open round-trip for supported subset
- mode switching + layout commands
- preview action + compatibility report wiring

## 9.3 Runtime parity tests

- `QUiLoader` availability and minimal load path under target runtime assumptions.
- clear skip/fail diagnostics when runtime prerequisites are absent.

## 9.4 Manual acceptance

- MVP workflow evidence in both light and dark mode.
- signals/slots mode walkthrough (phase 3)
- resource/promote preview workflows (phase 4)

---

## 10) Migration and rollout plan

1. Add Designer package and tests behind explicit `.ui` routing.
2. Route `.ui` opens to designer surface once MVP save/open/preview are stable.
3. Remove temporary dual pathways when confidence is high (hard cutover principle).
4. Expand parity features in staged epics (D2 -> D5).

---

## 11) Risks and mitigations

## Risk A — Layout editing complexity

- **Mitigation:** strict layout rules in model layer; command-driven edits; unit tests before UI polish.

## Risk B — `.ui` compatibility regressions

- **Mitigation:** reader/writer fixture suite + `QUiLoader` compatibility checks on every supported shape.

## Risk C — Custom widget behavior drift

- **Mitigation:** explicit promote metadata + registry abstraction + isolated preview path.

## Risk D — Shell complexity growth

- **Mitigation:** keep designer code in `app/designer/*`; shell only routes and hosts surfaces.

---

## 12) Definition of done for architecture adoption

The architecture plan is considered adopted when:

1. `app/designer/` package skeleton exists with clear module ownership.
2. `.ui` routing seam is implemented in shell.
3. model + IO + preview contracts are tested at unit/integration level.
4. Designer docs and backlog remain isolated under `docs/designer/`.

