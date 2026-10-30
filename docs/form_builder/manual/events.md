# Events

## The Events list
Select one widget. Behavior shows Events. The line under the tab is the widget's name and its object name, such as "Save · saveButton". Each event is a header ("When clicked") and its steps, in the order they run. "+ When…" adds an event. "+ Then…" adds a step to the event that has focus.

Nothing there yet: "Nothing happens yet when Cancel is clicked." A button also says "Double-click it on the form to write code for it."

Several widgets: "Select one widget to see what it does." A layout or a spacer: "Layouts and spacers don't have events. Select a widget."

## From other widgets
When another widget's step acts on the one you selected, From other widgets lists it: "When Clear is clicked: Clear Name". Enter selects that widget and shows the step.

## All events on this form
Select the form. All events on this form lists every step, grouped by widget in outline order. The filter is "Search events". Enter selects the widget the row names. Delete removes that step. An empty form says "No events on this form yet."

## The pickers
"+ When…" opens When…. Type to narrow the list. Enter opens Then…. Esc on the first page closes and does not change the form.

Then… lists what can happen: "Close this form", "Clear a field…", "Call a new method…", "A widget's own action…". A choice that needs a widget asks which one. Esc goes back one page. A finished choice is one undo step.

Ctrl+Shift+E opens the same picker. Form > Add event… does too.

## Keys
Alt+B opens Behavior and focuses the first event, or "+ When…" when there is none.

In the list: Up and Down move, Enter changes the row, Delete removes it, Alt+Up and Alt+Down move a step, Ctrl+D duplicates it, Space turns it off or on. Esc returns to the form.

The header's … menu is "Change event…" and "Delete the event". An event stored in two places shows "This event is stored in two places." and a Merge button. Merge is one undo step, "Merge the {event} event".

## Designer labels
Turning a step off and back on keeps a Qt Designer connection's label positions. Pointing a step at a different widget or action drops them, because the arrow's end moved. Undo always puts the form back exactly.
