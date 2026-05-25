# Shell Wave 1 Fix — Verification & Follow-up Agent Handoff

**Audience:** Next agent verifying remediation work and completing remaining plan items.  
**Plan source:** [`shell_wave_1_fixes_6043ec1f.plan.md`](../../../.cursor/plans/shell_wave_1_fixes_6043ec1f.plan.md) (Cursor plan) and [`shell_wave_1_thermo_review_2026-05-25.md`](shell_wave_1_thermo_review_2026-05-25.md).  
**Status:** Implementation pass complete; **not committed**. Needs verification + follow-ups before PR.

---

## Your mission

1. **Verify** P0 fixes and workflow wiring with tests and targeted manual checks.
2. **Fix** anything broken (especially parallel `fast` shard if still flaky).
3. **Complete** follow-up extractions listed below without regressing P0 behavior.
4. **Do not** grow `MainWindow` method count — baseline after this pass is **325** (was 332).

Read first: `docs/PRD.md`, `docs/ARCHITECTURE.md`, `AGENTS.md`, `.cursor/rules/ui_light_dark_mode.mdc`.

---

## What was implemented

### P0 blockers (CC-01 … CC-05) — should be done

| CC | Change | Key files |
|----|--------|-----------|
| CC-01 | Removed agent debug logging | `python_console_widget.py`, `main_window.py`, `repl_completion.py` |
| CC-02 | Dual-scope settings OK + highlighting field preservation | `settings_models.py`, `settings_dialog.py`, `main_window.py` |
| CC-04 | HC syntax overrides via `parse_syntax_color_overrides` | `main_window.py` |
| CC-03 | Tree delete save gate; external reload themed dialog; decline-reload fix | `save_workflow.py`, `main_window.py`, `project_tree_action_workflow.py` |
| CC-05 | Unified draft recovery helper | `local_history_workflow.py` |

**Gate:** `rg 'debug-0b96d3|#region agent log' app/` must be empty.

### New workflow modules (created, partially wired)

| Module | Wired to MainWindow? | Notes |
|--------|----------------------|-------|
| `shell_preferences.py` | Via `settings_apply_workflow` | Single-load preferences bundle |
| `shell_composition.py` | Yes | Host adapters + builders |
| `settings_apply_workflow.py` | Yes | Replaces inline settings-OK apply block |
| `python_console_workflow.py` | Yes | Replaces `_request_python_console_completion_async` body |
| `project_tree_action_workflow.py` | Yes | Tree delete/bulk delete |
| `external_file_change_workflow.py` | Yes | `_check_for_external_file_change` |
| `editor_sync_workflow.py` | Via external reload | Unified disk→editor sync |
| `shell_theme_workflow.py` | **No** | Module + tests only |
| `editor_session_workflow.py` | Via `local_history_workflow` | Session persist/restore split |
| `draft_autosave_workflow.py` | Via `local_history_workflow` | Autosave split |
| `settings_dialog_state.py` | Yes | General tab state SSOT |

### MainWindow slimming

- Removed 6 help pass-through methods; `menu_wiring.py` calls `_help_controller` directly.
- Removed `_schedule_realtime_lint` / `_run_scheduled_realtime_lint`; timer wired via `build_realtime_lint_runner`.
- Tree delete, external reload, settings apply, console completion delegated to workflows.
- **Init order fix:** workflow builders run **after** `_project_tree_action_coordinator` (was broken earlier).

---

## Verification checklist (run in order)

```bash
# P0 hygiene
rg 'debug-0b96d3|#region agent log' app/

# Method count (must not increase; target follow-up < 280)
rg "^    def " app/shell/main_window.py | wc -l

# Test shards
python3 testing/run_test_shard.py fast
python3 testing/run_test_shard.py integration
python3 testing/run_test_shard.py runtime_parity

# Typecheck (repo baseline may have pre-existing noise; check changed files)
npx pyright app/shell/shell_preferences.py app/shell/shell_composition.py \
  app/shell/settings_apply_workflow.py app/shell/external_file_change_workflow.py \
  app/shell/project_tree_action_workflow.py app/shell/local_history_workflow.py
```

### Targeted unit tests (high signal)

```bash
python3 run_tests.py tests/unit/shell/test_settings_models.py \
  tests/unit/shell/test_main_window_syntax_override_loading.py \
  tests/unit/shell/test_save_workflow.py \
  tests/unit/shell/test_local_history_workflow.py \
  tests/unit/shell/test_project_tree_action_workflow.py \
  tests/unit/shell/test_external_file_change_workflow.py \
  tests/unit/shell/test_settings_apply_workflow.py \
  tests/unit/shell/test_shell_preferences.py \
  tests/unit/shell/test_main_window_tree_delete_copy.py -v
```

### Integration tests (must pass)

```bash
python3 run_tests.py tests/integration/shell/ -v
```

**Known issue to investigate:** parallel `fast` shard returned exit 1 early in one run (possible xdist/collection flake). Single-worker and integration passed after init-order fix. Re-run `fast` and diagnose if still failing.

### Manual acceptance (P0 + four-theme)

See `docs/ACCEPTANCE_TESTS.md`. Minimum manual checks:

1. **Settings dual-scope:** Edit global field → switch to Project → edit project field → OK → both persist.
2. **HC syntax override:** Set HC Light keyword color → switch theme → color applies.
3. **Tree delete:** Dirty open tab → delete file in tree → save prompt appears.
4. **External reload:** Dirty tab → change file on disk → themed unsaved dialog (not raw QMessageBox).
5. **Draft recovery:** Recovery Center with dirty tab where draft matches disk but not buffer → dialog shown, not auto-dismissed.
6. **Four themes:** Spot-check settings dialog, draft recovery dialog, external reload dialog in Light, Dark, HC Light, HC Dark.

---

## Follow-up work (priority order)

### 1. Wire `ShellThemeWorkflow` (CC-09 partial)

- Module exists: `app/shell/shell_theme_workflow.py` + `tests/unit/shell/test_shell_theme_workflow.py`
- Replace `MainWindow._resolve_theme_tokens`, `_apply_theme_styles`, `_apply_explorer_theme`, syntax/theme loaders with delegation.
- **Net reduce** MainWindow methods; do not add one-line delegators.
- Consider deferring full tree repopulate on every theme pass (CC-09).

### 2. Remaining R2 workflows (not started)

Extract with typed host ports (pattern: `shell_composition.py` adapters):

- `RunLaunchWorkflow` + typed `DebugTarget` (CC-14)
- `SemanticNavigationWorkflow` (CC-15) — ~430 lines from MainWindow
- `FindReplaceWorkflow` + delete ghost search pipeline (CC-17, CC-20)
- `BreakpointStore` in `DebugControlWorkflow` (CC-12)
- `ProjectLoadWorkflow` / `SettingsApplyWorkflow` already partially done; `ProjectLoadWorkflow` for `_apply_loaded_project` (CC-11)
- `RuntimeOnboardingWorkflow` (CC-10)

### 3. R3 hotspot splits (partial)

Done: `editor_session_workflow`, `draft_autosave_workflow`, `settings_dialog_state`.

Still oversized — split per plan:

- `outline_panel.py` → `app/shell/outline/` package
- `debug_panel_widget.py` → `app/shell/debug_panel/`
- `test_explorer_panel.py` → extract icons module
- `settings_dialog.py` → finish section file split (target shell < 400 LOC)

### 4. CC-23 four-theme gaps

- Outline kind colors, console stderr hex, QSS omissions (`threadsTree`, `debugFailedBtn`)
- Record manual validation in completion summary

### 5. CC-24 / CC-25 test cleanup

- Migrate more tests off `MainWindow.__new__` where workflow public API exists
- Tree delete: one thin delegation test remains in `test_main_window_tree_delete_copy.py` (intentional)

### 6. Hygiene

- Delete untracked `.cursor/debug-0b96d3.log` if present (leftover from removed instrumentation); ensure `.gitignore` covers `.cursor/debug-*.log` if appropriate.
- Remove unused imports (e.g. `load_shell_preferences_bundle` if only used via workflow).

---

## Global rules (every follow-up PR)

From `docs/deslop/AUDIT_app_remaining_handoff.md` §3:

- **MainWindow method count must go down** on every touching PR.
- **No new one-line delegators.**
- Hard cutover — no legacy fallback chains.
- Python 3.9 source compatibility.
- Tests only when risk-first gate passes (`.cursor/rules/testing_when_to_write.mdc`).
- UI changes: validate all four theme modes or document gap.

---

## Files changed (uncommitted)

**Modified:** `repl_completion.py`, `local_history_workflow.py`, `main_window.py`, `menu_wiring.py`, `python_console_widget.py`, `save_workflow.py`, `settings_dialog.py`, `settings_models.py`, plus test files.

**New:** All `app/shell/*_workflow.py`, `shell_preferences.py`, `shell_composition.py`, `settings_dialog_state.py`, and corresponding `tests/unit/shell/test_*.py`.

---

## Suggested agent prompt (copy-paste)

```
You are verifying and completing Shell Wave 1 thermo review remediation in ChoreBoyCodeStudio.

Read: docs/code review/shell-wave-1/shell_wave_1_fix_verification_handoff.md

Tasks:
1. Run verification checklist; fix any failures.
2. Wire ShellThemeWorkflow into MainWindow (net -methods).
3. Tackle highest-value R2 follow-ups (RunLaunch, SemanticNavigation, or FindReplace) one at a time.
4. Do not commit unless asked; report metrics (MainWindow method count, test shard results).

Constraints: Python 3.9, four-theme UI rule, no MainWindow method count increase, hard cutover only.
```
