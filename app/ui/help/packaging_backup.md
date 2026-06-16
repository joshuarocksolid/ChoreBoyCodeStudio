# Packaging, Sharing, and Backup

## What Package Project creates

`Run > Package Project...` opens a packaging wizard and creates a new export folder
outside your live project.

The supported default profile is `installable`.

An installable export contains:

- an installer launcher `.desktop` file
- `installer/bootstrap.py`
- `installer/install.py`
- `installer/launcher_bootstrap.py`
- `payload/app_files/` with the packaged project source
- `package_manifest.json` and `package_report.json`
- generated `README.txt` and `INSTALL.txt`

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
- keep the installer `.desktop`, `installer/`, `payload/`, and package manifest files together
- run the installer and choose the final install folder
- let the installer publish a Desktop shortcut and, when available, an application-menu launcher

The installer launcher uses its `.desktop` `Path=` value as the package root.
If the exported folder is moved after packaging, regenerate the package or update
`Path=` before launching. After install, project packages launch from the
installed `app_files/` folder so project-relative imports and resources still work.

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
