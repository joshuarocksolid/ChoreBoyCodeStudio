# CRUD Showcase — ChoreBoy Example Project

This example project demonstrates what you can build with ChoreBoy Code Studio.
Load it from **Help > Load Example Project...** and press **F5** to run.

## What it shows

### Token-Driven Theming

- Automatic **light and dark mode** detection based on system palette.
- A `ThemeTokens` dataclass drives all visual styling via a single QSS stylesheet.
- Semantic status colours (green/amber/slate) adapt to both themes.

### Modern UI Patterns

- **QPainter icons** — all toolbar and tab icons are drawn programmatically (no image assets).
- **Status badge delegate** — task statuses render as coloured pills via `QStyledItemDelegate`.
- **Empty state overlay** — a friendly prompt appears when the task list is empty.
- **Themed detail card** — selecting a task shows a styled card with title, status pill, and description.
- **Primary/ghost buttons** — dialogs use accent-filled Save and bordered Cancel buttons.
- **Inline validation** — the title field highlights red if you try to save without a title.

### SQLite CRUD

- A local `tasks.sqlite3` database is created automatically in the project folder.
- You can **create**, **read**, **update**, and **delete** task records.
- Tasks have a title, description, and status (`pending`, `in_progress`, `done`).
- The toolbar includes a **search box** and a **status filter** combo box.

### Qt Widget Showcase

This project uses the following PySide2 widgets so you can see how they work:

- `QMainWindow` — top-level window with toolbar, status bar, and central widget.
- `QToolBar` — icon + text buttons for New, Edit, Delete, Refresh, plus embedded widgets.
- `QTableWidget` — data table with alternating rows, hidden grid lines, and row hover.
- `QStyledItemDelegate` — custom cell painting for the status badge column.
- `QSplitter` — resizable split between the table and the detail panel.
- `QTabWidget` — multiple pages with tab icons (Tasks, FreeCAD Probe, About).
- `QDialog` / `QFormLayout` — modal create/edit form with validation.
- `QComboBox` — dropdown for status selection and filtering.
- `QLineEdit` — single-line text input with clear button for search and task title.
- `QTextEdit` — multi-line text input for task descriptions.
- `QTextBrowser` — themed rich text for detail view, probe results, and README rendering.
- `QStatusBar` — coloured status counts at the bottom of the window.
- `QMessageBox` — confirmation dialogs and validation warnings.
- `QPushButton` — primary (accent), ghost (border), and danger button variants.
- `QLabel` — static text labels with themed styling.

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
    main_window.py     <- Qt GUI with toolbar, table, tabs, and delegate
    repository.py      <- SQLite CRUD operations
    freecad_probe.py   <- optional FreeCAD detection
    theme.py           <- light/dark theme tokens and QSS stylesheet
    icons.py           <- QPainter-based toolbar and tab icons
  README.md            <- this file
  cbcs/
    project.json       <- project metadata
```

## How to experiment

1. Add a few tasks using **+ New Task** in the toolbar.
2. Try filtering by status or searching by keyword.
3. Double-click a row to edit it.
4. Switch to the **FreeCAD Probe** tab and press the button.
5. Look at `app/theme.py` to see how the token system and QSS work.
6. Look at `app/icons.py` to see how QPainter icons are drawn.
7. Look at `app/main_window.py` to see how the GUI is assembled.
8. Modify anything you like and press **F5** to re-run.
