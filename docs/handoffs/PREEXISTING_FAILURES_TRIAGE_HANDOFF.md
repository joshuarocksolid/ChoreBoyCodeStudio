# Handoff: Triage & fix pre-existing test/tooling failures (post Fast-Shard-Recovery)

## Context
The `fast` shard (`python3 testing/run_test_shard.py fast`) was just restored to a clean
~54–68s / 1949-passed / 0-failures state (see the latest checkpoint in `AGENTS.md` and
`docs/TESTS.md` §9). During that work, three problem clusters were observed but deliberately
left out of scope because they live outside the fast shard. Your job is to **triage each cluster,
decide real-regression vs. environmental, and fix or correctly quarantine** them.

Read first (per `.cursor/rules/documentation_navigation.mdc`): `docs/DISCOVERY.md` (runtime/AppRun
facts, esp. debug transport + Cloud limitations), `docs/TESTS.md` §5/§9, `AGENTS.md`.
Honor the testing rules: `.cursor/rules/testing_when_to_write.mdc`,
`.cursor/rules/python39_compatibility.mdc`, and the hard-cutover rule. Do NOT add tests to chase
coverage, and do NOT mask real regressions with skips.

## How to run the relevant shards
```bash
cd /home/joshua/Documents/ChoreBoyCodeStudio
python3 testing/run_test_shard.py integration     # ~37-43s, surfaces Cluster A
python3 testing/run_test_shard.py performance      # surfaces Cluster B
npx pyright                                        # surfaces Cluster C
```
After any subprocess-spawning run, confirm no orphans 30s later:
`ps aux | rg "run_plugin_host|run_runner" | rg -v rg` (the `conftest.py` reaper should keep this empty).

---

## Cluster A — Debug-session integration failures (2 failures, `slow`-marked)
Failing IDs:
- `tests/integration/debug/test_debug_session_integration.py::test_debug_session_tracks_structured_pause_and_resume_events`
- `tests/integration/debug/test_breakpoint_stepping_flow.py::test_debug_flow_pauses_then_steps_and_finishes`

Evidence gathered: both fail for the **same root cause** — the debug channel never emits a
`"stopped"`/paused `ProcessEvent` within the wait window on this AppRun environment, so the
pause assertion times out. The sibling test `test_breakpoint_stepping_flow.py` already contains a
graceful-skip path ("Debug transport did not emit events in this environment ... known Cloud/AppRun
limitation") that triggers when `_has_debug_events()` is false — but the failing path is reached when
*some* debug events arrive yet no `stopped` event does. The recovery work did NOT touch the debug
transport (`app/run/run_service.py`, `process_supervisor.py`, `run_runner.py`), so this is
very likely pre-existing/environmental — **but confirm, don't assume.**

Triage steps:
1. Run each test in isolation through AppRun and capture the emitted `ProcessEvent` stream
   (event_type/payload) to see exactly which events arrive vs. don't.
2. Determine: is the debugpy/debug transport genuinely non-functional in this AppRun build, or is
   there a real regression in how `stopped` events are parsed/forwarded?
3. If genuinely environmental: make the two tests degrade the **same way** as the existing skip in
   `test_breakpoint_stepping_flow.py` — i.e. skip with a clear "known Cloud/AppRun debug-transport
   limitation" message **only** when debug events fail to arrive, so machines where the channel works
   still get real assertions. Keep the guard tight; never blanket-skip.
4. If it's a real regression in event handling, fix the transport/parsing instead and keep the assertions.

---

## Cluster B — `local_history` performance regression (documented, unverified this session)
File: `tests/integration/performance/test_local_history_performance.py`
(`test_list_global_history_files_500_timelines_under_250ms`, 250ms budget).

`AGENTS.md` / `docs/TESTS.md` record "**2 pre-existing failures** (`test_local_history_performance`
regressions tracked separately)" in the `performance` shard. NOTE: the file currently shows a single
test function, so the "2 failures" count is **stale doc carry-over** — re-run the performance shard to
get the real current state before doing anything.

Triage steps:
1. Run `python3 testing/run_test_shard.py performance` and record the actual pass/fail list + timings.
2. If `test_local_history_performance` fails, profile the global-history listing path it exercises
   (likely `app/.../local_history` listing) to find the regression vs. the 250ms budget.
3. Decide: real perf regression to fix, or an over-tight threshold on this machine. If you adjust the
   threshold, justify it with measured numbers and update the doc; if you fix code, keep the budget.
4. Reconcile the doc count (1 test vs. claimed "2 failures") so `AGENTS.md`/`docs/TESTS.md` match reality.

---

## Cluster C — pyright reports ~1751 errors (documented baseline is 0)
`npx pyright` currently emits ~1751 errors, all PySide2 stub-resolution noise (e.g. inherited Qt signals
like `textChanged`/`timeout` on custom widget subclasses such as `app/.../segmented_control.py`) in files
that were never touched by the recovery work. The documented baseline in `AGENTS.md` / `docs/TESTS.md`
is **0 errors, 0 warnings**. The recovery work confirmed none of its edited lines introduce new errors,
so this is an environment/config drift, not a code regression — **but it makes pyright unusable as a gate.**

Triage steps:
1. Confirm the `vendor` symlink resolves and PySide2 is found via `/opt/freecad/usr/lib/python3.11/
   site-packages` (`pyrightconfig.json` extraPaths). Compare against the env that produced the 0-error
   baseline.
2. Determine why Qt inherited-signal stubs no longer resolve (PySide2 stub availability, pyright version,
   or extraPaths/SOABI drift between cp39/cp311 vendor profiles — see `AGENTS.md` "Vendored dependencies").
3. Restore a clean `npx pyright` (0/0/0) by fixing config or stub resolution. Do NOT suppress errors
   blanketly. Re-verify `npx pyright -p pyrightconfig.tests.json` too.

---

## Definition of done
- Each cluster is either fixed at the root, or correctly quarantined (tight, justified skip) with a
  one-line rationale referencing `docs/DISCOVERY.md` where it's an AppRun/Cloud limitation.
- `integration`, `performance`, `runtime_parity` shards run with a known, documented pass/skip/fail
  state; `fast` shard stays green (re-run it to confirm no collateral).
- `npx pyright` is back to its documented baseline, or the new baseline is explained and recorded.
- `AGENTS.md` §"Latest checkpoint" and `docs/TESTS.md` §9 updated to match measured reality (no stale
  counts). Note which themes/shards were and weren't verified.
- No orphaned `run_plugin_host`/`run_runner` processes 30s after any run.
