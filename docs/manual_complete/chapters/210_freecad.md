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

## Export formats: what works headless

If your tool exports geometry, the format matters:

| Export | Headless? | Notes |
| --- | --- | --- |
| STL | Works | Available through the Part module without the GUI. |
| Native FreeCAD document (`.FCStd`) | Works | Create and save documents in code. |
| STEP / SVG (via GUI importers) | May fail | Exporters that depend on GUI modules fail headless with "Cannot load Gui module". |

When an export needs a GUI-only module, either use a headless-safe export path or run the
macro inside FreeCAD. Write output files to a folder inside your project so they travel
with it.

## A worked headless pattern

A reliable headless tool follows this shape:

1. `import FreeCAD` (never the GUI modules).
2. Create a document explicitly with `FreeCAD.newDocument(...)` — do not rely on
   `ActiveDocument`.
3. Build objects and call `doc.recompute()`.
4. Export with a headless-safe path, or save the `.FCStd`.
5. `print(...)` a summary so the Run Log shows what happened.

This keeps the tool fast and fully compatible with Code Studio's runner. See "Worked
Tutorial: A Headless FreeCAD Tool" for a full walkthrough.

## Why edit here but run in FreeCAD for GUI macros

Code Studio gives you a real editor — highlighting, completion (with a trusted FreeCAD API
index), linting, formatting, and version history — which the FreeCAD macro editor does not
match. FreeCAD gives you the live document and GUI context. Using both plays to each
tool's strength: author in Code Studio, execute GUI/document macros in FreeCAD.

## Completion for FreeCAD APIs

FreeCAD's API is partly backed by C++ bindings, which generic static analysis cannot fully
see. ChoreBoy Code Studio ships a trusted API index so that importing and completing
FreeCAD (and PySide2) symbols works while you write. See "Code intelligence".

## Where to go next

- Author headless tools from the template in "Projects: open, create, import".
- Understand the runtime model in Part V, "How it works".
