# Code Review Wave Artifacts

Point-in-time thermo-nuclear review records. These are **not operational runbooks**.

## Active programs (orchestrators)

### Thermo-nuclear (maintainability) — COMPLETE @ 2026-06-22

| Resource | Purpose |
|----------|---------|
| [`.cursor/agents/thermo-program-orchestrator.md`](../../.cursor/agents/thermo-program-orchestrator.md) | Custom agent — `/thermo-program-orchestrator` |
| [`THERMO_PROGRAM_WORKFLOW.md`](THERMO_PROGRAM_WORKFLOW.md) | Human workflow |
| [`THERMO_PROGRAM_ORCHESTRATOR.md`](THERMO_PROGRAM_ORCHESTRATOR.md) | Full prompt, roadmap, gates |
| [`PROGRAM_STATUS.md`](PROGRAM_STATUS.md) | Live state |

### Bugbot (review → fix loop)

| Resource | Purpose |
|----------|---------|
| [`.cursor/agents/bugbot-program-orchestrator.md`](../../.cursor/agents/bugbot-program-orchestrator.md) | Custom agent — `/bugbot-program-orchestrator` |
| [`BUGBOT_PROGRAM_WORKFLOW.md`](BUGBOT_PROGRAM_WORKFLOW.md) | Human workflow |
| [`BUGBOT_PROGRAM_ORCHESTRATOR.md`](BUGBOT_PROGRAM_ORCHESTRATOR.md) | Modes, slice manifest, dispatch templates |
| [`BUGBOT_PROGRAM_STATUS.md`](BUGBOT_PROGRAM_STATUS.md) | Live state (created on first run) |

One-shot review without fix loop: `/review-bugbot` skill.

## Contents

- [`run-wave-1/`](run-wave-1/) — run/debug/runner subsystem findings
- [`shell-wave-1/`](shell-wave-1/) — shell/UI subsystem findings (2026-05-25 baseline)
- [`shell-wave-2/`](shell-wave-2/) — shell/UI delta re-baseline after Wave 1 remediation (2026-06-17)
- [`editors-wave-1/`](editors-wave-1/) — editors subsystem findings + Wave 2 closure (2026-06-17)
- [`intelligence-wave-1/`](intelligence-wave-1/) — intelligence + shell/editor seam findings (2026-06-16)
- [`project-ssot-wave-1/`](project-ssot-wave-1/) — R4/R5 project inventory + dependency classifier SSOT findings (2026-06-16)

## Current backlog

For active follow-up work, see:

- [`docs/code review/shell-wave-2/shell_wave_2_remediation_plan.md`](../code%20review/shell-wave-2/shell_wave_2_remediation_plan.md) — **Shell Wave 2** remediation strategy (2026-06-17)
- [`docs/code review/shell-wave-2/shell_wave_2_implementation_plan.md`](../code%20review/shell-wave-2/shell_wave_2_implementation_plan.md) — **Shell Wave 2** end-to-end implementation plan (22 PRs, SHELL-R-01…SHELL-R-22, CC-SHELL2-01…CC-SHELL2-22)
- [`docs/code review/editors-wave-1/editors_wave_2_remediation_plan.md`](../code%20review/editors-wave-1/editors_wave_2_remediation_plan.md) — **Editors Wave 2** remediation strategy (closure 2026-06-17)
- [`docs/code review/editors-wave-1/editors_wave_2_implementation_plan.md`](../code%20review/editors-wave-1/editors_wave_2_implementation_plan.md) — **Editors Wave 2** implementation plan
- [`docs/code review/intelligence-wave-1/intelligence_wave_1_remediation_plan.md`](../code%20review/intelligence-wave-1/intelligence_wave_1_remediation_plan.md) — **Intelligence Wave 1** remediation strategy (2026-06-16)
- [`docs/code review/intelligence-wave-1/intelligence_wave_1_implementation_plan.md`](../code%20review/intelligence-wave-1/intelligence_wave_1_implementation_plan.md) — **Intelligence Wave 1** end-to-end implementation plan (18 PRs, CC-01…CC-23)
- [`docs/code review/project-ssot-wave-1/project_ssot_wave_1_remediation_plan.md`](../code%20review/project-ssot-wave-1/project_ssot_wave_1_remediation_plan.md) — **Project SSOT Wave 1** R4/R5 remediation strategy (2026-06-16)
- [`project-ssot-wave-1/project_ssot_wave_1_implementation_plan.md`](../code%20review/project-ssot-wave-1/project_ssot_wave_1_implementation_plan.md) — **Project SSOT Wave 1** end-to-end implementation plan (25 PRs, PROJ-R-01…PROJ-R-25)
- [`docs/code review/run-wave-1/run_wave_1_remediation_plan.md`](../code%20review/run-wave-1/run_wave_1_remediation_plan.md) — **Run Wave 1** remediation strategy (2026-06-22 re-baseline)
- [`docs/code review/run-wave-1/run_wave_1_implementation_plan.md`](../code%20review/run-wave-1/run_wave_1_implementation_plan.md) — **Run Wave 1** end-to-end implementation plan (25 PRs, RUN-R-01…RUN-R-25, CC-01…CC-25)
- [`docs/deslop/AUDIT_app_remaining_handoff.md`](../deslop/AUDIT_app_remaining_handoff.md)
- [`docs/TASKS.md`](../TASKS.md)

Do not treat quantitative metrics or open-action items in wave manifests as current unless re-verified against the live tree.
