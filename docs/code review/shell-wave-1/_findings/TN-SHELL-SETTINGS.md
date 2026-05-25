# TN-SHELL-SETTINGS — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-SETTINGS  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/settings_dialog.py` (1,311 LOC), `app/shell/settings_models.py` (692 LOC), `app/shell/settings_dialog_sections.py` (cross-read for R3 decomposition). Integration context: `app/shell/main_window.py` `_handle_open_settings_action` / post-dialog apply (`1709–1844`).

---

## Executive verdict

**Not thermo-clean.** R3 started tab extraction into `settings_dialog_sections.py`, but `settings_dialog.py` remains a **1.3k-line** dialog god-class with mirrored snapshot↔widget plumbing and four near-duplicate reset handlers. Worse, two **silent data-loss** paths sit on the OK path: (1) saving while **Project** scope is selected drops **Global** edits made earlier in the same session, because `merge_editor_settings_snapshot_for_scope` returns the original global payload unchanged and `MainWindow` never calls `dialog.global_scope_snapshot()`; (2) `_snapshot_from_controls` omits intelligence **highlighting** fields, so every merge rewrites them to dataclass defaults. The models layer (`settings_models.py`) is the right canonical home for parse/merge/effective layering, but `MainWindowSettingsSnapshot` still exposes positional tuples that amplify apply-path fragility (overlaps TN-SHELL-MW-04). Four-theme surface area is mostly token-driven and correctly scoped (global-only appearance + per-theme syntax palettes), but HC validation is undocumented for this dialog.

---

### TN-SHELL-SETTINGS-1 — Project-scope OK discards Global edits from the same session

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** BLOCKER
- **Evidence:** `app/shell/settings_models.py:556` — project-scope merge returns `(dict(global_settings_payload), merged_project_payload)` without applying dialog global edits. `app/shell/main_window.py:1748–1757` — uses `dialog.snapshot()` (active scope only) and `scope=selected_scope`; never `dialog.global_scope_snapshot()`. `app/shell/settings_dialog.py:430–432` — `global_scope_snapshot()` exists and captures both scopes on scope switch (`659–660`, `547–548`), but is unused by MainWindow.
- **Code-judo alternative:** On Accept, always persist **both** `_scope_snapshots[GLOBAL]` and `[PROJECT]` when project scope is available: `merge_editor_settings_snapshot(global_payload, dialog.global_scope_snapshot())` plus project diff merge from `dialog.project_scope_snapshot()`, regardless of which tab was focused at OK.
- **Suggested remediation:** Extend `merge_editor_settings_snapshot_for_scope` to accept optional `global_snapshot` / `project_snapshot` pair, or add `merge_editor_settings_snapshots_from_dialog(global_payload, project_payload, global_snap, project_snap)` that updates both layers atomically. Wire `_handle_open_settings_action` to both dialog accessors.
- **Tests that would prove fix:** `tests/unit/shell/test_settings_models.py` — edit global field in dialog memory, edit project field, OK with `selected_scope=project`; assert global payload changed. Qt test: switch Global → change tab width → Project → change exclude → OK; reload effective settings reflect **both**.
- **Handoff overlap:** R3 (models merge API), R2 (MainWindow apply)

---

### TN-SHELL-SETTINGS-2 — Settings OK wipes highlighting runtime fields not exposed in the dialog

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** BLOCKER
- **Evidence:** `app/shell/settings_dialog.py:496–545` — `_snapshot_from_controls` builds `EditorSettingsSnapshot(...)` with no `highlighting_adaptive_mode`, `highlighting_reduced_threshold_chars`, or `highlighting_lexical_only_threshold_chars`. `app/shell/settings_models.py:59–63` — fields exist on snapshot with defaults. `app/shell/settings_models.py:455–471` — `merge_editor_settings_snapshot` always writes intelligence highlighting keys from snapshot. `rg highlighting app/shell/settings_dialog.py` — zero matches.
- **Code-judo alternative:** Either (a) carry forward loaded values: parse current effective snapshot into dialog state and pass through unchanged fields in `_snapshot_from_controls`, or (b) add `EditorSettingsSnapshot.preserve_intelligence_runtime_fields(from: EditorSettingsSnapshot)` used at capture time, or (c) split “dialog-editable” vs “persisted intelligence runtime” so merge never touches keys the UI does not own.
- **Suggested remediation:** Minimal fix: store `_baseline_highlighting_*` from initial global snapshot in dialog and include in `_snapshot_from_controls`. Structural fix: narrow `merge_editor_settings_snapshot` to keys present in a `DialogEditableSnapshot` type.
- **Tests that would prove fix:** Given settings JSON with `highlighting_adaptive_mode: "reduced"`, open dialog, change unrelated checkbox, merge; assert mode still `"reduced"`. Regression against `tests/unit/shell/test_settings_models.py` highlighting cases.
- **Handoff overlap:** R3

---

### TN-SHELL-SETTINGS-3 — `settings_dialog.py` is 31% past the 1k-line rule; decomposition stalled mid-flight

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `wc -l` → 1,311 lines in `settings_dialog.py`; `settings_dialog_sections.py` exists (~318 LOC) but General tab alone remains ~200 lines of inline widget construction in `__init__` (`206–418`). Tab builders still mutate `dialog._*` private fields (`settings_dialog_sections.py:45–73`, `76–107`).
- **Code-judo alternative:** Finish R3 split: `settings_dialog_general.py` (appearance/output/editor/intelligence groups), `settings_dialog_tables.py` (column sizing, shortcut/syntax/lint table behaviors), thin `SettingsDialog` orchestrating scope + validation + snapshot capture only.
- **Suggested remediation:** Target dialog shell **under 400 LOC**; move table population/validation helpers next to their builders. Do not add new controls to `__init__` without extracting a section module in the same PR.
- **Tests that would prove fix:** Existing `tests/unit/shell/test_settings_dialog.py` stays green; optional import smoke that section modules load without constructing full dialog.
- **Handoff overlap:** R3

---

### TN-SHELL-SETTINGS-4 — Snapshot↔control mapping triplicated (capture, apply, reset)

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/settings_dialog.py:496–545` (`_snapshot_from_controls`), `562–629` (`_apply_snapshot_to_controls`), `720–759` (`_handle_reset_*_group_to_global`) — parallel field lists for editor/intelligence/output. Any new preference requires three edits; drift already visible (highlighting absent from capture only).
- **Code-judo alternative:** Declarative field binding table: `(attr_name, widget_getter, widget_setter, merge_key)` or small dataclass `GeneralTabState` with `from_snapshot` / `to_snapshot` / `reset_to(EditorSettingsSnapshot)` once.
- **Suggested remediation:** Introduce `settings_dialog_state.py` with grouped state objects per tab; dialog methods delegate. Collapse reset handlers into `reset_group("editor", baseline_snapshot)`.
- **Tests that would prove fix:** Round-trip test: snapshot → apply → capture equals snapshot for all dialog-owned fields (parametrize groups).
- **Handoff overlap:** R3

---

### TN-SHELL-SETTINGS-5 — MainWindow settings apply ignores dialog’s dual-scope API and re-parses disk six times

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1748–1809` — after save, six `_load_*` calls each hit `_load_main_window_settings()` (see TN-SHELL-MW-04-1). Open path loads global + effective twice (`1710–1720`) before dialog construction.
- **Code-judo alternative:** `_handle_open_settings_action` returns an `AppliedSettingsResult` built from **one** `parse_effective_main_window_settings` after save; apply to `MainWindow` fields in one unpack block. Dialog side already centralizes edits into snapshots — runtime apply should consume snapshots, not re-read JSON immediately.
- **Suggested remediation:** Pair with MW-04 preferences loader; pass merged effective snapshot from dialog close into apply handler to avoid redundant I/O and to enable snapshot-first apply (also fixes TN-SHELL-SETTINGS-1 if both scopes merged before reload).
- **Tests that would prove fix:** Mock `SettingsService.load_global` count == 1 per settings OK in integration test.
- **Handoff overlap:** R2 (MainWindow), R3 (models)
- **Handoff overlap note:** Dedup with **TN-SHELL-MW-04-1**, **TN-SHELL-MW-04-3**.

---

### TN-SHELL-SETTINGS-6 — `MainWindowSettingsSnapshot` positional tuples obscure the apply contract

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/settings_models.py:85–93` — `editor_preferences: tuple[int, int, str, ...]` (15 elements). `app/shell/main_window.py:1765–1780` — positional unpack with no field names at call site.
- **Code-judo alternative:** Reuse `EditorSettingsSnapshot` (or slim named dataclasses `EditorRuntimePrefs`, `CompletionRuntimePrefs`) end-to-end; delete tuple facades in `parse_main_window_settings`.
- **Suggested remediation:** R3 models cleanup when touching settings apply; avoid adding tuple elements when new editor prefs land.
- **Tests that would prove fix:** Extend `test_parse_main_window_settings_*` to assert named fields; pyright strict on MainWindow unpack sites.
- **Handoff overlap:** R3
- **Handoff overlap note:** **TN-SHELL-MW-04-6**.

---

### TN-SHELL-SETTINGS-7 — Lint rule handlers repeat `next(... LINT_RULE_DEFINITIONS ...)` lookup chains

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/settings_dialog.py:1119–1121`, `1131–1133`, `1143–1145`, `1172–1176` — identical linear search by `code` in four handlers.
- **Code-judo alternative:** Module-level `LINT_RULE_BY_CODE: dict[str, LintRuleDefinition]` built once from `LINT_RULE_DEFINITIONS` (canonical home: `lint_profile.py`).
- **Suggested remediation:** Import map; replace four `next(...)` blocks with `LINT_RULE_BY_CODE.get(code)` guard.
- **Tests that would prove fix:** No behavior change; existing lint override dialog tests suffice.
- **Handoff overlap:** R3

---

### TN-SHELL-SETTINGS-8 — Section builders couple to private dialog surface (`dialog._*`)

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/settings_dialog_sections.py:40–73` — `build_keybindings_tab` assigns `dialog._shortcut_table`, `dialog._shortcut_search_input`, etc. `TYPE_CHECKING` import only — runtime is untyped struct mutation.
- **Code-judo alternative:** `SettingsDialogTabs` dataclass returned by builders (tables, inputs, indices); `SettingsDialog` holds one `_tabs: SettingsDialogTabs` with explicit attributes.
- **Suggested remediation:** When splitting files (TN-SHELL-SETTINGS-3), pass back structured tab handles instead of widening `SettingsDialog` private namespace.
- **Tests that would prove fix:** Type-check `settings_dialog_sections` against a `Protocol` for required dialog host methods (`_populate_shortcut_table`, etc.) or eliminate host entirely.
- **Handoff overlap:** R3

---

### TN-SHELL-SETTINGS-9 — Four-theme UI: correct model, manual HC validation gap

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/settings_dialog.py:225–237` — theme combo lists System + Light + Dark + HC Light + HC Dark with WCAG tooltip. `app/shell/settings_dialog_sections.py:83–86` — syntax palette selector maps four `THEME_*` keys to separate override dicts (`531–538` in dialog capture). `app/shell/settings_dialog.py:115–118` — `build_settings_style_sheet(tokens)`; `1027–1036` — swatch border uses `tokens.border`, validation uses `tokens.diag_error_color`. `app/shell/settings_dialog.py:682–683` — Appearance group hidden in project scope (global-only theme). `app/core/constants.py:264–273` — `GLOBAL_ONLY_SETTINGS_ROOT_KEYS` includes theme/syntax/keybindings.
- **Code-judo alternative:** N/A — architecture is sound; gap is process.
- **Suggested remediation:** Add manual acceptance rows in `docs/ACCEPTANCE_TESTS.md` for Settings dialog in all four resolved themes (focus rings, segmented scope control, syntax swatches, invalid-color error border in HC modes). No per-theme hardcoded colors in new controls.
- **Tests that would prove fix:** Manual checklist; optional offscreen Qt screenshot test per theme token fixture if automation is later requested.
- **Handoff overlap:** none (manual QA)

---

### TN-SHELL-SETTINGS-10 — Mid-file import split and inline import in button builder

- **Persona:** TN-SHELL-SETTINGS
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/settings_dialog.py:66–74` — `_VALID_SYNTAX_THEME_KEYS` inserted between import blocks. `app/shell/settings_dialog_sections.py:293–294` — `from PySide2.QtGui import QIcon` inside `build_buttons_row`.
- **Code-judo alternative:** Move constant below all imports; hoist button-row imports to module top.
- **Suggested remediation:** Style-only cleanup when next touching those files.
- **Tests that would prove fix:** Lint/import order unchanged behavior.
- **Handoff overlap:** none

---

## Four-theme UI impact (summary)

| Area | Light / Dark | HC Light / HC Dark | Notes |
|------|----------------|---------------------|--------|
| Shell chrome | via `ShellThemeTokens` + `build_settings_style_sheet` | Same token path; HC uses thicker focus via `focus_border_width` elsewhere | Dialog constructed with `tokens=self._resolve_theme_tokens()` in MainWindow |
| Theme mode picker | All five modes (incl. System) | HC entries explicit (`UI_THEME_MODE_HIGH_CONTRAST_*`) | Hidden on Project scope — correct (global-only) |
| Syntax colors | Per-theme override dict | Dedicated HC Light/Dark columns in snapshot | Four palette defaults from `DEFAULT_*_PALETTE`; no editor preview in dialog |
| Validation / errors | `tokens.diag_error_color` on invalid hex | HC error color tuned in token set | Swatch border uses `tokens.border` — OK |
| Gaps | — | — | No automated four-theme dialog pass documented (TN-SHELL-SETTINGS-9) |

---

## Approval bar (thermo-nuclear)

**Blocked** until TN-SHELL-SETTINGS-1 and TN-SHELL-SETTINGS-2 are fixed or explicitly accepted with product sign-off. Structural debt (3–8) should be scheduled in R3 before adding more settings fields. Coordinate P1 “single effective settings load” with TN-SHELL-MW-04 integration rollup.

---

## Integration cross-references

- **TN-SHELL-MW-04-1 / 04-3 / 04-6** — redundant `_load_main_window_settings` and tuple unpack on apply path.
- **TN-SHELL-MW-01-3** — `ShellPreferencesSnapshot` initiative aligns with models/dialog snapshot consolidation.
