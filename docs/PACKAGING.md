# ChoreBoy Code Studio Packaging and Installer Workflow

## Purpose

This document explains the **ChoreBoy-specific** packaging and installation flow for
**ChoreBoy Code Studio itself**.

This is intentionally different from a generic Linux desktop app install.
ChoreBoy Code Studio targets the locked-down ChoreBoy environment, so the installer
and launcher behavior are designed around that reality.

## Two different "packaging" flows in this repo

There are two separate concepts that are easy to confuse:

1. **Product distribution packaging** — packaging **ChoreBoy Code Studio itself**
   so it can be copied to a ChoreBoy and installed.
   - entrypoints/files:
     - `package.py`
     - `packaging/install.py`

2. **In-app project packaging** — packaging a **user project created inside Code Studio**
   for export/share.
   - entrypoint/file:
     - `app/packaging/packager.py`

When this document says **installer** or **package**, it refers to the first flow:
shipping Code Studio itself.

## Distribution packaging flow

### Developer-side build

On the development machine, run:

```bash
python3 package.py
```

This produces:

- `dist/ChoreBoyCodeStudio-v<version>/`
- `dist/ChoreBoyCodeStudio-v<version>.zip`

The `.zip` archive is the email/distribution artifact. It is intentionally:

- password protected
- compressed
- enforced to stay at or below **15 MB**

The staging directory contains:

- `install_choreboy_code_studio.desktop`
- `installer/install.py`
- `payload/` with the application files to copy
- `INSTALL.txt`

## ChoreBoy user install contract

The supported install workflow is:

1. Copy the entire packaged folder into **`/home/default/`** on the ChoreBoy.
2. Keep the folder contents together.
   - Do **not** separate `install_choreboy_code_studio.desktop` from the rest of the installer folder.
   - The installer launcher locates `installer/install.py` relative to its own file location.
3. Launch `install_choreboy_code_studio.desktop` from that copied folder.
4. In the installer wizard, choose the **final install directory** where the Code Studio files should live.
5. The installer copies `payload/` into that chosen location.
6. The installer writes:
   - the application-menu entry in `~/.local/share/applications/`
   - and optionally a Desktop shortcut

## Important launcher behavior

The **installed** launcher is expected to **hardcode the chosen final install directory**.

That is deliberate.

Why:

- ChoreBoy is a known, constrained target environment.
- The installer’s job is to turn a copied staging folder into a stable installed app.
- The installed launcher should point at the exact chosen location for the app files.

### Consequence

If the installed Code Studio folder is moved later, the launcher will point at the old path.

The supported recovery is:

- **rerun the installer** and choose the new location

## Why `/home/default/` matters

On ChoreBoy, `/home/default/` is the normal user-home location and the expected place for
copied USB-delivered installer folders.

The distribution package is designed around that workflow:

- copy package into `/home/default/`
- run installer from there
- choose final app location

This is not meant to be a fully relocatable, arbitrary-folder, arbitrary-shortcut install model.

## Source of truth in code

### Installer package launcher

`package.py` generates `install_choreboy_code_studio.desktop`.

That launcher uses the launcher file’s location to find the bundled installer code:

- relative launcher lookup is correct **for the copied installer package**
- this is why the copied installer folder must stay intact

### Installed app launcher

`packaging/install.py` writes the installed `.desktop` entry.

That launcher:

- hardcodes the final chosen install directory
- launches `run_editor.py` from that exact location

### Archive size gate

`package.py` also acts as the release gate for the emailed installer archive:

- it creates a compressed `.zip`
- it measures the finished archive size
- it fails packaging if the archive exceeds **15 MB**

This is why the default vendored tree-sitter bundle stays Python-first and does
not ship every optional grammar offline by default.

## Developer guidance

When changing packaging/install behavior:

- do not describe the installer as a generic relocatable Linux app installer
- preserve the distinction between:
  - installer package location
  - final installed app location
- keep user-facing copy explicit about `/home/default/`
- keep user-facing copy explicit that the installed launcher hardcodes the chosen final path
- preserve the compressed archive + 15 MB budget contract unless the product distribution strategy changes
- if future work changes this contract, update:
  - `package.py`
  - `packaging/install.py`
  - `INSTALL.txt` generation
  - `vendor/README.md`
  - this document

## Summary

The supported mental model is:

- **Installer package**: copied into `/home/default/`, kept together, launched from there
- **Installed app**: copied wherever the user chooses, with launcher hardcoded to that chosen path

That is the intended ChoreBoy-specific packaging contract.
