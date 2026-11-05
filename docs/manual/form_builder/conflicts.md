# Conflicts

Two people can open the same invoice. The form notices when the row in the database changed after you loaded it.

## What you see

On save, the dialog says `Someone else changed this invoice since you opened it.` The word `invoice` is the record word for that form. A customer form says `customer`.

The buttons are:

- `Reload their version`. The form loads the row again. Your unsaved edits on that row are dropped, and the save stops.
- `Cancel`. The save stops. You keep what you typed.
- `Keep mine and save`. This button is on the dialog only when the form allows overwrite.

## To allow overwrite

On the Data source sheet, tick `Let people keep their version on a conflict`. The box is off until you tick it. The form file stores `allowOverwrite` on `cbcsData`.

Leave the box off when the second person should reload instead of writing over the first person's save.

## A row that was deleted

If the row is gone, the dialog says `This invoice was deleted by someone else.` The button is `Close`.

[Form builder manual](index.md)
