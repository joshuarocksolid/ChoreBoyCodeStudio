# TN-SHELL2-SETTINGS — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-SETTINGS  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**Scope:** `settings_dialog.py` (356 LOC), `settings_dialog_handlers.py` (778), `settings_models.py` (736), `settings_apply_workflow.py` (411), `settings_dialog_state.py` (56), `shell_preferences.py` (86), `file_project_commands_workflow.py` settings OK path (`handle_open_settings_action`). Cross-read: `settings_dialog_general.py` (343), `settings_dialog_sections.py` (316), `settings_dialog_tables.py` (101).

---

## Executive verdict

**REJECT — not thermo-clean, but Wave 1 P0 settings data-loss is fixed.** Shell Wave 1 blockers **CC-02** (dual-scope OK + highlighting field wipe) are **CLOSED**: `handle_open_settings_action` persists both `global_scope_snapshot()` and `project_scope_snapshot()`, and `GeneralTabState` round-trips highlighting runtime fields through `_snapshot_from_controls`. Decomposition also hit the R3 dialog-shell target (`settings_dialog.py` 356 LOC, down from 1,311). Dominant remaining risk: complexity was **relocated**, not deleted — `settings_dialog_handlers.py` is a **778-line untyped mixin** that absorbed most of the old god-class, `settings_models.py` remains a **736-line** parse/merge monolith, and `SettingsApplyBaseline` duplicates ~30 snapshot fields beside a parallel diff engine with at least one **dead flag** (`retention_policy_changed`). **CC-08** improved on the OK path (single `build_shell_preferences_bundle` from already-loaded payloads) but apply still unconditionally runs `apply_preferences_bundle` and full host mutation even for no-op toggles like auto-save-only. Schedule handler table splits and baseline/diff consolidation before adding more settings fields.

---

## Wave 1 CC re-validation

| CC | Wave 1 theme | Wave 2 status | Evidence |
|----|--------------|---------------|----------|
| **CC-02** | Settings OK data loss (dual-scope + highlighting wipe) | **CLOSED** | `file_project_commands_workflow.py:494–501` passes `global_snapshot=dialog.global_scope_snapshot()` and `project_snapshot=dialog.project_scope_snapshot()` into `merge_editor_settings_snapshot_for_scope`; dual-snapshot branch at `settings_models.py:553–575` merges global + project atomically. Highlighting: `GeneralTabState` includes `highlighting_*` (`settings_dialog_state.py:45–47`); `_snapshot_from_controls` spreads `general.to_snapshot_fields()` (`settings_dialog.py:277–279`). Tests: `test_merge_editor_settings_snapshot_for_scope_dual_snapshots_persist_global_edits`, `test_merge_editor_settings_snapshot_preserves_highlighting_runtime_fields`, `test_settings_dialog_state.py`. |
| **CC-08** | Settings/preferences load amplification | **PARTIAL** | OK path loads global + project once, builds `preferences_bundle` from merged payloads (`file_project_commands_workflow.py:507–515`), passes into apply — no second disk read when bundle supplied. Residual: `apply_after_settings_saved` always calls `apply_preferences_bundle` (`settings_apply_workflow.py:272`); `build_shell_preferences_bundle` still runs five parse passes per bundle; init/reload paths outside this slice still use `load_shell_preferences_bundle` via `shell_preferences_runtime.py`. Diff gating skips theme/editor/intelligence/shortcut work for auto-save-only (`test_apply_after_settings_saved_skips_expensive_paths_for_auto_save_toggle`) but not bundle apply. |
| **CC-21** | R3 hotspot modules oversized | **PARTIAL** | `settings_dialog.py` **356 LOC** (target <400 met). **778 LOC** `settings_dialog_handlers.py` + **736 LOC** `settings_models.py` remain ≥700 hotspots; package total ~2,686 LOC across seven modules vs prior ~2,300 in three — net spread, not net shrink. |

### Handlers monolith vs dialog split (356 LOC)

The split is **directionally correct** but **incomplete**. `SettingsDialog` is now a thin orchestrator (scope header, tab wiring, snapshot capture/apply). Event handlers, table population, validation, and reset logic moved into `SettingsDialogHandlersMixin` unchanged in shape — same method count, same implicit `self._*` coupling, same four `next(... LINT_RULE_DEFINITIONS ...)` chains. Code-judo next step: split mixin into **tab-scoped handler modules** (`settings_handlers_keybindings.py`, `settings_handlers_syntax.py`, `settings_handlers_linter.py`, `settings_handlers_files.py`) or a typed `SettingsDialogHost` protocol + small coordinator, not a single 778-line mixin.

---

### TN-SHELL2-SETTINGS-1 — Handlers monolith swapped in for dialog god-class

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `settings_dialog.py` 356 LOC; `settings_dialog_handlers.py` **778 LOC** — single `SettingsDialogHandlersMixin` with 40+ methods (`_populate_shortcut_table` through `_refresh_validation_state`). Mixin has no declared attribute contract; all state via undeclared `self._shortcut_table`, `self._linter_enabled_input`, etc.
- **Code-judo alternative:** Delete the mixin pattern. Return structured tab controllers from builders (`KeybindingsTabController`, `SyntaxTabController`, …) that own widgets + handlers; `SettingsDialog` holds controllers and delegates snapshot capture only.
- **Suggested remediation:** Wave 3 split handlers by tab domain; target **≤400 LOC per handler module**. Do not add new handler methods to the monolith.
- **Tests that would prove fix:** Existing `test_settings_dialog.py` / `test_settings_dialog_state.py` stay green; import smoke per handler module.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-SETTINGS-2 — `SettingsApplyBaseline` duplicates `EditorSettingsSnapshot` field-for-field

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `SettingsApplyBaseline` declares 30+ fields mirroring snapshot columns (`settings_apply_workflow.py:15–50`). `capture_settings_apply_baseline_from_snapshot` manually copies each field (`341–387`) — any new `EditorSettingsSnapshot` field requires three edits (dataclass, capture, diff) or diff silently misses it.
- **Code-judo alternative:** Baseline = `EditorSettingsSnapshot` + `effective_excludes: list[str]`. `build_settings_apply_diff(baseline_snapshot, updated_snapshot)` compares dataclass fields via a declared `SETTINGS_APPLY_DIFF_FIELDS` tuple or `dataclasses.fields` filter — one SSOT.
- **Suggested remediation:** Collapse `SettingsApplyBaseline` into snapshot + excludes; derive diff flags from field groups map `{ "theme_affecting": ("theme_mode", "ui_font_weight", ...) }`.
- **Tests that would prove fix:** Parametrize diff detection over all diff-tracked fields; fail if snapshot adds field not in diff map.
- **Handoff overlap:** R3, CC-08

---

### TN-SHELL2-SETTINGS-3 — `retention_policy_changed` computed but never consumed

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `SettingsApplyDiff.retention_policy_changed` set in `build_settings_apply_diff` (`settings_apply_workflow.py:109–114, 123`) but `apply_after_settings_saved` never reads `diff.retention_policy_changed`. Local-history retention edits rely on unconditional `apply_preferences_bundle` side effects.
- **Code-judo alternative:** Either wire retention changes to an explicit host hook (e.g. `apply_local_history_retention_policy`) or delete the flag and document that bundle apply owns retention — not both.
- **Suggested remediation:** If bundle apply handles retention, remove dead flag; else gate `apply_preferences_bundle` or add targeted retention apply when flag is true.
- **Tests that would prove fix:** Change only `local_history_retention_days`; assert retention hook fires once and unrelated paths (theme styles, relint) do not.
- **Handoff overlap:** CC-08, R3

---

### TN-SHELL2-SETTINGS-4 — Apply path always runs full preferences bundle even on narrow edits

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `apply_after_settings_saved` unconditionally calls `self._host.apply_preferences_bundle(resolved_bundle)` (`settings_apply_workflow.py:272`) before diff-gated editor/theme/shortcut paths. `test_apply_after_settings_saved_skips_expensive_paths_for_auto_save_toggle` asserts `editor_preferences_calls == 0` but still expects `len(host.applied_bundles) == 1`.
- **Code-judo alternative:** Split bundle into cheap metadata vs expensive runtime slices; apply bundle only when diff indicates main-window/intelligence/output/retention fields changed; timer/menu sync from diff flags.
- **Suggested remediation:** Extend diff model to cover bundle-affecting fields; skip `apply_preferences_bundle` when diff is empty aside from persist-only keys already saved to disk.
- **Tests that would prove fix:** Auto-save-only toggle: `applied_bundles == 0`; theme change: bundle + theme styles.
- **Handoff overlap:** CC-08, R2

---

### TN-SHELL2-SETTINGS-5 — Section builders still mutate private dialog surface (`dialog._*`)

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `settings_dialog_general.py:56–60` — `dialog._appearance_group = appearance_group`; `settings_dialog_sections.py` (keybindings/syntax/linter/files) assigns `dialog._shortcut_table`, `dialog._syntax_color_table`, etc. Handlers mixin reads the same private namespace with no `Protocol`.
- **Code-judo alternative:** `SettingsDialogWidgets` dataclass returned by builders; dialog exposes read-only property; handlers take widgets struct, not `self`.
- **Suggested remediation:** Introduce typed widget bundle in same R3 wave as handler split (TN-SHELL2-SETTINGS-1).
- **Tests that would prove fix:** Pyright on handler modules against widget bundle type; no new `dialog._foo` assignments outside builders.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-SETTINGS-6 — `settings_models.py` remains a 736-line parse/merge monolith

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** Single module owns `EditorSettingsSnapshot`, parse, merge, effective layering, project override diff/merge (`settings_models.py:110–737`). Fan-in 12 per manifest; every new preference touches merge + parse blocks.
- **Code-judo alternative:** Split `settings_snapshot.py` (dataclass + coercion helpers), `settings_merge.py` (payload merge + scope), `settings_effective.py` (layered parse only); keep re-exports in thin `settings_models.py`.
- **Suggested remediation:** Decompose when next adding settings keys; target **≤400 LOC** per module.
- **Tests that would prove fix:** Existing `test_settings_models.py` unchanged behavior; imports from public `settings_models` API stable.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-SETTINGS-7 — Lint handlers repeat linear `LINT_RULE_DEFINITIONS` scans

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `settings_dialog_handlers.py:564–566`, `576–578`, `588–590`, `617–619` — four identical `next((item for item in LINT_RULE_DEFINITIONS if item.code == code), None)` chains (Wave 1 TN-SHELL-SETTINGS-7 unfixed).
- **Code-judo alternative:** Module-level `LINT_RULE_BY_CODE: dict[str, LintRuleDefinition]` in `lint_profile.py` (canonical); handlers use `.get(code)`.
- **Suggested remediation:** One-line map import when touching linter tab.
- **Tests that would prove fix:** Behavior unchanged; existing lint override tests suffice.
- **Handoff overlap:** R3

---

### TN-SHELL2-SETTINGS-8 — `MainWindowSettingsSnapshot` positional tuples persist on apply boundary

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `settings_models.py:85–94` — `editor_preferences: tuple[int, int, str, ...]` (15 elements). `parse_main_window_settings` builds tuples (`328–344`); consumers unpack positionally in runtime apply (outside this slice).
- **Code-judo alternative:** Pass `EditorSettingsSnapshot` or named sub-dataclasses through `ShellPreferencesBundle.main_window` instead of tuples.
- **Suggested remediation:** Collapse tuples when touching `shell_preferences_runtime.apply_preferences_bundle`.
- **Tests that would prove fix:** Named-field assertions in `test_settings_models.py`; pyright on unpack sites.
- **Handoff overlap:** R3, CC-08, TN-SHELL-MW-04

---

### TN-SHELL2-SETTINGS-9 — OK-path orchestration is improved but lint apply reads host after bundle mutation

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** NEW
- **Severity:** NICE-TO-HAVE
- **Evidence:** `settings_apply_workflow.py:304–310` — relint decision compares `self._host.lint_rule_overrides()` / `diagnostics_enabled()` / `selected_linter()` **after** `apply_preferences_bundle`, not against `updated_snapshot` directly. Correct today only if bundle apply synchronously updates host before read; fragile ordering contract.
- **Code-judo alternative:** Diff lint fields from `updated_snapshot` vs baseline snapshot; relint when diff says so — no read-back from host.
- **Suggested remediation:** Add `lint_profile_changed` to `SettingsApplyDiff` computed from snapshot comparison; drop host read-back for decision.
- **Tests that would prove fix:** Host returns stale lint overrides after bundle apply; relint still fires when snapshot changed.
- **Handoff overlap:** R3, CC-08

---

### TN-SHELL2-SETTINGS-10 — Four-theme settings dialog: model correct, manual validation still undocumented

- **Persona:** TN-SHELL2-SETTINGS
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** Theme picker lists System + four resolved modes (`settings_dialog_general.py:61–67`); syntax tab four override dicts; swatch/validation use `tokens.border` / `tokens.diag_error_color` (`settings_dialog_handlers.py:463–485`). Appearance hidden on project scope (`handlers.py:118–119`). No automated four-theme dialog pass in test suite.
- **Code-judo alternative:** N/A — process gap.
- **Suggested remediation:** Manual acceptance rows in `docs/ACCEPTANCE_TESTS.md` for Settings in Light/Dark/HC Light/HC Dark.
- **Tests that would prove fix:** Manual checklist; optional offscreen token fixture later.
- **Handoff overlap:** none

---

## Four-theme UI impact (summary)

| Area | Light / Dark | HC Light / HC Dark | Notes |
|------|----------------|---------------------|--------|
| Shell chrome | `ShellThemeTokens` + `build_settings_style_sheet` | Same token path | Dialog gets tokens from `shell_theme_workflow().resolve_theme_tokens()` on open |
| Theme mode picker | Five modes incl. System | HC entries explicit | Global scope only — correct |
| Syntax colors | Per-theme override dicts | Dedicated HC columns in snapshot | Four `DEFAULT_*_PALETTE` sources |
| Validation | `tokens.diag_error_color` | HC-tuned via tokens | Swatch border uses `tokens.border` |
| Gaps | — | — | No documented four-theme manual pass (TN-SHELL2-SETTINGS-10) |

---

## Approval bar (thermo-nuclear)

**REJECT.** CC-02 closure and dialog decomposition are keepers — do not revert dual-snapshot merge or `GeneralTabState`. Blockers for thermo-clean in this slice:

1. **778 LOC handler mixin** without further split plan (TN-SHELL2-SETTINGS-1, CC-21).
2. **Baseline/diff duplication** and dead `retention_policy_changed` (TN-SHELL2-SETTINGS-2, TN-SHELL2-SETTINGS-3).
3. **Unconditional bundle apply** leaving CC-08 partial (TN-SHELL2-SETTINGS-4).

**Approve bar not met:** complexity relocated to handlers monolith; diff model half-wired; models module still ≥700 LOC. Safe to ship **behavior** (CC-02 closed); not safe to mark settings lane **thermo-clean** until handler/model decomposition and apply diff consolidation land.

---

## Integration cross-references

- **TN-SHELL-MW-04** — redundant preference reload on init (CC-08 remainder outside OK path).
- **TN-SHELL2-INTEG** — CC-02 stays CLOSED in Wave 1 supersession; CC-08/CC-21 remain PARTIAL.
- **Wave 1 TN-SHELL-SETTINGS-1…2** — superseded CLOSED; **3…8** — partially addressed; **9…10** — open/nice-to-have.
