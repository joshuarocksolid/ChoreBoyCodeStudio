# AGENTS.md

## Cursor Cloud specific instructions

### Runtime architecture

ChoreBoy Code Studio runs entirely inside FreeCAD's bundled Python runtime. There is **no virtualenv** — all code (app, tests, runner) executes via `/opt/freecad/AppRun`. This mirrors the ChoreBoy production environment described in `docs/DISCOVERY.md`.


| Component            | Path                                             |
| -------------------- | ------------------------------------------------ |
| FreeCAD AppRun       | `/opt/freecad/AppRun`                            |
| Bundled Python       | 3.11.13 (conda-forge)                            |
| Bundled PySide2      | 5.15.15                                          |
| Python site-packages | `/opt/freecad/usr/lib/python3.11/site-packages/` |
| Vendored packages    | `/workspace/vendor/`                             |


### How the two environments compare


| Aspect                  | ChoreBoy production       | Cursor Cloud dev             |
| ----------------------- | ------------------------- | ---------------------------- |
| AppRun path             | `/opt/freecad/AppRun`     | `/opt/freecad/AppRun` (same) |
| Python version          | 3.9.2                     | 3.11.13                      |
| PySide2                 | bundled in AppRun         | bundled in AppRun            |
| Display                 | X11 desktop               | X11 on `:1`                  |
| Subprocess restrictions | AppArmor (only `/bin/sh`) | None                         |
| Vendored `.so` wheels   | cp39                      | cp311                        |


All application code must target **Python 3.9** syntax (see `.cursor/rules/python39_compatibility.mdc`), even though the Cloud dev runtime is 3.11.

### Running tests

Default agent loop — fast lane (~30 s, all unit + non-slow integration through AppRun):

```bash
python3 testing/run_test_shard.py fast
```

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

`QT_QPA_PLATFORM=offscreen` and `--import-mode=importlib` are applied automatically by `run_tests.py`; do not pass them by hand. The `slow` marker (subprocess polling, debug session waits) is excluded from the `fast` shard so the agent loop stays under budget. The demoted `performance` marker is auto-excluded by `run_tests.py` unless you pass `-m performance` or a path under `tests/integration/performance/`. See `docs/TESTS.md` §5 for the canonical command catalog and §9 for the latest checkpoint numbers.

Latest checkpoint (2026-04-24, this branch):

- `python3 testing/run_test_shard.py fast` -> ~34s, **1445 passed, 1 skipped, 17 deselected, 0 failures**.
- `python3 testing/run_test_shard.py integration` -> ~37s, **59 passed**.
- `python3 testing/run_test_shard.py performance` -> ~34s, **15 passed, 2 pre-existing failures** (`test_local_history_performance` regressions tracked separately).
- `python3 testing/run_test_shard.py runtime_parity` -> ~4s, **17 passed**.

### Testing philosophy

This project favors **fewer, higher-value tests** over coverage chasing. Before adding a test, check the risk-first gate in `.cursor/rules/testing_when_to_write.mdc`; if no decision-gate question is answered yes, do not add the test. The anti-pattern catalog in `.cursor/rules/test_anti_patterns.mdc` lists the specific shapes (constant pinning, schema snapshots, lint-as-test, private-attr probing, mock-dominated tests) to avoid. The TDD workflow in `.cursor/rules/tdd_business_logic_non_ui.mdc` only kicks in once a test is justified. A standing audit of the existing suite lives at `docs/TEST_AUDIT.md`.

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
npx pyright
```

Focused test typing:

```bash
npx pyright -p pyrightconfig.tests.json
```

`pyrightconfig.json` targets Python 3.9 source compatibility and resolves imports through the repo root, `vendor/`, and `/opt/freecad/usr/lib/python3.11/site-packages`. `pyrightconfig.tests.json` is a staged, low-noise test coverage config. Latest checkpoint: both commands -> `0 errors, 0 warnings, 0 informations`.

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
(`tree_sitter_*`) are `abi3` and version-agnostic, so they are not affected.

For local Cursor Cloud development only, you can populate `vendor/` with the
current per-language tree-sitter bundle for the Cloud AppRun runtime:

```bash
mkdir -p vendor
pip3 install pyflakes==3.4.0 tree-sitter==0.23.2 \
  tree-sitter-python==0.23.6 tree-sitter-json==0.24.8 \
  tree-sitter-html==0.23.2 tree-sitter-xml==0.7.0 \
  tree-sitter-css==0.23.2 tree-sitter-bash==0.23.3 \
  tree-sitter-markdown==0.3.2 tree-sitter-yaml==0.7.0 \
  tree-sitter-toml==0.7.0 tree-sitter-javascript==0.23.1 \
  jedi parso "black==24.10.0" isort tomli rope \
  --target=vendor/ --python-version=3.11 --only-binary=:all: \
  --platform=manylinux_2_17_x86_64
```

**Important:** Black must be pinned to `24.10.0`. Black 25+ removed `black.Mode` and `black.NothingChanged` which the codebase depends on. The `jedi`, `parso`, `black`, `isort`, `tomli`, and `rope` packages are required by the intelligence and python_tools subsystems. Without them, related tests fail and editor features (formatting, code intelligence, refactoring) are unavailable.

The `--python-version=3.11` and `--platform` flags above are for Cloud dev
only. See `vendor/README.md` for the shipped ChoreBoy bundle contract and the
Python 3.9 production guidance.

### Installing dev tools into FreeCAD's Python

pytest (and other dev-only packages) are installed into FreeCAD's site-packages:

```bash
pip3 install pytest --target=/opt/freecad/usr/lib/python3.11/site-packages/
```

This is necessary because `run_tests.py` imports pytest from within the AppRun process.

### Key caveats

- **No `.venv`**: do not create a virtualenv. Everything runs through `/opt/freecad/AppRun`.
- `.venv-editor` may exist as legacy editor tooling scaffolding, but it is not a real Python environment and nothing should be run from it.
- The FreeCAD AppImage is extracted (not run as an AppImage) at `/opt/freecad/`. The `AppRun` script sets `PYTHONHOME`, SSL paths, and other environment variables automatically.
- `libxcb-xinerama0` and related xcb packages must be installed for Qt's xcb platform plugin to work with a display server.
- **Slow integration tests:** subprocess + debug-session integration tests are tagged `@pytest.mark.slow` and excluded from `python3 testing/run_test_shard.py fast`. They still run under the `integration` shard pre-PR, with per-test `pytest.mark.timeout(180)` overrides instead of the new global 30 s default.
- `**vendor/` symlink:** The repo may contain a `vendor` symlink pointing to a local developer's machine. Remove it before populating vendor: `[ -L vendor ] && rm vendor`.
- Canonical documentation: `docs/PRD.md` (product), `docs/DISCOVERY.md` (runtime), `docs/ARCHITECTURE.md` (design), `docs/TASKS.md` (backlog).

