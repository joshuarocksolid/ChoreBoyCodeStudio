# Packaging, Sharing, and Backup

## What Package Project creates

`Run > Package Project...` opens a packaging wizard and creates a new export folder
outside your live project.

The supported default profile is `installable`.

An installable export contains:

- an installer launcher `.desktop` file
- `installer/install.py`
- `payload/app_files/` with the packaged project source
- `package_manifest.json` and `package_report.json`
- generated `README.txt` and `INSTALL.txt`

Portable export is still available, but it depends on the `.desktop` file staying
in the same folder as the packaged files.

## What gets left out

Packaging intentionally skips temporary and support data such as:

- `cbcs/runs/`
- `cbcs/logs/`
- `cbcs/cache/`
- `__pycache__/`
- hidden dot-folders such as `.git/`
- `.pyc` files

If your entry file or icon points into one of those excluded paths, packaging stops before export.

## Validation before export

The wizard runs:

- package metadata checks from `cbcs/package.json`
- packaging preflight for entry file and output-path safety
- dependency audit against project files, `vendor/`, and the AppRun runtime

The generated `package_report.json` records those results.

## Where to put the result on ChoreBoy

For installable exports:

- copy the whole exported folder to `/home/default/`
- keep the installer `.desktop`, `installer/`, and `payload/` together
- run the installer and choose the final install folder
- let the installer publish an application-menu launcher and optional Desktop shortcut

For portable exports:

- keep the `.desktop` file in the export root
- move/copy the whole folder together
- if portable launch fails on the target desktop, re-export as `installable`

## Before packaging

1. Make sure the project default entry file exists.
2. Choose an output folder outside the live project.
3. Review `cbcs/package.json` metadata such as package ID, version, and description.
4. Re-run packaging after fixing any blocking validation issues.

## Before sending work for help

If packaging is failing or the exported app does not run as expected:

1. Reproduce the issue once.
2. Open Runtime Center or inspect `package_report.json` for the structured explanation.
3. Generate a support bundle.
4. Share the project, exported package, and support bundle together.
