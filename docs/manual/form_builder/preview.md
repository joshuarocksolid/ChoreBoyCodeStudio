# Preview and Try

Preview shows the form in its own window. Try is Preview with `Run behavior` turned on. On a database form, Try rolls the data changes back.

## To preview

Click `Preview` on the toolbar, or press `Ctrl+Shift+R`, or choose `Form > Preview`.

The window title starts with `Preview` and the form file name. A style or a screen size that is not the default is added to the title.

Preview uses the form as it is now, including unsaved edits.

`Form > Preview options` sets text size and screen scale. `Two widths` is `Ctrl+K, W`. `Form > View Python code` is `Ctrl+K, C`. `Form > Print…` prints the form. `Ctrl+P` stays Quick Open.

## To try the behavior

1. Tick `Run behavior` on the Preview toolbar. The tooltip is `Run the form's behavior`.
2. Press `Ctrl+Shift+R`.

The preview window shows `What ran` under the form. Clicks, checks, and record steps run there.

## What happens to the data

SQLite uses a scratch copy. The strip says `Data: scratch copy of …`. `Reset data` copies the file again. The scratch file is deleted when Preview closes.

PostgreSQL rolls back. The strip starts with `Data:` and the database name, then says `Changes are rolled back.` The banner starts with `Try: changes to` and the database name, then says the changes are rolled back and that other people may wait up to 2 seconds while a save runs.

After a save in that mode, What ran includes `Saved, then rolled back`. The row in the database is unchanged.

`In Try, only show the SQL` on the connection prints `Would run` and does not commit. The strip says `Only the SQL is shown.`

A form that connects through your own method says `This form uses your own connection method, so Try only shows what it would run.` There is no rollback banner in that case.

Try can also report a sequence number that was used and will be skipped on the next real save, and a table whose triggers do work outside the database. That outside work is not rolled back.

A lock that waits too long says another user is editing this record and Try stopped waiting after 2 seconds. A query that runs too long says Try stopped it after 5 seconds.

## When Preview stops

The Problems panel reports a preview process that stopped, a custom widget that did not load, a protocol mismatch, an exception in Try, and Preview turned off after repeated crashes. See the FB6 codes in [Form problems](diagnostics.md).

[Form builder manual](index.md)
