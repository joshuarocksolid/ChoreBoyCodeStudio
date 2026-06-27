# FreeCAD Workflows & Headless Limits

ChoreBoy Code Studio runs inside FreeCAD's bundled Python, which means your projects can
use the FreeCAD engine. This chapter explains what works, what does not, and the
recommended workflow for FreeCAD code.

## What you can do

- `import FreeCAD` works in your runs, so you can create and manipulate FreeCAD documents
  and geometry programmatically (a "headless" backend).
- The **Headless FreeCAD Tool** template gives you a starting point that uses FreeCAD
  along headless-safe paths.

## The headless limitation

Runs and debugging in ChoreBoy Code Studio execute **headless** — there is no FreeCAD
GUI and no active document attached to your run.

> [!LIMITATION] Code that needs the FreeCAD **GUI** or an open document will not work in a
> headless run. Specifically:
>
> - `FreeCAD.ActiveDocument` is `None` in a headless run.
> - GUI-dependent operations (selection, view manipulation, and some exporters that rely
>   on GUI modules) fail with errors such as "Cannot load Gui module in console
>   application."

This is a property of the runtime, not a bug. Some FreeCAD export formats (for example,
STL via the Part module) work headless, while others that depend on GUI modules do not.

## When a headless mismatch happens

If you run code that hits a GUI-only path, ChoreBoy Code Studio explains the failure as a
headless/GUI mismatch rather than just dumping a raw traceback, and links to guidance. You
can open this guidance any time from **Tools > FreeCAD Headless Notes**.

## The recommended workflow

For macros that need an open document or the GUI:

1. **Write and edit** the macro in ChoreBoy Code Studio. You get syntax highlighting,
   completion (including a trusted FreeCAD API index), linting, and formatting.
2. **Run it inside FreeCAD itself**, where the document and GUI context exist.

In other words, use Code Studio as the authoring environment and FreeCAD as the execution
environment for GUI/document-dependent macros. Use Code Studio's own Run/Debug for
headless scripts, utilities, and backend geometry generation.

## Completion for FreeCAD APIs

FreeCAD's API is partly backed by C++ bindings, which generic static analysis cannot fully
see. ChoreBoy Code Studio ships a trusted API index so that importing and completing
FreeCAD (and PySide2) symbols works while you write. See "Code intelligence".

## Where to go next

- Author headless tools from the template in "Projects: open, create, import".
- Understand the runtime model in Part V, "How it works".
