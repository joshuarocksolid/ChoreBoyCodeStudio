# Packaging, Sharing & Installing

When your project is ready to share or deploy, ChoreBoy Code Studio can package it into an
**installable** artifact that runs on another ChoreBoy appliance. This chapter covers
packaging, what the package contains, and how it is installed.

## The packaging wizard

Start it from the toolbar **Package Project** button, or **Run > Package Project**.

![Step 1 of the packaging wizard: choosing the destination](../screenshots/200_package_wizard.png)

The wizard guides you through a short sequence:

1. **Choose Package Destination.** Pick the **Output Folder** where the package will be
   written. Choose a folder outside your live project.
2. **Review and finish.** The wizard validates the project, runs a dependency audit, and
   writes the package.

> [!IMPORTANT] Always package to a folder **outside** the project being packaged.
> Packaging into the live project would overlap inputs and outputs; the wizard's preflight
> checks catch common problems like this before they cause a confusing failure.

## What the package contains

An installable package is a self-contained folder that includes:

- your project's files and vendored dependencies,
- an **installer** plus the runtime bootstrap files,
- generated documentation,
- `package_manifest.json` describing the package,
- `package_report.json` capturing validation and dependency-audit results.

> [!NOTE] Installable is the only supported package profile. The earlier "portable"
> profile has been retired.

## Installing the package on an appliance

1. Copy the package folder onto the target machine (for example, to `/home/default/`).
2. Double-click the installer's desktop launcher.
3. The installer verifies the package, copies files into the chosen install directory,
   and can publish a Desktop shortcut for the installed application.

The installer launcher locates itself by the package folder path. If you move the package
folder before installing, the launcher's path must match the new location.

## A worked install walkthrough

To deploy a packaged project on another ChoreBoy appliance:

1. Copy the entire package folder onto the target machine (for example, to
   `/home/default/`) using a USB drive.
2. Locate the installer's desktop launcher inside the package folder. If the appliance
   requires it, mark the launcher as trusted/allowed to launch the first time.
3. Double-click the installer launcher. It first **verifies** the package contents.
4. Choose the install location. The installer copies the files and can publish a Desktop
   shortcut for the installed application.
5. Launch the installed application from its shortcut.

> [!NOTE] The installer launcher finds itself by the package folder's path. If you move
> the package folder before installing, the launcher's recorded path must match the new
> location. The *installed* application's launcher, by contrast, is fixed to the install
> directory you chose.

## Upgrades

If you install a newer version of a package that is already installed, the installer can
detect the older version and offer to clean it up or install side by side. This keeps
upgrades predictable without relying on hidden, app-owned metadata.

To upgrade:

1. Package the new version of your project (a higher version in `cbcs/package.json`).
2. Copy it to the target machine and run its installer.
3. When the installer detects the older install, choose to replace it or install side by
   side, and let it clean up the previous version if you replace it.

## What the package report tells you

After exporting, inspect `package_report.json` in the output folder. It captures the
validation results and the dependency audit, so you can confirm the package is complete
before distributing it. If validation flagged a missing entry file or a missing vendored
dependency, fix it and re-export.

## Backups and portability

Because a project is just a folder, you do not need packaging to back it up:

- Copy the whole project folder to a USB drive, or
- Zip the folder and store it somewhere safe.

Use packaging when you want a clean, installable build for another machine; use a plain
folder copy or zip for everyday backups.

> [!IMPORTANT] Keep regular backups on a USB drive. Power interruptions and accidents
> happen; your projects are your files.

## What gets written to your project

Packaging does not modify your source code. It only writes packaging metadata to
`cbcs/package.json` so the next package build can reuse your choices.

## Where to go next

- Make sure dependencies are present before packaging — see "Managing dependencies".
- Understand packaging preflight messages in "Troubleshooting by symptom".
