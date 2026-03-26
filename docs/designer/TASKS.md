# ChoreBoy Designer — Tasks Backlog (Qt Widgets UI Builder)

## 1) Purpose

This file is the dedicated backlog for building the **Qt Designer-like UI Builder** inside ChoreBoy Code Studio.

It converts the user PRD into an execution-oriented hierarchy:

- **Epics** (program-level outcomes)
- **Stories** (thin, testable slices)
- **Tasks** (implementation units)

This backlog is intentionally separate from the main backlog so Designer planning stays isolated under `docs/designer/`.

---

## 2) Canonical References

This backlog models behavior after the official Qt Designer and Qt for Python docs:

1. Qt Widgets Designer Manual  
   <https://doc.qt.io/qt-6/qtdesigner-manual.html>
2. Qt Designer `.ui` File Format  
   <https://doc.qt.io/qt-6/designer-ui-file-format.html>
3. Qt Widgets Designer Widget Editing Mode  
   <https://doc.qt.io/qt-6/designer-widget-mode.html>
4. Qt Widgets Designer Editing Modes  
   <https://doc.qt.io/qt-6/designer-editing-mode.html>
5. Qt for Python `QUiLoader` usage  
   <https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html>
6. `QDesignerCustomWidgetInterface` constraints  
   <https://doc.qt.io/qt-6/qdesignercustomwidgetinterface.html>

---

## 3) Status and task-card format

### Status legend

- `TODO` — not started
- `IN PROGRESS` — actively implementing
- `DONE` — implemented and validated
- `BLOCKED` — waiting on prerequisite/decision

### Task-card contract

Every task in this file contains:

- **Status**
- **Objective**
- **Primary files**
- **Automated test layer**
- **Validation method**
- **Acceptance linkage**
- **Depends on**
- **Done when**

---

## 4) Milestone mapping (PRD alignment)

- **M1** = Epic D0 + core of Epic D1
- **M2** = Epic D2
- **M3** = Epic D3
- **M4** = Epic D4
- **M5** = Epic D5

---

## Epic D0 — Foundations & Compatibility Harness

### Story D0.S1 — Runtime capability and schema probes

#### Task D0.S1.T1 — Add QtUiTools/QUiLoader probe to startup diagnostics
- **Status:** DONE
- **Objective:** Extend startup capability probe so Designer prerequisites are explicit.
- **Primary files:** `app/bootstrap/capability_probe.py`, `app/core/models.py`, `tests/unit/bootstrap/test_capability_probe.py`
- **Automated test layer:** unit, integration
- **Validation method:** run targeted pytest for capability probe checks and startup integration probe surface.
- **Acceptance linkage:** Designer Foundation Checklist DF-01
- **Depends on:** none
- **Done when:** probe report contains a stable check for QtUiTools/QUiLoader availability and messaging is actionable.

#### Task D0.S1.T2 — Add `.ui` compatibility smoke harness (read/load/tree check)
- **Status:** DONE
- **Objective:** Verify generated and fixture `.ui` payloads can be loaded through `QUiLoader`.
- **Primary files:** `tests/integration/designer/test_ui_loader_smoke.py` (new), `tests/fixtures/designer/*.ui` (new)
- **Automated test layer:** integration, runtime_parity
- **Validation method:** run targeted integration/runtime-parity suite with pass/skip clarity.
- **Acceptance linkage:** DF-02
- **Depends on:** D0.S1.T1
- **Done when:** harness validates widget tree creation for minimal forms and reports failures with file/line context.

### Story D0.S2 — Designer subsystem scaffolding

#### Task D0.S2.T1 — Create designer package layout
- **Status:** DONE
- **Objective:** Introduce explicit module boundaries for the Designer subsystem.
- **Primary files:** `app/designer/__init__.py` + package scaffolding under `app/designer/*`
- **Automated test layer:** unit (import/smoke)
- **Validation method:** run focused unit tests confirming imports and no side effects at import time.
- **Acceptance linkage:** DF-03
- **Depends on:** none
- **Done when:** package structure exists with stable ownership boundaries and import-safe modules.

#### Task D0.S2.T2 — Define model-first `UIModel` contracts
- **Status:** DONE
- **Objective:** Provide canonical in-memory form representation before canvas/IO work.
- **Primary files:** `app/designer/model/*.py` (new), `tests/unit/designer/model/test_ui_model.py` (new)
- **Automated test layer:** unit
- **Validation method:** red-green tests for widget/layout/property/connection model serialization.
- **Acceptance linkage:** DF-04
- **Depends on:** D0.S2.T1
- **Done when:** model can represent top-level widget, child hierarchy, layout nodes, and base property types.

#### Task D0.S2.T3 — Add `.ui` reader/writer skeleton aligned to Qt schema
- **Status:** DONE
- **Objective:** Add explicit IO seam for UI XML import/export.
- **Primary files:** `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`, `tests/unit/designer/io/test_ui_reader_writer.py`
- **Automated test layer:** unit
- **Validation method:** unit tests for `<ui>`, `<widget>`, `<layout>`, `<property>`, `<item>` round-trip of supported subset.
- **Acceptance linkage:** DF-05
- **Depends on:** D0.S2.T2
- **Done when:** reader and writer can round-trip minimal supported structure deterministically.

---

## Epic D1 — MVP Designer (usable visual form builder)

### Story D1.S1 — Open `.ui` in visual designer surface

#### Task D1.S1.T1 — Route `.ui` files to Designer editor surface
- **Status:** DONE
- **Objective:** Open `.ui` in visual mode instead of text editor by default.
- **Primary files:** `app/shell/main_window.py`, `app/shell/menus.py`, `app/designer/editor_surface.py` (new)
- **Automated test layer:** integration
- **Validation method:** integration test verifies `.ui` file open path selects designer editor; non-`.ui` remains text editor.
- **Acceptance linkage:** DMVP-01
- **Depends on:** D0.S2.T1
- **Done when:** `.ui` tabs instantiate designer surface with no regression to existing text-tab flows.

#### Task D1.S1.T2 — Add New Form workflow (class/name/base widget)
- **Status:** DONE
- **Objective:** Create a valid initial `.ui` form from UI dialog flow.
- **Primary files:** `app/designer/new_form_dialog.py` (new), `app/shell/menus.py`, `app/designer/io/ui_writer.py`
- **Automated test layer:** unit, integration
- **Validation method:** integration test for menu action -> file creation -> designer open.
- **Acceptance linkage:** DMVP-02
- **Depends on:** D1.S1.T1, D0.S2.T3
- **Done when:** user can create form with class/object name and base widget; result is valid `.ui` XML.

### Story D1.S2 — MVP canvas, palette, and selection

#### Task D1.S2.T1 — Implement widget palette registry (MVP set)
- **Status:** DONE
- **Objective:** Provide deterministic palette entries for initial widget subset.
- **Primary files:** `app/designer/palette/widget_registry.py`, `app/designer/palette/palette_panel.py`, tests under `tests/unit/designer/palette/`
- **Automated test layer:** unit
- **Validation method:** unit tests for registry metadata (class, icon token, allowed parents, supported props).
- **Acceptance linkage:** DMVP-03
- **Depends on:** D0.S2.T1
- **Done when:** MVP widgets from PRD appear in organized palette groups.

#### Task D1.S2.T2 — Drag/drop placement onto form canvas
- **Status:** DONE
- **Objective:** Add Qt Designer-like drag from palette to canvas with valid parent constraints.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/canvas/drop_rules.py`, integration tests
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** integration drag/drop simulation + manual GUI validation artifact.
- **Acceptance linkage:** DMVP-04
- **Depends on:** D1.S2.T1, D0.S2.T2
- **Done when:** widget instances are inserted into `UIModel` and rendered on canvas at intended target.

#### Task D1.S2.T3 — Single-widget selection + selection outline
- **Status:** DONE
- **Objective:** Allow selecting one widget from canvas/object tree and show unambiguous selection chrome.
- **Primary files:** `app/designer/canvas/selection_controller.py`, `app/designer/inspector/object_inspector.py`
- **Automated test layer:** unit, integration
- **Validation method:** integration tests for synchronized selection across canvas + object inspector.
- **Acceptance linkage:** DMVP-05
- **Depends on:** D1.S2.T2
- **Done when:** selected widget state is consistent and visible across all relevant panels.
- **Implementation note:** canvas/object-inspector selection sync is implemented with deterministic controller state and visible selection highlighting across panels.

### Story D1.S3 — MVP property editor and object naming

#### Task D1.S3.T1 — Property editor scaffold for core properties
- **Status:** DONE
- **Objective:** Edit `objectName`, text/title, enabled, checked, tooltip, placeholder, geometry (where applicable).
- **Primary files:** `app/designer/properties/property_editor.py`, `app/designer/properties/property_schema.py`
- **Automated test layer:** unit, integration
- **Validation method:** tests for property edit propagation to model and canvas render.
- **Acceptance linkage:** DMVP-06
- **Depends on:** D1.S2.T3
- **Done when:** edited values persist in model and update immediately in canvas preview.

#### Task D1.S3.T2 — Duplicate objectName validation
- **Status:** DONE
- **Objective:** Prevent silent duplicate object names.
- **Primary files:** `app/designer/validation/name_rules.py`, `app/designer/validation/validation_panel.py`
- **Automated test layer:** unit
- **Validation method:** unit tests for duplicate detection and clear diagnostic payload.
- **Acceptance linkage:** DMVP-07
- **Depends on:** D1.S3.T1
- **Done when:** duplicate names surface warning/error in validation panel and are easy to fix.

### Story D1.S4 — MVP layout operations

#### Task D1.S4.T1 — Apply VBox/HBox/Grid layout to selected container
- **Status:** DONE
- **Objective:** Implement core layout actions matching Qt Designer mental model.
- **Primary files:** `app/designer/layout/layout_commands.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** unit, integration
- **Validation method:** model-level tests + integration apply-layout action tests.
- **Acceptance linkage:** DMVP-08
- **Depends on:** D1.S2.T2
- **Done when:** layout nodes are emitted correctly in model and reflected in rendered canvas.

#### Task D1.S4.T2 — Break layout action
- **Status:** DONE
- **Objective:** Allow reverting selected container from managed layout back to absolute/child-managed arrangement.
- **Primary files:** `app/designer/layout/layout_commands.py`, `tests/unit/designer/layout/test_layout_commands.py`
- **Automated test layer:** unit
- **Validation method:** state transition tests for break-layout behavior.
- **Acceptance linkage:** DMVP-09
- **Depends on:** D1.S4.T1
- **Done when:** layout removal preserves child widgets and emits valid model state.

### Story D1.S5 — Save/Open/Preview and MVP round-trip

#### Task D1.S5.T1 — Save `.ui` from `UIModel`
- **Status:** DONE
- **Objective:** Persist supported subset as standard `.ui` XML.
- **Primary files:** `app/designer/io/ui_writer.py`, `app/shell/main_window.py`
- **Automated test layer:** unit, integration
- **Validation method:** save-open-save deterministic tests for supported subset.
- **Acceptance linkage:** DMVP-10
- **Depends on:** D0.S2.T3, D1.S3.T1, D1.S4.T1
- **Done when:** saved file loads in Designer and through `QUiLoader` for MVP widgets/layouts.

#### Task D1.S5.T2 — Open `.ui` into `UIModel`
- **Status:** DONE
- **Objective:** Parse supported `.ui` subset and populate canvas/editor state.
- **Primary files:** `app/designer/io/ui_reader.py`, `app/designer/editor_surface.py`
- **Automated test layer:** unit, integration
- **Validation method:** fixture-based parse tests + integration open existing `.ui` workflow.
- **Acceptance linkage:** DMVP-11
- **Depends on:** D1.S5.T1
- **Done when:** existing `.ui` files in supported subset are editable without data loss in supported fields.

#### Task D1.S5.T3 — Preview current form via `QUiLoader`
- **Status:** DONE
- **Objective:** Add preview action that loads current saved/in-memory `.ui` through `QUiLoader`.
- **Primary files:** `app/designer/preview/preview_service.py`, `app/designer/preview/preview_window.py`
- **Automated test layer:** integration, runtime_parity, manual_acceptance
- **Validation method:** integration preview launch checks; runtime-parity check for loader behavior.
- **Acceptance linkage:** DMVP-12
- **Depends on:** D1.S5.T1, D0.S1.T2
- **Done when:** preview window reliably renders same structure as canvas for MVP scope.

---

## Epic D2 — Qt Designer-like productivity parity

### Story D2.S1 — Object inspector parity

#### Task D2.S1.T1 — Tree view of widget/layout hierarchy
- **Status:** DONE
- **Objective:** Mirror form tree structure and support selection sync.
- **Primary files:** `app/designer/inspector/object_inspector.py`
- **Automated test layer:** unit, integration
- **Validation method:** tree synchronization tests for insert/remove/reparent operations.
- **Acceptance linkage:** DPAR-01
- **Depends on:** D1.S2.T3
- **Done when:** inspector tree is stable and accurately reflects hierarchy/layers.

#### Task D2.S1.T2 — Reparent via object inspector drag/drop (valid-only)
- **Status:** DONE
- **Objective:** Enable structural edits while enforcing hierarchy constraints.
- **Primary files:** `app/designer/inspector/object_inspector.py`, `app/designer/canvas/drop_rules.py`
- **Automated test layer:** integration
- **Validation method:** integration tests for valid and invalid reparent scenarios.
- **Acceptance linkage:** DPAR-02
- **Depends on:** D2.S1.T1
- **Done when:** valid reparent works; invalid targets produce clear feedback and no model corruption.
- **Implementation note:** reparent mutation, validation, integration coverage, undo/redo snapshots, and invalid-target feedback messaging are implemented.

### Story D2.S2 — Advanced property editor

#### Task D2.S2.T1 — Type-aware property editors (bool/enum/int/float/string)
- **Status:** DONE
- **Objective:** Move from hardcoded MVP properties to schema-driven property editing.
- **Primary files:** `app/designer/properties/property_schema.py`, `app/designer/properties/property_editor.py`, `app/designer/properties/property_editor_panel.py`, `app/designer/editor_surface.py`
- **Automated test layer:** unit
- **Validation method:** schema coverage tests for editor-control mapping and value coercion.
- **Acceptance linkage:** DPAR-03
- **Depends on:** D1.S3.T1
- **Done when:** property panel auto-selects suitable editor controls by property type.

#### Task D2.S2.T2 — Reset-to-default support
- **Status:** DONE
- **Objective:** Allow explicit reset of modified properties.
- **Primary files:** `app/designer/properties/property_editor.py`, `app/designer/properties/property_editor_panel.py`, `app/designer/editor_surface.py`
- **Automated test layer:** unit, integration
- **Validation method:** property reset transition tests.
- **Acceptance linkage:** DPAR-04
- **Depends on:** D2.S2.T1
- **Done when:** property can be reset to schema default and serialized correctly.

### Story D2.S3 — Editing ergonomics

#### Task D2.S3.T1 — Rubber-band multi-selection
- **Status:** DONE
- **Objective:** Support selecting multiple widgets in canvas.
- **Primary files:** `app/designer/canvas/selection_controller.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** GUI-driven multi-select validation + integration selection-state checks.
- **Acceptance linkage:** DPAR-05
- **Depends on:** D1.S2.T3
- **Done when:** multiple selection and selection clearing are predictable and stable.
- **Implementation note:** selection controller now tracks selection sets and canvas/inspector trees run in extended-selection mode with synchronized clearing/updates.

#### Task D2.S3.T2 — Ctrl-drag clone behavior
- **Status:** DONE
- **Objective:** Match Qt Designer clone affordance for rapid iteration.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/commands/clone_command.py`
- **Automated test layer:** integration
- **Validation method:** interaction tests for clone semantics and naming behavior.
- **Acceptance linkage:** DPAR-06
- **Depends on:** D2.S3.T1
- **Done when:** clone action duplicates widget subtree/properties with deterministic unique names.
- **Implementation note:** duplicate-selection command is implemented with deterministic unique-name cloning and undo-backed snapshots.

#### Task D2.S3.T3 — Snap-to-grid and alignment guides
- **Status:** DONE
- **Objective:** Improve placement precision and visual feedback.
- **Primary files:** `app/designer/canvas/guides.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** manual artifacts + geometry snap tests.
- **Acceptance linkage:** DPAR-07
- **Depends on:** D1.S2.T2
- **Done when:** drag/move aligns to grid or guides per active settings.
- **Implementation note:** deterministic grid-snapped geometry applies to freeform insertions and geometry edits with settings-backed snap enable/grid-size controls.

### Story D2.S4 — Undo/Redo command stack

#### Task D2.S4.T1 — Command stack infrastructure
- **Status:** DONE
- **Objective:** Back all structural/property edits with undoable commands.
- **Primary files:** `app/designer/commands/command_stack.py`, `app/designer/commands/*.py`
- **Automated test layer:** unit
- **Validation method:** undo/redo state tests per command category (layout + insertion + property + reparent + connections + tab-order + buddy + resource mutations complete; remaining future feature categories pending).
- **Acceptance linkage:** DPAR-08
- **Depends on:** D1 core stories
- **Done when:** all editor mutations flow through command stack with reliable undo/redo.
- **Implementation note:** command-stack snapshot coverage now spans insertion/layout/property/reparent/connection/tab-order/buddy/resource/promote/component/duplicate/format gestures.

---

## Epic D3 — Signals/Slots, Tab Order, Buddy tools

### Story D3.S1 — Signals/slots editing mode

#### Task D3.S1.T1 — Mode switch + connection gesture on canvas
- **Status:** DONE
- **Objective:** Add dedicated mode for connection creation (source signal -> target slot).
- **Primary files:** `app/designer/modes/signals_slots_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** interaction tests for connection creation/cancel/removal.
- **Acceptance linkage:** DADV-01
- **Depends on:** D2.S4.T1
- **Done when:** users can create/edit connections in a dedicated mode without affecting widget-edit mode.
- **Implementation note:** mode switching, dedicated connections panel (add/edit/remove), and selection-driven connection gesture authoring are implemented with undo support.

#### Task D3.S1.T2 — Serialize `<connections>` block in `.ui`
- **Status:** DONE
- **Objective:** Persist signal/slot mapping in standard Qt `.ui` shape.
- **Primary files:** `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`
- **Automated test layer:** unit
- **Validation method:** reader/writer tests for connection nodes.
- **Acceptance linkage:** DADV-02
- **Depends on:** D3.S1.T1
- **Done when:** connections round-trip through save/open and survive preview reload.

### Story D3.S2 — Tab order editing mode

#### Task D3.S2.T1 — Tab-order mode UI and ordering actions
- **Status:** DONE
- **Objective:** Let users set focus chain order visually.
- **Primary files:** `app/designer/modes/tab_order_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** focus chain validation tests + manual mode walkthrough.
- **Acceptance linkage:** DADV-03
- **Depends on:** D2.S1.T1
- **Done when:** tab order can be authored and edited predictably.
- **Implementation note:** dedicated tab-order panel reorder actions and selection-driven tab-order gesture authoring are implemented with undo support.

#### Task D3.S2.T2 — Serialize `<tabstops>` in `.ui`
- **Status:** DONE
- **Objective:** Persist authored focus order.
- **Primary files:** `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`
- **Automated test layer:** unit
- **Validation method:** unit round-trip tests for tab stop sequence.
- **Acceptance linkage:** DADV-04
- **Depends on:** D3.S2.T1
- **Done when:** saved tab order is loaded by designer and respected by preview runtime.

### Story D3.S3 — Buddy editing mode

#### Task D3.S3.T1 — Buddy assignment interactions
- **Status:** DONE
- **Objective:** Associate labels with buddy controls through dedicated mode.
- **Primary files:** `app/designer/modes/buddy_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** buddy assignment tests and visual confirmation workflow.
- **Acceptance linkage:** DADV-05
- **Depends on:** D2.S1.T1
- **Done when:** label buddy links are created/edited/removed safely.
- **Implementation note:** dedicated buddy panel plus selection-driven buddy assignment gestures are implemented with undo-backed updates.

#### Task D3.S3.T2 — Serialize buddy property mappings
- **Status:** DONE
- **Objective:** Store buddy links in `.ui` properties compatible with Qt loading.
- **Primary files:** `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`
- **Automated test layer:** unit
- **Validation method:** property serialization tests for buddy links.
- **Acceptance linkage:** DADV-06
- **Depends on:** D3.S3.T1
- **Done when:** buddy links survive save/open and behave correctly in preview.

---

## Epic D4 — Resources, Promote, and Custom Widgets

### Story D4.S1 — Resource references and icon picking

#### Task D4.S1.T1 — Resource model + `.qrc` reference support
- **Status:** DONE
- **Objective:** Support `<resources>` in `.ui` for icon/property references.
- **Primary files:** `app/designer/model/resource_model.py`, `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`, `app/designer/editor_surface.py`, `app/shell/main_window.py`
- **Automated test layer:** unit
- **Validation method:** resource section round-trip tests.
- **Acceptance linkage:** DRES-01
- **Depends on:** D1.S5.T1
- **Done when:** `.ui` contains deterministic resource references and loads with expected icon paths.
- **Implementation note:** model + reader/writer support and add-resource workflow are in place with deterministic serialization.

#### Task D4.S1.T2 — Icon picker UX and property binding
- **Status:** DONE
- **Objective:** Allow selecting icon resources in property editor.
- **Primary files:** `app/designer/properties/icon_picker.py`, `app/designer/properties/property_editor.py`
- **Automated test layer:** integration
- **Validation method:** integration UI tests for icon property assignment.
- **Acceptance linkage:** DRES-02
- **Depends on:** D4.S1.T1
- **Done when:** icons can be selected, previewed, and serialized through supported property paths.
- **Implementation note:** icon property schema + picker control + iconset read/write support are implemented for supported button widget classes.

### Story D4.S2 — Promote-to workflow

#### Task D4.S2.T1 — Promote metadata editor and storage in `.ui`
- **Status:** DONE
- **Objective:** Add designer-side promote flow for custom class placeholders.
- **Primary files:** `app/designer/properties/promote_dialog.py`, `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`
- **Automated test layer:** unit, integration
- **Validation method:** tests for promote metadata read/write.
- **Acceptance linkage:** DRES-03
- **Depends on:** D1.S3.T1, D1.S5.T1
- **Done when:** promote metadata is editable and preserved across round-trip.
- **Implementation note:** promote-selected-widget flow and `<customwidgets>` round-trip metadata storage are implemented with menu-driven editing.

#### Task D4.S2.T2 — Python custom widget registry for preview loading
- **Status:** DONE
- **Objective:** Provide runtime registry mapping placeholder classes to Python widget classes.
- **Primary files:** `app/designer/preview/custom_widget_registry.py`, `app/designer/preview/preview_service.py`
- **Automated test layer:** unit, runtime_parity
- **Validation method:** tests for registry-based widget instantiation in preview.
- **Acceptance linkage:** DRES-04
- **Depends on:** D4.S2.T1
- **Done when:** preview can resolve promoted widget mappings without requiring native Qt Designer plugins.
- **Implementation note:** custom-widget preview registry, safety gating, and runner-assisted isolated compatibility probe are implemented with integration coverage for successful/failed custom-widget imports.

---

## Epic D5 — Advanced parity, round-trip fidelity, and ecosystem polish

### Story D5.S1 — Robust `.ui` round-trip preservation

#### Task D5.S1.T1 — Unknown node/property preservation strategy
- **Status:** DONE
- **Objective:** Avoid destructive rewrites for unsupported but valid `.ui` content.
- **Primary files:** `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`
- **Automated test layer:** unit
- **Validation method:** fixture tests with unknown sections preserved through save-open-save.
- **Acceptance linkage:** DADV2-01
- **Depends on:** D1.S5.T2
- **Done when:** unsupported nodes remain intact (or explicitly reported) during round-trip.
- **Implementation note:** top-level and nested unknown node/property passthrough storage are implemented across widget/layout/property parsing and writing.

#### Task D5.S1.T2 — Stable ordering/format strategy for diff-friendly `.ui`
- **Status:** DONE
- **Objective:** Emit deterministic XML ordering for cleaner reviews/versioning.
- **Primary files:** `app/designer/io/ui_writer.py`, tests under `tests/unit/designer/io/`
- **Automated test layer:** unit
- **Validation method:** golden-file tests for deterministic output order.
- **Acceptance linkage:** DADV2-02
- **Depends on:** D5.S1.T1
- **Done when:** repeated saves of unchanged model produce byte-stable (or predictably normalized) XML.
- **Implementation note:** deterministic writer ordering and dedicated “Format UI XML” command are implemented with deterministic formatter coverage.

### Story D5.S2 — Reusable components and templates

#### Task D5.S2.T1 — Save selection as reusable component
- **Status:** DONE
- **Objective:** Export widget subtrees for reuse.
- **Primary files:** `app/designer/components/component_service.py`, `app/designer/components/component_manifest.py`
- **Automated test layer:** unit, integration
- **Validation method:** component save/load insertion tests.
- **Acceptance linkage:** DADV2-03
- **Depends on:** D2.S1.T1
- **Done when:** selected subtree can be inserted into other forms with valid hierarchy/property mapping.
- **Implementation note:** component save service, manifest metadata persistence, and menu action are implemented for selected widget subtrees.

#### Task D5.S2.T2 — Insert component from library
- **Status:** DONE
- **Objective:** Add component library browser and insert command.
- **Primary files:** `app/designer/components/component_library_panel.py`, `app/designer/components/component_service.py`, `app/designer/editor_surface.py`
- **Automated test layer:** integration
- **Validation method:** integration tests for component insertion and serialization.
- **Acceptance linkage:** DADV2-04
- **Depends on:** D5.S2.T1
- **Done when:** component insertion behaves like palette insertion with predictable naming and ownership.
- **Implementation note:** insert-component action/service and component-library panel UX are implemented with validation, undo, and deterministic objectName conflict handling.

### Story D5.S3 — Designer lint/format and team workflows

#### Task D5.S3.T1 — UI naming convention lint rules
- **Status:** DONE
- **Objective:** Add optional lint checks for object naming consistency.
- **Primary files:** `app/designer/validation/lint_rules.py`, `app/designer/validation/validation_panel.py`
- **Automated test layer:** unit
- **Validation method:** lint rule tests and severity mapping checks.
- **Acceptance linkage:** DADV2-05
- **Depends on:** D1.S3.T2
- **Done when:** naming lint diagnostics are generated deterministically and are configurable.
- **Implementation note:** deterministic objectName naming lint diagnostics are implemented with settings-driven enable/disable control.

#### Task D5.S3.T2 — Format `.ui` command
- **Status:** DONE
- **Objective:** Provide explicit formatting command separate from save.
- **Primary files:** `app/designer/io/ui_formatter.py`, `app/shell/menus.py`
- **Automated test layer:** unit, integration
- **Validation method:** command invocation tests with formatting result checks.
- **Acceptance linkage:** DADV2-06
- **Depends on:** D5.S1.T2
- **Done when:** users can format `.ui` files on demand with deterministic output.

---

## 5) Acceptance linkage index (Designer-specific)

These IDs are local to the Designer program and are mapped in `docs/ACCEPTANCE_TESTS.md` section 10A.

- **DF-xx**: foundation checks (probe + schema/loader harness)
- **DMVP-xx**: MVP designer workflow checks
- **DPAR-xx**: parity/productivity checks
- **DADV-xx**: signals/slots/tab order/buddy checks
- **DRES-xx**: resources/promote/custom-widget checks
- **DADV2-xx**: advanced round-trip/component/team workflow checks
- **DFIX-xx**: post-audit reliability/correctness hardening checks
- **DGAP-xx**: post-audit parity gap closure checks

---

## 6) Immediate execution order recommendation

D0–D5 are complete and should be treated as baseline. Execute post-audit work in this order:

1. **D6** reliability hardening (insert/undo, preview lifecycle/timeout, layout fidelity, shortcut arbitration)
2. **D7** high-impact parity (palette breadth, property depth, signal/slot picker UX, clipboard subtree ops)
3. **D8** advanced parity and polish (`.ui` breadth, canvas affordances, preview variants)
4. **D9** action/menu/toolbar authoring subsystem (QAction ecosystem parity)
5. release hardening pass (targeted + full suites, manual acceptance evidence, docs sync)

---

## 7) Post-audit follow-up backlog (2026-03-26)

These items were discovered during the Designer parity audit and smoke tests in
`docs/designer/AUDIT_REPORT.md`.

## Epic D6 — Reliability and correctness hardening

### Story D6.S1 — Insert/undo reliability hardening

#### Task D6.S1.T1 — Fix repeated drag/drop insertion parent resolution
- **Status:** DONE
- **Objective:** Make repeated palette insertion reliable by resolving a valid container parent (selected container, ancestor fallback, or root fallback) instead of silently failing after first insert.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/canvas/drop_rules.py`, `tests/unit/designer/canvas/test_form_canvas.py`, `tests/integration/designer/test_designer_save_roundtrip.py` (or new insertion-focused integration test)
- **Automated test layer:** unit, integration
- **Validation method:** targeted insertion test proving multiple consecutive drops succeed when a valid container exists and invalid targets produce explicit feedback.
- **Acceptance linkage:** DFIX-01
- **Depends on:** none
- **Done when:** users can insert multiple widgets consecutively via drag/drop without hidden failure.
- **Implementation note:** `FormCanvas` now resolves insertion parents by selected widget -> ancestor container -> root fallback, emits explicit rejection messages, and regression coverage verifies repeated insertion recovery.

#### Task D6.S1.T2 — Route canvas drop mutations through snapshot command stack
- **Status:** DONE
- **Objective:** Ensure all insertion paths (palette click, drag/drop, component insertion) are consistently undoable/redoable and mark tabs dirty.
- **Primary files:** `app/designer/editor_surface.py`, `app/designer/canvas/form_canvas.py`, `tests/unit/designer/commands/test_command_stack.py`, integration coverage for insertion undo/redo
- **Automated test layer:** unit, integration
- **Validation method:** integration test: insert via drag/drop -> Ctrl+Z removes -> Ctrl+Shift+Z restores.
- **Acceptance linkage:** DFIX-02
- **Depends on:** D6.S1.T1
- **Done when:** insertion mutation source no longer changes undo/redo behavior.
- **Implementation note:** canvas drop events now delegate to a surface-owned insertion handler (`_insert_widget_via_snapshot`) so drag/drop and palette requests share the same snapshot/dirty pipeline.

### Story D6.S2 — Preview robustness

#### Task D6.S2.T1 — Stabilize in-process preview window lifecycle
- **Status:** DONE
- **Objective:** Make Preview Form reliably visible and diagnosable during manual use.
- **Primary files:** `app/designer/editor_surface.py`, `app/designer/preview/preview_window.py`, `tests/integration/designer/test_designer_preview_loader.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** preview action opens visible window (or explicit warning) on every invocation in smoke flow.
- **Acceptance linkage:** DFIX-03
- **Depends on:** none
- **Done when:** preview command is no longer perceived as a no-op.
- **Implementation note:** `DesignerEditorSurface` now retains a strong preview-window reference (`_active_preview_widget`), closes stale preview windows before opening new ones, and clears retained state on preview destroy to keep lifecycle deterministic.

#### Task D6.S2.T2 — Add isolated preview subprocess timeout + termination diagnostics
- **Status:** DONE
- **Objective:** Prevent hangs in custom-widget isolated preview compatibility checks.
- **Primary files:** `app/designer/preview/preview_service.py`, `tests/integration/designer/test_custom_widget_isolated_preview_runner.py`
- **Automated test layer:** integration
- **Validation method:** isolated preview tests complete deterministically and return actionable timeout/import/load errors.
- **Acceptance linkage:** DFIX-04
- **Depends on:** none
- **Done when:** no isolated preview path can block indefinitely.
- **Implementation note:** isolated preview now enforces a bounded subprocess timeout, uses AppRun-aware runner command construction, and returns explicit timeout/launch diagnostics without hanging the caller.

### Story D6.S3 — `.ui` layout fidelity corrections

#### Task D6.S3.T1 — Preserve layout item attributes (`row`/`column`/span/alignment) in round-trip
- **Status:** TODO
- **Objective:** Stop dropping grid/item placement metadata on save.
- **Primary files:** `app/designer/model/layout_node.py`, `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`, `tests/unit/designer/io/test_ui_reader_writer.py`
- **Automated test layer:** unit
- **Validation method:** fixture round-trip proving `<item>` attributes are preserved.
- **Acceptance linkage:** DFIX-05
- **Depends on:** none
- **Done when:** grid-based forms survive read-write-read without layout coordinate loss.

### Story D6.S4 — Shortcut conflict/scoping hardening

#### Task D6.S4.T1 — Enforce focus-scoped Designer mode shortcuts over Run shortcuts
- **Status:** TODO
- **Objective:** Resolve F5/F6 ambiguity between designer mode actions and run/debug actions.
- **Primary files:** `app/shell/menus.py`, `app/shell/main_window.py`, `app/designer/editor_surface.py`, shortcut-related tests under `tests/unit/shell/` + integration shortcut-focus checks
- **Automated test layer:** unit, integration
- **Validation method:** with designer tab focused F5/F6 switches modes; outside designer focus F5/F6 follow run/debug semantics.
- **Acceptance linkage:** DFIX-06
- **Depends on:** none
- **Done when:** shortcut behavior is deterministic, documented, and test-covered.

## Epic D7 — Core parity expansion (high-impact usability)

### Story D7.S1 — Must-have palette expansion

#### Task D7.S1.T1 — Add missing must-have widget box entries
- **Status:** TODO
- **Objective:** Expand from 13 baseline widgets to cover basic Qt Designer form-building needs.
- **Primary files:** `app/designer/palette/widget_registry.py`, `app/designer/canvas/drop_rules.py`, related property/schema + insertion tests
- **Automated test layer:** unit, integration
- **Validation method:** each must-have widget can be inserted and serialized in supported contexts.
- **Acceptance linkage:** DGAP-01
- **Depends on:** D6.S1.T1
- **Done when:** requested must-have list is represented with valid insertion behavior.

### Story D7.S2 — Property editor depth expansion

#### Task D7.S2.T1 — Add core Qt property groups and typed editors
- **Status:** TODO
- **Objective:** Support common Qt Designer properties (`sizePolicy`, min/max size, font, palette, cursor, styleSheet, windowTitle, windowIcon, layout margins/spacing).
- **Primary files:** `app/designer/properties/property_schema.py`, `app/designer/properties/property_editor.py`, `app/designer/properties/property_editor_panel.py`, IO tests as needed
- **Automated test layer:** unit, integration
- **Validation method:** per-property edit -> model update -> save/reopen persistence checks.
- **Acceptance linkage:** DGAP-02
- **Depends on:** D7.S1.T1 (recommended), D6.S3.T1 (for layout property fidelity)
- **Done when:** expanded property surface is editable and stable across round-trip.

### Story D7.S3 — Signal/slot editor parity upgrades

#### Task D7.S3.T1 — Introduce class-aware signal/slot picklists and validation
- **Status:** TODO
- **Objective:** Replace manual free-text connection editing with discoverable, class-aware signal/slot selection.
- **Primary files:** `app/designer/connections/connection_editor_panel.py`, `app/designer/editor_surface.py`, new signal/slot metadata helper(s), tests
- **Automated test layer:** unit, integration
- **Validation method:** source/target class-aware lists + prevented invalid pairings + persisted connection output.
- **Acceptance linkage:** DGAP-03
- **Depends on:** D7.S2.T1 (recommended)
- **Done when:** users no longer need manual signal/slot string typing for common workflows.

### Story D7.S4 — Clipboard operations parity

#### Task D7.S4.T1 — Implement cut/copy/paste widget-subtree workflows
- **Status:** TODO
- **Objective:** Support subtree clipboard operations (same-form and cross-form insert where safe).
- **Primary files:** `app/designer/editor_surface.py`, model/component helpers, command stack tests/integration tests
- **Automated test layer:** unit, integration
- **Validation method:** copy/cut/paste preserves subtree and objectName uniqueness with undo/redo support.
- **Acceptance linkage:** DGAP-04
- **Depends on:** D6.S1.T2
- **Done when:** clipboard subtree operations match expected designer productivity flow.

## Epic D8 — Advanced parity and polish

### Story D8.S1 — `.ui` format breadth expansion

#### Task D8.S1.T1 — Add action-related and ordering element support
- **Status:** TODO
- **Objective:** Expand reader/writer coverage for `<action>`, `<actiongroup>`, `<addaction>`, `<zorder>`, `<buttongroup>` and related nodes.
- **Primary files:** `app/designer/model/*`, `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`, new/updated IO fixture tests
- **Automated test layer:** unit
- **Validation method:** deterministic round-trip tests for newly supported XML elements.
- **Acceptance linkage:** DGAP-05
- **Depends on:** D6.S3.T1
- **Done when:** these nodes are no longer dropped or silently rewritten away.

### Story D8.S2 — Canvas affordance polish

#### Task D8.S2.T1 — Add in-place text edit + context menu + align/distribute/adjust-size tools
- **Status:** TODO
- **Objective:** Close major interaction affordance gaps vs Qt Designer widget editing mode.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/layout/layout_commands.py`, `app/shell/menus.py`, integration/manual acceptance coverage
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** GUI walkthrough proving in-place text edits, context actions, and align/distribute sizing tools.
- **Acceptance linkage:** DGAP-06
- **Depends on:** D6.S1.T1, D6.S1.T2
- **Done when:** core widget editing affordances feel Qt Designer-like for common operations.

### Story D8.S3 — Preview variants

#### Task D8.S3.T1 — Add preview style/device-size variants
- **Status:** TODO
- **Objective:** Expose alternate style/theme/device preview modes for practical form QA.
- **Primary files:** `app/designer/preview/preview_service.py`, `app/designer/preview/preview_window.py`, `app/shell/menus.py`, integration/manual acceptance coverage
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** trigger each variant and verify deterministic preview load/error behavior.
- **Acceptance linkage:** DGAP-08
- **Depends on:** D6.S2.T1, D6.S2.T2
- **Done when:** users can run style/device preview variants without unstable lifecycle behavior.

## Epic D9 — Action/menu/toolbar authoring parity

### Story D9.S1 — QAction model + `.ui` contract

#### Task D9.S1.T1 — Add action/actiongroup/addaction model ownership
- **Status:** TODO
- **Objective:** Introduce explicit models for QAction ecosystem elements and placement references.
- **Primary files:** `app/designer/model/*`, `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`, IO fixtures/tests
- **Automated test layer:** unit
- **Validation method:** deterministic parse/serialize coverage for action graph and placement nodes.
- **Acceptance linkage:** DGAP-07
- **Depends on:** D8.S1.T1
- **Done when:** action graph nodes are represented in model and survive round-trip.

### Story D9.S2 — Action editor workflows

#### Task D9.S2.T1 — Build action editor panel (CRUD + grouping)
- **Status:** TODO
- **Objective:** Provide dedicated UI for creating/editing/removing actions and action groups.
- **Primary files:** `app/designer/actions/*` (new), `app/designer/editor_surface.py`, integration tests
- **Automated test layer:** unit, integration
- **Validation method:** panel workflows verified for create/edit/delete and deterministic naming.
- **Acceptance linkage:** DGAP-07
- **Depends on:** D9.S1.T1
- **Done when:** users can author action definitions without manual XML edits.

### Story D9.S3 — Menu/toolbar composition workflows

#### Task D9.S3.T1 — Author menu bar / toolbar action placement for `QMainWindow`
- **Status:** TODO
- **Objective:** Support action placement and ordering in menu/toolbar structures for supported form classes.
- **Primary files:** `app/designer/actions/*`, `app/designer/editor_surface.py`, `app/designer/io/*`, integration/manual acceptance tests
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** compose menu/toolbar structures, save, reopen, and verify placement persistence.
- **Acceptance linkage:** DGAP-07
- **Depends on:** D9.S2.T1
- **Done when:** authored menu/toolbar structures are persisted and re-editable.

---

## 8) Execution slices (PR-oriented checklist)

The post-audit execution plan is implemented in thin slices:

1. PR-00 docs normalization (this backlog + acceptance/test docs sync)
2. PR-01 regression tests for critical gaps
3. PR-02/03 insertion reliability + command-stack unification
4. PR-04/05 preview lifecycle + isolated timeout hardening
5. PR-06 layout item attribute fidelity
6. PR-07 shortcut arbitration
7. PR-08 diagnostics unification (Designer validation -> Problems pane)
8. PR-09/10 palette expansion batches
9. PR-11/12 property schema depth batches
10. PR-13 signal/slot picker UX
11. PR-14 clipboard subtree operations
12. PR-15 `.ui` advanced node support
13. PR-16 action/menu/toolbar authoring subsystem
14. PR-17 canvas affordance polish
15. PR-18 preview variants + final hardening/docs closure

