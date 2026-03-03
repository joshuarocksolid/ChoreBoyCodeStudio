# CRUD Showcase — ChoreBoy Example Project

This example project demonstrates what you can build with ChoreBoy Code Studio.
Load it from **Help > Load Example Project...** and press **F5** to run.

## What it shows

### SQLite CRUD

- A local `tasks.sqlite3` database is created automatically in the project folder.
- You can **create**, **read**, **update**, and **delete** task records.
- Tasks have a title, description, and status (`pending`, `in_progress`, `done`).
- The toolbar includes a **search box** and a **status filter** combo box.

### Qt Widget Showcase

This project uses the following PySide2 widgets so you can see how they work:

- `QMainWindow` — top-level window with toolbar, status bar, and central widget.
- `QToolBar` — buttons for New, Edit, Delete, Refresh, plus embedded widgets.
- `QTableWidget` — data table with column headers and row selection.
- `QSplitter` — resizable split between the table and the detail panel.
- `QTabWidget` — multiple pages (Tasks, FreeCAD Probe, About).
- `QDialog` / `QFormLayout` — modal create/edit form with validation.
- `QComboBox` — dropdown for status selection and filtering.
- `QLineEdit` — single-line text input for search and task title.
- `QTextEdit` — multi-line text input for task descriptions.
- `QTextBrowser` — read-only rich text for detail view and probe results.
- `QStatusBar` — live task counts at the bottom of the window.
- `QMessageBox` — confirmation dialogs and validation warnings.
- `QPushButton` — standard clickable buttons.
- `QLabel` — static text labels.

### FreeCAD Integration (Optional)

The **FreeCAD Probe** tab safely checks whether FreeCAD is available in the
current runtime.  If it is, it displays the version and attempts to create a
headless `Part::Box` object.  If FreeCAD is not installed, you see a clear
fallback message — no crash.

This demonstrates the recommended pattern for optional FreeCAD features:
try the import, catch `ImportError`, and degrade gracefully.

## Project structure

```
crud_showcase/
  main.py              <- entry point (run this)
  app/
    __init__.py
    main_window.py     <- Qt GUI with toolbar, table, tabs
    repository.py      <- SQLite CRUD operations
    freecad_probe.py   <- optional FreeCAD detection
  README.md            <- this file
  .cbcs/
    project.json       <- project metadata
```

## How to experiment

1. Add a few tasks using **+ New Task** in the toolbar.
2. Try filtering by status or searching by keyword.
3. Double-click a row to edit it.
4. Switch to the **FreeCAD Probe** tab and press the button.
5. Look at `app/repository.py` to see how SQLite is used.
6. Look at `app/main_window.py` to see how the GUI is assembled.
7. Modify anything you like and press **F5** to re-run.
