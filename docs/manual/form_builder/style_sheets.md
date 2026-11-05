# Style sheets

A style sheet is a set of rules that restyle a widget and everything inside it. The property on the widget is `styleSheet`.

## To edit a style sheet

1. Select the widget, or select the form for the whole window.
2. On Properties, under Appearance, find `Style sheet` and click `Edit…`.

You can also right-click and choose `Edit style sheet…`, or use `Form > Style sheet of the form…`.

The drawer title is `STYLE SHEET`. `Insert` can add a colour, a picture, a gradient, a font, or a rule for this widget. `Done` closes the drawer.

The row summary reads `None`, `1 rule`, a count of rules, or `Can't be read`.

`Text colour` and `Background` on the Appearance group write into the same sheet. If the sheet cannot be read, those rows say `The style sheet can't be read, so it can't be changed here.`

## When Qt cannot read the sheet

The drawer checks the text as you type. A good sheet says `Looks right`. A sheet Qt cannot read says `Qt can't read this style sheet.`

The drawer does not write a sheet that does not apply. The canvas keeps the last sheet that did apply.

A bad sheet that is already in the file stays there. The Problems panel says the style sheet cannot be read, so Qt ignores all of it. The fix is `Edit style sheet`. A rule that matches nothing on the form is reported too, and the drawer marks it `No match`.

`Ctrl+F` while the drawer has focus opens `Find in style sheet`. That key does not open the drawer from the canvas.

[Form builder manual](index.md)
