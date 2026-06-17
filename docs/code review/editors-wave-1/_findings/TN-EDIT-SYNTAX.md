# TN-EDIT-SYNTAX — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-SYNTAX  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/syntax_engine.py` (228 LOC), `app/editors/syntax_registry.py` (157 LOC), `app/editors/ini_highlighter.py` (134 LOC). Cross-read: `app/treesitter/highlighter_core.py` (447 LOC), `app/treesitter/language_registry.py`, `app/shell/theme_tokens.py`, `app/shell/settings_dialog_handlers.py`. Focus: highlighting pipeline, tree-sitter vs INI fallback, HC overrides, bidirectional `editors`↔`treesitter` coupling.

---

## Executive verdict

**Directionally sound factory split, but the syntax seam is not thermo-clean yet.** Extracting `ThemedSyntaxHighlighter` + palette defaults into `syntax_engine.py` and routing creation through `SyntaxHighlighterRegistry` is the right code-judo move; INI regex fallback is appropriately isolated. Dominant risks: **bidirectional package coupling** (`syntax_registry` → `treesitter`, `highlighter_core` → `editors`), a **dual HC palette path** where `build_syntax_palette(high_contrast=…)` is never wired while shell/theme already pre-merge HC colors into overrides, and **triplicate token-key mapping** across `syntax_engine`, `theme_tokens._SYNTAX_OVERRIDE_FIELD_MAP`, and `syntax_palette_from_tokens`. `IniSyntaxHighlighter` also duplicates line-matching logic between paint and hover/describe paths. No file crosses 1k LOC; no AD-016/semantic-overlay violations in this slice. **REJECT** until HC wiring is collapsed to one SSOT path, the editors↔treesitter import cycle is broken (neutral shared layer or policy relocation), and INI line parsing is deduplicated before the next language/highlighter feature lands.

---

### TN-EDIT-SYNTAX-1 — Bidirectional `app/editors` ↔ `app/treesitter` imports

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/syntax_registry.py:11-14` — `from app.treesitter.highlighter_core import TreeSitterHighlighter` and `from app.treesitter.language_registry import …`. `app/treesitter/highlighter_core.py:8-9` — `from app.editors.editor_overlay_policy import effective_highlighting_mode` and `from app.editors.syntax_engine import TokenStyle, ThemedSyntaxHighlighter`. Registry lives in editors but tree-sitter core pulls editor overlay policy back in.
- **Code-judo alternative:** Move `syntax_engine.py` (contracts + `ThemedSyntaxHighlighter`) to a neutral package (`app/syntax/` or `app/highlighting/`) owned by neither subsystem; or relocate `effective_highlighting_mode` next to tree-sitter adaptive highlighting (it is only consumed by `TreeSitterHighlighter._effective_mode`). Registry stays in editors as orchestrator; tree-sitter depends on neutral contracts only.
- **Suggested remediation:** Hard cutover: extract shared module; update imports in one diff; delete reverse `editors` import from `highlighter_core.py`.
- **Tests that would prove fix:** `rg 'from app\.editors' app/treesitter/highlighter_core.py` empty (except tests); `rg 'from app\.treesitter' app/editors/syntax_engine.py app/editors/ini_highlighter.py` empty.
- **Handoff overlap:** §12.4, CC-02

---

### TN-EDIT-SYNTAX-2 — Dead `high_contrast` flag on `build_syntax_palette` vs shell token pipeline

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/syntax_engine.py:151-170,187,204` — `build_syntax_palette(..., high_contrast=False)` selects `DEFAULT_HC_*` when true, but `ThemedSyntaxHighlighter.__init__` and `set_theme_palette` never pass `high_contrast=True` (repo-wide grep: only definition sites). HC colors reach highlighters via `app/shell/shell_theme_workflow.py:160-173` → `tokens_from_palette` (`theme_tokens.py:184-191`) → `code_editor_widget.apply_theme` → `syntax_palette_from_tokens(tokens)` → overrides passed as `syntax_palette`. Direct highlighter construction with `is_dark=True` and empty palette gets **dark**, not HC, even in HC chrome mode.
- **Code-judo alternative:** **Delete** the `high_contrast` parameter and HC branches inside `build_syntax_palette`; document that HC is exclusively shell-resolved via `ShellThemeTokens` + user overrides. Or wire `tokens.is_high_contrast` through registry → `build_syntax_palette(high_contrast=…)` and drop duplicate HC injection in `tokens_from_palette` syntax fields — pick one path, not both.
- **Suggested remediation:** Single SSOT: shell owns mode selection; highlighter accepts fully merged palette only. Remove dead parameter or thread `is_high_contrast` from widget `apply_theme`.
- **Tests that would prove fix:** Unit test: HC Light tokens produce WCAG palette on highlighter without calling `build_syntax_palette(high_contrast=True)` manually; grep shows one HC resolution path.
- **Handoff overlap:** four-theme gate, CC-02

---

### TN-EDIT-SYNTAX-3 — Triplicate syntax token mapping / palette SSOT

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** STRUCTURAL
- **Evidence:** Default palettes defined once in `syntax_engine.py:22-148`. Token-key → shell-field mapping in `theme_tokens.py:320-350` (`_SYNTAX_OVERRIDE_FIELD_MAP`). Reverse mapping duplicated in `syntax_registry.py:126-157` (`syntax_palette_from_tokens`). Settings reset defaults in `settings_dialog_handlers.py:331-338` (`_syntax_defaults_for_theme`) import palettes again from `syntax_engine`. Adding one token category requires coordinated edits in ≥4 modules.
- **Code-judo alternative:** One module exports: (a) palette defaults, (b) `TOKEN_KEYS` tuple, (c) `palette_to_token_fields(tokens) -> SyntaxPalette` and `token_fields_to_palette(tokens) -> dict` generated from a single declarative map (dataclass or typed dict schema).
- **Suggested remediation:** Collapse `_SYNTAX_OVERRIDE_FIELD_MAP` and `syntax_palette_from_tokens` into `syntax_engine.py` (or shared `syntax_tokens.py`); `theme_tokens` and registry import helpers only.
- **Tests that would prove fix:** Parametrized test: every key in `DEFAULT_LIGHT_PALETTE` round-trips through `syntax_palette_from_tokens(tokens_from_palette(...))` without manual field lists.
- **Handoff overlap:** none

---

### TN-EDIT-SYNTAX-4 — `IniSyntaxHighlighter` duplicates line parser in paint and describe paths

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/ini_highlighter.py:38-65` (`highlightBlock`) and `:109-134` (`_token_name_for_column`) repeat the same sequence: comment → section → key/value regex match, column bounds, `_classify_value`. Any INI edge-case fix must land twice; drift already visible in `describe_position` using `_format(token_name if token_name != "section" else "section")` (`:84`) — redundant ternary on identical strings.
- **Code-judo alternative:** Pure function `parse_ini_line(text) -> IniLineSpans | None` returning named spans + token names; `highlightBlock` and `_token_name_for_column` call it once. Keeps regex fallback highlighter ~40 LOC thinner.
- **Suggested remediation:** Extract parser helper in `ini_highlighter.py` (or `ini_line_parser.py` if tests want isolation); delete duplicated match blocks.
- **Tests that would prove fix:** Parametrized tests on parser output; existing INI highlighter tests unchanged behavior.
- **Handoff overlap:** none

---

### TN-EDIT-SYNTAX-5 — `SyntaxHighlighterRegistry.create_for_path` returns `object | None` with duck-typed theme apply

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/syntax_registry.py:35,99-116` — factory returns `object | None`; `apply_theme` uses `hasattr(highlighter, "set_theme_palette")` else `set_dark_mode` with `# type: ignore[union-attr]`. All current highlighters inherit `ThemedSyntaxHighlighter` (`ini_highlighter.py:16`, `highlighter_core.py:33-39`), which implements both methods — legacy branch adds indirection without a second implementation.
- **Code-judo alternative:** Typed union `SyntaxHighlighter = IniSyntaxHighlighter | TreeSitterHighlighter | None` (or Protocol with `set_theme_palette`); delete `set_dark_mode` fallback in `apply_theme`.
- **Suggested remediation:** Narrow return type; remove dead `set_dark_mode`-only branch after confirming no external highlighter implementations.
- **Tests that would prove fix:** pyright clean on registry without `type: ignore`; `apply_theme` is 6 lines.
- **Handoff overlap:** none

---

### TN-EDIT-SYNTAX-6 — Language mode list and labels fork tree-sitter registry ownership

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/syntax_registry.py:17-19,64-76` — `_PLAIN_TEXT_LANGUAGE_KEY`, `_INI_LANGUAGE_KEY`, hardcoded display strings, and `_INI_EXTENSIONS` live beside `TreeSitterLanguageRegistry.available_language_modes()`. `language_mode_label` re-implements title casing for tree-sitter keys instead of delegating to `TreeSitterResolvedLanguage.display_name` / spec metadata. INI extension set is not shared with `language_registry.py` (INI intentionally absent from `LANGUAGE_SPECS` — fine, but extension list is editors-only magic).
- **Code-judo alternative:** Registry exposes `EditorLanguageMode` entries: `{key, label, factory}` including plain/INI entries; tree-sitter modes appended from language registry display names. Single `language_mode_label(key)` lookup table built at init.
- **Suggested remediation:** Consolidate mode metadata; avoid `language_key.replace("_", " ").title()` for user-facing labels when specs already carry `display_name`.
- **Tests that would prove fix:** `available_language_modes()` labels match tree-sitter spec display names for shared keys.
- **Handoff overlap:** none

---

### TN-EDIT-SYNTAX-7 — Tree-sitter adaptive highlighting policy imported from editors package

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** STRUCTURAL
- **Evidence:** `app/treesitter/highlighter_core.py:8,432-438` — `effective_highlighting_mode` from `app.editors.editor_overlay_policy` drives `_effective_mode()` inside tree-sitter capture pipeline. Adaptive mode thresholds are editor-widget policy (`code_editor_widget.set_highlighting_policy`) but enforcement lives in tree-sitter core — cross-layer leak noted in TN-EDIT-CORE-12 positive pattern for the policy module, negative here for **who imports it**.
- **Code-judo alternative:** Move `editor_overlay_policy.py` to `app/core/highlighting_policy.py` (or `app/highlighting/policy.py`) consumed by both widget and `TreeSitterHighlighter`; or pass resolved mode into highlighter instead of importing editor package from tree-sitter.
- **Suggested remediation:** Relocate policy module to neutral layer; tree-sitter accepts `effective_mode: str` from widget on each policy change.
- **Tests that would prove fix:** `rg 'from app\.editors' app/treesitter/` limited to syntax_engine shared contracts (post TN-EDIT-SYNTAX-1).
- **Handoff overlap:** TN-EDIT-CORE-12, §12.4

---

### TN-EDIT-SYNTAX-8 — Embedded tree-sitter highlighters read parent private `_palette`

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/treesitter/highlighter_core.py:365-377` — `_create_embedded_highlighter` passes `syntax_palette=dict(self._palette)` where `_palette` is private state on `ThemedSyntaxHighlighter` (`syntax_engine.py:187-188`). Injection children inherit theme correctly today but couple to underscore attribute instead of a public `current_syntax_palette()` or constructor snapshot.
- **Code-judo alternative:** Add `@property syntax_palette` on `ThemedSyntaxHighlighter` returning `Mapping[str, str]`; embedded path uses public accessor.
- **Suggested remediation:** One-line property; embedded factory uses it; document as stable for injection mixin.
- **Tests that would prove fix:** Injection highlight theme tracks parent after `set_theme_palette` without accessing `_palette` in tests.
- **Handoff overlap:** none

---

### TN-EDIT-SYNTAX-9 — `ThemedSyntaxHighlighter` + registry factory is the right extraction pattern (positive control)

- **Persona:** TN-EDIT-SYNTAX
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/syntax_engine.py:173-228` — shared palette build, format cache, theme refresh API. `app/editors/syntax_registry.py:26-62` — single `create_for_path` dispatcher: override → tree-sitter → INI extension fallback → plain. `app/editors/code_editor_widget.py:174-184,259-263` — widget delegates creation and theme to registry; no inline highlighter class selection in hub. File sizes remain healthy (228/157/134 LOC).
- **Code-judo alternative:** Extend this pattern for TN-EDIT-SYNTAX-1/3/4 fixes rather than re-inlining selection logic into `code_editor_widget.py`.
- **Suggested remediation:** Keep registry as sole factory; do not add per-language branches to widget.
- **Tests that would prove fix:** Existing `tests/unit/editors/test_syntax_highlighters.py` registry path continues to cover tree-sitter + INI creation.
- **Handoff overlap:** §12.4

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| Highlighting pipeline | Widget → `syntax_palette_from_tokens` → registry `create_for_path` / `apply_theme` — clear orchestration |
| Tree-sitter vs INI | Tree-sitter first; INI override + extension fallback — appropriate; no tree-sitter INI wheel assumed |
| HC overrides | Work end-to-end via shell tokens + per-theme user overrides; **`build_syntax_palette(high_contrast=)` unused** — dual-path smell |
| Four-theme compatibility | HC palette literals in `syntax_engine` + HC chrome in `theme_tokens`; highlighter sees merged overrides when shell applies theme |
| Bidirectional coupling | **Editors registry → treesitter; treesitter core → editors policy + syntax_engine** — presumptive structural blocker |
| 1k-line rule | All scoped files &lt; 450 LOC — compliant |
| Semantic `ExtraSelection` | Not in scope — compliant |

---

## Verdict

**REJECT** — Behavior and file sizing are acceptable, but the slice fails the thermo bar on maintainability boundaries: editors↔treesitter import cycle, unresolved dual HC palette path, and triplicate token mapping will compound cost on every new language token or theme mode. Ship TN-EDIT-SYNTAX-1 through TN-EDIT-SYNTAX-4 and TN-EDIT-SYNTAX-7 as P1 before adding syntax features; TN-EDIT-SYNTAX-5/6/8 as P2. Positive control TN-EDIT-SYNTAX-9 should be preserved through refactors.
