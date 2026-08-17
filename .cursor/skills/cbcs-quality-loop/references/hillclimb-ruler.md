# Frozen hillclimb ruler

Do not edit this command after the first honest baseline without starting a new `decisions.tsv` section.

## Retired freeze (M1 / launch-runtime)

`measure-m1` — series closed at 1/1. Do not mix those numbers with the series below.

## Current freeze (M1–M6 smoke, series 2)

Series 1 used a 3s sleep after Refresh and scored 5/6 (M4 empty). Refresh restarts in-flight collect. Series 2 polls `#shell.testExplorer.tree` via `control-cbcs wait`.

```bash
.cursor/skills/cbcs-quality-loop/scripts/measure-smoke \
  --repo /Users/local/Projects/ChoreBoyCodeStudio
```

What it does, in one isolated session:

1. M1 — `prove-launch` (window + `Runtime ready`)
2. M2 — welcome visible; **Help → Runtime Onboarding** opens
3. M3 — open smoke fixture; Run Active File; run log contains `cbcs-smoke-token`
4. M4 — Test Explorer tree has at least one node (poll; do not Refresh-restart)
5. M5 — Light / Dark / HC Light / HC Dark; chip still `Runtime ready` after each
6. M6 — edit `main.py` dirty, Save, chip not modified

Writes `measure.json` with per-step ok/detail. Stops the session; artifacts remain.

Metric: `passed/total` out of 6. Secondary: `elapsed_s` among 6/6 runs.

Stop predicate: 6/6 on two consecutive isolated runs **and** at least 8 logged iterations in this series.

Series 2 closed 2026-08-17: two consecutive 6/6, then 8 logged rows. Working payload is bare `pytest.main(...)` (no `SystemExit`). Sensitivity: wrapping `pytest.main` in `SystemExit` drops M4 to 5/6.

## Gate

```bash
python3 testing/run_test_shard.py fast
```

Only when a Linux AppRun is on this machine. Otherwise `gate=skipped-no-apprun`.

## Log

`~/ChoreBoy/artifacts/verify-cbcs/decisions.tsv`

Columns: `id`, `hypothesis`, `change`, `before`, `after`, `delta`, `gate`, `verdict`, `note`, `artifacts`
