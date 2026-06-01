# ChoreBoy Code Studio

A Python project editor and runner built for the ChoreBoy desktop environment. Code Studio runs inside FreeCAD's AppRun runtime, uses a separate runner process for user code, and ships with debugging, plugins, and project templates.

## Quick start

```bash
./scripts/setup_freecad_dev.sh    # first time: ~/opt/freecad/AppRun (Python 3.9)
./scripts/setup_vendor_py39.sh    # ChoreBoy-parity vendor bundle
./run_dev.sh
```

Cloud / Python 3.11 development: see [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md).

## Run tests

```bash
python3 testing/run_test_shard.py fast
```

Full command catalog: [`docs/TESTS.md` §5](docs/TESTS.md#5-core-commands).

## Documentation map

| Document | Purpose |
|----------|---------|
| [`docs/PRD.md`](docs/PRD.md) | Product goals, scope, workflows |
| [`docs/DISCOVERY.md`](docs/DISCOVERY.md) | Runtime facts and platform constraints |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Module boundaries and contracts |
| [`docs/TASKS.md`](docs/TASKS.md) | Implementation backlog |
| [`docs/ACCEPTANCE_TESTS.md`](docs/ACCEPTANCE_TESTS.md) | Manual MVP acceptance |
| [`docs/TESTS.md`](docs/TESTS.md) | Test strategy and commands |
| [`docs/TEST_AUDIT.md`](docs/TEST_AUDIT.md) | Test suite audit index |
| [`docs/manual/README.md`](docs/manual/README.md) | End-user manual source |
| [`CHANGELOG.md`](CHANGELOG.md) | Release history |
| [`AGENTS.md`](AGENTS.md) | Agent/CI operating rules |

## Release smoke testing

[`docs/SMOKE_WORKFLOW.md`](docs/SMOKE_WORKFLOW.md) — automated shards plus a short manual GUI checklist. Record results in [`smoke_test_results.md`](smoke_test_results.md).
