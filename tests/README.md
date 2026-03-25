# Test Layout

This directory contains the executable pytest suites for ChoreBoy Code Studio.

- `unit/` holds fast tests for pure business logic and small contracts.
- `integration/` holds cross-module tests for process, filesystem, and protocol behavior.
- `runtime_parity/` holds tests that require the FreeCAD AppRun runtime on a dev machine.

## Running tests

```bash
python3 run_tests.py -v
```

Use markers from `pyproject.toml` (`unit`, `integration`, `runtime_parity`, `manual_acceptance`) to target specific layers.

For faster local feedback and CI-style process sharding, use the named shard runner:

```bash
python3 testing/run_test_shard.py unit
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py performance
python3 testing/run_test_shard.py runtime_parity
```

- `integration` excludes `tests/integration/performance` so timing-sensitive assertions stay isolated.
- `performance` should remain a dedicated serial invocation.
- `--workers <count>` is available for targeted experiments, but serial shards are the default because measured `xdist` pilots were slower than the serial shard timings in this repo.
