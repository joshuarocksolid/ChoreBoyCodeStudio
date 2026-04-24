# Test Layout

This directory contains the executable pytest suites for ChoreBoy Code Studio.

- `unit/` holds fast tests for pure business logic and small contracts.
- `integration/` holds cross-module tests for process, filesystem, and protocol behavior.
- `runtime_parity/` holds tests that require the FreeCAD AppRun runtime on a dev machine.

## Running tests

The canonical command catalog lives in [docs/TESTS.md §5](../docs/TESTS.md#5-core-commands). Quick reference:

```bash
python3 testing/run_test_shard.py fast            # agent inner loop, ~30s
python3 testing/run_test_shard.py integration     # pre-PR; includes slow subprocess tests
python3 testing/run_test_shard.py performance     # wall-clock threshold checks (serial)
python3 testing/run_test_shard.py runtime_parity  # AppRun-specific
python3 testing/run_test_shard.py all             # everything, used for the architecture-hygiene gate
```

Targeting a specific path or `-k` expression goes through `run_tests.py` directly:

```bash
python3 run_tests.py tests/unit/run/test_run_service.py
python3 run_tests.py -k test_project_service
```

`run_tests.py` automatically applies `--import-mode=importlib` and `QT_QPA_PLATFORM=offscreen`; do not pass them by hand. Markers from `pyproject.toml` (`unit`, `integration`, `runtime_parity`, `manual_acceptance`, `slow`) can still be combined with `-m` for ad-hoc filtering, but prefer the shard names above for routine work.
