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

Run full suite:

```bash
python3 run_tests.py -v --import-mode=importlib
```

Run focused suites:

```bash
python3 run_tests.py -v --import-mode=importlib tests/unit
python3 run_tests.py -v --import-mode=importlib tests/integration
python3 run_tests.py -v --import-mode=importlib tests/integration/performance
```

Fast local feedback:

```bash
python3 testing/run_test_shard.py unit
python3 testing/run_test_shard.py unit -- -k test_project_service
```

Named shards for local or CI-style parallel jobs:

```bash
python3 testing/run_test_shard.py unit
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py performance
python3 testing/run_test_shard.py runtime_parity
```

- `integration` intentionally excludes `tests/integration/performance` so timing-sensitive checks can stay in their own serial lane.
- `performance` should remain a dedicated serial invocation because those tests assert wall-clock thresholds.
- `--workers <count>` is available for targeted experiments through `CBCS_PYTEST_WORKERS`, for example `python3 testing/run_test_shard.py unit --workers 4`, but serial shards remain the default.

Run static analysis:

```bash
npx pyright
```

## 6) Architecture hygiene validation gate

Before future editor-intelligence feature work, run the full automated gate and then execute `AT-72`:

```bash
python3 run_tests.py -v --import-mode=importlib
npx pyright
```

The full automated suite covers the unit, integration, runtime-parity, performance, and theme-related assertions that back the architecture-hygiene phase.

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

At latest validation checkpoint:

- `python3 run_tests.py -q --import-mode=importlib` -> **1189 passed, 1 skipped** (`tests/unit/editors/test_syntax_highlighters.py` skips when the optional SQL tree-sitter grammar is not vendored)
- `npx pyright` -> **0 errors, 0 warnings, 0 informations**
- `AT-72` remains the required manual confirmation step when touched shell/editor surfaces need light/dark validation.

## 10) Test speed notes

Speed audit measurements captured on 2026-03-25 on the local dev host showed:

- full suite wall time at roughly **156s** on the current branch
- `tests/unit` dropping from roughly **79s** to **25s** after trimming an oversized syntax-highlighting fixture
- `tests/integration` at roughly **75s**, with `tests/integration/performance` accounting for about **35s** of that total
- `tests/runtime_parity` at roughly **4s**

The same audit also piloted `pytest-xdist`, which is already available in the AppRun runtime:

- `tests/unit` with `CBCS_PYTEST_WORKERS=4` did not finish within **133s**, which was substantially slower than the **25s** serial shard
- `tests/integration --ignore=tests/integration/performance` with `CBCS_PYTEST_WORKERS=2` did not finish within **70s**, which was already slower than the roughly **40s** serial non-performance portion

Recommendation:

- prefer shard-level parallelism first (`unit`, `integration`, `performance`, `runtime_parity`)
- keep `pytest-xdist` opt-in only for targeted experiments on narrowly scoped subsets
- keep `tests/integration/performance` in its own serial lane
