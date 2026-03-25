# 10) Troubleshooting

Use this chapter when something does not work as expected.

## First checks (always do these)

1. Read the **Run Log** tab.
2. Check the **Problems** panel.
3. Look at startup status in the status bar.
4. Open `Tools > Runtime Center...`.
5. Run `Tools > Project Health Check` if you need fresh project-specific checks.

![Figure 14 — Tools menu with Project Health Check command](../screenshots/manual_14_project_health_check.png)

## Problem: project will not open

Likely causes:

- selected folder is not a valid/importable project,
- metadata file is invalid.

Fix:

1. Open a folder that contains Python files.
2. If needed, create/open with `File > New Project...`.
3. Check error message details in popup/log.

## Problem: run fails immediately

Likely causes:

- syntax/runtime error in file,
- wrong entry file.

Fix:

1. Open Problems panel.
2. Jump to first traceback line.
3. Fix and save.
4. Run again.

## Problem: entry file is missing

If the default entry file or a named run configuration points at a file that no longer exists, Code Studio now blocks the launch before the runner starts.

Fix:

1. Read the run preflight explanation in Runtime Center.
2. Update the project entry or run configuration to point at a real `.py` file.
3. Run project again.

## Problem: debug does not pause at breakpoints

Likely causes:

- breakpoint on non-executable line,
- unsaved file,
- debugging different file than expected.

Fix:

1. Save file first.
2. Move breakpoint to executable code.
3. Confirm active file vs project debug mode.
4. If still not pausing, use normal run + Run Log + Problems for diagnosis.

## Problem: FreeCAD macro needs document or Gui

Symptom:

- `FreeCAD.ActiveDocument` is `None` when running from Code Studio.
- Script fails with errors related to selection, view, or GUI operations.

Meaning:

Code Studio runs scripts headless. There is no open FreeCAD document or GUI context.

Fix:

1. Edit and save your macro in Code Studio (syntax highlighting and linting remain useful).
2. Run the macro inside FreeCAD (Macro > Macros or your usual macro launcher).
3. Use FreeCAD for execution and debugging; use Code Studio for editing.

## Problem: FreeCAD GUI module error in run

Symptom:

`Cannot load Gui module in console application`

Meaning:

Your script hit a GUI-only FreeCAD path in a headless run context.

Fix:

1. Open `Tools > FreeCAD Headless Notes`.
2. Open `Tools > Runtime Center...` if you want the structured explanation and next steps in one place.
3. Use headless-safe API path where possible.
4. Retest.

## Problem: uncertain environment state

Fix:

1. Run `Tools > Project Health Check`.
2. Review the issues in Runtime Center.
3. Apply the suggested correction.
4. Re-run the check.

## Generate support bundle

When you need help from another person:

1. Open project.
2. Use `Tools > Generate Support Bundle`.
3. Share generated bundle and project folder.

The support bundle now includes both `project_health.json` and a runtime explanation snapshot so another person can see the same issue summaries you saw in the app.

![Figure 15 — Tools menu with Generate Support Bundle command](../screenshots/manual_15_support_bundle.png)

