# Local ChoreBoy Dev Setup

This guide explains how to run ChoreBoy Code Studio on a developer machine with
maximum parity to the ChoreBoy production runtime (Python 3.9 + PySide2 +
FreeCAD AppRun).

## Layout

```text
Documents/
  ChoreBoyCodeStudio/                 application repo (`vendor` → symlink)
  ChoreBoyCodeStudio_artifacts/
    vendor_py39/                      Python 3.9 bundle (local ~/opt/freecad)
    vendor_py311/                      Python 3.11 bundle (Cloud /opt/freecad)
    vendor_cp39_cache/                cached cp39 tree-sitter wheel downloads
```

`dev_launch_editor.py` probes the selected AppRun SOABI and symlinks
`ChoreBoyCodeStudio/vendor` to the matching artifacts vendor tree before launch.

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

### 3. Launch

```bash
./run_dev.sh
```

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
