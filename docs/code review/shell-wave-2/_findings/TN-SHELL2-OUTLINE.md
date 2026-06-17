# TN-SHELL2-OUTLINE — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-OUTLINE  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**HEAD reviewed:** `430c56796089a8d25b082c44e1afa78e9a14d4ac` (no delta on outline slice files vs baseline)  
**Scope:** `app/shell/outline/` package (1,158 LOC across six modules), `app/shell/symbol_navigation_workflow.py` (380 LOC). Cross-read: `app/shell/editor_tab_outline_workflow.py` (199 LOC), `app/shell/shell_composition.py` (`apply_outline_theme`), `app/shell/shell_theme_workflow.py`, `app/shell/style_sheet_sections_panels.py` (`shell_section_outline_panel`), `app/intelligence/outline_service.py`, `tests/unit/shell/test_outline_panel.py` (434 LOC / 26 tests), `tests/unit/shell/test_semantic_navigation_workflow.py` (270 LOC / 7 tests).

---

## Executive verdict

**REJECT — R3 split landed, but outline slice is not thermo-clean.** Shell Wave 1’s 1,155-line `outline_panel.py` monolith is **gone**: the `app/shell/outline/` package splits header, filter, tree, icons, and orchestrator with **no module ≥700 LOC** (`outline_panel.py` 533, `outline_header.py` 304). Wave 1 collapse regressions are **closed** — header `set_collapsed` now drives the `collapsed` dynamic property on all toggle paths, and panel collapse layout funnels through `_apply_collapsed_layout`. **CC-21** for OUTLINE moves from stalled monolith to **PARTIAL (improved)** — hotspot LOC targets met, but package total (~1,158 LOC) is unchanged and orchestrator logic (sort, filter, render) still concentrates in `outline_panel.py`. **CC-09** stays **PARTIAL** — outline theme is wired through `ShellThemeWorkflow` (`apply_outline_theme` callback), but every theme pass still **clears and rebuilds the full symbol tree** via `_render_tree`. **CC-23** stays **PARTIAL** — kind colors remain binary `is_dark` palettes with no HC-specific tuning; chevron default and constant-glyph white are hardcoded hex. Residual structural debt: duplicated sort-mode ownership, `OutlineSymbol` tree cloning on every sort/theme render, untyped `apply_theme_tokens`, `clear_icon_caches` not wired on theme/shutdown, and `symbol_navigation_workflow.py` as a 380-line nested-callback repetition block. Test coverage for the panel is strong (26 tests); symbol navigation relies on indirect mocks.

---

## CC re-validation summary

| CC | Wave 1 theme | Status @ HEAD | Evidence |
|----|--------------|---------------|----------|
| **CC-09** | Theme orchestration + full tree rebuild on theme pass | **PARTIAL (improved wiring, same rebuild cost)** | Outline no longer styled from MainWindow fan-out — `shell_composition.py:542-544` registers `apply_outline_theme` → `OutlinePanel.apply_theme_tokens`. `shell_theme_workflow.py:210-211` invokes callback on every theme apply. `outline_panel.py:308-320` still calls `_render_tree(preserve_expansion=True)` when symbols exist — full tree clear + rebuild + icon repaint on each theme switch. |
| **CC-21** | R3 hotspot modules oversized (OUTLINE was 1,155 LOC monolith) | **PARTIAL (improved — monolith eliminated)** | Wave 1: single file 1,155 LOC (15% past 1k). Wave 2 @ `fccb611`: six modules, max 533 LOC; all under 700 LOC gate. Package total ~1,158 LOC — complexity **relocated**, not deleted. `outline_panel.py` still 533 LOC orchestrator (above 400 LOC R3 target). `symbol_navigation_workflow.py` 380 LOC is a separate untyped hotspot. |
| **CC-23** | Four-theme gaps (HC kind colors, inline styles) | **PARTIAL (unchanged)** | `outline_icons.py:19-46` — `_KIND_COLORS_DARK` / `_KIND_COLORS_LIGHT` only; `kind_color_for(kind, is_dark=...)` at `:44-46`. `outline_panel.py:312-313,393` — `_is_dark` from `tokens.is_dark`, no `is_high_contrast` branch. `outline_tree.py:77` — default chevron `#808080`. `outline_icons.py:72-73` — constant glyph hardcoded `#FFFFFF`. QSS section `shell_section_outline_panel` is token-driven — gap is icon/kind palette, not panel chrome QSS. |

No **REGRESSION** detected on CC-09, CC-21, or CC-23 relative to Wave 1 remediation outcomes for this slice.

---

### TN-SHELL2-OUTLINE-1 — CC-21: R3 split landed; monolith eliminated, orchestrator still overweight

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL (improved from Wave 1 OPEN on 1k boundary)
- **Severity:** STRUCTURAL
- **Evidence:** Wave 1 @ `7d1c89f`: `outline_panel.py` **1,155 LOC** (TN-SHELL-OUTLINE-1). Wave 2 @ `fccb611`: `outline_panel.py` 533, `outline_header.py` 304, `outline_icons.py` 140, `outline_tree.py` 101, `outline_filter.py` 59, `__init__.py` 21 — **zero files ≥700 LOC**, no 1k violation. Package total ~1,158 LOC vs prior single file ~1,155 — net spread, not net shrink (same pattern as TN-SHELL2-SETTINGS handlers relocation).
- **Code-judo alternative:** Extract `outline_render.py` (~150 LOC: `_render_tree`, `_add_symbol`, `_sort_symbols`, `_sort_recursive`) and `outline_filter_logic.py` (~80 LOC: `_apply_filter`, `_filter_visit`) so `outline_panel.py` orchestrator drops below **400 LOC** — the Wave 1 R3 target per module.
- **Suggested remediation:** One follow-up PR: render + filter extraction only; no new outline features until orchestrator < 400 LOC.
- **Tests that would prove fix:** Existing `test_outline_panel.py` (26 tests) stays green; optional LOC gate in CI for `outline_panel.py` < 450.
- **Handoff overlap:** R3, CC-21, architecture gate §2

---

### TN-SHELL2-OUTLINE-2 — CC-09: `apply_theme_tokens` triggers full symbol-tree rebuild on every theme pass

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `outline_panel.py:308-320` — `apply_theme_tokens` updates header/tree chevron colors, then if `self._symbols`: `_render_tree(preserve_expansion=True)` + optional `_apply_filter()`. `_render_tree` (`:359-377`) calls `self._tree.clear()`, rebuilds all items, re-applies icons. Triggered on every `ShellThemeWorkflow.apply_theme_styles` pass via `shell_composition.py:542-544`. Wave 1 CC-09 flagged outline full rebuild on theme; wiring improved (callback seam) but rebuild cost unchanged.
- **Code-judo alternative:** Theme refresh should **repaint icons in place** — iterate `_items_by_qualified_name`, call `item.setIcon(0, kind_icon(...))` with updated `kind_color_for(...)` from fresh tokens; update chevron/header icons only. Reserve `_render_tree` for symbol data changes (parse, sort mode, file switch).
- **Suggested remediation:** Pair with TN-SHELL2-OUTLINE-6 (token-driven kind colors); add perf smoke: theme toggle with 200-symbol file does not call `_tree.clear()`.
- **Tests that would prove fix:** Unit test: populate panel, spy `_tree.clear`, call `apply_theme_tokens` — assert clear count 0; expansion state preserved without rebuild.
- **Handoff overlap:** R2, R3, CC-09, TN-SHELL2-STYLES

---

### TN-SHELL2-OUTLINE-3 — CC-23: symbol kind colors binary light/dark; HC modes share standard palettes

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `outline_icons.py:19-46` — parallel `_KIND_COLORS_DARK` / `_KIND_COLORS_LIGHT` dicts; no HC-specific entries. `outline_panel.py:312-313` — `self._is_dark = bool(getattr(tokens, "is_dark", False))`; `:393` — `kind_color_for(symbol.kind, is_dark=self._is_dark_theme())`. HC Light and Light share light palette; HC Dark and Dark share dark palette. Cross-ref workspace four-theme rule and TN-SHELL2-ICON-6.
- **Code-judo alternative:** Drive kind colors from `ShellThemeTokens` semantic fields (e.g. `syntax_class_color`, `syntax_function_color`) or a four-entry palette keyed by `(is_dark, is_high_contrast)` in `theme_tokens.py`; delete module-level hex dicts.
- **Suggested remediation:** After token fields exist, wire `kind_color_for(tokens, kind)`; manual acceptance in HC Light/Dark for class/function/method glyphs on `#FFFFFF` / `#000000` panel backgrounds.
- **Tests that would prove fix:** Parametrized test with four `ShellThemeTokens` fixtures asserts distinct kind colors where HC requires AAA contrast bump.
- **Handoff overlap:** R3, CC-23, TN-SHELL2-STYLES, architecture gate §6

---

### TN-SHELL2-OUTLINE-4 — Sort mode owned twice; parallel validation and re-render paths persist

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `outline_header.py:53,181-191,260-267` — `_OutlineHeaderBar._sort_mode` validated locally, menu actions update and emit `sort_mode_changed`. `outline_panel.py:123,204-216,486-496` — `OutlinePanel._sort_mode` duplicates validation, `_render_tree`, filter re-apply, and `sort_mode_changed.emit`. `set_sort_mode` and `_handle_sort_changed` are near-mirror implementations differing only in header sync direction. Wave 1 TN-SHELL-OUTLINE-4 — **not fixed** by R3 split (same logic, new files).
- **Code-judo alternative:** Header is **dumb UI** — menu selection emits raw mode string; panel is **sole owner** of `_sort_mode`, validation, re-render, and outward `sort_mode_changed` signal. Header receives `set_sort_mode` for external sync only.
- **Suggested remediation:** Collapse during next outline PR; delete header `_sort_mode` field and duplicate validation in `_handle_sort_action_triggered`.
- **Tests that would prove fix:** Existing sort tests (`test_set_sort_mode_*`) stay green; add test that header menu trigger updates panel sort without header-local state drift.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-OUTLINE-5 — Sort clones entire `OutlineSymbol` tree on every re-render

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `outline_panel.py:327-357` — `_sort_symbols` / `_sort_recursive` rebuild `OutlineSymbol` namedtuples with reordered `children` on every `_render_tree` call. Triggered by `set_sort_mode` (`:212-213`), `_handle_sort_changed` (`:492-493`), `apply_theme_tokens` (`:317-318`), and `set_outline` (`:263`). Domain copies mutated for a **view concern** (display order).
- **Code-judo alternative:** Keep `_symbols` immutable from intelligence layer; sort at **view layer** only — either sort child item insertion order in `_add_symbol` via a sort-key function, or attach sort keys to `QTreeWidgetItem` data roles without cloning `OutlineSymbol`.
- **Suggested remediation:** Refactor `_render_tree` to accept `sort_mode` and sort sibling lists at insert time; delete `_sort_recursive`.
- **Tests that would prove fix:** Sort-mode tests unchanged; assert `panel.symbols()` tuple identity stable across sort toggles (symbols not replaced).
- **Handoff overlap:** R3, CC-09 (theme path also triggers clone)

---

### TN-SHELL2-OUTLINE-6 — `apply_theme_tokens` untyped; diverges from shell `apply_theme` convention

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `outline_panel.py:308` — `def apply_theme_tokens(self, tokens) -> None:  # type: ignore[no-untyped-def]` with bare `tokens` parameter and `getattr(tokens, "is_dark", False)` fallback (`:312-314`). Siblings (editors, console) use `apply_theme(tokens: ShellThemeTokens)`. Search sidebar uses scalar field bundle — outline is the outlier naming + typing pattern from Wave 1 TN-SHELL-OUTLINE-7.
- **Code-judo alternative:** Rename to `apply_theme(self, tokens: ShellThemeTokens) -> None`; read `tokens.is_dark`, `tokens.is_high_contrast`, `tokens.icon_primary`, `tokens.accent` directly; delete `# type: ignore`.
- **Suggested remediation:** Align during CC-23 kind-color token wiring (TN-SHELL2-OUTLINE-3); update `shell_composition.apply_outline_theme` call site only.
- **Tests that would prove fix:** Pyright clean on `outline_panel.py`; unit test with minimal `ShellThemeTokens` fixture asserts chevron + kind icons update.
- **Handoff overlap:** CC-23, TN-SHELL2-STYLES

---

### TN-SHELL2-OUTLINE-7 — `clear_icon_caches` exported but not wired on theme apply or editor shutdown

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `outline_icons.py:137-140` — `clear_icon_caches()` clears `_OUTLINE_ICON_CACHE` and `_CHEVRON_ICON_CACHE`. Exported from `outline/__init__.py:3,20`. **Not called** from `shell_theme_workflow.py` theme preamble or `run_editor.py:_clear_qt_module_caches` (`:42-50` clears file_type, problems, test_explorer only). Each theme apply creates new `(kind, color)` cache keys via `_render_tree` icon rebuild (TN-SHELL2-OUTLINE-2) while old pixmaps remain referenced.
- **Code-judo alternative:** Call `outline.clear_icon_caches()` in a single shell theme cache-clear hook alongside `file_type_icons`, `test_explorer_icons`, `problems_panel` — or eliminate full rebuild (TN-SHELL2-OUTLINE-2) so cache churn stops.
- **Suggested remediation:** Wire into `run_editor._clear_qt_module_caches` immediately; add theme apply preamble when TN-SHELL2-ICON-3 lands for `icon_provider`.
- **Tests that would prove fix:** Populate cache with two colors; call clear hook; assert dict lengths 0.
- **Handoff overlap:** CC-09, TN-SHELL2-ICON-3

---

### TN-SHELL2-OUTLINE-8 — Wave 1 collapse property bug closed; layout path unified

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** NEW (positive — Wave 1 TN-SHELL-OUTLINE-2/3 closed)
- **Severity:** NICE-TO-HAVE
- **Evidence:** Wave 1: `mousePressEvent` / `_handle_chevron_clicked` bypassed `setProperty("collapsed")` — QSS `header[collapsed="true"]` missed user collapse (`TN-SHELL-OUTLINE-2`). Wave 2: `outline_header.py:151-161` — `set_collapsed` sets `self.setProperty("collapsed", bool(collapsed))` and repolishes; `_toggle_collapsed` (`:253-255`) and chevron handler (`:257-258`) route through it. `outline_panel.py:171-184` — single `_apply_collapsed_layout` used by `set_collapsed` and `_handle_header_toggled`. Tests: `test_collapsed_header_property_set_for_styling`, `test_header_chevron_click_toggles_collapsed`.
- **Code-judo alternative:** Keep — this is the correct pattern. Extend chevron-click test to assert `header.property("collapsed")` if regression guard desired.
- **Suggested remediation:** None — preserve as regression baseline for R3 split quality proof.
- **Tests that would prove fix:** Already covered by `test_outline_panel.py`.
- **Handoff overlap:** R3 (closed)

---

### TN-SHELL2-OUTLINE-9 — Stranded `_max_height_expanded`; triplicate panel reset paths

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `outline_panel.py:127` — `self._max_height_expanded = self.maximumHeight()` assigned at init, **never read** (Wave 1 TN-SHELL-OUTLINE-9). `clear` (`:268-276`), `set_unsupported_language` (`:278-289`), and empty-symbol branch in `set_outline` (`:256-261`) each repeat tree clear, `_items_by_qualified_name.clear()`, symbol reset, empty-label text, stack widget switch with minor text variations.
- **Code-judo alternative:** Delete `_max_height_expanded`. Extract `_show_empty_state(message: str)` helper for the three reset paths.
- **Suggested remediation:** Low-risk cleanup PR; no behavior change.
- **Tests that would prove fix:** Existing `test_clear_resets_state`, `test_set_unsupported_language_shows_placeholder`, `test_set_outline_with_no_symbols_shows_empty_state` stay green.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-OUTLINE-10 — `symbol_navigation_workflow.py` 380 LOC: repetitive guards and nested callback soup

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `symbol_navigation_workflow.py:22-380` — four action handlers (`handle_go_to_definition_action`, `handle_goto_symbol_in_file_action`, `handle_find_references_action`, `handle_rename_symbol_action`) each repeat: resolve `dialog_parent` → check `loaded_project` → check active tab/editor → extract cursor context → define nested `on_success`/`on_error` → delegate to `intelligence_controller`. **Five** `# type: ignore[no-untyped-def]` on callback parameters (`:43,126,172,292,346`). `_choose_definition_location` uses `getattr` duck-typing on `location` objects (`:136-138`). Positive: uses typed `SemanticNavigationHost` protocol (`:19`) — better than `window: Any`.
- **Code-judo alternative:** Extract `_require_editor_context(action_name) -> EditorContext | None` guard helper and `_dispatch_intelligence(op, ..., on_success, on_error)` wrapper; split rename (plan + apply nested callbacks, `:250-380`) into `symbol_rename_workflow.py` or private module methods.
- **Suggested remediation:** Do not grow this file; next symbol-nav feature requires extraction first. Target ≤250 LOC orchestrator + typed callback aliases from intelligence contracts.
- **Tests that would prove fix:** Expand `test_semantic_navigation_workflow.py` (7 tests, mostly mocked QMessageBox) with host-stub unit tests per handler guard path.
- **Handoff overlap:** CC-07 (host protocol good), CC-21, Intelligence Wave 1 seam

---

### TN-SHELL2-OUTLINE-11 — Panel tests probe private layout internals

- **Persona:** TN-SHELL2-OUTLINE
- **Status:** RESIDUAL
- **Severity:** NICE-TO-HAVE
- **Evidence:** `test_outline_panel.py:151,164,171,216,249` — assertions on `panel._stack_layout`, `panel._stack_container.isHidden()`, `panel._collapsed_header_height()`. Imports private `_OutlineHeaderBar`, `_OutlineTreeWidget` from package (`:13-19`). Wave 2 CC-24 flags private-attr probing shell-wide; outline tests are moderate offenders (5+ private touches) vs good public API coverage elsewhere (26 tests on signals, sort, filter, collapse).
- **Code-judo alternative:** Add public seams: `panel.body_visible()`, `panel.stack_current_widget()`, `panel.collapsed_header_height()` — migrate tests off `_`-prefixed fields.
- **Suggested remediation:** Opportunistic during next outline PR; not blocking if R3 split stability is priority.
- **Tests that would prove fix:** Replace private assertions with public accessors; test count unchanged.
- **Handoff overlap:** CC-24, R6 (test audit)

---

## Positive keepers (do not regress)

- **R3 file split achieved** — no outline module ≥700 LOC; 1k monolith eliminated (TN-SHELL2-OUTLINE-1).
- **Collapse QSS path fixed** — header `collapsed` property on all toggle paths; unified `_apply_collapsed_layout` (TN-SHELL2-OUTLINE-8).
- **Intelligence boundary clean** — `EditorTabOutlineWorkflow` owns parse/cache/async; panel consumes `OutlineSymbol` tuples only; revision-gated delivery via `deliver_revision_gated_editor_result`.
- **Theme callback wired** — `ShellThemeWorkflow` → `apply_outline_theme` → `OutlinePanel.apply_theme_tokens` (CC-09 wiring improved vs MainWindow fan-out).
- **Strong panel characterization** — `test_outline_panel.py` 434 LOC / 26 tests covering hierarchy, expansion, sort, filter, collapse, signals, chevron tree.
- **Stylesheet section token-driven** — `shell_section_outline_panel(tokens)` uses semantic panel tokens; gap is icon palette sync, not QSS authoring.

---

## Gate checklist

| Gate | Status |
|------|--------|
| AD-015 — no new MainWindow outline methods | **PASS** — outline refresh in `EditorTabOutlineWorkflow` |
| 1k-line rule — outline modules | **PASS** — max 533 LOC |
| R3 orchestrator < 400 LOC | **FAIL** — `outline_panel.py` 533 |
| CC-09 theme without full tree rebuild | **FAIL** |
| CC-23 four-theme kind colors | **FAIL** |
| CC-21 OUTLINE hotspot split | **PARTIAL PASS** — split landed; orchestrator still heavy |
| Sort SSOT single owner | **FAIL** |
| Symbol nav workflow bounded | **FAIL** — 380 LOC, growing risk |

---

## Verdict matrix

| CC | Wave 2 status | Primary findings |
|----|---------------|------------------|
| **CC-09** | **PARTIAL** — callback wired; rebuild cost unchanged | TN-SHELL2-OUTLINE-2, -7 |
| **CC-21** | **PARTIAL (improved)** — monolith gone; orchestrator + symbol_nav remain | TN-SHELL2-OUTLINE-1, -4, -5, -10 |
| **CC-23** | **PARTIAL** — binary palettes; hardcoded chevron/constant hex | TN-SHELL2-OUTLINE-3, -6 |

**Verdict: REJECT.** R3 outline split is the **strongest remediation win** in this slice and closes Wave 1 collapse regressions, but thermo-clean requires: (1) theme refresh without `_render_tree` (TN-SHELL2-OUTLINE-2), (2) token-driven four-theme kind colors (TN-SHELL2-OUTLINE-3), (3) sort SSOT + stop cloning `OutlineSymbol` (TN-SHELL2-OUTLINE-4, -5), (4) `outline_panel.py` under 400 LOC (TN-SHELL2-OUTLINE-1). Do not add outline UI features or grow `symbol_navigation_workflow.py` until those land.

---

## Suggested fix wave (outline-only)

| Priority | Findings | Action |
|----------|----------|--------|
| P1 | OUTLINE-2, -3, -6 | In-place icon repaint on theme; token-driven kind colors; rename `apply_theme` |
| P1 | OUTLINE-4, -5 | Sort SSOT in panel; view-layer sort without `OutlineSymbol` clone |
| P2 | OUTLINE-1 | Extract render + filter modules; orchestrator < 400 LOC |
| P2 | OUTLINE-7 | Wire `clear_icon_caches` into shutdown + theme preamble |
| P2 | OUTLINE-10 | Extract symbol-nav guard helper; cap file at ~250 LOC |
| P3 | OUTLINE-9, -11 | Delete dead field; public test seams |

**Handoff:** TN-SHELL2-INTEG (CC supersession), TN-SHELL2-STYLES (token fields for kind colors), TN-SHELL2-ICON-3 (shared cache-clear hook).
