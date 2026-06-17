# TN-SHELL2-ICON — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL2-ICON  
**Date:** 2026-06-17  
**Baseline commit:** `fccb6113577752eed330fd8910f72de598c97ec2`  
**HEAD reviewed:** `430c56796089a8d25b082c44e1afa78e9a14d4ac` (no delta on icon slice files vs baseline)  
**Scope:** `app/shell/icon_provider.py` (1,106 LOC), `app/shell/file_type_icons.py` (523 LOC), `app/shell/menu_icons.py` (231 LOC). Cross-read: `app/shell/outline/outline_icons.py` (140 LOC), `app/shell/test_explorer_icons.py` (253 LOC), `app/shell/toolbar_icons.py`, `app/shell/icons.py`, `app/shell/problems_panel.py`, `app/shell/shell_theme_workflow.py`, `app/shell/main_window_panels.py`, `tests/unit/shell/test_menu_icons.py`, `tests/unit/shell/test_test_explorer_panel.py`.

---

## Executive verdict

**Not thermo-clean — REJECT.** `icon_provider.py` is the **only** `app/` module above 1,000 lines (1,106 LOC) and carries ~92 near-identical `*_icon(color)` SVG string factories with no decomposition plan — a presumptive architecture-gate blocker. Shell Wave 1 R3 partially landed (`outline_icons.py`, `test_explorer_icons.py` extracted from panel monoliths; `menu_icons.py` is a clean dispatcher), but the remediation **consolidated menu SVGs into `icon_provider`**, growing it from ~172 LOC at Wave 1 kickoff to 1,106 at Wave 2 baseline without splitting the new mass. QPainter icon factories remain duplicated across six shell modules with no shared paint primitive. **CC-21** stays **PARTIAL** (hotspot split incomplete; icon pipeline is now the sole 1k violation). **CC-23** stays **PARTIAL** (outline kind colors still binary `is_dark`; explorer chrome wired with hardcoded hex at construction). Test coverage is thin: one indirect menu smoke suite plus private-cache probing in test-explorer panel tests — no `icon_provider` or `file_type_icons` contract tests.

---

### TN-SHELL2-ICON-1 — Sole `app/` file past 1k: `icon_provider.py` at 1,106 LOC

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** BLOCKER
- **Evidence:** Metric sweep @ `fccb611` — `find app -name '*.py' -exec wc -l {} + | awk '$1 >= 1000'` returns only `icon_provider.py` (1,106). Wave 1 kickoff @ `7d1c89f`: same file was **172 LOC**; Wave 1 remediation absorbed menu-bar SVG factories here without subsequent split.
- **Code-judo alternative:** Decompose before any new icon work: `icon_provider_core.py` (~80 LOC: `_render_svg`, caches, `clear_icon_caches`), `context_icons.py` (explorer/tree/context-menu SVGs), `menu_bar_icons.py` (save/settings/run-adjacent menu SVGs from line ~343 onward), keep `file_type_icons.py` as-is. Orchestrator re-exports preserve import paths for one release, then hard cutover.
- **Suggested remediation:** First ICON-wave PR: split only — no new glyphs. Target each child < 400 LOC; parent shim < 100 LOC or delete shim after cutover.
- **Tests that would prove fix:** Existing `test_menu_icons.py` stays green; add import-boundary assertion that no single `app/shell/*icon*.py` module exceeds 700 LOC post-split.
- **Handoff overlap:** R3, CC-21, architecture gate §2 (1k-line rule)

---

### TN-SHELL2-ICON-2 — ~92 copy-paste `*_icon(color)` functions; missing data-driven SVG registry

- **Persona:** TN-SHELL2-ICON
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/icon_provider.py` — 92 `def *_icon` entries (`rg '^def ' icon_provider.py` → 92 matches). Each function is an inline SVG template differing only in path `body` strings and occasional two-color badge params (e.g. `save_as_icon` at `355-367`, `theme_light_icon` at `718-729`). Shared helpers `_menu_icon` / `_cached_context_icon` exist at `33-41` but still require per-icon wrapper functions for every menu action.
- **Code-judo alternative:** Single `IconSpec` dataclass (`name`, `body_template`, `color_slots: tuple[str, ...]`) + `build_icon(spec, *colors)` registry dict keyed by stable names. Menu dispatcher (`menu_icons._ACTION_ICON_BUILDERS`) maps action IDs to registry keys instead of 70+ `icon_provider.*` call sites. Deletes hundreds of lines without changing pixels.
- **Suggested remediation:** Pair with TN-SHELL2-ICON-1 split: registry lives in `menu_bar_icons.py`; context icons stay procedural where shapes are genuinely unique (folder open vs closed).
- **Tests that would prove fix:** Parametrized render smoke: every registry key produces non-null 16×16 pixmap in four theme token fixtures (reuse `test_menu_icons` token builders).
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-ICON-3 — `icon_provider` context cache never cleared; theme churn grows memory

- **Persona:** TN-SHELL2-ICON
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/icon_provider.py:16-41` — module-level `_CONTEXT_ICON_CACHE` grows on every distinct `(name, color)` key. No `clear_icon_caches()` in this module. Contrast: `file_type_icons.clear_icon_caches` (`518-523`), `outline_icons.clear_icon_caches` (`137-140`), `test_explorer_icons.clear_icon_caches` (`182-186`), `problems_panel.clear_icon_caches` (`186`) all expose teardown hooks. `shell_theme_workflow.apply_explorer_theme` (`215-235`) rebuilds icons with new token colors on each theme apply, creating new cache entries while old pixmaps remain referenced.
- **Code-judo alternative:** Add `clear_icon_caches()` to `icon_provider`; call from a single shell theme teardown hook alongside outline/test-explorer/problems clears. Or scope cache lifetime to `ShellThemeWorkflow` instance instead of process-global dict.
- **Suggested remediation:** Wire into theme apply preamble (before rebuilding menu/explorer icons) or app shutdown path used by other panel caches.
- **Tests that would prove fix:** Unit test: call `save_icon` with two colors, assert cache size 2; `clear_icon_caches()` → size 0; re-call returns fresh icons.
- **Handoff overlap:** CC-21, CC-23 (theme refresh correctness)

---

### TN-SHELL2-ICON-4 — Duplicate SVG raster pipelines in `icon_provider` and `file_type_icons`

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/icon_provider.py:19-27` — `_render_svg` / `_icon_from_svg` via `QSvgRenderer` + `QPainter`. `app/shell/file_type_icons.py:26-35` — `_svg_icon` with identical QByteArray → renderer → pixmap → painter flow and same 16×16 default. `icon_provider.file_type_icon_map` (`57-63`) delegates to `build_file_type_icon_map()` but does not reuse `_render_svg`.
- **Code-judo alternative:** One canonical `shell_svg_icons.render_svg(body: str, size: int = 16) -> QIcon` imported by both modules (or `file_type_icons` imports from `icon_provider_core`). Badge/QPainter paths stay in `file_type_icons`; SVG path is single implementation.
- **Suggested remediation:** Extract shared helper in ICON-wave split PR; delete duplicate `_svg_icon` wrapper.
- **Tests that would prove fix:** Single parametrized SVG render test at shared helper; `file_type_icons` and `icon_provider` both covered indirectly.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-ICON-5 — QPainter icon sprawl across six modules; Wave 1 extraction did not unify

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `rg 'QPainter' app/shell --type py -l` → `icon_provider.py`, `file_type_icons.py`, `outline/outline_icons.py`, `test_explorer_icons.py`, `toolbar_icons.py`, `icons.py`, `problems_panel.py`, `diff_view.py`, `search_sidebar_widget.py`, `unsaved_changes_dialog.py`. Wave 1 TN-SHELL-OUTLINE-6 flagged ~200 LOC of panel-local painters; remediation moved outline painters to `outline_icons.py` (`49-134`) and test-explorer painters to `test_explorer_icons.py` (`13-245`) — **file moves, not consolidation**. Each module repeats: `QPixmap` → fill transparent → `QPainter` → `Antialiasing` → draw → `end()`.
- **Code-judo alternative:** Thin `shell_pixmap_icons.py` with `_new_pixmap(size)`, `_badge_icon`, `_chevron_polygon`, `_circle_glyph` primitives; outline/test-explorer/problems/toolbar compose from shared builders. Long-term: token-aware `paint_icon(draw_fn, tokens)` pattern from `icons.py:9-20` extended for single-color themed panels.
- **Suggested remediation:** After TN-SHELL2-ICON-1 split, second PR introduces shared primitives and migrates `outline_icons` + `test_explorer_icons` action icons (`189-245`) first (highest duplication with `toolbar_icons`).
- **Tests that would prove fix:** Primitive-level unit tests (badge text centering, chevron orientation); panel tests stay behavior-only.
- **Handoff overlap:** R3, CC-21, TN-SHELL-OUTLINE-6 (Wave 1)

---

### TN-SHELL2-ICON-6 — CC-23: outline kind colors still binary `is_dark`, not `ShellThemeTokens`

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline/outline_icons.py:19-46` — parallel `_KIND_COLORS_DARK` / `_KIND_COLORS_LIGHT` dicts; `kind_color_for(kind, is_dark=...)` selects palette. `app/shell/outline/outline_panel.py:393` — `kind_color_for(symbol.kind, is_dark=self._is_dark_theme())`. No `is_high_contrast` branch; HC Light and Light share the light palette; HC Dark and Dark share the dark palette. Wave 1 CC-23 / TN-SHELL-OUTLINE-8 documented HC kind-color gap.
- **Code-judo alternative:** `kind_color_for(kind, tokens: ShellThemeTokens) -> str` reading semantic outline-kind token fields (add to `ShellThemeTokens` if missing) so HC modes get AAA-tuned hues without panel-level branching. Delete parallel hex dicts.
- **Suggested remediation:** Extend `theme_tokens.py` with outline kind colors per theme family; map in `tokens_from_palette`; outline_icons consumes tokens only.
- **Tests that would prove fix:** Parametrized test: four token fixtures → distinct or documented-equal kind colors for `class`/`function`; manual four-theme outline glyph check.
- **Handoff overlap:** R3, CC-23

---

### TN-SHELL2-ICON-7 — CC-23: explorer toolbar wired with hardcoded hex before theme workflow runs

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/main_window_panels.py:132-146` — `new_file_icon("#495057", "#3366FF")`, `new_folder_icon(...)`, `refresh_icon("#495057")` at panel construction. `shell_theme_workflow.apply_explorer_theme` (`226-235`) later applies `tokens.icon_primary` / `tokens.icon_muted` — correct path exists but first paint / early startup uses non-token colors. Wave 1 CC-23 flagged inline hardcoded shell chrome colors.
- **Code-judo alternative:** Construction uses placeholder empty icons or defers icon assignment until first `apply_explorer_theme` call (same pattern as menu bar via `apply_menu_icons`). No hex literals in `main_window_panels.py`.
- **Suggested remediation:** Remove hardcoded colors from `main_window_panels`; ensure theme workflow runs immediately after explorer panel build.
- **Tests that would prove fix:** Integration test: after panel wiring + theme apply, explorer button icon pixmap non-null and matches token-derived color (sample pixel or cache key assertion).
- **Handoff overlap:** R3, CC-23

---

### TN-SHELL2-ICON-8 — Test-explorer action icons duplicate `toolbar_icons` / `icon_provider.refresh_icon`

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/test_explorer_icons.py:189-245` — `_make_play_icon`, `_make_rerun_icon`, `_make_refresh_icon` hand-painted triangles/arrows. `app/shell/toolbar_icons.py:45-57` — `icon_run` (same play triangle). `app/shell/icon_provider.py:131-141` — `refresh_icon(color)` SVG refresh glyph. Wave 1 TN-SHELL-TEST-UI-1 recommended folding action icons into shared primitives; extraction to `test_explorer_icons.py` completed without dedup.
- **Code-judo alternative:** `action_icon("play", color)` → `toolbar_icons.icon_run(color)`; `action_icon("refresh", color)` → `icon_provider.refresh_icon(color)`; delete ~60 LOC of duplicate QPainter setup in test-explorer module.
- **Suggested remediation:** ICON-wave cleanup PR after TN-SHELL2-ICON-5 primitives exist; keep outcome/kind painters local (no toolbar equivalent).
- **Tests that would prove fix:** `test_test_explorer_panel` icon cache tests still pass; optional snapshot that play/refresh pixmaps match toolbar equivalents at same color.
- **Handoff overlap:** R3, CC-21, TN-SHELL-TEST-UI-1 (Wave 1)

---

### TN-SHELL2-ICON-9 — CC-21: icon pipeline test coverage thin; private-cache probing in panel tests

- **Persona:** TN-SHELL2-ICON
- **Status:** RESIDUAL
- **Severity:** STRUCTURAL
- **Evidence:** `tests/unit/shell/test_menu_icons.py` — 106 LOC, smoke only: mapping completeness (`59-63`), four-theme pixmap non-null (`81-88`), submenu wiring (`91-105`). No `test_icon_provider.py`, no `test_file_type_icons.py`, no `test_test_explorer_icons.py`. `tests/unit/shell/test_test_explorer_panel.py:55-127` imports `_OUTCOME_BUILDERS`, `_OUTCOME_ICON_CACHE`, `_KIND_ICON_CACHE`, `_ACTION_ICON_CACHE` — private module internals (anti-pattern per `test_anti_patterns.mdc`). Manifest P5: "`icon_provider` decomposition | partial icon tests | **High** gap."
- **Code-judo alternative:** Public contract tests at module boundaries: `build_menu_icon` (exists), plus `build_file_type_icon_map()` key coverage for critical extensions, `outcome_icon("passed", hex)` four-theme parametrize, `kind_icon` outline parity. Panel tests assert tree icon non-null after theme apply without touching caches.
- **Suggested remediation:** Risk-first tests only where branching exists: cache clear semantics (TN-SHELL2-ICON-3), extension map builder, four-theme menu render (extend existing file).
- **Tests that would prove fix:** New tests listed above; delete private-cache imports from panel tests when public API sufficient.
- **Handoff overlap:** R6 (test audit), CC-21, CC-24 (private probing)

---

### TN-SHELL2-ICON-10 — Menu bar icons split across three subsystems (`icon_provider`, `toolbar_icons`, `icons`)

- **Persona:** TN-SHELL2-ICON
- **Status:** NEW
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/menu_icons.py:78-179` — `_ACTION_ICON_BUILDERS` mixes `icon_provider.*` (~50 actions), `toolbar_icons.icon_run/icon_debug/...` (~15 run/debug actions), and `_test_icon` → `app/shell/icons.py:test_icon` (pytest menu entries). Reader must know three modules + two paint technologies (SVG strings vs QPainter) to audit one menu bar.
- **Code-judo alternative:** `menu_icons` dispatches to a **single** registry (TN-SHELL2-ICON-2) that owns all menu glyphs; toolbar reuses same registry keys for overlapping run/debug shapes. `icons.py` stays activity-bar-only.
- **Suggested remediation:** Consolidate during menu SVG registry migration; document ownership: "all menu/action bar glyphs → registry; activity bar → `icons.py`; file tree types → `file_type_icons.py`."
- **Tests that would prove fix:** `test_every_static_main_menu_action_has_icon_mapping` unchanged; add assertion that every builder resolves through one registry module.
- **Handoff overlap:** R3, CC-21

---

### TN-SHELL2-ICON-11 — `file_type_icon_map(primary_color)` accepts but ignores theme color

- **Persona:** TN-SHELL2-ICON
- **Status:** NEW
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/icon_provider.py:57-63` — docstring states `primary_color` "accepted for call-site compatibility but not used"; body calls `build_file_type_icon_map()` with no args. `shell_theme_workflow.apply_explorer_theme:221` — `sink.tree_file_icon_map = file_type_icon_map()` (no color passed). Intentional VS Code fixed palette in `file_type_icons.py` but API misleads callers expecting theme-aware tree icons.
- **Code-judo alternative:** Remove `primary_color` parameter (hard cutover) or rename to `file_type_icon_map()` only with no params; update type hints and call sites in one PR.
- **Suggested remediation:** Small API hygiene PR; no visual change.
- **Tests that would prove fix:** Pyright clean on call sites; no caller passes meaningful `primary_color`.
- **Handoff overlap:** none

---

## CC theme re-validation

| CC theme | Wave 1 status | Wave 2 (this slice) | Notes |
|----------|---------------|---------------------|-------|
| **CC-21** | PARTIAL — R3 hotspot splits stalled | **PARTIAL** — outline/test-explorer icon extraction **closed** their panel LOC debt; **`icon_provider` became the sole ≥1k `app/` file** and icon tests remain thin | TN-SHELL2-ICON-1, -5, -8, -9, -10 |
| **CC-23** | PARTIAL — four-theme gaps (outline kind colors, inline hex) | **PARTIAL** — outline still binary `is_dark` palettes; explorer construction hex literals remain | TN-SHELL2-ICON-6, -7; file-type fixed colors are intentional, not a regression |

No **REGRESSION** detected on CC-21 or CC-23 relative to Wave 1 remediation outcomes; residual debt shifted from panel monoliths to centralized `icon_provider` sprawl.

---

## Approval bar

| Gate | Result |
|------|--------|
| No `app/` file >1k without compelling structure | **FAIL** — `icon_provider.py` 1,106 LOC |
| CC-21 decomposition | **PARTIAL** |
| CC-23 four-theme icon colors | **PARTIAL** |
| Obvious code-judo path visible | **YES** — registry + split + shared SVG/paint primitives |
| Test signal at icon boundaries | **WEAK** |

**Verdict: REJECT.** Do not add menu/context SVG glyphs to `icon_provider.py` until TN-SHELL2-ICON-1 split and TN-SHELL2-ICON-2 registry land. Parallel track: TN-SHELL2-ICON-3 cache clear, TN-SHELL2-ICON-6/7 CC-23 token wiring, TN-SHELL2-ICON-9 risk-first tests.

---

## Suggested fix wave (ICON slice only)

| Step | Findings | Outcome |
|------|----------|---------|
| 1 | ICON-1, ICON-2, ICON-4 | Split `icon_provider`; SVG registry; shared `render_svg` |
| 2 | ICON-3, ICON-9 | `clear_icon_caches` + boundary tests |
| 3 | ICON-5, ICON-8 | Shared QPainter primitives; dedup test-explorer actions |
| 4 | ICON-6, ICON-7 | CC-23 token-driven outline kinds; remove explorer hex literals |
| 5 | ICON-10, ICON-11 | Menu registry unification; dead param cleanup |
