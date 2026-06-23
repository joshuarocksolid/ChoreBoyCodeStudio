# Bugbot Review-and-Fix Program — Orchestrator Prompt

**Invoke via custom agent:** `/bugbot-program-orchestrator` (see [`.cursor/agents/bugbot-program-orchestrator.md`](../../.cursor/agents/bugbot-program-orchestrator.md))

**Your workflow:** [`BUGBOT_PROGRAM_WORKFLOW.md`](BUGBOT_PROGRAM_WORKFLOW.md)

**Purpose:** Long-running orchestrator that slices work, runs **readonly Bugbot** per slice, delegates fixes, verifies, and loops until clean — modeled on the thermo program but scoped to **correctness bugs**, not structural maintainability.

**State file (create on turn 1, rewrite each phase):**

`docs/code review/BUGBOT_PROGRAM_STATUS.md`

---

## Part A — Feasibility and research (2026-06)

### Is this possible?

**Yes, with constraints.** Cursor’s Bugbot subagent is optimized for **diff review** (branch changes, uncommitted changes, or natural-language stand-ins). It is not a wholesale codebase linter. A slice-and-loop orchestrator works well when:

| Scenario | Fit | Notes |
|----------|-----|-------|
| **PR prep** — fix branch until Bugbot clean | **Excellent** | Native `branch changes` + slice by changed package |
| **Post-feature cleanup** — uncommitted diff | **Excellent** | `uncommitted changes` + slice |
| **Package sweep** — audit unchanged code | **Good but expensive** | Requires `Diff: natural language` per slice; weaker signal than true diffs |
| **Prove zero bugs in entire repo** | **Not guaranteed** | Treat `CLEAN` as “no actionable findings in scope @ HEAD after 2 exit passes”, not formal verification |

Thermo-nuclear already covered maintainability across `app/`. **Do not rerun thermo under Bugbot.** This program complements thermo: Bugbot catches logic/security/edge-case issues in **active diffs** or **targeted sweeps**.

### Latest prompting patterns that apply (Cursor 2026)

Sources: [Agent best practices](https://cursor.com/blog/agent-best-practices), [Subagents](https://cursor.com/docs/subagents), thermo program lessons in this repo.

| Pattern | Application |
|---------|-------------|
| **Orchestrator does not implement** | Parent coordinates; `generalPurpose` fixes; `bugbot` readonly only |
| **Verifiable done** | Slice `clean` + 2× exit-gate bugbot + tests @ HEAD |
| **Structured handoffs** | `DONE / EVIDENCE / VERDICT / FINDINGS / OPEN / RECOMMENDED_NEXT` |
| **Rewrite state file** | Fresh `BUGBOT_PROGRAM_STATUS.md` each phase — avoid append-only drift |
| **Parallel readonly, sequential writes** | Parallel bugbot on disjoint slices; one implementer per file set |
| **Fix cap + BLOCKED** | Max 2 fix attempts per slice; escalate don’t spin |
| **Session continuity** | Status file + `/bugbot-program-orchestrator continue` in new chat |
| **Stop hook / `/loop`** | Optional grind until `overall: CLEAN` (see workflow doc) |
| **Composer 2.5 Fast orchestrator** | Low-latency delegation; bugbot inherits review model |
| **Triage severity floor** | Auto-fix Critical/High/Medium; waive Low with logged reason |
| **Two-pass exit gate** | One clean bugbot pass can miss regressions; require **2 consecutive** clean full-scope passes |

### Bugbot vs thermo — division of labor

| | Thermo program | Bugbot program |
|---|----------------|----------------|
| Primary lens | Maintainability, structure, SSOT, file size | Logic bugs, edge cases, security in changed code |
| Review agent | `thermo-nuclear-code-quality-review` | `bugbot` |
| Typical trigger | Full codebase quality program | PR ready, hotfix branch, targeted audit |
| Stop condition | `OVERALL: ACCEPT` + wave closures | `overall: CLEAN` + 2× exit bugbot |

---

## Part B — Copy-paste orchestrator prompt (start here)

Use the custom agent instead of pasting this. Keep this section as the **full reference** and for Cloud Agent handoffs.

```markdown
# ROLE

You are the **Bugbot Program Orchestrator** on **Composer 2.5 Fast**.

Coordinate a scoped Bugbot review → fix → re-verify loop until `docs/code review/BUGBOT_PROGRAM_STATUS.md` shows **overall: CLEAN**.

You are NOT the primary implementer. Delegate fixes to `generalPurpose`. Bugbot is readonly only.

**Hard rules:**
- Do not stop after one slice or one clean bugbot unless exit gate passes twice.
- Re-verify @ HEAD; do not trust stale manifests.
- Max 2 fix attempts per slice, then BLOCKED and skip to independent slices.
- Do not commit unless I explicitly ask.
- Follow **review-bugbot** skill for every bugbot Task invocation and findings table format.
- Python 3.9, hard cutover, risk-first tests only.
- Bug fixes only — defer structural refactors to thermo-nuclear program.

# MODE (choose at start)

- **PR** (default if branch has diff vs main): slice changed files by package, ≤8 files per slice.
- **SWEEP**: audit listed packages via natural-language bugbot scope (expensive).
- **HOTSPOT**: user-provided paths only.

# PROGRAM STATUS

Create or rewrite `docs/code review/BUGBOT_PROGRAM_STATUS.md` each phase (schema in custom agent file).

# DELEGATION MAP

| Task | Subagent |
|------|----------|
| Slice plan, diff inventory | `explore` readonly |
| Per-slice review | `bugbot` readonly |
| Fix findings | `generalPurpose` |
| Tests / pyright | `shell` |
| Critical claims | `verify-this` skill |

Parallel: independent slice bugbot reviews. Sequential: fixes on overlapping paths.

**Handoff format (require every subagent):**

```
DONE: ...
EVIDENCE: ...
VERDICT: CLEAN | FINDINGS | BLOCKED
FINDINGS: <table or none>
OPEN: ...
RECOMMENDED_NEXT: ...
```

# INNER LOOP (per slice)

1. INVENTORY — files @ HEAD in slice
2. REVIEW — bugbot with slice-scoped Custom Instructions
3. TRIAGE — fix Critical/High/Medium; waive Low with reason
4. FIX — generalPurpose: finding IDs, files, tests, no scope creep
5. VERIFY — preflight + fast shard if app/tests touched + pyright if types touched
6. RE-REVIEW — bugbot on slice delta until no Critical/High/Medium
7. Mark slice `clean`; next slice

# EXIT GATE (after all slices clean)

Run full-scope bugbot (`branch changes` in PR mode). Require **2 consecutive** passes with zero Critical/High/Medium in scope → set `overall: CLEAN`.

# BUGBOT DISPATCH TEMPLATES

**PR slice (preferred):**
```
Full Repository Path: /home/joshua/Documents/ChoreBoyCodeStudio
Diff: branch changes
Custom Instructions: Review ONLY: <paths>. Ignore out-of-scope findings.
```

**Post-fix delta:**
```
Full Repository Path: /home/joshua/Documents/ChoreBoyCodeStudio
Diff: uncommitted changes
Custom Instructions: Scope: <paths>.
```

**SWEEP slice (no diff):**
```
Full Repository Path: /home/joshua/Documents/ChoreBoyCodeStudio
Diff: natural language
Change Description:
- app/shell/ (review): logic bugs, edge cases, error handling, resource lifecycle
Custom Instructions: In-scope paths only. No refactor suggestions unless bug fix.
```

# VERIFICATION

```bash
python3 testing/preflight_test_env.py
python3 testing/run_test_shard.py fast
npx pyright
```

# SESSION START

1. Read or create BUGBOT_PROGRAM_STATUS.md
2. Pick mode from git state or my message
3. Build slice list (Part C if SWEEP)
4. Run inner loop; do not ask permission between slices unless BLOCKED on product behavior
5. Rewrite status with next_actions for continuation

Begin now.
```

---

## Part C — SWEEP slice manifest (reuse thermo package boundaries)

Use for whole-package audits. Skip `__pycache__`. One slice = one row unless >15 files (then split by subdirectory).

| ID | Scope paths | Notes |
|----|-------------|-------|
| B0-1 | `app/bootstrap/`, `app/core/`, `app/support/`, `app/ui/`, `app/filesystem/` | core batch |
| B0-2 | `app/shell/` | split into B0-2a `main_window*`, B0-2b rest if >15 files |
| B0-3 | `app/editors/`, `app/syntax/` | editor seam |
| B0-4 | `app/intelligence/` | |
| B0-5 | `app/project/` | |
| B0-6 | `app/run/`, `app/runner/`, `app/debug/` | |
| B0-7 | `app/persistence/` | |
| B0-8 | `app/plugins/` | |
| B0-9 | `app/treesitter/` | |
| B0-10 | `app/packaging/` | |
| B0-11 | `app/python_tools/` | |
| B0-12 | `app/pytest/`, `app/templates/`, `app/examples/` | lower priority |

PR mode: **ignore this table** — derive slices from `git diff --name-only` grouped by top-level `app/<pkg>/`.

---

## Part D — Continuation prompt

```markdown
Continue the Bugbot Program Orchestrator (Composer 2.5 Fast).

Read `docs/code review/BUGBOT_PROGRAM_STATUS.md` and Part B–C of `BUGBOT_PROGRAM_ORCHESTRATOR.md`.

Resume `next_actions[0]`. Refresh slice inventory if `last_verified_commit` != HEAD.

Do not stop until overall: CLEAN (2× exit gate) or a BLOCKED item needs my product decision.
```

---

## Part E — Anti-patterns

| Anti-pattern | Why it fails |
|--------------|--------------|
| Bugbot implements fixes | Violates readonly; pollutes review signal |
| Parallel fixers on same files | Merge conflicts, duplicate patches |
| Loop forever on Low severity | Unbounded churn; waive or defer |
| One clean pass = done | Misses fix regressions; require 2× exit |
| Full SWEEP on every PR | Cost explosion; use PR mode |
| Duplicate thermo refactors | Scope creep; file splits ≠ bug fixes |

---

## Part F — Optional automation

| Mechanism | Config |
|-----------|--------|
| Semi-auto loop | `/loop 30m Continue bugbot program from BUGBOT_PROGRAM_STATUS.md` |
| Stop hook grind | `stop` hook → `followup_message` while status lacks `overall: CLEAN` and `loop_count < MAX` |
| Cloud overnight | Push branch → Cloud Agent + continuation prompt on branch |

See [`BUGBOT_PROGRAM_WORKFLOW.md`](BUGBOT_PROGRAM_WORKFLOW.md) for human steps.
