# TN-SHELL2-STYLES — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-STYLES  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**HEAD reviewed:** `430c56796089a8d25b082c44e1afa78e9a14d4ac` (delta vs baseline: `theme_tokens.py` import path `app.editors.syntax_engine` → `app.syntax.palette` only; no other style-slice file changes)  
**Scope:** `app/shell/style_sheet.py` (105 LOC), `app/shell/style_sheet_sections.py` (89 LOC), `app/shell/style_sheet_sections_*.py` (8 modules, 3,402 LOC combined), `app/shell/shell_theme_workflow.py` (259 LOC), `app/shell/theme_tokens.py` (339 LOC), `app/shell/syntax_color_preferences.py` (98 LOC). Cross-read: `app/shell/shell_composition.py` (`MainWindowShellThemeHost`), `app/shell/main_window_composition.py`, `tests/unit/shell/test_shell_theme_workflow.py`.

---

## Executive verdict

**Not thermo-clean — REJECT.** Wave 1’s stylesheet monolith and MainWindow theme fan-out were **meaningfully decomposed**: `build_shell_style_sheet` is a 105-line orchestrator over eight focused section modules (max 665 LOC), `ShellThemeWorkflow` is **wired** and owns token resolution plus explorer icon refresh, and **CC-04 is CLOSED** (four-scope syntax overrides load and resolve). Residual debt blocks approval: **CC-09 stays PARTIAL** because ~90 lines of surface-applier orchestration (deferred editor rehighlight chain, markdown/console/search/menu callbacks) remain in `MainWindowShellThemeHost._build_child_callbacks` instead of the theme workflow layer; **CC-23 stays PARTIAL** because primary-button hover/pressed colors across workspace/settings/dialogs use **binary `tokens.is_dark` literals** (`#4D7AFF` / `#2952CC`) that bypass HC accent tokens (`#7CB7FF`, `#0000C0`). No `build_shell_style_sheet` / section QSS contract tests exist beyond workflow callback smoke. No file in this slice crosses 1k LOC; the dominant smell is **relocated orchestration** and **four-theme QSS drift**, not file sprawl.

---

### TN-SHELL2-STYLES-1 — Wave 1 stylesheet monolith successfully split into token-driven section modules

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL (Wave 1 remediation landed)
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** `app/shell/style_sheet.py:48-74` — `build_shell_style_sheet` concatenates 22 `shell_section_*` builders; `app/shell/style_sheet_sections.py:8-53` re-exports from eight area modules. Metric sweep: largest child `style_sheet_sections_workspace.py` 665 LOC; orchestrator 105 LOC. Wave 1 `main_window.py` carried 50+ line inline QSS fan-out (`MW-03`); that path is gone.
- **Code-judo alternative:** **Keep** — this is the target architecture. Future QSS work adds sections or extends existing builders; do not re-inline on `MainWindow`.
- **Suggested remediation:** None for structure; use as template for ICON/diff decomposition.
- **Tests that would prove fix:** N/A (structure already correct).
- **Handoff overlap:** R3, CC-09 (outline/theme extraction prerequisite met)

---

### TN-SHELL2-STYLES-2 — CC-04 CLOSED: four-scope syntax overrides load and resolve at runtime

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL (Wave 1 bugfix closed; re-validated)
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** `app/shell/syntax_color_preferences.py:64-76` — `parse_syntax_color_overrides` iterates `SYNTAX_THEMES` (light, dark, HC light, HC dark). `app/shell/shell_theme_workflow.py:161-174` — `resolve_theme_tokens` selects `UI_SYNTAX_COLORS_HIGH_CONTRAST_*_KEY` when `base_tokens.is_high_contrast`, else light/dark keys; applies via `apply_syntax_token_overrides`. `tests/unit/shell/test_shell_theme_workflow.py:96-106`, `154-169` — HC light override round-trips to `tokens.syntax_keyword == "#000080"`. Wave 1 failure (`_load_syntax_color_overrides` light/dark only) is absent.
- **Code-judo alternative:** N/A — contract is direct and test-backed.
- **Suggested remediation:** Keep closed; extend tests only if settings round-trip regressions appear.
- **Tests that would prove fix:** Existing `test_load_syntax_color_overrides_includes_high_contrast_scopes` + `test_applies_high_contrast_syntax_overrides`.
- **Handoff overlap:** CC-04, R2

---

### TN-SHELL2-STYLES-3 — CC-09 PARTIAL: `ShellThemeWorkflow` wired but surface appliers live in composition host

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_composition.py:474`, `542` — `build_shell_theme_workflow(window)` + startup `apply_theme_styles()`. `app/shell/shell_composition.py:172-173` — `MainWindowRunLaunchHost.apply_theme_styles` delegates to workflow. Contrast: `app/shell/shell_composition.py:472-563` — `MainWindowShellThemeHost._build_child_callbacks` defines 10 nested closures (editor defer/rehighlight `QTimer` chain at `475-495`, markdown registry, console, run log, search sidebar token push, activity bar icons, menu icons, test explorer, outline, app tooltip). `ShellThemeWorkflow.apply_theme_styles` (`176-211`) only sequences callbacks; it does not own surface logic.
- **Code-judo alternative:** Extract **`ShellThemeSurfaceAppliers`** (or methods on `ShellThemeWorkflow`) — one function per surface with explicit widget refs; `MainWindowShellThemeHost` exposes properties only. Editor defer policy moves to editors layer (`TN-SHELL2-COMP-7`).
- **Suggested remediation:** Co-locate appliers with `shell_theme_workflow.py`; shrink host to token/property accessor; hard cutover imports.
- **Tests that would prove fix:** Extend `test_shell_theme_workflow.py` with fake applier module; composition test asserts host has no nested `def apply_*` beyond one-line delegates.
- **Handoff overlap:** CC-09, R2, TN-SHELL2-COMP-7, TN-SHELL2-COMP-8

---

### TN-SHELL2-STYLES-4 — CC-09 improvement: explorer tree repopulate removed from theme pass

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL (Wave 1 `MW-03-3` debt reduced)
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** `app/shell/shell_theme_workflow.py:215-235` — `apply_explorer_theme` updates sink icons and toolbar buttons only; **no** `populate_project_tree` call. Wave 1 flagged full `_populate_project_tree` on every theme switch. `tests/unit/shell/test_shell_theme_workflow.py:255-285` — `populate_project_tree` lambda never invoked when `loaded_project` is set.
- **Code-judo alternative:** Delete stale `ExplorerThemeHost.populate_project_tree` field (see TN-SHELL2-STYLES-10) to match behavior.
- **Suggested remediation:** Remove dead field in hard-cutover cleanup PR.
- **Tests that would prove fix:** Existing `test_updates_sink_and_buttons_without_tree_repopulate`.
- **Handoff overlap:** CC-09, R2

---

### TN-SHELL2-STYLES-5 — CC-23 PARTIAL: QSS primary-button hover/pressed uses binary `is_dark` literals, not four-theme tokens

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/style_sheet_sections_dialogs.py:8-13` — `_accent_hover` / `_accent_pressed` return `#4D7AFF` / `#3D6AEE` when `tokens.is_dark` else `#2952CC` / `#1F3FA6`; **no** `tokens.is_high_contrast` branch. HC tokens use distinct accents (`app/shell/theme_tokens.py:205`, `245` — `#7CB7FF`, `#0000C0`) but hover never derives from `tokens.accent`. Same pattern inlined in `style_sheet_sections_workspace.py:241-257`, `style_sheet_sections_settings.py:75`, `style_sheet_sections_dialogs.py:318-410`. Architecture gate §6 requires `ShellThemeTokens` only; these literals are a parallel palette keyed on dark/light binary.
- **Code-judo alternative:** Add `accent_hover` / `accent_pressed` (or `button_on_accent_fg`) fields to `ShellThemeTokens` populated in `tokens_from_palette` / `TOOLBAR_PRESETS`; section builders read tokens only — **delete all `is_dark` ternaries** in QSS modules.
- **Suggested remediation:** Token-layer hover derivation in one PR; grep-guard `is_dark` in `style_sheet_sections*.py` afterward.
- **Tests that would prove fix:** Parametrized four-theme test: `build_shell_style_sheet(tokens)` contains `tokens.accent` and token-derived hover, never hardcoded `#4D7AFF` for HC modes.
- **Handoff overlap:** CC-23, R3, architecture gate §6

---

### TN-SHELL2-STYLES-6 — Duplicated accent/destructive color helpers across section modules

- **Persona:** TN-SHELL2-STYLES
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/style_sheet_sections_dialogs.py:8-17` — `_accent_hover`, `_accent_pressed`, `_destructive_color`. `style_sheet_sections_run_dialogs.py:28` — inline `tokens.diag_error_color or ("#FF6B6B" if tokens.is_dark else "#E03131")`. `style_sheet_sections_workspace.py:241-257` — copy-pasted `#4D7AFF` / `#2952CC` ternaries without importing dialog helpers. `style_sheet_sections_settings.py:75`, `383` — same accent pattern plus separate error-surface ternary. `style_sheet_sections_chrome.py:38-56` — `_toolbar_accent_button_qss` is the **correct** pattern (caller passes resolved colors) but primary pushbuttons do not use it.
- **Code-judo alternative:** Single `app/shell/style_sheet_color_helpers.py` (or token fields per STYLES-5) consumed by all sections; primary buttons reuse `_toolbar_accent_button_qss` with token-derived bg/hover/pressed/fg.
- **Suggested remediation:** Collapse helpers in same PR as STYLES-5 token fields; delete inline duplicates.
- **Tests that would prove fix:** Import-boundary test: only one module defines accent hover literals.
- **Handoff overlap:** CC-23, R3

---

### TN-SHELL2-STYLES-7 — `ShellThemeTokens` 84-field dataclass is a token god-object

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/theme_tokens.py:54-139` — 84 fields on one frozen dataclass (chrome, toolbar, syntax, popup, debug, search, icons). `tokens_from_palette` (`163-319`) repeats three near-complete constructor blocks for HC dark, HC light, and light modes plus `_shell_theme_tokens_dark` for standard dark. `apply_syntax_token_overrides` maps 28 syntax keys via `_SYNTAX_OVERRIDE_FIELD_MAP`.
- **Code-judo alternative:** Nested frozen dataclasses — `ChromeTokens`, `ToolbarTokens`, `SyntaxTokens`, `DebugTokens` — composed into `ShellThemeTokens`; `tokens_from_palette` builds children from preset tables once. Section builders take `tokens.chrome.border` etc., shrinking parameter surface per module.
- **Suggested remediation:** Defer until STYLES-5/6 hover token work; split syntax fields first (highest field count) without breaking `replace()` call sites.
- **Tests that would prove fix:** Existing `test_shell_theme_workflow` token assertions stay green; pyright clean on nested access.
- **Handoff overlap:** CC-23, R3

---

### TN-SHELL2-STYLES-8 — No QSS contract tests for `build_shell_style_sheet` or section coverage

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL (manifest P5: high gap — workflow wiring vs module-only tests)
- **Severity:** STRUCTURAL
- **Evidence:** `rg 'build_shell_style_sheet|style_sheet_sections' tests/` → **no matches**. `tests/unit/shell/test_shell_theme_workflow.py` records callback invocation and tooltip token presence (`235-250`) but never asserts shell QSS contains object names (`shell.debug.threadsTree`, `shell.testExplorer.debugFailedBtn`) or four-theme accent strings. Wave 1 DEBUG/TEST-UI gaps were stylesheet omissions; fixes in `style_sheet_sections_panels.py` are unguarded by pytest.
- **Code-judo alternative:** Thin `test_style_sheet_contracts.py`: parametrized four `tokens_from_palette` fixtures → `build_shell_style_sheet` must include critical object-name selectors and `tokens.panel_bg`; avoid full QSS snapshot anti-pattern — assert **presence** of token values and selectors only.
- **Suggested remediation:** Add after STYLES-5 token hover fix so assertions target stable token fields.
- **Tests that would prove fix:** New unit module under `tests/unit/shell/`; four-theme parametrization.
- **Handoff overlap:** CC-23, CC-24 (test placement), P5 test map

---

### TN-SHELL2-STYLES-9 — CC-23 partial closure: `threadsTree` and `debugFailedBtn` now in panels QSS

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL (Wave 1 gaps closed in R3 stylesheet work)
- **Severity:** NICE-TO-HAVE (keeper)
- **Evidence:** Wave 1 `TN-SHELL-DEBUG` / `TN-SHELL-TEST-UI` documented missing selectors. `app/shell/style_sheet_sections_panels.py:270-297` — `QTreeWidget#shell\\.debug\\.threadsTree` grouped with stack/variables/watch/breakpoints trees (hover/selected). `378-404` — `QToolButton#shell\\.testExplorer\\.debugFailedBtn` grouped with refresh/run buttons. Object names set at `debug_panel_trees.py:161`, `test_explorer_panel.py:152`.
- **Code-judo alternative:** N/A — correct fix path; needs test guard (STYLES-8).
- **Suggested remediation:** Add selector-presence contract test; manual four-theme QA for debug/test panels.
- **Tests that would prove fix:** `assert "shell\\.debug\\.threadsTree" in build_shell_style_sheet(hc_tokens)`.
- **Handoff overlap:** CC-23, R3

---

### TN-SHELL2-STYLES-10 — Stale `ExplorerThemeHost.populate_project_tree` and `Any` host escape hatches

- **Persona:** TN-SHELL2-STYLES
- **Status:** NEW
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/shell_theme_workflow.py:84` — `populate_project_tree: Callable[[], None] | None = None` on `ExplorerThemeHost` but `apply_explorer_theme` never reads it (behavior removed per STYLES-4). `105-110` — `ShellThemeWorkflow.__init__(host: ShellThemeWorkflowHost | Any)` and `host` property returns `Any` despite `ShellThemeWorkflowHost` dataclass at `88-99`. `ExplorerThemeSink` uses `Any` for icon fields (`67-72`).
- **Code-judo alternative:** Hard-delete `populate_project_tree`; tighten workflow constructor to `ShellThemeWorkflowHost` only; type sink icons as `QIcon | None` with PySide import guard.
- **Suggested remediation:** Small hard-cutover PR; no behavior change.
- **Tests that would prove fix:** pyright on `shell_theme_workflow.py`; existing explorer tests unchanged.
- **Handoff overlap:** CC-09, architecture gate §3

---

### TN-SHELL2-STYLES-11 — `apply_explorer_theme` rebuilds token-agnostic `file_type_icon_map()` on every theme pass

- **Persona:** TN-SHELL2-STYLES
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/shell_theme_workflow.py:220-222` — `sink.tree_file_icon_map = file_type_icon_map()` and `filename_icon_map()` with **no** `tokens` argument; only generic `file_icon(tokens.icon_primary)` and folder icons receive theme colors. File-type badges use fixed brand colors inside `file_type_icons.py` (intentional for language recognition) but maps are rebuilt every `apply_theme_styles` call even when theme mode unchanged.
- **Code-judo alternative:** Cache file-type maps at project load / extension change only; theme pass updates token-colored icons (file, folder, toolbar) only. Or pass `tokens.icon_primary` into a token-aware map builder.
- **Suggested remediation:** Coordinate with TN-SHELL2-ICON slice; separate “brand badge” from “chrome tint” caches.
- **Tests that would prove fix:** Theme apply twice → `file_type_icon_map` factory call count 0 on second pass (mock).
- **Handoff overlap:** CC-09, CC-23, TN-SHELL2-ICON-3

---

## CC theme re-validation

| CC theme | Wave 1 status | Wave 2 (this slice) | Notes |
|----------|---------------|---------------------|-------|
| **CC-04** | OPEN → remediated | **CLOSED** | Four-scope `parse_syntax_color_overrides`; HC key selection in `resolve_theme_tokens`; unit tests at `test_shell_theme_workflow.py:96-169` | TN-SHELL2-STYLES-2 |
| **CC-09** | PARTIAL — theme on MainWindow + tree rebuild | **PARTIAL** — `ShellThemeWorkflow` **wired** (`main_window_composition.py:474`, `542`); tree repopulate **removed**; fan-out + deferred editor chain still in `MainWindowShellThemeHost` | TN-SHELL2-STYLES-3, -4, -11; TN-SHELL2-COMP-7, -8 |
| **CC-23** | PARTIAL — QSS omissions, inline styles, binary palettes | **PARTIAL** — `threadsTree` / `debugFailedBtn` QSS **closed**; primary hover still `is_dark` literals; hardcoded `#FFFFFF` on accent buttons (11 occurrences across section files); inline panel styles remain outside this slice (TEST-UI) | TN-SHELL2-STYLES-5, -6, -9, -8 |

No **REGRESSION** on CC-04, CC-09, or CC-23 relative to Wave 1 remediation outcomes. CC-04 promoted to **CLOSED**. CC-09 and CC-23 improved but fail thermo-clean bar.

---

## Approval bar

| Gate | Result |
|------|--------|
| No style-slice file >1k LOC | **PASS** (max `style_sheet_sections_workspace.py` 665) |
| CC-04 HC syntax overrides | **PASS** — CLOSED |
| CC-09 `ShellThemeWorkflow` wired | **PASS** (behavior) |
| CC-09 orchestration fully extracted | **FAIL** — PARTIAL |
| CC-23 four-theme QSS via `ShellThemeTokens` only | **FAIL** — PARTIAL (`is_dark` accent literals) |
| QSS / stylesheet contract tests | **FAIL** — none |
| Obvious code-judo path visible | **YES** — token hover fields + applier module + contract tests |
| Unwired theme workflow | **PASS** — not present |

**Verdict: REJECT.** Wave 1 structural wins (stylesheet split, workflow extraction, CC-04) are real and should not be reverted, but ship no new QSS surface area until TN-SHELL2-STYLES-5/6 tokenize accent hover/pressed, TN-SHELL2-STYLES-3 relocates appliers out of `shell_composition.py`, and TN-SHELL2-STYLES-8 adds selector-presence contract tests. Parallel: TN-SHELL2-STYLES-10 dead-field cleanup; TN-SHELL2-STYLES-11 explorer map cache policy with ICON slice.

---

## Suggested fix wave (STYLES slice only)

| Step | Findings | Outcome |
|------|----------|---------|
| 1 | STYLES-5, STYLES-6 | `accent_hover` / `accent_pressed` / `button_on_accent_fg` on `ShellThemeTokens`; delete `is_dark` literals in section builders |
| 2 | STYLES-3, STYLES-10 | `ShellThemeSurfaceAppliers` module; delete `populate_project_tree`; tighten host typing |
| 3 | STYLES-8, STYLES-9 | Four-theme QSS contract tests for critical object names + token embedding |
| 4 | STYLES-7, STYLES-11 | Optional: nested token dataclasses; explorer icon map cache policy |
