# 9) Packaging, Sharing, and Backup

This chapter covers how to move your work safely.

## Package a project

Use:

- `Run > Package Project...`

This creates a new export folder outside your live project.

Inside that folder you will see:

- a `.desktop` launcher file
- an `app_files/` folder with your packaged project source

The launcher starts the packaged project through the same FreeCAD AppRun runtime that Code Studio expects on ChoreBoy.

![Figure 13 — Package Project button in the main window](../screenshots/manual_13_package_project.png)

## Share projects with other users

When sharing:

1. Include the whole project folder.
2. Keep `cbcs/` metadata included.
3. Include `README.md` with basic run instructions.

For packaged exports, send the whole packaged folder, not only the `.desktop` file.

## Backup best practices

1. Back up project folders regularly (for example, to USB).
2. Keep at least two backup copies for important projects.
3. Do a quick run test after restoring from backup.

## Keep diagnostic history

Do not delete logs too aggressively.

Run logs in `cbcs/logs/` are useful when troubleshooting older issues.

## Before sending a project for help

Do this checklist:

1. Save all files.
2. Reproduce the issue once.
3. Generate a support bundle (see Chapter 10).
4. Share project + support bundle together.

## Packaging preflight

If packaging stops before export, read the Runtime Center explanation first.

Common blockers:

- missing default entry file
- entry file inside an excluded `cbcs/` path
- output folder overlapping the live project

## Where to place the launcher

To make the packaged app easy to start on ChoreBoy, place the `.desktop` file:

- on `~/Desktop/`

