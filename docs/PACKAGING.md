# Packaging and Distribution Contract

## Purpose

This document defines the supported packaging contract for both:

1. distributing **ChoreBoy Code Studio itself**
2. exporting **user projects packaged from inside Code Studio**

The goal is not generic Linux packaging. The goal is a reliable, AppRun-native,
offline-first distribution model that fits ChoreBoy's real constraints:

- the guaranteed runtime is `/opt/freecad/AppRun`
- writable locations may be `noexec`
- hidden folders are unreliable for project/app-owned state
- users should not need a terminal

## Supported Profiles

Two profiles exist in the shared packaging substrate:

1. `installable`
2. `portable`

`installable` is the supported default.

`portable` remains a stricter, decision-gated profile:

- it relies on the `.desktop` file staying beside the packaged files
- it does not publish menu/Desktop launchers automatically
- when portability is more important than convenience, it is acceptable
- when reliability and upgrades matter most, use `installable`

## Shared Metadata Contract

### Project-side metadata

Project packaging metadata lives in:

- `cbcs/package.json`

This is intentionally separate from:

- `cbcs/project.json`

`cbcs/project.json` remains the runtime/editor project manifest.
`cbcs/package.json` stores packaging-specific data such as:

- `package_id`
- `display_name`
- `version`
- `description`
- packaging entry-file override
- optional icon path

### Exported artifact metadata

Every exported package writes:

- `package_manifest.json`
- `package_report.json`
- `README.txt`
- `INSTALL.txt`

`package_manifest.json` is the machine-readable source of truth for:

- package kind (`product` or `project`)
- profile (`installable` or `portable`)
- stable `package_id`
- version and display name
- launcher contract
- entry-file path inside the installed/package root
- checksum list for artifact verification

`package_report.json` captures editor-side validation/audit output for supportability.

### Installed package marker

Installable packages write a visible install marker into the final install root:

- `cbcs_installed_package.json`

This marker exists so later installs can detect older versions of the same package
without relying on hidden cache or registry directories owned by Code Studio.

## Shared Artifact Layout

### Installable packages

Installable packages use a shared folder layout:

```text
<package_root>/
  install_<name>.desktop
  installer/
    install.py
  payload/
    ...
  package_manifest.json
  package_report.json
  README.txt
  INSTALL.txt
```

For project exports, `payload/` contains:

- `app_files/` with packaged project files

For the product installer, `payload/` contains:

- the application files for Code Studio itself

### Portable packages

Portable packages use:

```text
<package_root>/
  <name>.desktop
  app_files/
    ...
  package_manifest.json
  package_report.json
  README.txt
  INSTALL.txt
```

## Installer Contract

The shared standalone installer is:

- `packaging/install.py`

It is copied into installable package artifacts and runs on the target through AppRun.

The installer must:

- load `package_manifest.json`
- verify checksums before copying files
- perform a staged copy before switching the final install directory
- write the installed launcher into the final install root
- optionally publish an application-menu launcher
- optionally publish a Desktop shortcut
- detect older installs of the same `package_id`
- allow side-by-side installs and optional cleanup of older versions

The installed launcher is expected to hardcode the chosen final install directory.

That is deliberate. If the installed folder moves later, the supported recovery path is:

- rerun the installer so the launcher points at the new location

## Product Distribution Flow

Developer-side build entrypoint:

- `package.py`

`package.py` is intentionally thin: it prompts for the release version and delegates
to `app.packaging.product_builder.build_product_artifact(...)`. The shared
installable artifact layout is written by `app.packaging.artifact_builder`, while
`product_builder` owns product-specific payload selection, vendor staging, cp39
tree-sitter validation, archive creation, and budget enforcement.

Supported behavior:

1. build a manifest-driven installable package for Code Studio itself
2. produce a staging directory under:
   - `CBCS_ARTIFACTS_DIR/dist/choreboy_code_studio_installer_v<version>/`
3. produce a compressed password-protected archive:
   - `CBCS_ARTIFACTS_DIR/dist/choreboy_code_studio_installer_v<version>.zip`
4. enforce the product archive budget:
   - **15 MB maximum**

Product release archives no longer have a built-in password fallback. Release
builders must pass `archive_password` to `build_product_artifact(...)` or set
`CBCS_PACKAGE_ZIP_PASSWORD`; otherwise archive creation fails with an explicit
configuration error. This keeps release credentials out of source defaults.

During staging, the product builder auto-fetches the cp39 manylinux `tree-sitter`
wheel and overlays `_binding.cpython-39-x86_64-linux-gnu.so` onto
`payload/vendor/tree_sitter/`. The wheel is cached under
`CBCS_ARTIFACTS_DIR/vendor_cp39_cache/` so subsequent builds are
offline-friendly. This keeps the product bundle on the cp39 contract even
when the local artifacts vendor was populated for Cloud-dev (cp311) use.

The product archive budget applies to Code Studio distribution only.
It does **not** define the size budget for user-project packages.

## In-App Project Packaging Flow

Editor entrypoint:

- `Run > Package Project...`

Supported behavior:

1. open a packaging wizard
2. select `installable` or `portable`
3. review/edit `cbcs/package.json` metadata
4. run validation + dependency audit
5. export a manifest-driven artifact
6. show the resulting package/report paths

Validation covers:

- entry-file safety
- output overlap with the live project
- hidden/excluded paths
- package metadata completeness
- dependency audit against project files, `vendor/`, and AppRun
- direct subprocess assumptions that are likely unsafe on ChoreBoy
- `shell=True` subprocess calls, which are blocked by the dependency audit

Packaging excludes transient/support content such as:

- `cbcs/runs/`
- `cbcs/logs/`
- `cbcs/cache/`
- `__pycache__/`
- hidden dot-folders
- `.pyc` files

## Launcher Rules

### Installable launcher rule

Installed launchers:

- use direct AppRun bootstrap
- do not use `/bin/sh`
- hardcode the final chosen install directory

### Portable launcher rule

Portable launchers:

- use a spec-compliant `/bin/sh -c ... %k` wrapper to pass launcher location into AppRun
- pass `%k` as a separate desktop-file argument
- resolve package root from the launcher path before execing AppRun
- must not hide `%k` inside the quoted Python command body passed to AppRun
- validate that packaged entry paths are relative, contain no parent traversal,
  and resolve to files under the package root before running

Both launcher profiles reject unsafe `entry_relative_path` values at manifest
creation time. The generated bootstrap also re-checks that the resolved runtime
entry remains inside an absolute package root.

## ChoreBoy Staging Rule

Installable packages are designed around the ChoreBoy copy-and-launch workflow:

1. copy the whole installer package into `/home/default/`
2. keep the installer folder together
3. run the installer launcher from there
4. choose the final install directory

The installer warns when the staging package is not under `/home/default/`.

## Source of Truth Files

When packaging behavior changes, update the matching source files together:

- `package.py`
- `packaging/install.py`
- `app/packaging/`
- `app/ui/help/packaging_backup.md`
- `docs/manual/chapters/09_packaging_backup.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/TASKS.md`
- `docs/ARCHITECTURE.md`
- `vendor/README.md` when the product archive budget or shipped vendor bundle changes

For shipped native dependencies, `vendor/README.md` is the canonical contract
for the ChoreBoy product bundle, including the required tree-sitter ABI and the
curated grammar set that must fit inside the installer archive budget.

## Summary

The supported mental model is:

- **installable**: validated, installer-grade, upgrade-aware, AppRun-native
- **portable**: lighter-weight, still AppRun-native, but stricter about launcher placement
- **product distribution** and **project export** now share the same manifest/installer contract instead of drifting separately
