# AGENTS.md

## Cursor Cloud specific instructions

### Runtime architecture

ChoreBoy Code Studio runs entirely inside FreeCAD's bundled Python runtime. There is **no virtualenv** — all code (app, tests, runner) executes via `/opt/freecad/AppRun`. This mirrors the ChoreBoy production environment described in `docs/DISCOVERY.md`.

| Component | Path |
|---|---|
| FreeCAD AppRun | `/opt/freecad/AppRun` |
| Bundled Python | 3.11.13 (conda-forge) |
| Bundled PySide2 | 5.15.15 |
| Python site-packages | `/opt/freecad/usr/lib/python3.11/site-packages/` |
| Vendored packages | `/workspace/vendor/` |

### How the two environments compare

| Aspect | ChoreBoy production | Cursor Cloud dev |
|---|---|---|
| AppRun path | `/opt/freecad/AppRun` | `/opt/freecad/AppRun` (same) |
| Python version | 3.9.2 | 3.11.13 |
| PySide2 | bundled in AppRun | bundled in AppRun |
| Display | X11 desktop | X11 on `:1` |
| Subprocess restrictions | AppArmor (only `/bin/sh`) | None |
| Vendored `.so` wheels | cp39 | cp311 |

All application code must target **Python 3.9** syntax (see `.cursor/rules/python39_compatibility.mdc`), even though the Cloud dev runtime is 3.11.

### Running tests

Use the project's `run_tests.py` which launches pytest inside AppRun:

```bash
python3 run_tests.py -v --import-mode=importlib
```

- `--import-mode=importlib` is required because test directories lack `__init__.py` and have duplicate file names across `tests/unit/` and `tests/integration/`.
- `QT_QPA_PLATFORM=offscreen` is set automatically by `run_tests.py`.
- The `runtime_parity` test passes because AppRun is installed at the expected path.
- There is one pre-existing test failure: `test_handle_drop_move_returns_oserror_message`.

To run a subset:

```bash
python3 run_tests.py -v --import-mode=importlib tests/unit/
python3 run_tests.py -v --import-mode=importlib -k test_project_service
```

### Running the editor (dev mode)

Launch exactly as ChoreBoy does — through AppRun:

```bash
cd /workspace && /opt/freecad/AppRun -c "
import os, runpy, sys
root = '/workspace'
sys.path.insert(0, root) if root not in sys.path else None
os.chdir(root)
runpy.run_path('/workspace/run_editor.py', run_name='__main__')
"
```

Requires `DISPLAY` (available as `:1` in Cloud). The status bar should show "Runtime ready (6/6 checks)".

### Type checking (pyright)

```bash
pyright
```

Pyright uses the `.venv-editor` stub directory (which symlinks to FreeCAD's site-packages) for import resolution. The `pyrightconfig.json` is already configured. All remaining errors (~460) are pre-existing PySide2 type-stub issues, not code bugs. Zero `reportMissingImports` errors.

### Vendored dependencies

The `vendor/` directory is gitignored. Populate it with:

```bash
pip3 install pyflakes==3.4.0 tree-sitter==0.21.3 tree-sitter-languages==1.10.2 \
  --target=vendor/ --python-version=3.11 --only-binary=:all: \
  --platform=manylinux_2_17_x86_64
```

The `--python-version=3.11` and `--platform` flags ensure correct cp311 `.so` wheels matching FreeCAD's Python. See `vendor/README.md` for details.

### Installing dev tools into FreeCAD's Python

pytest (and other dev-only packages) are installed into FreeCAD's site-packages:

```bash
pip3 install pytest --target=/opt/freecad/usr/lib/python3.11/site-packages/
```

This is necessary because `run_tests.py` imports pytest from within the AppRun process.

### Key caveats

- **No `.venv`**: do not create a virtualenv. Everything runs through `/opt/freecad/AppRun`.
- `.venv-editor` is a thin stub directory used **only** by pyright for import resolution — it is not a real Python environment and nothing should be run from it.
- The FreeCAD AppImage is extracted (not run as an AppImage) at `/opt/freecad/`. The `AppRun` script sets `PYTHONHOME`, SSL paths, and other environment variables automatically.
- `libxcb-xinerama0` and related xcb packages must be installed for Qt's xcb platform plugin to work with a display server.
- Canonical documentation: `docs/PRD.md` (product), `docs/DISCOVERY.md` (runtime), `docs/ARCHITECTURE.md` (design), `docs/TASKS.md` (backlog).
