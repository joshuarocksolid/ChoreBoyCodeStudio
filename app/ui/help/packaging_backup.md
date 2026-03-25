# Packaging, Sharing, and Backup

## What Package Project creates

`Run > Package Project...` creates a new export folder outside your live project.

Inside that folder you will see:

- a `.desktop` launcher file
- an `app_files/` folder with the packaged project source

The launcher is wired to start the packaged project through the FreeCAD AppRun runtime.

## What gets left out

Packaging intentionally skips temporary and support data such as:

- `cbcs/runs/`
- `cbcs/logs/`
- `cbcs/cache/`
- `__pycache__/`
- `.pyc` files

If your entry file points into one of those excluded paths, packaging will stop before export.

## Where to put the result on ChoreBoy

You can copy the packaged folder to a shared location or USB drive.

To make a launcher shortcut available on ChoreBoy, place the `.desktop` file:

- on `~/Desktop/`

Keep the `.desktop` file next to the packaged folder contents so the relative launcher path stays valid.

## Before packaging

1. Make sure the project default entry file exists.
2. Choose an output folder outside the live project.
3. Re-run packaging after fixing any preflight warnings.

## Before sending work for help

If packaging is failing or the exported app does not run as expected:

1. Reproduce the issue once.
2. Open Runtime Center for the structured explanation.
3. Generate a support bundle.
4. Share the project and support bundle together.
