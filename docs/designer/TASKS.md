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
- **Status:** PARTIAL
- **Objective:** Add Qt Designer-like drag from palette to canvas with valid parent constraints.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/canvas/drop_rules.py`, integration tests
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** integration drag/drop simulation + manual GUI validation artifact.
- **Acceptance linkage:** DMVP-04
- **Depends on:** D1.S2.T1, D0.S2.T2
- **Done when:** widget instances are inserted into `UIModel` and rendered on canvas at intended target.

#### Task D1.S2.T3 — Single-widget selection + selection outline
- **Status:** PARTIAL
- **Objective:** Allow selecting one widget from canvas/object tree and show unambiguous selection chrome.
- **Primary files:** `app/designer/canvas/selection_controller.py`, `app/designer/inspector/object_inspector.py`
- **Automated test layer:** unit, integration
- **Validation method:** integration tests for synchronized selection across canvas + object inspector.
- **Acceptance linkage:** DMVP-05
- **Depends on:** D1.S2.T2
- **Done when:** selected widget state is consistent and visible across all relevant panels.

### Story D1.S3 — MVP property editor and object naming

#### Task D1.S3.T1 — Property editor scaffold for core properties
- **Status:** PARTIAL
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
- **Status:** PARTIAL
- **Objective:** Implement core layout actions matching Qt Designer mental model.
- **Primary files:** `app/designer/layout/layout_commands.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** unit, integration
- **Validation method:** model-level tests + integration apply-layout action tests.
- **Acceptance linkage:** DMVP-08
- **Depends on:** D1.S2.T2
- **Done when:** layout nodes are emitted correctly in model and reflected in rendered canvas.

#### Task D1.S4.T2 — Break layout action
- **Status:** PARTIAL
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
- **Status:** TODO
- **Objective:** Support selecting multiple widgets in canvas.
- **Primary files:** `app/designer/canvas/selection_controller.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** GUI-driven multi-select validation + integration selection-state checks.
- **Acceptance linkage:** DPAR-05
- **Depends on:** D1.S2.T3
- **Done when:** multiple selection and selection clearing are predictable and stable.

#### Task D2.S3.T2 — Ctrl-drag clone behavior
- **Status:** TODO
- **Objective:** Match Qt Designer clone affordance for rapid iteration.
- **Primary files:** `app/designer/canvas/form_canvas.py`, `app/designer/commands/clone_command.py`
- **Automated test layer:** integration
- **Validation method:** interaction tests for clone semantics and naming behavior.
- **Acceptance linkage:** DPAR-06
- **Depends on:** D2.S3.T1
- **Done when:** clone action duplicates widget subtree/properties with deterministic unique names.

#### Task D2.S3.T3 — Snap-to-grid and alignment guides
- **Status:** TODO
- **Objective:** Improve placement precision and visual feedback.
- **Primary files:** `app/designer/canvas/guides.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** manual artifacts + geometry snap tests.
- **Acceptance linkage:** DPAR-07
- **Depends on:** D1.S2.T2
- **Done when:** drag/move aligns to grid or guides per active settings.

### Story D2.S4 — Undo/Redo command stack

#### Task D2.S4.T1 — Command stack infrastructure
- **Status:** PARTIAL
- **Objective:** Back all structural/property edits with undoable commands.
- **Primary files:** `app/designer/commands/command_stack.py`, `app/designer/commands/*.py`
- **Automated test layer:** unit
- **Validation method:** undo/redo state tests per command category (layout + insertion + property + reparent + connections + tab-order + buddy + resource mutations complete; remaining future feature categories pending).
- **Acceptance linkage:** DPAR-08
- **Depends on:** D1 core stories
- **Done when:** all editor mutations flow through command stack with reliable undo/redo.

---

## Epic D3 — Signals/Slots, Tab Order, Buddy tools

### Story D3.S1 — Signals/slots editing mode

#### Task D3.S1.T1 — Mode switch + connection gesture on canvas
- **Status:** PARTIAL
- **Objective:** Add dedicated mode for connection creation (source signal -> target slot).
- **Primary files:** `app/designer/modes/signals_slots_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** interaction tests for connection creation/cancel/removal.
- **Acceptance linkage:** DADV-01
- **Depends on:** D2.S4.T1
- **Done when:** users can create/edit connections in a dedicated mode without affecting widget-edit mode.
- **Implementation note:** mode switching, dedicated connections panel (add/edit/remove), and a selection-driven connect gesture are implemented with undo support; direct line-drawing gesture authoring remains pending.

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
- **Status:** PARTIAL
- **Objective:** Let users set focus chain order visually.
- **Primary files:** `app/designer/modes/tab_order_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** focus chain validation tests + manual mode walkthrough.
- **Acceptance linkage:** DADV-03
- **Depends on:** D2.S1.T1
- **Done when:** tab order can be authored and edited predictably.
- **Implementation note:** dedicated tab-order panel with reorder actions is implemented and undo-backed; direct canvas gesture authoring is still pending.

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
- **Status:** PARTIAL
- **Objective:** Associate labels with buddy controls through dedicated mode.
- **Primary files:** `app/designer/modes/buddy_mode.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration, manual_acceptance
- **Validation method:** buddy assignment tests and visual confirmation workflow.
- **Acceptance linkage:** DADV-05
- **Depends on:** D2.S1.T1
- **Done when:** label buddy links are created/edited/removed safely.
- **Implementation note:** dedicated buddy panel and mode wiring are implemented with undo-backed assignments; direct canvas gesture authoring is still pending.

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
- **Status:** PARTIAL
- **Objective:** Support `<resources>` in `.ui` for icon/property references.
- **Primary files:** `app/designer/model/resource_model.py`, `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`, `app/designer/editor_surface.py`, `app/shell/main_window.py`
- **Automated test layer:** unit
- **Validation method:** resource section round-trip tests.
- **Acceptance linkage:** DRES-01
- **Depends on:** D1.S5.T1
- **Done when:** `.ui` contains deterministic resource references and loads with expected icon paths.
- **Implementation note:** model + reader/writer support and add-resource workflow are in place; icon property binding remains pending in D4.S1.T2.

#### Task D4.S1.T2 — Icon picker UX and property binding
- **Status:** PARTIAL
- **Objective:** Allow selecting icon resources in property editor.
- **Primary files:** `app/designer/properties/icon_picker.py`, `app/designer/properties/property_editor.py`
- **Automated test layer:** integration
- **Validation method:** integration UI tests for icon property assignment.
- **Acceptance linkage:** DRES-02
- **Depends on:** D4.S1.T1
- **Done when:** icons can be selected, previewed, and serialized through supported property paths.
- **Implementation note:** icon property schema + picker control + iconset read/write support are implemented for push/tool buttons; full preview-focused icon workflows and broader widget coverage remain.

### Story D4.S2 — Promote-to workflow

#### Task D4.S2.T1 — Promote metadata editor and storage in `.ui`
- **Status:** PARTIAL
- **Objective:** Add designer-side promote flow for custom class placeholders.
- **Primary files:** `app/designer/properties/promote_dialog.py`, `app/designer/io/ui_writer.py`, `app/designer/io/ui_reader.py`
- **Automated test layer:** unit, integration
- **Validation method:** tests for promote metadata read/write.
- **Acceptance linkage:** DRES-03
- **Depends on:** D1.S3.T1, D1.S5.T1
- **Done when:** promote metadata is editable and preserved across round-trip.
- **Implementation note:** promote action for selected widget and `<customwidgets>` round-trip metadata storage are implemented; richer promote management UX remains.

#### Task D4.S2.T2 — Python custom widget registry for preview loading
- **Status:** TODO
- **Objective:** Provide runtime registry mapping placeholder classes to Python widget classes.
- **Primary files:** `app/designer/preview/custom_widget_registry.py`, `app/designer/preview/preview_service.py`
- **Automated test layer:** unit, runtime_parity
- **Validation method:** tests for registry-based widget instantiation in preview.
- **Acceptance linkage:** DRES-04
- **Depends on:** D4.S2.T1
- **Done when:** preview can resolve promoted widget mappings without requiring native Qt Designer plugins.

---

## Epic D5 — Advanced parity, round-trip fidelity, and ecosystem polish

### Story D5.S1 — Robust `.ui` round-trip preservation

#### Task D5.S1.T1 — Unknown node/property preservation strategy
- **Status:** TODO
- **Objective:** Avoid destructive rewrites for unsupported but valid `.ui` content.
- **Primary files:** `app/designer/io/ui_reader.py`, `app/designer/io/ui_writer.py`
- **Automated test layer:** unit
- **Validation method:** fixture tests with unknown sections preserved through save-open-save.
- **Acceptance linkage:** DADV2-01
- **Depends on:** D1.S5.T2
- **Done when:** unsupported nodes remain intact (or explicitly reported) during round-trip.

#### Task D5.S1.T2 — Stable ordering/format strategy for diff-friendly `.ui`
- **Status:** TODO
- **Objective:** Emit deterministic XML ordering for cleaner reviews/versioning.
- **Primary files:** `app/designer/io/ui_writer.py`, tests under `tests/unit/designer/io/`
- **Automated test layer:** unit
- **Validation method:** golden-file tests for deterministic output order.
- **Acceptance linkage:** DADV2-02
- **Depends on:** D5.S1.T1
- **Done when:** repeated saves of unchanged model produce byte-stable (or predictably normalized) XML.

### Story D5.S2 — Reusable components and templates

#### Task D5.S2.T1 — Save selection as reusable component
- **Status:** TODO
- **Objective:** Export widget subtrees for reuse.
- **Primary files:** `app/designer/components/component_service.py`, `app/designer/components/component_manifest.py`
- **Automated test layer:** unit, integration
- **Validation method:** component save/load insertion tests.
- **Acceptance linkage:** DADV2-03
- **Depends on:** D2.S1.T1
- **Done when:** selected subtree can be inserted into other forms with valid hierarchy/property mapping.

#### Task D5.S2.T2 — Insert component from library
- **Status:** TODO
- **Objective:** Add component library browser and insert command.
- **Primary files:** `app/designer/components/component_library_panel.py`, `app/designer/canvas/form_canvas.py`
- **Automated test layer:** integration
- **Validation method:** integration tests for component insertion and serialization.
- **Acceptance linkage:** DADV2-04
- **Depends on:** D5.S2.T1
- **Done when:** component insertion behaves like palette insertion with predictable naming and ownership.

### Story D5.S3 — Designer lint/format and team workflows

#### Task D5.S3.T1 — UI naming convention lint rules
- **Status:** TODO
- **Objective:** Add optional lint checks for object naming consistency.
- **Primary files:** `app/designer/validation/lint_rules.py`, `app/designer/validation/validation_panel.py`
- **Automated test layer:** unit
- **Validation method:** lint rule tests and severity mapping checks.
- **Acceptance linkage:** DADV2-05
- **Depends on:** D1.S3.T2
- **Done when:** naming lint diagnostics are generated deterministically and are configurable.

#### Task D5.S3.T2 — Format `.ui` command
- **Status:** TODO
- **Objective:** Provide explicit formatting command separate from save.
- **Primary files:** `app/designer/io/ui_formatter.py`, `app/shell/menus.py`
- **Automated test layer:** unit, integration
- **Validation method:** command invocation tests with formatting result checks.
- **Acceptance linkage:** DADV2-06
- **Depends on:** D5.S1.T2
- **Done when:** users can format `.ui` files on demand with deterministic output.

---

## 5) Acceptance linkage index (Designer-specific)

These IDs are local to the Designer program and should later be linked into `docs/ACCEPTANCE_TESTS.md` once implementation starts:

- **DF-xx**: foundation checks (probe + schema/loader harness)
- **DMVP-xx**: MVP designer workflow checks
- **DPAR-xx**: parity/productivity checks
- **DADV-xx**: signals/slots/tab order/buddy checks
- **DRES-xx**: resources/promote/custom-widget checks
- **DADV2-xx**: advanced round-trip/component/team workflow checks

---

## 6) Immediate execution order recommendation

1. D0.S1 and D0.S2 (probe + model/io scaffolding)
2. D1.S1 through D1.S5 (MVP path: open/edit/save/preview)
3. D2 stories (object/property/layout productivity + undo/redo)
4. D3 and D4 (signals/slots + focus tools + custom widget workflows)
5. D5 (fidelity and ecosystem polish)

