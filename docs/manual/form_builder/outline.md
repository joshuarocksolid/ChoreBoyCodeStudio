# The outline

The outline lists every widget on the form. The pane header is `Outline`. Press `Alt+1` to move focus there.

## What a row shows

The row's main text is the object name. The faint caption is the kind of widget and its visible text, such as `Line edit “Full name”`.

A page caption uses the container's word. A tab widget says `Tab 1 · Printing`. A toolbox or a stacked widget says `Page`. A wizard says `Step`. An MDI area says `Window`.

A hidden widget is drawn faint. A problem shows a problem mark on the row.

The filter box says `Find a widget`. When nothing matches, the pane says `No widget matches “…”` and offers `Clear`.

## Rename

Select a widget. Press F2. You can also double-click the outline row, or edit `Name` at the top of the inspector.

The name box refuses an empty name, a reserved name, a second widget with the same name, and a name that would replace a method of the window. The reason appears on the box. Those refusals are not rows in the Problems panel.

## Nest and un-nest

In the outline, Tab nests the selection into the previous sibling, when that sibling can hold it. Shift+Tab un-nests it.

When nothing above can hold the widget, the status line says `Nothing above to nest into.` A page stays inside its container. A widget that is already at the top says it is already at the top level.

On the canvas, Tab moves the selection. Nesting is an outline key.

[Form builder manual](index.md)
