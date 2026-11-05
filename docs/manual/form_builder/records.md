# Records

A record form loads the keys for the table, then shows one record at a time.

## To bind the form

1. Open the Data pane with `Ctrl+Shift+D`, or use `Connect to a table…` on an empty Data tab.
2. Choose the connection and the table. The table needs one key column.
3. Click `Bind fields by name` to match columns to fields.
4. Click `Add record toolbar` when you want First, Previous, Next, Last, New, Save, Revert, Delete, and Find on the form.

The empty Data tab says `This form isn't connected to a database.` `Add a connection…` shows when the project has no connection yet.

On the source sheet, `Opens at` can be `First`, `Last`, `A new record`, or `Nothing`. Order is `Ascending` or `Descending`.

`Let people keep their version on a conflict` is off until you tick it. See [Conflicts](conflicts.md).

## What the running form does

The position label reads `Record 1 of 1`, or `New` plus the record word, while you are on a new row. The record word comes from the source. A table named `invoices` uses `invoice`.

The toolbar keys on the running form are:

- First is Ctrl+Home
- Previous is PgUp
- Next is PgDown
- Last is Ctrl+End
- New is Ctrl+N
- Save is Ctrl+S
- Find is Ctrl+F

Revert, Delete, and the position label have no shortcut.

Moving, New, Find, and Show all ask `Save changes to this …?` when the row is dirty. The buttons are Save, Discard, and Cancel. Closing the window asks the same question. Cancel leaves you on the row.

Delete asks `Delete this …?` with Delete and Cancel.

The stored source is `cbcsData` on the form. Each bound field stores the column name on `cbcsBind`. `Only show, never save` stores `cbcsBindMode` as `readOnly`.

A form that is not connected to a table, with a record step on it, is reported in the Problems panel. See [Form problems](diagnostics.md).

[Form builder manual](index.md)
