# TN-SHELL-OUTLINE — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-SHELL-OUTLINE  
**Date:** 2026-05-25  
**Baseline commit:** `7d1c89f9154aafb9cf6ccbd38d88890f5e0f39f9`  
**Scope:** `app/shell/outline_panel.py` (1,155 LOC, R3 handoff). Cross-read: `app/intelligence/outline_service.py`, `app/shell/main_window.py` (outline refresh + layout state), `app/shell/main_window_panels.py` (wiring), `app/shell/style_sheet_sections_panels.py` (`shell_section_outline_panel`), `app/shell/icon_provider.py`, `app/shell/theme_tokens.py`, `tests/unit/shell/test_outline_panel.py` (434 LOC).

---

## Executive verdict

**Not thermo-clean.** The panel is a well-scoped feature widget with sensible private subcomponents (`_OutlineHeaderBar`, `_OutlineFilterRow`, `_OutlineTreeWidget`, `_IndentGuideDelegate`), but all five layers plus ~200 lines of hand-rolled `QPainter` icon factories live in a **single 1,155-line file** — 15% past the 1k boundary with no decomposition yet despite R3 handoff intent. Worse, collapse is implemented through **three divergent code paths**; two of them (`mousePressEvent`, `_handle_chevron_clicked`) mutate `_collapsed` without updating the `collapsed` dynamic property that `shell_section_outline_panel` styles depend on, so user-driven collapse can silently skip QSS (accent top border, hover background). Sort mode is duplicated between header and panel; collapse layout is copy-pasted between `set_collapsed` and `_handle_header_toggled`. Symbol sorting clones the entire `OutlineSymbol` tree on every re-render instead of sorting at the view layer. The intelligence boundary (`outline_service`) is clean; the sprawl is entirely shell-side presentation. **Would not approve** further feature work landing in this file without an R3 split and collapse-path unification.

---

### TN-SHELL-OUTLINE-1 — 155 lines past the 1k boundary; no decomposition despite R3 label

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py` — 1,155 LOC per wave manifest (`docs/code review/shell-wave-1/00-manifest.md:101`). File bundles module docstring, constants, icon caches, four private widget classes, and `OutlinePanel` orchestrator in one translation unit.
- **Code-judo alternative:** R3 split into focused modules under `app/shell/outline/` (or `outline_panel_*` siblings): `outline_icons.py` (~200 LOC), `outline_header.py` (~300 LOC), `outline_filter.py` (~50 LOC), `outline_tree.py` (~80 LOC), `outline_panel.py` (~400 LOC orchestrator + tree model glue). Each file stays under 400 LOC and maps to one reader mental model.
- **Suggested remediation:** Land split as first R3 PR for outline; no new behavior until file count ≥ 2. Re-export `OutlinePanel` and `clear_icon_caches` from `outline_panel.py` shim if needed for one release, then hard cutover imports in `main_window_panels.py`.
- **Tests that would prove fix:** Existing `tests/unit/shell/test_outline_panel.py` stays green; optional import-boundary check that `outline_panel.py` orchestrator < 500 LOC post-split.
- **Four-theme impact:** Split itself is neutral; enables HC palette work (finding 8) without touching tree logic.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-2 — Header collapse toggles bypass `setProperty("collapsed")` — stylesheet drift on main UX path

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py:419-428` — `set_collapsed` updates `self.setProperty("collapsed", bool(collapsed))` and repolishes. `487-494` and `528-532` — `mousePressEvent` and `_handle_chevron_clicked` flip `self._collapsed` directly, update chevron/actions, emit `toggled`, but **never** call `setProperty` or `set_collapsed`. Stylesheet rules at `app/shell/style_sheet_sections_panels.py:95-98` (`header[collapsed="true"]`) therefore miss user-initiated collapse.
- **Code-judo alternative:** Single `_toggle_collapsed()` on `_OutlineHeaderBar` that always funnels through `set_collapsed(bool)` (property + chevron + visibility). Delete direct `_collapsed` mutation from event handlers.
- **Suggested remediation:** Fix in R3 split (`outline_header.py`); add unit test that chevron click sets `header.property("collapsed") == True` before/after polish cycle.
- **Tests that would prove fix:** `test_header_chevron_click_toggles_collapsed` extended to assert `panel.header_bar().property("collapsed")`; manual four-theme check that collapsed strip shows accent top border on click (not only on programmatic `set_collapsed`).
- **Four-theme impact:** **Light, Dark, HC Light, HC Dark** — collapsed header chrome (`border-top: accent`, `tree_hover_bg`) may not apply on the primary toggle path; functional collapse works, visual contract breaks.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-3 — Collapse layout orchestration is copy-pasted between `set_collapsed` and `_handle_header_toggled`

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py:754-772` and `1076-1092` — identical blocks: hide filter row, hide/show `_stack_container`, compute `_collapsed_header_height()`, set min/max height, restore filter visibility. Only the early-return guard and `collapsed_changed.emit` differ.
- **Code-judo alternative:** One `_apply_collapsed_layout(collapsed: bool, *, emit: bool)` private method; `set_collapsed` and `_handle_header_toggled` become guard + state assign + single call. Header emits signal; panel owns layout — header should not mirror collapse layout at all (already true), but panel must not duplicate the block.
- **Suggested remediation:** Collapse during R3 refactor; pair with TN-SHELL-OUTLINE-2 so all entry points hit one method.
- **Tests that would prove fix:** Parametrize existing collapse tests over `set_collapsed(True)` vs `header_bar().chevron_button().click()` — both must yield identical `minimumHeight()`, `filter_row.isHidden()`, `stack_container.isVisible()`.
- **Four-theme impact:** Low — height math is theme-agnostic; reduces risk of fixing one path and not the other.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-4 — Sort mode owned twice; parallel validation and re-render paths

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py:319`, `449-459`, `534-541` — `_OutlineHeaderBar._sort_mode` validated and updated locally, emits `sort_mode_changed`. `713`, `799-811`, `1106-1116` — `OutlinePanel._sort_mode` duplicates validation, `_render_tree`, filter re-apply, and `sort_mode_changed.emit`. `set_sort_mode` and `_handle_sort_changed` are near-identical except header sync direction.
- **Code-judo alternative:** Header is **view-only** for sort UI (menu check state); panel is sole owner of `_sort_mode`. Header emits raw menu selection; panel `set_sort_mode` is the only mutator. Or extract `OutlineSortController` with one `_sort_mode` field consumed by header binding and tree render.
- **Suggested remediation:** During R3 split, delete `_sort_mode` from `_OutlineHeaderBar`; header calls `panel.request_sort_mode(mode)` or only mirrors via `set_sort_mode` on panel. Align with `ExplorerOutlineLayoutController` from TN-SHELL-MW-03-4 for persisted sort mode.
- **Tests that would prove fix:** Existing sort tests (`test_set_sort_mode_*`) plus assert header menu state stays synced when sort changed only via panel API.
- **Four-theme impact:** None.
- **Handoff overlap:** R2, R3

---

### TN-SHELL-OUTLINE-5 — Sort clones entire `OutlineSymbol` tree — view concern mutating domain copies

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py:933-963` — `_sort_symbols` / `_sort_recursive` rebuild `OutlineSymbol` namedtuples with reordered `children` on every `_render_tree` call (`965-983`). `set_sort_mode` (807-808) and `apply_theme_tokens` (921-922) both trigger full sort+rebuild.
- **Code-judo alternative:** Keep `_symbols` immutable from `outline_service`; sort **item insertion order** in `_add_symbol` via a sort key function, or build a flat `(depth, sort_key, symbol)` list and attach to tree without cloning dataclass instances. Theme refresh should only refresh icons (`_update_item_icons`), not rebuild+sort the symbol tree.
- **Suggested remediation:** Extract `_sort_key(symbol) -> tuple` pure function; `_render_tree` sorts sibling iterables in place. Split `apply_theme_tokens` into icon-only refresh path vs full rebuild (file change only).
- **Tests that would prove fix:** Large fixture outline (100+ symbols): sort mode toggle + theme apply do not allocate new `OutlineSymbol` trees (identity test on `panel.symbols()`); perf smoke optional.
- **Four-theme impact:** Theme toggle on large files may flicker less if icon-only path used — UX win in all four modes.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-6 — ~200 lines of bespoke `QPainter` icons belong in canonical shell icon layer

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/outline_panel.py:101-205` — `_make_kind_icon`, `_chevron_icon`, `_make_codicon_text_icon`, module-level caches. Repo already centralizes themed icons in `app/shell/icon_provider.py` (SVG render pipeline) and `app/shell/icons.py`; `problems_panel.py` also hand-rolls `QPainter` pixmaps — pattern is duplicated, not shared.
- **Code-judo alternative:** `app/shell/outline/outline_icons.py` (or extend `icon_provider.py` with `outline_kind_icon(kind, tokens)` / `chevron_icon(color, expanded)`) so panel files contain zero `QPainter` code. Kind colors become token-driven functions, not parallel `_KIND_COLORS_*` dicts.
- **Suggested remediation:** First R3 extraction: move icon helpers + `clear_icon_caches` to dedicated module; wire lifecycle cleanup where shell tears down (if any). Longer term, consolidate with problems panel painter icons behind one `shell_pixmap_icons.py`.
- **Tests that would prove fix:** Move icon unit assertions from `test_outline_panel.py` (if any pixmap tests) to `test_outline_icons.py`; panel tests import public `OutlinePanel` only.
- **Four-theme impact:** Centralizing colors in token helpers is prerequisite for HC-aware kind glyphs (finding 8).
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-7 — `apply_theme_tokens` is untyped and diverges from shell `apply_theme` convention

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/outline_panel.py:911-924` — `def apply_theme_tokens(self, tokens) -> None:  # type: ignore[no-untyped-def]` with `getattr(tokens, "is_dark", False)` fallback. `app/shell/main_window.py:1229-1263` — siblings use `apply_theme(tokens: ShellThemeTokens)` (editors, console) or scalar field bundles (search sidebar). Cross-ref TN-SHELL-MW-03-6.
- **Code-judo alternative:** Rename to `apply_theme(self, tokens: ShellThemeTokens) -> None`; read `tokens.icon_primary`, `tokens.is_dark`, `tokens.is_high_contrast` explicitly. Removes silent `AttributeError` swallow at 917-918.
- **Suggested remediation:** Align during R3 panel split; update `main_window.py:1263` call site in same PR.
- **Tests that would prove fix:** Unit test with minimal `ShellThemeTokens` fixture asserts chevron + kind icons update; pyright clean on `outline_panel.py` without ignore.
- **Four-theme impact:** Explicit `ShellThemeTokens` makes HC fields available to finding 8.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-8 — Symbol kind colors are binary light/dark, not HC-aware

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/outline_panel.py:74-95`, `999-1000` — `_KIND_COLORS_DARK` / `_KIND_COLORS_LIGHT` only; `_is_dark_theme()` ignores `tokens.is_high_contrast` (`928-931`). Cross-ref TN-SHELL-MW-03-7 and workspace four-theme rule.
- **Code-judo alternative:** When `tokens.is_high_contrast`, select AAA-contrast kind palette from `theme_tokens.py` (or dedicated `_KIND_COLORS_HC_LIGHT` / `_HC_DARK` tables). Stylesheet chrome already uses HC tokens; icons should follow.
- **Suggested remediation:** After TN-SHELL-OUTLINE-6 icon extraction; manual acceptance in HC Light/Dark for class/function/method glyphs on `#FFFFFF` / `#000000` panel backgrounds.
- **Tests that would prove fix:** Parametrized test: HC token fixture returns different hex than non-HC for at least `class` and `function` kinds.
- **Four-theme impact:** **HC Light / HC Dark** — kind icon hues may fail AAA against pure white/black panel bg until tuned.
- **Handoff overlap:** R3

---

### TN-SHELL-OUTLINE-9 — Stranded `_max_height_expanded` field; triplicate clear/reset paths

- **Persona:** TN-SHELL-OUTLINE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/outline_panel.py:717` — `self._max_height_expanded = self.maximumHeight()` assigned at init, never read. `869-877`, `879-891`, `857-861` — `clear`, `set_unsupported_language`, and empty-symbol branch in `set_outline` each repeat tree clear, `_items_by_qualified_name.clear()`, `_symbols` reset, empty-label text, stack widget switch with small text variations.
- **Code-judo alternative:** Delete `_max_height_expanded` or wire it into expand path if max-height clamp was intended. Single `_show_empty_state(message: str)` helper absorbs three branches.
- **Suggested remediation:** Low-risk cleanup in R3 split PR; no behavior change.
- **Tests that would prove fix:** Existing `clear` / unsupported-language tests stay green.
- **Four-theme impact:** None.
- **Handoff overlap:** R3

---

## Positive signals (not findings)

- **`outline_service` boundary is correct** — panel consumes `OutlineSymbol` / `find_innermost_symbol`; no parsing in the widget (`38`, `897`).
- **Private sub-widgets are the right decomposition sketch** — header/filter/tree/delegate classes are cohesive; they need files, not further nesting in one module.
- **Expansion snapshot + filter pre-expansion** — `_snapshot_expanded` / `_pre_filter_expansion` (`1011-1048`) show deliberate UX state handling worth preserving through refactor.
- **Test coverage exists** — `tests/unit/shell/test_outline_panel.py` (434 LOC) covers hierarchy, expansion preservation, sort, filter, collapse, signals; good characterization base for R3 splits.
- **Stylesheet section is token-driven** — `shell_section_outline_panel(tokens)` uses semantic panel tokens; gap is dynamic property sync (finding 2), not QSS authoring.

---

## Approval bar (this module)

**Would not approve** new outline features or substantial edits to `outline_panel.py` until: (1) file splits below ~400 LOC per module, (2) collapse toggles unify through one property-aware path, (3) sort ownership consolidates to a single layer, (4) theme apply can refresh icons without full symbol-tree clone. Pair R3 panel work with R2 `ExplorerOutlineLayoutController` (TN-SHELL-MW-03-4) so MainWindow outline method count drops rather than grows.
