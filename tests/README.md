# Test Layout

This directory contains the executable pytest suites for ChoreBoy Code Studio.

- `unit/` holds fast tests for pure business logic and small contracts.
- `integration/` holds cross-module tests for process, filesystem, and protocol behavior.
- `runtime_parity/` holds tests that require the FreeCAD AppRun runtime on a dev machine.

## Running tests

```bash
source .venv/bin/activate && python -m pytest -v
```

Use markers from `pyproject.toml` (`unit`, `integration`, `runtime_parity`, `manual_acceptance`) to target specific layers.
