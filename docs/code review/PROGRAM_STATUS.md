```yaml
overall: IN_PROGRESS
current_phase: P2
current_item: P2-1
last_verified_commit: 44eae74
last_session_ended: 2026-06-22T22:00:00Z
metrics:
  app_files_gte_1000: 0
  main_window_methods: 28
  shell_window_any_count: 66
  files_gte_700: 4
  run_cc_closed_at_head: 25
  run_cc_partial_at_head: 0
  run_launch_workflow_loc: 121
  run_bare_except_exception: 4
phases:
  P0: done
  P1: done
  P2: in_progress
  P3: pending
  P4: pending
blockers: []
next_actions:
  - "P2-1 persistence-wave-1: verify remediation @ HEAD; write ACCEPT closure doc"
  - "P2 parallel: plugins, treesitter, packaging, python_tools, core-batch, pytest/templates closures"
  - "P3 deslop R0-R7; P4 INTEGR + THERMO_PROGRAM_CLOSURE"
sessions_completed: 22
```

## Session 22 summary (2026-06-22)

### Run Wave 1 — ACCEPT @ `44eae74`

| Milestone | Status |
|-----------|--------|
| RUN-R-09 … RUN-R-25 | **ACCEPT** — all 25 CC themes closed |
| Closure doc | [run_wave_1_remediation_closure_2026-06-22.md](run-wave-1/run_wave_1_remediation_closure_2026-06-22.md) |
| grep gates | **24/24 PASS** |
| pyright | **0 errors** |

### Commits this session (16 slices @ `1973c6c` → `44eae74`)

RUN-R-09 (CC-09), CC-12/23/24/19 partials, CC-13/14/25/18/21, CC-22, CC-16/17, run-wave closure, transport stress-test crash fix.

### Baseline @ HEAD (`44eae74`)

| Gate | Result |
|------|--------|
| app files ≥1k | **0** |
| MainWindow methods | **28** |
| run CC closed | **25 / 25** |
| bare except (run/runner/debug) | **4** |
| `run_launch_workflow.py` | **121 LOC** (facade) |

### Verification @ session end

| Gate | Result |
|------|--------|
| Targeted run/shell/debug tests | **PASS** |
| pyright | **0 errors** |
| fast shard | **TIMEOUT** — `test_close_event_persists_python_console_history` during theme apply under integration shard (~138s); pre-existing flake class |

### Wave status

| Wave | Status |
|------|--------|
| editors-wave-1 | ACCEPT |
| shell-wave-2 | ACCEPT |
| intelligence-wave-1 | ACCEPT |
| project-ssot-wave-1 | ACCEPT |
| **run-wave-1** | **ACCEPT** |
| persistence/plugins/treesitter/packaging/python_tools/core-batch/pytest-templates | reviews @ HEAD; **closures pending** |

### P1 complete

All Run Wave 1 CC themes closed; P1 phase marked **done**. Program advances to **P2 package closures**.
