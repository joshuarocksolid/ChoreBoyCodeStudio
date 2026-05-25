# TN-SHELL-MW-03 — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-MW-03  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/main_window.py` lines 1118–1395 — outline layout hooks, theme token resolution, stylesheet application, and adjacent settings loaders through zoom handlers (slice boundary per manifest).

**Context:** `main_window.py` is **5,549 LOC** with **332** methods — far beyond the thermo 1k-line smell. This slice is not the sole cause, but it concentrates two high-churn concerns (explorer outline layout + global theme orchestration) that R2/R3 explicitly target for extraction.

---

## Executive verdict

**Not thermo-clean.** The dominant risk is **four-theme correctness**: high-contrast syntax color overrides are resolved at runtime but never loaded into `MainWindow._syntax_color_overrides`, so HC Light/HC Dark custom syntax colors silently fall back to base tokens while the settings dialog persists all four scopes. Structurally, this slice is a **coordination knot** — seven outline handler/apply methods plus a 50+ line `_apply_theme_styles` fan-out that rebuilds the project tree on every theme pass — with no `ShellThemeWorkflow` / layout workflow counterpart to the existing `SaveWorkflow` / `PythonStyleWorkflow` pattern from R2. Code-judo path: one canonical syntax-override loader, a theme workflow that owns token resolution + child `apply_theme*` dispatch (without full tree repopulate), and outline layout state owned beside `layout_persistence.py` rather than as more `MainWindow` methods.

---

### TN-SHELL-MW-03-1 — HC syntax overrides never reach `_resolve_theme_tokens`

- **Persona:** TN-SHELL-MW-03
- **Severity:** BLOCKER
- **Evidence:** `app/shell/main_window.py:1318-1324` — loader returns only light/dark keys:

```python
return {
    constants.UI_SYNTAX_COLORS_LIGHT_KEY: dict(snapshot.syntax_color_overrides_light),
    constants.UI_SYNTAX_COLORS_DARK_KEY: dict(snapshot.syntax_color_overrides_dark),
}
```

  `app/shell/main_window.py:1195-1208` — resolver selects HC keys when `base_tokens.is_high_contrast`:

```python
theme_key = (
    constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_DARK_KEY
    if base_tokens.is_dark
    else constants.UI_SYNTAX_COLORS_HIGH_CONTRAST_LIGHT_KEY
)
syntax_overrides = self._syntax_color_overrides.get(theme_key, {})
```

  Canonical four-scope parsing already exists: `app/shell/syntax_color_preferences.py:63-75` (`parse_syntax_color_overrides`). Snapshot carries HC fields: `app/shell/settings_models.py:72-73`.

- **Code-judo alternative:** Delete the bespoke two-key dict. Load via `parse_syntax_color_overrides(settings_payload)` on init and settings reload (same path as `settings_models` merge at 490–498), or add `syntax_overrides_from_snapshot(snapshot) -> dict[str, dict[str, str]]` in `syntax_color_preferences.py` and call it from one place.
- **Suggested remediation:** Fix loader in R2 `MainWindow` extraction PR or a focused hard-cutover PR before R3 stylesheet work. Reload path at ~1803 must stay in sync.
- **Tests that would prove fix:** Unit test: build snapshot with distinct HC override hex values → `_load_syntax_color_overrides` / `_resolve_theme_tokens` in HC Light and HC Dark modes → assert `apply_syntax_token_overrides` output differs from base. Regression belongs in `tests/unit/shell/` (not settings-only tests — those already cover `parse_syntax_color_overrides` HC scopes).
- **Four-theme impact:** **HC Light and HC Dark** — user-customized syntax colors in Settings are ignored at runtime; chrome may still theme via `tokens_from_palette`, but editor/shell syntax override contract is wrong on half the supported modes. Light/Dark unaffected for persisted overrides.
- **Handoff overlap:** R2 (settings reload on `MainWindow`), R3 (`TN-SHELL-SETTINGS` owns dialog persistence — already correct)

---

### TN-SHELL-MW-03-2 — Theme orchestration is a MainWindow mega-sequence

- **Persona:** TN-SHELL-MW-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1214-1265` — `_apply_theme_styles` sequentially: resolve tokens, tab icons, `setStyleSheet`, every open editor, markdown panes, console, explorer theme, run log, search sidebar (partial token fields), activity bar icon triple, test explorer, outline panel. Re-entrancy guard `_is_applying_theme_styles` is correct but confirms this is a fragile orchestration hub. `app/shell/main_window.py:1283-1301` — `gsettings` subprocess for system dark preference lives on `MainWindow`. `current_theme_tokens` / `_resolve_theme_tokens` are the public seam used by `ShellHelpController`, `editor_tab_factory`, and dialogs.

- **Code-judo alternative:** Extract **`ShellThemeWorkflow`** (or `ThemeApplyWorkflow`) per R2: owns `_resolve_theme_tokens`, `_apply_theme_styles`, `_apply_explorer_theme` (icon refresh only), `_system_prefers_dark_theme`, `_handle_set_theme`, `_sync_theme_menu_check_state`, `_persist_theme_mode`, `_load_theme_mode`, `_load_ui_font_weight`, `_load_syntax_color_overrides`. `MainWindow` keeps `current_theme_tokens()` as a one-line forward **only if** required by existing controllers — prefer injecting `Callable[[], ShellThemeTokens]` at construction and deleting duplicate `_current_theme_tokens` elsewhere (see MW-16 slice).
- **Suggested remediation:** R2 wave-4 extraction; wire menu actions directly to workflow methods; pass narrow collaborators (settings service, widget registries) not `self` whole window.
- **Tests that would prove fix:** Characterization test that theme mode change invokes the same child `apply_theme` set (mock widgets); existing `test_main_window_theme_preference_cache.py` moves to workflow module.
- **Four-theme impact:** All four modes flow through this path; HC correctness depends on TN-SHELL-MW-03-1 fix inside the extracted workflow.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-03-3 — `_apply_explorer_theme` repopulates the full project tree on every theme apply

- **Persona:** TN-SHELL-MW-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1267-1281`:

```python
def _apply_explorer_theme(self, tokens: ShellThemeTokens) -> None:
    self._tree_file_icon = file_icon(tokens.icon_primary)
    ...
    if self._loaded_project is not None:
        self._populate_project_tree(self._loaded_project, preserve_state=True)
```

  Called from `_apply_theme_styles` on every theme switch and settings reload (~1818). `docs/ARCHITECTURE.md` §21.3 gates theme-switch editor cost; full tree rebuild is unrelated to token maps and scales with project size.

- **Code-judo alternative:** Icon refresh via `QTreeWidgetItem.setIcon` walk or a `ProjectTreeWidget.refresh_icons(tokens)` method without `_populate_project_tree`. Keep repopulate for structural tree changes only.
- **Suggested remediation:** Part of `ShellThemeWorkflow` / explorer panel R3 split; coordinate with `TN-SHELL-MW-11` tree display critic.
- **Tests that would prove fix:** Unit test with stub tree: `apply_theme` called → `setIcon` or refresh helper invoked, `_populate_project_tree` not called; optional integration timing guard if performance suite is extended.
- **Four-theme impact:** Switching among Light/Dark/HC Light/HC Dark on large projects may cause visible flicker/lag; HC users switching for accessibility hit the same path.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-MW-03-4 — Outline layout state is seven more MainWindow methods

- **Persona:** TN-SHELL-MW-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1118-1165` — `_apply_outline_layout_state`, `_apply_explorer_splitter_handle_state`, four signal handlers, `_handle_outline_hide_requested`. State fields `self._outline_collapsed`, `_outline_follow_cursor`, `_outline_sort_mode` pair with `layout_persistence.py` but logic stays on `MainWindow`. Wiring in `app/shell/main_window_panels.py:164-174`.

- **Code-judo alternative:** Move to **`ExplorerOutlineLayoutController`** or extend layout persistence module with an object that owns apply + signal handlers + persist hooks. Menu/splitter reset in `_handle_reset_layout_action` (1112–1115) calls the same apply entry point — controller absorbs that too. Satisfies handoff rule: **method count on MainWindow must go down**; no new one-line delegators.
- **Suggested remediation:** R2 extraction before R3 `outline_panel.py` split (`TN-SHELL-OUTLINE`); panel keeps UI, controller owns MainWindow-adjacent state sync.
- **Tests that would prove fix:** Existing layout persistence tests + new test: collapsed → `setHandleWidth(0)` and handle disabled; follow-cursor toggle persists and triggers refresh when enabled.
- **Four-theme impact:** Low for outline chrome (panel uses `apply_theme_tokens` at 1262–1263); splitter handle visibility is theme-agnostic.
- **Handoff overlap:** R2, R3 (`TN-SHELL-OUTLINE`)

---

### TN-SHELL-MW-03-5 — Settings loaders in slice repeat `load_global` and include a stranded import-policy loader

- **Persona:** TN-SHELL-MW-03
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window.py:1167-1173` — `_load_import_update_policy` sits between outline handlers and theme resolution (wrong neighborhood). `1303-1331` — `_load_theme_mode`, `_load_ui_font_weight`, `_load_shortcut_overrides`, `_load_syntax_color_overrides`, `_load_lint_rule_overrides`, `_load_selected_linter` each call `self._settings_service.load_global()` or `_load_effective_editor_settings_snapshot()` independently.

- **Code-judo alternative:** Single `MainWindowSettingsSnapshot` (or reuse `parse_editor_settings_snapshot` once per reload) passed to theme workflow and settings-apply path; move import policy loader next to other import/update merge helpers in `settings_models` or an existing settings workflow.
- **Suggested remediation:** R2 thin-pass cleanup per handoff §R2 item 4 (settings getters); can land with theme workflow extraction.
- **Tests that would prove fix:** Refactor-safe if existing `test_settings_models` and settings-apply characterization tests pass; optional assert one `load_global` per settings dialog OK.
- **Four-theme impact:** None directly; reduces risk of inconsistent snapshot reads when theme + syntax overrides reload together.
- **Handoff overlap:** R2

---

### TN-SHELL-MW-03-6 — Inconsistent child theme APIs (`apply_theme` vs `apply_theme_tokens` vs field scalars)

- **Persona:** TN-SHELL-MW-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/main_window.py:1229-1263` — editors/markdown/console use `apply_theme(tokens)`; search sidebar uses four scalar fields; outline uses `apply_theme_tokens(tokens)` with `# type: ignore` on parameter in `outline_panel.py:911`.

- **Code-judo alternative:** Standardize on `apply_theme(tokens: ShellThemeTokens)` at panel boundaries (search sidebar already has token fields on `ShellThemeTokens`). Reduces `_apply_theme_styles` branch surface when workflow extracts.
- **Suggested remediation:** R3 panel splits; align with `TN-SHELL-OUTLINE` and search sidebar critic.
- **Tests that would prove fix:** Extend `test_search_sidebar_widget.py::test_apply_theme_tokens` to full-token path.
- **Four-theme impact:** Indirect — fewer hand-picked fields means HC token additions (e.g. `focus_border_width`) propagate automatically.
- **Handoff overlap:** R3

---

### TN-SHELL-MW-03-7 — Outline symbol kind colors are binary light/dark, not HC-aware

- **Persona:** TN-SHELL-MW-03
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/outline_panel.py:74-95` — `_KIND_COLORS_DARK` / `_KIND_COLORS_LIGHT` only; `apply_theme_tokens` sets `_is_dark` from `tokens.is_dark` (`911-916`), not `tokens.is_high_contrast`. HC modes therefore reuse standard light/dark kind palettes.

- **Code-judo alternative:** Drive kind colors from semantic tokens or a small HC palette table in `theme_tokens.py` when `is_high_contrast` (AAA contrast targets per workspace UI rule). Defer to `TN-SHELL-OUTLINE` R3 split.
- **Suggested remediation:** R3 after panel module split; manual four-theme acceptance for outline icons in HC modes.
- **Tests that would prove fix:** Optional snapshot/visual acceptance; unit test that HC tokens select distinct kind color map when introduced.
- **Four-theme impact:** **HC Light / HC Dark** — symbol glyphs may be lower contrast than chrome text until tuned; not a functional break like TN-SHELL-MW-03-1.
- **Handoff overlap:** R3 (`TN-SHELL-OUTLINE`)

---

## Cross-slice notes (not separate findings)

- Duplicate accessor `_current_theme_tokens` at line 3425 mirrors `_resolve_theme_tokens` — belongs to a later slice / R2 dedup when theme workflow lands.
- `ARCHITECTURE.md` §11.1 still says "syntax-color customization overrides (light/dark token maps)" — documentation drift vs four-theme product; fix in R0 doc closeout, not this slice.

---

## Approval bar (this slice)

| Criterion | Status |
|-----------|--------|
| No structural regression | **Fail** — HC syntax override gap |
| Code-judo opportunity addressed | **Fail** — theme + outline orchestration still on `MainWindow` |
| File-size discipline | **Fail** (pre-existing) — 5.5k LOC file; slice adds orchestration, not decomposition |
| Four-theme contract | **Fail** on HC syntax overrides; chrome path OK via `tokens_from_palette` |
| Canonical helpers | **Fail** — incomplete syntax override load vs `parse_syntax_color_overrides` |

**Presumptive blockers for merge of any future fix PR touching this slice:** TN-SHELL-MW-03-1, TN-SHELL-MW-03-2 (or equivalent workflow extraction plan), TN-SHELL-MW-03-3 if theme perf flicker is observed on ChoreBoy projects.
