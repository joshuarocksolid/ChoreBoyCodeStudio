# Run Wave 1 — Remediation Closure Report

**Date:** 2026-06-22  
**Program:** Run Wave 1 remediation (RUN-R-01 … RUN-R-25)  
**Baseline review:** [run_wave_1_thermo_review_2026-05-25.md](run_wave_1_thermo_review_2026-05-25.md)  
**Verified commit:** `649e19f`  
**Verdict:** **ACCEPT (Run Wave 1 CC matrix complete)**

---

## 1. CC-RUN theme closure matrix

All 25 CC themes **closed** @ verified commit.

| CC | Priority | RUN-R | Status | Evidence |
|----|----------|-------|--------|----------|
| CC-01 | P0 | R-02 | **closed** | Transport EOF + shutdown-before-close; lifecycle tests |
| CC-02 | P0 | R-03 | **closed** | Pause authority via `DebugExecutionState` |
| CC-03 | P0 | R-04 | **closed** | `_assert_idle()` first; second start preserves transport |
| CC-04 | P0 | R-05 | **closed** | Shared `PytestLaunchPlan` grep gate |
| CC-05 | P0 | R-06 | **closed** | `-q -rA` → `parse_test_results` → explorer |
| CC-06 | P0 | R-02 | **closed** | Transport error closes server; stress tests |
| CC-07 | P1 | R-08 | **closed** | Breakpoint wire SSOT in `debug_breakpoints.py` |
| CC-08 | P1 | R-04 | **closed** | Manifest rollback on failed launch |
| CC-09 | P1 | R-09 | **closed** | `RunSessionStore` single shell mirror |
| CC-10 | P1 | R-10 | **closed** | `debug_runner.py` facade ≤30 LOC |
| CC-11 | P1 | R-11 | **closed** | No `app/run/pytest_*` |
| CC-12 | P1 | R-12 | **closed** | `start_run` ≤50 LOC; no `HostProcessManager` |
| CC-13 | P1 | R-13 | **closed** | Mode-aware manifest validation + tuple tests |
| CC-14 | P1 | R-14 | **closed** | REPL protocol typed builders + validation |
| CC-15 | P1 | R-15 | **closed** | `continued` clears inspector state |
| CC-16 | P1 | R-16 | **closed** | `run_launch_workflow.py` facade 121 LOC; split modules ≤215 |
| CC-17 | P1 | R-17 | **closed** | Exit-gated restart; `ALREADY_RUNNING` QMessageBox |
| CC-18 | P1 | R-18 | **closed** | `BreakpointStore` methods-only API + grep gates |
| CC-19 | P1 | R-19 | **closed** | REPL launch SSOT via `RunService.start_repl_sidecar` |
| CC-20 | P1 | R-20 | **closed** | `console_model` / `exit_status` in `app/shell/` |
| CC-21 | P2 | R-21 | **closed** | No legacy debug reducer paths |
| CC-22 | P2 | R-22 | **closed** | bare `except Exception:` count **4** (≤8) |
| CC-23 | P2 | R-23 | **closed** | 14 transport lifecycle tests |
| CC-24 | P2 | R-24 | **closed** | Typed `TestOutcome` end-to-end |
| CC-25 | P2 | R-25 | **closed** | Unified clear-console contract + policy tests |

---

## 2. Metric gates @ verified baseline

| Metric | Kickoff (2026-05-25) | Closure |
|--------|----------------------|---------|
| `app/` files ≥1000 LOC | 0 | **0** |
| `run_service.py` LOC | 330 | **372** |
| `run_launch_workflow.py` LOC | 676 | **121** (facade) |
| `debug_runner.py` LOC | 8 | **8** |
| bare `except Exception:` (run/runner/debug) | 15 | **4** |
| MainWindow methods | — | **28** (gate ≤40) |

---

## 3. Grep preservation gates

Automated in `tests/unit/run/test_run_wave_grep_gates.py` — **24 tests green** @ closure.

---

## 4. Verification results

| Gate | Result |
|------|--------|
| `test_run_wave_grep_gates.py` | **PASS** (24) |
| Run/debug/runner unit sweep | **PASS** (session 22) |
| pyright | **0 errors** |
| fast shard | **pending** @ closure write (session 22 rerun) |

---

## 5. Residual / out of scope

- Four-theme manual acceptance for run/debug UI — deferred to release QA (token-path only changes in CC-24/25).
- `docs/ARCHITECTURE.md` may still list relocated modules under `app/run/` — doc sync deferred to P4 INTEGR.

---

## 6. Verdict

**ACCEPT** — Run Wave 1 CC matrix complete; grep gates and targeted tests green @ `649e19f`.
