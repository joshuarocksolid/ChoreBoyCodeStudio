# Worked Tutorial: A Headless FreeCAD Tool

This tutorial builds a backend tool that uses the FreeCAD engine **without** a graphical
window — a "headless" tool. It is the right pattern for geometry generation, batch
processing, and automation that runs through Code Studio's runner.

Read "FreeCAD workflows & headless limits" first if you have not; this tutorial puts that
guidance into practice.

## What you will build

A script that uses `import FreeCAD` to create a simple document and a shape, then reports
what it made — all headless, with output in the Run Log.

## Step 1 — Create the project

1. **File > New Project from Template...**.
2. Choose **Headless FreeCAD Tool (headless_tool)**.
3. Name it (for example, `BoxMaker`) and choose a location.

The generated project uses FreeCAD along headless-safe paths and sets `template` to
`headless_tool` in `cbcs/project.json`.

## Step 2 — Understand the headless contract

Headless runs have no GUI and no active document:

- `import FreeCAD` works, so you can create documents and geometry in code.
- `FreeCAD.ActiveDocument` is `None`, and GUI-only operations fail.

> [!LIMITATION] Do not call GUI modules (selection, view manipulation) or GUI-only
> exporters in a headless tool. If you need those, edit here and run inside FreeCAD —
> see "FreeCAD workflows & headless limits".

## Step 3 — Write the logic

In the backend module, create a document and a shape explicitly rather than relying on an
active document. A typical headless pattern:

```python
import FreeCAD

def build():
    doc = FreeCAD.newDocument("BoxMaker")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 10
    box.Width = 20
    box.Height = 5
    doc.recompute()
    return doc
```

Save with `Ctrl+S`. As you type, completion from the trusted FreeCAD API index helps with
`FreeCAD` members (see "Code intelligence").

## Step 4 — Run it

1. Press `Shift+F5` (**Run Project**).
2. Watch the **Run Log**. Because there is no window, all feedback appears there.
3. Add `print(...)` statements to report what your tool created, then run again.

> [!TIP] Headless tools are ideal for Code Studio's runner because they start, do their
> work, print results, and exit — a clean, fast loop.

## Step 5 — Handle a headless mismatch

To see the guidance system in action, temporarily add a GUI-only call and run it. The run
fails, and Code Studio explains it as a headless/GUI mismatch rather than only showing a
raw traceback. Open **Tools > FreeCAD Headless Notes** for the full explanation, then
remove the GUI-only call.

## Step 6 — Export results the headless-safe way

Some exports work headless (for example, STL via the Part module) while GUI-dependent
exporters do not. If your tool writes output files, prefer headless-safe export paths and
write to a folder inside your project so the results travel with it.

## Step 7 — Test the logic

Headless logic is easy to test because it is just functions:

1. Add `tests/test_build.py`.
2. Assert on properties of the objects your `build()` function creates.
3. Run tests from the **Test Explorer** (`Ctrl+Shift+X`).

## Step 8 — Package and share

Package the tool with **Package Project**. Because it is headless, it runs the same way on
another appliance through the installed launcher. See "Packaging, sharing & installing".

## Where to go next

- Build a windowed app in "Worked Tutorial: Build a Windowed (Qt) App".
- Read the runtime capabilities (databases, reports) in "Appendix C — Runtime Capabilities".
