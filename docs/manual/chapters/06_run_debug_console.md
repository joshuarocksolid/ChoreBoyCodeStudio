# 6) Run, Debug, and Python Console

This chapter explains how to execute and investigate your code.

## Run modes at a glance

- **Run Active File** (`F5`): runs the file in the active editor tab.
- **Run Project** (`Shift+F5`): runs the configured project entry file.
- **Debug Active File** (`Ctrl+F5`): starts debug flow for active file.
- **Debug Project** (`Ctrl+Shift+F5`): debug run for project entry file.

## Basic run workflow

1. Save the file (`Ctrl+S`).
2. Press `F5`.
3. Watch **Run Log**.
4. If errors appear, open **Problems** and jump to issue lines.

![Figure 10 — Run toolbar and bottom panels](../screenshots/manual_10_run_toolbar_panels.png)

## Debug workflow (explicit step-by-step)

### Step 1 — Set breakpoints

Click in the editor gutter next to a line number.
A marker appears for that line.

### Step 2 — Start debug

Use `Ctrl+F5` for active file, or `Ctrl+Shift+F5` for project entry.

### Step 3 — Use Debug panel

Open the **Debug** bottom tab and use:

- Continue (`F6`)
- Pause (`Ctrl+F6`)
- Step Over (`F10`)
- Step Into (`F11`)
- Step Out (`Shift+F11`)

You can also inspect stack and variable info in the panel.

### Step 4 — Stop debugging

Use **Stop** when done or when execution is stuck.

## Important debug notes

Debug behavior depends on runtime conditions.
If breakpoints do not pause where expected:

1. Confirm breakpoint is on executable code (not blank/comment line).
2. Save file before starting debug.
3. Confirm you started the correct mode (Active File vs Project).
4. Use Run Log + Problems as fallback diagnosis path.

In other words: if stepping is not acting as expected, you can still diagnose most issues quickly with a normal run and traceback.

## Python Console (REPL)

Use the **Python Console** tab for quick experiments.

Examples:

```python
x = 2
print(x + 3)
```

You can run short snippets, test expressions, and inspect values without changing files first.

## When to use each tool

- Use **Run** for normal development.
- Use **Debug** when you need step-by-step control.
- Use **Python Console** for quick experiments and checks.

## FreeCAD macro workflow

For FreeCAD macros that need an open document (`FreeCAD.ActiveDocument`) or the GUI (selection, view manipulation, etc.):

- **Recommended workflow**: Edit and save in Code Studio, then run the macro inside FreeCAD.
- Code Studio provides syntax highlighting, linting, and editing. FreeCAD provides the document and GUI context needed for execution and debugging.
- Code Studio Run/Debug runs scripts headless. `FreeCAD.ActiveDocument` is `None` and GUI operations fail, so it is suitable for headless scripts and utilities only.

