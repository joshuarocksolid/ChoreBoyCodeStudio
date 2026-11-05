# Packaging

`Run > Package Project...` builds the installable app. The packaged app imports the generated Python. It does not load the `.ui` file at runtime.

## Before you package

Save every form. A missing or older `ui_*.py` is `Generated form file is missing` or `Generated form file is out of date`. On FreeCAD 1.1 the fix button is `Save the form now`. On an older FreeCAD the badge is `Warning` and the label is `Warning: export continues`. The next step says to open the project in FreeCAD 1.1 or later and save the form.

A picture stored as a file path is `A picture uses a file path`. Open the form, select the widget, and choose `Add to project pictures`. The packaged app does not carry that outside file, so the picture is blank when it runs.

Code that still loads a `.ui` file at runtime is reported. Use `Adopt a form your code already loads`, then paste the `setupUi` suggestion into the window class. A packaged app should call `setupUi` on the generated class.

A `.ui` file the app loads, and that the package list leaves out, is `The package list is missing a form`. Put the file back in the project.

A generated module that mentions `cbcs_connections.py` needs that file in the package. Save a form that uses a connection so the file is written.

## What does not ship

Copies of hand-edited generated files under `cbcs/form_builder` are left out of the package.

## Where the app is installed

The installer places the app under `/home/default/FreeCAD/Apps/`. Install that package on each cart that should run it. Point the connection at the main unit's PostgreSQL. See the [acceptance checklist](../../form_builder/ACCEPTANCE.md).

[Form builder manual](index.md)
