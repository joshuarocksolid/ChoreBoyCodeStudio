# TN-EDIT-CORE — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-CORE  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/code_editor_widget.py` (754 LOC), `app/editors/code_editor_chrome_mixin.py` (232 LOC), `app/editors/code_editor_bracket_overlay_mixin.py` (116 LOC), `app/editors/editor_overlay_policy.py` (43 LOC), `app/editors/paste_hint_overlay.py` (199 LOC). Cross-read for MRO/overlay assembly: `code_editor_diagnostics.py`, `code_editor_search.py`, `code_editor_semantics.py` (not in slice). Gates: §12.4 mixin model, no semantic `ExtraSelection`, four-theme `ShellThemeTokens`, intelligence imports presentation-only.

---

## Executive verdict

**Not thermo-clean — the composition hub is directionally split but the widget still absorbs orchestration debt faster than the mixins absorb features.** `editor_overlay_policy.py` and the chrome/bracket extractions are credible code-judo; bracket matching and gutter paint are appropriately bounded. Dominant risks: **`CodeEditorWidget` at 754 LOC** with ~270 lines of paste-hint wiring, overlay refresh, and theme/highlighter policy still inline (250 LOC headroom to the 1k presumptive blocker); **`RollingLatencyTracker` imported from `app.intelligence`** (metrics infra, not presentation); **four-theme collapse** where bracket and paste-hint styling fork on `is_dark` or hardcoded hex instead of token fields; and **intelligence-adjacent state** (`DiagnosticSeverity`, hover/completion callback fields) initialized in the hub while behavior lives in sibling mixins — the same ownership fracture flagged in TN-INT-SHELL-EDITORS-10. No AD-016 session bypass or semantic `ExtraSelection` pipeline appears in this slice; overlay `ExtraSelection` usage here is presentation (line highlight, bracket, search, debug, diagnostics paint). **REJECT** until paste-hint + overlay orchestration extract to mixins/modules, latency tracking moves out of `app.intelligence`, and a written decomposition cap keeps the hub under ~650 LOC before the next editor feature lands.

---

### TN-EDIT-CORE-1 — Hub widget at 754 LOC with no decomposition cap before next growth

- **Persona:** TN-EDIT-CORE
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_widget.py:53-61,64-152` — six mixins plus `QPlainTextEdit`, ~90 lines of `__init__` state (completion, hover, paste hint, overlay cache, diagnostics colors, search colors, highlighter policy). File totals **754 LOC**; `_README.md` 1k rule flags presumptive blocker territory. Paste hint (~lines 352-581), overlay refresh (~605-723), and theme/highlighter attach (~154-276) remain in the hub after chrome/bracket splits.
- **Code-judo alternative:** Treat 650 LOC as a hard budget on `code_editor_widget.py`. Extract `CodeEditorPasteHintMixin` and `CodeEditorOverlayMixin` (or `editor_overlay_coordinator.py` pure helper + thin mixin) so the hub is wiring-only: MRO, `apply_theme` delegation, and public façade methods. Document the cap in `ARCHITECTURE.md` §12.4.
- **Suggested remediation:** Land paste-hint + overlay extractions in one hard cutover; delete duplicated state from widget `__init__`. Block new hub methods without corresponding mixin home.
- **Tests that would prove fix:** `wc -l code_editor_widget.py` ≤ 650 after extraction; existing paste-hint and overlay unit/acceptance paths unchanged.
- **Handoff overlap:** §12.4, CC-02

---

### TN-EDIT-CORE-2 — `RollingLatencyTracker` pulls editor hub into `app.intelligence`

- **Persona:** TN-EDIT-CORE
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_widget.py:37,75-77,725-753` — `from app.intelligence.latency_tracker import RollingLatencyTracker`; three trackers in `__init__`; `_record_latency_metric` couples editor paint paths to intelligence package metrics. Gate 8: editors import typed presentation models only; latency tracker is observability infra, not a presentation DTO.
- **Code-judo alternative:** Move `RollingLatencyTracker` / `LatencySnapshot` to `app.core.metrics` or `app.bootstrap.metrics` (same module intelligence uses). Widget imports from core; intelligence and editors share one neutral home.
- **Suggested remediation:** Relocate tracker module; re-export from intelligence temporarily only if external callers exist, then hard cutover imports in editors.
- **Tests that would prove fix:** `rg 'from app.intelligence' app/editors/code_editor_widget.py` lists only `CompletionItem`, `CodeDiagnostic`, `DiagnosticSeverity` (presentation types); no `latency_tracker`.
- **Handoff overlap:** R4, AD-016

---

### TN-EDIT-CORE-3 — Paste-hint orchestration stranded in hub (~120 LOC) despite pure UI widget

- **Persona:** TN-EDIT-CORE
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/paste_hint_overlay.py:1-6` — doc states wiring lives in `CodeEditorWidget`. `app/editors/code_editor_widget.py:352-581` — `insertFromMimeData`, `_maybe_show_flat_python_paste_hint`, overlay lifecycle, session dismiss flags, test triggers, and context-menu augmentation all in hub. Contrast: gutter chrome extracted to `code_editor_chrome_mixin.py`, bracket match to `code_editor_bracket_overlay_mixin.py`.
- **Code-judo alternative:** `CodeEditorPasteHintMixin` owns `_paste_hint_*` state, `_ensure_paste_hint_overlay`, handlers, and test helpers; hub keeps only `insertFromMimeData` one-liner delegating to mixin. `PasteHintOverlay` stays pure UI.
- **Suggested remediation:** Move lines 89-94, 352-581 (paste paths) into new mixin; wire `_init_paste_hint_state()` from hub `__init__`.
- **Tests that would prove fix:** Existing paste-hint tests pass via mixin methods; hub LOC drops ~120.
- **Handoff overlap:** §12.4, none

---

### TN-EDIT-CORE-4 — ExtraSelection overlay engine monolithic in hub while policy is extracted

- **Persona:** TN-EDIT-CORE
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/editor_overlay_policy.py:8-43` — pure helpers for large-doc mode and viewport window (good). `app/editors/code_editor_widget.py:605-723` — `_refresh_extra_selections`, cache/generation invalidation, viewport capping, bounded search, and `_build_non_cursor_extra_selections` orchestration remain in hub. Mixins supply fragments (`_build_bracket_match_selections`, `_debug_execution_extra_selection`, diagnostics/search lists) but hub is the only composer.
- **Code-judo alternative:** `EditorOverlayComposer` (pure function: mode + selections in → ordered list out) or `CodeEditorOverlayMixin` owning cache fields and `_refresh_extra_selections`; hub calls `_highlight_current_line` → mixin. Keeps §12.4 “focused mixins for diagnostics overlays” honest.
- **Suggested remediation:** Move overlay cache fields (`_overlay_*`, `_cached_non_cursor_selections`) and refresh pipeline to overlay mixin; hub retains `cursorPositionChanged` connect only.
- **Tests that would prove fix:** Large-file overlay cap and generation short-circuit tests target mixin/composer module; behavior parity on `MAX_OVERLAY_SELECTIONS_LARGE_FILE`.
- **Handoff overlap:** §12.4, CC-02

---

### TN-EDIT-CORE-5 — Bracket overlay theme collapses four themes to `is_dark` binary

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_bracket_overlay_mixin.py:30-31` — `_apply_bracket_overlay_theme(self, *, is_dark: bool)` sets `#5C3D1A` vs `#FFD8A8` only. `app/editors/code_editor_widget.py:163` — `apply_theme` passes `is_dark=tokens.is_dark`, not full tokens. HC Light and Light share light branch; HC Dark and Dark share dark branch — no HC-specific contrast tuning. `ShellThemeTokens` has no `bracket_match_bg` field (`theme_tokens.py:54-120`).
- **Code-judo alternative:** Add optional `bracket_match_bg` to `ShellThemeTokens` (populated in HC presets); `_apply_bracket_overlay_theme(tokens: ShellThemeTokens)` reads token or derived syntax accent.
- **Suggested remediation:** Token field + four-theme preset values; delete `is_dark` parameter from bracket mixin.
- **Tests that would prove fix:** Manual four-theme acceptance: bracket pair visible on `#FFFFFF` HC Light and `#000000` HC Dark editor backgrounds.
- **Handoff overlap:** none

---

### TN-EDIT-CORE-6 — `PasteHintOverlay.apply_theme` hardcodes accent/hover hex outside tokens

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/paste_hint_overlay.py:92-104` — docstring says “light / dark”; `accent = tokens.accent or ("#3B82F6" if is_dark else "#1D4ED8")`; `accent_hover`, `always_hover_bg`, `dismiss_hover_bg` are literal hex forks on `is_dark`, not `tokens.tree_hover_bg` / `tokens.chrome_hover_overlay`.
- **Code-judo alternative:** Map hover surfaces from existing semantic tokens (`chrome_hover_overlay`, `tree_hover_bg`, `accent`); add `popup_button_hover` to tokens if HC modes need thicker contrast. Use `tokens.focus_border_width` on focusable-adjacent chrome if borders are added later.
- **Suggested remediation:** Replace hardcoded hover hex with token reads; extend HC presets where contrast fails WCAG AAA on popup chrome.
- **Tests that would prove fix:** Four-theme manual acceptance for paste hint after flat Python paste (Re-indent / Always / dismiss hover states readable).
- **Handoff overlap:** none

---

### TN-EDIT-CORE-7 — Chrome mixin hardcodes breakpoint marker colors bypassing tokens

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_chrome_mixin.py:65-69,77` — init defaults `#E03131`, `#D97706`, `#D0E2FF`, `#F1F3F5`; `_apply_chrome_theme` maps gutter/debug from tokens but breakpoint uses `QColor("#FF6B6B") if tokens.is_dark else QColor("#E03131")` instead of a token field (e.g. reuse `diag_error_color` or dedicated `breakpoint_color`).
- **Code-judo alternative:** Add `breakpoint_color` to `ShellThemeTokens` or alias to existing semantic error accent; chrome reads one token in init and `apply_theme`.
- **Suggested remediation:** Token-driven breakpoint color in `_apply_chrome_theme`; remove init hardcoded defaults where `apply_theme` always follows construction.
- **Tests that would prove fix:** Breakpoint dot visible in HC Light/Dark gutter icon zone (manual acceptance).
- **Handoff overlap:** none

---

### TN-EDIT-CORE-8 — Inline import in paste-hint show path violates module import discipline

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_widget.py:486-488` — inside `_maybe_show_flat_python_paste_hint`: `from app.editors.text_editing import FLAT_PYTHON_CONFIDENCE_LOW`. Same module already imports `repair_flat_python_indentation`, `looks_like_flat_python_paste` at top (`:27-31`).
- **Code-judo alternative:** Add `FLAT_PYTHON_CONFIDENCE_LOW` to top-level import from `text_editing`; no function-body import.
- **Suggested remediation:** One-line import fix at module top; delete inline import.
- **Tests that would prove fix:** Lint/rule pass; paste-hint low-confidence suppression unchanged.
- **Handoff overlap:** none

---

### TN-EDIT-CORE-9 — Intelligence presentation types and callback slots initialized in hub, behavior in sibling mixins

- **Persona:** TN-EDIT-CORE
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/code_editor_widget.py:96-112,127-132` — `_completion_*`, `_hover_*`, `_signature_help_*`, `_diagnostic_lines: dict[int, DiagnosticSeverity]` in hub `__init__`. Semantics/diagnostics mixins own setters, key handling, and tooltip dispatch (`code_editor_semantics.py`, `code_editor_diagnostics.py`). MRO: diagnostics before semantics (`:53-59`) — hover dispatch split across mixins (TN-INT-SHELL-EDITORS-10).
- **Code-judo alternative:** Each mixin owns its private state via `_init_semantics_state()` / `_init_diagnostics_state()` called from hub; hub does not declare intelligence fields. Tooltip entry consolidates under semantics mixin.
- **Suggested remediation:** Move field declarations to owning mixins; hub `__init__` calls mixin init hooks only. Pair with TN-INT-SHELL-EDITORS-10 hover consolidation.
- **Tests that would prove fix:** Characterization tests for completion/hover/diagnostics still pass; single `_hover_request_generation` owner.
- **Handoff overlap:** TN-INT-SHELL-EDITORS-10, AD-016

---

### TN-EDIT-CORE-10 — Hub retains hardcoded pre-theme QColor defaults for editor chrome overlays

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_widget.py:118-129` — `_line_highlight`, search match, diagnostic underline colors as literal `#EEF7FF`, `#FFE066`, etc., until first `apply_theme`. `apply_theme` (`:162-173`) overwrites from tokens when present — flash-of-wrong-theme on first paint if widget shown before theme bind.
- **Code-judo alternative:** Lazy-init colors from `ShellThemeTokens` defaults at construction (pass tokens from factory) or neutral transparent until `apply_theme`; no light-theme-assumptive literals in hub.
- **Suggested remediation:** Factory always calls `apply_theme` before `show`; or init from `tokens_from_palette` default for current mode.
- **Tests that would prove fix:** Widget constructed in dark mode without intermediate `apply_theme` does not paint light `#EEF7FF` line highlight.
- **Handoff overlap:** none

---

### TN-EDIT-CORE-11 — Test-only paste-hint trigger API expands public widget surface

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/code_editor_widget.py:434-462` — `has_flat_python_paste_hint_visible`, `trigger_flat_python_paste_hint_reindent`, `trigger_flat_python_paste_hint_always`, `trigger_flat_python_paste_hint_dismiss` documented as “Test helper” on production widget class.
- **Code-judo alternative:** Expose helpers via test double mixin, `# noqa: test-only` module under `tests/support/`, or signal injection on `PasteHintOverlay` without polluting widget public API.
- **Suggested remediation:** Move triggers to mixin test shim or overlay direct access in tests only.
- **Tests that would prove fix:** Tests updated to use overlay/mixin seam; public widget API slimmed.
- **Handoff overlap:** none

---

### TN-EDIT-CORE-12 — `editor_overlay_policy.py` is the right extraction pattern (positive control)

- **Persona:** TN-EDIT-CORE
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/editor_overlay_policy.py:8-43` — pure functions `is_large_document`, `effective_highlighting_mode`, `visible_document_window`; no Qt imports; hub delegates (`code_editor_widget.py:674-686,714-722`). Testable without widget instance.
- **Code-judo alternative:** Extend this module (or sibling `editor_overlay_composer.py`) for selection ordering and cap logic currently in hub — replicate this pattern for paste-hint predicates if any grow beyond `text_editing`.
- **Suggested remediation:** Use as template for TN-EDIT-CORE-3/4 extractions; do not re-inline policy into widget.
- **Tests that would prove fix:** Unit tests on policy functions for boundary thresholds (already low-cost to add if missing).
- **Handoff overlap:** none

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| §12.4 mixin model | Chrome + bracket split credible; paste hint + overlay composer still hub-bound |
| 1k-line rule | 754 LOC — **within limit but presumptive smell**; ~250 LOC headroom |
| No semantic `ExtraSelection` | Compliant — bracket/search/debug/diagnostics paint only; no tree-sitter semantic overlay pipeline |
| Four-theme tokens | Partial — gutter/line/search/diag from tokens; bracket/breakpoint/paste hint use `is_dark` or hex forks |
| Intelligence import boundary | **`latency_tracker` leak**; `CompletionItem` / `DiagnosticSeverity` acceptable presentation types |
| Prior hover split | TN-INT-SHELL-EDITORS-10 still applies; hub init duplicates mixin-owned fields |

---

## Verdict

**REJECT** — Slice is not thermo-clean for continued editor-core growth. No BLOCKER-tier AD-016/AD-018 violations in these five files, but STRUCTURAL hub sprawl (754 LOC, intelligence metrics import, mixin ownership fracture) and missing decomposition plan fail the §12.4 bar before the next feature wave. Ship TN-EDIT-CORE-1 through TN-EDIT-CORE-4 and TN-EDIT-CORE-2 as P1; four-theme and inline-import items are P2 backlog.
