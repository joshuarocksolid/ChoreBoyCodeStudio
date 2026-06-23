```yaml
overall: CLEAN
mode: SWEEP
scope: app/ (exit gate — uncommitted remediation diff)
base_branch: main
last_verified_commit: 535a37bd80e0d881a315a84585a387566cb057b7
last_session_ended: 2026-06-23T01:05:00Z
exit_gate:
  consecutive_clean_passes: 2
  required: 2
  bugbot_passes_completed: 2
  clean_sweep_agents:
    - 253c7c26-aab6-4de9-aa49-15d18669c849
    - 40309082-8980-40fe-8f1c-76fc00ddbd5f
slices:
  - id: core-batch
    status: clean
    findings_open: 0
  - id: shell-mainwindow
    status: clean
    findings_open: 0
  - id: shell-run-repl
    status: clean
    findings_open: 0
  - id: shell-editor
    status: clean
    findings_open: 0
  - id: shell-ui-theme
    status: clean
    findings_open: 0
  - id: shell-workflows
    status: clean
    findings_open: 0
  - id: editors-syntax
    status: clean
    findings_open: 0
  - id: intelligence
    status: clean
    findings_open: 0
  - id: project
    status: clean
    findings_open: 0
  - id: run-runner-debug
    status: clean
    findings_open: 0
  - id: persistence-plugins
    status: clean
    findings_open: 0
  - id: treesitter-packaging
    status: clean
    findings_open: 0
  - id: misc-tools
    status: clean
    findings_open: 0
exit_gate_findings_resolved:
  - id: EXIT-HIGH-01
    severity: High
    location: app/shell/run_event_workflow.py
    title: Stale exit still runs exit hooks
    resolution: run_id guard in apply_run_event exit branch
  - id: EXIT-MED-01
    severity: Medium
    location: app/shell/lint_workflow.py
    title: Per-file lint ignores lazy manifest
    resolution: manifest_materialized threaded through per-file lint path
  - id: EXIT-MED-02
    severity: Medium
    location: app/project/recent_projects.py
    title: max_entries truncates recents on remember
    resolution: remember_recent_project persists full list; max_entries slices return only
  - id: EXIT-HIGH-02
    severity: High
    location: app/shell/run_output_coordinator.py:83-90
    title: Stale exit guard skips cleared session
    resolution: |
      Exit processed only when active_run_id is non-null and event.run_id matches
      (or event.run_id is unset). Delayed exits after session cleared are ignored.
    test: tests/unit/shell/test_run_output_coordinator.py (stale/matching exit tests)
  - id: EXIT-MED-03
    severity: Medium
    location: app/shell/run_event_workflow.py:256-267
    title: Shutdown drain ignores run_id on exit
    resolution: |
      _drain_exit_cleanup_events uses shared _is_matching_exit_event guard;
      apply_run_event exit branch aligned to same helper.
    test: tests/unit/shell/test_run_event_workflow.py (drain stale/matching tests)
  - id: EXIT-MED-04
    severity: Medium
    location: app/editors/completion_popup/completion_controller.py:217-225
    title: Enter on header traps popup
    resolution: |
      accept_current hides popup when move_to_next_selectable leaves selection on
      a tier header or no row (no selectable below).
    test: test_accept_current_on_trailing_header_hides_popup_when_no_selectable_below
  - id: EXIT-MED-05
    severity: Medium
    location: app/pytest/runner_service.py:96-105
    title: Nested class cursor test wrong id
    resolution: Full class stack joined with :: for nested pytest node ids
    test: test_identify_test_at_cursor_returns_full_nested_class_chain
metrics:
  total_findings_fixed: 36
  total_findings_waived: 2
  total_findings_open: 0
  additional_findings_fixed_this_phase: 4
verification:
  targeted_tests: green (15 selected regression tests)
  fast_shard: green @ 2026-06-22
  pyright: 0 errors @ 2026-06-22
blockers: []
next_actions:
  - "Program CLEAN — optional: commit the working-tree remediation diff when ready"
sessions_completed: 8
```

CLEAN: 36 findings fixed, 2 waived, 0 open. Two consecutive parent-dispatched confirming Bugbot sweeps over the uncommitted `app/` diff found no bugs (2/2 exit gate). Fast shard + pyright green. Changes remain uncommitted in the working tree.
