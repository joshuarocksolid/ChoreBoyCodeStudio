# Layouts

A layout keeps fields in rows or columns when the window changes size. Put widgets in a layout instead of dropping them at fixed pixels.

## To lay out the selection

Select the widgets, or select the box that should hold them. Open `Form > Layout` and choose a kind.

| Menu | Key | What you get |
| --- | --- | --- |
| Horizontal | Ctrl+1 | A row |
| Vertical | Ctrl+2 | A column |
| Horizontal splitter | Ctrl+3 | A row the user can drag |
| Vertical splitter | Ctrl+4 | A column the user can drag |
| Grid | Ctrl+5 | Rows and columns |
| Form | Ctrl+6 | Labels beside fields |

`Wrap in…` (`Ctrl+Shift+G`) asks which box to wrap the selection in. Group box, frame, and tab widget are in that list, along with the layouts.

`Unwrap` is `Ctrl+Shift+B`. `Remove layout…` breaks the layout and leaves the widgets. `Adjust size` is `Ctrl+J`. `Simplify grid` drops empty rows and columns. `Keep at content size` holds the widget at the size of its contents.

A main window tells you to lay out the central widget instead of the window.

## Hug, Fill, and Fixed

`Form > Size` sets how a widget uses the room its layout offers.

- `Hug` is as big as the content needs, and no bigger.
- `Fill` takes the spare room the layout gives it.
- `Fixed` is an exact pixel size.

Each one has a width command and a height command. `Reset size` clears the choice. The selection chip shows the words, such as `Hug × Fill`.

## A new field on a form layout

Insert a line edit into a form layout. Code Studio adds a label that reads `New field:` and makes that label the field's buddy. The label editor opens so you can type the real caption.

Buttons, check boxes, radio buttons, and group boxes skip the extra label. They already show their own text.

See [Buddies and tab order](buddies_and_tab_order.md).

[Form builder manual](index.md)
