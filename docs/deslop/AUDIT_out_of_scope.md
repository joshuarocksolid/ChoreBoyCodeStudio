# Deslop Audit — Out Of Scope (tests, scripts, plugins, templates, examples, launchers)

**Status:** handoff v1 (2026-04-25)  
**Related:** [AUDIT_app.md](AUDIT_app.md) (historical `app/` audit), [AUDIT_app_remaining_handoff.md](AUDIT_app_remaining_handoff.md) (remaining `app/` work)

## 1. Purpose

The original app deslop pass intentionally excluded non-`app/` trees. This document records **follow-up audit targets** so agents can file small PRs without mixing them into the historical `app/` audit narrative.

## 2. Scope

| Area | Path | Notes |
| --- | --- | --- |
| Tests | `tests/` | Prioritize brittleness, private-widget coupling, and low-signal assertions over raw LOC. |
| Scripts | `scripts/` | One-off automation; refactor when touched. |
| Bundled plugins | `bundled_plugins/` | Must stay consistent with plugin manifest and host contracts. |
| Templates | `templates/` (repo root) | User-facing starter content; copy and structure matter. |
| Examples | `example_projects/` | Help-only; see [docs/ARCHITECTURE.md](../ARCHITECTURE.md) §18.4. |
| Launchers | `run_editor.py`, `run_runner.py`, `run_plugin_host.py` | Thin AppRun entrypoints; keep stable. |
| Packaging scripts | Repo root / `package.py` helpers | Product packaging contract; see [AGENTS.md](../../AGENTS.md) and [docs/PACKAGING.md](../PACKAGING.md) if present. |

## 3. Finding categories (for future briefs)

Use these labels when filing issues or PR descriptions:

1. **Must fix before release** — security, data loss, broken install, or CI blockers.
2. **Refactor when touched** — style, duplication, or clarity issues with no standalone urgency.
3. **Do not touch unless product scope changes** — stable, working surfaces with high churn cost.

## 4. Suggested first passes

1. **Tests:** search for `._` widget access in `tests/unit/shell/` and `tests/integration/shell/`; list candidates for public-signal rewrites.
2. **Root launchers:** confirm they only bootstrap `sys.path` + `runpy` and do not duplicate app logic.
3. **Bundled plugins:** run manifest validation and grep for hidden-path tokens (forbidden on ChoreBoy; see [docs/DISCOVERY.md](../DISCOVERY.md) §4A).
4. **Templates / examples:** ensure `template.json` / metadata align with [docs/ARCHITECTURE.md](../ARCHITECTURE.md) project model.

## 5. What this document is not

- Not a second copy of the `app/` slop catalog; do not merge duplicate “fixed vs open” status here.
- Not a commitment to line-count refactors in `tests/` without risk-first justification.

End of out-of-scope audit handoff.
