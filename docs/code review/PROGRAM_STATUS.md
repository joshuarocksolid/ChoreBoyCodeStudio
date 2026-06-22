```yaml
overall: IN_PROGRESS
current_phase: P1
current_item: P1-4
last_verified_commit: 57aac8d
last_session_ended: 2026-06-22T20:30:00Z
metrics:
  app_files_gte_1000: 0
  main_window_methods: 28
  shell_window_any_count: 66
  files_gte_700: 4
  run_runner_debug_loc: 4792
  debug_runner_loc: 8
  run_launch_workflow_loc: 676
  run_bare_except_exception: 15
  project_intelligence_imports: 0
  run_cc_closed_at_head: 9
  run_cc_partial_at_head: 4
phases:
  P0: done
  P1: in_progress
  P2: in_progress
  P3: pending
  P4: pending
blockers: []
next_actions:
  - "P1-4 RUN-R-08: CC-07 breakpoint wire SSOT — manifest codec round-trip tests; unify breakpoint serialization"
sessions_completed: 21
```

## Session 21 summary (2026-06-22)

### Commits landed (6 slices + RUN-R-04/06/07)

| Commit | Scope |
|--------|-------|
| `c34dc1e` | P2-6 support foundation seams (CC-CORE-02/03) |
| `2a1f611` | P2-6 shell support bundle wiring (CC-CORE-03/04/05) |
| `be4e8f8` | P2-6 HelpThemeTokens protocol (CC-CORE-08) |
| `ce5d221` | P2-7 pytest subprocess env SSOT + discovery hardening |
| `508d207` | P2-7 template default_entry manifest parity |
| `8272f48` | RUN-R-04 CC-03 + CC-08 atomic start_run tests |
| `57aac8d` | RUN-R-06 CC-05 -q -rA explorer outcome tests |

### Baseline @ HEAD (`57aac8d`)

| Gate | Result |
|------|--------|
| app files ≥1k | **0** |
| MainWindow methods | **28** |
| files ≥700 LOC | **4** (max 782 python_console_widget) |
| run CC closed | **9** (CC-01…06, CC-08, CC-10, CC-11) |
| run CC partial | **4** (CC-12, CC-19, CC-23, CC-24) |
| P0 milestone (CC-01…06) | **ALL CLOSED** |

### Run Wave 1 status

| Milestone | Status |
|-----------|--------|
| RUN-R-01…03 | ACCEPT |
| RUN-R-04 (CC-03, CC-08) | ACCEPT |
| RUN-R-06 (CC-05) | ACCEPT |
| RUN-R-07 P0 verification | **DONE** — grep gates + P0 test sweep green |
| RUN-R-08…25 | open |

### P2 progress (this session)

- Core-batch support/pytest/templates remediation landed (5 commits)
- Package reviews exist @ `c4aed0a`; closures pending for persistence/plugins/treesitter/packaging/python_tools

### Verification @ session end

| Gate | Result |
|------|--------|
| P0 milestone tests (47) | **PASS** |
| Targeted slice tests | **PASS** |
| fast shard | not re-run this session (prior flaky `test_main_window_background_teardown` noted) |

### Wave status

| Wave | Status |
|------|--------|
| editors-wave-1 | ACCEPT |
| shell-wave-2 | ACCEPT (P1 milestones) |
| intelligence-wave-1 | ACCEPT (P1 milestones) |
| project-ssot-wave-1 | ACCEPT |
| run-wave-1 | **open** — P0 done; Wave 2 CC themes remain |
