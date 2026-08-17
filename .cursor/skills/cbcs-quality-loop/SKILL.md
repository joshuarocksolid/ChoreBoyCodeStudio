---
name: cbcs-quality-loop
description: Parent-only pstack eval and hillclimb loop for the verify-cbcs skill. Never plant this directory into a candidate worktree. Use when measuring or improving how agents drive the live ChoreBoy Code Studio editor.
---

# CBCS quality loop (parent only)

This skill is for the **parent** (you). It is not a user-facing drive recipe.

The lever candidates may see is [../verify-cbcs/SKILL.md](../verify-cbcs/SKILL.md). That tree must stay free of eval / judge / arena / candidate / rubric / score / benchmark framing. Do not copy this file, `references/`, or `scripts/` into a worktree you hand a candidate.

Follow pstack:

- Eval playbook: poteto-mode `playbooks/eval.md`
- Hillclimb playbook: poteto-mode `playbooks/hillclimb.md`
- Arena skill for fan-out + one blinded judge
- Models: `~/.cursor/rules/pstack-models.mdc` (`arena runners`, `arena cross-judge pool`, `hillclimb`)

## When to use which

| Goal | Loop |
|------|------|
| Did a skill/recipe change make agents drive better? | **Eval** (blinded candidates, one judge) |
| Drive one metric up with keep-or-revert iterations | **Hillclimb** (frozen ruler, `decisions.tsv`) |

Do not start a multi-model arena while generating or first-proving `verify-cbcs`. Take a baseline with the frozen ruler first.

## Eval

### Frame

Variant under test: the `verify-cbcs` skill (or a later recipe patch). Success: the agent launches an isolated live editor, doctors it, drives the real Qt path, and leaves proof.

Judge-only criteria: [references/judge-criteria.md](references/judge-criteria.md).

Organic prompts: [references/organic-prompts.md](references/organic-prompts.md). Give the candidate **only** the prompt and a planted `verify-cbcs` skill. No “follow the skill”, no principle chain, no mention of judging.

### Blinding (non-negotiable)

In anything the candidate can see (paths, files, prompt):

- No `eval`, `test`, `judge`, `experiment`, `rubric`, `score`, `compare`, `benchmark`, `candidate`, or `arena` in directory or file names you create for them.
- Worktree names look like projects (`studio-launch`, `notes-on-open`), not `candidate-1`.
- Do not tell them other arms exist.
- The judge may know it is judging. It sees outputs by sanitized label only, never a model name.
- One judge scores every arm in a single pass.

`verify-cbcs` uses product words like “Test Explorer”. That is the app. Do not add meta words on top.

### Run

1. Sanitized worktree per arm. Plant `.cursor/skills/verify-cbcs/` only.
2. Same organic prompt to each arena runner (pstack-models `arena runners`).
3. One blinded judge on a different model family (`arena cross-judge pool`).
4. You read every transcript under this workspace’s `agent-transcripts/`. Grade chain-following from files opened and the shape of the drive, not self-report.
5. Synthesize. Promote the variant only if the judge and your reading agree it is better on the rubric.

## Hillclimb

### Ruler (freeze after the first honest baseline)

Documented in [references/hillclimb-ruler.md](references/hillclimb-ruler.md).

One command family:

```bash
.cursor/skills/cbcs-quality-loop/scripts/measure-m1 --repo /Users/local/Projects/ChoreBoyCodeStudio
```

Emits `passed` / `total` (M1 is 1/1), artifact dir, and wall time. After you freeze it, changing the command invalidates every earlier number.

Direction: higher pass rate, then lower time-to-first-proof among full passes.

Stop predicate: M1–M6 all pass on two consecutive isolated runs **and** at least 8 logged iterations. A lucky first win cannot stop the run. Expanding from M1 to M1–M6 is a ruler change — freeze a new command and start a new log.

### Gate

If a Linux AppRun exists: `python3 testing/run_test_shard.py fast` beside the ruler. If it does not (Mac cockpit): write `gate=skipped-no-apprun` and do **not** treat that skip as product proof.

### Loop

1. Log path: `~/ChoreBoy/artifacts/verify-cbcs/decisions.tsv` (out of git; survives reverts).
2. One hypothesis per iteration, grounded in how launch/drive actually works.
3. Hand the change to a hillclimb-model subagent; review the diff.
4. Measure with the frozen command. Keep only if the metric moves past noise and the gate is green or honestly skipped.
5. Otherwise revert in full. Log the row either way.

First hillclimb target is **the skill** (recipes, handles, helper). If a live drive shows a product bug, report it. Do not paper over it in the feature map.

## Evidence

- Live proof and ruler output: `~/ChoreBoy/artifacts/verify-cbcs/<run-id>/`
- Hillclimb log: `~/ChoreBoy/artifacts/verify-cbcs/decisions.tsv`
- Never commit screenshots or the TSV
