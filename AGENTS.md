# AGENTS.md

## Cursor Cloud specific instructions

ChoreBoy Code Studio runs inside FreeCAD's bundled Python. There is no virtualenv. Tests and the editor go through an AppRun. Product behavior is in `docs/DISCOVERY.md`.

### Runtimes

`.cursor/Dockerfile` bakes the two AppImages, Miniconda, and the Python 3.9 conda prefix. `scripts/cloud_setup_screenshot_runtime.sh` is the `install` command. It creates anything the image does not already have, then installs `vendor_py39`, `vendor_py311`, and the pinned pyright package. Versions and checksums are in `scripts/cloud_runtime_pins.env`.

| Runtime | Path | Measured contents |
| --- | --- | --- |
| PySide2 lane. Default for `run_tests.py`. | `/opt/freecad/AppRun` | FreeCAD 1.0.2, Python 3.11.13, PySide2 5.15.15. No PySide6. |
| PySide6 lane and form builder. | `/opt/freecad-1.1/AppRun` | FreeCAD 1.1.4, Python 3.11.14, PySide6 6.8.3. `QtUiTools` and `QtDesigner` import. |
| Python 3.9 prefix. | `~/opt/freecad/AppRun` | conda-forge `freecad=1.0.0`, Python 3.9.23, PySide2 5.15.15. PySide6 is also installed. The FreeCAD `PySide` shim imports PySide6. |
| Qt6 `uic` and `rcc` | `/usr/local/bin/cbcs-fb-uic`, `/usr/local/bin/cbcs-fb-rcc` | Both report 6.8.3. They exec `usr/lib/qt6/uic` and `usr/lib/qt6/rcc` inside the 1.1 tree. |
| Form-builder interpreter | `/usr/local/bin/cbcs-fb-python` | 1.1 `usr/bin/python` with `PYTHONHOME` set. It does not force `QT_QPA_PLATFORM`. |

`run_tests.py` uses `/opt/freecad/AppRun` unless `CBCS_APPRUN` is set. That default is the PySide2 lane. `CBCS_QT_API` is not required there.

`./run_dev.sh` prefers `~/opt/freecad/AppRun` when `CBCS_APPRUN` and `FREECAD_APPRUN` are both unset. On this image that is the conda prefix, so an unset launch follows the PySide6 shim. Login shells export `FREECAD_APPRUN=/opt/freecad/AppRun` from `/etc/profile.d/cbcs-cloud.sh`. Other shells should load the same values first.

```bash
set -a
. /etc/cbcs-cloud.env
set +a
```

| Variable | Value |
| --- | --- |
| `FREECAD_APPRUN` | `/opt/freecad/AppRun` |
| `CBCS_FB_APPRUN_11` | `/opt/freecad-1.1/AppRun` |
| `CBCS_FB_PY311` | `/usr/local/bin/cbcs-fb-python` |
| `CBCS_FB_UIC` | `/usr/local/bin/cbcs-fb-uic` |
| `CBCS_FB_RCC` | `/usr/local/bin/cbcs-fb-rcc` |
| `CBCS_ARTIFACTS_DIR` | `/home/ubuntu/cbcs_artifacts` |

`DISPLAY` defaults to `:1` in the profile script. `scripts/cloud_start_display.sh` starts Xvfb on `:1` only when neither `$DISPLAY` nor `:1` is already up. `run_tests.py` sets `QT_QPA_PLATFORM=offscreen` when that variable is empty. The FreeCAD 1.1 `AppRun` then exports `QT_QPA_PLATFORM=xcb`, so a shard launched through that AppRun uses the virtual display. `cbcs-fb-python` leaves the caller's platform alone.

Both AppImages are Python 3.11 and use `vendor_py311`. The conda prefix uses `vendor_py39`. `dev_launch_editor.py` points `vendor/` at the tree that matches the selected AppRun.

### Form builder

The feature runs on PySide6 only. Use the 1.1 AppRun, not the conda prefix.

```bash
CBCS_APPRUN="$CBCS_FB_APPRUN_11" CBCS_QT_API=pyside6 python3 testing/run_test_shard.py fast
"$CBCS_FB_UIC" -v
"$CBCS_FB_RCC" -v
```

`spikes/form_builder/tests/test_oracle.py` on `feat/form-builder-spike` hardcodes `/Applications/FreeCAD.app/Contents/Resources/lib/qt6/uic` and `Path("/Applications/FreeCAD.app")`. It does not read `CBCS_FB_UIC`. A symlink from that macOS path onto `/opt/freecad-1.1/usr` would make the binary resolve. An environment variable would not, until that branch reads one. The corpus test treats a missing FreeCAD.app as an empty file list and passes. The `uic` comparison fails at `subprocess.check_call` until the binary exists at the hardcoded path.

The 1.1 interpreter does not ship pytest. Point `PYTHONPATH` at `vendor_py311` for the spike smoke.

```bash
git fetch origin feat/form-builder-spike
git worktree add /tmp/spike origin/feat/form-builder-spike
cd /tmp/spike
QT_QPA_PLATFORM=offscreen PYTHONPATH="$CBCS_ARTIFACTS_DIR/vendor_py311" \
  "$CBCS_FB_PY311" -m pytest spikes/form_builder/tests -q -p no:cacheprovider
```

### How the environments compare

| Aspect | ChoreBoy production (V6.5) | ChoreBoy FreeCAD 1.1 | Cursor Cloud |
| --- | --- | --- | --- |
| AppRun | `/opt/freecad/AppRun` | `/opt/freecad/AppRun` on the appliance | `/opt/freecad/AppRun` (1.0.2, PySide2) and `/opt/freecad-1.1/AppRun` (1.1.4, PySide6) |
| Python | 3.9.2 | 3.11.14 | 3.11.13 (1.0.2), 3.11.14 (1.1.4), 3.9.23 (conda prefix) |
| Qt | PySide2 5.15.2 | PySide6 6.8.3 | PySide2 5.15.15 on 1.0.2. PySide6 6.8.3 on 1.1.4. |
| Display | X11 desktop | X11 desktop | X11 on `:1` |
| Subprocess restrictions | AppArmor allows `/bin/sh` | AppArmor allows exec of `/opt/freecad/AppRun` and denies `/bin/sh`, bash, `shell=True`, and git | None |
| Native code | vendored cp39 `.so` via memfd | tree-sitter from the image, memfd removed | `vendor_py311` for the AppImages, `vendor_py39` for the conda prefix |

All application code must target **Python 3.9** syntax (see `.cursor/rules/python39_compatibility.mdc`). The 3.11 AppImages do not relax that rule.

### Importing Qt

CBCS runs on PySide2 and PySide6 from one codebase. In app, test and testing code, import Qt only through `app.qt`, never from a binding:

```python
from app.qt.QtWidgets import QAction, QDialog   # QAction family works on both
from app.qt.qt_compat import exec_qt, enum_value, event_pos
exec_qt(dialog)          # not dialog.exec_()
enum_value(modifiers)    # not int(modifiers); int() raises on PySide6 flag enums
```

`app/bootstrap/qt_binding_choice.py` picks the binding. `CBCS_QT_API=pyside2|pyside6` forces it; otherwise CBCS follows FreeCAD's `PySide` shim when present, else prefers PySide6. The `qt-portability` dune check (`python3 -m tools.dune.check`) enforces this, and `python3 tools/qt_codemod.py` rewrites stray binding imports. User-facing code (templates, example projects, the installer) instead imports FreeCAD's `PySide` shim, `from PySide.QtWidgets import …`, with `QAction`/`QActionGroup`/`QShortcut` from `PySide.QtGui`. See `docs/PYSIDE6_MIGRATION_PLAN.md`.

### Running tests

Default agent loop — fast lane (~30–60 s, all unit + non-slow integration through AppRun):

```bash
python3 testing/run_test_shard.py fast
```

`run_test_shard.py` runs [`testing/preflight_test_env.py`](testing/preflight_test_env.py) first (stale AppRun child detection + `pytest-timeout` availability). The fast shard also has a 180 s outer watchdog. `run_tests.py` sets `CBCS_DISABLE_BACKGROUND_RUNTIME=1` so MainWindow tests do not auto-spawn plugin-host/REPL subprocesses.

**Agent anti-patterns that look like hangs:**

- Piping shard output through `rg "passed|failed"` hides pytest progress dots.
- Wrapping the fast shard in `timeout 170` before confirming the current checkpoint wall time.
- Leaving aborted `run_tests.py` sessions running — check `python3 testing/preflight_test_env.py` or `ps aux | rg 'run_plugin_host|run_runner'` before blaming pytest.

Pre-PR / CI lanes when you need the heavier coverage:

```bash
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py performance
python3 testing/run_test_shard.py runtime_parity
```

When you only need a specific path or expression (still through AppRun):

```bash
python3 run_tests.py tests/unit/some/test_module.py
python3 run_tests.py -k test_project_service
```

PySide6 lane. `CBCS_APPRUN` selects the runtime. `CBCS_QT_API=pyside6` is required on a prefix that also has PySide2. The 1.1 tree is PySide6-only, and the variable still documents the lane.

```bash
CBCS_APPRUN="${CBCS_FB_APPRUN_11:-/opt/freecad-1.1/AppRun}" CBCS_QT_API=pyside6 python3 testing/run_test_shard.py fast
```

Every change that touches Qt code should pass on both bindings. Today's ChoreBoy is PySide2 and the FreeCAD 1.1 image is PySide6-only. The live ChoreBoy VMs are the final check: `.cursor/skills/verify-cbcs` (`control-cbcs shard fast`) runs the suite in-process on a guest. ChoreBoyExp is the FreeCAD 1.1 VM; see `docs/PYSIDE6_MIGRATION_PLAN.md` for how to drive it.

`QT_QPA_PLATFORM=offscreen` and `--import-mode=importlib` are applied automatically by `run_tests.py`; do not pass them by hand. The `slow` marker (subprocess polling, debug session waits) is excluded from the `fast` shard so the agent loop stays under budget. The demoted `performance` marker is auto-excluded by `run_tests.py` unless you pass `-m performance` or a path under `tests/integration/performance/`. See `docs/TESTS.md` §5 for the canonical command catalog and §9 for the latest checkpoint numbers.

Latest checkpoint (2026-06-17, `main` branch):

- `python3 testing/run_test_shard.py fast` -> **~170s wall time**, **2064 selected / 24 deselected**, **0 failures** on a clean machine after the reaper/split-shard fix. The fast shard now runs unit and integration as two sequential AppRun sessions (shared 180s watchdog) to avoid Qt session bloat. Run `python3 testing/preflight_test_env.py` first; no orphaned `run_plugin_host`/`run_runner` children after exit.
- `python3 testing/run_test_shard.py integration` -> ~55s, **64 passed, 3 skipped, 0 failures**. Slow debug integration tests skip when AppRun emits no debug channel or no `stopped` pause event (see `docs/DISCOVERY.md` §4D; guards in `tests/support/debug_transport_guards.py`).
- `python3 testing/run_test_shard.py performance` -> ~74s, **11 passed, 0 failures** (four modules under `tests/integration/performance/`).
- `python3 testing/run_test_shard.py runtime_parity` -> ~4s, **17 passed**.

Canonical test command catalog: [`docs/TESTS.md`](docs/TESTS.md) §5.

### Testing philosophy

This project favors **fewer, higher-value tests** over coverage chasing. Before adding a test, check the risk-first gate in `.cursor/rules/testing_when_to_write.mdc`; if no decision-gate question is answered yes, do not add the test. The anti-pattern catalog in `.cursor/rules/test_anti_patterns.mdc` lists the specific shapes (constant pinning, schema snapshots, lint-as-test, private-attr probing, mock-dominated tests) to avoid. The TDD workflow in `.cursor/rules/tdd_business_logic_non_ui.mdc` only kicks in once a test is justified. A standing audit of the existing suite lives at `docs/TEST_AUDIT.md`.

### Running the editor (dev mode)

Launch through AppRun with the repo dev script (prefers `~/opt/freecad/AppRun` when present):

```bash
./run_dev.sh
```

Dry-run to inspect the resolved command:

```bash
./run_dev.sh --dry-run
```

Verify tree-sitter / syntax-highlighting parity:

```bash
./run_dev.sh --probe
```

First-time local setup:

```bash
./scripts/setup_freecad_dev.sh      # ~/opt/freecad/AppRun (Python 3.9)
./scripts/migrate_vendor_to_py311.sh  # if legacy artifacts/vendor/ exists
./scripts/setup_vendor_py39.sh      # ChoreBoy-parity vendor bundle
```

See [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md) for the full dual-vendor workflow
(`vendor_py39/` vs `vendor_py311/` under `ChoreBoyCodeStudio_artifacts/`).

PySide6 editor on the virtual display:

```bash
set -a; . /etc/cbcs-cloud.env; set +a
CBCS_APPRUN="$CBCS_FB_APPRUN_11" CBCS_QT_API=pyside6 DISPLAY="${DISPLAY:-:1}" ./run_dev.sh
```

`~/opt/freecad` exists on a finished install, so `./run_dev.sh` without `CBCS_APPRUN` launches the conda prefix. The status bar should show "Runtime ready" when capability checks pass. A missing tree-sitter load also shows `Syntax highlighting off`.

### Type checking (pyright)

```bash
npx pyright
```

Focused test typing:

```bash
npx pyright -p pyrightconfig.tests.json
```

`pyrightconfig.json` targets Python 3.9 source compatibility and resolves imports through the repo root, `vendor/`, and `/opt/freecad/usr/lib/python3.11/site-packages` (the FreeCAD 1.0.2 tree). `scripts/resolve_pyright_extrapaths.sh` prefers `~/opt/freecad/lib/python3.9/site-packages` when that PySide2 tree exists. PySide2 Shiboken stub noise is scoped via execution-environment `report*` overrides documented in `docs/LOCAL_DEV.md`. Pin: `package.json` → `pyright@1.1.414`. `pyrightconfig.tests.json` is a staged, low-noise test coverage config. Latest checkpoint: both commands -> `0 errors, 0 warnings, 0 informations`.

### Vendored dependencies

The `vendor/` directory is gitignored. If it exists as a dangling symlink (from
local dev), remove it first (`rm vendor`).

The shipped product has one supported native bundle contract:

- ChoreBoy target runtime
- Python `3.9.2`
- SOABI `cpython-39-x86_64-linux-gnu`
- curated bundle documented in `vendor/README.md`

Any product artifact must use that `cp39` contract. Do not package or ship a
`cp311` vendor tree.

`package.py` enforces the contract at staging time and self-heals the
`tree_sitter` core binding: it downloads the cp39 manylinux wheel via
`pip download --python-version=3.9 --platform=manylinux_2_17_x86_64`, caches it
under `<artifacts>/vendor_cp39_cache/`, and overlays
`_binding.cpython-39-x86_64-linux-gnu.so` onto the staged payload. This means
the local `vendor/tree_sitter/` may legitimately hold a cp311 binding for
Cloud-dev use without breaking `python package.py`. Grammar wheels
(`tree_sitter_*`) are `abi3` across Python versions, not across OS or CPU.
`validate_choreboy_tree_sitter_bundle` requires each `_binding*.so` to be a
little-endian ELF64 x86-64 binary. A Darwin `abi3` file will fail the build.

For local Cursor Cloud development only, populate the Python 3.11 bundle:

```bash
./scripts/setup_vendor_py311.sh
```

For local ChoreBoy-parity development (Python 3.9 via `~/opt/freecad/AppRun`):

```bash
./scripts/setup_vendor_py39.sh
```

Legacy `ChoreBoyCodeStudio_artifacts/vendor/` trees can be migrated once with
`./scripts/migrate_vendor_to_py311.sh`. At launch, `dev_launch_editor.py`
symlinks `repo/vendor` to `vendor_py39` or `vendor_py311` based on the active
AppRun SOABI (override with `CBCS_VENDOR_PROFILE=py39|py311`).

Manual Cloud-dev install (equivalent to `setup_vendor_py311.sh`):

```bash
mkdir -p vendor
pip3 install pyflakes==3.4.0 tree-sitter==0.23.2 \
 tree-sitter-python==0.23.6 tree-sitter-json==0.24.8 \
 tree-sitter-html==0.23.2 tree-sitter-xml==0.7.0 \
 tree-sitter-css==0.23.2 tree-sitter-bash==0.23.3 \
 tree-sitter-markdown==0.3.2 tree-sitter-yaml==0.7.0 \
 tree-sitter-toml==0.7.0 tree-sitter-javascript==0.23.1 \
 jedi parso "black==24.10.0" isort tomli rope \
 pytest==8.3.4 pluggy iniconfig exceptiongroup \
 --target=vendor/ --python-version=3.11 --only-binary=:all: \
 --platform=manylinux_2_17_x86_64
```

**Important:** Black must be pinned to `24.10.0`. Black 25+ removed `black.Mode` and `black.NothingChanged` which the codebase depends on. The `jedi`, `parso`, `black`, `isort`, `tomli`, and `rope` packages are required by the intelligence and python_tools subsystems. Without them, related tests fail and editor features (formatting, code intelligence, refactoring) are unavailable. The `pytest` (+ `pluggy`, `iniconfig`, `exceptiongroup`, `pytest-timeout`) packages are bundled so the in-app Test Explorer and the global 30 s per-test timeout in `pyproject.toml` work on real ChoreBoy without extra installs.

The `--python-version=3.11` and `--platform` flags above are for Cloud dev
only. See `vendor/README.md` for the shipped ChoreBoy bundle contract and the
Python 3.9 production guidance.

### Installing dev tools into FreeCAD's Python

`pytest` and `pytest-timeout` are bundled in `vendor/` (see "Vendored dependencies" above). Both
`run_tests.py` and the in-app Test Explorer inject `vendor/` onto the AppRun
subprocess `sys.path` before importing pytest, so no separate pytest install
into `/opt/freecad/usr/lib/python3.11/site-packages/` is required.

If `pytest-timeout` is missing from vendor (legacy tree), install it into AppRun site-packages:

```bash
pip3 install pytest-timeout --target=/opt/freecad/usr/lib/python3.11/site-packages/
```

### Key caveats

- **No `.venv`**: do not create a virtualenv. Everything runs through `/opt/freecad/AppRun`.
- `.venv-editor` may exist as editor tooling scaffolding for pyright; recreate it with `./scripts/setup_venv_editor.sh`, but do not run the app or tests from it.
- The FreeCAD AppImage is extracted (not run as an AppImage) at `/opt/freecad/`. The `AppRun` script sets `PYTHONHOME`, SSL paths, and other environment variables automatically.
- `libxcb-xinerama0` and related xcb packages must be installed for Qt's xcb platform plugin to work with a display server.
- **Slow integration tests:** subprocess + debug-session + RunService project/template execution tests are tagged `@pytest.mark.slow` and excluded from `python3 testing/run_test_shard.py fast`. They still run under the `integration` shard pre-PR, with per-test `pytest.mark.timeout(180)` overrides instead of the global 30 s default.
- **Test subprocess hygiene:** `run_tests.py` sets `CBCS_DISABLE_BACKGROUND_RUNTIME=1`; `tests/conftest.py` reaps leaked `run_plugin_host`/`run_runner` children after every test and at session end.
- `**vendor/` symlink:** The repo may contain a `vendor` symlink pointing to a local developer's machine. Remove it before populating vendor: `[ -L vendor ] && rm vendor`.
- Canonical documentation: `docs/PRD.md` (product), `docs/DISCOVERY.md` (runtime), `docs/ARCHITECTURE.md` (design), `docs/TASKS.md` (backlog).

