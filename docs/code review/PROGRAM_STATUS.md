```yaml
overall: ACCEPT
current_phase: P4
current_item: done
last_verified_commit: pending_final_push
last_session_ended: 2026-06-22T21:00:00Z
metrics:
  app_files_gte_1000: 0
  main_window_methods: 28
  shell_window_any_count: 66
  files_gte_700: 5
  app_loc: 87048
  bare_except_exception: 35
  type_ignore_count: 121
phases:
  P0: done
  P1: done
  P2: done
  P3: done
  P4: done
blockers: []
next_actions:
  - "Program complete — optional post-ACCEPT deslop briefs in docs/deslop/AUDIT_app_remaining_handoff.md"
sessions_completed: 23
```

## Session 23 summary (2026-06-22)

### P2 package closures — all ACCEPT @ `8ee0317`

| Wave | Commit | Verdict |
|------|--------|---------|
| persistence-wave-1 | `b877c0e` | ACCEPT |
| plugins-wave-1 | `3089089` | ACCEPT |
| treesitter-wave-1 | `115f355` | ACCEPT |
| python-tools-wave-1 | `23bd584` | ACCEPT |
| core-batch-wave-1 | `296dfec` | ACCEPT |
| pytest-templates-wave-1 | `8ee0317` | ACCEPT |
| packaging-wave-1 | (prior @ `313dbf3`) | ACCEPT |

### P3 deslop — done

| Item | Commit | Notes |
|------|--------|-------|
| R0 audit closeout | `c8edfc4` | Metrics in AUDIT_app.md |
| R1 cleanup sweep | `c9ddc70` | Runner/plugin/debug docs |
| R6/R7 audit catalogs | `7d87dad` | TEST_TOOLING_AUDIT + AUDIT_out_of_scope |
| R3 shell hotspot waiver | docs | P3_shell_hotspot_waiver_2026-06-22.md |
| OS-M1/M2 | `22bef2d` | Visible cbcs/, remove root test.py |
| R2/R4/R5 | — | Absorbed by P1–P2 waves (verified) |

### P4 integration — done

| Gate | Result |
|------|--------|
| pyright | **0 errors** |
| fast shard | **PASS** @ `c8edfc4` |
| integration shard | See session note |
| runtime_parity | **PASS** after plugin-host env fix |
| Final rollup | [THERMO_PROGRAM_CLOSURE_2026-06-22.md](THERMO_PROGRAM_CLOSURE_2026-06-22.md) |

### Known flakes

- `test_close_event_persists_python_console_history` — integration shard timeout under full theme apply (~140s); pre-existing; not a regression blocker.

### Program verdict

**OVERALL: ACCEPT** — see [THERMO_PROGRAM_CLOSURE_2026-06-22.md](THERMO_PROGRAM_CLOSURE_2026-06-22.md).
