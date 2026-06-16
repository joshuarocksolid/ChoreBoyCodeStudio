# Handoff: Make the fast test shard blazing fast again

**Copy everything below the line into a new agent session.**

---

## Mission

Restore `python3 testing/run_test_shard.py fast` to a reliable **~30–50 s** agent inner loop (see `docs/TESTS.md` §5.1 and `AGENTS.md` checkpoints), with **0 failures** and **no orphaned FreeCAD subprocesses** after a run or abort.

## Situation (2026-06-01)

### What the user observed

```bash
cd /home/joshua/Documents/ChoreBoyCodeStudio && \
  timeout 170 python3 testing/run_test_shard.py fast 2>&1 | \
  tee /tmp/fast_final2.txt | rg "passed|failed|ERROR" | tail -3
```

- Feels like a **hang** because `rg` filters out pytest progress dots; nothing prints until the final summary.
- **`timeout 170` often kills the run** before completion on this machine (~3+ min to ~96%, then a long/stuck tail).
- Docs claim **~34–49 s** and **1445 passed**; collect-only now reports **1949 tests** in the fast shard — investigate doc drift vs real regression.

### Measured on Joshua’s machine (same day)

| Slice | Wall time | Notes |
|-------|-----------|--------|
| `tests/unit -m "not slow"` | **~31 s** | Healthy; matches doc budget |
| Full `fast` shard | **>180 s** to ~96%, then failures / subprocess churn | Not doc-fast |
| `tests/integration … -m "not slow"` alone | **>6 min** when aborted | ~50 tests; dominant cost |
| Stale pytest parents | **49–100+ min** elapsed | Multiple concurrent `run_tests.py` → AppRun → pytest sessions left running after aborted agent shells |

### Architecture (why it’s slow)

1. `testing/run_test_shard.py fast` → `run_tests.py` → **`/opt/freecad/AppRun -c pytest.main(...)`** (heavy bootstrap).
2. Fast shard = `tests/unit` + `tests/integration` (ignore performance), **`-m "not slow"`**.
3. **~1899 unit + ~50 integration** tests collected (17 deselected).
4. Integration tests (e.g. `test_global_history_restore`, `test_preview_tab_promotes_on_first_edit`, run/debug flows) spawn **nested AppRun** children (`run_plugin_host.py`, `run_runner.py`) under `/tmp/pytest-of-joshua/…`.
5. Tail failures (`F` at ~96%) correlated with **dozens of lingering `freecad -c` processes** and **412 MB** `/tmp/pytest-of-joshua` — looks like **subprocess leak / no teardown**, not idle pytest.

### Cleanup already done

- Killed stale pytest trees (parents like PIDs `183517`, `359355`, `786794` — multiple hour-long sessions).
- `pkill` + `rm -rf /tmp/pytest-of-joshua`.
- Verified via `ps aux | rg ChoreBoyCodeStudio/(run_tests|run_plugin_host|run_runner)` — no matches.

**Before benchmarking**, confirm the machine is clean:

```bash
ps aux | rg "ChoreBoyCodeStudio/(run_tests|run_plugin_host|run_runner)|pytest-of-joshua" | rg -v "rg "
test ! -d /tmp/pytest-of-joshua && echo clean || echo "rm -rf /tmp/pytest-of-joshua"
```

## Hypotheses to validate (priority order)

1. **Subprocess / supervisor teardown** — integration tests start plugin host + runner but do not reliably terminate on failure, timeout, or session end → zombie AppRun army, later tests starve CPU/RAM and “hang.”
2. **Tests that should be `@pytest.mark.slow`** still run in fast shard (subprocess polling, REPL lifecycle) — compare `docs/TESTS.md` slow marker intent vs actual marks in `tests/integration/`.
3. **Suite growth** — 1949 vs documented 1445 passed; separate “count inflation” from “per-test slowdown.”
4. **Parallelism unused** — `CBCS_PYTEST_WORKERS` / xdist may help unit slice; integration may need serial + fixtures, not blind `-n`.
5. **Double AppRun boot per integration test** — consider session-scoped fixtures, fakes at boundary, or a single long-lived test harness process (hard cutover; no permanent legacy fallback — see `.cursor/rules/hard_cutover_refactor.mdc`).

## Required workflow for the next agent

1. Read in order: `docs/PRD.md` (scope), `docs/DISCOVERY.md` (runtime), `docs/ARCHITECTURE.md`, `docs/TESTS.md` §5, `AGENTS.md`.
2. Establish **baseline** (machine must be clean first):

   ```bash
   cd /home/joshua/Documents/ChoreBoyCodeStudio
   START=$(date +%s)
   python3 testing/run_test_shard.py fast -- --durations=20
   echo "seconds=$(( $(date +%s) - START ))"
   ```

3. Split baselines:

   ```bash
   python3 run_tests.py -q tests/unit -m "not slow"
   python3 run_tests.py -q tests/integration --ignore=tests/integration/performance -m "not slow" --durations=15
   ```

4. Identify top offenders; fix teardown / marking / harness **before** micro-optimizing unit tests.
5. After fixes, update **`AGENTS.md`** and **`docs/TESTS.md` §9** checkpoint numbers (pass count + wall time).
6. Run `python3 testing/run_test_shard.py fast` twice back-to-back; second run must not leave `pytest-of-joshua` processes.
7. `npx pyright` if production code changes.

## Success criteria

- [ ] `python3 testing/run_test_shard.py fast` completes in **≤60 s** on this machine (stretch: **≤50 s** per docs).
- [ ] **0 failures**, stable pass count documented.
- [ ] No `/tmp/pytest-of-joshua` processes **30 s** after pytest exits.
- [ ] Failing integration tests (if any remain) fail fast with clear assertion — not 30 s × N subprocess timeouts.

## Constraints

- Python **3.9** syntax in app code (`.cursor/rules/python39_compatibility.mdc`).
- Tests via **AppRun** only (`run_tests.py`); do not add `.venv`.
- Follow **risk-first** test rules (`.cursor/rules/testing_when_to_write.mdc`) — no coverage theater.
- Prefer **hard cutover** over long-lived dual paths.
- `slow` tests stay out of fast shard; `performance` stays in its own shard.

## Key files to inspect

- `run_tests.py`, `testing/run_test_shard.py`
- `app/run/process_supervisor.py`, `app/run/run_service.py`
- `tests/integration/shell/test_global_history_restore.py`
- `tests/integration/shell/test_main_window_quick_open_integration.py`
- `tests/integration/run/test_run_service_integration.py` (already `slow` — use as pattern)
- `testing/main_window_shutdown.py` (if exists — teardown helpers)

## Anti-patterns for this effort

- Piping fast shard through `rg "passed|…"` while debugging (hides progress).
- Using `timeout 170` on a shard that legitimately needs 3+ min until fixed.
- Leaving multiple `run_tests.py` sessions running (check `ps` before blaming pytest).

## Deliverables

1. Root-cause note (1 paragraph) in PR or commit message.
2. Code/fixes for teardown, markers, or harness.
3. Updated test checkpoint in `AGENTS.md` / `docs/TESTS.md`.
4. Optional: pytest plugin or conftest `autouse` finalizer to reap AppRun children on session end (if that’s the chosen design).

---

*Handoff authored after investigation session 2026-06-01. Parent pytest PIDs that were killed: multiple sessions including `183517` (~100 min), `359355` (~50 min), `786794` (~24 min).*
