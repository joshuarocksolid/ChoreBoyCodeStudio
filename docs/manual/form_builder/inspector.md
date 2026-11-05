# The inspector

The inspector is the pane on the right. Press `Alt+4` to move focus there. It has three tabs. `Properties`, `Behavior`, and `Data`.

The header shows the object name and the class. A class you wrote yourself reads `your class, based on` the Qt class under it. The path under the name shows where the selection sits.

When the selection has events, the Behavior tab adds a count, such as `Behavior (2)`.

## Properties

For a widget, the groups are Content, Pages, Input, Appearance, Size, Placement, Layout, Accessibility, and All properties.

For the form itself, the sections are Window, Layout, Tab order, Problems, and Files.

A property that is stored in the file is drawn stronger than a default. Reset puts the default back and removes that line from the file.

`Ctrl+F` while the inspector has focus opens `Find a property`.

## Behavior

This tab holds the rules and the events for the selection.

- `STATE` is the kind of value, when the widget is enabled, visible, or read-only, and the formula for its value.
- `CHECKS` are the tests a value must pass.
- `EVENTS` are the steps that run when something happens.
- `FROM OTHER WIDGETS` lists steps on other widgets that act on this one.

Press `Alt+B` to open this tab. See [Logic](logic.md) and [Signals and slots](signals.md).

## Data

This tab binds a field to a column. A label or a layout says `Labels and layouts aren't bound. Select a field.`

A field that can be bound has a `Column` row. `Only show, never save` keeps the column on screen and leaves it out of the save. A combo filled from another table has a `Lookup` section.

`Alt+D` opens this tab. The left pane also has a Data section for the form's table, its toolbar, and its lines. Press `Ctrl+Shift+D` for that pane. See [Records](records.md).

[Form builder manual](index.md)
