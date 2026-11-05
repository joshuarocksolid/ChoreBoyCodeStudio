# Connections

Code Studio keeps the database connections for the project. A form names a connection. The password stays in the connection settings, not in the `.ui` file.

`Form > Overlays > Connections` draws signal arrows. Database connections are on `File > Settings...`, page `Connections`. See [Signals and slots](signals.md).

## To add a connection

1. Choose `File > Settings...` and open `Connections`. On a form, `Add a connection…` on the Data tab opens the same page.
2. With no connections yet, the page says `No connections yet. Add one to bind forms to a database.`
3. Click `+ Add SQLite file` or `+ Add PostgreSQL`. When the list already has one, use `+ Add` and the same two names.

With no project open, the page says `Open a project to manage its connections.`

## SQLite

Set `Name`, `Code`, and `File`. `Choose…` picks the file. Keep the database inside the project so it is packaged with the app. A file outside the project shows `Keep the database inside the project so it is packaged with the app.`

SQLite has no password row.

## PostgreSQL

Set `Host`, `Port`, `Database`, `User`, `Schema`, and `Password`. The port defaults to 5432.

The password choices are:

- `Ask when the app starts`
- `Remember on this machine`
- `No password`

A new PostgreSQL connection starts on `Ask when the app starts`. The password prompt is titled `Password` and reads `Password for …`. The checkbox `Remember on this machine` appears on that prompt only when the connection uses that choice.

The remembered password is a file on this computer. If other users of the computer can read it, the page warns you. The Problems panel can show the same warning. The fix is on that row. See FB321 in [Form problems](diagnostics.md).

## Test

Click `Test`. The button reads `Testing…` until the check finishes. Esc cancels it.

A SQLite success reads `Connected` and the table count. A PostgreSQL success names the server, the table count, and the driver. The drivers Code Studio tries are `psycopg` and `pg8000`, both shipped with FreeCAD. A failure names a refused password, a host it cannot reach, a missing database, or `No PostgreSQL driver could be loaded (tried psycopg, pg8000).`

`In Try, only show the SQL` leaves the database unchanged and prints the statements in Preview. See [Preview and Try](preview.md).

`Create setup function` writes a function in `connection_setup.py` when you need a hook after connect.

## Names

The `Code` row is the name forms store. It uses letters, digits, and underscores, and it starts with a letter or an underscore.

Renaming a connection that forms already use asks you to update those forms. Removing a connection that a form still uses asks you to remove it from that form first.

The generated module is `cbcs_connections.py`. Its header says to edit connections in `Settings › Connections` and not to edit the file. See [Generated files](generated_files.md).

[Form builder manual](index.md)
