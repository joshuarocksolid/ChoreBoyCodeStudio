# Logic in the form builder

This is a design proposal for behavior in the ChoreBoy Code Studio form builder. It is research only. No application repository was modified.

The person who uses the builder is a shop owner writing an order, invoice, inventory, or customer window. The next person is a Python developer who will open `forms/name_window.py` and expect ordinary PySide6. The file they share is `forms/name.ui`. Layout and logic both live there. `forms/ui_name.py` is generated on every save. The window class is created once and is not rewritten, except for an empty method stub the builder may insert.

## Overview

Compile four kinds of behavior into plain Python. The generated module contains ordinary functions, and the app does not import a rules engine.

Widget-to-widget links and "call my method" stay in the standard `<connections>` and `<slots>` elements. Enable rules, computed values, validation, and record binding stay in dynamic properties whose names start with `cbcs`. The generator reads those properties and writes functions in `ui_name.py`. Qt Designer keeps the properties. `QUiLoader` keeps them and does nothing with them. A form opened in stock Designer still loads. A form run through our generator actually behaves.

The shop owner mostly sees a sentence, such as "When Discount is checked, enable Discount rate." The developer sees the function that sentence became, and can ignore it by handling the click in the window class.

An earlier architecture note recommended a JSON layout file and said the binder should not emit SQL. That note is `docs/form_builder/research/D_first_principles_architecture.md`. This proposal follows the later decision instead. The `.ui` file is the source of truth. Level 4 does emit SQL. The window class can still replace that SQL. The operator could return to "SQL only in the window" by stopping after Phase 3 below.

## Key concepts

Behavior has four levels. They share one compiler. They do not share one visual language.

| Level | What the person means | Stored in the `.ui` file | What runs |
| --- | --- | --- | --- |
| 1 | When this widget changes, set that widget. | `<connection>` | `sender.signal.connect(receiver.slot)` |
| 2 | When this happens, call my method. | `<connection>` plus `<slot>` | The method on the window class |
| 3 | Keep this property true, or check this value. | `cbcsBehavior` on the widget or the form | Generated functions, no `eval` |
| 4 | This form edits a table. | `cbcsData` on the root widget | Generated `sqlite3` or PostgreSQL code |

A value rule recalculates when its inputs change. An action runs when an event happens. Those are different records. Power Apps documents the same split. Microsoft Learn says "Most formulas calculate a value." The same page says "Because these functions change the state of the app, they can't be automatically recalculated." Source: [Understand behavior formulas for canvas apps](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/working-with-formulas-in-depth).

A connection is one row. Sender, signal, receiver, slot. A rule is one JSON object on a widget. A data source is one JSON object on the form. None of these is a graph.

## Where things live

| File | Who writes it | Role |
| --- | --- | --- |
| `forms/name.ui` | The builder | Layout, connections, slots, `cbcsBehavior`, `cbcsData` |
| `forms/ui_name.py` | The generator, every save | `Ui_Name.setupUi` and `retranslateUi`, plus the expanded rules |
| `forms/name_window.py` | The user | `self.ui.setupUi(self)` and any method a Level 2 action names |
| Project settings | The user, outside the form | PostgreSQL connection name, host, and password |

`cbcsBehavior` and `cbcsData` are strings. Each is a `<property>` with `stdset="0"` and `<string notr="true">`. `notr="true"` keeps stock `uic` from wrapping the JSON in `translate()`. Our generator does not emit `setProperty` for these names. It emits the Python the JSON describes. Stock `uic` would emit `setProperty`, and the rules would sit inert. That matches the decision already verified for `QUiLoader`.

The generator writes `connectslotsbyname="false"` on `<ui>` when it owns connections. Qt writes that attribute only when the flag is false. A missing attribute means true. Research R3 records that from the Qt 6.8.3 sources. Automatic `on_objectName_signal` names are a separate mechanism. A near miss connects nothing and prints a warning. Research P quotes that warning. Level 2 uses an explicit `<connection>` and a method name that does not start with `on_`. Qt's own UI-file guide says "we recommend against using this in new code." The reason on that page is that renaming a widget forces the matching slot name to change. Source: [Using a Designer UI file](https://doc.qt.io/qt-6/designer-using-a-ui-file.html).

## How other tools let a non-programmer add behavior

### Microsoft Access

Access stores two different things on a form. A bound form has a record source. Controls have a control source, so the field and the box are the same idea. Navigation is a built-in bar. A subform shows child rows. Microsoft documents that a subform loads before the main form, and that a subform does not receive Activate. Source: [Order of events for database objects](https://support.microsoft.com/en-us/access/order-of-events-for-database-objects).

The other thing is an event. The Event tab can hold `[Event Procedure]` or `[Embedded Macro]`. Microsoft says "Embedded macros become part of the object or control in which they are embedded." Source: [Create a user interface (UI) macro](https://support.microsoft.com/en-us/access/create-a-user-interface-ui-macro). A macro is an ordered list of actions. An `If` block guards an action with an expression such as `[Counter]=10`. The Expression Builder fills `Forms![Orders]![OrderID]` and validation rules such as `<> 0`. Source: [Examples of expressions](https://support.microsoft.com/en-us/access/examples-of-expressions).

What people hit. The event order is long enough that Microsoft publishes a chart. A `Requery` in the wrong event moves the record. A `DoEvents` inside `BeforeUpdate` raises error 2115 when focus moves to a subform. That reproduction is from mwolfe02, accepted answer, [Stack Overflow 25367080](https://stackoverflow.com/questions/25367080/error-2115-macro-function-set-to-beforeupdate-validationrule-is-preventing-pgm). Copy the bound form, the navigation bar, the subform, and the short action list. Refuse the event chart. A shop owner cannot sequence Open, Load, Current, Enter, BeforeUpdate, and AfterInsert.

### FileMaker

A script trigger points a layout object, a layout, or a file at a script. Claris says "A script trigger in FileMaker Pro is a mechanism that causes a user-defined script to execute when a supported event occurs." Source: [Understanding and using script triggers](https://support.claris.com/s/article/Understanding-and-using-Script-Triggers-1503692961228?language=en_US). Some triggers run before the event and can cancel it by returning false. Some run after.

The trap is that many edits do not fire the trigger. Claris says "Bulk operations that may change many records at once will not activate a script trigger." `Set Field` does not activate `OnObjectModify`. Source: [Actions that don't activate script triggers](https://help.claris.com/en/pro-help/content/actions-dont-activate-triggers.html).

A portal shows related records. A filter is a calculation. Claris says "a portal filter is evaluated only when the record is loaded." Changing a global used by that filter does nothing until `Refresh Portal`. Source: [Working with related data in portals](https://help.claris.com/en/pro-help/content/working-with-portals.html). Copy "return false to cancel the event" for confirm and validation. Refuse a trigger set so large that `Set Field` and a typed edit behave differently. Our generated `setValue` must go through the same refresh as a keystroke.

### Visual Basic 6 and Windows Forms

The gesture people remember is the double-click. PaulOTron2000 wrote "I just double click on a button in the design view, which brings me straight to the code." Source: [Stack Overflow 25003852](https://stackoverflow.com/questions/25003852/very-slow-design-view-on-a-complex-form-with-a-lot-of-controls), 2014-07-28. The same gesture annoys other people. slightly_drifting wrote "Double clicking UI controls and it automatically goes to the code behind is annoying." Source: archived Reddit thread `r/csharp` `1d4jr87`, 2024-05-31, quoted in research P. w0ut, in that same thread, noted that clearing the handler removes a stub that was only just created.

WinForms binding puts a `BindingSource` between the controls and the list. Microsoft says "The BindingSource component acts as both a conduit and a data source for other controls to bind to." Source: [BindingSource Component Overview](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/controls/bindingsource-component-overview). A `BindingNavigator` is a strip whose buttons call `MoveFirst`, `MovePrevious`, `MoveNext`, `MoveLast`, add, and remove. Microsoft says "you can supply your own ToolStrip buttons." Source: [BindingNavigator Control Overview](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/controls/bindingnavigator-control-overview-windows-forms).

`ErrorProvider` is the validation picture to copy. Microsoft says "If an error description string is specified for the control, an icon appears next to the control." Source: [ErrorProvider](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.errorprovider?view=windowsdesktop-9.0). The same page says the icon is not enough for accessibility, and the app still needs text. Our error is a label, not only an icon.

The generated `*.Designer.cs` file is the warning. dahlbyk wrote "You should never modify .designer.cs. Period." Source: [Stack Overflow 16161994](https://stackoverflow.com/questions/16161994/manual-editing-of-designer-cs-file), 2013-04-23. `ui_name.py` gets the same banner. The window file is the one a person may edit.

### Delphi and Lazarus

Delphi is the tool this audience still means by "easy." FeistySkink wrote "I feel like Delphi, along with maybe VB6 and WinForms, have been the pinnacle of easy UI development." Source: [Hacker News 43462299](https://news.ycombinator.com/item?id=43462299), 2025-03-24. The same thread, quoted in research P, also says the default form was pixels and a fixed font. Copy the double-click into a method in another file. Do not copy pixel layout. Layout is a separate report.

Data-aware controls are a `TDataSource` plus a field name. Embarcadero says "TDataSource provides an interface between a dataset component and data-aware controls on a form." The same page says a data source also links master and detail. Source: [TDataSource](https://docwiki.embarcadero.com/Libraries/Athens/en/Data.DB.TDataSource). `TDBEdit` shows the current value of one field at design time once the dataset is active. Source: [Displaying and Editing Fields in an Edit Box](https://docwiki.embarcadero.com/RADStudio/Sydney/en/Displaying_and_Editing_Fields_in_an_Edit_Box). The field editor is a list of columns, not a formula language.

That live preview depends on a database connection while you edit. ChoreBoy is offline, and the editor must not import the user's project. Research D records both constraints. We preview rules against the widgets on the canvas. We do not open the shop database unless the person presses an explicit "Run this SQL" action.

### Power Apps and Power Fx

Power Fx puts a formula on a property. Microsoft's overview says the formula "recalculates the value automatically, similar to how a spreadsheet does." Source: [Microsoft Power Fx overview](https://learn.microsoft.com/en-us/power-platform/power-fx/overview). `Visible`, `DisplayMode`, and `Default` are value formulas. `OnSelect` is a behavior formula. `Navigate`, `Patch`, and `SubmitForm` are legal only in behavior formulas. Several actions are separated by semicolons and run in order. Microsoft says "If an error occurs, subsequent functions might not start." Source: [Understand behavior formulas](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/working-with-formulas-in-depth).

`SubmitForm` switches on the form mode. Edit updates the current item. New creates a record. View ignores submit. Source: [EditForm, NewForm, SubmitForm](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-form). A gallery is a template row, not a copied row.

The trap is delegation. Microsoft says "Power Apps gets the first 500 records from the data source and then runs the actions in the query." A nondelegable `Filter` on a large table looks successful and is wrong. The editor shows a warning. Source: [Understand delegation in a canvas app](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/delegation-overview). A later drag can also replace a responsive formula with a constant. Research A cites that from Microsoft's responsive-layout page.

Copy the split between value and action, the formula bar, the warning next to the formula, and `SubmitForm` as one verb. Refuse a second syntax. Power Fx is MIT, and the studio is not. The engine is not a Python library we can ship on the appliance. Refuse silent local evaluation of a database query. Our SQL is the statement we generated, with bound parameters, or it is Python the developer wrote.

### Anvil

Anvil is the closest Python split. A binding is one Python expression on one property. Anvil says "A Data Binding associates a property of a component with a single Python expression." Writeback runs on `pressed_enter` or `lost_focus`, not when bindings refresh. A `KeyError` is ignored so an empty dict still renders. Source: [Data Bindings](https://anvil.works/docs/client/component-properties/data-bindings). Meredydd, 2023-05-02, confirmed the silence is intentional. "KeyErrors in Data Binding expressions are ignored." Source: [Anvil forum 16800](https://anvil.works/forum/t/keyerrors-in-data-bindings-are-silenced/16800).

The event button inserts a real method and opens it. That is the Level 2 gesture, with a body the designer does not own.

Copy one expression per property, and copy "do not rewrite the method body." Refuse silent `KeyError`. A missing widget name is a design-time error. A missing record key at run time is a blank only when the author wrote `coalesce` or the record is new. Any other exception is an inline error, not a success.

### Appsmith, Retool, and Budibase

All three attach an ordered action list to an event, then offer a JavaScript escape hatch.

Retool component handlers run in parallel. Retool says "You can add multiple event handlers to a single component, but note that they run in parallel." The same page says to chain work on the query's Success or Failure handler, which runs in order. Source: [Configure event handlers](https://docs.retool.com/apps/guides/interaction-navigation/event-handlers). `{{ }}` bindings are the value language. The binding drawer can show the current value. Research A quotes Budibase's hover preview in the same family.

Appsmith chains `onSuccess`, and the UI stops at two levels. Appsmith says "You can only execute two levels of onSuccess callbacks from the UI." Deeper chains require enabling JavaScript. Source: [Trigger UI Actions](https://docs.appsmith.com/core-concepts/writing-code/ui-actions).

Budibase runs the list in order and stops on failure. Budibase says "Actions run synchronously; if one fails, the actions after won't run." A later action can read `{{ Action 1.Query Result }}`. Source: [Chaining actions](https://docs.budibase.com/docs/chaining-actions).

Copy the ordered list, the stop-on-failure rule, and Success or Failure only for the SQL actions we actually generate. Refuse parallel handlers, a two-level callback limit, and `{{ }}` as a second syntax inside SQL. One failure path is enough. The generated `cbcs_save` returns false, and the action list stops.

### Bubble, Glide, and Airtable Interfaces

Bubble is an event plus an ordered action list. A condition on the event skips the whole list. A condition on one action skips that step. Bubble says "When a condition is set on an event, the entire workflow only runs if that condition evaluates as true." Source: [Conditional workflow properties](https://manual.bubble.io/core-resources/bubble-workflows/conditional-workflow-properties). The product does not export an app. Research A records that, and records a review that calls the workflow strip a poor way to understand a screen. Our Behavior tab lists every rule on this form in one search, so the order is visible without opening a popup per step. Bubble also says "Frontend workflow actions run in order but the next action does not wait on the previous action to be complete before triggering." Source: [Workflow actions](https://manual.bubble.io/help-guides/logic/workflows/actions). Our list waits. The next action starts only after the previous one returns.

Glide attaches actions to a button, a form submit, or a collection click. Glide says "You can even create workflows that combine several action steps together into a sequence." Data steps include Add Row and Set Column Values. Navigation steps include Go to Tab. Source: [Introduction to Actions](https://www.glideapps.com/docs/automation/actions.md). That verb list is the right size for our action menu.

Airtable Interface buttons are also a fixed menu. On a record layout the menu includes Update record, Delete record, and Run automation. Source: [Using buttons in interfaces](https://support.airtable.com/articles/2099494420-using-buttons-in-interfaces). Copy the short menu. Refuse a general automation host. "Run your method" and "Run the save for this form" are the two escapes.

### Excel

Microsoft Research says "Spreadsheets are the world's most widely used programming language, by several orders of magnitude." Source: [Influencing mainstream software](https://www.microsoft.com/en-us/research/blog/influencing-mainstream-software-applying-programming-language-research-ideas-to-transform-spreadsheets/). The formula sits on the cell. Dependents recalculate. The formula bar shows the text. A beginner learns `=A2*B2` because the result is visible and the inputs have addresses.

What breaks is a formula that has become a program. Nested `IF` is hard to read, and the fix in modern Excel is a named `LAMBDA`, which is a real language. We stop before that. A value rule may call a whitelist of functions. It may not define one. If the shop needs a function, the developer writes it in the window module and the rule calls it by the Level 2 path, or the rule's expression calls a name we added to the whitelist on purpose.

### Blockly, Scratch, Blueprints, and Node-RED

Blockly turns blocks into a code string. The Blockly docs say "Instead you generate code strings, and then execute those." Source: [Generate code](https://docs.blockly.com/guides/get-started/code-generation/). The reverse direction is the problem. A Node-RED Blockly node shows the JavaScript and says "This code is readonly, which means you cannot change it!" The reason given on that page is that blocks cannot be rebuilt from the JavaScript. Source: [node-red-contrib-blockly](https://flows.nodered.org/node/node-red-contrib-blockly).

Scratch hat blocks start a script when an event fires. This session did not re-fetch a Scratch page. Research A already records hat blocks and broadcasts as the wiring model, and records the current Scratch editor as AGPL-3.0-only. Do not vendor it.

Unreal Blueprints are a node graph with exec pins and data pins. This session did not re-fetch the Epic page. Research A records that the graph does not round-trip to text, pointing at [Hacker News 37509533](https://news.ycombinator.com/item?id=37509533). Research D already rejects a node graph for this product. The rejection still holds. A graph is a second program, it does not merge, and the shop's real logic is a total and a SQL save.

Node-RED's own wires are a good editor for messages between services. They are not a form. Dashboard layout and flow layout are different pictures. Copy nothing from the graph. The property sheet on one selected object is the inspector we already need.

### Qt Designer and QDataWidgetMapper

Designer already has Level 1. F4 drags an arrow. The dialog lists signals and slots. Qt says "When a form is saved, all connections are preserved so that they will be ready for use when your project is built." Inherited `QWidget` members stay hidden until "Show all signals and slots" is checked. Otherwise "the signals and slots inherited from QWidget will be hidden." Source: [Signals and Slots Editing Mode](https://doc.qt.io/qt-6/designer-connection-mode.html).

The mode is easy to miss, and a new row is easy to scroll past. Serge K wrote "You will not see it, it is somewhere on top or bottom, you must yet scroll to it." Source: [qt-interest, January 2017](https://lists.qt-project.org/pipermail/interest/2017-January/025592.html). Research P quotes the longer message. Our Behavior tab is the default place to add a connection. F4 and the arrows remain for people who want the canvas.

`QDataWidgetMapper` maps one model section to one widget property. Navigation is `toFirst`, `toPrevious`, `toNext`, `toLast`. `AutoSubmit` writes when a widget loses focus. Qt says "ManualSubmit will not update the model unless submit() is called." Qt also says "Only one-to-one mappings between sections and widgets are allowed." Source: [QDataWidgetMapper](https://doc.qt.io/qt-6/qdatawidgetmapper.html).

Research D counted `QDataWidgetMapper` uses in four ChoreBoy application trees on 2026-10-20. The count was zero. Those apps copy a dict into widgets and read it back. A mapper also wants `QSqlTableModel` or another `QAbstractItemModel`. Shipping Qt SQL drivers for PostgreSQL 9.3 is a second product. We generate the load and store functions a mapper would have hidden. A developer who wants a mapper can still construct one in the window class. The generator does not.

## Principles

These are the rules the rest of the design is applying.

1. A value is a formula, or it is a constant. It is not both fighting over one property. Power Apps loses when a drag replaces a formula with a number. The builder stores `enabledWhen` separately from the widget's `enabled` property. The constant remains the design-time default. The formula wins at run time.

2. An action is a sentence with an order. "Validate, then call `save_invoice`." Retool's parallel handlers and Bubble's popup-per-step both hide the order. The list on the event is the order.

3. The result of a value rule is visible while you edit it. Excel and the Anvil properties panel do this. The Behavior tab shows the current result against the canvas widgets. A SQL action shows the statement and the parameters. It does not run them.

4. Errors sit on the widget. WinForms puts an icon next to the control and still needs text. We show a label under the field. The Problems list gets the same text at design time.

5. The generated file is readable, and it is not the file you edit. WinForms, `pyuic`, and Anvil agree. musicamante wrote "you must never edit those files." Source: [Stack Overflow 66544701](https://stackoverflow.com/questions/66544701/qmainwindow-object-has-no-attribute-addwidget), 2021-03-09, quoted in research P. The banner on `ui_name.py` repeats that. The interesting logic is either a short function the generator owns, or a method the user owns.

6. There is a named escape hatch, and only one. Level 2 is that hatch. Blocks, graphs, and a second formula language are how a tool grows a program nobody can diff.

7. Undo applies to a rule the same way it applies to a move. The rule is data. Deleting a widget lists the connections and rules that mention it before the delete proceeds. Research A already asks for that list.

8. A database write is explicit. Delegation bugs and FileMaker's "this edit did not fire the trigger" are the same family. The generator writes one function per verb (`cbcs_save`, `cbcs_delete`, `cbcs_reload`). Buttons call those verbs. Value rules never write the database.

## Choices considered

| Approach | Shop owner | Python developer | Decision |
| --- | --- | --- | --- |
| Sentence list compiled to a Python subset | Reads "when X, do Y" and can open the expression | Reads `ui_name.py` and sees the same expression | Use this |
| Power Fx or Excel syntax, compiled to Python | Familiar if they know spreadsheets | The file does not match the formula they typed | Refuse. One syntax. The sentence UI hides it for common cases |
| Python `eval` of the property string | Same syntax | A hostile or broken `.ui` can run anything | Refuse. The compiler walks an allowlist AST and emits calls |
| `QDataWidgetMapper` and Qt SQL models | Navigation looks native | Zero uses in the surveyed apps, and PostgreSQL 9.3 through Qt SQL is a port we do not need | Refuse as the generated path |
| Node graph or Blockly | Approachable on a small example | Does not merge, does not round-trip, second runtime | Refuse |
| SQL only in the window class | The owner cannot save a record without learning `sqlite3` | The cleanest code | Offer as hooks, not as the only path |

Experience First picks the sentence list over a grid of JSON. Foundational Thinking picks the AST and the two JSON records before the inspector. Model the Domain picks one connection row and one rule object, not a new boolean for every event. Laziness Protocol and Subtract Before You Add pick "no graph" and "no statement language." Exhaust the Design Space is the table above. This brief is one report, so the comparison is that table, not a throwaway UI.

## How it works

The builder edits a document model that mirrors the `.ui` tree. A save writes deterministic XML, then runs the generator.

The generator does five jobs.

1. It emits widget construction the way `uic` does, including `retranslateUi`.
2. It emits one `connect` per `<connection>`.
3. It parses every `cbcsBehavior` with an allowlisted AST. A bad object is a Problems row and emits no code for that object.
4. It topologically sorts value rules. A cycle is a Problems row. No code for the cycle.
5. It emits `cbcs_save` and the other data verbs from `cbcsData`.

`setupUi` ends by connecting dependency signals to `_cbcs_refresh`, then calling `_cbcs_refresh` once. `_cbcs_refresh` sets a re-entrancy flag, runs computed values in dependency order, then runs enabled, visible, and read-only rules. Setting a spin box during refresh must not start another refresh.

The window class calls `setupUi`. After that, `self.ui._host` is the window. Generated code calls `before_save` on the host only if the host actually defines it.

```python
before = getattr(self._host, "before_save", None)
if before is not None and before() is False:
    return False
```

A missing hook is not an error. A hook that returns `False` cancels the verb. Any other return value continues.

## Level 1, widget to widget

The canvas keeps Designer's arrows. F4 still enters that mode. The default UI is the Behavior tab, because the arrow mode is the one people cannot find.

The picker has two lists. The short list is the pairs below. "Show all signals and slots" reveals the meta-object, with `QWidget` members included, matching Designer's checkbox.

| Source signal | Target slot | Sentence |
| --- | --- | --- |
| `QAbstractButton.clicked()` | `setEnabled(bool)`, `setVisible(bool)`, `setFocus()`, `click()`, `clear()`, `show()`, `hide()` | When clicked, enable Discount rate |
| `QAbstractButton.toggled(bool)` | `setEnabled(bool)`, `setVisible(bool)`, `setChecked(bool)` | When toggled, check Taxable |
| `QLineEdit.returnPressed()` | `setFocus()` on the next tab-order widget | When Enter is pressed, go to Price |
| `QLineEdit.textChanged(QString)` | `setText(QString)` on a label | When the text changes, copy it to the label |
| `QComboBox.currentIndexChanged(int)` | `QStackedWidget.setCurrentIndex(int)` | When the choice changes, show that page |
| `QSpinBox.valueChanged(int)` | `setValue(int)` | When the number changes, copy it |

The full list can connect anything Qt would connect. The picker asks the meta-object whether the slot's arguments are a prefix of the signal's arguments. A `textChanged(QString)` wired to `setEnabled(bool)` is a design-time error, not a surprise at run time.

Arrows are blue for Level 1. The label is the sentence for a curated pair, and `clicked → setEnabled` for a raw pair. Delete removes the `<connection>` and leaves the widgets. Double-click on the arrow opens the same picker. Dragging the arrow still writes the `hint` points Designer already stores, so a form remains readable in Designer.

Try mode on the canvas fires Level 1 for real against the canvas widgets. Those slots are Qt methods. Nothing imports the user project.

## Level 2, call your method

A Level 2 connection is the same `<connection>`. The receiver is the form. The slot is a method on the window.

```xml
<slots>
  <slot>save_invoice()</slot>
</slots>
<connections>
  <connection>
    <sender>saveButton</sender>
    <signal>clicked()</signal>
    <receiver>Invoice</receiver>
    <slot>save_invoice()</slot>
  </connection>
</connections>
```

Generated code:

```python
self.saveButton.clicked.connect(Invoice.save_invoice)
```

The method name is whatever the person typed. The suggestion is `save_invoice`, not `on_saveButton_clicked`. The `on_` prefix would also match `connectSlotsByName` if a future save turned that flag back on, and the click would run twice.

Double-click on a widget opens the Behavior tab. It does not insert a stub by itself. The tab's primary button is "Create method." That button inserts the stub only when the name is missing, then jumps to the line. Clearing the action removes a stub only when the body is still the empty template. A body the user has edited is left in place, and the Problems list says the method is now unused. This keeps the Delphi jump, and it avoids the accidental stub WinForms users complain about.

The signature check is mechanical. `clicked()` accepts `def save_invoice(self)`. `toggled(bool)` accepts that, or `def show_tax(self, checked)`. A method with two parameters besides `self` is an error. A missing method is an error. A method whose body still contains only `pass` is a warning. The check parses `name_window.py` with the standard library `ast` module. It does not import the module.

Try mode does not call the method. The canvas shows "Would call save_invoice." The editor process must not import the project. Research D and research C both keep user code out of the editor.

## Level 3, the expression language

The language is a subset of Python expressions. The sentence editor writes it. A person can also type it. The generator prints it back as the same expression, so a developer who reads `ui_name.py` sees `qty * price` and not a translated tree.

### What a program can contain

Allowed nodes are constants, names, attribute reads on an allowlist, comparisons, boolean operations, arithmetic, a conditional expression, and calls to the functions below.

Allowed operators are `+`, `-`, `*`, `/`, `//`, `%`, `==`, `!=`, `<`, `<=`, `>`, `>=`, `and`, `or`, `not`, and the conditional `value if condition else other`. Parentheses work. Unary minus works.

Rejected nodes are statements, assignment, `lambda`, comprehensions, starred arguments, f-strings, subscripts, slices, `await`, bitwise operators, `is`, `in`, and `**`. A person who needs a power call writes `pow(base, exp)`. A person who needs a loop writes a method.

There is no statement form of `if`. The conditional expression is the only branch. The sentence "If the box is checked, 10, else 0" inserts `10 if discountCheck else 0`.

### Names

A bare name is a widget `objectName` on this form, or the generated name `recordIsNew`. `discountCheck` means the main value of that widget. `record.customer_id` is a column from the last loaded row. `record` is the only name that has attributes. `recordIsNew` is true when Level 4 is editing a row that has never been inserted.

If an `objectName` and a column use the same spelling, the bare name is the widget. The builder warns. The suggested widget name is `customerNameEdit`. The column stays `customer_name`. "Bind by name" is a button that creates bindings where the names already match. It is not the meaning of a bare token.

Attribute reads on a widget are limited to `value`, `text`, `checked`, `enabled`, `visible`, `currentIndex`, `rowCount`, and `currentId`. Anything else is a parse error. `value` is the main value. The other names exist so a rule can say `notesEdit.visible` without guessing which property Qt uses.

| Widget class | Main value | Empty result |
| --- | --- | --- |
| `QLineEdit` | `text()` stripped of surrounding spaces | `""`, not `None` |
| `QPlainTextEdit`, `QTextEdit` | `toPlainText()` | `""` |
| `QSpinBox`, `QSlider` | `value()` as `int` | never blank |
| `QDoubleSpinBox` | `value()` as `Decimal` | never blank |
| `QCheckBox`, `QRadioButton` | `isChecked()` | `False` |
| `QComboBox` | `currentData()` if it is not `None`, otherwise `currentText()` | `None` when the index is `-1` |
| `QDateEdit` | `datetime.date`, or `None` when the special value is showing | `None` |
| `QTimeEdit` | `datetime.time` | never blank |
| `QDateTimeEdit` | `datetime.datetime` | never blank |
| `QLabel` | `text()` | `""` |
| `QTabWidget`, `QStackedWidget` | `currentIndex()` | never blank |
| `QTableView` | no main value | use `rowCount` or `currentId` |

`QDoubleSpinBox` values become `Decimal` at the boundary so a total does not use binary float. Integer spin boxes stay `int` until they meet a `Decimal` in an arithmetic helper, which then promotes both sides.

### Null and blank

`blank(x)` is true when `x` is `None`, or when `x` is a string whose stripped form is empty. The number `0` is not blank. `False` is not blank.

`coalesce(a, b, ...)` returns the first argument that is not blank.

Arithmetic helpers return `None` if either operand is `None`. They do not treat `None` as zero. A total that should treat a blank price as zero writes `coalesce(price, 0) * qty`.

`==` and `!=` accept `None`. Ordered comparisons return `False` when either side is `None`. They do not raise. `and` and `or` use ordinary Python truth. `None` is false there.

Division by zero, and a `Decimal` conversion failure, become a run-time field error. The previous displayed value stays. The form does not close.

This is stricter than Anvil's silent `KeyError`, and kinder than a raw Python `TypeError` on `None > 0`.

### Functions

| Function | Result |
| --- | --- |
| `blank(x)`, `coalesce(...)` | Blank tests |
| `len`, `str`, `int`, `float`, `bool`, `abs`, `min`, `max`, `round` | Same roles as Python, but `int("x")` returns `None` instead of raising |
| `lower`, `upper`, `trim` | Text |
| `contains`, `startswith`, `endswith` | Case-sensitive text tests |
| `matches(text, pattern)` | `re.search` against a pattern compiled at design time. An invalid pattern is a design-time error |
| `pow(base, exp)` | Power, null-safe |
| `today()`, `now()` | Local date, local datetime |
| `date(year, month, day)` | `datetime.date` or `None` |
| `year`, `month`, `day` | Parts of a date |
| `money(text)` | `Decimal` from a string that may contain a currency symbol and commas, or `None` |
| `email_ok(text)`, `phone_ok(text)`, `date_ok(text)` | The same tests as the validation presets |

`email_ok` uses `^[^@\s]+@[^@\s]+\.[^@\s]+$`. It is a typo check, not an RFC parser. `phone_ok` strips spaces, dashes, parentheses, and dots, allows a leading `+`, and accepts 10 to 15 remaining digits. `date_ok` accepts `YYYY-MM-DD` only.

No function opens a file, imports a module, or reads an attribute the table above does not name.

### Value rules on a widget

| Key | Meaning |
| --- | --- |
| `enabledWhen` | `setEnabled(bool(expr))`. A blank result disables |
| `visibleWhen` | `setVisible(bool(expr))` |
| `readOnlyWhen` | `setReadOnly(True)` when the expression is true, for widgets that have `setReadOnly`. Others use `setEnabled(not expr)` |
| `setValueFrom` | Writes the main value when a dependency changes. Does not run when the write came from `_cbcs_refresh` |
| `format` | Display only. See below |

`format` does not change the stored value. A money label shows `$1.50`. A money edit shows `1.50` while focused and the formatted text when focus leaves, if the author opted into display format. The value rule still reads the main value, not the formatted text.

```json
{"kind": "number", "decimals": 2, "prefix": "$"}
```

```json
{"kind": "date", "pattern": "yyyy-MM-dd"}
```

`kind` is `number`, `date`, or `text`. Unknown kinds are design-time errors.

### Validation

Validation is a list. The list order is the order the form checks. The builder inserts new rules in this default order. Required, then preset, then range, then length, then pattern, then expression.

| Kind | Fields | Passes when |
| --- | --- | --- |
| `required` | `message` | `blank(value)` is false |
| `preset` | `preset` is `email`, `phone`, or `date`. Blank values pass, so pair it with `required` | The matching `*_ok` function |
| `min`, `max` | `value` number | Numeric comparison. Blank passes |
| `minLength`, `maxLength` | `value` integer | `len(text)`. Blank passes |
| `regex` | `pattern`, `message` | `matches`. The pattern is compiled at design time |
| `expression` | `expr` must be true. May name other widgets | Cross-field checks such as `endDate >= startDate` |

A failing check writes the message onto the error label and returns false. Later checks on that same widget still run, so the person sees every message for the field. The action list stops when the form-level validate action fails. It does not keep saving.

### Actions

An action list hangs off one signal inside `on`. The keys are Qt signal signatures, such as `clicked()` and `toggled(bool)`.

| `do` | Fields | Effect |
| --- | --- | --- |
| `message` | `text`, `level` is `info`, `warning`, or `error` | `QMessageBox` |
| `confirm` | `text`, `title` | Stops the list when the person chooses No |
| `openForm` | `form`, `mode` is `dialog` or `window` | Imports `forms.<form>_window` and shows it. Dialog is modal |
| `close` | `result` is `accept`, `reject`, or `close` | Calls that method on the host |
| `clearForm` | none | Sets each bound widget to its empty value and clears child rows in memory. Does not write the database |
| `setValue` | `widget`, `expr` | Writes one main value |
| `focus` | `widget` | `setFocus` |
| `setEnabled`, `setVisible` | `widget`, `expr` | One-shot. A value rule is the right tool if the property should keep tracking |
| `setTab`, `setPage` | `widget`, `index` or `name` | `QTabWidget` or `QStackedWidget` |
| `call` | `method` | Calls the method on the window. This is Level 2 inside a longer list |
| `validate` | none | Runs every validation list on the form. Stops the action list on failure |
| `sql` | `action` is `reload`, `first`, `previous`, `next`, `last`, `new`, `save`, `delete`, or `find` | Level 4 verbs. Absent data is a design-time error |
| `stop` | none | Ends the list |

Each action may have `when`. A false `when` skips that step and continues. A failed `confirm`, `validate`, `call`, or `sql` stops the list. `call` is failed when the method is missing or when it returns `False`. Other exceptions propagate. They are bugs in user code, and swallowing them would hide the traceback the developer needs.

`openForm` is the only import the generated file performs beyond Qt and the database driver. The form name must match `^[A-Za-z_][A-Za-z0-9_]*$`.

## Rule JSON

Two property names exist. Both are dynamic, both are `stdset="0"`, and both use `<string notr="true">`.

`cbcsBehavior` goes on a widget or on the root. `cbcsData` goes on the root only.

The writer emits compact JSON, with keys in the order below, and omits keys whose value is null or whose list is empty. Two saves of an unchanged form match. A `<` or `>` inside an expression is XML-escaped in the file. The parser reads the unescaped property value.

Schema version is the integer `v`. The only accepted value in this proposal is `1`. A later generator may accept `1` forever. An unknown `v` is a Problems error, and that object emits no code.

```json
{
  "v": 1,
  "enabledWhen": "discountCheck",
  "visibleWhen": "record.id != None",
  "readOnlyWhen": "not recordIsNew",
  "setValueFrom": "qty * price",
  "format": {"kind": "number", "decimals": 2, "prefix": "$"},
  "validation": [
    {"kind": "required", "message": "Email is required"},
    {"kind": "preset", "preset": "email", "message": "Enter a valid email"},
    {"kind": "expression", "expr": "endDate >= startDate", "message": "End date is before start date"}
  ],
  "on": {
    "clicked()": [
      {"do": "validate"},
      {"do": "confirm", "text": "Save this invoice?", "title": "Save"},
      {"do": "call", "method": "save_invoice"}
    ]
  }
}
```

`recordIsNew` is a generated bool. It is true when Level 4 has a new row that has never been inserted.

`cbcsData` schema:

```json
{
  "v": 1,
  "source": {
    "engine": "sqlite",
    "file": "data/shop.db",
    "connection": null
  },
  "record": {
    "mode": "record",
    "table": "invoices",
    "primaryKey": "id",
    "columns": ["id", "customer_id", "invoice_date", "notes"],
    "orderBy": "id"
  },
  "bindings": [
    {
      "widget": "customerCombo",
      "column": "customer_id",
      "lookup": {
        "table": "customers",
        "key": "id",
        "display": "name",
        "orderBy": "name"
      }
    }
  ],
  "children": [
    {
      "widget": "linesView",
      "table": "invoice_lines",
      "foreignKey": "invoice_id",
      "primaryKey": "id",
      "columns": [
        {"column": "description", "header": "Description", "widget": "text"},
        {"column": "qty", "header": "Qty", "widget": "number"},
        {"column": "price", "header": "Price", "widget": "number"}
      ]
    }
  ]
}
```

`engine` is `sqlite` or `postgres`. SQLite uses `file`, a path relative to the project. PostgreSQL uses `connection`, a name looked up in project settings. The other key is null. Passwords never appear in the `.ui` file.

`mode` is `record` or `list`. `list` is a search window and is Phase 5. `columns` is optional. When it is omitted, the generator uses every binding's column plus the primary key. A column name and a table name must match `^[A-Za-z_][A-Za-z0-9_]*$`. The generator quotes them as SQL identifiers. Values always go through parameters.

Default binding. If `bindings` is omitted, every child widget whose `objectName` equals a column name is bound. The builder button "Bind by name" writes the explicit list so the file shows the choice.

Identifiers the compiler rejects do not get concatenated into SQL. There is no expression language in the `WHERE` clause in version 1. Find is one `LIKE` parameter.

## How a rule becomes Python

The compiler never calls `eval` on the property string. It parses with `ast.parse(expr, mode="eval")`, rejects nodes outside the allowlist, and prints a function.

Widget reads become `self.qtySpin.value()` or the main-value helper `_cbcs_value(self.qtySpin)`. Operators become the null-safe helpers so the null rules live in one place. Those helpers are copied into every generated module. They are not an importable runtime. A person can read one `ui_name.py` and see the whole mechanism.

```python
from decimal import Decimal, InvalidOperation
import re

def _cbcs_blank(value):
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False

def _cbcs_mul(left, right):
    if left is None or right is None:
        return None
    return Decimal(str(left)) * Decimal(str(right))
```

A design-time failure leaves the previous generated function out of the file. The form still builds. The widget keeps its constant `enabled` value from the normal property. The Problems list says why.

## Six forms

The fragments below are the behavior portion. Widget construction is the usual `uic` shape and is omitted. Each file starts with the helpers above.

### 1. A discount checkbox enables a field

`discountEdit` has this property:

```xml
<property name="cbcsBehavior" stdset="0">
  <string notr="true">{"v":1,"enabledWhen":"discountCheck"}</string>
</property>
```

```python
def _cbcs_refresh(self):
    if self._cbcs_in_refresh:
        return
    self._cbcs_in_refresh = True
    try:
        self.discountEdit.setEnabled(bool(self.discountCheck.isChecked()))
    finally:
        self._cbcs_in_refresh = False
```

`setupUi` connects `self.discountCheck.toggled` to `_cbcs_refresh` and calls it once. Unchecked means disabled. The line edit's own `enabled` property in the `.ui` file remains the design-time default for Designer and `QUiLoader`.

### 2. A line total is quantity times price

`totalLabel` stores `{"v":1,"setValueFrom":"qtySpin * priceSpin","format":{"kind":"number","decimals":2,"prefix":"$"}}`.

```python
def _cbcs_apply_total(self):
    total = _cbcs_mul(self.qtySpin.value(), self.priceSpin.value())
    if total is None:
        self.totalLabel.setText("")
        return
    self.totalLabel.setText("$" + format(total, ".2f"))
```

`qtySpin.valueChanged` and `priceSpin.valueChanged` call `_cbcs_refresh`, which calls `_cbcs_apply_total`. A spin box always has a number, so this label updates on every change, including the first `setupUi` call. No button is required. That is the Excel rule, applied to two spin boxes.

### 3. Required email, with a label under the field

The builder inserts `emailError`, a `QLabel`, under `emailEdit` when the first validation rule is added. The author can restyle it. The generator does not invent a layout cell the author never placed. If the label is missing, the message goes to the tooltip and the Problems list warns at design time.

`emailEdit` stores:

```json
{
  "v": 1,
  "validation": [
    {"kind": "required", "message": "Email is required"},
    {"kind": "preset", "preset": "email", "message": "Enter a valid email"}
  ]
}
```

```python
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _cbcs_show_error(self, widget, label, message):
    label.setText(message)
    label.setVisible(message != "")
    widget.setProperty("cbcsInvalid", message != "")
    widget.style().unpolish(widget)
    widget.style().polish(widget)

def _cbcs_validate_email(self):
    value = self.emailEdit.text().strip()
    if _cbcs_blank(value):
        self._cbcs_show_error(self.emailEdit, self.emailError, "Email is required")
        return False
    if _EMAIL.search(value) is None:
        self._cbcs_show_error(self.emailEdit, self.emailError, "Enter a valid email")
        return False
    self._cbcs_show_error(self.emailEdit, self.emailError, "")
    return True
```

`cbcsInvalid` is a dynamic property the project's style sheet can already target. The text is what a screen reader can read, which is the gap Microsoft documents on `ErrorProvider`.

`textChanged` clears the error when the value becomes valid again. Save still runs the check.

### 4. Save validates, then calls a method

`saveButton` stores:

```json
{
  "v": 1,
  "on": {
    "clicked()": [
      {"do": "validate"},
      {"do": "call", "method": "save_invoice"}
    ]
  }
}
```

```python
def _cbcs_on_saveButton_clicked(self):
    if not self._cbcs_validate_form():
        return
    self._host.save_invoice()

def _cbcs_validate_form(self):
    ok = True
    if not self._cbcs_validate_email():
        ok = False
    return ok
```

The window file, which the builder creates once:

```python
class InvoiceWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Invoice()
        self.ui.setupUi(self)

    def save_invoice(self):
        pass
```

`setupUi` connects `clicked` to `_cbcs_on_saveButton_clicked`. The user's method is reached only after validation returns true. Replacing `pass` with a repository call is the developer's job. If they would rather use Level 4, they change the second action to `{"do":"sql","action":"save"}` and delete the method, or they keep the method and call `self.ui.cbcs_save()` themselves.

A missing `save_invoice` is a Problems error. Try mode says "Would call save_invoice" and does not construct `InvoiceWindow`.

### 5. A customer combo filled from a table

The combo binding is the lookup object in `cbcsData` above. The generator loads it when the form loads, and again from the Reload verb. It does not reload on every keystroke.

```python
def cbcs_load_customer_combo(self, connection):
    self.customerCombo.blockSignals(True)
    try:
        self.customerCombo.clear()
        self.customerCombo.addItem("", None)
        cursor = connection.execute(
            'SELECT "id", "name" FROM "customers" ORDER BY "name"'
        )
        for row in cursor.fetchall():
            self.customerCombo.addItem(str(row[1]), row[0])
    finally:
        self.customerCombo.blockSignals(False)
```

The empty first row is `None`, so a required rule can still fail the field. The stored invoice column is `customer_id`, taken from `currentData()`. The visible text is the name. This is the Delphi field list, with an explicit lookup query instead of a live dataset on the canvas.

SQLite uses `?` placeholders. PostgreSQL uses `%s`. The generator picks from `engine`. Identifiers stay quoted the same way on both.

### 6. An invoice bound to SQLite, with lines

`cbcsData` is the schema in the previous section, with `"engine": "sqlite"` and `"file": "data/shop.db"`. Navigation buttons are Level 1 connections from `firstButton`, `prevButton`, `nextButton`, `lastButton`, `newButton`, `saveButton`, and `deleteButton` to generated slots. Those slots are the verbs below. They live on `Ui_Invoice`, and the connection is made in `setupUi` to `self.cbcs_save` and the others. They are not `connectSlotsByName` names.

Dirty state is a bool on the Ui object. Every bound widget's change signal sets it. `_cbcs_refresh` does not. Save and reload clear it.

The builder inserts this `closeEvent` only when the window class does not already define one.

```python
def closeEvent(self, event):
    if not self.ui.cbcs_confirm_discard():
        event.ignore()
        return
    super().closeEvent(event)
```

```python
def cbcs_confirm_discard(self):
    if not self._cbcs_dirty:
        return True
    answer = QMessageBox.question(
        self._host,
        "Unsaved changes",
        "Discard unsaved changes?",
    )
    return answer == QMessageBox.StandardButton.Yes
```

Load and navigation:

```python
def cbcs_reload(self):
    rows = self._cbcs_query(
        'SELECT "id", "customer_id", "invoice_date", "notes" '
        'FROM "invoices" ORDER BY "id"'
    )
    self._cbcs_rows = rows
    if not rows:
        self.cbcs_new()
        return
    self._cbcs_index = min(self._cbcs_index, len(rows) - 1)
    self._cbcs_show_row(rows[self._cbcs_index])

def _cbcs_show_row(self, row):
    self._cbcs_loading = True
    try:
        self._cbcs_select_combo(self.customerCombo, row[1])
        self.invoiceDateEdit.setDate(row[2])
        self.notesEdit.setPlainText(row[3] or "")
        self._cbcs_load_lines(row[0])
        self._cbcs_dirty = False
        self._cbcs_is_new = False
    finally:
        self._cbcs_loading = False
    self._cbcs_refresh()
```

`cbcs_first`, `cbcs_previous`, `cbcs_next`, and `cbcs_last` move `_cbcs_index` and call `_cbcs_show_row`. Each one calls `cbcs_confirm_discard` first. `cbcs_new` clears the widgets, sets `_cbcs_is_new`, and leaves the primary key as `None`.

Save is an update when the primary key is loaded, and an insert when the row is new. PostgreSQL 9.5 added `INSERT ... ON CONFLICT`. The project announcement calls UPSERT shorthand for "INSERT, ON CONFLICT UPDATE". Source: [PostgreSQL 9.5 release announcement](https://www.postgresql.org/about/news/postgresql-95-upsert-row-level-security-and-big-data-1636/). PostgreSQL 9.4 added `jsonb`. Source: [PostgreSQL 9.4 release notes](https://www.postgresql.org/docs/9.4/release-9-4.html). The generator emits neither. A form save already knows whether the row is new, so it does not need a blind upsert.

`RETURNING` appears in the INSERT syntax of the 9.5 manual and is not listed among the 9.5 additions. Using it on 9.3 is an inference from that silence, not a test against a 9.3 server. The SQLite path uses `lastrowid` and does not need `RETURNING`. The spike in the last section runs the SQLite path. It does not claim a 9.3 server was available. The Python `sqlite3` connection commits when a `with connection` block finishes, and rolls back when that block raises. An explicit `BEGIN` on a connection that already opened a transaction raises "cannot start a transaction within a transaction", so the sample does not send `BEGIN` itself.

```python
def cbcs_save(self):
    if not self._cbcs_validate_form():
        return False
    before = getattr(self._host, "before_save", None)
    if before is not None and before() is False:
        return False
    connection = self._cbcs_connect()
    with connection:
        invoice_id = self._cbcs_save_invoice(connection)
        self._cbcs_save_lines(connection, invoice_id)
    self._cbcs_dirty = False
    after = getattr(self._host, "after_save", None)
    if after is not None:
        after()
    self.cbcs_reload()
    return True

def _cbcs_save_invoice(self, connection):
    customer_id = self.customerCombo.currentData()
    invoice_date = self.invoiceDateEdit.date().toPython()
    notes = self.notesEdit.toPlainText()
    if self._cbcs_is_new:
        connection.execute(
            'INSERT INTO "invoices" ("customer_id", "invoice_date", "notes") '
            "VALUES (?, ?, ?)",
            (customer_id, invoice_date, notes),
        )
        return connection.execute("SELECT last_insert_rowid()").fetchone()[0]
    invoice_id = self._cbcs_rows[self._cbcs_index][0]
    cursor = connection.execute(
        'UPDATE "invoices" SET "customer_id" = ?, "invoice_date" = ?, "notes" = ? '
        'WHERE "id" = ?',
        (customer_id, invoice_date, notes, invoice_id),
    )
    if cursor.rowcount == 0:
        raise LookupError("This invoice was deleted by someone else.")
    return invoice_id
```

Line items are a `QStandardItemModel` on `linesView`. The model is not a `QSqlTableModel`. On save, the generator deletes child rows whose ids are no longer in the grid, updates rows that still have an id, and inserts rows that do not.

```python
def _cbcs_save_lines(self, connection, invoice_id):
    kept = []
    model = self.linesView.model()
    for row in range(model.rowCount()):
        line_id = model.item(row, 0).data(Qt.ItemDataRole.UserRole)
        values = (
            model.item(row, 1).text(),
            Decimal(model.item(row, 2).text() or "0"),
            Decimal(model.item(row, 3).text() or "0"),
            invoice_id,
        )
        if line_id is None:
            connection.execute(
                'INSERT INTO "invoice_lines" '
                '("description", "qty", "price", "invoice_id") VALUES (?, ?, ?, ?)',
                values,
            )
            new_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
            kept.append(new_id)
        else:
            connection.execute(
                'UPDATE "invoice_lines" SET "description" = ?, "qty" = ?, '
                '"price" = ?, "invoice_id" = ? WHERE "id" = ?',
                values + (line_id,),
            )
            kept.append(line_id)
    if kept:
        marks = ",".join("?" for _ in kept)
        connection.execute(
            'DELETE FROM "invoice_lines" WHERE "invoice_id" = ? AND "id" NOT IN ('
            + marks
            + ")",
            (invoice_id, *kept),
        )
    else:
        connection.execute(
            'DELETE FROM "invoice_lines" WHERE "invoice_id" = ?',
            (invoice_id,),
        )
```

The `IN` clause is a list of `?` whose length equals the ids we just wrote. Those ids are integers from the database or from `last_insert_rowid`. They are not expression text.

PostgreSQL uses the same control flow. Placeholders are `%s`. Insert uses `INSERT ... RETURNING "id"` if the spike confirms 9.3, and otherwise uses a `SELECT` against the sequence the table already owns. A unique violation is SQLSTATE `23505`. The generator maps that to "A record with this value already exists." It does not retry the insert as an update. Two users inserting the same natural key should see the error, not silently overwrite. The PostgreSQL wiki's historic upsert page says "one must use a retry loop" in `READ COMMITTED` when the database has no upsert statement and the writer does not know whether the row exists. Source: [UPSERT](https://wiki.postgresql.org/wiki/UPSERT). A form save already knows. A new row inserts. A loaded primary key updates. A zero-row update is a missing record, not a cue to insert.

Delete is `DELETE FROM "invoices" WHERE "id" = ?` inside a transaction that first deletes `invoice_lines` for that id. The button's action list is `confirm`, then `sql` `delete`. A missing child table foreign key in the database is not required, because the generator deletes the children itself.

Find, in this phase, is one column. `cbcs_find` asks for a string and runs `WHERE "notes" LIKE ?` with the `%` wildcards added around a value that has `%` and `_` escaped. The result replaces `_cbcs_rows`. A full search form is `mode: list` in Phase 5.

### How a developer overrides any of it

The window class owns the process. It can do any of the following without the generator fighting back.

- Replace the Save button's action with `call`, and write `save_invoice`. The generated `cbcs_save` remains available as `self.ui.cbcs_save()`.
- Define `before_save`, `after_save`, `before_delete`, or `after_load`. Return `False` to cancel.
- Replace `closeEvent` and call `self.ui.cbcs_confirm_discard()` or ignore it.
- After `setupUi`, disconnect a generated verb and connect a different method. The `.ui` connection record is the builder's copy. A hand edit in the window runs later and wins.
- Ignore `cbcsData` entirely. A form with no `cbcsData` generates no SQL.

The generator never replaces a method body. The next save rewrites `ui_name.py` only.

## Errors

Design time uses the Problems list the editor already has. Each row names the form, the widget, the property, and the sentence.

| Condition | Severity |
| --- | --- |
| Expression does not parse, or uses a forbidden node | Error. That rule emits no code |
| Name is not a widget and not `record` | Error |
| Validation pattern does not compile | Error |
| Action calls a method the window file does not define | Error |
| Signal and slot arguments are incompatible | Error |
| Value rules form a cycle | Error |
| `cbcsData` names a column the last successful probe did not return | Warning if no database is reachable. Error if a probe just ran and the column is absent |
| Format kind is unknown, or `v` is not 1 | Error |
| Two widgets share an `objectName` | Error. Qt already requires unique names |

The expression editor underlines the token. The widget gets a badge. Both use the same message.

Run time, for a rule the compiler accepted:

| Failure | What the person sees |
| --- | --- |
| Validation returned false | The error label under the field. Save does not run |
| `confirm` returned No | The rest of the action list does not run |
| Arithmetic or conversion failed inside a value rule | The error label says the rule failed. The previous value stays. The app stays open |
| SQL raised | A message box with the database message. The transaction is rolled back. Dirty state stays true |
| Unique violation `23505` | The message "A record with this value already exists." |
| Update changed zero rows | "This invoice was deleted by someone else." Reload is offered |
| PostgreSQL connection name is missing | "The connection shop-pg is not in project settings." No password prompt is stored back into the form |
| User method raised | The normal traceback. Generated code does not catch it |

Try mode is a canvas toggle. It runs value rules and validation against the widgets on the canvas. It fires Level 1 slots. It does not import the window module, and it does not open a database connection. A SQL action shows the statement and the bound values in the Behavior tab. A separate button, "Run this SQL", is the only way the builder touches the database, and it is off by default because a save writes.

## Builder controls

The inspector gains one Behavior tab. The first control is a sentence list for the selected widget.

- When `[signal]` , do `[action]`.
- Enable when `[expression]`.
- Show when `[expression]`.
- Read-only when `[expression]`.
- Value is `[expression]`.
- Check `[required or email or a custom expression]`.

The expression row is a single line. Ctrl+Enter commits it. The line under it shows the current result, or the design-time error. Tab moves from the sentence to the expression to the error text.

The Events list is the `on` object, in signal order. Keyboard users add a row with Ctrl+N, pick a signal with the arrow keys, and reorder actions with Alt+Up and Alt+Down. F4 still toggles the canvas arrows for Level 1.

The Data panel edits `cbcsData`. It asks for SQLite file or connection name, table, primary key, and the lookup for the selected combo. It can insert the navigation buttons as a row of Level 1 connections. The person can delete any of those buttons afterward.

The canvas overlay draws Level 1 arrows in blue and Level 2 arrows in green. Level 3 dependencies stay hidden until "Show formula links" is on. That toggle exists because a total, a tax line, and a balance can cover the form in arrows. The default picture is the clicks.

Search covers this form's `objectName` values, signal names, method names, expression text, table names, and column names. The shortcut is the editor's existing find, scoped to the open form, with a "Behavior" result group. A hit opens the Behavior tab on that widget.

Undo is one command per rule edit, the same command stack as a geometry change.

## What the logic layer does not include

The layer stops at connections, a Python expression subset, an action list, and one record source with optional child rows.

It does not include a general programming language. No loops, no new functions, no classes, no imports except `openForm` of another form in the same project.

It does not include a node graph, Blockly, or Scratch. Those tools fail the round-trip test or the licence test, and they duplicate Level 2.

It does not include a query builder. Version 1 find is one `LIKE`. A join, a union, or a report belongs in the window class, where it can be tested.

It does not include `ON CONFLICT`, `jsonb`, or credentials in the `.ui` file. PostgreSQL 9.3 has neither statement. The password lives in project settings.

It does not include a runtime rules library. If the generated function is wrong, the person reads the function.

It does not rewrite `name_window.py` beyond one empty stub, and one `closeEvent` when Level 4 dirty tracking is turned on and the method is absent.

It does not evaluate database filters inside value rules. That is the Power Apps delegation bug, avoided by not having the feature.

## Phased plan

Each phase ends with a running form a reviewer can click. Later phases do not change the JSON keys earlier phases wrote.

### Phase 1, call a method

Double-click opens the Behavior tab. "Create method" inserts a stub and jumps to it. The generator emits the `<connection>` and the `connect` call. Problems reports a missing method and a bad signature. `connectslotsbyname` is false.

This is the smallest slice that matches the gesture Delphi and WinForms users actually praise. A shop owner can wire Save to a method a developer already wrote.

### Phase 2, three value rules

`enabledWhen`, `setValueFrom`, and `required`, plus the error label. Try mode evaluates those on the canvas. Scenarios 1, 2, and 3 work. The expression allowlist is the full allowlist, not a temporary dialect, so Phase 3 does not parse a second language.

This is the hobbyist slice. A discount box and a live total do not require a method.

### Phase 3, the rest of the action list

Presets, cross-field checks, confirm, open form, focus, tabs, and search across the form. Scenario 4 works. Arrows and the curated Level 1 picker ship here if Phase 1's table was enough to wire methods. If the picker slips, Phase 1's raw signal list still functions.

### Phase 4, one SQLite table

`cbcsData` for a single table, combo lookup, navigation, dirty `closeEvent`, and the `before_save` hook. Scenario 5 works. Scenario 6 works without the child grid. The database file is project-relative. No PostgreSQL yet.

### Phase 5, lines, PostgreSQL, and list forms

Child `QTableView`, transactions, the driver probe, SQLSTATE `23505`, and `mode: list` as a second form that opens the record form. Scenario 6 is complete.

PostgreSQL waits until SQLite save is boring. The placeholder difference and the connection settings are the whole port. The SQL shape stays the one Phase 4 proved.

## Spike

The spike is a throwaway script, not the inspector. It proves the compiler and the SQLite verb before anyone builds a Behavior tab.

1. Parse the allowlist. Assert that `qty * price`, `blank(email)`, and `10 if discountCheck else 0` produce an AST, and that `import os`, `obj.__class__`, and `items[0]` do not.
2. Emit Python for scenarios 1 through 4 into a string. `exec` that string in a test with stand-in widgets. Assert the checkbox disables the edit, the total is `Decimal("6.00")` for quantity 2 and price 3, a blank email fails, and a valid email calls a fake `save_invoice` only after validation.
3. Write one `.ui` with `cbcsBehavior` and `notr="true"`. Parse it with `xml.etree`. Assert the property survives a second write unchanged.
4. Run scenario 6's save, reload, and line replace against a temporary SQLite file. Assert a transaction rolls back when the child insert raises. Assert a second save updates the same invoice id. Assert delete removes children.
5. Do not open a PostgreSQL connection in the spike. Record `RETURNING` versus sequence `SELECT` as an open question for Phase 5.

Pass means the six scenarios have executable Python behind them. Fail means we still only have a document. The inspector is not part of the spike.

## Gotchas

Stock `uic` and `QUiLoader` will not run the rules. Only our generator does. The banner in `ui_name.py` should say that, or the next person will load the `.ui` at runtime and report that totals do not update.

`connectSlotsByName` plus an `on_` method name double-fires. The generator sets the flag false and avoids the prefix.

A value rule that writes a widget fires that widget's change signal. The re-entrancy flag is load-bearing. Without it, a total that reads itself loops.

Anvil ignores a missing key. We do not. A rename of `objectName` must update expressions. The rename command already has to update connections. It updates `cbcsBehavior` strings in the same command, and it updates `cbcsData` widget names.

FileMaker filters do not refresh when the underlying data changes. Our child grid reloads inside `_cbcs_show_row` and after save. It does not listen to the database.

Access subforms load before the parent. Our lines load after the parent row, inside `_cbcs_show_row`. Actions on the form's first refresh must tolerate an empty grid.

PostgreSQL 9.3 will reject `ON CONFLICT` and `jsonb`. A hand-written method can still send those statements. The generator must not.

The editor does not import the window module. Signature checks are AST checks. A method defined by `setattr` at runtime looks missing. That is acceptable. The fix is a normal `def`.

Dirty tracking misses edits made by user code that changes a widget while `_cbcs_loading` is false. Those edits should set the dirty flag, and they will, if they go through the widget signals. A direct model poke that does not emit `dataChanged` will not. `after_load` is the place to attach a custom model, and that model should emit the usual signals.

## Open limits

The expression language has no dates in `min` and `max` beyond the comparison operators. `endDate >= startDate` is an expression rule, not the `min` kind.

Money format and `Decimal` quantize to the `decimals` field. They do not know locales. A shop that needs a comma decimal writes `format` later, or formats in the window.

List forms and master-detail beyond one child table wait for Phase 5. Two child tables are a second `children` entry when Phase 5 lands. The schema already allows the array. The generator can refuse more than one child until then, with a Problems error.

There is no multi-user merge. Last save wins, except that an update of zero rows tells the person the row vanished. A shop with two clerks on PostgreSQL can lose a field another clerk changed. The developer handles that in `before_save` if the business requires it.

`openForm` does not pass a record id in version 1. The opened window loads its own first row. Passing `{"invoice_id": record.id}` is a later key on that action. Leaving it out keeps Phase 3 smaller.

## Sources

Official pages fetched for this proposal:

- [Qt signals and slots editing mode](https://doc.qt.io/qt-6/designer-connection-mode.html)
- [QDataWidgetMapper](https://doc.qt.io/qt-6/qdatawidgetmapper.html)
- [Power Apps behavior formulas](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/working-with-formulas-in-depth)
- [Power Fx overview](https://learn.microsoft.com/en-us/power-platform/power-fx/overview)
- [Power Apps delegation](https://learn.microsoft.com/en-us/power-apps/maker/canvas-apps/delegation-overview)
- [SubmitForm](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-form)
- [Anvil data bindings](https://anvil.works/docs/client/component-properties/data-bindings)
- [Access UI macros](https://support.microsoft.com/en-us/access/create-a-user-interface-ui-macro)
- [Access expressions](https://support.microsoft.com/en-us/access/examples-of-expressions)
- [Access event order](https://support.microsoft.com/en-us/access/order-of-events-for-database-objects)
- [FileMaker script triggers](https://support.claris.com/s/article/Understanding-and-using-Script-Triggers-1503692961228?language=en_US)
- [FileMaker triggers that do not run](https://help.claris.com/en/pro-help/content/actions-dont-activate-triggers.html)
- [FileMaker portals](https://help.claris.com/en/pro-help/content/working-with-portals.html)
- [BindingSource](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/controls/bindingsource-component-overview)
- [BindingNavigator](https://learn.microsoft.com/en-us/dotnet/desktop/winforms/controls/bindingnavigator-control-overview-windows-forms)
- [ErrorProvider](https://learn.microsoft.com/en-us/dotnet/api/system.windows.forms.errorprovider?view=windowsdesktop-9.0)
- [TDataSource](https://docwiki.embarcadero.com/Libraries/Athens/en/Data.DB.TDataSource)
- [TDBEdit](https://docwiki.embarcadero.com/RADStudio/Sydney/en/Displaying_and_Editing_Fields_in_an_Edit_Box)
- [Retool event handlers](https://docs.retool.com/apps/guides/interaction-navigation/event-handlers)
- [Appsmith UI actions](https://docs.appsmith.com/core-concepts/writing-code/ui-actions)
- [Budibase chaining actions](https://docs.budibase.com/docs/chaining-actions)
- [Bubble conditions](https://manual.bubble.io/core-resources/bubble-workflows/conditional-workflow-properties)
- [Glide actions](https://www.glideapps.com/docs/automation/actions.md)
- [Airtable interface buttons](https://support.airtable.com/articles/2099494420-using-buttons-in-interfaces)
- [Excel as a programming language, Microsoft Research](https://www.microsoft.com/en-us/research/blog/influencing-mainstream-software-applying-programming-language-research-ideas-to-transform-spreadsheets/)
- [Blockly code generation](https://docs.blockly.com/guides/get-started/code-generation/)
- [node-red-contrib-blockly](https://flows.nodered.org/node/node-red-contrib-blockly)
- [PostgreSQL 9.5 UPSERT announcement](https://www.postgresql.org/about/news/postgresql-95-upsert-row-level-security-and-big-data-1636/)
- [PostgreSQL 9.4 release notes](https://www.postgresql.org/docs/9.4/release-9-4.html)
- [PostgreSQL wiki, UPSERT](https://wiki.postgresql.org/wiki/UPSERT)
- [Using a Designer UI file](https://doc.qt.io/qt-6/designer-using-a-ui-file.html)
- [Bubble workflow actions](https://manual.bubble.io/help-guides/logic/workflows/actions)

Local research already in the repo, read for this proposal:

- `docs/form_builder/research/A_market_survey.md`
- `docs/form_builder/research/P_user_pain_points.md`
- `docs/form_builder/research/R3_designer_parity_checklist.md`
- `docs/form_builder/research/D_first_principles_architecture.md`

Follow-up pages opened in this file are the Qt auto-connect note, Bubble's action-order page, and the PostgreSQL upsert wiki. A research pass also opened the Epic 4.27 Blueprint guide and a Scratch analysis paper. Those two are not quoted here. No PostgreSQL 9.3 server was contacted.
