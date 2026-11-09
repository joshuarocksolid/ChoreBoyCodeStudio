# Start a form

To start a form, open a project. Choose `File > New Form…`. You can also right-click a folder in the project tree and choose `New Form…`.

With no project open, Code Studio says `Open a project first.`

The tab is titled `New form`. Type a name. The folder list defaults to `forms/`. The line under the name tells you which files that name will create. A form named `invoice` in `forms/` creates `forms/invoice.ui`, `forms/ui_invoice.py`, and `forms/invoice_window.py`.

Names use letters, digits, and `_`, and they start with a letter. `ui_` and `cbcs_` are reserved. A Python keyword is refused.

`Ctrl+N` starts a new project. The New form tab has no shortcut of its own.

## Pick a starting point

The cards are in four groups.

**Your templates.** This group is hidden until you have saved a template. `Form > Save as template…` stores a copy of the design and its pictures. Your code and your data are not included. You can keep the template for all of your projects or for this project only.

**Templates.**

- `Data entry form`. Labels and fields.
- `List and detail`. A list beside one item.
- `Table with search`. Search above a table.
- `Dialog with OK and Cancel`. Fields, OK, and Cancel.
- `Dialog with side buttons`. Fields, with the buttons at the side.

**Start blank.**

- `Widget`. An empty vertical layout.
- `Main window`. An empty central area.
- `Dialog`. An empty dialog layout.
- `Wizard`. Two steps, with Back and Next.

Click a card in those groups. Code Studio writes the files and opens the form on the Design view.

**From what you have.**

- `Build a form from a table`. This opens a dialog. It does not write a file until you create the form.
- `Adopt a form your code already loads`. Use this when the app already opens a `.ui` file.

## Build a form from a table

1. On the New form tab, click `Build a form from a table`.
2. Choose a connection. If the list is empty, click `Add connection…` and follow [Connections](connections.md).
3. Under `Make`, choose `Record form`, `List screen`, or `List screen and record form`.
4. Tick the columns to include. You can change `Shows as` and `Label`.
5. When another table points at this one, tick `Include lines from` and choose the link.
6. Click the button at the bottom. It reads `Create … form with N fields`, and it adds `and lines` or `and a list` when those options are on. A list-only choice reads `Create … list with N columns`.

The form is bound to that table. A list screen uses a second file whose name ends in `_list`.

`Open this screen when the app starts` is available when `main.py` is still the stock file. When `main.py` is your own code, the box stays off. The note tells you to open the new screen from `main.py` yourself.

## What you should see

The `.ui` file opens on the canvas. The outline shows the fields. Save writes the generated Python beside the `.ui` file. Put your own code in the window file. See [Generated files](generated_files.md).

[Form builder manual](index.md)
