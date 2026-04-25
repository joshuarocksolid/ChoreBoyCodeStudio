# Test and Tooling Audit — Status (2026-04-25)

## Scope

Follow-up to [AUDIT_app_remaining_handoff.md](AUDIT_app_remaining_handoff.md) §R6: test brittleness, private-widget coupling, and optional static tools.

## Decision: no new repo-wide tools in this pass

- **Ruff / Vulture / Radon / Lizard** are not added. The repo already uses `pyright` (see [AGENTS.md](../../AGENTS.md)) and pytest with a risk-first test policy (see [.cursor/rules/testing_when_to_write.mdc](../../.cursor/rules/testing_when_to_write.mdc)).
- Adding another linter or complexity scanner would need: AppRun/no-venv execution story, Python 3.9 compatibility, CI alignment, and proof of low noise — deferred until a concrete recurring failure class justifies it.

## Test suite hygiene (ongoing)

- Prefer **public behavior** assertions (signals, model state) over private widget names in `tests/unit/shell/` and `tests/unit/editors/`.
- Delete or rewrite tests that only pin layout object identity when a future R3/R6 follow-up touches the same UI.

## Validation reference

```bash
python3 testing/run_test_shard.py fast
npx pyright
```
