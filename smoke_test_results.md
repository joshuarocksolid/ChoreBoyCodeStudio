# Smoke Test Results — TEMPLATE

> Replace this file contents on each smoke run. See [`docs/SMOKE_WORKFLOW.md`](docs/SMOKE_WORKFLOW.md) and [`docs/SMOKE_TEST_REPORT.md`](docs/SMOKE_TEST_REPORT.md).

**Release candidate / branch:** _e.g. main @ abc1234_
**Tester / environment:** _ChoreBoy production | Cloud DISPLAY | local ~/opt/freecad_
**Date:** YYYY-MM-DD

## Layer 1 — Automated

| Shard | Result | Notes |
|-------|--------|-------|
| `python3 testing/run_test_shard.py fast` | PASS / FAIL | |
| `python3 testing/run_test_shard.py runtime_parity` | PASS / SKIP | |
| `python3 testing/run_test_shard.py integration` | PASS / FAIL | |
| `python3 testing/run_test_shard.py performance` | PASS / FAIL | 2 known local-history perf failures OK to note |

## Layer 2 — Manual

| Step | Result | Notes |
|------|--------|-------|
| M1 Launch | PASS / FAIL / WARN | |
| M2 Welcome / onboarding | PASS / FAIL / WARN | |
| M3 Run / preflight | PASS / FAIL / WARN | |
| M4 Test explorer | PASS / FAIL / WARN | |
| M5 Themes (Light, Dark, HC Light, HC Dark) | PASS / FAIL / WARN | |
| M6 Spot-checks | PASS / FAIL / WARN | |

## Issues found

- _(none)_
