# Form builder

This manual is for shop programmers who build data-entry apps in ChoreBoy Code Studio. An invoice, a customer card, and an inventory count are the kind of screen this tool is for.

You draw the window on a form. Code Studio saves a `.ui` file and writes the Python that shows it. Your own code goes in the window file. The generated file is rewritten every time you save the form.

Open a project first. Then use `File > New Form…`, or right-click a folder in the project tree and choose `New Form…`.

## Start here

- [Start a form](start.md). Blank, template, or a form built from a table.
- [The canvas](canvas.md). Select, zoom, and switch between Design and XML.
- [The widget box](widget_box.md). Insert a field.
- [The outline](outline.md). See every widget, rename one, and nest one.
- [The inspector](inspector.md). Properties, Behavior, and Data.
- [Layouts](layouts.md). Rows, columns, grids, and Hug, Fill, and Fixed.

## Make the form easy to use

- [Buddies and tab order](buddies_and_tab_order.md). Underlined letters and the Tab key.
- [Pictures](pictures.md). Pictures that still show after you package the app.
- [Style sheets](style_sheets.md). Colours and rules for one widget or the whole form.
- [Your own class](own_class.md). A Python widget you already wrote.
- [Signals and slots](signals.md). What happens when someone clicks.
- [Logic](logic.md). Rules, checks, formulas, and the four layers stored in the form file.

## Data

- [Connections](connections.md). SQLite and PostgreSQL. Code Studio keeps the passwords.
- [Records](records.md). One record at a time.
- [Lines and grids](lines.md). Invoice lines under a header.
- [Find](find.md). Find a widget while you design. Find a record while the app runs.
- [Conflicts](conflicts.md). Someone else saved the same record.

## Run it and ship it

- [Preview and Try](preview.md). Look at the form. Try writes, then rolls them back.
- [Generated files](generated_files.md). What you edit, and what you leave alone.
- [Rename and move a form](rename_and_move.md).
- [Packaging](packaging.md).
- [Form problems](diagnostics.md). Every problem code the Problems panel can show.
- [Keyboard reference](keyboard.md).
- [What is different from Qt Designer](qt_designer.md).

A person can walk an invoice from a table through Try, Preview, and a package on two carts with the [acceptance checklist](../../form_builder/ACCEPTANCE.md).
