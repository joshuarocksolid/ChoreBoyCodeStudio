# Find

Find while you design and Find on a running record form are two different keys that share a name.

## While you design

`Edit > Find` and `Ctrl+F` follow the focus.

- In the outline, the filter box `Find a widget` opens.
- In the inspector, `Find a property` opens.
- In the style sheet drawer, `Find in style sheet` opens.
- On the XML view, the editor find bar opens.
- On the Design canvas, with none of those open, the key does not open a find bar.

`Ctrl+R` is Go to widget. Type part of a name, a label, or a class, and jump to it.

`Ctrl+Shift+F` is Find in Files in the rest of Code Studio. While a form tab is the one you are looking at, that key filters the Logic pane instead of searching the project. With no form and no project, Find in Files says `Open a project first.`

## On a running record form

The toolbar button `Find` uses `Ctrl+F` inside the app you built. It asks `Find` in a small dialog. Unsaved changes are offered for save first.

An empty search shows the current record again. Any other text replaces the list of keys with the matches and shows the first one. A label you named `findLabel` can show `Showing … matches. [Show all]`. The default toolbar does not add that label. The `Show all` step loads the full key list again.

[Form builder manual](index.md)
