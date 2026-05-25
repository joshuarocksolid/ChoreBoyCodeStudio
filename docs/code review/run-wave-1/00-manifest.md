# Scope manifest: run-wave-1 thermo-nuclear review

Status: Wave 1 kickoff  
Baseline commit: `24a7cb37fc9c4d2890ab0c0d701d7e61098c13c2`  
Date: 2026-05-25  
Intent: **Document only** — no remediation commits in this round.

---

## Purpose

Strict thermo-nuclear maintainability pass over the run/debug process boundary:

- [`app/run/`](../../app/run/) — editor-side orchestration, subprocess supervisor, pytest services
- [`app/runner/`](../../app/runner/) — child-process entrypoint, REPL sidecar, debug engine
- [`app/debug/`](../../app/debug/) — shared debug contract, transport, session state
- Shell seam — orchestration modules that call the above

Sequenced as **Shell Wave 4** in [`shell_wave_1_thermo_review_2026-05-25.md`](../shell-wave-1/shell_wave_1_thermo_review_2026-05-25.md) §7.

---

## Metric sweep (at kickoff)

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

## High-risk hotspots

- `app/runner/debug_runner.py` — 803 LOC god module
- `app/run/process_supervisor.py` + `run_service.py` — subprocess blast radius
- `app/debug/debug_transport.py` + `debug_session.py` — editor/runner desync risk
- `app/shell/run_launch_workflow.py` — 725 LOC shell orchestration into run layer
- pytest services mixed into `app/run/` lifecycle package

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
└── run_wave_1_thermo_review_2026-05-25.md
```

---

## Validation commands (for fix agent, not this review round)

```bash
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py runtime_parity
npx pyright
```
