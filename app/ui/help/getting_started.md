# Getting Started

ChoreBoy Code Studio is a simple editor for Python projects.
It is built for machines with limits, so it focuses on the basics that matter most:
open a project, edit files, save work, and run code safely.

When you run code, the app uses a separate runner process.
That means your script can fail without taking down the editor window.
For hobby projects, this makes trial and error much safer.

## First 10 Minutes

1. Check startup status.
   Look at the bottom status bar.
   If you see `Startup: Runtime ready (x/y checks)`, you are good to go.
   If you see `Startup: Runtime issues (x/y checks)`, you can still keep going, but run `Tools > Project Health Check` soon.

2. Create or open a project.
   - New project: `File > New Project...`
   - Existing project folder: `File > Open Project...`

3. Open `main.py`.
   In the project tree, click `main.py`.
   If your project does not have one yet, create it and use that as your first entry file.

4. Add one simple test line.
   Try:
   `print("Hello from ChoreBoy Code Studio")`

5. Save your file.
   Press `Ctrl+S` or use `File > Save`.
   Get in the habit of saving before each run.

6. Run the project.
   Press `F5` or use `Run > Run`.
   The run starts in a separate process.

7. Read the output.
   Open the `Run Log` tab at the bottom.
   This tab shows normal output, errors, and traceback details from your latest run.

8. Stop when needed.
   If a script keeps running, press `Shift+F5` or use `Run > Stop`.

9. Fix issues quickly.
   Open the `Problems` tab.
   It summarizes errors and warnings, and helps you jump to the right file.

10. Run again.
    Edit, save, run, check `Run Log`, repeat.
    This short cycle is the fastest way to make progress.

## Pick a Starter Template

If you are creating a new project, pick the simplest template that fits your goal:

- `Utility Script`
  Best for quick automation, data cleanup, and first experiments.
  Start here if you are unsure.

- `Qt App`
  Best when you want a window, buttons, and forms.
  Use this for desktop-style tools.

- `Headless FreeCAD Tool`
  Best for FreeCAD backend work without GUI dependencies.
  Use this when your code should run in console/headless mode.

You can always start with a simple template and move to a bigger one later.

## When Something Goes Wrong

Start with these checks, in this order:

1. `Run Log` tab
   Read the latest output and traceback.
   Most run failures are explained here.

2. `Problems` tab
   Look for syntax and runtime issue summaries.

3. Startup status in the bottom bar
   If runtime checks failed, that can explain import or run errors.

4. `Tools > Project Health Check`
   This gives actionable checks for project setup issues.

5. `Tools > Generate Support Bundle`
   Use this when you need to share diagnostics with someone helping you.

## Important Headless Note

Some FreeCAD features require GUI modules and do not work in console/headless runs.
If you see an error like `Cannot load Gui module in console application`, your code likely hit a GUI-only path.

Open `Tools > FreeCAD Headless Notes` for safe guidance.

## Keep Your Work Safe

- Your projects are normal folders on disk.
- Save often with `Ctrl+S`.
- Use `Ctrl+Shift+S` for `Save All` when multiple files are open.
- Back up project folders to USB regularly.
- Per-run logs are stored in your project under `.cbcs/logs`, which is useful for debugging later.

## Shortcuts to Remember

- `F5` Run
- `Shift+F5` Stop
- `Ctrl+S` Save
- `Ctrl+Shift+S` Save All
- `Ctrl+O` Open Project
- `Ctrl+P` Quick Open

## Good Next Step

Build one small tool you can use right away.
Keep the loop simple: edit -> save -> run -> check `Run Log` -> improve.
Small wins are the fastest path to bigger projects.
