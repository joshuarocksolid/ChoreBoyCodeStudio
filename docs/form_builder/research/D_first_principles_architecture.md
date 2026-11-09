# A visual GUI builder for ChoreBoy Code Studio

This report is a design analysis for a layout builder inside ChoreBoy Code Studio. It is research only. No repository was modified.

The person who uses the builder is a small-business owner or hobbyist writing a PySide window that will run on a ChoreBoy appliance. The next engineer inherits a document format, a generator, and a canvas. Those two people pull in opposite directions if the file format is Qt Designer XML, and they pull together if the file is a layout tree that generates ordinary Python.

## Recommendation

Build a JSON layout document, generate a `setup_ui` module from it, and keep behavior in a separate Python file that the user and an AI assistant own. Draw the form with real stock Qt widgets inside the editor. Show user-written widgets as placeholders, and run the real window through the existing AppRun runner.

Leave branch `origin/cursor/qt-ui-designer-implementation-3f01` as history. That branch already separated a model from the file, and then spent the product on `.ui` parity and a tree. The visual canvas was never the canvas.

Scores below are judgments on a 1 to 5 scale, equal weight, 5 meaning the best fit for this product. They are not measurements.

| Candidate | Score |
| --- | ---: |
| Declarative document, generated Python, code-behind | 44 |
| Qt `.ui` as the file the user keeps | 29 |
| Python source round-trip through a syntax tree | 29 |

## Constraints that bind every option

These facts come from the current ChoreBoy Code Studio tree unless a URL says otherwise.

The appliance runtime today is FreeCAD AppRun. `docs/DISCOVERY.md` records Python 3.9.2, PySide2, and Qt 5.15.2 (`PySide2.QtPrintSupport`). `PySide2.QtUiTools` loads a real `.ui` file. The discovery note calls that a workflow of designing on another machine and copying the file across.

AppArmor, tested 2026-03-06, allows `subprocess` execution of `/bin/sh` and blocks the other binaries in that probe, including `/usr/bin/python3`. The same profile does not stop Code Studio from launching another `/opt/freecad/AppRun`. `docs/PRD.md` section 6 makes a second AppRun the runner. `docs/handoffs/TEST_SPEED_HANDOFF.md` records nested AppRun children for `run_runner.py` and `run_plugin_host.py`, and it records that AppRun plus the offscreen Qt plugin dominates test time. A preview process is possible. A preview process per drag is not affordable.

`docs/ARCHITECTURE.md` section 4.1 says the editor and user code never share a Python process. Section 4.2 says files are the source of truth. Section 4.3 prefers JSON files, JSON lines, and plain text over hidden IPC. Section 4.5 says probe capabilities instead of assuming them. Section 24 puts runtime plugin code in a separate host process. The editor does not import that code.

`tests/conftest.py` and `run_tests.py` set `QT_QPA_PLATFORM=offscreen`. Headless widget tests already exist.

Writable mounts are `noexec`. `docs/DISCOVERY.md` section 4E shows `/home/default` and `/tmp` reject `import` of a `.so`, while `/opt/freecad` is executable and read-only. A custom widget in a user project has to be pure Python. A compiled Designer plugin cannot be dropped into the project and imported. `docs/CHOREBOY_RUNTIME_PITFALLS.md` D-1 records a `SIGSEGV` when a background thread mutates widgets. Canvas rebuilds stay on the GUI thread.

The generator runs as Python inside the editor. It does not call `uic`. Packaged apps already block `shell=True` and subprocess targets other than `/bin/sh` (`docs/PACKAGING.md`). The generator does not shell out.

Today every file opens as a `CodeEditorWidget`. Markdown is the only wrapped surface, installed from `FEATURE_SPECS` in `app/features/spec.py`. `.ui` is an XML text tab. `docs/designer/TASKS.md` on current `HEAD` still describes a Designer-style builder, and the task cards checked for this report are `TODO`. `app/designer/` is gone. The canvas belongs next to the markdown feature installer. It does not belong in the plugin host, which runs in another process and cannot own widgets.

Public FreeCAD 1.1.0 was published 2026-03-25. The Linux, macOS, and Windows asset names include `py311`. The FreeCAD developers' handbook says current main targets Python 3.11 or newer and Qt 6.4, and that the decision to stop Qt 5 support was announced on 5 January 2026. The same handbook page still shows an apt line that installs PySide2 packages, so that page is mixed. What the ChoreBoy "test update" of about 2026-09-29 actually contains, including PySide6, psycopg, pg8000, and tree-sitter, was not verified in this session. Treat the migration as pending, and keep the document free of binding names.

The first draft of this report treated Code Studio's own dialogs as the layout sample. That sample is the wrong one. `rg -o` counts of `*.py`, excluding `tests`, `vendor`, and `__pycache__`, on 2026-10-20:

| Pattern | `app/` in Code Studio | Template `packages/` | `FCC_QT/packages` | Apex `packages/` |
| --- | ---: | ---: | ---: | ---: |
| `QVBoxLayout` | 114 | 87 | 140 | 212 |
| `QHBoxLayout` | 119 | 78 | 112 | 127 |
| `QGridLayout` | 0 | 1 | 10 | 15 |
| `QFormLayout` | 25 | 0 | 13 | 10 |
| `QStackedWidget` | 14 | 12 | 15 | 15 |
| `QScrollArea` | 13 | 16 | 12 | 26 |
| `addStretch` | 34 | 52 | 87 | 58 |
| `QSpacerItem` | 0 | 0 | 0 | 0 |
| `setObjectName` | 360 | 309 | 444 | 197 |
| `.ui` files | 0 | 0 | 0 | 0 |
| `QDataWidgetMapper` | 0 | 0 | 0 | 0 |

Paths: `/Users/local/Projects/ChoreBoyCodeStudio/app`, `/Users/local/Projects/ChoreBoy-PySide2-QtWidgets_Template/packages`, `/Users/local/Projects/FCC_QT/packages`, `/Users/local/Projects/apex_part_manager_on_choreboy/packages`.

Shop windows are nested boxes, a sidebar plus a `QStackedWidget`, and cards. Apex `FormCardSection` in `apex_primitives.py` is a 12-column `QGridLayout` with `setColumnStretch(col, 1)` on every column. A field is a label stacked on an input, placed with row, column, and span. `QFormLayout` is the short-dialog tool. It is absent from the template package. `QSpacerItem` does not appear. Empty space is `addStretch`. `QDockWidget` is not how these apps are built.

Styling is object-name QSS. Code Studio derives its sheet from `app/shell/theme_tokens.py`. The template stores QSS as Python modules and reapplies it by `objectName`. A generated widget with a new name will not pick up `pageContainer` or `btnPrimary`.

Data entry copies a dict or a repository row into widgets and reads the widgets back on save. None of the four trees uses `QDataWidgetMapper` or `QSqlTableModel`. A binder that emits Qt SQL models would describe an app nobody here ships.

## What the previous builder was

Branch `origin/cursor/qt-ui-designer-implementation-3f01` is commit `62da66aa153c208793059d07d53cacf30c8ecca6`. `git rev-list --count` reports 285 commits on that ref, 212 of them not in current `HEAD`, and 47 of those touching `app/designer`. The package is 7,308 lines. `app/designer/editor_surface.py` is 2,120 of them. Current `HEAD` has no `app/designer` tree.

`docs/designer/ARCHITECTURE_PLAN.md` on that branch sets an internal `UIModel` as the edit model and `.ui` XML as the file. Preview is a `QUiLoader` check. Custom widgets go to an isolated runner.

`FormCanvas` is a `QTreeWidget` with the header "FORM STRUCTURE". Dropping a palette item inserts a model node. It does not place a live control in a layout you can see. The 2026-03-26 audit (`docs/designer/AUDIT_REPORT.md`) records a first drop that works and later drops that fail, a preview that did not appear in manual use, and multi-selection blocked because the drops failed. Several of those defects were later marked resolved in the same report. The canvas at the branch tip is still the tree.

The tip model is a widget node, an optional layout node, and layout items that can hold a widget, a nested layout, or a spacer. Properties at the tip include `objectName`, `geometry`, min and max size, `sizePolicy`, spacing, margins, `styleSheet`, font, and palette. `geometry` is still a normal field, with a default of 640 by 480. That is the Designer habit of storing a rectangle even when a layout will ignore it at runtime.

The palette on that branch has no `QFormLayout`. Undo stores a full before-and-after XML snapshot and re-parses it (`app/designer/commands/command_stack.py`). A promoted custom widget does not open a window. `preview_runner.py` loads the form, calls `deleteLater()`, and prints `ISOLATED_PREVIEW_OK`. `.ui` paths open only the designer surface. There is no XML text fallback on that branch.

The useful leftovers are the split between model and widgets, snapshot undo, a widget registry, and the rule that custom-widget preview is a subprocess. The part that missed the product is the belief that Qt Designer parity is the builder.

**Redesign from first principles.** If a visual layout tool had been a starting requirement, the first screen would have been a form, and the file would have been whatever that form needs. Designer XML and a structure tree are a different product that happens to sit next to the same widgets.

**Attack the premise.** The premise behind another parity pass is that a faithful `.ui` editor becomes a good builder once the bugs are gone. The audit's own failures were about insertion, preview, and selection, and the representation underneath was still a tree of XML nodes. Fixing drop targets does not change that premise. A visual canvas on top of the same XML mirror would keep geometry, unknown XML blobs, and Designer concepts the shop owner does not use.

## The data shape

**Foundational thinking** and **model the domain** both say to name the structure before the widgets.

A form is a tree of containers. Each container has one layout or no layout. A layout has an ordered list of items. An item holds one child, plus the grid cell or the stretch that belongs to that relationship. Behavior is not in this tree.

```text
FormDocument
  format_version
  root: WidgetNode

WidgetNode
  id                  stable, survives rename
  class_name          "QLineEdit", "QPushButton", a registered custom name
  object_name         Python attribute, and the QSS object name
  properties          only values the user changed
  layout              LayoutNode or empty

LayoutNode
  kind                vbox, hbox, grid, form, stack, splitter, scroll, tab
  spacing, margins
  column_stretch[]    grid only, one weight per column
  items[]

LayoutItem
  kind                child or stretch
  child               WidgetNode when kind is child
  stretch_factor      addWidget stretch, or addStretch when kind is stretch
  row, column, row_span, column_span
  alignment
```

Illegal combinations stay out of the type. A node has one layout or none. A child item has one child. A stretch item has no child. `geometry` exists only when the parent container has no layout. Connections and field bindings are lists beside the tree.

`id` is the merge key. `object_name` is what the user reads in code and what the theme stylesheet selects. Renaming a button does not retarget every connection if connections store `id`. A theme rename is a separate, visible edit, because existing QSS keys such as `btnPrimary` are part of the look.

The generator writes `invoice_ui.py`. The user writes `invoice_window.py`. Regenerating the first file never rewrites the second. A handler that does not exist yet is a Problems-panel entry. An explicit action inserts the method once, and only if it is absent.

## Axis 1. Source of truth

### Qt `.ui` XML

Qt Widgets Designer writes an XML widget tree. The User Interface Compiler reads it and emits C++ or Python with `setupUi()`. `QUiLoader` builds the same tree at runtime. Qt's Python guide tells you not to edit the generated file, because the next run replaces it. `QUiLoader` warns that untrusted `.ui` files are a security risk, and it connects signals with string signatures. The Qt for Python tutorial says that path cannot handle Python types such as `str` or `list` on custom widgets.

Pros. The format already expresses layouts, spacers, tab order, and resources. `PySide2.QtUiTools` is present on today's appliance. An ESO Qt 5 to Qt 6 migration note says UI files themselves are independent of the Qt version.

Cons. The file is verbose, so small edits create noisy diffs. Custom Python widgets need a loader subclass or a Designer plugin. Shipping `QUiLoader` in every app adds a runtime dependency and the string-connection limit. An assistant that edits XML can break well-formedness in ways a person cannot see. The previous builder already took this path and did not become a visual tool.

Fit. Use `.ui` as an import and export, not as the file the user lives in.

### Our own document, compiled to Python

A JSON document matches `docs/ARCHITECTURE.md` section 4.3. A generator emits plain `QVBoxLayout` calls. The shipped app imports that module and does not parse the document.

Pros. Diffs can be stable if keys are ordered and only overrides are stored. A schema rejects an AI edit before it is saved. The generator is the only place that mentions PySide2 or PySide6. Hand editing is possible for someone who can read JSON. There is no loader on the appliance.

Cons. JSON is clumsier than Python for a one-line tweak. The generator must grow a case for every layout kind we promise. Users who already think in `.ui` need an importer later.

Fit. This is the structure file. Pair it with a code-behind file, which is the next option's real home.

### Generated Python with protected regions

The tool writes between markers and hopes the user leaves them alone.

Pros. One file looks simple. The runtime is plain Python.

Cons. Assistants and hobbyists edit the whole file. Markers rot. A merge conflict inside a protected region is worse than a conflict in JSON, because both sides look like real code. Qt's own `uic` documentation chooses the opposite rule. Do not edit the generated file.

Fit. Reject protected regions.

### Bidirectional Python via a syntax tree

LibCST can parse a module and print it back byte for byte, including comments. That guarantee covers tokens and comments. Recovering a layout tree is a separate problem. A layout in Python is a sequence of `addWidget`, `addLayout`, `setStretch`, and `setContentsMargins` calls. Many different sequences build the same tree, and many sequences are legal Python that are not a tree we can edit. A constrained subset means the user and the assistant may only write the subset. That removes the reason to use Python as the model.

Pros. The file the user opens is the file the app runs. Hand editing is ordinary Python. No loader.

Cons. The inverse compiler is the product. Python 3.9 on the appliance and newer syntax on a development machine will diverge the moment the subset grows. Phase 2 behavior in the same file makes every layout regen a behavior merge.

Fit. Reject round-trip as the source of truth. Offer a read-only "show the generated Python" view if people want to see the calls.

### Hybrid document plus code-behind

The document owns structure, properties, and the names of connections. The Python file owns method bodies, SQL, and anything the builder cannot see. This is the same split `uic` already teaches, with `setupUi` on one object and the window class beside it.

Pros. Layout regen does not touch behavior. An assistant can edit either file for the job it is good at. Phase 2 adds a bindings list to the document and more generated glue, without a new file format. The end app has no loader.

Cons. Two files per form. Users must learn which file to open. The builder has to create the window class on first save and then leave it alone.

Fit. This is the recommendation. The declarative document is the layout source of truth. The code-behind is the behavior source of truth. Neither file is generated into the other.

## Axis 2. Canvas rendering

### Live stock widgets in the editor

Qt Widgets Designer edits real widgets so property changes show up immediately. For a layout builder, real widgets are also the only honest `sizeHint`. A label's hint depends on font and word wrap. A mock that guesses will teach the wrong stretch.

Pros. Fidelity and theme match the runner, as long as both use the same Qt. Cost is one widget tree, which a form of a few dozen controls can stand. Overlays and an event filter can draw selection and drop targets without a second process.

Cons. A C++ crash in a widget kills the editor. Python exceptions can be caught. Segfaults cannot. User project code on this canvas would break `docs/ARCHITECTURE.md` section 4.1.

Fit. Use live widgets for the stock catalog. Install an event filter so design clicks select and insert, and so the control does not run its real click behavior. Keep a layout tree next to the canvas. That tree is the accessible structure and the keyboard structure.

### Out-of-process render

Qt Design Studio renders QML in a puppet process and sends pixmaps plus geometry back. The editor restarts the puppet after a crash. That is the right shape when the scene can abort the process.

Pros. A bad custom widget cannot kill the editor.

Cons. On this product the child has to be another AppRun. The test handoff already shows that bootstrap is heavy. Sending images on every property edit spends the low-end machine on IPC. AppArmor does not offer a general sandbox binary. The isolation you can actually buy is the runner you already have.

Fit. Do not build a puppet for phase 1. Preview means "run this window" through the existing runner. Use a subprocess probe only when loading a custom widget, which the old designer already attempted, and give it a timeout.

### `QGraphicsProxyWidget`

The proxy embeds a real `QWidget` in a graphics scene and forwards events. Qt documents that the embedded widget can differ slightly from a normal widget, that it must be a top-level widget with no other visible parent, and that `WA_PaintOnScreen` widgets and external controllers such as `QOpenGLWidget` cannot be embedded. The Qt 6.8 page says the class should not be used for high-performance cases, and that an OpenGL viewport will not work for some combinations.

Pros. Zoom and rubber-band selection come from the graphics view.

Cons. You pay for a scene, a proxy per widget, and a list of cases that do not embed. Layout fidelity is the feature. Zoom is not.

Fit. Reject for the form canvas.

### Custom-drawn mocks

Pros. Nothing the user wrote can crash the editor. Painting is cheap.

Cons. Size hints, styles, and fonts will lie. A layout tool that lies about size will make people set fixed pixels, which is the failure mode this builder exists to prevent.

Fit. Use a labeled stand-in only for a custom class the editor must not import. Do not mock `QPushButton`.

## Axis 3. Layout authoring

### Direct Qt layouts

The user drops into a `QVBoxLayout`, `QGridLayout`, `QFormLayout`, stacked layout, splitter, scroll area, or tab widget. The model stores that kind and nothing else.

Pros. What you see is what the generator emits. Completeness is a checklist of layout kinds.

Cons. Qt's vocabulary is the screen. "Break layout" and "lay out in a grid" are Designer phrases. They are accurate and they are a poor first lesson.

### Frames that map one to one onto those layouts

A frame has a direction. Vertical, horizontal, grid, and form cover the daily dialogs. Stack, splitter, scroll, and tabs are frame types on the same tree. Dropping shows an insertion line. A keyboard command wraps the selection in a frame. Another unwraps it. The layout tree stays visible.

This is the part worth copying from auto-layout tools. The mapping has to be exact. A vertical frame emits a `QVBoxLayout`, with the same child order and the same stretch.

Pros. Nested structure is visible. The generator stays boring. Non-experts get one gesture, wrap, for the thing they otherwise do by editing code.

Cons. Someone has to design the drop indicators and the wrap command well, or the frame metaphor is just Designer with new names.

Fit. This is the authoring model. **Experience first** says the wrap gesture and the insertion line matter more than a complete property grid on day one.

### Absolute positioning

A container with no layout, and `setGeometry` in the generator.

Pros. It matches widgets that really have no layout. The model can represent it by leaving `layout` empty.

Cons. It is the wrong default. People who place buttons by coordinates will not get a window that survives a resize, a longer label, or a theme font change.

Fit. Allow it only as an explicit empty layout. The canvas should say that the container will not resize its children. Do not offer a pixel grid as the normal canvas.

### How nesting, stretch, and size policy stay understandable

Drop indicators show the slot in the parent layout, including a grid cell. If the selection is not a container, insert into the nearest layout ancestor, and say so in the status bar. The old canvas failed when the selection became a button.

Size policy words map onto `QSizePolicy`. Hug contents, preferred, expanding, and fixed. Stretch on a layout item is a weight. Qt's layout page defines the real rule. Extra space follows stretch when any stretch is non-zero, and otherwise follows size policy, and minimum and maximum still win. The property editor should use the words, and a "why is this size" line should state which of those three rules fired. That line is generated from the model and from the live widget's `sizeHint`, not from a second layout engine.

Show the same form at two widths on demand. Qt has no breakpoints. Inventing them would be a second layout system.

Keyboard. Arrows move in the tree. Modified arrows reorder inside one layout. Wrap, unwrap, and delete are commands. Multi-selection is legal for siblings. Wrapping a mixed set from different parents is refused.

## Axis 4. Property editing

### Schema from `QMetaObject`

Qt's property system marks attributes `DESIGNABLE`, `STORED`, and `USER`. `QMetaProperty` can list them. Designer-style editors use that.

Pros. The long tail of properties shows up without a hand-written catalog. New stock widgets bring their properties with them.

Cons. A `QWidget` has more designable properties than a shop owner can use. Qt 6 also changed enum storage. A Qt 5 `QVariant` of an enum often stringifies as an int. A Qt 6 build of the same property stringifies as the enumerator name. A property panel that persists ints will not survive the move. Stylesheet selectors have the same split. Qt's own test expects the integer form on Qt 5 and the name on Qt 6.

### Curated catalog

Pros. The first screen can be text, buddy label, size policy, stretch, spacing, and margins.

Cons. A catalog that omits margins and stretch cannot do what layout code can do. The March 2026 audit called the old schema shallow. The branch tip later included the layout fields, and the canvas still did not show them in a form.

### Curated fields, with the meta list behind a disclosure

Fit. Ship a small catalog per class, stored as overrides in the document, enums as names. A disclosure runs `QMetaObject` for the rest and writes the same override record. Unknown properties round-trip as named values. They do not round-trip as raw XML.

### Styling

Keep a `styleSheet` property, because that is what Qt applies. Do not make raw QSS the normal path. Code Studio already derives shell styles from tokens in `app/shell/theme_tokens.py`. A form can have a small token set for spacing, font, and a few colors. The generator emits those as widget properties and one stylesheet string. People who need a selector can open the advanced field.

### Responsive behavior

Responsive here means size policy, stretch, minimum, and maximum. It does not mean media queries. The two-width preview is the teaching tool.

## Axis 5. Logic and behavior

Phase 1 should not invent a programming language. The growth path is a list on the document that the generator turns into `connect` calls and, later, into property assignments.

### Signals and slots table

A row is sender id, signal name, receiver id, method name. The generator emits `button.clicked.connect(window.save)`. Signal names come from the meta-object for stock classes, which the old `signal_slot_metadata.py` already explored. Python-only signals on custom widgets are declared in the registry, because the editor must not import the project.

Fit. This table is a view of the connections list. The list is the only stored connection model.

### Event to action rules

"When the button is clicked, call save" is the same row in plainer words. Use the words in the UI. Store the signal name.

### Node graph or blocks

Pros. They look approachable.

Cons. They are a new runtime, a new file, and a poor way to write the SQL and validation these apps already need. They do not grow out of a layout tree. They replace the code-behind.

Fit. Do not build them. A later product could, beside this one. Building them now would throw away the phase 1 file split.

### Code-behind with generated stubs

The window class is normal Python. The first time a connection names `save`, the user can insert `def save(self):` if it is missing. After that, the method is theirs.

Fit. This is the phase 2 base. **Laziness protocol** says not to add a visual language when a method body already runs on the appliance.

### Formulas and field bindings

A later list can say that `name_edit.text` reads and writes `customer.name` on a dict the window already holds. The generator writes `load_record` and `read_record`. The window calls its existing service on save. The four app trees surveyed above fill widgets by hand and contain zero `QDataWidgetMapper` uses. Qt SQL models are the wrong phase 2.

ChoreBoy apps already use SQLite and, on many machines, PostgreSQL 9.3. `docs/CHOREBOY_RUNTIME_PITFALLS.md` says that server lacks `ON CONFLICT` and JSONB. The binder does not emit SQL.

This grows from phase 1 because the document already has stable ids and a generator. The layout work stays.

## Axis 6. Extensibility

### Custom widgets

A project manifest names the class, the module, and the stock base to imitate on the canvas. The canvas builds the base and paints the class name. The runner imports the module. That keeps user code out of the editor. The class is pure Python. `docs/DISCOVERY.md` section 4E blocks importing a `.so` from the project directory.

### Components

A component is a saved subtree. Inserting it allocates new ids and object names. The component stays a document fragment.

### Plugin API

Palette entries and property editors that ship with Code Studio are ordinary editor code. Third-party editor code goes through the existing plugin host in `docs/ARCHITECTURE.md` section 24, which does not import into the editor process. Do not load Qt Designer C++ plugins. They are the wrong language, and `QUiLoader`'s plugin path is how untrusted code would enter a process.

Phase 1 needs the manifest and the component file. It does not need a new plugin surface.

## Axis 7. AI integration

The safe edit is the one a schema can reject.

An assistant that edits the JSON can add a row, wrap a frame, or rename a control. The builder validates, applies the change as commands, and shows the canvas. If validation fails, the file is unchanged.

An assistant that edits `.ui` XML can look correct and drop a grid attribute. The old reader did that until a later fix.

An assistant that edits the code-behind is welcome. An assistant that edits `invoice_ui.py` is fighting the next regen. The generated file should say that at the top, the same way Qt documents `uic` output.

Explain and fix are a headless layout pass. Build the widgets offscreen, read geometries, and report facts such as "the name field is fixed width inside an expanding column." Store nothing from that pass. The document remains the source of truth.

Prompt-to-layout is the same pipeline. The model proposes a document. The schema accepts it. The person sees a form and edits it. The assistant never becomes the writer of the Python that runs.

## Axis 8. Undo, selection, access, keyboard, tests

Undo records commands against the document. A command is data. Redo reapplies it and rebuilds the widget tree from the document. The old designer used before-and-after snapshots, and the audit found drop paths that skipped them. Snapshots are a fallback for a command we have not named. They are not the model.

Selection is a set of node ids. The canvas and the tree show the same set.

The layout tree is how a keyboard user and a screen reader see the form. The canvas alone is a picture of widgets that are eating mouse input on purpose. Every canvas command must exist as a tree command.

Tests split in two. Document commands, schema checks, and the generator run without Qt. A second set builds the widget tree with `QT_QPA_PLATFORM=offscreen`, which Code Studio already sets in `tests/conftest.py`. Assert parent, layout class, grid row and column, stretch, and `sizeHint` relationships. Do not assert pixels. Qt's test overview says the offscreen plugin is only fully supported on X11, and a public Qt Forum thread shows `hasFocus()` failing under offscreen unless the test waits. Code Studio already runs offscreen tests on developer machines that are not all X11. Follow the existing harness, and do not add focus assertions.

**Boundary discipline.** Parse the JSON at the file boundary. After that, the canvas trusts the model. Do not re-validate inside every command.

## Axis 9. What must survive PySide6

The document, the command log, the ids, and the catalog of layout kinds stay free of PySide types. Enum values are names (`Expanding`), never integers. Class names are strings.

The generator and the widget factory are the seams. One module emits imports and `exec` versus `exec_` for the probed binding. Generated code stays valid Python 3.9 until the appliance the user actually has is probed as 3.11. Do not emit `match`, or the parenthesized context-manager syntax that 3.9 rejects.

Do not store `QVariant` dumps. Do not store stylesheet selectors that depend on enum integers. Do not require `QtUiTools` in the shipped app. `QDesktopWidget` is gone in Qt 6. Do not generate it.

Probe PySide the way `docs/PRD.md` risk 3 already asks the editor to probe `QtUiTools`. The probe result picks the generator target. It does not migrate the user's document.

## Three candidates

### Qt-native `.ui`

The user keeps a `.ui` file. The editor's model is a mirror of that XML. Preview uses `QUiLoader`. Behavior is a window class that loads the file or calls `setupUi` from `uic`.

This is the previous branch, plus the visual canvas it never had. Layout completeness is real, because the format is Qt's. The costs are XML diffs, custom widgets, string-based connections, and a canvas that must stay faithful to Designer concepts such as stored geometry. Qt 5 and Qt 6 both read the structure. Stylesheet enum selectors inside those files do not mean the same thing on both.

### Declarative model, codegen, code-behind

The user keeps `invoice.form.json` and `invoice_window.py`. The builder writes `invoice_ui.py`. The canvas is live stock widgets. Custom classes are placeholders. Preview is the runner. Phase 2 adds connections and bindings to the JSON.

The shipped app is ordinary PySide calls. An assistant can edit the JSON under a schema, or the window class under normal Python review. The generator is rewritten once for PySide6. The documents are not.

### Python is the model

The user keeps one Python file. The builder parses a constrained subset with LibCST, edits the tree, and prints Python. There is no second document.

Hand editing and AI editing look ideal until the edit leaves the subset. Then the tool can no longer open the file, which is the worst failure for this audience. Layout and behavior share a file, so phase 2 rewrites the thing phase 1 just stabilized.

## Scored matrix

Scale. 5 is a strong fit for Code Studio's users, runtime, and the pending binding change. 1 is a reject. Equal weights. The total is a judgment index for comparing the three columns. Nobody measured these cells.

| Criterion | `.ui` file | Document plus codegen | Python round-trip |
| --- | ---: | ---: | ---: |
| A non-expert can build a nested form | 2 | 4 | 2 |
| The model can express Qt layouts | 5 | 4 | 3 |
| Diffs and merges stay readable | 2 | 4 | 3 |
| An AI edit is safe to accept | 2 | 5 | 2 |
| A hobbyist can hand-edit the source | 2 | 4 | 5 |
| The source survives PySide6 | 4 | 5 | 3 |
| The shipped app needs no loader | 3 | 5 | 5 |
| Phase 2 does not replace phase 1 | 3 | 5 | 2 |
| Editor and user code stay split | 4 | 5 | 3 |
| We can build it without another parity project | 2 | 3 | 1 |
| **Total** | **29** | **44** | **29** |

Notes on the close call between the two low scores. `.ui` wins completeness because the format already has every layout item. Round-trip wins hand editing because the file is Python. Both lose the product. The `.ui` score of 3 on "no loader" assumes a generated `setupUi`. Shipping `QUiLoader` in the app drops that cell to 2 and the total to 28.

Doubling the two product criteria, non-expert authoring and phase 2 growth, moves the totals to 34, 53, and 33. The order does not change. That sensitivity is still a judgment, not an experiment.

## Why the middle column

The shop owner needs to see a form resize. The maintainer needs a file an assistant cannot silently corrupt, and a Qt 6 port that touches the generator. Saved forms stay as they are. The middle column is the one that gives both of those without a loader and without a visual programming language.

A pass over the designer branch recommended keeping `.ui` plus `QUiLoader` as the app contract. The four application trees above contain zero `.ui` files. The generator should emit the imperative PySide2 those apps already run. This session did not search the AppRun image for a `uic` executable. The generator is in-process Python so that search does not block the design.

The `.ui` column is the right import path on the day someone brings an existing Designer file. It is the wrong daily file, and this repo already spent 47 designer commits learning that a tree of that file does not become the product.

The Python column is the right read-only view of generator output. It is the wrong place to recover a layout after an assistant inserts a helper method between two `addWidget` calls.

**Never block on the human.** JSON is the choice. Code Studio's architecture already prefers JSON. YAML is easier to type and harder to validate. The operator could choose YAML later without changing the tree, the canvas, or the generator's input object. TOML fits a flat config better than a nested tree.

## Roadmap

### Phase 0, spikes

Run the spikes in the next section before writing the editor surface. They are the design space check this report could not execute. The brief was research only.

### Phase 1, layouts

Document schema. Commands. Generator for vertical box, horizontal box, grid with column span and per-column stretch, form rows, and `addStretch`. Live canvas, insertion line, wrap, unwrap, layout tree. `setObjectName` on every node. Curated properties, including size policy and stretch. Undo. Offscreen geometry tests. Create the code-behind once. The host is a center-tab surface registered the way markdown is, in `app/features/spec.py`.

### Phase 1b, the rest of the layout checklist

Stack, splitter, scroll, tabs, alignment. Token set that emits spacing and a short stylesheet, using object names the existing QSS already selects. Components, including a 12-column card like Apex `FormCardSection`. Custom-widget placeholders. Keyboard reorder. Two-width preview. `QSpacerItem` stays out until a real file needs it. The survey found none.

### Phase 2, behavior

Connection list and the plain-language table. Insert a missing method on demand. Generate `load_record` and `read_record` against a dict the window already owns. Leave SQL in the service the app already calls.

Stop there. A node editor is a different product.

## Spikes that de-risk the choice

Each spike ends in an observation. The code from the spike can be thrown away.

1. **Live canvas.** Build one offscreen dialog with a nested vertical box and a 12-column grid like Apex `FormCardSection`. Drag logic can be a function call if a mouse is unavailable. Assert positions after resize. Pass if `sizeHint` of a word-wrapped label changes the column. Fail if a mock rectangle was enough, which would reopen the mock-canvas option.

2. **One document, two generators.** Emit PySide2 and PySide6 from the same JSON. Diff the bodies after the import lines. Pass if the layout calls match and enums are names. This is the Qt 6 spike. Do it before the canvas grows.

3. **Runner preview cost.** Launch one generated window through the existing AppRun runner and record cold start. The test handoff already says this bootstrap is heavy. Pass if a single preview is acceptable. Fail if the number is so large that preview cannot be a button. A slow number means preview should be rare. It does not justify a pixmap pipeline.

4. **Custom widget boundary.** Placeholder in-process, real class only in the runner, with a timeout. Pass if a raising `__init__` becomes an error in the Problems panel and the editor process is still alive. A segfault fixture is optional and only inside the runner.

5. **Schema versus XML versus Python, with an assistant.** Give the same five forms to an assistant as JSON schema, `.ui`, and unconstrained Python. Accept only output that validates or still parses as the subset. This spike is the one that could overturn the AI column of the matrix. If JSON validation fails as often as XML, the safety score was too high.

6. **Round-trip probe.** Parse the existing shell dialogs, starting with `app/shell/settings_dialog_general.py`, with LibCST, and count how many layout trees recover without a special case. Pass for the Python candidate only if most of those files recover. Expect a fail. If they recover cleanly, reopen candidate 3.

7. **Words for size policy.** A throwaway panel with hug, preferred, expanding, and fixed, plus a "why is this size" line. Pass if a person who did not write it can predict which widget grows when the window grows. This is the experience spike for axis 3.

8. **`.ui` import, one way.** Load one Designer file that contains a grid with row and column spans through a reader into the document, then generate Python. Pass if spans survive. This checks the import path. It does not make `.ui` the source of truth.

9. **Command replay.** Apply twenty commands, rebuild widgets, replay from empty, and compare the two trees. Pass if parents, order, and stretch match. That is the undo test.

10. **AppArmor confirmation on a real appliance.** Confirm a nested AppRun still starts under the production profile. The repo evidence says the editor already does this for Run. The 2026-03-06 whitelist did not list AppRun among the fourteen binaries. Confirm the production profile before designing any second process that is not AppRun.

## Principles that changed a choice

**Redesign from first principles.** The requirement is a visual layout tool with a later behavior layer. The previous design was Designer parity. The recommendation starts from the layout tree and the code-behind split, and treats `.ui` as import.

**Attack the premise.** Another fix on top of the tree canvas assumes the tree was the right surface. The branch tip says it was not.

**Foundational thinking.** The document types come before the canvas, the generator, and the property panel.

**Model the domain.** One layout per container, one child per item, geometry only without a layout, connections beside the tree.

**Experience first.** Wrap, insertion lines, and plain size-policy words outrank a full meta-object grid and a node editor.

**Laziness protocol.** No protected regions, no puppet, no visual language, no second layout engine hiding under "auto-layout."

**Boundary discipline.** JSON is parsed at the edge. User modules load in the runner. The editor canvas builds stock classes only.

**Exhaust the design space.** Three candidates are scored here. Spikes 1, 5, 6, and 7 are the comparisons that still need a run. This session did not build them, because the brief was research only.

**Never block on the human.** JSON, live stock widgets, and code-behind stubs are the defaults. The operator could pick YAML, a `.ui` daily file plus a visual canvas, or a read-only Python view with no JSON. Those are preference calls. A round-trip editor is the one this report argues against on evidence, not on taste.

## Sources

Repo files read for this report.

- `docs/DISCOVERY.md` (Python 3.9.2, Qt 5.15.2, `QtUiTools`, AppArmor section 4G, `noexec` section 4E)
- `docs/ARCHITECTURE.md` (sections 4 and 24)
- `docs/PRD.md` (section 6 runner, section 7 `.ui` tabs, risk 3 probe)
- `docs/CHOREBOY_RUNTIME_PITFALLS.md` (PostgreSQL 9.3 floor, GUI-thread `SIGSEGV` in D-1)
- `docs/designer/TASKS.md` on current `HEAD` (Designer backlog still `TODO`)
- Layout counts on 2026-10-20 from Code Studio `app/`, `ChoreBoy-PySide2-QtWidgets_Template/packages`, `FCC_QT/packages`, and `apex_part_manager_on_choreboy/packages`
- Apex `packages/apex_part_manager_app/ui/widgets/apex_primitives.py` (`FormCardSection`, 12-column grid)
- `docs/handoffs/TEST_SPEED_HANDOFF.md` (nested AppRun cost)
- `tests/conftest.py`, `run_tests.py` (`QT_QPA_PLATFORM=offscreen`)
- `app/shell/theme_tokens.py`
- Branch `origin/cursor/qt-ui-designer-implementation-3f01`, including `docs/designer/ARCHITECTURE_PLAN.md`, `docs/designer/AUDIT_REPORT.md`, `app/designer/canvas/form_canvas.py`, `app/designer/model/ui_model.py`, `app/designer/model/layout_node.py`, `app/designer/properties/property_schema.py`, `app/designer/preview/preview_runner.py`

External pages.

- Qt User Interface Compiler, <https://doc.qt.io/qt-6/uic.html>
- Using a Designer file from C++, <https://doc.qt.io/qt-6/designer-using-a-ui-file.html>
- Using a Designer file from Python, <https://doc.qt.io/qt-6/designer-using-a-ui-file-python.html>
- `pyside6-uic`, including the warning not to edit generated files, <https://doc.qt.io/qtforpython-6/tools/pyside-uic.html>
- `QUiLoader`, including the untrusted-file warning, <https://doc.qt.io/qt-6/quiloader.html>
- Qt for Python `.ui` tutorial, including the Python-type connection limit, <https://doc.qt.io/qtforpython-6/tutorials/basictutorial/uifiles.html>
- Designer widget editing mode, <https://doc.qt.io/qt-6/designer-widget-mode.html>
- Qt property system, <https://doc.qt.io/qt-6/properties.html>
- Layout management, <https://doc.qt.io/qt-6/layout.html>
- `QSizePolicy`, <https://doc.qt.io/qt-6/qsizepolicy.html>
- `QBoxLayout.addWidget` stretch rule, <https://doc.qt.io/qt-6/qboxlayout.html>
- Changes to Qt Widgets in Qt 6, including removal of `QDesktopWidget`, <https://doc.qt.io/qt-6/widgets-changes-qt6.html>
- `QGraphicsProxyWidget`, <https://doc.qt.io/qt-6/qgraphicsproxywidget.html> and the high-performance note on <https://doc.qt.io/qt-6.8/qgraphicsproxywidget.html>
- Qt Design Studio puppet, <https://wiki.qt.io/User:Tim.Jenssen/QML_Puppet_Rendering_in_Qt_Design_Studio> and <https://wiki.qt.io/QtDesignStudio/Troubleshooting>
- Qt Test offscreen support, <https://doc.qt.io/qt-6/qtest-overview.html>
- LibCST exact reprint goal, <https://libcst.readthedocs.io/en/latest/parser.html> and <https://github.com/Instagram/LibCST/blob/bffd53063e53c798a7a4540a718aa91f80ebb140/docs/source/motivation.rst>
- ESO note that UI files are version-independent, <https://www.eso.org/projects/elt/develop/cut/3.4.3/user_manual/sphinx/html/docs/910_qt5_to_qt6_migration.html>
- Qt 6 stylesheet enum selectors, <https://github.com/TinyTrebuchet/qtbase/commit/b749163bb81c1a5e46ec14fa0fecdbced1a7ed85>
- Enum `QVariant` type change between 5.15 and 6.5, <https://forum.qt.io/topic/144632/different-property-type-for-enum-in-5-15-6-5>
- Offscreen focus flakiness, <https://forum.qt.io/topic/109767/headless-gui-testing-with-qt>
- Custom widget crash inside Designer when the class derives from `QMainWindow`, <https://forum.qt.io/topic/143164/custom-widget-crash-in-designer-if-derived-from-qmainwindow>
- FreeCAD 1.1.0 assets, <https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.0>
- FreeCAD 1.1 release announcement, <https://freecad.github.io/Website/news/freecad-version-1-1-released/>
- FreeCAD handbook dependency floor, <https://freecad.github.io/DevelopersHandbook/gettingstarted/dependencies.html>

## Unverified, and investigation gaps

Unverified here. The contents of the ChoreBoy FreeCAD 1.1 test update from about 2026-09-29. Whether production AppArmor allows nested AppRun on every appliance revision, as opposed to the developer machines where Run already works. Whether FreeCAD's Qt 6 build on that image still ships `QtUiTools`. The handbook page is inconsistent about PySide2 versus PySide6, so it is not a clean citation for the binding that image will have.

Why-style coverage. Source control for the designer branch was read with git. Long-form rationale was read from `docs/designer/` on that branch and from `docs/ARCHITECTURE.md`. No issue tracker, team chat, error tracker, or product analytics for this repository was available in this session. The connected MCP tools are for other products. That gap matters if the reason to discard the branch lives in a conversation this report did not see. The code on the branch is enough to leave the tree-shaped canvas behind. A full history of the 47 commits would need the missing conversation record.

Model note. The routed explorer default `grok-4.7-xhigh-fast` and the explainer default `claude-opus-5-5-xhigh` are not in this session's allowed model list. Explorers were started on `grok-4.7-high`. The synthesis in this file was written from the repo reads, git reads, and the pages above, not from a second-model explainer pass.
