# AGENTS.md

## Cursor Cloud specific instructions

### Overview

ChoreBoy Code Studio is a Qt (PySide2) Python IDE that runs on the locked-down ChoreBoy environment via FreeCAD's bundled AppRun runtime. In the Cursor Cloud dev environment, FreeCAD AppRun is not available, so the project uses a Python 3.10 virtualenv with PySide2 installed from pip instead.

### Python environment

- Python 3.10 is required (PySide2 5.15.2.1 does not support Python 3.12+).
- The virtualenv lives at `/workspace/.venv` and is created via `python3.10 -m venv /workspace/.venv`.
- Activate or reference binaries directly: `/workspace/.venv/bin/python`, `/workspace/.venv/bin/pytest`.
- System package `python3.10` is installed via the deadsnakes PPA.
- System package `libxcb-xinerama0` (and related xcb libs) is needed for Qt xcb platform plugin when running the GUI with a display.

### Vendored dependencies

- `vendor/` is gitignored and must be populated before tests that touch tree-sitter or linting.
- Install with: `pip install pyflakes==3.4.0 tree-sitter==0.21.3 tree-sitter-languages==1.10.2 --target=vendor/`
- See `vendor/README.md` for full details on platform-specific binaries.

### Running tests

```bash
QT_QPA_PLATFORM=offscreen /workspace/.venv/bin/python -m pytest tests/ -v --import-mode=importlib
```

- `--import-mode=importlib` is required because test directories lack `__init__.py` files and there are duplicate test file names across `tests/unit/` and `tests/integration/`.
- `QT_QPA_PLATFORM=offscreen` avoids requiring a display server for tests.
- The `run_tests.py` script requires FreeCAD AppRun (not available in Cloud); run pytest directly instead.
- `runtime_parity` tests skip automatically when AppRun is absent.

### Running the editor (dev mode)

```bash
cd /workspace && /workspace/.venv/bin/python run_editor.py
```

- Requires `DISPLAY` to be set (available in Cloud VM as `:1`).
- Status bar shows "Runtime issues (4/6 checks)" — expected in Cloud since AppRun is absent.

### Type checking

```bash
/workspace/.venv/bin/pyright --pythonpath /workspace/.venv/bin/python
```

- Pre-existing PySide2 type-stub errors (~862) are expected; these are not code bugs.

### Key caveats

- There is one pre-existing test failure: `test_handle_drop_move_returns_oserror_message` in `tests/unit/shell/test_project_tree_action_coordinator.py`.
- All application code must target Python 3.9 compatibility (see `.cursor/rules/python39_compatibility.mdc`), even though the dev environment uses Python 3.10.
- Do not use hidden (dot-prefixed) directory names for project metadata or app state (see `.cursor/rules/no_hidden_folders.mdc`).
- Canonical documentation: `docs/PRD.md` (product), `docs/DISCOVERY.md` (runtime), `docs/ARCHITECTURE.md` (design), `docs/TASKS.md` (backlog).
