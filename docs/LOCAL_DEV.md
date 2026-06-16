# Local ChoreBoy Dev Setup

This guide explains how to run ChoreBoy Code Studio on a developer machine with
maximum parity to the ChoreBoy production runtime (Python 3.9 + PySide2 +
FreeCAD AppRun).

## Layout

```text
Documents/
  ChoreBoyCodeStudio/                 application repo (`vendor` → symlink)
  ChoreBoyCodeStudio_artifacts/
    .venv-editor/                    optional editor tooling venv (pyright only)
    vendor_py39/                      Python 3.9 bundle (local ~/opt/freecad)
    vendor_py311/                      Python 3.11 bundle (Cloud /opt/freecad)
    vendor_cp39_cache/                cached cp39 tree-sitter wheel downloads
```

`dev_launch_editor.py` probes the selected AppRun SOABI and symlinks
`ChoreBoyCodeStudio/vendor` to the matching artifacts vendor tree before launch.

## Environment comparison

| Aspect | ChoreBoy production | Cursor Cloud / local dev |
|--------|---------------------|---------------------------|
| Python | 3.9.2 (AppRun only) | 3.11.13 (Cloud `/opt/freecad`) or 3.9.2 (`~/opt/freecad/AppRun`) |
| AppRun | `/opt/freecad/AppRun` | Same default; local setup prefers `~/opt/freecad/AppRun` |
| Qt / PySide2 | 5.15.2 (probed on device) | 5.15.15 (Cloud conda bundle) |
| Subprocess policy | AppArmor: only `/bin/sh` whitelisted | Unrestricted on typical dev machines |
| Source compatibility | Python 3.9 syntax required | Same — see `pyrightconfig.json` |

See also [`docs/CHOREBOY_RUNTIME_PITFALLS.md`](CHOREBOY_RUNTIME_PITFALLS.md) for cross-project pitfall patterns.

## First-time setup

### 1. FreeCAD AppRun (Python 3.9)

```bash
./scripts/setup_freecad_dev.sh
```

Creates `~/opt/freecad/AppRun` with Python 3.9, PySide2, and FreeCAD.

### 2. Vendor bundle

If you have a legacy `ChoreBoyCodeStudio_artifacts/vendor/` directory:

```bash
./scripts/migrate_vendor_to_py311.sh
```

Then install the ChoreBoy-parity bundle:

```bash
./scripts/setup_vendor_py39.sh
```

For Cloud / Python 3.11 dev:

```bash
./scripts/setup_vendor_py311.sh
```

### 3. Editor tooling venv

```bash
./scripts/setup_venv_editor.sh
```

Creates `ChoreBoyCodeStudio_artifacts/.venv-editor` with the pinned pyright
tooling used by the workspace settings. This venv is for IDE/static-analysis
tools only; do not activate it before `./run_dev.sh`.

### 4. Launch

```bash
./run_dev.sh
```

`run_dev.sh` launches through FreeCAD AppRun, not `.venv-editor`. If a shell
venv is active, the launcher strips virtualenv activation variables before
starting AppRun so FreeCAD does not try to load stale `activate_this.py` files.

## Pyright (static analysis)

```bash
npm install   # once, pins pyright@1.1.410 from package.json
npx pyright
npx pyright -p pyrightconfig.tests.json
```

`pyrightconfig.json` adds FreeCAD `site-packages` to `extraPaths` so `PySide2`
imports resolve. Shipped PySide2 `.pyi` stubs are incomplete for Shiboken
subclasses; the `app` execution environment sets `reportArgumentType`,
`reportAttributeAccessIssue`, `reportCallIssue`, `reportIncompatibleMethodOverride`,
`reportReturnType`, and `reportAssignmentType` to `"none"` so real syntax/import
issues still surface without ~1700 Qt noise diagnostics. Use
`scripts/resolve_pyright_extrapaths.sh` to print the preferred site-packages path
(`~/opt/freecad` py39 when present, else Cloud `/opt/freecad` py311).

## Verification

```bash
./run_dev.sh --probe
```

Expect JSON output with `"is_available": true` and a cp39 SOABI when using
`~/opt/freecad/AppRun`.

Force Cloud runtime:

```bash
CBCS_APPRUN=/opt/freecad/AppRun ./run_dev.sh --probe
```

## Overrides

| Variable | Purpose |
|---|---|
| `CBCS_APPRUN` | Force AppRun path |
| `FREECAD_APPRUN` | Cross-project AppRun override |
| `CBCS_ARTIFACTS_DIR` | Non-default artifacts location |
| `CBCS_VENDOR_PROFILE` | Force `py39` or `py311` vendor tree |

When using the Python 3.9 vendor tree, `black==24.10.0` requires `click<8.2`
(Python 3.9 cannot import Click 8.2+). `./scripts/setup_vendor_py39.sh` pins
that constraint automatically.

## memfd

Tree-sitter native bindings load through memfd (see `docs/DISCOVERY.md` §4E).
Local conda Python may lack `os.memfd_create`; `app/bootstrap/memfd_shim.py`
installs a libc-backed shim at editor startup so the same code path runs on dev
and ChoreBoy.

## Syntax highlighting troubleshooting

If editor files appear as plain text:

1. Run `./run_dev.sh --probe` and check for ABI mismatch in `status_message`.
2. Ensure `vendor_py39` exists when using Python 3.9 AppRun.
3. Check the status bar for `Syntax highlighting off`.

The Python Console REPL does not use tree-sitter highlighting; only editor tabs do.
