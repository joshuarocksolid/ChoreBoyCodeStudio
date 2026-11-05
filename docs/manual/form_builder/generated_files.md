# Generated files

Saving a form in a project writes the Python that shows it. You edit the window file. You leave the generated module alone.

## What save writes

For `forms/invoice.ui`, save writes `forms/ui_invoice.py`. The first save also creates `forms/invoice_window.py` when that file is not there yet. Later saves leave the window file in place and rewrite `ui_invoice.py`.

A form under `forms/` also gets `forms/__init__.py` if that file is missing.

The class in the window file is the form's class name plus `Window`. Your methods belong in that class.

`cbcs_connections.py` is rewritten from `Settings > Connections`. Edit the connections there.

## The banner

The top of `ui_invoice.py` says it was generated from the `.ui` file by ChoreBoy Code Studio, that you should not edit it, and that it is rewritten every time the form is saved. The next line names the window file.

When the form has rules, checks, or data, two more lines say the behaviour runs only through the generated file, and that loading the `.ui` file with `QUiLoader` gives the layout without the behaviour.

Opening the generated file shows a bar with the same warning. The buttons are `Open` the `.ui` file, `Open` the window file, and `Edit anyway`. `Edit anyway` lets you type in that tab. The bar stays.

## If you edit the generated file anyway

Save asks before it replaces the file. The dialog says the file has edits made by hand and that saving the form will replace them. The choices are `Replace`, `Open` the file, and `Cancel save`. Cancel leaves the `.ui` file unsaved.

Replace keeps a copy under `cbcs/form_builder/hand_edits/` and then writes the new module. The Problems panel warns that a generated file was edited by hand, and the fix is `Open the saved copy`.

## Names that cannot be generated

A widget name, or a form file name, that cannot be a Python module is an error. A generated file that is older than the form is a warning. A form outside the project is an info note. The codes are in [Form problems](diagnostics.md), from FB501 through FB510.

[Form builder manual](index.md)
