# Run Wave 1 — Remediation Plan (Phase 2)

Status: ready for implementation  
Implementation plan: [`run_wave_1_implementation_plan.md`](run_wave_1_implementation_plan.md)  
Baseline (re-verified): `4a5c2c7672305168bcad60f3f65dcdb506caf152`  
Source review: [`run_wave_1_thermo_review_2026-05-25.md`](run_wave_1_thermo_review_2026-05-25.md)  
Integration themes: [`_findings/TN-RUN-INTEG.md`](_findings/TN-RUN-INTEG.md)

Phase 1 (document-only review) is complete. **RUN-R-01** (re-baseline + grep gates + implementation plan) landed at `4a5c2c7`.

---

## Goals

1. Close all **P0** themes CC-01 … CC-06 before run/debug feature growth.
2. Close all **P1** themes CC-07 … CC-20 (mandatory for wave ACCEPT).
3. Close or disposition **P2** themes CC-21 … CC-25 per implementation plan §14.
4. Preserve extractions already landed since May 2025 review (`RunSessionController`, `RunOutputCoordinator`, `RunLaunchWorkflow`, `app/pytest/` package, `debug_runner` decomposition).
5. No `app/` file ≥1000 LOC; `debug_runner.py` remains a thin facade.

---

## Re-baseline delta vs 2026-05-25 kickoff

| Metric | Kickoff (`24a7cb3`) | @ HEAD (`4a5c2c7`) | Notes |
|--------|-------------------:|-------------------:|-------|
| run + runner + debug LOC | 4,624 | **4,792** | pytest moved out of `app/run/` (+168 net in boundary) |
| `debug_runner.py` LOC | 803 | **8** | Split → `app/runner/debug/*` (CC-10 **closed**) |
| `run_service.py` LOC | 329 | **372** | `plan_launch`, `_assert_idle`, transport error forward |
| `run_launch_workflow.py` LOC | 725 | **676** | Shell W2 partial |
| pytest services location | `app/run/pytest_*` | **`app/pytest/`** | CC-11 **closed** |
| `HostProcessManager` | present | **deleted** | CC-12 partial |
| `_is_debug_paused` on `RunService` | present | **removed** | CC-02 partial |
| `PytestLaunchPlan` | absent | **`app/pytest/launch_plan.py`** | CC-04 **closed** |
| pytest runner `-rA` with `-q` | absent | **present** | CC-05 partial |
| `test_debug_transport_lifecycle.py` | absent | **present** | CC-23 partial |
| bare `except Exception:` (run/runner/debug) | 11 | **15** | CC-22 **open** (regressed count — audit paths) |

Several P0/P1 themes have **partial or full fixes** since the review; RUN-R-02 … RUN-R-25 must verify @ HEAD before marking closed (grep gates + targeted tests).

---

## Non-negotiable rules (every PR)

- Hard cutover importers; no long-lived compatibility wrapper for old transport/pytest/debug paths.
- Python 3.9 syntax; no dot-prefixed runtime paths.
- Do not grow `debug_runner.py` past ~30 LOC — add modules under `app/runner/debug/`.
- Shell seam workflows use typed host bundles (`RunLaunchWorkflowHost`, `DebugShellHost`) — no new `window: Any` in run/debug workflows.
- Four-theme validation for UI-touching shell PRs (Light, Dark, HC Light, HC Dark).
- Tests only when risk-first gate applies: transport lifecycle, pause authority, re-entrant start, pytest launch parity, subprocess blast radius.

---

## Wave 0 — Baseline + grep gates (RUN-R-01)

**Blocks:** CC-23 (partial), all later RUN-R items

**Goal:** Re-baseline metrics @ HEAD; lock structural wins; scaffold executable plan.

### Step 0.1 — Re-baseline manifest

Update [`00-manifest.md`](00-manifest.md) metric sweep @ `4a5c2c7`.

### Step 0.2 — Grep gate tests

Add `tests/unit/run/test_run_wave_grep_gates.py` — guards:

- No `app/run/pytest_*` modules
- `debug_runner.py` ≤30 LOC (facade)
- No `RunService._is_debug_paused`
- `app/pytest/launch_plan.py` imported by discovery + runner
- No `HostProcessManager` under `app/run/`
- `app/run/run_service.py` calls `_assert_idle()` before launch side effects

**Gate:** `python3 run_tests.py tests/unit/run/test_run_wave_grep_gates.py` green.

---

## Wave 1 — P0 blockers (transport + pause + atomic start)

**Blocks:** CC-01, CC-02, CC-03, CC-04, CC-05, CC-06

### Step 1.1 — Transport failure semantics (CC-01, CC-06)

Verify EOF/write failure → `_on_error` → runner `_transport_failed` → editor `_close_debug_transport_server`. Add integration: fake transport EOF mid-pause → runner exits cooperatively.

### Step 1.2 — Pause authority SSOT (CC-02)

Confirm toolbar/panel/breakpoint sync derive from `DebugSession` after queue drain only. Add integration characterization if toolbar/panel disagree.

### Step 1.3 — Atomic start_run (CC-03, CC-08 partial)

`_assert_idle()` is first — verify transport opens only after supervisor accepts; rollback manifest on failed launch. Integration: second `start_run` without stop raises `RunLifecycleError`.

### Step 1.4 — Pytest launch parity (CC-04, CC-05)

`PytestLaunchPlan` shared — add parity test discovery vs runner argv when `run_tests.py` present/absent. Verify `-rA` summary populates explorer on Run All.

---

## Wave 2 — Contract + lifecycle structural

**Blocks:** CC-07, CC-08, CC-09, CC-10 (done), CC-11 (done), CC-12, CC-13, CC-14, CC-15, CC-19

Breakpoint wire SSOT, manifest codec, session store, REPL protocol typing, `LaunchContext` coordinator slimming.

---

## Wave 3 — Shell seam

**Blocks:** CC-16, CC-17, CC-18, CC-20, CC-25

Split `run_launch_workflow.py`; exit-gated restart; `BreakpointStore` encapsulation; relocate `ConsoleModel`/`exit_status`; unify clear-console policy.

---

## Wave 4 — Pytest typing + test audit

**Blocks:** CC-23 (remainder), CC-24

Typed `TestOutcome`; consolidate problem parser; transport lifecycle suite completeness.

---

## Wave 5 — R1 hygiene

**Blocks:** CC-21, CC-22

Legacy reducer cleanup; narrow bare `except Exception:` on hot paths (target ≤8 in run/runner/debug).

---

## Program complete when

See [`run_wave_1_implementation_plan.md`](run_wave_1_implementation_plan.md) §1 — all CC-01 … CC-25 dispositioned; fast shard + pyright clean; four-theme gaps documented for UI PRs.
