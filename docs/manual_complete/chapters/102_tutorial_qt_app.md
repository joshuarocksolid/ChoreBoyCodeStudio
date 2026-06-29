# Worked Tutorial: Build a Windowed (Qt) App

This tutorial walks through building a small windowed application from the **Qt App**
template, end to end: create, explore, edit, run, debug, test, and package. It ties
together the individual features covered in earlier chapters into one realistic workflow.

> [!NOTE] This is a learning-oriented tutorial. For reference details on any single step,
> follow the cross-references to the feature chapters.

## What you will build

A small Qt window with a button and a label. Clicking the button updates the label. Along
the way you will use the editor, the runner, the debugger, the Python Console, and the
packaging wizard — the full development loop.

## Step 1 — Create the project

1. Choose **File > New Project from Template...**.
2. In the **Template:** dropdown, choose **Qt App (qt_app)**.
3. Click **OK**, name the project (for example, `HelloQt`), and choose a location.

The project opens automatically. See "Projects: open, create, import" for the full New
Project flow.

## Step 2 — Explore the generated structure

Open the files in the **Explorer**. A Qt App project typically contains:

- a top-level entry file (`main.py`) that creates the `QApplication`, applies a
  stylesheet, builds the main window, and starts the Qt event loop;
- an `app/` package with the window and supporting modules;
- `cbcs/project.json` with `template` set to `qt_app` and `default_entry` set to
  `main.py`;
- a `README.md` describing how to run it.

Open `main.py` and read it. Notice the shape of a Qt program:

```python
from PySide2.QtWidgets import QApplication

def main():
    app = QApplication.instance() or QApplication(sys.argv)
    # ... build and show the window ...
    return app.exec_()
```

> [!NOTE] `app.exec_()` starts the Qt event loop, which runs until the window closes. That
> is why a windowed program stays "running" in Code Studio until you close its window or
> press **Stop**.

## Step 3 — Run it for the first time

1. Press `Shift+F5` (**Run Project**).
2. The **Run Log** shows the run starting, and your window opens as a separate window.
3. Interact with the window, then close it (or press **Stop**, `Shift+F2`).

See "Running code" for the full run model.

## Step 4 — Make a change

Open the window module under `app/` and find where the UI is built. Add a label and a
button, and connect the button to a handler that updates the label. Save with `Ctrl+S`,
then run again (`Shift+F5`) to see your change.

> [!TIP] Use code completion (`Ctrl+Space`) as you type Qt calls — the editor ships a
> trusted PySide2 API index so member completion works even though Qt is C++-backed. See
> "Code intelligence".

## Step 5 — Debug a problem

Suppose the label does not update. Investigate with the debugger:

1. Click the gutter next to the line inside your button handler to set a breakpoint
   (`F9`).
2. Press `Ctrl+Shift+F5` (**Debug Project**).
3. Click the button in your running window — execution pauses at the breakpoint.
4. Open the **Debug** panel and inspect the local variables and call stack.
5. Use **Step Over** (`F10`) to advance line by line, then **Continue** (`F6`).

See "Debugging" for the full debugger reference, including the fallback workflow if
pausing is not available in your environment.

## Step 6 — Experiment in the Python Console

Use the **Python Console** to try a Qt expression without editing the file. For example,
create a `QLabel` and check its default text. Because the console runs in a separate
process, nothing you try there can destabilize the editor. See "The Python Console".

## Step 7 — Add a test

1. Create a `tests/` folder and a `test_logic.py` file.
2. Write a test for any non-UI logic your app contains (UI itself is best validated by
   running the app).
3. Open the **Test Explorer** (`Ctrl+Shift+X`) and run your tests.

See "The testing workflow" for discovery and run scopes.

## Step 8 — Format and lint

1. Run **Tools > Format Current File** to apply Black formatting.
2. Run **Tools > Organize Imports** to sort imports.
3. Check the **Problems** panel for any diagnostics and fix them.

See "Python formatting & imports" and "Linting & the Problems panel".

## Step 9 — Package it

1. Click **Package Project** (toolbar) or **Run > Package Project**.
2. Choose an output folder **outside** the project.
3. Finish the wizard to produce an installable package.

See "Packaging, sharing & installing" for the install/upgrade story.

## What you practiced

You used the entire development loop: template creation, editing with intelligence,
running, debugging, the console, testing, formatting, linting, and packaging — exactly the
workflow you will repeat for real projects.

## Where to go next

- Build a non-windowed tool in "Worked Tutorial: A Headless FreeCAD Tool".
- Build a simple script in "Worked Tutorial: A Utility Script".
