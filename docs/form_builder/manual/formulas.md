# Formulas

## State
Select one widget. Behavior shows State above Events.

A line edit lists Kind, Enabled when, Visible when, Read-only when, Value, Default, and Format. A button lists Enabled when and Visible when. Read-only when appears when the widget can be read-only. Value and Default appear when the widget has a value. Kind appears for a line edit, a label, or a plain text edit. Format appears for a label or a line edit, under Value.

An empty row shows its usual state in grey: "always", "never", "typed by the person", or "as designed". A filled row shows the formula and "now: {value}". A yes or no reads as "yes" or "no". A missing value reads as "blank".

Enter on a row opens the formula field. The field opens directly.

## The formula field
The field is one line. Shift+Enter adds a line, up to six. Further Shift+Enter does nothing.

Ctrl+Enter saves. Esc puts the stored formula back. A formula with no error is also saved when you leave the field. A formula with an error stays open, and the line under the field says "Fix or press Esc to undo this formula".

That line reads the type and "now: {value}". A second line reads the formula with display names when that differs from the typed text. A formula with an error shows the problem, not a type. "A window value" is only the type of a window.m() read.

Each save is one undo step, "Set Enabled when for Discount rate". Clearing the field is "Clear Enabled when for Discount rate".

## Completion
After two letters, or Ctrl+Space, a list opens. Widgets come first, as "{name}  {display}  {Kind}", then functions with a one-line description, then `window.` methods once you have typed `window.`. Tab or Enter accepts the row. Accepting a display name writes the object name.

## Fixes
An error is underlined in red, a warning in amber, and a note with a dotted line. The message is on the status line. Ctrl+. applies the fix when there is one. When there are several, a list of the fixes opens. Applying a fix does not save the row.

## Kind and Format
Kind is Text, Whole number, Number (places), Money, Percent, Date, or Time. Number (places) has a places control named "Decimal places", from 0 to 6. Changing Kind saves `cbcsKind`. Format is how a label or a line edit shows its value: money, number:N, percent:N, date:short, date:long, date:iso, text:upper, text:proper.

## A rule instead of a connection
Connecting a check box's toggled signal to setEnabled asks "Keep {target} enabled only while {sender} is checked? A rule also gets this right when the form opens." Make it a rule is the default. It saves Enabled when as the check box's name and does not add the connection. Connect anyway keeps the connection. Esc changes nothing.

setVisible asks "Keep {target} visible only while {sender} is checked? A rule also gets this right when the form opens."
