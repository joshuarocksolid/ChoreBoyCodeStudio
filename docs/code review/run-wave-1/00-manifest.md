# Scope manifest: run-wave-1 thermo-nuclear review

Status: Phase 2 remediation in progress (RUN-R-01 @ HEAD)  
Kickoff baseline: `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2` (2026-05-25)  
Re-baseline commit: `4a5c2c7672305168bcad60f3f65dcdb506caf152` (2026-06-22)  
Intent: Review complete; remediation tracked in [`run_wave_1_implementation_plan.md`](run_wave_1_implementation_plan.md).

---

## Purpose

Strict thermo-nuclear maintainability pass over the run/debug process boundary:

- [`app/run/`](../../app/run/) — editor-side orchestration, subprocess supervisor, pytest services
- [`app/runner/`](../../app/runner/) — child-process entrypoint, REPL sidecar, debug engine
- [`app/debug/`](../../app/debug/) — shared debug contract, transport, session state
- Shell seam — orchestration modules that call the above

Sequenced as **Shell Wave 4** in [`shell_wave_1_thermo_review_2026-05-25.md`](../shell-wave-1/shell_wave_1_thermo_review_2026-05-25.md) §7.

---

## Metric sweep (at kickoff — 2026-05-25)

| Metric | Value |
|--------|------:|
| Baseline commit | `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2` |
| `app/run/` + `app/runner/` + `app/debug/` Python LOC | 4,624 |
| `debug_runner.py` LOC | 803 |
| `run_service.py` LOC | 329 |
| `process_supervisor.py` LOC | 316 |
| `run_manifest.py` LOC | 395 |
| `debug_session.py` LOC | 315 |
| `run_launch_workflow.py` LOC | 725 |
| Bare `except Exception:` in run/runner/debug | 11 |
| `# type: ignore` in run/runner/debug | 7 |
| `window: Any` in shell seam modules (sample) | 1 |

## Metric sweep (re-baseline @ `4a5c2c7` — 2026-06-22)

| Metric | Value | Δ vs kickoff |
|--------|------:|--------------|
| Re-baseline commit | `4a5c2c7672305168bcad60f3f65dcdb506caf152` | — |
| `app/run/` + `app/runner/` + `app/debug/` Python LOC | **4,792** | +168 (pytest relocated to `app/pytest/`) |
| `debug_runner.py` LOC | **8** (facade) | −795 (**CC-10 closed**) |
| `app/runner/debug/` package LOC | ~1,050 (split modules) | new |
| `run_service.py` LOC | **372** | +43 (`plan_launch`, transport error path) |
| `process_supervisor.py` LOC | **326** | +10 |
| `run_manifest.py` LOC | **480** | +85 |
| `debug_session.py` LOC | **294** | −21 |
| `run_launch_workflow.py` LOC | **676** | −49 (shell W2) |
| pytest services | **`app/pytest/`** (5 modules) | moved from `app/run/` (**CC-11 closed**) |
| `HostProcessManager` | **absent** | deleted (**CC-12 partial**) |
| Bare `except Exception:` in run/runner/debug | **15** | +4 (**CC-22 open**) |
| `# type: ignore` in run/runner/debug | **7** | unchanged |
| CC themes closed @ HEAD | **3** (CC-04, CC-10, CC-11) | partial on 9 P0/P1 |

Re-run before fix-agent work:

```bash
git rev-parse HEAD
find app/run app/runner app/debug -name "*.py" -not -path "*__pycache__*" -exec wc -l {} + | tail -1
wc -l app/runner/debug_runner.py app/run/run_service.py app/run/process_supervisor.py
rg "^\s*except\s+Exception\s*:\s*$" app/run app/runner app/debug --type py | wc -l
```

---

## In scope — slice critics (9)

| ID | Primary files | ~LOC | Cluster |
|----|---------------|-----:|---------|
| TN-RUN-01 | `run_manifest.py`, `runtime_launch.py`, `runner_command_builder.py`, `exit_status.py` | 472 | Editor↔runner contract |
| TN-RUN-02 | `process_supervisor.py`, `host_process_manager.py`, `run_service.py`, `console_model.py`, `output_tail_buffer.py` | 792 | Subprocess lifecycle |
| TN-RUN-03 | `pytest_discovery_service.py`, `pytest_runner_service.py`, `problem_parser.py` | 607 | Test Explorer backend |
| TN-RUNNER-01 | `runner_main.py`, `execution_context.py`, `output_bridge.py`, `traceback_formatter.py` | 323 | Normal bootstrap path |
| TN-RUNNER-02 | `repl_control.py`, `repl_protocol.py`, `repl_completion.py` | 474 | REPL sidecar + completion |
| TN-RUNNER-03 | `debug_runner.py` | 803 | Runner-side debug engine |
| TN-DEBUG-01 | `debug_models.py`, `debug_breakpoints.py`, `debug_protocol.py`, `debug_command_service.py`, `safe_eval.py`, `debug_runtime_probe.py` | 577 | Shared protocol/models |
| TN-DEBUG-02 | `debug_session.py`, `debug_transport.py` | 556 | Editor session + socket I/O |
| TN-RUN-SHELL | `run_launch_workflow.py`, `run_session_controller.py`, `run_output_coordinator.py`, `repl_session_manager.py`, `debug_control_workflow.py` (+ presenter/store cross-read) | 1,877 | Shell orchestration seam |

### Integration (1 meta critic, runs last)

| ID | Role |
|----|------|
| TN-RUN-INTEG | Dedupe cross-cutting themes → CC-01… IDs; map to R1 / R-run fix waves |

---

## Out of scope

- Unrelated `app/shell/` (covered in shell wave 1 except seam modules above)
- `app/intelligence/` (wave 5 backlog)
- R4 project file inventory SSOT, R5 dependency classifier SSOT (except duplicated traversal noted in findings)
- Fix commits, test changes, pyright fixes in this round

---

## Canonical read order for critics

1. [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md) — §4.1 process boundary, §6 process model, §8 runtime modes, §13 runner contract
2. [`docs/deslop/AUDIT_app_remaining_handoff.md`](../../deslop/AUDIT_app_remaining_handoff.md) — R1 cleanup scope
3. Assigned slice or module
4. Listed cross-reads and characterization tests

---

## High-risk hotspots (@ re-baseline)

- `app/run/process_supervisor.py` + `run_service.py` — subprocess blast radius (CC-03, CC-08)
- `app/debug/debug_transport.py` + `debug_session.py` — editor/runner desync risk (CC-01, CC-06)
- `app/shell/run_launch_workflow.py` — 676 LOC shell orchestration (CC-16)
- `app/run/run_manifest.py` — 480 LOC contract surface (CC-07, CC-13)
- P0 transport/pause themes — verify @ HEAD before feature growth (see implementation plan §3)

**Resolved since kickoff:** `debug_runner.py` god module (split to `app/runner/debug/`); pytest package extraction.

---

## Output artifacts

```
docs/code review/run-wave-1/
├── 00-manifest.md                    (this file)
├── _findings/
│   ├── _README.md
│   ├── TN-RUN-01.md … TN-RUN-03.md
│   ├── TN-RUNNER-01.md … TN-RUNNER-03.md
│   ├── TN-DEBUG-01.md, TN-DEBUG-02.md
│   ├── TN-RUN-SHELL.md
│   └── TN-RUN-INTEG.md
├── run_wave_1_thermo_review_2026-05-25.md
├── run_wave_1_remediation_plan.md
└── run_wave_1_implementation_plan.md
```

---

## Validation commands (for fix agent, not this review round)

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py runtime_parity
npx pyright
```
