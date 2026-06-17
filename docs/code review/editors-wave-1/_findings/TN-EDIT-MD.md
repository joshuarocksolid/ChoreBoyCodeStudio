# TN-EDIT-MD — Thermo-Nuclear Code Quality Review

**Critic ID:** TN-EDIT-MD  
**Date:** 2026-06-17  
**Baseline commit:** `042be49e5777c587391ddbb396b7ea150e296dfe`  
**Scope:** `app/editors/markdown_editor_pane.py` (200 LOC), `app/editors/markdown_preview_widget.py` (168 LOC), `app/editors/markdown_rendering.py` (117 LOC). Cross-read: `app/shell/editor_tab_workflow.py` (markdown mode/actions, `release_editor_widget`), `app/shell/editor_tab_factory.py` (pane assembly), `app/shell/project_tree_ui_workflow.py` (rename/release seams), `app/shell/shell_composition.py` (`apply_markdown_themes`). Focus: dual-pane ownership, preview refresh, theme tokens, split from code editor. Gates: four-theme `ShellThemeTokens`, §12.4 editor separation, hard-cutover bias, 1k-line rule on shell tab workflow.

---

## Executive verdict

**Not thermo-clean — the three editor modules are a credible split from `CodeEditorWidget`, but shell dual-registry ownership and preview chrome theming leave maintainability debt at the seam.** `markdown_rendering.py` is the right pure-helper layer; `MarkdownEditorPane` owns debounced refresh, mode visibility, and scroll sync without bloating the code editor hub. Dominant risks: **parallel `_editor_widgets_by_path` / `_markdown_panes_by_path` registries with copy-pasted unwrap logic**, **rename-away-from-`.md` orphaning the composite pane**, **triplicated mode control (pane toolbar, View menu, tab context menu) with no checked-state sync**, **toolbar/status chrome never receiving tokens**, and **preview CSS that ignores existing `syntax_markdown_*` token fields while the source editor paints them via tree-sitter**. Preview refresh policy (debounce + large-file guard + manual Refresh) is sound; `apply_theme` does not re-render, so stylesheet updates can lag on an already-rendered document. **REJECT** until shell lifecycle owns one markdown unwrap path, rename teardown is atomic, pane chrome participates in four-theme `apply_theme`, and preview re-render hooks close the theme/refresh loop.

---

### TN-EDIT-MD-1 — Dual registry forces duplicate markdown unwrap in two shell workflows

- **Persona:** TN-EDIT-MD
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/editor_tab_factory.py:179-195` — `CodeEditorWidget` registers in `_editor_widgets_by_path`; tab content becomes `MarkdownEditorPane` stored separately in `_markdown_panes_by_path`. `app/shell/editor_tab_workflow.py:235-243` and `app/shell/project_tree_ui_workflow.py:362-371` — identical loops: find pane whose `source_editor() is widget`, pop dict entry, `markdown_pane.deleteLater()`, else `widget.deleteLater()`. `app/shell/main_window_composition.py:415` — project tree uses `project_tree_ui_workflow.release_editor_widget`, not a shared primitive.
- **Code-judo alternative:** One `MarkdownTabContent` registry helper (or method on a small `MarkdownTabRegistry`) that owns `{path → pane}`, exposes `release_widget(widget)`, `rekey(old, new)`, and `apply_all_themes(tokens)`. Both workflows delegate; delete duplicated loops.
- **Suggested remediation:** Extract shared unwrap/teardown to `app/shell/markdown_tab_registry.py` (or `editor_tab_workflow` canonical owner with tree workflow calling through host). Hard cutover — remove duplicate method bodies.
- **Tests that would prove fix:** Close tab and project-tree delete both tear down pane + source without double-`deleteLater`; `rg "markdown_pane.deleteLater" app/shell` hits one implementation.
- **Handoff overlap:** TN-EDIT-SHELL-TAB, CC-02

---

### TN-EDIT-MD-2 — Rename from Markdown to non-Markdown orphans composite pane

- **Persona:** TN-EDIT-MD
- **Severity:** STRUCTURAL
- **Evidence:** `app/shell/project_tree_ui_workflow.py:379-388` — on path update, if `markdown_pane.source_editor() is widget`, dict entry is popped; re-insert happens **only** when `is_markdown_path(new_path)`. No `markdown_pane.deleteLater()`, no tab widget swap back to bare `CodeEditorWidget`. Pane toolbar + preview remain tab content while registry drops the mapping; View menu markdown actions disable via `active_markdown_pane()` miss.
- **Code-judo alternative:** Treat extension change as tab-type migration: if `not is_markdown_path(new_path)`, reparent `source_editor()` into tab slot (or rebuild tab via factory), destroy pane, clear preview timers. Symmetric to factory wrap on open.
- **Suggested remediation:** Add `unwrap_markdown_pane(widget, new_path)` to shared registry; call from `update_widget_language_for_path` and any save-as/rename path. Integration test: rename `README.md` → `README.txt` leaves single `CodeEditorWidget` tab content.
- **Tests that would prove fix:** `test_rename_md_to_py_unwraps_markdown_pane` — tab widget is `CodeEditorWidget`, `_markdown_panes_by_path` empty, no leaked `MarkdownEditorPane`.
- **Handoff overlap:** TN-EDIT-SHELL-FACTORY, CC-02

---

### TN-EDIT-MD-3 — Mode control triplicated without a single SSOT or menu checked sync

- **Persona:** TN-EDIT-MD
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/markdown_editor_pane.py:76-81,141-153` — toolbar mode buttons call `set_mode` locally. `app/shell/editor_tab_workflow.py:360-381,383-397,524-542` — View menu handlers and tab context menu each call `markdown_pane.set_mode(...)` independently; `refresh_markdown_action_states` only toggles `setEnabled`, not checked state on menu actions. `MarkdownEditorPane.mode_changed` signal (`:34`) is emitted but never wired in `editor_tab_factory.py:183-195`.
- **Code-judo alternative:** Shell owns mode **commands**; pane owns mode **presentation**. Wire `mode_changed → refresh_markdown_action_states` and set `QAction.setChecked` from `pane.mode()`. Context menu should call `set_active_markdown_mode` (one path), not inline `set_mode` duplicates.
- **Suggested remediation:** Connect `mode_changed` at factory; extend `refresh_markdown_action_states` to mirror checked state; collapse context menu branches to workflow helpers.
- **Tests that would prove fix:** Toggle mode from pane toolbar → View menu checked state matches; toggle from menu → pane toolbar check state matches.
- **Handoff overlap:** TN-EDIT-SHELL-TAB, none

---

### TN-EDIT-MD-4 — Pane toolbar and status label bypass four-theme token application

- **Persona:** TN-EDIT-MD
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/markdown_editor_pane.py:136-139` — `apply_theme` delegates only to `_source_editor` and `_preview`. Toolbar (`:65-94`), mode buttons (`:178-185`), `_status_label` (`:91-93`), and `QSplitter` chrome receive no stylesheet or token reads. `app/shell/shell_composition.py:475-477` — shell theme pass calls `markdown_pane.apply_theme(tokens)` but pane chrome stays platform default. Tests cover preview browser only (`tests/unit/editors/test_markdown_editor_pane.py:56-64` — light/dark smoke, no HC).
- **Code-judo alternative:** Extend `apply_theme` to style toolbar from semantic tokens (`panel_bg`, `text_primary`, `text_muted`, `border`, `chrome_hover_overlay`, `tokens.focus_border_width` for HC focus). Reuse patterns from `find_replace_bar` or shell toolbar styling — do not hardcode hex.
- **Suggested remediation:** Token-driven stylesheet on `#shell.markdownEditorPane.toolbar`, mode buttons, status label; manual four-theme acceptance (Light, Dark, HC Light, HC Dark) for toolbar + paused status text on HC backgrounds.
- **Tests that would prove fix:** Four-theme manual acceptance; optional unit assert that `apply_theme` sets non-empty stylesheet on toolbar objectName.
- **Handoff overlap:** none

---

### TN-EDIT-MD-5 — Preview CSS ignores `syntax_markdown_*` tokens; source/preview visual contract forks

- **Persona:** TN-EDIT-MD
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/shell/theme_tokens.py:117-120` — `syntax_markdown_heading`, `syntax_markdown_emphasis`, `syntax_markdown_strong`, `syntax_markdown_code` exist and feed tree-sitter source highlighting (`tests/unit/editors/test_syntax_registry.py:129`). `app/editors/markdown_preview_widget.py:69-104` — preview `setDefaultStyleSheet` maps headings to `text_primary`, links to `accent`, code to `badge_bg`; never reads `syntax_markdown_*`. User sees tree-sitter-colored Markdown in source mode and a generic sans-serif preview in preview/split.
- **Code-judo alternative:** Map preview element styles directly from `syntax_markdown_*` (with `text_primary`/`border` fallbacks). One visual vocabulary across source and preview; HC presets tune both together.
- **Suggested remediation:** Replace generic heading/code rules with token fields; verify contrast on `#FFFFFF` HC Light and `#000000` HC Dark editor backgrounds.
- **Tests that would prove fix:** Snapshot or string assert that `apply_theme` default stylesheet contains `tokens.syntax_markdown_heading` when non-empty; four-theme manual parity check source vs preview heading color.
- **Handoff overlap:** TN-EDIT-SYNTAX, none

---

### TN-EDIT-MD-6 — Preview refresh loop does not re-render after theme change

- **Persona:** TN-EDIT-MD
- **Severity:** STRUCTURAL
- **Evidence:** `app/editors/markdown_preview_widget.py:55-105` — `apply_theme` updates widget stylesheet and `document().setDefaultStyleSheet` only. `app/editors/markdown_editor_pane.py:136-139` — no `schedule_preview_render()` after theme apply. Qt `QTextDocument` default stylesheet changes do not reliably repaint existing Markdown until content is set again; `show_preview_paused_message` embeds inline colors (`:129-139`) that freeze at render time. `app/shell/shell_theme_workflow.py:194` — theme switches call `apply_markdown_themes` globally without follow-up render.
- **Code-judo alternative:** After preview `apply_theme`, if pane mode is PREVIEW or SPLIT and preview is not paused, call `render_markdown(current_text)` (or pane-level `schedule_preview_render()`). Keeps theme + refresh atomic.
- **Suggested remediation:** `MarkdownEditorPane.apply_theme` ends with conditional `schedule_preview_render()`; preview widget optionally re-applies paused HTML from stored counts when tokens change.
- **Tests that would prove fix:** Render preview → switch dark→HC Dark → heading/link colors update without manual Refresh; theme workflow test asserts render invoked after `apply_markdown_themes`.
- **Handoff overlap:** none

---

### TN-EDIT-MD-7 — Local file links drop fragment; preview navigation incomplete at boundary

- **Persona:** TN-EDIT-MD
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/markdown_rendering.py:112-117` — `resolve_markdown_link` returns `LINK_KIND_LOCAL_FILE` with `anchor` populated. `app/editors/markdown_preview_widget.py:150-153` — `_handle_anchor_clicked` calls `local_link_callback(resolved.target_path)` only; `resolved.anchor` ignored. Factory wires callback to `open_file_in_editor(linked_path, preview=False)` (`editor_tab_factory.py:187-189`) with no line/anchor argument.
- **Code-judo alternative:** Extend `LocalLinkCallback` to `(path, anchor | None)` or reuse `open_file_at_line` from `editor_tab_workflow.py:314-322`. Same contract as in-doc `#anchor` handling (`:147-148`).
- **Suggested remediation:** Pass anchor through callback; factory opens file then `go_to_line` or scroll if anchor maps to heading id (future: shared anchor resolver).
- **Tests that would prove fix:** Click `[section](other.md#section)` invokes callback with anchor; integration opens target tab at section.
- **Handoff overlap:** none

---

### TN-EDIT-MD-8 — Editor-layer split is the right code-judo move (positive control)

- **Persona:** TN-EDIT-MD
- **Severity:** NICE-TO-HAVE
- **Evidence:** `app/editors/markdown_rendering.py:31-117` — pure path sniffing, link resolution, Qt capability probes; no Qt widgets. `app/editors/markdown_editor_pane.py:31-121` — composite owns layout/mode/debounce; injects existing `CodeEditorWidget` without forking it. `app/editors/markdown_preview_widget.py:27-116` — preview-only QTextBrowser wrapper. Total **485 LOC** across three focused modules; no file approaches 1k. `is_markdown_path` / `qt_markdown_supported` gate at factory (`editor_tab_factory.py:182`) keeps code editor free of markdown branches.
- **Code-judo alternative:** Preserve this boundary; push remaining shell spaghetti (TN-EDIT-MD-1/2/3) outward rather than inlining markdown conditionals into `CodeEditorWidget` or `editor_tab_workflow` inline blocks.
- **Suggested remediation:** Document in ARCHITECTURE §12.4 that Markdown tabs are composite content widgets, not editor mixins; use as template for future structured editors (JSON schema view, etc.).
- **Tests that would prove fix:** Existing unit tests (`test_markdown_rendering.py`, `test_markdown_editor_pane.py`) and integration (`test_markdown_viewer_integration.py`) remain green after shell refactors.
- **Handoff overlap:** §12.4, TN-EDIT-CORE

---

## Cross-cutting notes

| Theme | Status in slice |
|-------|-----------------|
| Split from code editor | **Good** — injected `CodeEditorWidget`, three-module extraction, factory gate |
| Dual-pane ownership | **Weak** — parallel registries, duplicate release, rename orphan |
| Preview refresh | **Mostly good** — 200 ms debounce, 300k char guard, force Refresh; theme change gap |
| Four-theme tokens | **Partial** — preview body uses core tokens; toolbar/status omitted; `syntax_markdown_*` unused in preview |
| 1k-line rule | Markdown modules well under budget; `editor_tab_workflow.py` at **1,013 LOC** before further markdown menu growth (TN-EDIT-SHELL-TAB) |
| Hard-cutover | Factory path is clean; shell rename/teardown needs cutover unwrap |

---

## Verdict

**REJECT** — Editor modules (`markdown_*`) are thermo-clean enough to ship as a pattern, but the slice fails the approval bar on **shell dual-ownership spaghetti** (TN-EDIT-MD-1, TN-EDIT-MD-2), **incomplete four-theme surface** (TN-EDIT-MD-4, TN-EDIT-MD-5), and **non-atomic theme/preview refresh** (TN-EDIT-MD-6). Treat TN-EDIT-MD-1 through TN-EDIT-MD-4 and TN-EDIT-MD-6 as P1 before Editors Wave 1 markdown work expands; TN-EDIT-MD-3, TN-EDIT-MD-5, TN-EDIT-MD-7 as P2 polish. Positive control TN-EDIT-MD-8 should be preserved through refactors.
