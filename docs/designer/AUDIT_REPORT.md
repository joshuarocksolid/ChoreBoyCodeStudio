# Qt UI Designer — Parity Audit Report

Date: 2026-03-26  
Scope: `app/designer/*`, shell integration, manual GUI smoke, Qt Designer parity gap analysis

---

## Phase 1 — Implementation Audit (Code + Tests)

### Automated validation executed

- `python3 run_tests.py -v tests/unit/designer` → **104 passed**
- `python3 run_tests.py -v tests/integration/designer/...` (all designer integration tests except isolated preview file) → **16 passed**
- `python3 run_tests.py -v tests/runtime_parity/test_designer_quiloader_runtime.py` → **1 passed**
- `python3 run_tests.py -v tests/integration/designer/test_custom_widget_isolated_preview_runner.py --timeout=20` → **2 failed (timeout)**
  - Failure evidence: `/tmp/designer_isolated_preview.junit.xml`
  - Both tests timed out in `probe_ui_xml_compatibility_isolated()` waiting on `subprocess.run(...)`.

### Subsystem findings table

| Subsystem | Status | Findings |
|---|---|---|
| Model | **OK** | Concrete dataclass model contracts exist and are covered by unit tests. No stubs found. |
| IO (reader/writer/formatter) | **ISSUE** | Strong baseline round-trip support (connections/resources/tabstops/customwidgets/unknown nodes), but layout `<item>` attributes (grid row/column/span/alignment) are not modeled and are dropped on save. |
| Canvas | **ISSUE** | Drag/drop insertion path is brittle: after first insertion, selection often points to non-container and subsequent inserts fail silently; drop path also bypasses command-stack dirty/undo wiring. |
| Palette | **OK** | 13-widget baseline registry implemented and filter/search UI present. |
| Inspector | **OK** | Tree sync + reparent path is implemented and tested. |
| Properties | **ISSUE** | Typed/grouped editor exists, but schema depth is narrow relative to Qt Designer property surface. |
| Connections | **ISSUE** | Add/edit/remove exists, but editor is table/manual-text oriented; no class-aware signal/slot picklists or slot discovery. |
| Modes | **OK** | Widget/Signals/Buddy/Tab Order modes and panel switching are implemented. |
| Layout | **OK** | HBox/VBox/Grid + break-layout implemented for modeled structures. |
| Commands | **ISSUE** | Snapshot undo/redo works for many surface actions, but drag/drop canvas mutations are not consistently routed through snapshot commands. |
| Preview | **ISSUE** | In-process preview call exists but manual smoke could not observe preview window reliably; isolated preview subprocess has no timeout and can hang integration/runtime paths. |
| Validation | **ISSUE** | Validation panel with severity icons exists, but duplicate-name scenario is prevented during property edit (cannot be exercised via normal workflow), and diagnostics UX is split between designer validation list vs shell Problems panel. |
| Components | **OK** | Save/list/insert component workflows implemented with manifest-backed storage and tests. |
| Shell integration | **ISSUE** | `.ui` routing and action dispatch are implemented, but shortcut semantics are ambiguous/inconsistent (Designer modes share F5/F6 with Run/Continue definitions). |
| Styling | **OK** | Dedicated designer styles are comprehensive across panels and controls; manual light/dark usability looked acceptable. |

---

## Prioritized issue list (critical / major / minor)

### Critical

1) **Canvas drag/drop insertion becomes effectively single-use in common flow**  
- **File/lines:** `app/designer/canvas/form_canvas.py:76-99,130-159`  
- **Details:** `insert_widget_by_class_name()` uses current selection as parent. After first insert, selection becomes inserted widget (e.g., `QPushButton`), which is not a valid container. Subsequent insertions fail (often silently through Qt drop path).  
- **Suggested fix:** Add explicit parent-resolution strategy:
  - prefer selected container;
  - otherwise climb to nearest valid ancestor;
  - fallback to root widget;
  - surface explicit user feedback on invalid target.
- **Status (2026-03-26):** **RESOLVED (PR-01)**  
  Insert parent resolution now walks selected widget -> ancestor containers -> root fallback and emits explicit rejection messaging when no valid target exists. Regression coverage:
  - `tests/unit/designer/canvas/test_form_canvas.py::test_insert_widget_by_class_name_resolves_container_from_ancestor_selection`
  - `tests/unit/designer/canvas/test_form_canvas.py::test_insert_widget_by_class_name_falls_back_to_root_when_selection_invalid`
  - `tests/unit/designer/canvas/test_form_canvas.py::test_insert_widget_by_class_name_falls_back_when_selection_is_non_container`
  - `tests/integration/designer/test_designer_save_roundtrip.py::test_designer_repeated_insertions_recover_after_non_container_selection`

2) **Drop-event mutations bypass snapshot command tracking**  
- **File/lines:** `app/designer/canvas/form_canvas.py:130-142`, `app/designer/editor_surface.py:782-803`  
- **Details:** Palette button path `_handle_palette_insert_request()` wraps mutations with before/after snapshot + dirty state, but raw drop path mutates model directly in canvas without snapshot push.  
- **Suggested fix:** Route all insertion events (double-click and drop) through one surface-level mutation API that always records command stack snapshots and dirty state.
- **Status (2026-03-26):** **RESOLVED (PR-02)**  
  Canvas drop insertion is now delegated to a surface-owned insertion handler that shares the same snapshot mutation pipeline as palette insertion. Regression coverage:
  - `tests/unit/designer/test_editor_surface.py::test_editor_surface_canvas_insert_route_updates_dirty_and_undo`
  - `tests/integration/designer/test_open_ui_designer_surface.py::test_open_ui_file_uses_designer_surface`

### Major

3) **Preview window not reliably observable in manual flow**  
- **File/lines:** `app/designer/editor_surface.py:153-179`, `app/shell/main_window.py:1484-1493`  
- **Details:** `preview_current_form()` calls `preview_widget.show()` and returns. No retained preview reference in surface/shell; manual smoke repeatedly observed no visible preview despite action invocation.  
- **Suggested fix:** Keep preview widget lifecycle anchored (e.g., `self._active_preview_widget`) and expose deterministic visibility/error signaling.
- **Status (2026-03-26):** **RESOLVED (PR-03)**  
  `DesignerEditorSurface` now retains a strong `_active_preview_widget` reference, closes any prior preview before opening a new one, and clears the reference on widget destruction. Regression coverage:
  - `tests/unit/designer/test_editor_surface.py::test_editor_surface_preview_retains_active_widget_reference`
  - `tests/integration/designer/test_designer_preview_loader.py::test_designer_preview_and_compatibility_actions`

4) **Isolated custom-widget preview can hang indefinitely**  
- **File/lines:** `app/designer/preview/preview_service.py:67-109`  
- **Details:** `subprocess.run(...)` has no timeout; isolated preview integration tests time out externally at 20s.  
- **Suggested fix:** Add explicit timeout + termination handling + actionable error message payload (timeout vs import failure vs loader failure).
- **Status (2026-03-26):** **RESOLVED (PR-04)**  
  Isolated preview probing now enforces an internal subprocess timeout, reports runtime-qualified timeout diagnostics, and uses a FreeCAD-safe runpy command path so probes complete deterministically under AppRun. Regression coverage:
  - `tests/unit/designer/preview/test_preview_service.py::test_probe_ui_xml_compatibility_isolated_passes_timeout`
  - `tests/unit/designer/preview/test_preview_service.py::test_probe_ui_xml_compatibility_isolated_reports_timeout`
  - `tests/unit/designer/preview/test_preview_service.py::test_build_isolated_preview_command_uses_runpy_for_freecad_runtime`
  - `tests/integration/designer/test_custom_widget_isolated_preview_runner.py::test_isolated_preview_runner_loads_promoted_custom_widget`

5) **Grid layout fidelity loss in `.ui` round-trip**  
- **File/lines:** `app/designer/io/ui_reader.py:110-123`, `app/designer/model/layout_node.py:16-22`, `app/designer/io/ui_writer.py:63-73`  
- **Details:** Layout-item attributes on `<item>` (e.g., row/column/rowspan/colspan/alignment) are not parsed/stored/re-emitted.  
- **Suggested fix:** Extend `LayoutItem` with attribute map, parse attributes in reader, write attributes in writer, and add regression fixtures for grid forms.
- **Status (2026-03-26):** **RESOLVED (PR-05)**  
  `LayoutItem` now stores per-item attributes and reader/writer round-trips `row`/`column`/`rowspan`/`colspan`/`alignment` on `<item>` nodes. Regression coverage:
  - `tests/unit/designer/io/test_ui_reader_writer.py::test_read_write_round_trip_preserves_grid_layout_item_attributes`
  - `tests/integration/designer/test_designer_save_roundtrip.py::test_designer_save_roundtrip_preserves_grid_layout_item_attributes`

6) **Mode/run shortcut overlap (F5/F6) is ambiguous**  
- **File/lines:** `app/shell/menus.py:548-562,571-577,648-650`, `app/designer/editor_surface.py:997-1008`  
- **Details:** F5/F6 are assigned both to designer modes and run/debug actions. Manual behavior is inconsistent/inert depending on focus and action context.  
- **Suggested fix:** Introduce explicit shortcut-scope arbitration:
  - when designer surface focused, mode shortcuts win;
  - otherwise run/debug actions win;
  - add integration tests for focus-sensitive shortcut resolution.
- **Status (2026-03-26):** **RESOLVED (PR-06)**  
  Main-window shortcut override handling now routes F5/F6 deterministically based on active focused Designer surface; run/debug actions continue to own F5/F6 outside focused Designer scope. Regression coverage:
  - `tests/unit/shell/test_shortcut_preferences.py::test_should_route_designer_mode_shortcut_only_when_designer_tab_active`
  - `tests/integration/shell/test_run_debug_toolbar_integration.py::test_f5_f6_shortcuts_are_focus_scoped_between_designer_and_run`

7) **Validation UX split and not reflected in shell Problems pane**  
- **File/lines:** `app/designer/editor_surface.py:491-557`  
- **Details:** Designer validation renders in in-surface list; shell Problems panel can show “No problems” simultaneously, creating conflicting UX states.  
- **Suggested fix:** unify diagnostics plumbing or clearly scope/descope designer validation visibility from global Problems UI.
- **Status (2026-03-26):** **RESOLVED (PR-07)**  
  Designer validation issues now emit from `DesignerEditorSurface`, are converted into shell `CodeDiagnostic` entries, and are merged into the global Problems panel alongside lint/runtime diagnostics. Regression coverage:
  - `tests/integration/designer/test_open_ui_designer_surface.py::test_designer_validation_issues_are_visible_in_global_problems_panel`
  - `tests/unit/shell/test_main_window_debug_routing.py::test_handle_designer_validation_issues_changed_rebuilds_problems`
  - `tests/unit/shell/test_main_window_debug_routing.py::test_handle_designer_validation_issues_changed_clears_file_when_empty`

8) **New-form defaults immediately trigger naming lint warnings**  
- **File/lines:** `app/designer/new_form_dialog.py:185-190`, `app/shell/main_window.py:915-928`  
- **Details:** Default root object names are class-like (`MainForm`) while naming lint expects lowerCamelCase, causing immediate warning on freshly created forms.  
- **Suggested fix:** choose lint-compliant default object naming, or exclude root form object from lint by rule.

### Minor

9) **Property surface remains shallow vs Qt Designer baseline**  
- **File/lines:** `app/designer/properties/property_schema.py:20-49`  
- **Details:** Schema lacks many commonly expected widget/layout properties (sizePolicy/min/max/font/palette/styleSheet/windowIcon/layout spacing/margins, etc.).  
- **Suggested fix:** expand schema progressively by widget class group, with typed editors and defaults.

10) **Connections panel lacks introspected signal/slot catalogs**  
- **File/lines:** `app/designer/connections/connection_editor_panel.py:29-112`  
- **Details:** Manual table editing and “Add Default Connection” are present, but no object-class-aware signal/slot chooser UX.  
- **Suggested fix:** introduce signal/slot metadata provider and combobox-based selection with compatibility filtering.

---

## Phase 2 — Smoke Test Results

Manual GUI smoke testing was executed in two passes (broad pass + focused retest of failed/blocked items).

### Checklist results

| # | Checklist item | Result | Notes |
|---|---|---|---|
| 1 | New Form workflow | **PASS** | Dialog created `.ui` and opened designer tab. |
| 2 | Palette categories/icons/filter | **PASS** | Categorized widget list and filter field present. |
| 3 | Drag/drop QPushButton | **FAIL** | First drop worked; repeated drops failed in common flow. |
| 4 | Selection sync canvas/inspector | **PASS** | Selection synchronization worked bidirectionally in tested states. |
| 5 | Property editing (objectName/text) | **PASS** | Property edits reflected in tree/panel/model view. |
| 6 | Layout + break layout | **PASS** | Layout actions executed and broke as expected in tested case. |
| 7 | Mode switching (Widget/Signals/Buddy/Tab) | **PASS** | Mode buttons switched active panel state. |
| 8 | Save / close / reopen | **PASS** | Saved `.ui` reopened with preserved structure. |
| 9 | Preview Form | **FAIL** | Menu action invoked; preview window not observed in manual runs. |
| 10 | Undo/Redo | **PASS** | Property-edit undo/redo worked (Ctrl+Z and Ctrl+Shift+Z). Insertion-path coverage remains limited by drag/drop reliability issue. |
| 11 | Duplicate objectName validation | **FAIL** | Duplicate entry is prevented early (“Object name must be unique”), so expected “create duplicate then validate” flow cannot be exercised as requested. |
| 12 | Multi-selection | **FAIL** | Blocked by inability to reliably add multiple widgets via drag/drop flow. |
| 13 | Light/Dark mode usability | **PASS** | View→Theme switching worked; designer remained readable in both modes. |

### Visual issue notes

- Repeated drag/drop operations from palette can fail silently after initial insertion (no clear in-UI error cue).
- Preview command can appear no-op during manual use.
- Designer validation list and shell Problems pane can disagree (designer warning visible while Problems pane reports no problems).

### Crash/freeze/traceback observations

- No full editor crash observed in manual smoke.
- Isolated preview integration tests produced deterministic **timeouts** in automated execution (see Phase 1 automated validation evidence).

### Manual evidence artifacts (screenshots)

- `/tmp/computer-use/97d7c.webp` (first successful drop)
- `/tmp/computer-use/42c81.webp` (subsequent drop failure)
- `/tmp/computer-use/ba359.webp` (Preview Form action invoked)
- `/tmp/computer-use/79550.webp`, `/tmp/computer-use/87cf5.webp` (dark/light themes)
- `/tmp/computer-use/860af.webp` (designer lint warning rendering)

---

## Phase 3 — Feature Gap Analysis (Qt Designer vs current implementation)

Legend: **Missing / Partial / Complete**

## A) Widget palette coverage

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Core widget box breadth | Broad standard widget families (inputs, item views, containers, displays, buttons, main-window primitives) | 13 entries (`QWidget`, `QFrame`, `QGroupBox`, `QTabWidget`, `QScrollArea`, `QLineEdit`, `QTextEdit`, `QComboBox`, `QCheckBox`, `QRadioButton`, `QLabel`, `QPushButton`, `QSpacerItem`) | **Partial** |
| Must-have missing set (examples from request) | Includes `QSpinBox`, `QDoubleSpinBox`, `QSlider`, `QProgressBar`, `QDateEdit`, `QTimeEdit`, `QDateTimeEdit`, `QDial`, `QListWidget`, `QTreeWidget`, `QTableWidget`, `QToolButton`, `QDialogButtonBox`, `QStackedWidget`, `QSplitter`, `QMenuBar`, `QToolBar`, `QStatusBar`, `QMainWindow` | Most missing | **Missing** |

## B) Property editor depth

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Property breadth by class | Extensive class-specific property sheets | Narrow baseline schema | **Partial** |
| `sizePolicy`, `minimumSize`, `maximumSize`, `font`, `palette`, `cursor`, `styleSheet`, `windowTitle`, `windowIcon`, layout spacing/margins | Supported in Qt Designer property editor | Largely absent from current schema | **Missing** |
| Grouped property UX | Grouped categories | Grouped categories present | **Partial** |

## C) Layout system

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| VBox/HBox/Grid apply/break | Supported | Supported | **Complete** |
| QFormLayout authoring | Supported | Not implemented | **Missing** |
| Layout spacing/margins editing | Supported | Not modeled | **Missing** |
| Grid row/column/span fidelity | Supported in `.ui` format | Attributes dropped in IO | **Missing** |
| Splitter workflows | Supported | No splitter palette/widget handling workflows | **Missing** |

## D) Signal/slot editor

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Visual signal/slot editing with object metadata | Supported | Signals mode + editable table | **Partial** |
| Class-aware signal/slot pick lists | Supported by configure dialogs/editor | Not implemented (manual text edits) | **Missing** |
| Custom slot authoring workflow | Supported | Not explicit | **Missing** |

## E) Action editor / menu & toolbar authoring

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| QAction/action group editor | Supported | No action editor subsystem | **Missing** |
| Menu bar / toolbar editing on form | Supported for applicable forms | No dedicated authoring surface | **Missing** |

## F) `.ui` file-format coverage

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| `class/widget/layout/item/property/tabstops/resources/customwidgets/connections` | Supported | Supported | **Complete** |
| Unknown-node preservation | Not always emphasized, but format accepts additional blocks | Implemented for many unknown nodes/properties | **Complete** |
| `action`, `actiongroup`, `addaction`, `zorder`, `buttongroup`, richer spacer/layout item metadata | Supported in Qt Designer ecosystem | Not modeled/emitted comprehensively | **Missing** |

## G) Clipboard / drag operations

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Cut/copy/paste widget subtree | Supported | Not implemented as standard clipboard flow | **Missing** |
| Cross-form paste | Supported | Not implemented | **Missing** |
| Robust drag reordering | Supported | Partial (inspector reparent, limited by insertion path issues) | **Partial** |

## H) Preview modes

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Basic preview | Supported | Implemented but manually unreliable | **Partial** |
| Preview in alternate styles/themes | Supported | Not exposed | **Missing** |
| Form factor/device-size preview | Supported | Not exposed | **Missing** |

## I) Missing editor affordances

| Feature | Qt Designer | Current implementation | Gap |
|---|---|---|---|
| Resize handles and true geometry canvas affordances | Supported | Not implemented (tree-structured canvas) | **Missing** |
| In-place text editing on canvas | Supported | Not implemented | **Missing** |
| Widget context menus | Supported | Limited/absent | **Missing** |
| Align/distribute tools | Supported | Missing | **Missing** |
| Adjust-size/size-to-content | Supported | Missing | **Missing** |
| Keyboard traversal across property editors | Supported | Partial | **Partial** |

### Gap implementation slices (complexity, files, dependencies)

| Gap | Complexity | Key files | Dependencies |
|---|---|---|---|
| Fix drag/drop parent resolution + command routing | **M** | `app/designer/canvas/form_canvas.py`, `app/designer/editor_surface.py` | None (unblocks many) |
| Add preview lifecycle retention + error visibility | **S-M** | `app/designer/editor_surface.py`, `app/designer/preview/*` | None |
| Add isolated preview timeout and diagnostics | **S** | `app/designer/preview/preview_service.py` | None |
| Preserve layout item attributes in IO | **M** | `app/designer/model/layout_node.py`, `app/designer/io/ui_reader.py`, `ui_writer.py` | None |
| Expand must-have widget palette set | **M-L** | `app/designer/palette/widget_registry.py`, `canvas/drop_rules.py`, property schema + tests | Parent/drop rules |
| Expand property schema depth | **L** | `app/designer/properties/property_schema.py`, `property_editor.py`, `property_editor_panel.py` | Widget palette expansion helpful |
| Connection editor with introspected signal/slot pickers | **L** | `app/designer/connections/connection_editor_panel.py`, mode integration | Property/schema metadata infra |
| QAction/actiongroup/menu/toolbar editing | **XL** | new `app/designer/actions/*`, IO reader/writer, surface integration | `.ui` format expansion |
| Clipboard subtree cut/copy/paste | **L** | `app/designer/editor_surface.py`, model cloning helpers, commands | Command stack centralization |
| Preview style/device variants | **M** | preview service/window + menu wiring | Stable basic preview |

### Recommended implementation order (impact-first)

1. Drag/drop command + parent-resolution fixes (restores basic usability)
2. Preview reliability + isolated timeout hardening
3. `.ui` grid/layout attribute fidelity fixes
4. Must-have widget palette expansion
5. Property-schema expansion for common Qt properties
6. Signal/slot picker UX improvements
7. Clipboard subtree workflows
8. `.ui` format expansion (`action*`, `zorder`, `buttongroup`)
9. Action Editor/menu/toolbar authoring
10. Advanced affordances (align/distribute/in-place edit/preview styles)

---

## Phase 4 — Prioritized Roadmap

## 1) Critical fixes (broken or claim-complete-but-not-reliable)

### R1. Fix repeated drag/drop insertion failure and silent rejection
- **Description:** Ensure insertion remains functional after first widget and always provides explicit feedback.
- **Files:** `app/designer/canvas/form_canvas.py`, `app/designer/editor_surface.py`, `tests/unit/designer/canvas/test_form_canvas.py`, `tests/integration/designer/test_designer_save_roundtrip.py` (or dedicated new integration test)
- **Effort:** **M**
- **Dependencies:** None
- **Acceptance criteria:**
  - Multiple consecutive drops succeed into valid parent context.
  - Invalid target emits explicit UI status/error.
  - Every insert is undoable and marks tab dirty.

### R2. Unify insertion mutation path under command stack
- **Description:** Route drop/double-click/insert-component insertions through one snapshot command pathway.
- **Files:** `app/designer/editor_surface.py`, `app/designer/canvas/form_canvas.py`, command tests
- **Effort:** **M**
- **Dependencies:** R1
- **Acceptance criteria:**
  - Ctrl+Z/Ctrl+Shift+Z works consistently for all insertion types.
  - Dirty flag behavior is consistent across insertion gestures.

### R3. Harden preview reliability and lifecycle
- **Description:** Keep preview widget alive, visible, and diagnosable.
- **Files:** `app/designer/editor_surface.py`, `app/designer/preview/preview_window.py`, integration smoke test
- **Effort:** **S-M**
- **Dependencies:** None
- **Acceptance criteria:**
  - Preview always opens or surfaces explicit failure reason.
  - Manual smoke item #9 passes reliably.

### R4. Add timeout/error hardening for isolated preview subprocess
- **Description:** Prevent indefinite hangs from custom-widget isolated probes.
- **Files:** `app/designer/preview/preview_service.py`, `tests/integration/designer/test_custom_widget_isolated_preview_runner.py`
- **Effort:** **S**
- **Dependencies:** None
- **Acceptance criteria:**
  - Isolated preview path exits deterministically (success/failure/timeout).
  - Integration tests no longer hang.

## 2) High-impact gaps (basic real-world usability)

### R5. Preserve grid/item layout attributes in `.ui` IO
- **Files:** `app/designer/model/layout_node.py`, `app/designer/io/ui_reader.py`, `ui_writer.py`, IO tests/fixtures
- **Effort:** **M**
- **Dependencies:** None
- **Acceptance criteria:** Grid row/column/span/alignment survives read-write-read round-trip.

### R6. Expand palette to must-have widget set
- **Files:** `app/designer/palette/widget_registry.py`, `canvas/drop_rules.py`, property schema/tests
- **Effort:** **M-L**
- **Dependencies:** R1
- **Acceptance criteria:** Must-have widget list from audit matrix is insertable and serializable.

### R7. Expand property schema to core Qt Designer expectations
- **Files:** `app/designer/properties/property_schema.py`, `property_editor.py`, `property_editor_panel.py`, tests
- **Effort:** **L**
- **Dependencies:** R6 (partial)
- **Acceptance criteria:** Core properties (`sizePolicy`, min/max size, font, palette, styleSheet, windowTitle/icon, layout margins/spacing) are editable and serialized.

### R8. Resolve designer/run shortcut arbitration (F5/F6)
- **Files:** `app/shell/menus.py`, `app/shell/main_window.py`, designer surface shortcuts/tests
- **Effort:** **M**
- **Dependencies:** None
- **Acceptance criteria:** Focus-scoped shortcut behavior is deterministic and covered by integration tests.

## 3) Medium-impact gaps (expected by experienced Qt Designer users)

### R9. Add signal/slot metadata pickers and validation
- **Files:** `app/designer/connections/connection_editor_panel.py`, mode integration, tests
- **Effort:** **L**
- **Dependencies:** R7 useful
- **Acceptance criteria:** Users choose from available signals/slots per object class, with invalid combos blocked.

### R10. Implement clipboard subtree operations (cut/copy/paste)
- **Files:** `app/designer/editor_surface.py`, command stack/model clone helpers, tests
- **Effort:** **L**
- **Dependencies:** R2
- **Acceptance criteria:** Subtree copy/paste and cut/paste work within and across forms.

### R11. Add `.ui` format coverage for action/actiongroup/addaction/zorder/buttongroup
- **Files:** IO reader/writer + model contracts + tests
- **Effort:** **L-XL**
- **Dependencies:** R5
- **Acceptance criteria:** Supported XML elements round-trip with deterministic formatting.

## 4) Polish items

### R12. Align/distribute/adjust-size affordances
- **Files:** canvas/layout command modules, menus, tests
- **Effort:** **L**
- **Dependencies:** R1/R2

### R13. In-place text editing and context menus
- **Files:** canvas/editor surface interaction layer
- **Effort:** **M-L**
- **Dependencies:** R1

### R14. Preview style/device variants
- **Files:** preview service/menu wiring
- **Effort:** **M**
- **Dependencies:** R3/R4

---

## Appendix — Suggested follow-on acceptance updates

- Add manual acceptance checks specifically for:
  - repeated drag/drop insertions,
  - preview visibility assertion,
  - insertion undo/redo consistency,
  - shortcut conflict resolution under designer focus.

---

## Program alignment update (PR-00 normalization)

The implementation program now maps these post-audit linkage families into the active backlog/acceptance docs:

- **DFIX-xx** reliability/correctness hardening tasks (D6)
- **DGAP-xx** parity-gap closure tasks (D7, D8)

Additionally, the previously identified QAction/menu/toolbar parity gap is now represented as a dedicated backlog epic:

- **D9 — Action/menu/toolbar authoring parity** in `docs/designer/TASKS.md`

This resolves the prior planning gap where action-editor parity was called out in the audit but lacked an explicit implementation track.

