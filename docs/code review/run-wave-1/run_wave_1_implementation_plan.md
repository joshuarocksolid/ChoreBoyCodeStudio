# Run Wave 1 — End-to-End Implementation Plan

Status: **implementation-ready** (Phase 2 execution)  
Baseline (re-verified): `4a5c2c7672305168bcad60f3f65dcdb506caf152`  
Source review: [`run_wave_1_thermo_review_2026-05-25.md`](run_wave_1_thermo_review_2026-05-25.md)  
Strategy doc: [`run_wave_1_remediation_plan.md`](run_wave_1_remediation_plan.md)  
Integration themes: [`_findings/TN-RUN-INTEG.md`](_findings/TN-RUN-INTEG.md)

This plan is the **executable** companion to the remediation plan: every CC-RUN theme CC-01 … CC-25 maps to concrete steps, files, PRs (`RUN-R-01` … `RUN-R-25`), verification gates, and dependencies.

---

## 1. Program scope and completion definition

### In scope

- Close all **P0** themes CC-01 … CC-06 (mandatory).
- Close all **P1** themes CC-07 … CC-20 (mandatory for wave ACCEPT).
- Close or disposition **P2** themes CC-21 … CC-25 per §14.
- Preserve grep gates from RUN-R-01; extend as themes close.

### Program complete when (all must pass)

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | CC-01 … CC-06 closed with evidence | P0 closure checklist (§4) |
| 2 | CC-07 … CC-20 closed | CC matrix (§3) status = closed |
| 3 | CC-21 … CC-25 disposition satisfied | §14 |
| 4 | No `app/` Python file ≥1000 LOC | `find app -name '*.py' -exec wc -l {} + \| awk '$1>=1000'` → empty |
| 5 | `debug_runner.py` ≤30 LOC (facade only) | grep gate test |
| 6 | Pytest discovery + runner share `PytestLaunchPlan` | grep gate test |
| 7 | Fast shard + integration (run/debug) green | §16 |
| 8 | `npx pyright` → 0 errors | §16 |
| 9 | Four-theme manual acceptance for UI-touching PRs | §17 |
| 10 | Closure doc written | `run_wave_1_remediation_closure_YYYY-MM-DD.md` |

### P0-only milestone (optional early ship gate)

Ship **P0 milestone** after RUN-R-02 … RUN-R-07 land (CC-01 … CC-06 verified @ HEAD). P1 themes remain mandatory before wave ACCEPT.

---

## 2. Non-negotiable rules (every PR)

1. **Hard cutover** — delete old paths in the same PR; no `try new / fallback old` chains.
2. **Python 3.9** syntax; no dot-prefixed storage paths.
3. **`debug_runner.py` stays a facade** — logic in `app/runner/debug/*`.
4. **Pytest launch** — discovery and runner must use `build_pytest_launch_plan` / `build_pytest_command`.
5. **Pause authority** — derive from `DebugSession` after queue drain; never duplicate on `RunService`.
6. **Four-theme validation** for shell UI PRs — record in PR summary.
7. **Tests** only when risk-first gate applies (transport lifecycle, re-entrant start, pytest parity, subprocess blast radius).

---

## 3. CC theme closure matrix (@ HEAD `4a5c2c7`)

Status key: **closed** | **partial** | **open** | **waived**

| CC | Pri | Status @ HEAD | Primary RUN-R | Key files | Verification |
|----|-----|---------------|---------------|-----------|--------------|
| CC-01 | P0 | **closed** | RUN-R-02 | `debug_transport.py`, `command_loop.py`, `run_service.py` | lifecycle + mid-pause + shutdown-order fix |
| CC-02 | P0 | **closed** | RUN-R-03 | `debug_session.py`, `run_session_controller.py`, `actions.py` | `_is_debug_paused` removed; `test_refresh_action_states_derives_pause_from_debug_execution_state` |
| CC-03 | P0 | **closed** | RUN-R-04 | `run_service.py`, `process_supervisor.py` | `_assert_idle()` first; second start preserves transport |
| CC-04 | P0 | **closed** | RUN-R-05 | `app/pytest/launch_plan.py` | grep gate + `test_pytest_*` |
| CC-05 | P0 | **closed** | RUN-R-06 | `runner_service.py`, `discovery_service.py`, `test_runner_workflow.py` | `-q -rA` stdout → `parse_test_results` → explorer outcomes |
| CC-06 | P0 | **closed** | RUN-R-02 | `debug_transport.py`, `run_service.py` | shutdown-before-close fix; threaded stress + RunService close test |
| CC-07 | P1 | **closed** | RUN-R-08 | `run_manifest.py`, `debug_breakpoints.py`, `command_loop.py` | Breakpoint round-trip SSOT |
| CC-08 | P1 | **closed** | RUN-R-04 | `run_service.py`, `launch_context.py` | Manifest rollback on failed launch |
| CC-09 | P1 | open | RUN-R-09 | `run_service.py`, `run_session_controller.py`, shell mirrors | Single session store |
| CC-10 | P1 | **closed** | RUN-R-10 | `debug_runner.py`, `app/runner/debug/*` | facade ≤30 LOC |
| CC-11 | P1 | **closed** | RUN-R-11 | `app/pytest/*` | no `app/run/pytest_*` |
| CC-12 | P1 | partial | RUN-R-12 | `run_service.py`, `launch_context.py` | `HostProcessManager` gone; `start_run` slim |
| CC-13 | P1 | open | RUN-R-13 | `run_manifest.py` | Mode-aware validation; tuple containers |
| CC-14 | P1 | open | RUN-R-14 | `repl_control.py`, `repl_protocol.py` | Protocol validation |
| CC-15 | P1 | open | RUN-R-15 | `debug_session.py` | `continued` clears inspector |
| CC-16 | P1 | open | RUN-R-16 | `run_launch_workflow.py` | Split below 500 LOC |
| CC-17 | P1 | open | RUN-R-17 | `run_debug_presenter.py`, restart paths | Exit-gated restart |
| CC-18 | P1 | open | RUN-R-18 | `BreakpointStore`, shell workflows | No dict alias injection |
| CC-19 | P1 | partial | RUN-R-19 | `run_service.py`, `repl_session_manager.py` | REPL launch SSOT in run layer |
| CC-20 | P1 | open | RUN-R-20 | `console_model.py`, `exit_status.py` | Relocate to shell |
| CC-21 | P2 | open | RUN-R-21 | `debug_session.py` | Legacy reducer removed |
| CC-22 | P2 | open | RUN-R-22 | supervisor, repl_control, runner bootstrap | bare `except` ≤8 |
| CC-23 | P2 | partial | RUN-R-23 | `tests/unit/debug/test_debug_transport_lifecycle.py` | Expand lifecycle suite |
| CC-24 | P2 | partial | RUN-R-24 | `outcome_types.py`, `problem_parser.py` | Typed outcomes end-to-end |
| CC-25 | P2 | open | RUN-R-25 | `clear_console_policy.py`, runner hints | Unified clear policy |

**@ HEAD summary:** 10 closed (CC-01, CC-02, CC-03, CC-04, CC-05, CC-06, CC-07, CC-08, CC-10, CC-11), 4 partial, 11 open — **P0 milestone verified @ `57aac8d`**; RUN-R-09 (Wave 2) next.

---

## 4. P0 blocker closure checklist

| CC | Done when | Command / test |
|----|-----------|----------------|
| **CC-01** | Runner exits on transport EOF mid-pause; no unbounded `queue.get()` | `python3 run_tests.py tests/unit/debug/test_debug_transport_lifecycle.py` + new integration |
| **CC-02** | Toolbar/panel/breakpoint sync agree on pause state | Integration debug session test |
| **CC-03** | Second `start_run` raises; first transport preserved | `python3 run_tests.py tests/unit/run/test_run_service.py -k idle` |
| **CC-04** | Discovery + runner share launch plan | `python3 run_tests.py tests/unit/run/test_run_wave_grep_gates.py -k launch_plan` |
| **CC-05** | Run All updates explorer from `-q -rA` stdout | `test_test_runner_workflow` characterization |
| **CC-06** | Transport error closes editor server; send races guarded | lifecycle + threaded stress test |

---

## 5. RUN-R PR map (25 items)

| RUN-R | Wave | CC themes | Scope summary | Gate |
|-------|------|-----------|---------------|------|
| **RUN-R-01** | 0 | CC-23 partial | Re-baseline @ HEAD; remediation + implementation plans; grep gates | `test_run_wave_grep_gates.py` |
| **RUN-R-02** | 1 | CC-01, CC-06 | Transport EOF/write → error path; server close; runner `_transport_failed` | lifecycle + integration |
| **RUN-R-03** | 1 | CC-02 | Pause authority SSOT via `DebugSession` | integration toolbar/panel |
| **RUN-R-04** | 1 | CC-03, CC-08 | Atomic `start_run`; manifest rollback | unit + integration |
| **RUN-R-05** | 1 | CC-04 | Pytest launch parity tests (discovery vs runner) | parity parametrized test |
| **RUN-R-06** | 1 | CC-05 | Explorer outcome pipeline with production stdout | workflow test |
| **RUN-R-07** | 1 | — | P0 milestone verification + doc update | §4 all green |
| **RUN-R-08** | 2 | CC-07 | Breakpoint wire SSOT / manifest codec | round-trip tests |
| **RUN-R-09** | 2 | CC-09 | `RunSessionStore` single mirror | integration exit/restart |
| **RUN-R-10** | 2 | CC-10 | *(closed @ HEAD)* — preserve grep gate | grep gate |
| **RUN-R-11** | 2 | CC-11 | *(closed @ HEAD)* — preserve grep gate | grep gate |
| **RUN-R-12** | 2 | CC-12 | Slim `start_run` coordinator | LOC + unit tests |
| **RUN-R-13** | 2 | CC-13 | Manifest validation + tuple containers | mode rejection tests |
| **RUN-R-14** | 2 | CC-14 | REPL protocol typing + validation | `test_repl_protocol.py` |
| **RUN-R-15** | 2 | CC-15 | Session reducer: `continued` clears inspector | unit reducer tests |
| **RUN-R-16** | 3 | CC-16 | Split `run_launch_workflow.py` | each module <400 LOC |
| **RUN-R-17** | 3 | CC-17 | Exit-gated restart; surface `ALREADY_RUNNING` | slow integration |
| **RUN-R-18** | 3 | CC-18 | `BreakpointStore` encapsulation | store invariant tests |
| **RUN-R-19** | 2 | CC-19 | REPL launch SSOT in run layer | import graph gate |
| **RUN-R-20** | 3 | CC-20 | Relocate presentation modules to shell | import graph |
| **RUN-R-21** | 5 | CC-21 | Remove legacy debug reducer paths | grep + unit |
| **RUN-R-22** | 5 | CC-22 | Narrow bare `except Exception:` | count ≤8 |
| **RUN-R-23** | 4 | CC-23 | Expand transport lifecycle suite | full lifecycle module |
| **RUN-R-24** | 4 | CC-24 | Typed test outcomes end-to-end | pyright strict on pytest pkg |
| **RUN-R-25** | 3 | CC-25 | Unified clear-console policy | characterization tests |

**Parallelism:** RUN-R-02 before RUN-R-03 (transport before pause integration). RUN-R-08 unblocks runner breakpoint deletes. RUN-R-16 … RUN-R-20 can parallelize by module after P0 milestone.

---

## 6. Re-baseline metrics (@ `4a5c2c7`)

| Metric | Value |
|--------|------:|
| `app/run/` + `app/runner/` + `app/debug/` LOC | 4,792 |
| `debug_runner.py` LOC | 8 |
| `run_service.py` LOC | 372 |
| `process_supervisor.py` LOC | 326 |
| `run_manifest.py` LOC | 480 |
| `debug_session.py` LOC | 294 |
| `run_launch_workflow.py` LOC | 676 |
| bare `except Exception:` (run/runner/debug) | 15 |
| `# type: ignore` (run/runner/debug) | 7 |
| `window: Any` in run/debug shell seam | 0 in `run_launch_workflow.py` |

Re-run before each RUN-R PR:

```bash
git rev-parse HEAD
find app/run app/runner app/debug -name "*.py" -exec wc -l {} + | tail -1
wc -l app/runner/debug_runner.py app/run/run_service.py app/shell/run_launch_workflow.py
rg "^\s*except\s+Exception\s*:\s*$" app/run app/runner app/debug --type py | wc -l
python3 run_tests.py tests/unit/run/test_run_wave_grep_gates.py
```

---

## 7. CC-RUN grep gates (RUN-R-01)

Automated in `tests/unit/run/test_run_wave_grep_gates.py`:

| Gate | Assertion |
|------|-----------|
| CC-11 | No `app/run/pytest*.py` |
| CC-10 | `debug_runner.py` ≤30 LOC; `app/runner/debug/*` modules exist |
| CC-04 | `build_pytest_launch_plan` in discovery + runner |
| CC-02 partial | No `_is_debug_paused` in `run_service.py` |
| CC-03 partial | `_assert_idle()` before `plan_launch()` in `start_run` |
| CC-12 partial | No `HostProcessManager` under `app/run/` |
| CC-01/06 partial | Transport error forwards + closes server; runner pause loop bounded |
| CC-05 | Runner uses `-q` + `-rA`; workflow maps summary lines to explorer |
| CC-22 ceiling | bare `except Exception:` count ≤20 (tighten to ≤8 at RUN-R-22) |

Manual gates (extend as themes close):

```bash
rg "from app\.run\.pytest" app/ || true          # CC-11 → empty
rg "_is_debug_paused" app/run/ || true           # CC-02 → empty
rg "HostProcessManager" app/run/ || true           # CC-12 → empty
rg "window: Any" app/shell/run_launch_workflow.py app/shell/debug_control_workflow.py || true
find app -name "*.py" -exec wc -l {} + | awk '$1>=1000 {print}'
```

---

## 14. P2 disposition (CC-21 … CC-25)

| CC | Disposition |
|----|-------------|
| CC-21 | Close in RUN-R-21 or waive if legacy path unreachable |
| CC-22 | Close in RUN-R-22 — target ≤8 bare except |
| CC-23 | Partial closed @ HEAD; complete in RUN-R-23 |
| CC-24 | Partial — `TestOutcome` exists; complete typing in RUN-R-24 |
| CC-25 | Close in RUN-R-25 or document UX waiver |

---

## 16. Verification commands (every execute)

```bash
python3 testing/preflight_test_env.py
python3 run_tests.py tests/unit/run/test_run_wave_grep_gates.py
python3 run_tests.py tests/unit/run/ tests/unit/debug/ tests/unit/runner/
python3 testing/run_test_shard.py fast
npx pyright
find app -name "*.py" -exec wc -l {} + | awk '$1>=1000 {print "BLOCKER:", $2}'
rg "^    def " app/shell/main_window.py | wc -l   # expect ≤40
```

Integration (pre-PR for transport/debug PRs):

```bash
python3 testing/run_test_shard.py integration
```

---

## 17. Four-theme validation

Record in PR summary for any UI-touching RUN-R item (shell workflows, debug panel, test explorer):

- Light, Dark, HC Light, HC Dark
- Note gap if manual validation not run

---

## 18. Next session start

After RUN-R-01 (this session): execute **RUN-R-02** (CC-01 + CC-06 transport verification + integration test for mid-pause EOF).
