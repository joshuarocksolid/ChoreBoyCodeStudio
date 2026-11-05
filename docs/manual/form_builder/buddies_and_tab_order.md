# Buddies and tab order

A buddy is the field that receives focus when someone presses the underlined letter on a label. Tab order is the path of the Tab key through the fields.

The toolbar has `Tab order` (`F8`) and `Buddies` (`F7`). The same commands are under `Form > Overlays`. One overlay is open at a time. `Done · Esc`, F3, or Esc closes it.

## To set tab order

1. Press F8.
2. The banner says `Click fields in the order Tab should visit them.`
3. Click the fields in the order you want, or select a field and press Enter.
4. Shift+click, or Shift+Enter, continues numbering from the selected field.
5. Backspace takes back the last number you gave during this visit.

A widget that does not take focus has no number. The status line says so.

`Reset to reading order` deletes the saved order. With no saved order, Tab follows the page from top to bottom, then left to right.

`Form > Overlays > Tab order list…` opens the same order on the form's Properties tab. Drag a row, or press Alt+Up and Alt+Down. `Use reading order` shows only when a custom order is stored. A custom order says `Custom order. New fields join it where they sit on the form.`

The saved order is a `tabstops` list in the `.ui` file. Reading order is computed and is not written into the file.

## To pair a label with a field

1. Press F7.
2. The banner says `Drag from a label to its field.`
3. Drag from the label to the field, or press Enter on the label and Enter on the field.

`Pair labels automatically` sets a buddy only on labels that do not have one yet. The status line reports how many labels were paired.

You can also set one label from the inspector. Select the label. On Content, choose `Buddy`. `None` clears it. The help on that row says the field gets focus when the user presses the label's Alt letter.

The buddy is stored on the label as the field's object name.

[Form builder manual](index.md)
