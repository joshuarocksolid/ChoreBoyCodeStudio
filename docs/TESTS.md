# ChoreBoy Code Studio — Test Strategy & Current Validation

## 1) Purpose

This document captures the **active** testing strategy and commands for the shipped implementation.

It aligns with:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/TASKS.md`

## 2) Framework and markers

- Test runner: `pytest` bundled in repo **`vendor/`** (injected onto `sys.path` by [`run_tests.py`](../run_tests.py) before `pytest.main`). Tests execute inside FreeCAD AppRun; pytest is **not** assumed to be preinstalled in AppRun site-packages.
- Markers (defined in `pyproject.toml`):
  - `unit`
  - `integration`
  - `runtime_parity`
  - `manual_acceptance`
  - `slow` — wall-time exceeds the agent fast-lane budget (subprocess polling, debug-session waits). Carries a `pytest.mark.timeout(180)` override; excluded from the `fast` shard.
  - `performance` — wall-clock benchmarks under `tests/integration/performance/`; excluded from default `run_tests.py` and the `fast`/`integration` shards unless explicitly targeted.

Global `timeout = 30` in `pyproject.toml` requires `pytest-timeout`, bundled in `vendor/` (see `scripts/setup_vendor_py39.sh` / `setup_vendor_py311.sh` and `AGENTS.md`).

## 3) Test layout

- `tests/unit/` — deterministic contract tests
- `tests/integration/` — multi-component filesystem/subprocess/runtime boundary tests
- `tests/runtime_parity/` — reserved for AppRun-specific checks where applicable

## 4) What is covered

Implemented coverage includes:

- bootstrap, logging, capability probe, path contracts
- project manifest/schema validation, project loading, and first-open metadata initialization for plain Python folders
- recent project persistence
- editor tab manager, dirty/save semantics, autosave store
- project tree model, quick-open ranking, find-in-files scanning
- run manifest schema, run id/log path generation
- process supervisor lifecycle and stop behavior
- runner bootstrap, execution context, traceback logging
- run orchestration end-to-end (manifest -> runner -> output -> log)
- diagnostics and support bundle generation
- built-in template discovery/materialization and generated-project execution
- responsiveness threshold checks (integration timing assertions)
- completion context/broker contracts, trusted API-index lookup, lazy item resolve,
worker prioritization, and completion latency gates

## 5) Core commands

This section is the canonical "how to run tests" instruction. Other docs (`AGENTS.md`, `tests/README.md`, `docs/SMOKE_WORKFLOW.md`, the per-task `Validation method:` snippets in `docs/TASKS.md`) point here.

### 5.1 Agent inner loop — fast shard (~55–60 s)

```bash
python3 testing/run_test_shard.py fast
```

Equivalent to `tests/unit + tests/integration -m "not slow" --ignore=tests/integration/performance`. Use this for every iterative AI-agent / TDD cycle. `QT_QPA_PLATFORM=offscreen` and `--import-mode=importlib` are applied automatically by `run_tests.py`; do not pass them manually.

### 5.2 Pre-PR / CI — broader shards

```bash
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py performance
python3 testing/run_test_shard.py runtime_parity
```

- `integration` is the full integration shard (slow + non-slow), excluding the performance subdirectory so timing-sensitive checks remain serial.
- `performance` is its own serial shard because those tests assert wall-clock thresholds.
- completion-specific latency gates live in
`tests/integration/performance/test_completion_latency_performance.py`.
- `runtime_parity` validates AppRun-specific paths.
- `all` (`python3 testing/run_test_shard.py all`) runs everything, including `tests/integration/performance` and any `slow`-marked tests.

### 5.3 Targeted runs — specific path or `-k` expression

```bash
python3 run_tests.py tests/unit/some/test_module.py
python3 run_tests.py -k test_project_service
```

`run_tests.py` is also what every shard ultimately invokes; reach for it directly only when you need to target a path that does not match a shard.

### 5.4 Parallelism (opt-in, experimental)

```bash
python3 testing/run_test_shard.py fast --workers 2
```

`--workers <count>` forwards to `pytest-xdist` via `CBCS_PYTEST_WORKERS`. Per the audit in §10, multi-worker xdist is **not** the default because each worker pays its own AppRun + Qt cold-start cost; use it only for narrow-scope experiments.

### 5.5 Static analysis

```bash
npx pyright
```

Focused test typing is available separately:

```bash
npx pyright -p pyrightconfig.tests.json
```

This config intentionally starts with low-noise helper/security tests instead of
type-checking the whole historical test suite at once. Ruff, Vulture, Radon,
and Lizard remain report-only recommendations until their dependencies are
approved and installed outside the AppRun pytest lane.

### 5.6 Form builder gates

`testing/run_form_builder_checks.py` runs the form-builder gates and prints one table. The process exits with status 1 when a selected gate fails. A skipped gate does not fail the run.

```bash
python3 testing/run_form_builder_checks.py
python3 testing/run_form_builder_checks.py --json /tmp/form-builder-checks.json
```

`--quick` skips `unit-py39-pyside6` and `pyright`. `--full` also runs `fast-shard-regression`. `--only` runs the named gates and ignores `--quick` and `--full`.

| Gate | What runs |
| --- | --- |
| `unit-py311` | pytest `tests/form_builder`, excluding `oracle` and `perf`, on `/Applications/FreeCAD.app/Contents/Resources/bin/python` |
| `unit-py39-pyside6` | the same tests through `~/opt/freecad/AppRun` with `CBCS_QT_API=pyside6` |
| `syntax-py39` | compile every `.py` file under `app/features/form_builder/` with that AppRun |
| `pyright` | `npx pyright app/features/form_builder`, then `npx pyright -p pyrightconfig.tests.json tests/form_builder` |
| `dune` | `python3 -m tools.dune.check` |
| `fast-shard-regression` | `python3 testing/run_test_shard.py fast` |
| `oracle` | pytest `-m oracle` on the Python 3.11 interpreter above |
| `perf` | pytest `-m perf` on that interpreter |

Both pytest lanes set `QT_QPA_PLATFORM=offscreen` and `CBCS_DISABLE_BACKGROUND_RUNTIME=1`. Pytest comes from the matching `vendor_py311` or `vendor_py39` tree, the same injection `run_tests.py` uses. `--import-mode=importlib` comes from `pyproject.toml`. When `vendor_py311` is absent, the Python 3.11 lane loads pytest from another tree that has it and appends that tree after the interpreter's site-packages. The pass row names that tree.

`syntax-py39` and `pyright` report `skipped: no package` until `app/features/form_builder/` contains Python files. A missing interpreter reports `skipped: runtime not found at ...`. Override the interpreters with `CBCS_FORM_BUILDER_PY311` and `CBCS_FORM_BUILDER_PY39`. When the AppRun is missing and the package exists, `syntax-py39` uses `ast.parse(..., feature_version=(3, 9))` on the interpreter that launched the runner.

`pyrightconfig.tests.json` is an allowlist. Add `tests/form_builder` to its `include` list when the suite grows past the smoke test. The runner still passes that path on the pyright command line.

`oracle` and `perf` are registered in `tests/form_builder/conftest.py`. The perf row records `os.getloadavg()` at the start and end of the gate (1, 5, and 15 minute averages). Those averages include every process on the machine. `fast-shard-regression` stays in the table and does not run unless you pass `--full` or `--only fast-shard-regression`.

Dune is the check in `tools/dune/check.py`: ownership, file roles, concurrency, handles, composition, Qt portability, the feature map, and policy.

Tests in `tests/form_builder/` are skipped when the active binding is not PySide6. `run_test_shard.py all` collects this directory. The fast shard does not.

## 6) Architecture hygiene validation gate

Before future editor-intelligence feature work, run the full automated gate and then execute `AT-72`:

```bash
python3 testing/run_test_shard.py all
npx pyright
```

`run_test_shard.py all` runs every test (unit, integration, performance, runtime_parity, including `slow`-marked subprocess and debug-session tests). It backs the same assertions that the architecture-hygiene phase requires.

## 7) Manual acceptance validation

Manual acceptance is executed against `docs/ACCEPTANCE_TESTS.md`:

- MVP gate (`AT-01`, `AT-03`, `AT-24`, `AT-05`, `AT-06`, `AT-07`, `AT-08`, `AT-10`, `AT-11`, `AT-12`, `AT-14`, `AT-15`, `AT-16`) validated with GUI evidence.
- Extended checks (`AT-17`, `AT-19`, `AT-20`, `AT-21`, `AT-22`, `AT-23`) validated with GUI + artifact evidence.
- `AT-18` draft recovery is validated via integration simulation test (`tests/integration/persistence/test_autosave_recovery.py`) because force-kill GUI simulation is unsafe in this cloud session.
- `AT-72` is the manual acceptance gate for the editor architecture hygiene slice, including light/dark theme confirmation for touched shell/editor surfaces.

## 8) Notes for cloud environment

- Tests run through `/opt/freecad/AppRun` using real PySide2, the binding on today's ChoreBoy. On Cursor Cloud that path is the FreeCAD 1.0.2 tree. Run the PySide6 lane too (`CBCS_APPRUN=${CBCS_FB_APPRUN_11:-/opt/freecad-1.1/AppRun} CBCS_QT_API=pyside6 python3 testing/run_test_shard.py fast`) for anything that touches Qt. The FreeCAD 1.1 tree is PySide6-only.
- `QT_QPA_PLATFORM=offscreen` is set by default in `run_tests.py` so tests do not require a display server. The FreeCAD 1.1 `AppRun` then exports `QT_QPA_PLATFORM=xcb`, so the PySide6 shard needs `DISPLAY` (Xvfb `:1` on the cloud image).

## 9) Current baseline result

Latest validation checkpoint. Pass counts are maintained in [`AGENTS.md`](../AGENTS.md). The 2026-10-21 Cursor Cloud run is the current measurement. The 2026-06-01 notes below it are the previous `main` baseline.

- `python3 testing/run_test_shard.py fast` -> **~170s wall time**, **2064 selected / 24 deselected**, **0 failures** (2026-06-17 reaper/split-shard checkpoint on a clean machine). Fast shard runs unit then integration as two sequential AppRun sessions under the shared 180s watchdog. Subprocess hygiene: cached `/proc` reaper in [`testing/runtime_child_reaper.py`](../testing/runtime_child_reaper.py), targeted per-test reaping in [`tests/conftest.py`](../tests/conftest.py), preflight via [`testing/preflight_test_env.py`](../testing/preflight_test_env.py).
- `python3 testing/run_test_shard.py integration` -> **~55s wall time**, **64 passed, 3 skipped, 0 failures** (slow debug tests skip when no debug channel or no `stopped` pause on this AppRun build; see `docs/DISCOVERY.md` §4D).
- `python3 testing/run_test_shard.py runtime_parity` -> **~4s wall time**, **17 passed**.
- `python3 testing/run_test_shard.py performance` -> **~74s wall time**, **11 passed, 0 failures** (all modules under `tests/integration/performance/`).
- `npx pyright` -> 0 errors, 0 warnings, 0 informations.
- `npx pyright -p pyrightconfig.tests.json` -> 0 errors, 0 warnings, 0 informations.
- `AT-72` remains the required manual confirmation step when touched shell/editor surfaces need four-theme validation.

The fast shard collects **1949 tests** (the 2026-06-01 MainWindow shell-workflow extraction added ~500 tests vs the prior 1445 checkpoint). Per-test cost is unchanged; the higher wall time is suite growth, not regression. A modal-dialog hang (`test_welcome_runtime_onboarding`) that previously stalled the shard past 180s is fixed, and `timeout_method = "thread"` now force-terminates any future C-level block at the 30s timeout instead of hanging.

## 10) Test speed notes

Speed audit re-run on 2026-04-24 after the fast-lane refactor (counts aligned with [`AGENTS.md`](../AGENTS.md) checkpoint on 2026-06-01):

- `python3 testing/run_test_shard.py fast` -> **~54–68s** wall time (**1949 passed**, 17 deselected via `-m "not slow"`). This is the agent default loop.
- The suite grew from 1445 to 1949 collected fast-shard tests after the 2026-06-01 MainWindow shell-workflow extraction; per-test cost is unchanged, so the wall time tracks the larger suite. Still exercises every Qt-touching unit test and every non-slow integration test.
- The `slow` marker now scopes the four worst offenders (`test_process_supervisor_integration`, `test_run_service_integration`, `test_breakpoint_stepping_flow`, `test_debug_session_integration`) with `pytest.mark.timeout(180)` overrides, so the new global `timeout = 30` applies cleanly to everything else.

The 2026-03-25 audit had already flagged `pytest-xdist` as net-negative; the 2026-04-24 re-benchmark re-confirms it after the session-scoped `qapp` fixture and lazy tree-sitter init landed:

- `python3 testing/run_test_shard.py fast --workers 2` failed to make progress within **>360s** (had to be killed). The two AppRun workers each pay their own Qt + tree-sitter bootstrap and serialize on offscreen-platform-plugin initialization, which dominates any parallelism win.
- Earlier numbers held: `tests/unit` with `CBCS_PYTEST_WORKERS=4` did not finish within **133s** vs **~25s** serial; `tests/integration --ignore=tests/integration/performance` with `CBCS_PYTEST_WORKERS=2` did not finish within **70s**.

Recommendations:

- Default to **serial shards** (`fast`, `integration`, `performance`, `runtime_parity`).
- Treat `--workers <count>` as a per-shard experiment knob, not a steady-state speed-up.
- Keep `tests/integration/performance` in its own serial lane (still excluded from the `integration` shard).
- The global `timeout = 30` in `pyproject.toml` is the safety net; tests legitimately needing longer carry `pytest.mark.timeout(...)` overrides instead of inflating the default. `timeout_method = "thread"` is set so a test blocked in a C-level call (Qt modal `exec_`, blocking subprocess/IO, native joins) is force-terminated at the timeout — the default `signal` method cannot interrupt those frames and would hang the whole shard.
- `tests/conftest.py` reaps leaked `run_plugin_host`/`run_runner` children after integration/runtime_parity/plugin tests and at `pytest_sessionfinish`. The `/proc` scan is cached (500ms TTL) so the fast shard no longer pays ~23s of per-test scan overhead.

