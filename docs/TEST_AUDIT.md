# Test Suite Audit — Standing Reference

## Purpose

This document is the maintained index for **how and why** the ChoreBoy Code Studio test suite is structured. It satisfies the link from [`AGENTS.md`](../AGENTS.md) and complements the command catalog in [`docs/TESTS.md`](TESTS.md) §5.

Before adding tests, apply the risk-first gate in [`.cursor/rules/testing_when_to_write.mdc`](../.cursor/rules/testing_when_to_write.mdc). For anti-patterns to avoid, see [`.cursor/rules/test_anti_patterns.mdc`](../.cursor/rules/test_anti_patterns.mdc).

## Suite layout

| Directory | Role |
|-----------|------|
| `tests/unit/` | Fast, in-process contract and business-logic tests |
| `tests/integration/` | Cross-module filesystem, subprocess, and protocol boundaries |
| `tests/runtime_parity/` | AppRun-specific checks (skip clearly when AppRun is missing) |

Shard commands (canonical): [`docs/TESTS.md` §5](TESTS.md#5-core-commands).

## Marker taxonomy

Defined in [`pyproject.toml`](../pyproject.toml):

| Marker | Meaning |
|--------|---------|
| `unit` | Fast isolated tests |
| `integration` | Multi-component real-boundary tests |
| `runtime_parity` | Requires FreeCAD AppRun or equivalent |
| `manual_acceptance` | Links to manual scenarios in [`ACCEPTANCE_TESTS.md`](ACCEPTANCE_TESTS.md) — not used in pytest files by design |
| `slow` | Subprocess polling, debug-session waits; excluded from `fast` shard |
| `performance` | Wall-clock benchmarks under `tests/integration/performance/`; excluded from default `run_tests.py` |

## Tooling decisions

Summarized from [`docs/deslop/TEST_TOOLING_AUDIT.md`](deslop/TEST_TOOLING_AUDIT.md):

- **Pyright** is the active static checker (`npx pyright`, `npx pyright -p pyrightconfig.tests.json`).
- **Ruff / Vulture / Radon / Lizard** are deferred until a concrete recurring failure class justifies them.
- **pytest** runs via AppRun through [`run_tests.py`](../run_tests.py) with vendor-bundled pytest (see [`docs/TESTS.md`](TESTS.md) §2).

## Test hygiene (ongoing)

- Assert **public behavior** (signals, model state, return values) — not private widget names or `_private_attr` internals.
- Delete tests when refactors remove the conditions they guarded.
- Prefer parametrization over copy-paste variants.
- Do not pin constants to literals, snapshot `to_dict()` at non-boundaries, or mock-dominate integration seams.

## Known pre-existing failures / skips

| Area | Status | Notes |
|------|--------|-------|
| `tests/integration/performance/test_local_history_performance.py` | 2 pre-existing failures | Tracked separately; run via `python3 testing/run_test_shard.py performance` |
| AppRun missing | runtime_parity tests self-skip | Expected on machines without `/opt/freecad/AppRun` |

Refresh this table when the [`AGENTS.md`](../AGENTS.md) checkpoint block is updated.

## Validation reference

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py performance
python3 testing/run_test_shard.py runtime_parity
npx pyright
npx pyright -p pyrightconfig.tests.json
```

## Last updated

**2026-06-01** — `main` branch. Checkpoint counts: [`AGENTS.md`](../AGENTS.md).
