# ChoreBoy Code Studio — Testing Strategy (Setup Baseline)

## 1. Purpose

This document defines the initial testing framework setup for the project before implementation code exists.

Current scope is setup only:
- configure automated testing conventions
- establish test directory layout
- document execution cadence and gates
- do not add real test cases yet

## 2. Core Constraints

Testing strategy must remain aligned with the canonical docs:
- `AGENTS.md`
- `docs/PRD.md`
- `docs/DISCOVERY.md`
- `docs/ARCHITECTURE.md`
- `docs/ACCEPTANCE_TESTS.md`

Key constraints to preserve:
- target runtime is FreeCAD AppRun (`/opt/freecad/AppRun`), not normal system Python
- user project code must run in a separate runner process
- UI-heavy behavior is validated primarily through manual acceptance flows
- supportability artifacts (logs, traceback, explicit failure behavior) are first-class

## 3. Framework Baseline

Automated framework:
- `pytest` as the default test runner
- built-in `unittest.mock` for unit-test isolation only

Deferred until implementation matures:
- broad UI automation (`pytest-qt`, etc.)
- strict coverage thresholds as a blocking gate

Configured markers in `pyproject.toml`:
- `unit`
- `integration`
- `runtime_parity`
- `manual_acceptance`

## 4. Test Layout

The repository test scaffold is:
- `tests/unit/`
- `tests/integration/`
- `tests/runtime_parity/`

Guidance:
- `unit` for pure business logic and deterministic contracts
- `integration` for editor/runner, filesystem, and protocol boundaries
- `runtime_parity` for tests that require `/opt/freecad/AppRun` on the dev machine

## 5. Test Pyramid and Gate Model

1. Unit tests (fast local feedback)
2. Integration tests (boundary and contract confidence)
3. Manual acceptance checks on target-like/runtime-parity behavior

Manual acceptance remains the release confidence gate for UI workflows, per `docs/ACCEPTANCE_TESTS.md`.

## 6. Execution Cadence

During active development:
- run unit tests manually and frequently
- run integration tests manually before merging larger slices
- run runtime-parity tests manually when touching runner/runtime-sensitive behavior

Before release candidates:
- execute the acceptance checklist manually (`AT-01` through `AT-16` minimum)

## 7. Local Commands (When Coding Starts)

These commands are documented now for consistency; they are not required to run during setup.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip pytest
pytest -m unit
pytest -m integration
pytest -m runtime_parity
```

If runtime-parity tests require explicit AppRun location, run with:

```bash
CBCS_APPRUN=/opt/freecad/AppRun pytest -m runtime_parity
```

## 8. Traceability Starter (Tasks -> Test Layers)

Initial mapping to keep aligned while implementation starts:
- `T02` to `T04`, `T14`, `T15`: mostly `unit` coverage first
- `T16` to `T22`: primarily `integration` and `runtime_parity` coverage
- acceptance correlation for core vertical slice: `AT-10` to `AT-16`

Update this mapping as tasks move from TODO to DONE.

## 9. Setup Status

Completed in this setup slice:
- pytest configuration added in `pyproject.toml`
- test directory scaffold added under `tests/`
- this strategy document created

Intentionally deferred:
- writing actual tests
- running test suites
