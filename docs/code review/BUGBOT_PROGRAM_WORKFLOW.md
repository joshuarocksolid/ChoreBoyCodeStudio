# Bugbot Program — Your Workflow (Human Guide)

What **you** do vs what the **orchestrator agent** automates.

**Orchestrator agent:** `.cursor/agents/bugbot-program-orchestrator.md`  
**Invoke:** `/bugbot-program-orchestrator` in Agent chat.

---

## When to use this vs other tools

| Tool | Use when |
|------|----------|
| `/review-bugbot` | One-shot review of current diff; **no fixes** |
| `/bugbot-program-orchestrator` | Loop: slice → review → fix → re-review until clean |
| `/thermo-program-orchestrator` | Structural/maintainability program (already ACCEPT @ 2026-06-22) |

---

## One-time setup (~5 minutes)

```bash
python3 testing/preflight_test_env.py
```

Optional smoke: `python3 testing/run_test_shard.py fast`

Commit when ready:

- `.cursor/agents/bugbot-program-orchestrator.md`
- `docs/code review/BUGBOT_PROGRAM_ORCHESTRATOR.md`
- `docs/code review/BUGBOT_PROGRAM_WORKFLOW.md` (this file)

---

## Every session — what you do

### Kickoff

1. Agent chat → **Composer 2.5 Fast**
2. Type:

```text
/bugbot-program-orchestrator
```

Or with scope:

```text
/bugbot-program-orchestrator PR mode on this branch
/bugbot-program-orchestrator SWEEP app/shell/ app/run/
/bugbot-program-orchestrator HOTSPOT app/persistence/local_history_repository.py
```

### While it runs

**You do nothing** unless:

| Signal | Your action |
|--------|-------------|
| Product behavior question (fix vs intended) | One-sentence answer |
| `blockers` with `needs_user: true` | Read and unblock |
| Checkpoint commit wanted | “commit bugbot program progress” |
| Agent stuck / context heavy | New chat: `/bugbot-program-orchestrator continue` + `@BUGBOT_PROGRAM_STATUS.md` |

### End of session

Glance at `docs/code review/BUGBOT_PROGRAM_STATUS.md`:

```yaml
overall: IN_PROGRESS   # or CLEAN | BLOCKED
next_actions:
  - "..."
exit_gate:
  consecutive_clean_passes: 0
```

---

## Resume

```text
/bugbot-program-orchestrator continue
```

Or:

```text
Continue bugbot program from @docs/code review/BUGBOT_PROGRAM_STATUS.md
```

Optional loop:

```text
/loop 30m Continue bugbot program. Read BUGBOT_PROGRAM_STATUS.md and execute next_actions[0].
```

---

## Done when

1. `BUGBOT_PROGRAM_STATUS.md` → `overall: CLEAN`
2. `exit_gate.consecutive_clean_passes: 2`
3. Fast shard + pyright clean if code changed

---

## Quick reference

```text
START:     /bugbot-program-orchestrator [PR|SWEEP|HOTSPOT scope]
RESUME:    /bugbot-program-orchestrator continue
STATUS:    docs/code review/BUGBOT_PROGRAM_STATUS.md
ONE-SHOT:  /review-bugbot  (review only, no fix loop)
DONE WHEN: overall: CLEAN + 2× exit gate
```
