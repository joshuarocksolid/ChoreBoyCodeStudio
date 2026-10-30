# Your code

## Double-click
Double-click a button, a check box, a radio button, a command link, a dialog button box, or an action. Code Studio writes a method for that widget's usual event and selects `pass`.

The method page is "Call a new method…". The name field starts with the suggested name. The line under it is one of these:

"Adds print_receipt() to ShopWindow in shop_window.py."

"Use a method name like print_receipt: letters, digits and _, starting with a letter."

"{name} is a method of {Qt base class}, so it would replace it. Try {suggestion}."

"Methods named on_… also run by their name. Pick another name."

"ShopWindow already has {name}. This event will call it."

When the event sends a value, the page has "My method receives {value words}". Leave it off unless the method should take that value.

"METHODS IN {window file}" lists methods this event can call. One this event already calls is marked "already here".

When the file cannot be listed, the page shows one line: "{window file} can't be read: {reason}", "{window file} has no class that calls self.ui.setupUi(self).", or "This form isn't in a project, so it has no window file."

## Write code for
The widget's menu has "Write code for “clicked”" for the usual event. It writes the same method a double-click writes.

A form that is not in a project says "This form isn't in a project, so it has no window file." A form in the project but not in forms/ says "This form isn't in forms/, so Code Studio doesn't write Python for it." Double-click then opens the event picker for the usual event, and the status bar shows the same sentence.

A form saved by a newer version of Code Studio says "This form's behavior was saved by a newer version of Code Studio, so it can't be changed here." If the method is already there, double-click still opens it.

## Undo
Writing the method is one step on the form. The text itself is one edit in the window file's tab.

Undo removes the step and the method while the method is still the text Code Studio inserted. Edit the method, then undo, and the step goes. The method stays. The status says "Removed the step. {method}() has your code in it, so it stays in {file}."

Redo puts the step back, and puts the method back when the class does not already have it.

## Go to code
F12, or Form > Go to code, opens the window file at the method. A step row goes to that step's method. A selected widget goes to the method of its usual event, or the first event that has one. The form itself goes to the class line.

Nothing to open: "{display name} has no code yet. Double-click it, or press Ctrl+Shift+E to add an event." Or "{method}() isn't in {file} yet. Press Ctrl+. to create it."

A call step shows its place as "shop_window.py:42". Missing method: "not in shop_window.py". The file could not be checked: "not checked".

## Your methods
Select the form. Your methods lists every method the form names.

"print_receipt() · Print receipt clicked · line 42"

"close_shift() · not used · line 60"

"export_day() · not in shop_window.py"

The caption is "Code Studio adds methods to {file} and never changes the rest of it."

Enter opens the method. Delete on a declaration no step uses is one step, "Remove method declaration {name}". A used one says "{name} is used by {n} steps. Delete those steps first."

Signals the form declares are listed under "SIGNALS YOUR FORM DECLARES".

## Connect methods by name
Form settings has "Connect methods by name". It is on unless the form stores the setting as false. The caption is "Methods named on_{widget}_{event} with @Slot run without a step. Qt Designer calls this Connect slots by name."

With it on, a matching method is a row in that event: "on_okButton_clicked() runs by its name". It has no number. Its menu is "Go to code" and "Why does it run?". The status says "Qt runs methods named on_{object}_{event} by themselves, because Connect methods by name is on."

## Run
F5 with an unsaved window file asks "Save {file} before running? It has code this form calls." Save and run saves the file, then runs. Run without saving runs the form as it is. Cancel does not run. A clean or closed window file does not ask.

## Preview
Preview does not import the window file. It stands in for each method the form names. The status bar says "Preview: {display name} {event words} would call {method}() in {file}." when one event calls it, and "Preview: {method}() in {file} would run." when more than one does.
