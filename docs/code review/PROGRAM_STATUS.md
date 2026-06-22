```yaml
overall: IN_PROGRESS
current_phase: P1
current_item: P1-1
last_verified_commit: 6317aad
last_session_ended: 2026-06-22T22:30:00Z
metrics:
  app_files_gte_1000: 0
  main_window_methods: 28
  shell_window_any_count: 66
  files_gte_700: 5
  shell_composition_loc: 404
phases:
  P0: done
  P1: in_progress
  P2: pending
  P3: pending
  P4: pending
blockers: []
next_actions:
  - "SHELL-R-17 CC-SHELL2-20: expand PythonConsoleWorkflow session lifecycle (submit/interrupt/restart); ensure no console handlers remain on MainWindow; verify test_python_console_workflow + test_python_console_widget; preserve window:Any ≤79"
sessions_completed: 7
```

## Session 7 summary (2026-06-22) — SHELL-R-14

### Landed

**SHELL-R-14 (CC-SHELL2-17 ACCEPT):** Verified stop/restart/clear-console lifecycle already off MainWindow @ HEAD (landed in prior Shell Wave 2 remediation `3551015`):
- `menu_wiring.py`: `on_stop` → `RunDebugPresenter.stop_session`, `on_restart` → `restart_session`, `on_clear_console` → `PythonConsoleWorkflow.handle_clear_console_action`
- `RunDebugPresenter.restart_session()` defers relaunch via `_pending_restart`; `run_event_workflow.apply_run_event(exit)` calls `execute_pending_restart_if_any()` (exit-gated, no stop-then-immediate race)
- MainWindow has no `_handle_stop_action` / `_handle_restart_action`

**Session additions:** Strengthening tests only:
- `test_apply_run_event_exit_executes_pending_restart` (unit)
- `test_stop_action_routes_through_presenter` (integration)

### Verification @ HEAD (6317aad + uncommitted session 7)

| Gate | Result |
|------|--------|
| fast shard | **PASS** (exit 0, ~125s) |
| pyright | **0 errors** |
| app files ≥1k | **0** |
| main_window methods | **28** |
| `window: Any` shell-wide | **66** (gate ≤79 **PASS**) |
| Run lifecycle tests (17) | **PASS** |
| Editors grep gates | clean |

### CC theme status (Shell Wave 2)

| CC | PR | Status |
|----|-----|--------|
| CC-SHELL2-05 | R-04b/c | **ACCEPT** |
| CC-SHELL2-17 | R-14 | **ACCEPT** |
| CC-SHELL2-18 | R-15 | **ACCEPT** |
| CC-SHELL2-19 | R-16 | **ACCEPT** |
| CC-SHELL2-20 | R-17 | **OPEN** |

### Wave status

| Wave | Status |
|------|--------|
| editors-wave-1 | ACCEPT |
| shell-wave-2 | in_progress — Wave 4 complete; Wave 5 R-17 next; R-18–R-20 pending |
| intelligence-wave-1 | open (P1-2) |
| project-ssot-wave-1 | open (P1-3) |
| run-wave-1 | open (P1-4) |

Shell Wave 2 closure doc deferred until Wave 5–6 CC themes closed.

### Uncommitted working tree (ready for parent commit)

```
 M tests/integration/shell/test_run_debug_toolbar_integration.py
 M tests/unit/shell/test_run_event_workflow.py
```

### Verification commands (re-run before next execute)

```bash
python3 run_tests.py tests/unit/shell/test_run_event_workflow.py tests/integration/shell/test_run_debug_toolbar_integration.py
python3 testing/preflight_test_env.py
python3 testing/run_test_shard.py fast
npx pyright
```
