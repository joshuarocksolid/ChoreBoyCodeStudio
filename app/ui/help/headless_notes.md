# FreeCAD Headless Notes

- Code Studio runs project code through the FreeCAD AppRun runtime in normal
  console/headless mode.
- That means some FreeCAD operations that depend on `FreeCADGui`,
  selection state, view state, or an already-open GUI document will not work here.
- A common symptom is:
  `Cannot load Gui module in console application`
- When you see that error, treat it as a runtime mismatch, not a mysterious crash.

## What usually works

- backend FreeCAD document creation
- geometry generation that does not require GUI modules
- scripts designed for headless-safe export or processing paths

## What often fails

- `FreeCADGui` imports
- selection/view-dependent macros
- GUI-only export helpers
- code that assumes an interactive FreeCAD window is already open

## What to do next

1. Read the `Run Log` and `Problems` panels first.
2. Open `Tools > Runtime Center...` if you want the structured explanation and next steps in one place.
3. Check whether your script depends on GUI modules or GUI state.
4. Switch to a headless-safe API path where possible.
5. If the workflow truly requires a FreeCAD GUI document, edit in Code Studio but run the script from FreeCAD instead.

## Support tip

Keep your run logs. They are useful for diagnostics and support bundle generation.
