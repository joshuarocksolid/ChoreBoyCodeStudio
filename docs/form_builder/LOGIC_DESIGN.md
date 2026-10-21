# Form builder logic layer: design

Status: design for product-owner review. 20 October 2026. No application code was changed.

This document designs how a person adds behaviour to a form in the ChoreBoy Code Studio (CBCS) form builder. It covers all four agreed levels:

1. A widget drives another widget (native Qt `<connections>`).
2. A widget calls your Python method (native `<connections>` plus `<slots>`, method in `forms/name_window.py`).
3. No-code rules: enabled, visible and read-only *when*, calculated values, defaults, checks, and event actions.
4. Data binding to SQLite and PostgreSQL 9.3: load, save, navigate, lookups, master-detail, list and search screens.

Levels 3 and 4 are stored as Qt dynamic properties in `forms/name.ui` and expanded into plain Python inside `forms/ui_name.py`. There is no runtime library.

Inputs read: `research/L_logic_research_grok.md` (Grok's tool research and draft design), `research/P_user_pain_points.md`, `research/R3_designer_parity_checklist.md`, `research/R1_runtime_ui_loading.md`, `research/A_market_survey.md`, `research/D_first_principles_architecture.md`, and `docs/CHOREBOY_RUNTIME_PITFALLS.md`. This document is written to stand on its own. It keeps most of Grok's draft and changes about a dozen of its decisions. Section 0 lists those changes.

## How to read this document

| If you want | Read |
| --- | --- |
| The decisions on one page | Section 0 |
| What a user sees and does | Section 2, including the three walkthroughs |
| The formula language | Section 4 |
| What is saved in the `.ui` file | Section 6 |
| What the generated Python looks like | Section 7 |
| What gets built first | Section 9 |
| What I need you to decide | Section 10 |

Words used throughout:

- **Form**: one `.ui` file and the window built from it.
- **Window class**: the user's class in `forms/name_window.py`. It calls `self.ui.setupUi(self)`. The builder creates this file once and then only ever adds an empty method stub.
- **Generated module**: `forms/ui_name.py`, rewritten on every save. Nobody edits it.
- **Rule**: a standing statement about a widget, such as "Enabled when Discount is checked" or "Value = Qty × Price". Rules are re-checked whenever their inputs change.
- **Event**: something that happens once, such as a click. An event runs an ordered list of **steps**.
- **Check**: a validation rule on a field, such as "Required" or "Must be an email address".
- **Formula**: the small expression language used inside rules, checks and steps (Section 4). The UI says "formula". The spec says "expression". They mean the same thing.

---

## 0. Decisions on one page

| # | Decision | Why, in one line |
| --- | --- | --- |
| 1 | **One Events list per widget is the single place to see and edit what happens.** The builder picks the storage. A plain connection is saved as a native `<connection>`. Anything with two or more steps or a condition is saved as a `cbcsOn…` step list. | People see one ordered list. Designer and `QUiLoader` still get native connections for the simple cases. |
| 2 | **"Keep in sync" is a rule, not a connection.** The connection picker sends "enable X while this is checked" to an *Enabled when* rule. | A `toggled → setEnabled` connection does nothing at startup or when a record loads, so the screen starts out wrong. A rule is checked at startup and after every load. |
| 3 | **Formulas use a small, typed subset of Python.** Excel-style input (`=`, `<>`, `IF(…)`, `AND(…)`, `&`) is recognised and fixed with one keystroke. Only the Python form is saved. | CBCS users already write Python. What they type is what appears in the generated file, and what they learn carries over to their own code. |
| 4 | **Formulas are type-checked at design time** against each widget's kind (Text, Number, Money, Date…). | Most "the total is wrong" bugs become a red underline while editing instead of a surprise when the app runs. |
| 5 | **One dynamic property per concern, saved as plain text.** For example `cbcsEnabledWhen = discountCheck`. JSON is used only for lists (checks, steps, grid columns, data source), written one item per line. | The file stays readable and diffable, and a developer can edit it in Qt Designer's property editor. One big JSON blob per widget would be none of those. |
| 6 | **Field bindings live on the field itself** (`cbcsBind = customer_id`), not in a central list. | Copy, paste and rename carry the binding with the widget. A central list goes stale when a widget is renamed. |
| 7 | **No magic method names.** Every method the generated code calls (handlers, `before_save` and the other hooks) is named explicitly in the `.ui` file and checked against `name_window.py` by parsing it. | Misspelling a magic name fails silently. That is the same trap as `connectSlotsByName`, which research P documents. |
| 8 | **Try mode runs the real generated code** in the preview process. It uses a stand-in for your window class and, for SQLite, a scratch copy of the database. | What you try is exactly what ships. You can press Save in Try mode without damaging real data. |
| 9 | **Data forms load only the list of record keys, then fetch one record at a time.** Unsaved changes are found by comparing the fields with the values loaded. Concurrent edits are detected before saving. Line items are saved by comparing old and new rows. Generated SQL uses plain DB-API calls and is safe on PostgreSQL 9.3. | Fast on large tables. No false "unsaved changes" prompts. One clerk cannot silently overwrite another clerk's edit. |
| 10 | **The database hand-off is one user-owned file, `cbcs_connections.py`, created once.** It sits next to a no-secrets `connections.json`. Passwords never go in the project. | It handles the driver probe (`cb_psycopg`, then `psycopg`, then `pg8000`) and connection settings in one place you can read and edit. See open question 1. |
| 11 | **The record toolbar is made of ordinary parts.** Inserting it adds normal buttons that carry normal steps and *Enabled when* rules. | Nothing is hidden. Every piece can be restyled, deleted or overridden. |
| 12 | **"Eject to code"** turns a form's generated data code into ordinary methods in the window class. It runs only on request, can be undone, and is one-way. | It is the escape hatch for anyone who outgrows the no-code data layer, without starting again. |

### Changes from Grok's draft

| Draft said | This design | Reason |
| --- | --- | --- |
| One JSON `cbcsBehavior` blob per widget | One property per concern, plain text for formulas (Decision 5) | Readable in Designer, line-level diffs |
| A central `bindings` list in `cbcsData` | `cbcsBind` and `cbcsLookup` on each widget (Decision 6) | Survives copy, paste and rename |
| `connectslotsbyname="false"` on every form | Keep Qt's default (on). Warn about the two real traps instead (Section 3.6) | Developers following Qt tutorials expect `on_x_clicked` with `@Slot` to work |
| Double-click opens the Behavior tab and does not create a stub | Double-click creates a stub for the default event, once. Undo removes it while it is still empty | This was already decided in the brief, and it is the Delphi and VB6 gesture people praise |
| `before_save` and other hooks found with `getattr` | Hooks are named explicitly and checked (Decision 7) | A misspelled hook should be an error, not ignored |
| Insert a `closeEvent` into the user's window file | An event filter in generated code catches the close (verified, Section 7.7) | Never edit user code beyond the empty stub |
| Load all rows into memory for navigation | Load keys only (Decision 9) | 100,000 invoices must still open instantly |
| Dirty flag set by change signals | Compare current fields with the loaded snapshot | Typing a value and then typing the old value back is not a change |
| Delete child rows `NOT IN (kept ids)` | Track deleted rows explicitly | `NOT IN` would delete a line another user just added |
| `RETURNING` on 9.3 is "an inference" | Verified in the 9.3 manual | The 9.3 INSERT synopsis includes `RETURNING` |
| Try mode never touches data | Try with a scratch SQLite copy. PostgreSQL is read-only in Try mode, with "would run" output | People need to try Save |
| Spike tests only the compiler | Spike tests the editing experience with real users as well as the compiler (Section 9.2) | The open risk is ease of use, not code generation |
| Rename updates formula text | The same, plus a repair dialog when a rename happened outside CBCS (in Designer or a text editor) | Designer does not know about our formulas |

---

## 1. Design principles

Each principle names the failure it prevents and the evidence for it.

### P1. One place to look, one order of execution

Everything that happens when a widget's signal fires appears in one list, in run order. That includes native connections, step lists, and (read-only) connections your own code makes in `name_window.py`.

Evidence: Designer hides new connections in a separate mode and a table you have to scroll ("You will not see it, it is somewhere on top or bottom", Serge K, 2017, in research P). Retool event handlers run in parallel and Bubble's frontend actions do not wait for each other (Grok research). VB6 spaghetti comes from behaviour scattered with no overview. Budibase's rule "actions run synchronously; if one fails, the actions after won't run" is the model people can predict.

Prevents: VB6 spaghetti, Retool ordering surprises, the Designer "where did my connection go" problem.

### P2. Rules describe states. Events describe moments.

"Enabled when", "Visible when", "Read-only when", "Value =" and "Default =" are rules. They are re-checked whenever their inputs change, including at startup and after a record loads. "When clicked, do A then B" is an event. The UI never mixes the two. The connection picker steers "keep in sync" intents to rules.

Evidence: Power Fx splits value formulas from behaviour formulas because state-changing functions "can't be automatically recalculated" (Microsoft Learn, in Grok research). FileMaker shows the cost of event-only logic: `Set Field` does not fire `OnObjectModify`, and portal filters do not refresh, so the screen drifts out of date.

Prevents: initial-state bugs (the field is enabled at startup even though the box is unchecked), FileMaker-style "this change did not fire the trigger" drift, and Access-style sequencing of Open, Load, Current and BeforeUpdate.

### P3. A rule and a constant never fight over one property

A rule is stored separately from the widget's normal Qt property. `cbcsEnabledWhen` sits next to `enabled`. The normal property stays the design-time default that Designer and `QUiLoader` show. At run time the rule wins. Dragging, resizing or editing a widget never rewrites a rule. A widget with a *Value =* rule is shown as "Calculated", and its Qt value cannot be typed over in the inspector.

Evidence: Power Apps replaces a responsive formula with a constant when a control is dragged (research A, Microsoft's responsive-layout page).

Prevents: Power Apps formula wipe-out.

### P4. The formula is the code

Formulas are a small subset of Python. The generated module contains almost exactly what you typed: `qtySpin * priceSpin` becomes `self.qtySpin.value() * _cbcs_dec(self.priceSpin.value(), 2)`, with a comment that quotes the original. There is no second language to translate between, no `{{ }}` templating inside strings or SQL, and no node graph.

Evidence: Retool, Appsmith and Budibase grow `{{ }}` bindings scattered through every property, and Appsmith stops its UI at two levels of callbacks. Blockly-generated JavaScript is read-only because "blocks cannot be rebuilt from the JavaScript" (node-red-contrib-blockly). Blueprints do not merge (research A). Anvil's "one Python expression per property" works for a Python audience (Grok research).

Prevents: `{{}}` sprawl, Blueprint unmergeability, Access macro opacity, because the generated Python *is* the explanation.

### P5. Show the result while you edit, and the error where it happens

Every formula shows its current value against the canvas while you type. It is underlined when wrong and explained in plain words. The widget gets a badge. The Problems panel gets the same message. At run time, a failed check shows text under the field, not only an icon or a message box.

Evidence: Excel teaches `=A2*B2` because the result is visible (Microsoft Research, in Grok research). Microsoft says ErrorProvider's icon alone is not accessible, so the app still needs text. Anvil silently ignores `KeyError` in bindings, and people complain about it.

Prevents: silent failures and errors that only appear once the app is running.

### P6. Your code is yours; generated code only calls what you named

The builder only writes to `ui_name.py`, plus one empty stub per handler you ask for. Generated code calls only methods named in the `.ui` file. Every generated name starts with `cbcs_` or `_cbcs_`, so it never collides with a widget or with your methods. Any generated behaviour can be replaced from the window class (Section 7.8).

Evidence: "You should never modify .designer.cs. Period" (dahlbyk), and pyuic's "you must never edit those files" (musicamante), both in research P. The WinForms complaint about accidental double-click stubs, and w0ut's praise that "if the handler was just created it will also remove the handler".

Prevents: WinForms dangling handlers, lost edits, and generated code fighting user code.

### P7. Explicit beats magic; names are checked, never guessed

Handlers are explicit `<connection>` elements. Hooks are explicit names. Widget references in formulas are checked object names. A near miss is a design-time error with a suggested fix.

Evidence: `connectSlotsByName` connects nothing on a near miss and only prints "No matching signal" (research P). It also skips an undecorated method (R1, measured). Qt's own guide recommends against auto-connect in new code (Grok research).

Prevents: handlers that silently never run.

### P8. Database writes are explicit, visible and bounded

Formulas never touch the database. Only steps write: Save, Delete and New. Every SQL statement the form will run is visible in the Data panel with its parameters. Searches tell you when results were cut off.

Evidence: Power Apps delegation silently returns the first 500 rows (Microsoft Learn, in Grok research). FileMaker portal filters go stale without anyone noticing. PostgreSQL 9.3 has no `ON CONFLICT` and no `JSONB` (`CHOREBOY_RUNTIME_PITFALLS.md` A-1). A connection left in a failed transaction breaks every later query (pitfalls E-1).

Prevents: silently truncated data, upserts that overwrite someone else's work, and stuck transactions.

---

## 2. The user experience, end to end

### 2.1 The inspector's Behavior tab

The inspector has three tabs: **Properties** (Qt properties, as in Designer), **Behavior**, and **Data** (only when the form has a data source). The Behavior tab shows a count badge when the selected widget has any logic. The tab has three sections that always appear in the same order: *State*, *Checks*, *Events*.

```
+- Inspector -----------------------------------------------------+
| Properties | Behavior (3) | Data                                |
+-----------------------------------------------------------------+
| Discount rate   discountEdit : QLineEdit        Kind [Percent v] |
|                                                                 |
| STATE                                                           |
|   Enabled when   Discount is checked                  now: no   |
|   Visible        always                                 [+]     |
|   Read-only      never                                  [+]     |
|   Value          typed by the user                      [+]     |
|   Default        0                                     now: 0%  |
|                                                                 |
| CHECKS                                   run when leaving field |
|   1  Required          "Enter a discount rate"                  |
|   2  Between 0 and 50  "Discount must be 0% to 50%"             |
|      [+ Add check v]   error shows in: discountEditError        |
|                                                                 |
| EVENTS                                                          |
|   When editing is finished                                      |
|     1  Set totalEdit to  subtotal * (1 - discountEdit)          |
|   [+ When... v]                                                 |
+-----------------------------------------------------------------+
```

How it behaves:

- **The top line** shows the widget's display name and its object name. The display name comes from its buddy label ("Discount rate:"), or its own `text`, or else its object name. Clicking the object name renames it, and the rename is carried through everywhere (2.12). **Kind** (Section 4.3) only appears for widgets whose text needs interpreting, such as `QLineEdit` and `QLabel`.
- **State rows** are always listed, even when empty, so the person can see what is possible. That is the Access-property-sheet lesson: discovering something means seeing a slot for it. An empty row shows its default in grey ("always", "never", "typed by the user"). Click or press Enter to edit.
- **"now:"** shows the live result against the canvas: *yes*, *no*, a number, or a red "error". It updates as you change widgets on the canvas, because the canvas widgets are real widgets.
- **The Checks list** is in run order. Drag or press Alt+Up and Alt+Down to reorder. Each row shows its message. The message is generated from the buddy label until you edit it: "Discount rate is required".
- **Events** groups steps under one header per signal. **[+ When...]** opens the event picker (2.2).

A form-level Behavior tab (shown when nothing is selected, or the form itself is selected) has the same sections with form events: *When the form opens*, *Before the form closes*, *When a record is loaded*, *Before saving*, *After saving*, *Before deleting*, *When a new record starts*.

### 2.2 The event picker: "When <event> → <steps>"

`[+ When...]` opens a filterable list. Common events for that widget class are listed first, in plain words. The full Qt signal list is underneath, behind "More events".

```
+- When... (saveButton : QPushButton) ---------------+
| > type to filter                                   |
|  COMMON                                            |
|   * clicked                      clicked()         |
|     pressed and held             pressed()         |
|  MORE EVENTS (Qt signals)                     [v]  |
|     released()  toggled(bool)  destroyed() ...     |
|  [ ] show signals inherited from QWidget           |
+----------------------------------------------------+
```

The common events per class (the full list is always one click away):

| Widget | Common events, in this order | Default event (double-click) |
| --- | --- | --- |
| `QPushButton`, `QToolButton`, `QCommandLinkButton` | clicked | clicked |
| `QCheckBox`, `QRadioButton` | is checked or unchecked (`toggled(bool)`), clicked | toggled |
| `QLineEdit` | editing finished (`editingFinished()`), Enter pressed (`returnPressed()`), text changed while typing (`textChanged(QString)`) | editingFinished |
| `QPlainTextEdit`, `QTextEdit` | text changed (`textChanged()`) | textChanged |
| `QComboBox` | choice changed (`currentIndexChanged(int)`), choice picked by the user (`activated(int)`) | currentIndexChanged |
| `QSpinBox`, `QDoubleSpinBox`, `QSlider`, `QDial` | value changed (`valueChanged`), editing finished (`editingFinished()`, spin boxes only) | valueChanged |
| `QDateEdit`, `QTimeEdit`, `QDateTimeEdit` | date changed (`dateChanged(QDate)`) and the time and datetime equivalents | dateChanged |
| `QTabWidget` | tab changed (`currentChanged(int)`) | currentChanged |
| `QListWidget` | item activated (`itemActivated`), selection changed (`currentRowChanged(int)`) | itemActivated |
| `QTableView` and `QTreeView` bound to data | row activated (`activated(QModelIndex)`, which covers double-click and Enter), current row changed (a pseudo-event, see below) | activated |
| `QDialogButtonBox` | OK or Save (`accepted()`), Cancel (`rejected()`), any button (`clicked(QAbstractButton*)`) | accepted |
| `QAction` (menus, toolbars) | triggered | triggered |
| Form (root) | opens, before close, record loaded, before save, after save, before delete, new record | none |

"Current row changed" is not a widget signal. It belongs to the view's selection model. The builder offers it as an event and the generator connects `view.selectionModel().currentRowChanged`. This is one of a small set of **pseudo-events**. The others are the form events above. They exist because the real Qt mechanism is too obscure for this audience.

After an event is picked, the step picker opens immediately (2.4). Most events have exactly one step.

### 2.3 How the builder stores an Events list (invisible to the user)

| What is in the list | Saved as | Visible in Qt Designer | Runs under `QUiLoader` |
| --- | --- | --- | --- |
| Only plain connections: a Qt slot on a widget, or a method on your window, with no condition | One `<connection>` per step, in list order | Yes, as arrows | Widget slots yes. Window methods no, because the loader cannot see your class |
| Anything else: two or more mixed steps, a condition, a no-code step | One `cbcsOn<Signal>` property holding the step list | As a dynamic property | No (inert) |

The conversion happens automatically and can be undone like any other edit. If someone adds a native connection in Designer to a signal that also has a `cbcsOn…` list, both run. The Events list shows both groups with the warning "This event is stored in two places" and a **Merge** button. Qt runs connected slots in the order they were connected. The generator connects native connections first (as `uic` does), then the step list. The Events list shows that order honestly.

### 2.4 The step picker and the step editor

```
+- Then... ------------------------------------------+
| > type to filter                                   |
|  FIELDS        Check all fields | Set a field      |
|                Clear fields | Move focus to        |
|  SHOW          Show / hide | Enable / disable      |
|                Show a message | Ask yes or no      |
|                Switch tab or page                  |
|  WINDOWS       Open another form | Close this form |
|  RECORD        New | Save | Delete | Undo changes  |
|                First | Previous | Next | Last      |
|                Find | Reload lookups               |
|                Add line | Delete line              |
|  YOUR CODE     Call a method in invoice_window.py  |
|  FLOW          Stop here if...                     |
+----------------------------------------------------+
```

RECORD steps only appear when the form has a data source. Each step has an optional **only if** condition, shown as an indented line. A step list reads as numbered sentences:

```
When Save is clicked
  1  Check all fields                       (stops here if a field fails)
  2  Ask "Save this invoice?"               (stops here on No)
  3  Call save_invoice()                    -> invoice_window.py:42
     only if  invoiceTotal > 0
```

Notes beside steps that can stop the list, such as "(stops here if...)", are always shown. Whether the rest of the list runs is never hidden.

### 2.5 The condition and value editors

Every formula slot has two modes. The editor switches modes automatically whenever it can do so without losing anything.

**Builder mode** is for conditions shaped like "field, comparison, value" joined by *all of* or *any of*:

```
Enabled when  [ all of v ]
   [ Discount (discountCheck)  v ] [ is checked        v ]
   [ Customer (customerCombo)  v ] [ is not blank      v ]
   [+ condition]                               [Formula >]
```

The comparison menu depends on the field's type. Text fields offer is, is not, is blank, is not blank, contains, starts with. Numbers offer =, not =, <, <=, >, >=, between. Yes/No fields offer is checked, is not checked. Dates offer is before, is after, is today, is blank. Choices offer is, is one of.

**Formula mode** is a single-line code editor (multi-line with Shift+Enter) using the same editor component as the CBCS code editor:

```
Value =  qtySpin * priceSpin|
         ------------------
         Number (Money)    now: $6.00      as words: Qty x Price
  +- completions -------------------------------+
  | priceSpin      Price          Money          |
  | priceListCombo Price list     Choice         |
  | pow(...)       function                      |
  +---------------------------------------------+
```

- Completion lists widgets by object name *and* display name, then functions, then `form.` and `record.` members. Typing "Price" finds `priceSpin`.
- The status line shows the **type** of the result, the **live value**, and a plain-words reading.
- Errors are underlined with a message and, where possible, a one-key fix (Ctrl+.). See 4.10.
- Builder mode can always become formula mode. Formula mode becomes builder mode only if the formula is a plain "all of" or "any of" list of comparisons. Otherwise the [Builder] button says "This condition is too complex for the builder. Edit it as a formula." Nothing is ever converted with loss.

### 2.6 The Data panel

The Data panel is a dock beside the widget box. With nothing bound yet, it shows a single button: **Connect this form to a table...**

```
+- Data -------------------------------------------------------+
| Source   shop (SQLite: data/shop.db)            [change]     |
| Table    invoices          Key  id          Order  date desc |
| Opens at [newest record v]   Conflicts [warn before overwrite]|
|                                                              |
| FIELDS (drag onto the form)       BOUND TO                   |
|   id             INTEGER  key     -                          |
|   invoice_no     TEXT     unique  invoiceNoEdit              |
|   customer_id    INTEGER  -> customers   customerCombo  (lookup)|
|   invoice_date   TEXT     date    invoiceDateEdit            |
|   notes          TEXT             notesEdit                  |
|   status         TEXT             (not bound)  [bind...]     |
|                                                              |
| LINES   invoice_lines.invoice_id -> linesView     [edit]     |
|                                                              |
| [Bind fields by name] [Insert record toolbar] [Show SQL]     |
| Python hooks: before save  -  [create]  after load - [create]|
| Schema read 20 Oct 14:02  [Refresh]                          |
+--------------------------------------------------------------+
```

- **Drag a column onto the canvas** to create a labelled field of the right class and kind, already bound. A date column becomes a `QDateEdit`. A foreign key becomes a lookup `QComboBox`. Its object name is the column name (`invoice_date`), which matches the agreed default that the object name equals the column name. Person-friendly names like `invoiceDateEdit` are a rename away, and renaming keeps the binding (Decision 6).
- **Bind fields by name** binds every unbound widget whose object name matches a column. Matching is exact first, then by stem (`invoiceDateEdit` and `invoice_date`). It writes explicit `cbcsBind` values, previews them first, and can be undone.
- **Show SQL** lists every statement the form will run (select keys, load one record, insert, update, delete, the lookup queries), with parameter placeholders. This is the Power Apps delegation lesson: nothing about data access is hidden.
- **The schema** is read from SQLite with Python's built-in `sqlite3` in read-only mode. For PostgreSQL it is read by a short-lived helper process (the existing runner pattern), so the editor never loads native driver libraries. The schema is cached in `cbcs/schema/<connection>.json`, so the panel and the design-time checks still work offline. The cache is marked stale after 7 days.

Lookups and line grids have their own small editors, opened from the panel or from the Behavior tab of the combo or grid (Section 5).

### 2.7 The canvas overlay

By default the canvas shows only a small logic badge in a widget's top-right corner, and only on widgets that have logic. The badge letters are `=` for calculated, `?` for conditional state, `!` for checks, `>` for events, and `D` for bound to data. Hovering shows a one-line summary.

When a widget is **selected**, its relationships are drawn, and only its relationships:

```
   [ Qty  2 ]----.
                  \  feeds
   [ Price 3.00 ]--+--> [ Line total  $6.00 ] =
                                 |
                                 '--> [ Invoice total ] =   (dependent)
```

- Grey dashed arrows go *into* the selection from the fields its formulas read.
- Grey dashed arrows go *out* to fields whose formulas read it.
- Solid blue arrows are Level 1 connections (widget to widget).
- A green `{ }` marker means a Level 2 call into your code. Hovering shows the method name, and clicking jumps to it.
- **Show all logic** (Ctrl+Shift+L) draws every relationship on the form, for the occasional overview.
- **F4** enters Designer's connection-drawing mode (parity with R3 item 2) for people who prefer dragging arrows. Dropping a connection opens the same step picker.

This is the deliberate answer to "logic graphs turn into spaghetti". Showing every relationship by default is what makes Blueprint graphs and VB6 forms unreadable. Showing them on demand for one widget keeps them useful.

### 2.8 The Logic outline and search

A **Logic** panel (a tab beside the object tree) lists every piece of behaviour on the form:

```
+- Logic (invoice.ui) ------------------------- [Read as text] -+
| > filter: total                    [Rules][Checks][Events][Data][!] |
|  STATE                                                         |
|    discountEdit   Enabled when  discountCheck                  |
|    lineTotalLabel Value =  qtySpin * priceSpin                 |
|    totalLabel     Value =  sum(linesView.lineTotal)            |
|  CHECKS                                                        |
|    emailEdit      Required, Email address                      |
|  EVENTS                                                        |
|    saveButton     clicked: Check all fields, Call save_invoice |
|    closeButton    clicked: close()            (native)         |
|    Invoice        Before saving: before_save()  (Python hook)  |
|  IN YOUR CODE (read-only, found in invoice_window.py)          |
|    printButton    clicked -> self.print_invoice   line 31      |
|  ! 1 problem: priceListCombo is not bound                      |
+----------------------------------------------------------------+
```

- Search covers object names, display names, formula text, method names, tables and columns. Ctrl+Shift+F searches within the open form. The project-wide Find gains a "Forms logic" result group.
- **In your code** lists connections found by parsing `name_window.py` without running it, for simple patterns such as `self.ui.X.signal.connect(self.method)`. The list is best-effort and labelled as such. It is there so that the Events list is complete wherever possible (P1).
- **Read as text** produces a plain-English description of the whole form that can be printed or copied. For example: "Discount rate is enabled only when Discount is checked. Line total is always Qty times Price..." This is the cure for Access macro opacity. A shop owner can hand the page to someone else and ask "is this right?"

### 2.9 Errors at design time

Every problem appears in three places with the same text: underlined in the formula, as a red badge on the widget, and as a row in CBCS's existing **Problems** panel. A Problems row names the form, widget, rule and fix, and double-clicking it selects the widget and opens the rule.

| Code | Severity | Example message | Quick fix |
| --- | --- | --- | --- |
| FB101 | Error | `qtySpn` is not a field on this form. Did you mean `qtySpin`? | Replace |
| FB102 | Error | Can't multiply Text by Number. `priceEdit` holds text. | Set `priceEdit` kind to Money, or wrap it in `number(...)` |
| FB103 | Error | Loops and assignments aren't available in formulas. | Move this into a method (creates a stub) |
| FB104 | Error | These values depend on each other in a circle: total, then tax, then total. | Select the cycle |
| FB105 | Error | This pattern is not valid: missing `)` at position 7. | none |
| FB201 | Error | `save_invoice` is not defined in `InvoiceWindow` (`invoice_window.py`). | Create method |
| FB202 | Error | `show_tax(self, a, b)` needs 2 values, but `toggled` sends 1. It would fail when clicked. | Fix signature |
| FB203 | Warning | `save_invoice` is still empty (`pass`). | Go to code |
| FB204 | Error | Method name `close` would replace QDialog's own `close`. | Rename to `close_invoice` |
| FB205 | Warning | `on_saveButton_clicked` also auto-connects by name, so it would run twice. | Rename |
| FB206 | Warning | `on_okButton_clicked` lacks `@Slot()`, so Qt will not auto-connect it. | Add decorator |
| FB207 | Warning | Your code calls `self.ui.discountEdit.setEnabled(...)`, but an *Enabled when* rule also controls it. The rule wins on every refresh. | Show the rule |
| FB301 | Error | Column `invoice_number` no longer exists in `invoices` (schema read 20 Oct). | Rebind |
| FB302 | Warning | Schema is 9 days old. | Refresh |
| FB303 | Error | `customerCombo` is bound to `customer_id`, but its lookup has no key column. | Edit lookup |
| FB401 | Error | `cbcsOnClicked` on `saveButton` is not valid JSON (line 3). This rule was kept as-is and generates no code. | Open raw |
| FB402 | Error | This form was saved by a newer CBCS (logic version 2). Logic is shown read-only and preserved. | none |

A rule with an error generates **no code**, but the rest of the form still generates and runs. The widget then keeps the constant value from its normal Qt property (P3). Saving is never blocked by a logic error. Running the app from CBCS shows "This form has 1 logic error" with a link to the problems.

### 2.10 Try mode: test the form without running the app

**Try** (Ctrl+R, the same key as Designer's Preview) opens the form in CBCS's preview process. It uses the *actual* generated `ui_name.py`, with two substitutions:

- **A stand-in window class** replaces your `name_window.py`, which is never imported, so a bug in your code cannot break the builder. When a step calls `save_invoice()`, the Try log records "Would call save_invoice()". The **window values** pane lets you supply return values for formulas that use `window.something()` (4.7). For example `window.is_manager()` can be set to `True`.
- **Data**: SQLite runs against a scratch copy of the database file, made when Try starts and discarded when it closes ("Keep scratch copy" is available for debugging). Save, Delete and New work for real. PostgreSQL connects with the same settings but read-only. Every write is shown as "Would run: `UPDATE "invoices" SET ...` with values (...)". A *Writes are rolled back* option exists for developers.

```
+- Try: Invoice -------------------------------------+- Try log ---------------------+
|  Customer [Acme      v]   Date [2026-10-20]        | 14:02:11 Rules ran (12)       |
|  [x] Discount  Rate [ 10 ]                         | 14:02:15 Check emailEdit:     |
|  Email [bob@        ]                              |          "Enter an email..."  |
|        Enter an email address like name@example.com| 14:02:15 Save stopped at step |
|  ...                                               |          1 (Check all fields) |
|  [Save]  [Close]                                   | 14:02:31 Would call           |
+----------------------------------------------------+          save_invoice()       |
| Window values: window.is_manager() [True v]        | [Clear] [Copy]                |
| Data: scratch copy of data/shop.db  [Reset data]   |                               |
+----------------------------------------------------+-------------------------------+
```

Clicking a log line selects the rule or step that produced it in the builder. Editing a rule while Try is open regenerates the module and reloads the preview. Field values are kept where object names still match.

The "now:" values in the inspector (2.1) are a separate, instant mechanism inside the editor. The compiler turns the formula into the same Python expression it would generate, and evaluates it against the canvas widgets' current values. One compiler means one meaning for every formula. There is no second interpreter to drift out of step with the generated code.

### 2.11 Run-time errors in the shipped app

| What went wrong | What the person using the app sees |
| --- | --- |
| A check fails | The message under the field. The field is outlined red (the dynamic property `cbcsInvalid` can be styled with a style sheet). The message is also the tooltip. On Save, focus moves to the first bad field. If the form has a status bar, it shows "2 fields need attention". |
| Division by zero or an impossible date in a formula | The calculated field shows blank, and its tooltip says "Can't divide by zero". The app keeps running. |
| An "Ask" step answered No, or a "Stop if" step | The rest of the list silently does not run, as designed. |
| A database error on save | The transaction is rolled back. Known errors are shown on the field they belong to. A uniqueness violation on `invoice_no` puts "Another invoice already uses this Invoice no." under that field. Other errors show a message box with the database's text. The changes stay on screen so nothing is lost. |
| Someone else changed the record | "Someone else changed this invoice since you opened it. [Reload their version] [Cancel]" |
| The database cannot be reached when the form opens | "Can't open the shop database: <reason>. [Retry] [Close]". Bound fields stay disabled until it connects. |
| An exception in your own method | A normal Python traceback. Generated code never swallows exceptions from user code. In the CBCS run console, a traceback frame inside `ui_name.py` has an **Open rule** link, because every generated block carries a comment naming its source rule. |

### 2.12 Keyboard-first editing

| Key | Action |
| --- | --- |
| Alt+B | Focus the Behavior tab for the selected widget |
| Ctrl+Shift+E | Add an event (opens "When..." with the filter focused) |
| Enter, F2 in a rule row | Edit the formula |
| Ctrl+Enter | Commit the formula. Esc cancels |
| Ctrl+Space | Complete |
| Ctrl+. | Apply the suggested fix |
| Alt+Up, Alt+Down | Move a step or check |
| Ctrl+D, Delete | Duplicate or delete a step |
| F12 | Go to the method in `name_window.py` |
| Shift+F12 | Find every rule, step and line of code that uses this widget |
| Ctrl+Shift+L | Show all logic on the canvas |
| Ctrl+Shift+F | Search this form's logic |
| Ctrl+R | Try mode |
| F4 | Draw connections (Designer parity) |
| Double-click a widget | Go to, or create, the handler for its default event |
| F2 on the canvas | Edit the widget's text in place |
| Shift+F2 | Rename the widget's object name |

The event picker, step picker and completion list are fully keyboard-driven: type to filter, then use the arrow keys and Enter.

Double-click changes Designer's behaviour on purpose. In Designer, double-clicking a button edits its text in place (R3 item 30). Here, double-clicking a button, check box or action goes to its handler, as in Delphi and VB6, which the brief already decided. In-place text editing moves to F2, and to double-click on widgets that have no meaningful event (labels and group boxes).

### 2.13 Undo, copy and paste, rename, delete

- **Undo.** Every rule, check, step, binding and connection edit is one command on the form's existing undo stack, alongside moves and property edits. Creating a handler stub through double-click or **Create method** is one compound command. Undoing it removes the connection, and also removes the stub from `name_window.py`, but only if the stub is still exactly the empty template the builder wrote (checked against a stored hash of the text). If the user has typed into it, the method stays and Problems shows "save_invoice is no longer connected to anything". If `name_window.py` is open in a code tab, the stub is inserted through that tab's document, so it also appears in the code tab's own undo history.
- **Copy and paste** carry all behaviour, because behaviour lives in the widgets' dynamic properties, and the clipboard format is a `.ui` fragment. On paste, widgets that would duplicate an existing name are renamed (`qtySpin` becomes `qtySpin2`). References *within the pasted set* are rewritten to the new names. References to widgets *outside* the set are kept. A banner says: "Pasted 3 widgets. 2 formulas now point at the copies; 1 still reads `discountCheck`." Pasting into a different form where a referenced name does not exist keeps the formula and flags it (FB101). Nothing is dropped silently. Step lists that call a method keep the call, and Problems offers to create the method in the target window.
- **Rename** goes through the token stream, not text replacement. It updates formulas (`qtySpin.text` but not the string `"qtySpin"`), step targets, error-label references, connections, tab stops and buddies. It also offers a preview to update `self.ui.oldName` in `name_window.py`, and other files that import that form, using CBCS's existing rename-refactor support. Renaming a method from the Events list renames the `def` and its callers.
- **Delete** of a widget that other logic uses asks first: "Qty (qtySpin) is used by: Line total (Value), Check on Price. Delete anyway? Those rules will show as broken." with [Delete] [Cancel]. Undo restores everything.
- **Renames made outside CBCS** (in Designer or a text editor) are detected the next time the form opens. If formulas reference names that no longer exist, a **Repair references** dialog pairs each missing name with a widget of the same class that appeared since the last save. The generated `ui_name.py` records all widget names, which gives the "before" list. Nothing is changed until the user confirms.

### 2.14 Walkthrough 1: a discount check box enables a field

Maria is building an order form. She has a check box *Discount* (`discountCheck`) and a field *Discount rate* (`discountEdit`).

1. She selects *Discount rate*, then presses Alt+B or clicks **Behavior**.
2. Under STATE, the row "Enabled when: always" is shown in grey. She clicks it.
3. Builder mode opens with one condition row. In the first box she types "disc" and picks *Discount (discountCheck)*. The second box, now showing options for a Yes/No field, already reads *is checked*.
4. The status line shows "now: no", because the check box on the canvas is unchecked. The canvas field greys out immediately.
5. She presses Ctrl+Enter. The row reads "Enabled when: Discount is checked". The field gets a `?` badge.
6. She presses Ctrl+R. In Try mode she ticks *Discount* and the field enables. She unticks it and it disables. When she closes Try mode, it is closed.

If instead she had pressed F4 and dragged an arrow from the check box to the field, choosing "toggled → setEnabled", the picker would have said:

> Keep *Discount rate* enabled only while *Discount* is checked? A rule also gets this right when the form opens and when a record loads.  **[Make it a rule]**  [Connect anyway]

What is saved is one property on `discountEdit`: `cbcsEnabledWhen` = `discountCheck`. The code generated from it is in Section 7.2.

### 2.15 Walkthrough 2: invoice line total live = qty × price

Tom has `qtySpin` (`QSpinBox`), `priceSpin` (`QDoubleSpinBox`, 2 decimals) and a label `lineTotalLabel`.

1. He selects the label. In Behavior, he clicks "Value: shown as designed".
2. Formula mode opens, because values default to formula mode. He types `qty` and completion offers `qtySpin   Qty   Whole number`. He presses Tab, types ` * pri` and Tab again.
3. The status line reads "Number   now: 6   as words: Qty × Price".
4. He opens **Format** on the same row and picks *Money*. "now:" becomes `$6.00`, and the canvas label shows `$6.00`.
5. Being an Excel user, he first typed `=qtySpin*priceSpin`. The editor showed "Formulas don't start with `=` [Ctrl+. remove]", and one keystroke fixed it.
6. In Try mode, changing either spin box updates the label as he types.

For line items in a grid, the same formula appears as a **calculated column** `lineTotal = qty * price` in the grid editor (5.6). The invoice total is then `sum(linesView.lineTotal)`. Sections 7.3 and 7.7 show both.

### 2.16 Walkthrough 3: Save checks the form, then calls the developer's method

Priya owns the code. She wants Save to check the fields, then run her own `save_invoice` method.

1. She double-clicks the **Save** button. Because Save has no clicked behaviour yet, the builder:
   - suggests the name `save_invoice`, from the button's text "Save" and the form name "Invoice";
   - adds `<slot>save_invoice()</slot>` and a `<connection>` from `saveButton.clicked()` to it;
   - adds this to `InvoiceWindow` in `invoice_window.py` and opens the file at the `pass`:
     ```python
     def save_invoice(self):
         """Runs when saveButton is clicked."""
         pass
     ```
   She is now in the code editor. If she presses Ctrl+Z in the form builder right away, both the connection and the empty stub go away.
2. Back in the builder, she selects the email field and adds the checks **Required** and **Email address**. CBCS offers to add an error label under the field ("Show messages under the field? [Add label]"). She accepts, and `emailEditError` is inserted into the layout under `emailEdit`.
3. She opens Save's Events list. It shows `When clicked: 1 Call save_invoice()`. She presses **+ Then...** and picks **Check all fields**, then presses Alt+Up to move it first. The list now reads `1 Check all fields (stops here if a field fails), 2 Call save_invoice()`. The builder converts the storage from a `<connection>` to `cbcsOnClicked` automatically. The `<slot>` declaration stays.
4. In Try mode, clicking Save with an empty email shows "Email is required" under the field and focuses it. The Try log says "Save stopped at step 1". With a valid email, the log says "Would call save_invoice()".
5. In `save_invoice` she writes her repository call. She can read values with `self.ui.emailEdit.text()`, or call `self.ui.cbcs_validate()` herself elsewhere.

The generated code is in Section 7.5.

---

## 3. Levels 1 and 2 in detail

### 3.1 The friendly signal and slot picker

The picker is organised by **intent**, not by signal. After picking the sender's event, the user picks *what should happen*. Each intent maps to an exact Qt connection or to a rule.

| Sender | Intent shown | Stored as |
| --- | --- | --- |
| Any button | Close this form / Accept (OK) / Cancel | `clicked()` to form `close()`, `accept()` or `reject()` |
| Any button | Clear *field* | `clicked()` to `field.clear()` |
| Any button | Move focus to *field* | `clicked()` to `field.setFocus()` |
| Any button | Call a method in your window... | Level 2 connection |
| `QCheckBox` and `QRadioButton` | Enable, show or make read-only *field* while checked | **an *Enabled when* / *Visible when* / *Read-only when* rule** (Decision 2) |
| `QCheckBox` | Check *other check box* too | `toggled(bool)` to `setChecked(bool)` |
| `QLineEdit` | When Enter is pressed, go to *next field* | `returnPressed()` to `next.setFocus()` |
| `QLineEdit` | Copy the text into *label* | Value rule `label = thisEdit` (rule, not connection) |
| `QComboBox` | Show the matching page of *stacked widget or tabs* | `currentIndexChanged(int)` to `setCurrentIndex(int)` |
| `QSlider` and `QSpinBox` | Keep *other slider or spin box* in step | Two connections, `valueChanged(int)` to `setValue(int)` in both directions. This is safe, because Qt does not emit when the value is unchanged |
| `QDialogButtonBox` | OK accepts, Cancel rejects | `accepted()` to `accept()`, `rejected()` to `reject()` (Designer's template) |
| `QAction` | Close this window / call method | `triggered()` |

Below the intents, **All slots** lists the target's real slots with the same "show inherited from QWidget" checkbox Designer has (R3 item 3). Only slots compatible with the signal are listed. Qt's rule is that a slot's parameters must be a prefix of the signal's, with matching types. Incompatible slots appear greyed with the reason ("needs a bool; clicked() sends nothing"). The picker reads signals and slots from Qt's meta-object system for stock classes, which the editor process may import. For promoted Python widgets it reads a declaration in the widget registry, never the project's code (research D).

### 3.2 Handler naming

| Rule | Example |
| --- | --- |
| A button uses its text as a verb plus the form name | Save on Invoice gives `save_invoice`. Print gives `print_invoice` |
| Other widgets use the object-name stem plus a short event | `discountCheck` toggled gives `discount_toggled`. `customerCombo` changed gives `customer_changed` |
| Always `snake_case`, a valid identifier, unique in the class | |
| **Never** starts with `on_` | so it can never also match `connectSlotsByName` (3.6) |
| Never shadows a Qt method of the window's base class | `close`, `show`, `update`, `accept`, `done` and `print` are refused with FB204. The check uses the real `QDialog` or `QMainWindow` class in the editor process, which is safe, because it is stock Qt |

The suggested name is pre-selected in an inline box, so typing replaces it. Enter accepts.

### 3.3 Stub insertion and jump-to-code

- The window class is found by parsing `name_window.py` with Python's `ast` module, never by importing it. It is the class whose methods contain `setupUi(self)` called on a `Ui_<Name>` object. If no such class is found, **Create method** is disabled and the button explains why.
- The stub is appended after the class's last method. Indentation and blank lines follow the file's existing style. The docstring states the trigger, and argument names follow the signal:
  ```python
  def discount_toggled(self, checked):
      """Runs when discountCheck is checked or unchecked."""
      pass
  ```
  Arguments are included only when the person ticks "My method receives the new value" in the picker. Otherwise the stub takes only `self`. This works because PySide6 calls a plain Python method with as many of the signal's values as the method accepts. That was verified on 6.8.3: `toggled(bool)` connected to `def f(self)` and to `def f(self, checked)` both ran.
- No `@Slot` decorator is added. Explicit connections work with plain methods (verified), and a wrongly typed `@Slot(...)` is itself a common bug. `@Slot` matters only for `connectSlotsByName` (R1, measured), and our names never use that mechanism.
- **Jump-to-code**: F12, double-clicking a *Call* step, or Ctrl+click on a method name opens `name_window.py` at the `def` line. It reuses an open tab.

### 3.4 Signature checks

Checks run on every builder save, and whenever `name_window.py` is saved. They use the `ast` parse, never an import.

| Signal sends | The method's required parameters (excluding `self`) | Result |
| --- | --- | --- |
| N values | 0 to N, with any extras having defaults, or `*args` | OK |
| N values | more than N required | **Error FB202**. PySide6 accepts the connection, then raises `TypeError: missing 1 required positional argument` *on each click*. That was verified on 6.8.3, so it has to be caught at design time |
| any | method missing | **Error FB201**, with a [Create method] fix |
| any | the method is a `@staticmethod` or `@property` | Error |
| any | the body is only `pass` or a docstring | Warning FB203 |
| any | the method is inherited from a base class in another project file | Resolved by following the import with `ast`. If the base class cannot be found: Info, "can't verify" |

### 3.5 How Level 2 connects at run time

A Level 2 connection uses the form object itself as the `<receiver>`. `uic`, and our generator, which copies `uic` exactly here, emit a direct connection to the object passed to `setupUi`. That object is your window. Verified with `lib/qt6/uic -g python` from FreeCAD 1.1.3:

```xml
<slots><slot>save_invoice()</slot></slots>
<connection>
  <sender>saveButton</sender><signal>clicked()</signal>
  <receiver>Invoice</receiver><slot>save_invoice()</slot>
</connection>
```

```python
self.saveButton.clicked.connect(Invoice.save_invoice)   # Invoice is your InvoiceWindow
```

So:

- The method must exist on the window class when `setupUi(self)` runs. A method defined in the class always does. A method attached later with `setattr` does not.
- `QUiLoader`, which builds a plain `QDialog`, prints `QObject::connect: No such slot QDialog::save_invoice()` and carries on (verified). That is the expected, harmless "logic is inert under the loader" behaviour.
- Generated `cbcsOn…` step lists call your method the same way, as `self._form.save_invoice()`. `self._form` is the object passed to `setupUi`.

### 3.6 Auto-connect by name (`connectSlotsByName`)

Grok's draft turns auto-connect off for every form. This design leaves Qt's default on. `uic` emits `QMetaObject.connectSlotsByName(Form)`, and developers following Qt tutorials expect `@Slot() def on_okButton_clicked(self)` to work. The two real traps become warnings instead:

- FB205: a method that is both explicitly connected and named `on_<object>_<signal>` would run twice.
- FB206: an `on_<object>_<signal>` method without `@Slot` will not connect (R1 measured 0 calls without the decorator).

The Events list shows auto-connected methods as rows labelled "(auto-connected by name)". The Form Settings checkbox (R3 item 7) stays available for anyone who wants it off.

---

## 4. Level 3: formulas, steps, checks and formats

### 4.1 Python subset or Excel-style? The argument

| Question | Python subset | Excel or Power Fx style |
| --- | --- | --- |
| Who are our users? | People who write their own PySide apps in CBCS. Every one of them will see Python, and many already write it | Many shop owners know Excel formulas |
| What appears in the generated file? | Nearly the same text | A translation, so the formula they typed and the code they debug differ |
| Does it carry over? | Learning `a if c else b`, `and`, `not`, `==` helps them in `name_window.py` | Excel knowledge does not help them write their window class |
| Equality | `==` (people coming from Excel type `=`) | `=` (Python developers would misread it) |
| Branching | `x if cond else y`, which reads backwards to newcomers | `IF(cond, x, y)`, which is familiar |
| Text joining | `+` | `&` |
| Parsing and safety | Python's own `ast` module plus an allowlist, about 300 lines, with exact error positions | A hand-written parser, plus a precedence table we must document |
| Prior art for this audience | Anvil bindings are single Python expressions for a Python audience | Power Fx targets people who will never see code. Our users will |

**Decision: a typed Python subset.** The two places where Excel habits are strong, equality and branching, are handled in the editor rather than by adding a second syntax:

- The editor recognises Excel-isms and offers a one-keystroke rewrite to Python (4.10). It never saves the Excel form.
- Builder mode (2.5) writes conditions and `if` / `otherwise` values for people who never want to type `x if c else y`.

This keeps the principle "one syntax, and it is the code". It also accepts that non-programmers will mostly use builder mode and sentences, not raw formulas.

### 4.2 Grammar

The language is a subset of Python 3 expressions. It is parsed with `ast.parse(text, mode="eval")` and then checked against the allowlist below. Precedence and associativity are exactly Python's.

```
formula     := conditional
conditional := or_expr [ "if" or_expr "else" conditional ]
or_expr     := and_expr { "or" and_expr }
and_expr    := not_expr { "and" not_expr }
not_expr    := "not" not_expr | comparison
comparison  := sum { comp_op sum }                 # chains allowed: 0 <= x <= 100
comp_op     := "==" | "!=" | "<" | "<=" | ">" | ">=" | "in" | "not" "in"
sum         := term { ("+" | "-") term }
term        := unary { ("*" | "/") unary }
unary       := ("-" | "+") unary | postfix
postfix     := atom [ "." NAME [ "." NAME ] ]      # see 4.5 for which attributes exist
atom        := NUMBER | STRING | "True" | "False" | "None"
             | NAME | call | "(" formula ")" | list
call        := callee "(" [ formula { "," formula } ] ")"   # positional arguments only
callee      := FUNCTION_NAME | "window" "." NAME
list        := "[" [ literal { "," literal } ] "]"   # only on the right of in / not in
literal     := NUMBER | STRING | "True" | "False" | "-" NUMBER
```

| Allowed `ast` nodes | Rejected, with the message shown |
| --- | --- |
| `Expression`, `BoolOp` (`And`, `Or`), `UnaryOp` (`Not`, `USub`, `UAdd`), `BinOp` (`Add`, `Sub`, `Mult`, `Div`), `Compare` (`Eq`, `NotEq`, `Lt`, `LtE`, `Gt`, `GtE`, `In`, `NotIn`), `IfExp`, `Call`, `Name`, `Attribute`, `Constant` (int, float, str, bool, None), `List` and `Tuple` of literals as the right side of `in` | Assignment and walrus: "Formulas can't change things. Use a *Set a field* step." `lambda`, comprehensions, `**`, `//`, `%`, bitwise operators, `is`, subscripts and slices, f-strings, keyword arguments, starred arguments, `await`, and any attribute not listed in 4.5: "Not available in formulas. Use a method (creates a stub)." |

The language deliberately has no statements, no variables, no user-defined functions, no loops and no imports. Number literals are exact decimals: `1.1` means `Decimal("1.1")`, never a binary float. `1_000` is allowed. Strings use single or double quotes with Python escape rules.

### 4.3 Types and widget kinds

Every name in a formula has a type that is known at design time. That is what makes design-time checking possible.

| Type | Python value at run time | Can be blank? |
| --- | --- | --- |
| Text | `str`, stripped of surrounding spaces | yes (`None`) |
| Whole | `int` | depends on the widget |
| Number | `decimal.Decimal`. Whole numbers are a subtype | depends |
| Money | `Decimal` rounded to 2 places. It is a Number with a default display format | depends |
| YesNo | `bool` | only for tri-state check boxes |
| Date, Time, DateTime | `datetime.date`, `datetime.time`, `datetime.datetime` | depends |
| Choice of T | the selected key (type T) or text | yes |
| Page | a tab or stack page, compared by name | no |
| Column of T | a list, only inside aggregate functions | not applicable |
| Any | the value from `window.method()` when it has no return annotation | yes |

**Kind** (`cbcsKind`) tells the builder how to read a text-holding widget. It applies to `QLineEdit`, `QLabel`, `QPlainTextEdit`, and a bound grid column. The kinds are `text` (default), `whole`, `number:N` (N decimal places), `money`, `percent` (the user types 10, the value is 0.10), `date`, `time`. A numeric kind on a `QLineEdit` also makes the generator attach a `QRegularExpressionValidator`, so letters cannot be typed. If the text still does not parse (for example "-"), the value is blank and the built-in check "Enter a number" fails.

Main value per widget class:

| Widget class | Type | Read | Blank when | Write (for *Value* and *Default* targets) |
| --- | --- | --- | --- | --- |
| `QLineEdit` | Text, or by kind | `text().strip()`, parsed by kind | empty after stripping, or unparsable | `setText(formatted)` |
| `QPlainTextEdit`, `QTextEdit` | Text | `toPlainText().strip()` | empty | `setPlainText` |
| `QLabel` | Text, or by kind | `text()` | empty | `setText(formatted)` |
| `QSpinBox`, `QSlider`, `QDial`, `QProgressBar` | Whole | `value()` | spin box only: when `specialValueText` is set and the value is at the minimum (Qt's own "no value" idiom; the builder's "Allow blank" option sets this up) | `setValue` |
| `QDoubleSpinBox` | Number, or Money when prefix is `$` and decimals is 2 | `Decimal` of `value()` rounded to `decimals()` | same special-value rule | `setValue(float(x))` |
| `QCheckBox` | YesNo | `isChecked()` | tri-state and partially checked | `setChecked` |
| `QRadioButton` | YesNo | `isChecked()` | never | `setChecked` |
| Radio group (`<buttongroup>`) | Text | the checked button's `cbcsChoice` property, or its object name | none checked | check the matching button |
| `QComboBox` with a lookup or item data | Choice of the key type | `currentData()` | index -1, or the blank first item | select by data |
| `QComboBox`, plain | Text | `currentText()` | empty | select by text, or set the text if editable |
| `QDateEdit` | Date | `date().toPython()` | the special-value rule at `minimumDate` ("Allow blank") | `setDate` |
| `QTimeEdit`, `QDateTimeEdit` | Time, DateTime | `toPython()` | the same rule | set |
| `QTabWidget`, `QStackedWidget` | Page | `currentWidget()` | never | `setCurrentWidget` |
| `QListWidget` | Text | `currentItem().text()` | no current item | select the matching item |
| Bound `QTableView` | none. Use attributes | `.count`, `.selected.<col>`, `.<col>` in aggregates | not applicable | not applicable |

Writing a value to a widget whose *Value* is calculated never puts the form into "unsaved changes" by itself. Calculated, unbound fields are not part of the record. A calculated field that is bound to a column (for example a stored total) is saved, and its change does count as a change.

### 4.4 Coercion

There is **no implicit conversion between Text and other types**. That is the big difference from Excel, and it is safe because errors are caught at design time with a fix offered.

| Expression | Result |
| --- | --- |
| Whole `+ - *` Whole | Whole |
| Whole or Number with Number, any of `+ - * /` | Number (`Decimal`) |
| Whole `/` Whole | Number (`7 / 2 == 3.5`) |
| Money with Number | Money |
| Text `+` Text | Text. A blank counts as `""` |
| Text `+` Number | **error FB102**, fixed with `text(x)` |
| Date `+` Whole, Date `-` Whole | Date (days) |
| Date `-` Date | Whole (days) |
| Comparing Number with Text | **error FB102**, fixed with `number(...)` |
| `and`, `or`, `not` | operands must be YesNo. Text and Number are rejected with "Use `not is_blank(x)`" or "Use `x != 0`" |
| A condition slot (*Enabled when* and the others) | must be YesNo. A blank result counts as **no** |
| `x in ["A", "B"]` | the list items must match x's type |

### 4.5 Names

| Name | Meaning |
| --- | --- |
| `objectName` (for example `qtySpin`) | the widget's main value (4.3) |
| `widget.text` | the displayed text: a combo's shown name, or a spin box's text with prefix |
| `widget.enabled`, `widget.visible`, `widget.checked` | the current state (YesNo) |
| `widget.count` | the number of items in a combo, or rows in a grid |
| `combo.<column>` | an extra column loaded with a lookup, for example `customerCombo.terms_days` (5.4). There is no database query at evaluation time |
| `grid.selected.<column>` | the value in the current row |
| `grid.<column>` | the whole column. Only valid inside `sum`, `count`, `avg`, `min`, `max` |
| `record.<column>` | the value of a column of the current record as loaded, including columns not bound to any widget (Level 4) |
| `form.isNew`, `form.isDirty`, `form.position`, `form.count` | record state (Level 4). `position` counts from 1 |
| `window.method()` | calls a method on your window class (4.7) |
| a page name, for example `shippingPage` | a tab or stack page, for `detailTabs == shippingPage` |

`form`, `record`, `window`, `True`, `False`, `None`, function names and anything starting with `cbcs` are **reserved**. A widget given one of those names gets FB101, with a rename offered.

### 4.6 Blank (null) rules

| Situation | Rule |
| --- | --- |
| `is_blank(x)` | true for `None`, and for an empty or whitespace-only string. `0` and `False` are **not** blank |
| `x == None`, `x == ""` | both mean `is_blank(x)`. `!=` is the opposite |
| Arithmetic | if either side is blank, the result is blank. `if_blank(price, 0) * qty` treats a blank price as zero |
| Text `+` | a blank counts as `""` |
| `<`, `<=`, `>`, `>=` with a blank | **False**, never an error |
| `sum`, `avg`, `min`, `max`, `count` | skip blanks. `sum` of nothing is 0. `avg`, `min` and `max` of nothing are blank |
| Division by zero | blank, and the target's tooltip says why (2.11) |
| A condition that is blank | **no** (disabled, hidden, not read-only, check fails only if it is a custom check) |
| Displaying a blank | empty text, or the spin box's special-value text |
| Saving a blank | `NULL`. For a `NOT NULL` text column (known from the schema), the empty string `''` is saved instead, and the binding says so |

Spin boxes are never blank unless "Allow blank" is set. This matches what users see: a spin box always shows a number.

### 4.7 Calling your code from a formula: `window.method()`

A formula may call a method on the window class: `window.is_manager()`, or `window.price_for(productCombo, qtySpin)`. This is the controlled bridge for things formulas cannot express, such as permissions, settings, or tax tables.

- The method must exist (checked with `ast`). Its return annotation gives the type (`-> bool` gives YesNo). Without an annotation the type is Any, and a condition slot wraps the result in `bool()` with an Info note.
- It runs during every rule refresh, so it should be fast and should not change anything. The method's docstring stub says so, and CBCS documents it.
- Try mode never calls it. The person supplies a value in the **window values** pane.
- Rules re-run when widgets change and after a record loads. If the method's answer changes for other reasons (a user logs in), your code calls `self.ui.cbcs_refresh()`.

### 4.8 Function library

Names follow Python where Python has the function. Other names are plain words in `snake_case`. Every function is total: it returns blank rather than raising.

| Function | Signature | Notes |
| --- | --- | --- |
| `is_blank` | `(x) -> YesNo` | |
| `if_blank` | `(x, fallback) -> T` | `if_blank(discountEdit, 0)` |
| `round` | `(n, places=0) -> Number` | half-up (2.5 becomes 3, as people expect), not Python's banker's rounding |
| `abs`, `min`, `max` | as in Python | `min` and `max` take 2 or more values, or one column |
| `sum`, `avg`, `count` | `(column) -> Number` | `count(grid)` counts rows |
| `number` | `(text) -> Number` | accepts `$1,234.50`. Blank if it does not parse |
| `whole` | `(n) -> Whole` | truncates toward zero |
| `text` | `(x, format="") -> Text` | format codes as in 4.11, for example `text(invoiceDateEdit, "date:long")` |
| `len` | `(text) -> Whole` | |
| `upper`, `lower`, `trim`, `proper` | `(text) -> Text` | `proper` gives "Title Case" |
| `left`, `right` | `(text, n) -> Text` | |
| `contains`, `starts_with`, `ends_with` | `(text, part) -> YesNo` | case-insensitive (the shop-floor expectation). `matches` is the exact tool |
| `replace` | `(text, old, new) -> Text` | |
| `matches` | `(text, pattern) -> YesNo` | the pattern must be a literal and is compiled at design time (FB105) |
| `is_email`, `is_phone`, `is_zip` | `(text) -> YesNo` | the same tests as the check presets (4.9) |
| `today`, `now` | `() -> Date / DateTime` | local time |
| `date` | `(y, m, d) -> Date` | blank if the date does not exist |
| `year`, `month`, `day`, `weekday` | `(date) -> Whole` | `weekday`: Monday is 1 |
| `add_days`, `add_months` | `(date, n) -> Date` | `add_months` clamps to the last day of the month |
| `days_between` | `(a, b) -> Whole` | |

About 35 functions in all. New functions are added to the library on purpose, release by release, never by users.

### 4.9 Checks (validation)

**Kinds**:

| Check | Stored | Passes when | Default message |
| --- | --- | --- | --- |
| Required | `{"check": "required"}` | not blank | "<Label> is required" |
| Number / whole number | implied by kind | text parses | "Enter a number" |
| Between | `{"check": "range", "min": 0, "max": 50}` | blank, or min ≤ value ≤ max. Numbers and dates. Either bound may be omitted | "<Label> must be between 0 and 50" |
| Length | `{"check": "length", "min": 2, "max": 40}` | blank, or the length is in range | "...must be 2 to 40 characters" |
| Preset | `{"check": "email"}`, `"phone"`, `"zip"` | blank, or the preset test passes | "Enter an email address like name@example.com" |
| Pattern | `{"check": "pattern", "pattern": "^[A-Z]{3}-\\d+$"}` | blank, or a full match | "<Label> is not in the right format" (write your own) |
| One of | `{"check": "oneOf", "values": ["Open", "Paid"]}` | blank, or listed | |
| Formula (cross-field) | `{"check": "formula", "formula": "dueDateEdit >= invoiceDateEdit"}` | the formula is yes | required: write the message |
| Unique (Level 4) | `{"check": "unique"}` | no other record has this value in the bound column | "Another invoice already uses this <Label>" |

Presets: `email` is `^[^@\s]+@[^@\s]+\.[^@\s]+$`, a typo catcher rather than an RFC parser. `phone` is 10 to 15 digits after removing spaces, dashes, dots and parentheses, with an optional leading `+`. `zip` is a US ZIP: `^\d{5}(-\d{4})?$`. Blank passes every check except Required, so Required plus a preset is the normal pair, and the builder suggests it.

**Native first.** When Qt can store a rule itself, the builder uses the native property instead, and shows it in the Checks list with a "Qt" tag:

| Check | Native property |
| --- | --- |
| Maximum length of a `QLineEdit` | `maxLength` |
| Range of a spin box or date edit | `minimum` / `maximum`, `minimumDate` / `maximumDate` |
| Fixed format such as a part number | `inputMask` (offered when the pattern is a simple fixed shape) |

That way the form keeps more of its behaviour in Designer and `QUiLoader`.

**When checks run.** This is the standard pattern for forms that do not scold:

1. **On leaving the field** (`editingFinished`, or focus out for other widgets), once the user has touched it. Untouched fields are not checked on the way past.
2. **While typing, but only to clear.** Once an error is showing, the field is re-checked on each change, so the message disappears as soon as the value becomes valid.
3. **On Check all fields** (a step, also run first by **Save**): every field, touched or not. Focus moves to the first failing field.
4. **Cross-field formula checks** re-run when *any* field they read changes, but only if the check is already showing.
5. **Unique** runs only on Save, because it needs one query.

Each field shows **its first failing message only**. The order in the Checks list is the priority.

**Where messages show.** In the field's error label (`cbcsErrorLabel`, a normal `QLabel` that the builder inserts under the field, and that the person can move or restyle). The field also gets the dynamic property `cbcsInvalid=true`, so a style sheet rule such as `*[cbcsInvalid="true"] { border: 1px solid #c62828; }` from the project theme outlines it. The message is also the field's tooltip. Without an error label, the tooltip and outline still work, and Problems shows an Info row. An optional `cbcsErrorSummary` label on the form lists "2 fields need attention" after a failed save.

### 4.10 Editor help for Excel habits

Each of these is recognised and offered as a one-keystroke fix (Ctrl+.). Only the Python form is saved.

| Typed | Message | Fix |
| --- | --- | --- |
| `=a*b` (leading `=`) | Formulas don't start with `=` | `a*b` |
| `a = b` in a condition | Use `==` to compare | `a == b` |
| `a <> b` | Use `!=` | `a != b` |
| `IF(c, x, y)` | Write `x if c else y` | rewritten |
| `AND(a, b)`, `OR(a, b)`, `NOT(a)` | Use `and`, `or`, `not` | rewritten |
| `a & b` | Join text with `+` | `text(a) + text(b)` |
| `TRUE`, `true`, `FALSE` | | `True`, `False` |
| `ISBLANK(x)`, `x = ""` | | `is_blank(x)` |
| `10%` | | `0.10` |
| `&&`, `\|\|`, `!` | | `and`, `or`, `not` |
| `Qty * Price` (display names) | These are labels | `qtySpin * priceSpin` |

### 4.11 Formats

`cbcsFormat` changes how a value is *shown*, never the value itself. Formulas always read the value.

| Format | Shows | Applies to |
| --- | --- | --- |
| `money` | `$1,234.50`, with negatives as `-$12.00` | `QLabel`, `QLineEdit` (formatted on leaving the field, raw while editing), grid columns |
| `number:N` | `1,234.5` with N places | same |
| `percent:N` | `12.5%` | same |
| `date:short`, `date:long`, `date:iso` | `10/20/2026`, `October 20, 2026`, `2026-10-20` | labels and line edits. `QDateEdit` uses its native `displayFormat` |
| `text:upper`, `text:proper` | applied when leaving the field, and also changes the stored text | line edits |

The currency symbol, separators and short-date order come from the project manifest (`cbcs/project.json`, key `"formats"`), defaulting to US English. See open question 3. For spin boxes the builder sets the native `prefix` and `decimals` instead (native first).

### 4.12 Event steps (the action vocabulary)

A step list is a JSON array of step objects. Every step may have a `"when"` formula. A false `when` skips that step and continues.

| UI words | JSON | Effect | Can stop the list? |
| --- | --- | --- | --- |
| Check all fields | `{"do": "validate"}`, or with `"fields": ["emailEdit", ...]` | runs checks (4.9) | **yes**, if any check fails |
| Set a field | `{"do": "set", "field": "totalEdit", "formula": "..."}` | writes the main value | no |
| Clear fields | `{"do": "clear", "fields": [...]}` | sets each field to blank, or its minimum | no |
| Move focus to | `{"do": "focus", "field": "..."}` | | no |
| Enable, disable, show, hide | `{"do": "enable", "field": "..."}` and so on | a one-off change. The builder warns if a rule also controls that property | no |
| Show a message | `{"do": "message", "level": "info", "text": "Saved."}`, or `"formula"` instead of `"text"` | `QMessageBox` | no |
| Ask yes or no | `{"do": "ask", "text": "Delete this line?"}` | `QMessageBox.question` | **yes**, on No |
| Stop here if | `{"do": "stop", "when": "...", "message": "..."}` | shows the optional message | **yes** |
| Switch tab or page | `{"do": "page", "field": "detailTabs", "page": "shippingPage"}` | | no |
| Open another form | `{"do": "openForm", "form": "customer", "mode": "dialog", "key": "customerCombo", "then": "refreshLookups"}` | imports `forms.customer_window`, opens it, and loads the record with that key if one is given. In `dialog` mode, the list continues after the dialog closes | no |
| Close this form | `{"do": "close", "result": "accept"}` (`accept`, `reject` or `close`) | runs the unsaved-changes prompt first | **yes**, if the user cancels |
| Call a method | `{"do": "call", "method": "save_invoice"}` | `self._form.save_invoice()` | **yes**, if it returns `False`. Exceptions propagate |
| New, Save, Delete, Undo changes, Reload | `{"do": "new"}`, `"save"`, `"delete"`, `"revert"`, `"reload"` | Level 4 (5.5) | **yes**, if the step fails or is cancelled |
| First, Previous, Next, Last | `{"do": "first"}` and so on | Level 4. Asks about unsaved changes | **yes**, if the user cancels |
| Find | `{"do": "find"}` | Level 4 (5.5) | no |
| Reload lookups | `{"do": "refreshLookups", "fields": [...]}` | re-runs the lookup queries | no |
| Add line, Delete line | `{"do": "addRow", "grid": "linesView"}`, `"deleteRow"` | Level 4 grid | Delete asks first |

Execution is strictly sequential and synchronous. The next step starts only after the previous one returns, and modal dialogs block. Exceptions from your methods are never caught, so you get a real traceback (P6).

Not in the vocabulary, deliberately: loops, variables, "for each row", HTTP calls, file writes, timers, printing, and arbitrary SQL. Each of those is one *Call a method* step away (Section 8).

---

## 5. Level 4: data binding

### 5.1 Connections and credentials

A **connection** is a named definition in the project. The builder edits it through Project Settings → Connections. It is stored in `connections.json` at the project root, which is shipped with the app and holds **no passwords**:

```json
{
  "shop": {"engine": "sqlite", "file": "data/shop.db"},
  "office": {"engine": "postgres", "host": "192.168.1.20", "port": 5432,
             "database": "shop", "user": "clerk"}
}
```

When the first data source is added, the builder creates **`cbcs_connections.py`** once, at the project root. It is user-owned, like `name_window.py`. Generated forms call `open_connection("shop")` from it, unless the form names a connection hook (5.9). It contains plain, readable code that:

- opens SQLite paths relative to the project;
- for PostgreSQL, tries drivers in order: `cb_psycopg.connect` (ChoreBoy's vendored bootstrap, per pitfalls C-1), then `psycopg`, then `pg8000`. The first one that imports wins. If none does, the error says which drivers it tried and suggests the vendor bundle;
- runs `SET client_encoding TO 'UTF8'` on every PostgreSQL connection (pitfalls B-1);
- keeps one open connection per name for the app's lifetime;
- resolves the password in this order: `set_password(name, pw)` called by your login dialog; then `~/.config/<app>/connections.local.json` (per machine, file mode 0600, which may also override host and port); then a one-time password prompt (`QInputDialog` with hidden echo) that is kept in memory for the session only.

Nothing secret is ever written into `.ui`, `ui_*.py`, `connections.json` or the project manifest. The editor's Data panel uses the same files for schema reads. Its password, if one is needed, is held in memory for the editor session only.

Why a project file rather than inlining the code in every form: driver probing, encoding and credential lookup are about 80 lines that must be identical in every form, and must be changeable in one place when ChoreBoy's driver story changes. Keeping that file user-owned, readable, and created only once keeps it in the spirit of "no runtime library". Open question 1 asks you to confirm this reading.

### 5.2 Form data source (`cbcsData` on the form)

| Setting | Values | Default |
| --- | --- | --- |
| connection | a name from `connections.json` | the only one, if there is one |
| table | a table name. Record forms edit a single table, so that save knows where to write | |
| key | the primary key column | read from the schema |
| order | a list of `[column, "asc" or "desc"]` | `[[key, "asc"]]` |
| openAt | `first`, `last`, `new`, `none` (wait for `cbcs_open(key)`) | `first`, after ordering |
| conflicts | `check` (warn if the row changed since load) or `overwrite` | `check` |
| deleteLines | `true` deletes line rows with the record | `true` when the form has a lines grid |
| hooks | explicit method names (5.9) | none |

A *query* (read-only `SELECT`) is allowed as the source of a **list screen** (5.7), but not of a record form. Joins for display are done with lookups (5.4), so a record form always has one obvious table to write to.

### 5.3 Field bindings

`cbcsBind` on a widget names its column. The type mapping is checked against the schema at design time:

| Column type (SQLite affinity, or PostgreSQL type) | Suggested widget | Value conversion |
| --- | --- | --- |
| INTEGER, `int4`, `int8`, `serial` | `QSpinBox`, or a lookup `QComboBox` for foreign keys | `int` |
| NUMERIC, REAL, `numeric(p,s)`, `float8` | `QDoubleSpinBox`, or `QLineEdit` with kind `number:s` or `money` | `Decimal(str(v))` on read. SQLite: bound as `str` (Python's `sqlite3` cannot bind `Decimal`, verified; column affinity stores a number). PostgreSQL: bound as `Decimal` |
| TEXT, `varchar(n)`, `text` | `QLineEdit` (with native `maxLength` = n) or `QPlainTextEdit` | `str`. Blank is saved as NULL, or `''` for NOT NULL columns |
| a column whose name or type contains `date` | `QDateEdit` | SQLite: ISO text `YYYY-MM-DD`, converted explicitly in both directions (Python 3.12 deprecates the default adapters). PostgreSQL: `date` |
| BOOLEAN, or INTEGER 0/1 named `is_*` / `has_*` | `QCheckBox` | SQLite 0/1. PostgreSQL `boolean` |

A binding can be marked **read-only** (shown, never written), for computed or audit columns such as `created_at`.

### 5.4 Lookups (combos filled from a table)

`cbcsLookup` on a `QComboBox`:

```json
{"table": "customers", "key": "id", "show": "name", "order": "name",
 "also": ["terms_days", "phone"], "blank": "(choose a customer)"}
```

- The lookup loads when the form opens, and again on **Reload lookups**, which the *Open another form → then* option uses after editing a customer. It never reloads per keystroke.
- `also` columns travel with each item, so formulas can read `customerCombo.terms_days`, for example `Default = add_days(invoiceDateEdit, customerCombo.terms_days)`, with no query at evaluation time (P8).
- An optional first item (`blank`) makes "no selection" possible. Pair it with Required.
- Type-ahead: if the combo is editable, the generator attaches a `QCompleter` with case-insensitive contains-matching. For lists over 2,000 rows, the builder suggests a search dialog step instead of a combo.
- A record whose key is not in the lookup list (for example an inactive customer) is still shown: the item is added as "(unknown #17)" rather than silently changing the value.

### 5.5 Record navigation, toolbar, New, Save, Delete, Find

**Loading.** On open, the form runs one query for keys only: `SELECT "id" FROM "invoices" ORDER BY ...`. That is 100,000 integers, about a megabyte, in milliseconds. Showing a record fetches that one row by key, then its lines. Positions ("Record 3 of 120") come from the key list.

**Insert record toolbar** (Data panel) inserts a horizontal layout of ordinary widgets, each with ordinary steps and rules:

| Widget | Steps | Rule | Native shortcut |
| --- | --- | --- | --- |
| `firstButton`, `previousButton` | first, previous | Enabled when `form.position > 1` | Ctrl+Home, PgUp |
| `positionLabel` | | Value = `"Record " + text(form.position) + " of " + text(form.count)` | |
| `nextButton`, `lastButton` | next, last | Enabled when `form.position < form.count` | PgDown, Ctrl+End |
| `newButton` | new | | Ctrl+N |
| `saveButton` | save | Enabled when `form.isDirty or form.isNew` | Ctrl+S |
| `revertButton` | revert | Enabled when `form.isDirty` | |
| `deleteButton` | ask "Delete this invoice?", delete | Enabled when `not form.isNew` | |
| `findButton` | find | | Ctrl+F |

Shortcuts use each button's native `shortcut` property. Every piece can be deleted, restyled or given extra steps. This is Decision 11: the toolbar is built from the same parts a person could build by hand, so there is nothing magic to debug.

| Verb | Behaviour |
| --- | --- |
| **New** | Asks about unsaved changes, then clears the fields, applies *Default* rules, empties the lines, and sets `form.isNew`. The key stays blank until saved |
| **Save** | Runs all checks. Runs the Before saving form event and the `beforeSave` hook, either of which can cancel. Inserts or updates the record and lines in **one transaction**. Commits, then re-reads the record (so database defaults and triggers show up), then runs After saving and `afterSave`. Returns `True` or `False` |
| **Delete** | Runs Before deleting and `beforeDelete`. Deletes the lines, if `deleteLines` is set, then the record, in one transaction. Moves to the next record, or the previous one, or New |
| **Undo changes** (`revert`) | Reloads the current record from the database. New records are cleared |
| **Find** | Asks for text, searches the configured search columns (default: every bound text column) with case-insensitive `LIKE`, and narrows the key list: "Showing 3 matches. [Show all]". Real search screens are list forms (5.7) |
| First, Previous, Next, Last | Ask about unsaved changes, then show that record |

**Unsaved changes.** `form.isDirty` is computed by comparing the current field values (and line rows) with the snapshot taken at load. Typing a change and then typing it back is *not* dirty, and changes made by your code count automatically. The prompt reads "Save changes to this invoice? [Save] [Discard] [Cancel]". It appears before navigating, before New, before *Open another form* in window mode, before Close, and on the window's close button. The generated code catches the close with an event filter, so your window file is never edited (verified on 6.8.3: ignoring the `Close` event in a filter makes `close()` return `False`). For a `QDialog`, Escape calls `reject()`. The generated `_cbcs_close_guard` also covers the Escape key on dialogs.

**Concurrent edits** (`conflicts: check`, the default). An update includes the originally loaded values in its `WHERE` clause. SQLite uses `"col" IS ?`. PostgreSQL 9.3 uses `"col" IS NOT DISTINCT FROM %s`, which handles NULL. If no row matches, nothing is written and the person is told (2.11). Only the parent record is checked. Line rows are last-writer-wins, and that is documented. This replaces the draft's "zero rows means deleted" with a check that also catches *changed*, which matters on PostgreSQL with two clerks.

### 5.6 Master-detail line items

`cbcsRows` on a `QTableView`:

```json
{"table": "invoice_lines", "link": "invoice_id", "key": "id", "order": "line_no",
 "position": "line_no",
 "columns": [
  {"column": "product_id", "header": "Product", "lookup": {"table": "products", "key": "id", "show": "name", "also": ["price"]}},
  {"column": "description", "header": "Description"},
  {"column": "qty", "header": "Qty", "kind": "whole", "default": "1"},
  {"column": "price", "header": "Price", "kind": "money", "default": "product_id.price"},
  {"name": "lineTotal", "header": "Total", "kind": "money", "formula": "qty * price"}
 ]}
```

- The model is a `QStandardItemModel` built by generated code. A lookup column gets a generated combo delegate. Numeric kinds get Qt's standard spin-box editors. Calculated columns are read-only. In a column's formula, the other columns of the same row are plain names (`qty`, `price`), and `product_id.price` reads a lookup's `also` column.
- **Add line** appends a row with the column defaults. **Delete line** asks first, then removes the row and records its key in a *deleted* list. Ctrl+Insert and Ctrl+Delete on the grid do the same.
- **Save** writes, inside the parent's transaction: deletes for the recorded keys, updates for changed rows (compared with the snapshot), and inserts for new rows with the link column set to the parent key. `position` is rewritten as the row order (1, 2, 3...). Rows another user added meanwhile are untouched. That is why explicit deletes replace the draft's `NOT IN`.
- Form formulas reach the grid through aggregates: `sum(linesView.lineTotal)`, `count(linesView)`.
- Column checks (Required, Between) are shown as a red cell with a tooltip. Check all fields reports "Line 3: Qty is required" and selects that cell.
- Version 1 allows **one** lines grid per form, and one level deep. The schema allows more, and the generator refuses more with a Problems error until a later phase.

### 5.7 List and search screens

A list screen is a form whose `cbcsData` has `"mode": "list"`. It typically holds a search box, a `QTableView`, and New and Open buttons.

```json
{"mode": "list", "connection": "shop", "table": "customers",
 "columns": ["name", "phone", "city"], "search": ["name", "phone", "email"],
 "searchField": "searchEdit", "order": [["name", "asc"]], "limit": 500,
 "open": {"form": "customer", "key": "id"}}
```

- Typing in `searchEdit` re-queries after 250 ms of quiet. The search is `LIKE ? ESCAPE '\'` on SQLite, which is case-insensitive for ASCII, and `ILIKE %s` on PostgreSQL. `%` and `_` in the search text are escaped.
- **No silent truncation**: when more rows match than `limit`, a label says "Showing the first 500 of 1,284. Type more to narrow the list." This is the Power Apps delegation lesson.
- Enter or double-click opens the record form in a dialog with that key. When the dialog closes, the list re-runs its query and keeps the selection.
- Instead of a table, the source may be a fixed read-only `query` (`SELECT ... FROM ... JOIN ...`). Search and order are applied by wrapping it: `SELECT * FROM (<query>) AS q WHERE ...`. Wrapping works on SQLite and on PostgreSQL 9.3. There is never any templating inside the user's SQL.
- Optional filter widgets: `{"filters": [{"field": "statusCombo", "column": "status"}]}`. A blank filter widget means "any".

### 5.8 SQL that is safe on PostgreSQL 9.3 and SQLite

| Concern | Rule |
| --- | --- |
| Driver interface | DB-API 2.0 only: `cursor()`, `execute(sql, params)`, `fetchone`, `fetchall`, `commit`, `rollback`. That works with `sqlite3`, `psycopg` 3 and `pg8000` alike |
| Placeholders | `?` for SQLite. `%s` for PostgreSQL (psycopg format style. pg8000's DB-API default is also `format`) |
| Identifiers | always double-quoted. Names must match `^[A-Za-z_][A-Za-z0-9_]*$`, or the binding is refused at design time. Values are **always** parameters |
| New keys | SQLite: `cursor.lastrowid`. PostgreSQL: `INSERT ... RETURNING "id"` (present in the 9.3 manual's INSERT synopsis) |
| Upsert | never generated. A form always knows whether it is inserting or updating. No `ON CONFLICT` (pitfalls A-1) |
| JSON columns | not generated. No `JSONB` |
| NULL-safe comparison | SQLite `IS`. PostgreSQL `IS NOT DISTINCT FROM` |
| Case-insensitive search | SQLite `LIKE`. PostgreSQL `ILIKE` |
| Transactions | each verb is a `try` block: `commit()` on success, and `rollback()` then re-raise on *any* exception, so a shared connection never stays in a failed transaction (pitfalls E-1) |
| Encoding | `SET client_encoding TO 'UTF8'` in `cbcs_connections.py`. Results are passed through a bytes-to-str guard (pitfalls B-2) |
| Error mapping | SQLite `IntegrityError` text ("UNIQUE constraint failed: invoices.invoice_no", "NOT NULL constraint failed: ...") and PostgreSQL SQLSTATE `23505`, `23502` and `23503` are mapped to the bound field's error label |

### 5.9 How a developer overrides any piece

| Want | How |
| --- | --- |
| Run code before or after save, load or delete | Data panel → Python hooks → [create]. Writes `"hooks": {"beforeSave": "before_save"}` and a stub. `before_save()` returning `False` cancels. Hook names: `afterLoad`, `beforeSave`, `afterSave`, `beforeDelete`, `afterDelete`, `newRecord` |
| Use the app's own existing connection (for example Iron Advantage's executor) | the hook `"connection": "db_connection"` → `def db_connection(self, name): return self.app.db`. Generated code then calls it instead of `cbcs_connections` |
| Replace Save entirely | Change the Save button's steps to *Call a method*. Inside it, use the building blocks: `self.ui.cbcs_validate()`, `self.ui.cbcs_read_fields()` (a dict of column to value), `self.ui.cbcs_read_lines()`, `self.ui.cbcs_mark_saved(key)` |
| Load a record from your code | `self.ui.cbcs_open(key)` |
| Fill fields from your own dict | `self.ui.cbcs_write_fields(row_dict)`, then `self.ui.cbcs_refresh()` |
| Ask "is anything unsaved?" | `self.ui.cbcs_is_dirty()`, `self.ui.cbcs_confirm_leave()` |
| Re-run rules after your code changes something rules read | `self.ui.cbcs_refresh()` |
| Turn off one generated event without deleting it | in the Events list, untick *Enabled*. It is stored as `"enabled": false` and generates no connection |
| Leave the no-code data layer | **Eject to code**: copies the generated data methods into the window class as ordinary methods (with SQL as plain strings), removes `cbcsData`, `cbcsBind`, `cbcsLookup` and `cbcsRows`, and rewires the steps to *Call a method*. One undoable command. It is one-way after that |

The public names above are documented as a stable API. Everything else is `_cbcs_` and private.

---

## 6. Storage

### 6.1 Property names

All logic properties are Qt dynamic properties with `stdset="0"`. Formulas and JSON are saved as `<string notr="true">`. Verified on FreeCAD 1.1.3: `uic` passes them through as `setProperty`, multi-line text included, and `QUiLoader` keeps them.

| Property | On | Value | Example |
| --- | --- | --- | --- |
| `cbcsLogic` | form root | `<number>`, the logic schema version | `1` |
| `cbcsEnabledWhen` | any widget | formula (YesNo) | `discountCheck` |
| `cbcsVisibleWhen` | any widget | formula (YesNo) | `not form.isNew` |
| `cbcsReadOnlyWhen` | input widgets | formula (YesNo) | `record.status == "Paid"` |
| `cbcsValue` | value widgets | formula, a calculated value | `qtySpin * priceSpin` |
| `cbcsDefault` | value widgets | formula, applied on open and on New | `today()` |
| `cbcsKind` | `QLineEdit`, `QLabel`, `QPlainTextEdit` | kind code | `money` |
| `cbcsFormat` | `QLabel`, `QLineEdit` | format code | `money` |
| `cbcsValidate` | input widgets | JSON array of checks | see 6.2 |
| `cbcsErrorLabel` | input widgets | the error label's object name | `emailEditError` |
| `cbcsErrorSummary` | form root | a label's object name | `formErrors` |
| `cbcsOn<Signal>` | any widget or action | JSON array of steps | `cbcsOnClicked` |
| `cbcsOn<FormEvent>` | form root | JSON array of steps | `cbcsOnOpened`, `cbcsOnClosing`, `cbcsOnRecordLoaded`, `cbcsOnNewRecord`, `cbcsOnBeforeSave`, `cbcsOnAfterSave`, `cbcsOnBeforeDelete` |
| `cbcsData` | form root | JSON object | 5.2 or 5.7 |
| `cbcsBind` | input widgets | column name | `customer_id` |
| `cbcsBindMode` | input widgets | `readOnly` (optional) | |
| `cbcsLookup` | `QComboBox` | JSON object | 5.4 |
| `cbcsRows` | `QTableView` | JSON object | 5.6 |
| `cbcsChoice` | `QRadioButton` | text value within its group | `Card` |

`cbcsOn<Signal>` is `cbcsOn` followed by the signal name with its first letter in upper case: `clicked` becomes `cbcsOnClicked`, `currentIndexChanged` becomes `cbcsOnCurrentIndexChanged`. In the rare case that a Qt 6 widget has two overloads of the same signal name, the array is wrapped as `{"signal": "valueChanged(int)", "steps": [...]}`. Signal names come from the class's meta-object, so the mapping is exact.

### 6.2 JSON schemas (version 1)

Written as TypeScript-style shapes for brevity. `?` marks an optional key. `Formula` is a string in the formula language (Section 4).

```ts
type Check =
  | {check: "required", message?: string}
  | {check: "range", min?: number|string, max?: number|string, message?: string}   // string = formula, e.g. "today()"
  | {check: "length", min?: number, max?: number, message?: string}
  | {check: "email"|"phone"|"zip", message?: string}
  | {check: "pattern", pattern: string, message: string}
  | {check: "oneOf", values: (string|number)[], message?: string}
  | {check: "formula", formula: Formula, message: string}
  | {check: "unique", message?: string}

type Step = {do: StepVerb, when?: Formula, enabled?: false, /* verb fields, 4.12 */ }

type Data =        // record form
  {connection: string, table: string, key: string,
   order?: [string, "asc"|"desc"][], openAt?: "first"|"last"|"new"|"none",
   conflicts?: "check"|"overwrite", deleteLines?: boolean, search?: string[],
   hooks?: {afterLoad?: string, beforeSave?: string, afterSave?: string,
            beforeDelete?: string, afterDelete?: string, newRecord?: string,
            connection?: string}}
 | {mode: "list", connection: string, table?: string, query?: string,
    columns: string[], search?: string[], searchField?: string,
    filters?: {field: string, column: string}[],
    order?: [string, "asc"|"desc"][], limit?: number,
    open?: {form: string, key: string}}

type Lookup = {table: string, key: string, show: string, order?: string,
               also?: string[], blank?: string}

type Rows = {table: string, link: string, key: string, order?: string, position?: string,
             columns: ({column: string, header?: string, kind?: string, lookup?: Lookup,
                        default?: Formula, readOnly?: true, validate?: Check[]}
                     | {name: string, header?: string, kind?: string, formula: Formula})[]}
```

A full example of a widget with logic:

```xml
<widget class="QLineEdit" name="emailEdit">
 <property name="cbcsBind" stdset="0">
  <string notr="true">email</string>
 </property>
 <property name="cbcsErrorLabel" stdset="0">
  <string notr="true">emailEditError</string>
 </property>
 <property name="cbcsValidate" stdset="0">
  <string notr="true">[
  {"check": "required"},
  {"check": "email", "message": "Enter an email address like name@example.com"}
]</string>
 </property>
</widget>
```

### 6.3 Determinism (clean diffs)

- Logic properties are written **after** all standard properties of a widget, in the fixed order of the table in 6.1. Standard properties keep the builder's general canonical order.
- A property is omitted when it is empty or at its default. A rule removed in the UI removes the element. It never leaves `<string notr="true"></string>`.
- JSON is canonical: keys in schema order (the order in 6.2), no trailing spaces, `ensure_ascii=False`, and integers without `.0`. **Arrays of objects are written one object per line, objects inside one line.** A small object such as a lookup is written on a single line. Adding a check is a one-line diff. Reordering two steps is a two-line diff.
- Formula text is saved exactly as normalised by the editor: single spaces around binary operators and after commas, no other changes. Normalising happens when the formula is committed, so saving twice gives identical bytes.
- XML escaping (`<`, `&`) is done by the writer. Readers unescape. `>` is written unescaped, as Qt does.
- Two saves of an unchanged form produce identical files. This is a test, not a hope (9.1).

### 6.4 References across renames

References to other widgets inside formulas and steps are **object names**, chosen deliberately over hidden IDs:

| Option | For | Against |
| --- | --- | --- |
| **Object names (chosen)** | Readable in the file, in Designer and in the generated code. Matches how Qt itself references widgets (connections, buddies, tab stops) | A rename outside CBCS breaks references |
| A hidden `cbcsId` on each widget, with references by ID | Survives external renames | An unreadable property on every widget. Designer's copy and paste duplicates the IDs. Formulas become unreadable in the file and in Designer |

Inside CBCS, renames are propagated through tokens (2.13). Outside CBCS, the **Repair references** dialog fixes them on the next open (2.13). Bindings (`cbcsBind`) and checks live on the widget itself, so they never need repair.

### 6.5 When a file is edited in Qt Designer and comes back

| What happens in Designer | What CBCS does on open |
| --- | --- |
| Layout and property edits | nothing special |
| Dynamic properties are kept (stated in the brief, verified for `uic` and `QUiLoader`) but possibly re-ordered, or saved without `notr` | read them regardless of order and `notr`. The next CBCS save re-canonicalises (a one-time diff) |
| A dynamic property's text is edited in Designer's property editor | it is parsed like any other. Errors go to Problems (FB401) and the text is kept exactly |
| A widget with logic is copied | its logic is copied too. Duplicate references are fine |
| A widget is renamed | Repair references (2.13) |
| A referenced widget is deleted | broken references are listed in Problems. Nothing is removed |
| Native connections are added or removed | the Events list shows them. A signal that has both native connections and a `cbcsOn` list gets the "two places" warning and [Merge] |
| `connectslotsbyname` is changed | respected |

**Forward compatibility.** Readers preserve unknown `cbcs*` properties and unknown JSON keys verbatim when saving. A `cbcsLogic` version newer than the editor supports makes the logic read-only (FB402). The layout stays editable and the logic is written back untouched. A version-1 editor never silently drops data written by a version-2 editor.

Note for the engineering team: `QFormBuilder.save()` is **not** a model of Designer's serializer. In this session's experiment it dropped every dynamic property on a load-and-save round trip. Round-trip tests against Designer must use the real Designer, by hand or scripted (9.2).

---

## 7. Code generation

### 7.1 Shape of the generated module

`ui_name.py` is the `uic`-identical module (widget construction, `retranslateUi`, native connections, `connectSlotsByName`), plus, only when the form has logic:

```
header banner
imports (PySide6 + only what logic needs: decimal, datetime, re, sqlite3,
         cbcs_connections)
class Ui_Invoice(object):
    setupUi(self, Invoice)            # uic-identical, then: self._cbcs_setup(Invoice)
    retranslateUi(self, Invoice)      # uic-identical
    # ---- Behaviour ------------------------------------------------------
    _cbcs_setup                       # connect rule inputs, checks, events; first refresh
    cbcs_refresh                      # every rule, in dependency order
    _cbcs_check_<field> ...           # one function per checked field
    cbcs_validate
    _cbcs_<widget>_<signal> ...       # one function per step list
    # ---- Data -----------------------------------------------------------
    cbcs_open, cbcs_read_fields, cbcs_write_fields, cbcs_save, ...
helper classes (only if used): _CbcsLines, _CbcsCloseGuard, _CbcsLookupDelegate
helper functions (only if used): _cbcs_dec, _cbcs_mul, _cbcs_money, ...
```

The banner:

```python
################################################################################
## Generated from invoice.ui by ChoreBoy Code Studio. Do not edit this file:
## it is rewritten every time the form is saved. Put your code in
## invoice_window.py.
## The behaviour below (rules, checks, data) runs only through this file.
## Loading invoice.ui with QUiLoader gives the layout without the behaviour.
################################################################################
```

Rules of the generator:

1. **Readable first.** Each block starts with a comment quoting its source, for example `# lineTotalLabel: Value = qtySpin * priceSpin`. Variable names come from the widgets. When types prove that a value cannot be blank (for example spin boxes), plain operators are emitted. Null-safe helpers are used only where a value could be blank.
2. **Helpers are emitted only if used**, at the bottom, in a fixed order. They are identical in every form, so a reader learns them once. There is no shared runtime module (as decided).
3. **Deterministic.** The same `.ui` file always gives the same bytes. Rules are sorted topologically, and ties are broken by widget tree order.
4. **Python 3.11 and PySide6 only.** No `match`, no f-string tricks that go beyond readability. Enums are written in full (`QMessageBox.StandardButton.Save`), matching `uic` 6.8.
5. **Never catches user exceptions.** Helpers are total, so they never raise. User methods propagate.
6. **Refresh algorithm.** One `cbcs_refresh()` recomputes every *Value* rule in dependency order, then every state rule. It is protected by a re-entrancy flag, because writing a calculated field fires that field's change signal. Every widget read by any rule has its change signal connected to `cbcs_refresh`. The cost is about a microsecond per rule per change, which is negligible for forms with a few hundred rules. Narrower refreshes are a later optimisation, invisible in the file format.

The scenario code below was checked in this session. A stand-in `ui_invoice.py` with these behaviour sections (and simplified widget construction) ran under FreeCAD 1.1.3's Python with an offscreen display against a temporary SQLite database. The test checked the enable rule, $6.00 for 2 × 3.00, the email messages, that the method is called only after checks pass, the lookup contents, a $16.50 total recalculated to $22.50 after an edit to a line, a blocked conflicting save, an insert with lines, and the close guard.

### 7.2 Scenario 1: the discount check box enables a field

```python
    def _cbcs_setup(self, Invoice):
        self._form = Invoice
        self._cbcs_refreshing = False
        # Rule inputs: when any of these change, the rules run again.
        self.discountCheck.toggled.connect(self.cbcs_refresh)
        self.cbcs_refresh()

    def cbcs_refresh(self, *args):
        """Run every rule on this form again. Safe to call from your own code."""
        if self._cbcs_refreshing:
            return
        self._cbcs_refreshing = True
        try:
            # discountEdit: Enabled when  discountCheck
            self.discountEdit.setEnabled(self.discountCheck.isChecked())
        finally:
            self._cbcs_refreshing = False
```

### 7.3 Scenario 2: line total = qty × price, live

```python
            # lineTotalLabel: Value =  qtySpin * priceSpin   (format: money)
            line_total = self.qtySpin.value() * _cbcs_dec(self.priceSpin.value(), 2)
            self.lineTotalLabel.setText(_cbcs_money(line_total))
```

`_cbcs_setup` also connects `qtySpin.valueChanged` and `priceSpin.valueChanged` to `cbcs_refresh`. The helpers:

```python
def _cbcs_dec(value, places):
    if value is None:
        return None
    return Decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def _cbcs_money(value):
    if value is None:
        return ""
    value = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return ("-$" if value < 0 else "$") + format(abs(value), ",.2f")
```

Because both spin boxes can never be blank, the multiplication is a plain `*`. If `priceEdit` were a `QLineEdit` of kind money, which can be blank, the line would read `_cbcs_mul(self.qtySpin.value(), _cbcs_parse_money(self.priceEdit.text()))`.

### 7.4 Scenario 3: required email with an inline error label

```python
        # Checks: a field is checked when the user leaves it; once an error is
        # showing it is re-checked as they type, so it clears straight away.
        self.emailEdit.editingFinished.connect(self._cbcs_touch_emailEdit)
        self.emailEdit.textChanged.connect(self._cbcs_recheck_emailEdit)
        self._cbcs_touched = set()

    def _cbcs_check_emailEdit(self):
        value = _cbcs_text(self.emailEdit)
        # Required
        if value is None:
            return "Email is required"
        # Email address
        if not _cbcs_is_email(value):
            return "Enter an email address like name@example.com"
        return ""

    def _cbcs_touch_emailEdit(self):
        self._cbcs_touched.add("emailEdit")
        _cbcs_show_error(self.emailEdit, self.emailEditError, self._cbcs_check_emailEdit())

    def _cbcs_recheck_emailEdit(self, *args):
        if "emailEdit" in self._cbcs_touched:
            _cbcs_show_error(self.emailEdit, self.emailEditError, self._cbcs_check_emailEdit())

    def cbcs_validate(self):
        """Check every field. Shows messages, focuses the first bad field, returns True if all pass."""
        first_bad = None
        for widget, label, check in [
            (self.emailEdit, self.emailEditError, self._cbcs_check_emailEdit),
        ]:
            self._cbcs_touched.add(widget.objectName())
            message = check()
            _cbcs_show_error(widget, label, message)
            if message and first_bad is None:
                first_bad = widget
        if first_bad is not None:
            first_bad.setFocus()
            return False
        return True
```

```python
_CBCS_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _cbcs_text(widget):
    text = widget.text().strip()
    return text if text else None


def _cbcs_is_email(text):
    return _CBCS_EMAIL.fullmatch(text) is not None


def _cbcs_show_error(widget, label, message):
    label.setText(message)
    label.setVisible(bool(message))
    widget.setToolTip(message)
    if widget.property("cbcsInvalid") != bool(message):
        widget.setProperty("cbcsInvalid", bool(message))
        widget.style().unpolish(widget)   # re-apply style sheet rules on [cbcsInvalid="true"]
        widget.style().polish(widget)
```

`setupUi` hides `emailEditError` initially, because its text is empty.

### 7.5 Scenario 4: Save checks the fields, then calls the user's method

```python
        self.saveButton.clicked.connect(self._cbcs_saveButton_clicked)

    def _cbcs_saveButton_clicked(self):
        # When saveButton is clicked:
        #   1. Check all fields (stop if any fail)
        if not self.cbcs_validate():
            return
        #   2. Call save_invoice() in invoice_window.py
        self._form.save_invoice()
```

The user's file, which the builder created once and added the stub to:

```python
from PySide6.QtWidgets import QDialog

from forms.ui_invoice import Ui_Invoice


class InvoiceWindow(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)

    def save_invoice(self):
        """Runs when saveButton is clicked."""
        pass
```

If the list had a third step that depends on the method's result, the generated code would read `if self._form.save_invoice() is False: return`.

### 7.6 Scenario 5: customer combo filled from a table

```python
    def cbcs_load_lookups(self):
        """Fill combo boxes from their lookup tables. Runs on open and on 'Reload lookups'."""
        cursor = self._cbcs_connection().cursor()
        # customerCombo: customers.id, showing name, also terms_days
        cursor.execute('SELECT "id", "name", "terms_days" FROM "customers" ORDER BY "name"')
        current = self.customerCombo.currentData()
        self.customerCombo.blockSignals(True)
        self.customerCombo.clear()
        self.customerCombo.addItem("(choose a customer)", None)
        for key, name, terms_days in cursor.fetchall():
            self.customerCombo.addItem(str(name), key)
            self.customerCombo.setItemData(self.customerCombo.count() - 1,
                                           {"terms_days": terms_days}, _CBCS_ALSO_ROLE)
        _cbcs_select(self.customerCombo, current)
        self.customerCombo.blockSignals(False)

    def _cbcs_connection(self):
        return open_connection("shop")        # from cbcs_connections.py (5.1)
```

A formula like `customerCombo.terms_days` compiles to `_cbcs_also(self.customerCombo, "terms_days")`, which reads the item data stored above.

### 7.7 Scenario 6: invoice bound to SQLite, with navigation and lines

The form has `cbcsData = {"connection": "shop", "table": "invoices", "key": "id", "order": [["invoice_date", "desc"], ["id", "desc"]], "hooks": {"beforeSave": "before_save"}}`, bound fields `invoiceNoEdit`, `customerCombo`, `invoiceDateEdit` (Default `today()`) and `notesEdit`, a `linesView` with `cbcsRows` (5.6), `totalLabel` with Value `sum(linesView.lineTotal)`, and the record toolbar.

```python
    # ---- Data: invoices in "shop" -------------------------------------------

    def cbcs_open(self, key=None):
        """Load the list of invoice keys, then show `key` (or the first invoice)."""
        cursor = self._cbcs_connection().cursor()
        cursor.execute('SELECT "id" FROM "invoices" ORDER BY "invoice_date" DESC, "id" DESC')
        self._cbcs_keys = [row[0] for row in cursor.fetchall()]
        if key in self._cbcs_keys:
            self._cbcs_show(self._cbcs_keys.index(key))
        elif self._cbcs_keys:
            self._cbcs_show(0)
        else:
            self._cbcs_start_new()

    def cbcs_read_fields(self):
        """The bound field values, as a dict of column name to value."""
        return {
            "invoice_no": _cbcs_text(self.invoiceNoEdit),
            "customer_id": self.customerCombo.currentData(),
            "invoice_date": self.invoiceDateEdit.date().toPython(),
            "notes": self.notesEdit.toPlainText().strip() or None,
        }

    def cbcs_write_fields(self, row):
        self.invoiceNoEdit.setText(row["invoice_no"] or "")
        _cbcs_select(self.customerCombo, row["customer_id"])
        self.invoiceDateEdit.setDate(_cbcs_qdate(row["invoice_date"]))
        self.notesEdit.setPlainText(row["notes"] or "")

    def _cbcs_show(self, index):
        key = self._cbcs_keys[index]
        cursor = self._cbcs_connection().cursor()
        cursor.execute('SELECT "invoice_no", "customer_id", "invoice_date", "notes" '
                       'FROM "invoices" WHERE "id" = ?', (key,))
        names = [column[0] for column in cursor.description]
        row = dict(zip(names, cursor.fetchone()))
        self.cbcs_write_fields(row)
        cursor.execute('SELECT "id", "description", "qty", "price" FROM "invoice_lines" '
                       'WHERE "invoice_id" = ? ORDER BY "line_no", "id"', (key,))
        self._cbcs_lines.load(cursor.fetchall())
        self._cbcs_index = index
        # Snapshot for "unsaved changes" and for the conflict check on save.
        self._cbcs_loaded = {"key": key, "row": row, "fields": self.cbcs_read_fields(),
                             "lines": self._cbcs_lines.snapshot()}
        self._cbcs_touched.clear()
        self.cbcs_refresh()
        # Hook: after_load() in invoice_window.py (only if named in the Data panel)

    def cbcs_is_dirty(self):
        """True if the fields or lines differ from what was loaded."""
        return (self.cbcs_read_fields() != self._cbcs_loaded["fields"]
                or self._cbcs_lines.snapshot() != self._cbcs_loaded["lines"])

    def cbcs_confirm_leave(self):
        """Ask about unsaved changes. Returns False if the user cancels."""
        if not self.cbcs_is_dirty():
            return True
        answer = QMessageBox.question(
            self._form, "Unsaved changes", "Save changes to this invoice?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Save:
            return self.cbcs_save()
        return answer == QMessageBox.StandardButton.Discard

    def cbcs_next(self):
        if self._cbcs_index < len(self._cbcs_keys) - 1 and self.cbcs_confirm_leave():
            self._cbcs_show(self._cbcs_index + 1)

    # cbcs_first, cbcs_previous and cbcs_last have the same shape.

    def cbcs_save(self):
        """Check, then insert or update the invoice and its lines in one transaction."""
        if not self.cbcs_validate():
            return False
        # Hook: before_save() in invoice_window.py; returning False cancels.
        if self._form.before_save() is False:
            return False
        fields = self.cbcs_read_fields()
        key = self._cbcs_loaded["key"]
        connection = self._cbcs_connection()
        cursor = connection.cursor()
        try:
            if key is None:
                cursor.execute(
                    'INSERT INTO "invoices" ("invoice_no", "customer_id", "invoice_date", "notes") '
                    'VALUES (?, ?, ?, ?)', _cbcs_params(fields.values()))
                key = cursor.lastrowid
            else:
                # Only update if nobody changed the row since it was loaded.
                old = self._cbcs_loaded["row"]
                cursor.execute(
                    'UPDATE "invoices" SET "invoice_no" = ?, "customer_id" = ?, '
                    '"invoice_date" = ?, "notes" = ? WHERE "id" = ? '
                    'AND "invoice_no" IS ? AND "customer_id" IS ? '
                    'AND "invoice_date" IS ? AND "notes" IS ?',
                    _cbcs_params(list(fields.values()) + [key] + list(old.values())))
                if cursor.rowcount == 0:
                    raise _CbcsConflict()
            self._cbcs_lines.save(cursor, "invoice_id", key)
            connection.commit()
        except _CbcsConflict:
            connection.rollback()
            self._cbcs_conflict_message("invoice")
            return False
        except Exception as error:
            connection.rollback()
            if _cbcs_show_db_error(self, error):     # known constraint -> field message
                return False
            raise
        self.cbcs_open(key)                          # re-read: defaults, triggers, order
        return True
```

The conflict check compares with the **raw values as loaded** (`row`), not with values read back through the widgets. A NULL `notes` read into an empty text box must not look like a change made by someone else.

Line items (an excerpt of the generated helper class, which only appears in forms that have a lines grid):

```python
class _CbcsLines(object):
    """In-memory rows for linesView (invoice_lines), saved together with the invoice."""

    def save(self, cursor, link_column, link_key):
        for line_id in self.deleted:                         # rows the user deleted
            cursor.execute('DELETE FROM "invoice_lines" WHERE "id" = ?', (line_id,))
        for r in range(self.model.rowCount()):
            row = self.row(r)
            line_id = self.key(r)
            values = _cbcs_params([row["description"], row["qty"], row["price"], r + 1])
            if line_id is None:                              # new row
                cursor.execute(
                    'INSERT INTO "invoice_lines" ("description", "qty", "price", "line_no", '
                    '"invoice_id") VALUES (?, ?, ?, ?, ?)', values + [link_key])
            elif self.changed(r):                            # edited row
                cursor.execute(
                    'UPDATE "invoice_lines" SET "description" = ?, "qty" = ?, "price" = ?, '
                    '"line_no" = ? WHERE "id" = ?', values + [line_id])
        self.deleted = []
```

```python
            # linesView column lineTotal: Value =  qty * price
            self._cbcs_lines.compute("lineTotal", lambda row: _cbcs_mul(row["qty"], row["price"]))
            # totalLabel: Value =  sum(linesView.lineTotal)   (format: money)
            self.totalLabel.setText(_cbcs_money(_cbcs_sum(self._cbcs_lines.column("lineTotal"))))
```

The close guard. The window file is never touched:

```python
class _CbcsCloseGuard(QObject):
    """Asks about unsaved changes when the window is closed (or Escape on a dialog)."""

    def __init__(self, ui, form):
        super().__init__(form)
        self.ui = ui
        form.installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Close and not self.ui.cbcs_confirm_leave():
            event.ignore()
            return True
        if (event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape
                and isinstance(obj, QDialog) and not self.ui.cbcs_confirm_leave()):
            return True
        return False
```

**The same form on PostgreSQL** differs only in these lines:

```python
                cursor.execute(
                    'INSERT INTO "invoices" ("invoice_no", "customer_id", "invoice_date", "notes") '
                    'VALUES (%s, %s, %s, %s) RETURNING "id"', list(fields.values()))
                key = cursor.fetchone()[0]
    ...
                    'WHERE "id" = %s AND "invoice_no" IS NOT DISTINCT FROM %s AND ...'
```

`_cbcs_params` (Decimal and date to text) is used only for SQLite. psycopg and pg8000 bind `Decimal` and `date` natively.

### 7.8 Hooks and public API the user can rely on

| Name on `self.ui` | Purpose |
| --- | --- |
| `cbcs_refresh()` | run all rules again |
| `cbcs_validate()` | run all checks. Returns `bool` |
| `cbcs_open(key=None)` | load keys and show a record |
| `cbcs_read_fields()`, `cbcs_write_fields(row)` | dict in, dict out |
| `cbcs_read_lines()` | list of dicts for the lines grid |
| `cbcs_is_dirty()`, `cbcs_confirm_leave()` | unsaved-changes support |
| `cbcs_new()`, `cbcs_save()`, `cbcs_delete()`, `cbcs_revert()`, `cbcs_first()`, `cbcs_previous()`, `cbcs_next()`, `cbcs_last()`, `cbcs_find()`, `cbcs_load_lookups()` | the verbs |
| `cbcs_current_key()` | the key of the record on screen, or `None` |

Hooks are methods on *your window*, named in the Data panel (5.9) or as *Call* steps. They are always called directly, never looked up with `getattr`.

### 7.9 How generated code avoids fighting user code

| Risk | Protection |
| --- | --- |
| Name collisions | every generated attribute starts with `cbcs_` or `_cbcs_`. Widget names starting with `cbcs` are refused |
| User code sets a property a rule owns | warning FB207. The rule wins on the next refresh, as documented |
| The user wants their own handler order | native and generated connections are both made inside `setupUi`. Anything the user connects afterwards runs after them |
| The user wants to stop generated behaviour | untick *Enabled* on the event, change the steps, or *Eject* |
| Editing the user's file | only an empty stub, only on request, removable by undo while still empty |

---

## 8. Scope limits and hand-off points

What we will **not** build, and where a person goes instead:

| Not built | Why | Hand-off point |
| --- | --- | --- |
| A general programming language (statements, variables, loops, user functions) | It becomes Excel `LAMBDA` and Power Fx sprawl. Python is already right there | *Call a method* step. `window.method()` in a formula |
| Node graphs, Blockly or visual scripting | They do not round-trip, do not merge, and duplicate Level 2 (Grok, research A and D) | `name_window.py` |
| Templating inside strings or SQL (`{{ }}`) | Retool and Appsmith sprawl | formulas are their own fields. SQL takes parameters only |
| A query builder (joins, groups, unions) | a second product. Joins for display are lookups | a list screen's fixed `query`, or a method using the connection |
| Upserts, `ON CONFLICT`, `JSONB`, generated columns | PostgreSQL 9.3 (pitfalls A-1) | your own SQL in a method |
| Database access inside formulas | the Power Apps delegation trap | lookup `also` columns, `window.method()` |
| Reports and printing | ChoreBoy reports go through Jasper and PDFium (pitfalls) | *Call a method* |
| Multiple lines grids, or nested grids (grids within grids) | version 1 scope | Phase 5 or later. Until then, a method |
| Timers, background work, threads | Qt widget changes from threads crash (pitfalls D-1) | a method |
| Locking records across users | PostgreSQL row locks held while a form is open are a support burden | the conflict check (5.5) |
| Qt SQL models (`QSqlTableModel`, `QDataWidgetMapper`) | zero uses in the surveyed apps (research D). Qt SQL drivers for PostgreSQL 9.3 are not shipped | generated DB-API code. A developer may still build a mapper in the window class |
| Running rules when the `.ui` is loaded with `QUiLoader` | no runtime library, by decision | the generated module |
| AI features | product decision | none |

The **exact hand-off points** to Python are four, and only four:

1. A *Call a method* step, or a Level 2 connection.
2. `window.method()` inside a formula.
3. Named data hooks (`beforeSave` and the others), including the `connection` hook.
4. The public `self.ui.cbcs_*` API, and *Eject to code*.

---

## 9. Delivery plan

### 9.1 Phases, ordered for maximum value early

Each phase ships something a shop owner can use on a real form. Later phases never change JSON written by earlier ones.

| Phase | Ships | Unlocks | Main risk retired |
| --- | --- | --- | --- |
| **1. Events and your code** | Behavior tab (Events section only). Event picker with common events. Intent-based connection picker. Double-click to create a stub, with undo. Naming rules. `ast` signature checks. F12. Problems FB2xx. Logic outline (events only). Native storage | Wiring buttons to methods, the most common need, with Delphi-style speed | The window-class contract and cross-file undo |
| **2. Rules and checks** | The formula compiler (full grammar, types, Excel fixes). State rules (Enabled, Visible, Read-only, Value, Default). Kinds. Formats. Checks (required, range, length, presets) with error labels. Live "now:" values. Try mode without data. Step lists with Check all fields, Call, Message, Ask, Stop. Rename and paste propagation. Walkthroughs 1 to 3 work | No-code behaviour for hobbyists. Scenarios 1 to 4 | Whether non-programmers can use the language. This phase follows the spike |
| **3. The rest of Level 3** | The full step vocabulary (set, clear, focus, page, open and close form). Cross-field and pattern checks. Canvas overlay. Read as text. Repair references. Code-connection discovery | Multi-window apps. Explainable forms | Overlay performance on large forms |
| **4. One SQLite table** | Connections settings. `cbcs_connections.py`. Data panel with schema cache. Bindings. Lookups with `also`. Keys-only navigation. Record toolbar. New, Save, Delete, Revert, Find. Snapshot dirty tracking. Close guard. Conflict check. Hooks. Try mode on a scratch database. Scenario 5, and scenario 6 without lines | The order-entry, customer-list and inventory forms | Generated data code that is readable *and* correct |
| **5. Lines, lists, PostgreSQL** | Master-detail grid (delegates, calculated columns, aggregates, diff save). List and search screens. The PostgreSQL path (helper-process schema reads, driver probe, `%s`, `RETURNING`, SQLSTATE mapping). *Eject to code*. Scenario 6 in full | Invoicing. Shops that run on PostgreSQL | The driver probe on a real ChoreBoy |

PostgreSQL waits until the SQLite save path is boring. The SQL shape is the same, and only the dialect table (5.8) changes.

### 9.2 The logic spike

**Goal:** before building the real inspector, find out whether the *editing experience* in Phase 2 works for both audiences, and whether the compiler and generator match this design. The draft's spike tested only the compiler. The bigger unknown is whether shop owners can do this at all.

**Scope (throwaway code, under `scratch/`, not in the app):**

1. A standalone PySide6 window under FreeCAD AppRun: a fixed 10-widget invoice form on a mock canvas (real widgets), a Behavior tab with the State, Checks and Events sections, builder and formula modes, completion, live "now:", Excel fixes, and a Try button that runs the generated module in a second AppRun process.
2. A compiler covering the full grammar of 4.2, type checking for Text, Number, Money, YesNo and Date, and code generation for *Enabled when*, *Value*, *Default*, Required plus Email, and a two-step Save list (Check all fields, Call).
3. Stub insertion into a real `invoice_window.py`, with undo while still empty.
4. Save to `.ui` with the canonical writer.

**Tests:**

- *Users*: 5 people, 3 non-programmers (shop-owner profile) and 2 Python developers. A two-minute introduction, then walkthroughs 1, 2 and 3 with no help. Record the time taken, errors made and where people looked first.
- *Developers*: show the generated `ui_invoice.py` and ask them to predict what happens when the email is blank and Save is clicked, and where they would add their own code.
- *Technical*: golden-file tests of generated code for scenarios 1 to 4. Byte-identical regeneration. A 150-widget, 60-rule form saves and generates in under 100 ms on the Mac. A form with all the spike's rules is opened in real Qt Designer 6.8.3 (from FreeCAD's bundle), a widget is moved, the form is saved, and the builder reopens it with every rule intact.

**Success criteria (all must hold to proceed to Phase 2 as designed):**

| Criterion | Target |
| --- | --- |
| Walkthrough 1 completed without help | 5 of 5, median under 60 seconds |
| Walkthrough 2 completed without help | at least 4 of 5. Non-programmers may use builder mode or the completion list |
| Walkthrough 3 completed without help | 2 of 2 developers, and at least 2 of 3 non-programmers up to the point of "Call" |
| Developers correctly predict the behaviour from generated code | 2 of 2 |
| No participant edits `ui_invoice.py` or is confused about which file to edit | 5 of 5 |
| Determinism, performance and Designer round-trip tests | all pass |

**If it fails:** if walkthrough 2 fails for non-programmers, invest in builder mode for values ("Qty [×] Price") before shipping formulas, and keep the language. If the Designer round trip loses properties, revisit Decision 5 (fall back to a single JSON property per widget) before Phase 2 starts. If developers mispredict the generated code, simplify the generator's output before adding features.

---

## 10. Open questions for the product owner

1. **Is a user-owned `cbcs_connections.py` acceptable under "no runtime library"?** It is created once, is readable, the user can edit it, and generated forms import `open_connection` from it. The alternative is to repeat about 80 lines of driver-probe, encoding and password code inside every `ui_*.py`. That is worse to maintain and impossible to customise per project. My recommendation is the single user-owned file.
2. **PostgreSQL in Try mode: read-only (my recommendation), or allow writes inside a transaction that is rolled back?** Rolled-back writes are more realistic, but they hold row locks against real clerks while someone is designing on a live shop database.
3. **Default formats: US English (`$`, `1,234.50`, `MM/DD/YYYY`) everywhere, with a project setting to change it?** Or do some ChoreBoy customers need other currencies or date orders on day one?
4. **How do we weight the two audiences in Phase 2?** If most target users never open `name_window.py`, builder mode for *values* (not just conditions) should ship in Phase 2 rather than after the spike shows a need. If most users are learning Python, formulas first is right. Your sense of the customer mix decides this.

---

## Appendix: evidence from this session

| Claim | How it was checked |
| --- | --- |
| `uic` passes `cbcs*` dynamic string properties through as `setProperty`, including multi-line JSON | Ran `/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic -g python` on a sample form |
| `uic` emits `self.saveButton.clicked.connect(Invoice.save_invoice)` for a form-slot connection, then `connectSlotsByName` | Same run |
| `QUiLoader` keeps multi-line dynamic properties, and warns "No such slot QDialog::save_invoice()" for form slots | Loaded the same file with FreeCAD 1.1.3's PySide6 6.8.3, offscreen |
| `QFormBuilder.save()` drops dynamic properties on a round trip, so it is not a stand-in for Designer | Load-and-save experiment |
| PySide6 calls plain methods with 0 or 1 of a signal's values. A method needing more is accepted at connect time and raises `TypeError` on each emit | Connected `toggled` and `clicked` to methods with 0, 1, optional and 2 parameters |
| Ignoring `QEvent.Close` in an event filter blocks `close()` | `close()` returned `False` and the window stayed visible |
| Python's `sqlite3` cannot bind `Decimal`. Binding `str` lets column affinity store a number | `ProgrammingError: type 'decimal.Decimal' is not supported`, then a NUMERIC column read back 1.5 as `real` |
| PostgreSQL 9.3 supports `INSERT ... RETURNING` | 9.3 manual, INSERT synopsis (postgresql.org/docs/9.3/sql-insert.html) |
| The scenario code works end to end | A stand-in `ui_invoice.py` and a test script under the session scratchpad passed against a temporary SQLite database |

## Owner decisions on the open questions (2026-10-20)

1. **Connections: managed by CBCS, not a hand-written file.** Named connections ("Shop database") are a project setting with their own screen (add, edit, **Test**). SQLite paths are relative to the project; PostgreSQL keeps host/database/user. The same named connection is used everywhere: form-from-table, Try mode, the Data panel and the running app. CBCS **generates** `cbcs_connections.py` from those settings, like `ui_*.py`; the user never edits it. Passwords never go in the project. Each connection picks one of: ask when the app starts, remember on this machine only (in the user's home config, outside the project, so it's never packaged or shared), or none (SQLite). An optional `on_connect(conn)` hook in user code is the escape hatch for custom setup. This replaces the "user-owned `cbcs_connections.py`" recommendation in section 5.
2. **Try mode on PostgreSQL: write, then roll back** (owner's choice over read-only). Mitigations to design in: short transactions, a visible "Try mode: changes will be rolled back" banner, a statement timeout, and a warning that row locks can briefly block other users.
3. **Locale: US English by default** ($1,234.50, MM/DD/YYYY), with a per-project setting.
4. **Users are a real mix**, so the point-and-click builder for conditions and calculated values ships in **phase 2**, alongside typed formulas.
