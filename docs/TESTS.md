# ChoreBoy Code Studio — Test Strategy & Current Validation

## 1) Purpose

This document captures the **active** testing strategy and commands for the shipped implementation.

It aligns with:
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/ACCEPTANCE_TESTS.md`
- `docs/TASKS.md`

## 2) Framework and markers

- Test runner: `pytest`
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
- project manifest/schema validation and project loading
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

Activate venv:

```bash
source .venv/bin/activate
```

Run full suite:

```bash
python -m pytest -v
```

Run focused suites:

```bash
python -m pytest -v tests/unit
python -m pytest -v tests/integration
python -m pytest -v tests/integration/performance
```

Type check:

```bash
python -m mypy app/ dev_launch_editor.py run_editor.py run_runner.py launcher.py
```

Expected mypy baseline in cloud VM remains 4 known pre-existing errors:
- `app/shell/status_bar.py` (`setProperty` bytes typing mismatch)
- `run_editor.py` dynamic Qt loader object typing (3 errors)

## 6) Manual acceptance validation

Manual acceptance is executed against `docs/ACCEPTANCE_TESTS.md`:

- MVP gate (`AT-01`, `AT-03`, `AT-05`, `AT-06`, `AT-07`, `AT-08`, `AT-10`, `AT-11`, `AT-12`, `AT-14`, `AT-15`, `AT-16`) validated with GUI evidence.
- Extended checks (`AT-17`, `AT-19`, `AT-20`, `AT-21`, `AT-22`, `AT-23`) validated with GUI + artifact evidence.
- `AT-18` draft recovery is validated via integration simulation test (`tests/integration/persistence/test_autosave_recovery.py`) because force-kill GUI simulation is unsafe in this cloud session.

## 7) Notes for cloud environment

- `/opt/freecad/AppRun` and `FreeCAD` module are absent in cloud VM; related diagnostics correctly report those as unavailable.
- PySide2 in cloud uses a compatibility shim to run against PySide6.

## 8) Current baseline result

At latest validation checkpoint:

- `python -m pytest -q` -> **137 passed**
- `mypy` -> **4 known pre-existing errors (expected baseline)**
