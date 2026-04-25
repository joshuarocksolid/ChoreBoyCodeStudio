# ChoreBoy Code Studio — Test Strategy & Current Validation

## 1) Purpose

This document captures the **active** testing strategy and commands for the shipped implementation.

It aligns with:

- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/TASKS.md`

## 2) Framework and markers

- Test runner: `pytest` (shipped inside the FreeCAD AppRun runtime)
- Markers (defined in `pyproject.toml`):
  - `unit`
  - `integration`
  - `runtime_parity`
  - `manual_acceptance`
  - `slow` — wall-time exceeds the agent fast-lane budget (subprocess polling, debug-session waits). Carries a `pytest.mark.timeout(180)` override; excluded from the `fast` shard.

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

## 5) Core commands

This section is the canonical "how to run tests" instruction. Other docs (`AGENTS.md`, `tests/README.md`, `docs/SMOKE_WORKFLOW.md`, the per-task `Validation method:` snippets in `docs/TASKS.md`) point here.

### 5.1 Agent inner loop — fast shard (~30 s)

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

- Tests run through `/opt/freecad/AppRun` using real PySide2 — the same Qt binding used in production.
- `QT_QPA_PLATFORM=offscreen` is set by default in `run_tests.py` so tests do not require a display server.

## 9) Current baseline result

Latest validation checkpoint (2026-04-25, end-to-end maintainability refactor branch):

- `python3 testing/run_test_shard.py fast` -> **~36-45s wall time**, passed.
- `python3 testing/run_test_shard.py integration` -> **~43s wall time**, passed.
- `python3 testing/run_test_shard.py runtime_parity` -> **~6s wall time**, passed.
- `python3 testing/run_test_shard.py performance` -> baseline pass in this branch.
- `npx pyright` -> 0 errors, 0 warnings, 0 informations.
- `npx pyright -p pyrightconfig.tests.json` -> 0 errors, 0 warnings, 0 informations.
- `AT-72` remains the required manual confirmation step when touched shell/editor surfaces need light/dark validation.

Compared to the pre-refactor baseline of `~92s` for the full suite, the agent fast lane is now **~2.9x faster** while still exercising every Qt-touching unit test and every non-slow integration test.

## 10) Test speed notes

Speed audit re-run on 2026-04-24 after the fast-lane refactor:

- `python3 testing/run_test_shard.py fast` -> **~32s** wall time (1354 passed, 17 deselected via `-m "not slow"`, 1 skipped). This is the agent default loop.
- The full pre-refactor suite (`python3 run_tests.py`) was ~92s; the fast shard is roughly **2.9x** faster while still exercising every Qt-touching unit test and every non-slow integration test.
- The `slow` marker now scopes the four worst offenders (`test_process_supervisor_integration`, `test_run_service_integration`, `test_breakpoint_stepping_flow`, `test_debug_session_integration`) with `pytest.mark.timeout(180)` overrides, so the new global `timeout = 30` applies cleanly to everything else.

The 2026-03-25 audit had already flagged `pytest-xdist` as net-negative; the 2026-04-24 re-benchmark re-confirms it after the session-scoped `qapp` fixture and lazy tree-sitter init landed:

- `python3 testing/run_test_shard.py fast --workers 2` failed to make progress within **>360s** (had to be killed). The two AppRun workers each pay their own Qt + tree-sitter bootstrap and serialize on offscreen-platform-plugin initialization, which dominates any parallelism win.
- Earlier numbers held: `tests/unit` with `CBCS_PYTEST_WORKERS=4` did not finish within **133s** vs **~25s** serial; `tests/integration --ignore=tests/integration/performance` with `CBCS_PYTEST_WORKERS=2` did not finish within **70s**.

Recommendations:

- Default to **serial shards** (`fast`, `integration`, `performance`, `runtime_parity`).
- Treat `--workers <count>` as a per-shard experiment knob, not a steady-state speed-up.
- Keep `tests/integration/performance` in its own serial lane (still excluded from the `integration` shard).
- The global `timeout = 30` in `pyproject.toml` is the new safety net; tests legitimately needing longer carry `pytest.mark.timeout(...)` overrides instead of inflating the default.

