# How It Works

This chapter explains, in plain language, how ChoreBoy Code Studio works under the hood
and why it is built the way it is. You do not need this to use the application, but it
makes many behaviors and limitations make sense.

## The ChoreBoy environment

ChoreBoy is a locked-down appliance. Compared with an ordinary computer:

- You cannot install software from the internet, and there is no app store.
- There is no terminal or command prompt for users.
- Writable storage is restricted, and some security policies block running arbitrary
  programs.

ChoreBoy Code Studio is designed to deliver a real developer experience *within* these
limits. Almost every design choice — and several limitations noted throughout this manual
— traces back to working within the ChoreBoy environment.

## It runs inside FreeCAD's Python

ChoreBoy ships with FreeCAD, and FreeCAD includes a complete Python runtime and the Qt
user-interface toolkit (PySide2). ChoreBoy Code Studio runs inside that bundled runtime.
That is why:

- no separate installation of Python is needed,
- your code can `import FreeCAD` for headless geometry work,
- the editor and your programs all use the same Python version that ships on the
  appliance.

## The editor and the runner are separate processes

This is the most important idea in the product. The **editor** (the window you work in)
and the **runner** (where your program executes) are two different operating-system
processes.

When you press Run:

1. The editor writes a small **run manifest** describing exactly what to run.
2. The editor launches a fresh runner process for that manifest.
3. The runner executes your code and streams its output back to the Run Log.
4. The runner exits; the editor records the result.

Why this matters:

- **Crash isolation.** If your code crashes or loops forever, only the runner is
  affected. The editor stays alive and responsive.
- **Clean output.** Your program's output is captured cleanly and saved to a per-run log.
- **Control.** Stopping a run simply terminates the runner process and its children.

The **Python Console** and **debug** sessions use the same model: they run in separate
processes and communicate with the editor over well-defined channels.

## Files are the source of truth

ChoreBoy Code Studio deliberately stores everything as plain, visible files: your code,
project metadata (`cbcs/project.json`), settings (JSON), run manifests, and logs. There is
no hidden, proprietary database holding your project together.

Benefits:

- You can copy, zip, back up, and inspect everything with ordinary tools.
- Support is easier, because a Support Bundle is just files.
- The application can recover gracefully if an index or cache is missing — those are only
  accelerators, never the source of truth.

## Capability probing

Because the environment can vary, the editor checks what the runtime supports at startup
(the "capability check" reflected in the status bar) instead of assuming. When something
is missing, it tells you clearly rather than failing in a confusing way. The Runtime
Center turns those checks into plain-language explanations.

## Acceleration vs truth

Several features have a fast "acceleration" layer and a trustworthy "truth" layer, kept
separate on purpose:

- **Syntax highlighting** and a **symbol index** make the editor fast.
- **Semantic analysis** (for go-to-definition, references, and rename) is the trustworthy
  layer. It never silently presents a guess as a fact; approximate results are labeled.

If an accelerator (like the symbol index) is stale or missing, the editor still works —
it just rebuilds when convenient.

## The run lifecycle in detail

When you press Run, the steps are:

1. The editor resolves the **entry file** and the active **run configuration** (argv,
   working directory, environment).
2. It writes a **run manifest** (a JSON file under `cbcs/runs/`) describing exactly how to
   run.
3. It launches a fresh **runner process** for that manifest, in its own session so its
   children can be cleaned up together.
4. The runner sets up the path, executes your entry file, and streams stdout/stderr back
   to the **Run Log** while also writing a saved per-run log.
5. On exit, the runner returns an exit code; the editor records the final state
   (finished, failed, terminated).

Because everything is described by a manifest and captured in logs, runs are reproducible
and easy to support — and stopping a run simply terminates that runner process group.

## What happens when you save

A save writes the buffer to disk, clears the modified marker, records a **Local History
checkpoint**, and (if enabled) runs format/organize-imports. Crucially, your text is
written even if a style step fails — save reliability outranks style automation.

## Acceleration vs truth (why results are sometimes labeled)

You may notice the editor labels some results as "approximate." That is deliberate: fast
accelerators (syntax highlighting, the symbol index) make the editor responsive, while a
separate semantic layer provides trustworthy go-to-definition, references, and rename. The
editor never presents a fast guess as a proven fact — if it cannot be sure, it says so.

## Safety by design

- Editing features never execute your project code inside the editor process.
- Recovery flows restore into the editor buffer first, never silently overwriting files.
- Plugins run in a separate host process, isolated from the editor.

## Why the separate runner is worth it

Running your code in the same process as the editor would be simpler to build, but it
would mean that any infinite loop, crash, or memory blow-up in your program could freeze
or kill the editor — losing your unsaved work and your place. By spending a little
complexity on a separate runner process, the application guarantees the editor stays alive
and responsive no matter what your code does. That trade is the foundation of the product's
reliability.

## Files you can safely inspect and back up

Because everything is plain files, you can confidently:

- copy a whole project folder to USB as a backup;
- zip a project to share it;
- open `cbcs/project.json`, settings JSON, and logs in any text viewer;
- inspect a Support Bundle's contents before sharing it.

Nothing important is hidden in a proprietary format, which is exactly what makes the
application supportable on a locked-down appliance.

## A note on versions and migration

Project metadata, run manifests, settings, and package manifests carry **schema
versions**. If a future release changes a format, the application migrates older data in a
controlled, logged way rather than breaking it — so your existing projects keep working.

## Where to go next

- See the concrete files this produces in "File & folder reference".
- Read the runtime facts that shaped these choices in the project's `docs/DISCOVERY.md`.
