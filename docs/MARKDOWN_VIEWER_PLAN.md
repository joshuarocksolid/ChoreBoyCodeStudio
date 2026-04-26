# Markdown Viewer Feature Plan

## Purpose

ChoreBoy Code Studio already opens `.md` files as source text and has
tree-sitter Markdown highlighting, but many product, architecture, manual, and
plugin documents are authored in Markdown. Users need a first-class way to read
those files as formatted documents without leaving the editor.

The target experience is similar to modern code editors: a Markdown file opens
inside the normal editor tab area, and the user can switch between raw Markdown,
rendered Preview, and an optional split view.

## Current Codebase Fit

The existing architecture is a good foundation for this feature.

- The editor shell is a Qt/PySide2 desktop app launched inside FreeCAD AppRun.
- File tabs are owned by `EditorManager` and materialized by
`EditorTabFactory`.
- The central workspace is currently a `QTabWidget` where each file tab contains
one `CodeEditorWidget`.
- `EditorWorkspaceController` maps file paths to `CodeEditorWidget` instances
and owns buffer revision counters used by diagnostics and intelligence.
- Markdown syntax highlighting already exists through the tree-sitter pipeline:
`app/treesitter/language_specs.py`, `app/treesitter/markdown_lexical.py`, and
the syntax token palette.
- The app already uses theme-aware rich text in `QTextBrowser` for help and
runtime explanation dialogs.

The important constraint is that the editor process must not execute arbitrary
project code. Markdown preview must render document text only. It should not run
scripts, execute commands from code fences, or depend on external browser or CLI
processes.

## External Editor Research

### Cursor and VS Code

VS Code's built-in Markdown workflow is the closest model to Cursor's behavior.
It supports:

- source/preview toggle with `Ctrl+Shift+V`;
- side-by-side editor and preview with `Ctrl+K V`;
- live preview updates as the source changes;
- synchronized scrolling between source and preview;
- tab/context menu commands and command palette commands;
- security controls that disable script execution and restrict remote content.

Source: [https://code.visualstudio.com/docs/languages/markdown](https://code.visualstudio.com/docs/languages/markdown)

Cursor inherits much of this VS Code model. Cursor users expect a visible preview
affordance for Markdown files and the `Ctrl+Shift+V` shortcut, with a simple
"Markdown vs Preview" mental model.

Cursor community references:

- [https://forum.cursor.com/t/markdown-file-preview-button-disappeared/30315/9](https://forum.cursor.com/t/markdown-file-preview-button-disappeared/30315/9)
- [https://forum.cursor.com/t/markdown-preview-mode-without-splitting-screen/141637](https://forum.cursor.com/t/markdown-preview-mode-without-splitting-screen/141637)

### JetBrains IDEs

JetBrains IDEs expose a polished Markdown editor with:

- a top-right control to choose Editor, Preview, or Editor and Preview;
- vertical or horizontal split preview layout;
- default preview layout settings;
- synchronized scrolling;
- theme-consistent preview styles;
- optional advanced Markdown assistance such as tables, links, diagrams, and
formatting.

Source: [https://www.jetbrains.com/help/idea/2025.3/markdown.html](https://www.jetbrains.com/help/idea/2025.3/markdown.html)

### Qt/PySide2 Rendering Capabilities

Qt 5.14+ text widgets support Markdown rendering through
`QTextEdit.setMarkdown()` / `QTextBrowser.setMarkdown()`. Qt's rich text widgets
render through `QTextDocument`, which supports a useful but limited HTML 4
subset. This is lighter and safer than embedding Chromium/WebEngine.

Sources:

- [https://doc.qt.io/archives/qtforpython-5.14/PySide2/QtWidgets/QTextBrowser.html](https://doc.qt.io/archives/qtforpython-5.14/PySide2/QtWidgets/QTextBrowser.html)
- [https://doc.qt.io/qt-5.15/richtext-html-subset.html](https://doc.qt.io/qt-5.15/richtext-html-subset.html)

Because ChoreBoy Code Studio runs under bundled PySide2, the implementation must
include a small runtime-parity check that confirms `setMarkdown()` exists in the
target FreeCAD AppRun runtime before depending on it.

## UX Goals

The viewer should feel like a native part of the editor, not a separate help
window.

- Markdown files open in the normal tab strip.
- A compact mode control appears for Markdown tabs only.
- Modes are easy to understand: `Markdown`, `Preview`, `Split`.
- The rendered preview uses the current app theme and remains readable in light
and dark mode.
- Preview updates automatically after edits, with a small debounce.
- The user can copy text from Preview.
- Links to local files should be handled inside Code Studio when possible.
- External links should be visibly distinct and should not launch surprise
network-dependent workflows on ChoreBoy.
- Large files must not freeze the UI.

## Implementation Options

### Option 1: Native Qt Markdown Preview With `QTextBrowser`

Use a `QTextBrowser`-based preview widget and feed it Markdown through
`setMarkdown()` when available. Keep the existing `CodeEditorWidget` as the
source editor, and wrap Markdown tabs in a small composite widget that can show
source-only, preview-only, or split.

Pros:

- Lowest dependency risk.
- Runs in-process inside the existing PySide2 runtime.
- No browser engine or subprocess required.
- Aligns with existing `QTextBrowser` usage in help/runtime dialogs.
- Easy to theme from `ShellThemeTokens`.
- Good enough for README/manual-style documents.

Cons:

- Rendering fidelity is not full GitHub/Chromium-level HTML.
- Advanced Markdown extensions such as Mermaid and KaTeX are out of scope.
- Scroll synchronization is approximate unless we add heading/anchor mapping.

### Option 2: Pure-Python Markdown Parser to Sanitized HTML

Vendor a Python 3.9-compatible Markdown parser such as `markdown-it-py` or
`mistune`, render Markdown to sanitized HTML, and display that HTML in
`QTextBrowser`.

Pros:

- Better CommonMark/GFM control than a hand-rolled parser.
- Can add extensions incrementally.
- Still avoids WebEngine.

Cons:

- Adds a vendored dependency and packaging surface.
- Still constrained by Qt's HTML subset.
- Requires explicit sanitization and resource policy.
- More code than Option 1 for limited user-visible gain at MVP.

### Option 3: `QWebEngineView` / Browser-Based Preview

Render Markdown to HTML/CSS and show it in a Chromium-backed web view.

Pros:

- Best visual fidelity.
- Supports richer CSS and future diagram/math renderers.
- Similar technology model to VS Code's preview.

Cons:

- Highest runtime risk on ChoreBoy.
- May not be available in the bundled PySide2/FreeCAD runtime.
- Larger memory footprint.
- Larger security surface.
- More packaging and runtime-parity work.

### Option 4: Separate Read-Only Preview Tab

Opening a Markdown preview creates a second tab such as `README.md [Preview]`.

Pros:

- Smaller immediate layout change.
- Easy to implement as a new widget type in `QTabWidget`.

Cons:

- Fights the current one-path-one-tab model.
- Makes tab management noisy.
- Harder to keep source and preview paired.
- Less like the user's requested Cursor-style toggle.

### Option 5: External Viewer / Help Dialog

Open Markdown files in a separate dialog using the existing help dialog
renderer.

Pros:

- Smallest implementation.
- Reuses existing code directly.

Cons:

- Not an editor-integrated workflow.
- Poor for editing and previewing side by side.
- Current `markdown_to_html()` helper intentionally supports only a small
Markdown subset.
- Does not meet the requested modern code-editor UX.

## Recommended Approach

Use Option 1 as the MVP: a native Qt Markdown preview integrated into the
existing editor tab system.

Specifically:

1. Add a reusable `MarkdownPreviewWidget` backed by `QTextBrowser`.
2. Add a `MarkdownEditorPane` composite for Markdown tabs:
  - existing `CodeEditorWidget` for source;
  - `MarkdownPreviewWidget` for rendered output;
  - a `QSplitter` for split mode;
  - a small mode toolbar with `Markdown`, `Preview`, and `Split`.
3. Keep `EditorManager` and `EditorWorkspaceController` focused on the source
  buffer. The workspace controller should still register the underlying
   `CodeEditorWidget`, so save, diagnostics, outline, local history, and
   intelligence keep working.
4. Use Qt's native Markdown renderer after a runtime-parity check confirms
  support in FreeCAD AppRun.
5. Defer WebEngine, Mermaid, KaTeX, export-to-PDF, and full GFM parity until
  there is evidence users need them.

This is optimal because it respects the project's architecture: small modules,
no new process model, no hidden state, no terminal dependency, no user-code
execution, and a UI that can be implemented as a thin vertical slice.

## Proposed User Experience

### Tab Behavior

- `.md`, `.markdown`, `.mkd`, and optionally `.mdx` open as Markdown-capable
tabs.
- The tab's source editor remains the canonical editable buffer.
- The rendered preview is derived from the current buffer, not the last saved
disk contents.
- Dirty state, local history, save, find, and run-state behavior remain tied to
the source buffer.

### Mode Control

For Markdown tabs, show a compact segmented control near the top-right of the
editor area:

```text
[ Markdown ] [ Preview ] [ Split ]
```

Recommended defaults:

- First release default: `Preview` for Markdown files opened normally.
- If the user edits or switches to `Markdown`, remember that mode globally for
the session.
- Add a persisted setting later: `markdown.default_preview_mode`.

The wording should favor user clarity over implementation jargon. `Markdown`
means raw source. `Preview` means rendered document. `Split` means source and
preview side by side.

### Shortcuts and Commands

Add commands:

- `Markdown: Show Source`
- `Markdown: Show Preview`
- `Markdown: Show Split View`
- `Markdown: Toggle Preview`

Suggested shortcuts:

- `Ctrl+Shift+V`: toggle `Markdown` / `Preview` for the active Markdown tab.
- `Ctrl+K, V`: show split view for the active Markdown tab.

These match common VS Code/Cursor muscle memory without disrupting the existing
editor shortcuts.

### Theme

Preview styling must derive from `ShellThemeTokens`:

- background: `editor_bg`;
- primary text: `text_primary`;
- muted text: `text_muted`;
- borders/rules: `border`;
- code background: `badge_bg` or a dedicated preview code token;
- links/accent: `accent`.

The preview must be checked in both light and dark modes.

### Links and Images

Initial behavior:

- Relative Markdown links to local files should resolve relative to the current
Markdown file.
- Clicking a local `.md` link should open that file in Code Studio.
- Clicking a local source file should open it in Code Studio.
- Image paths should resolve relative to the current Markdown file when
supported by `QTextBrowser`.
- External links should use the existing desktop URL handling only after clear
affordance. ChoreBoy is LAN/offline-first, so the preview must not assume
internet access.

### Safety

- Do not execute fenced code blocks.
- Do not run shell commands embedded in Markdown.
- Do not enable JavaScript.
- Do not depend on remote assets.
- Sanitize or ignore raw HTML if the native renderer permits unsafe constructs.
If `QTextDocument.MarkdownNoHTML` is available through PySide2, prefer it for
MVP.

## Architecture Design

### New Modules

Add:

```text
app/editors/markdown_preview_widget.py
app/editors/markdown_editor_pane.py
app/editors/markdown_rendering.py
```

Suggested responsibilities:

- `markdown_rendering.py`
  - file-extension helpers;
  - runtime capability probe for Qt Markdown support;
  - optional Markdown feature flags;
  - HTML/style helpers if needed.
- `markdown_preview_widget.py`
  - owns the `QTextBrowser`;
  - applies theme;
  - renders Markdown text;
  - handles local link activation;
  - exposes scroll-position helpers for later sync work.
- `markdown_editor_pane.py`
  - owns source editor + preview widget + mode toolbar;
  - switches modes;
  - debounces render updates;
  - applies theme to both child widgets;
  - exposes the source `CodeEditorWidget` for existing editor workflows.

### Existing Modules to Touch

- `app/shell/editor_tab_factory.py`
  - instantiate `MarkdownEditorPane` for Markdown paths;
  - keep the underlying `CodeEditorWidget` registered with
  `EditorWorkspaceController`;
  - add the composite pane to `QTabWidget` instead of adding the source editor
  directly.
- `app/shell/main_window_panels.py`
  - no large structural change should be required if the mode toolbar lives
  inside `MarkdownEditorPane`.
- `app/shell/main_window.py`
  - add command handlers for Markdown preview modes;
  - route active Markdown pane mode changes;
  - apply theme changes to open Markdown preview panes.
- `app/shell/menus.py`, `app/shell/menu_wiring.py`,
`app/shell/shortcut_preferences.py`
  - add commands and shortcuts.
- `app/shell/settings_models.py`, `app/core/constants.py`,
`app/shell/settings_dialog.py`
  - add settings only after MVP behavior is proven:
  `markdown.default_mode`, `markdown.sync_scroll`, and possibly
  `markdown.allow_raw_html`.
- `app/shell/style_sheet_sections_workspace.py` or a new stylesheet section
  - style preview toolbar and browser.
- `docs/ACCEPTANCE_TESTS.md`
  - add manual validation for Markdown preview once the feature is implemented.

### State Model

Keep Markdown preview mode as UI state, separate from file content state.

MVP state:

- active mode per open Markdown tab;
- last session-level mode;
- render debounce timer per Markdown tab.

Future persisted state:

- global default Markdown mode;
- per-file mode restoration if session restore becomes first class;
- preview split ratio.

Do not store preview state in project metadata. It is editor UI preference, not
project identity.

## Step-by-Step Implementation Plan

### Phase 0: Runtime Spike

1. In the FreeCAD AppRun runtime, verify:
  - `QTextBrowser.setMarkdown` exists;
  - `QTextDocument.MarkdownDialectGitHub` and `MarkdownNoHTML` availability;
  - basic rendering for headings, lists, fenced code blocks, tables, links, and
  images;
  - light/dark palette behavior.
2. Document the runtime result in the implementation PR or update this file.
3. If native Markdown is missing, choose Option 2 before writing UI code. Do not
  build a permanent dual-renderer fallback chain.

### Phase 1: Core Preview Widget

1. Create `app/editors/markdown_rendering.py`.
2. Add `is_markdown_path(path: str) -> bool`.
3. Add `qt_markdown_supported() -> bool`.
4. Create `MarkdownPreviewWidget`.
5. Render Markdown from a string using native Qt Markdown.
6. Apply theme tokens to the widget and document.
7. Add local link activation hooks, initially opening local files through a
  callback supplied by the shell.
8. Add focused unit tests for pure helpers only. Avoid brittle UI snapshot tests.

### Phase 2: Markdown Tab Composite

1. Create `MarkdownEditorPane`.
2. Move source-editor construction behind a helper so `EditorTabFactory` can
  create either:
  - a plain `CodeEditorWidget` for normal files;
  - a `MarkdownEditorPane` containing a `CodeEditorWidget` for Markdown files.
3. Add source, preview, and split modes.
4. Add a `QButtonGroup` or equivalent segmented toolbar.
5. Add a `QTimer` render debounce, initially around 150-250 ms.
6. Ensure `textChanged` still updates `EditorManager`, local history, save state,
  diagnostics, outline, and status as it does today.
7. Ensure closing a tab deletes both the composite pane and the source editor
  without leaking widgets.

### Phase 3: Shell Integration

1. Update `EditorTabFactory._materialize_opened_editor_tab()` to detect Markdown
  paths.
2. Register the underlying source editor with `EditorWorkspaceController`.
3. Add the tab content widget as the composite pane for Markdown files.
4. Track open Markdown panes by path, or provide a lookup from the tab widget.
5. Add handlers in `MainWindow`:
  - show source;
  - show preview;
  - show split;
  - toggle preview.
6. Hide or disable Markdown commands when the active tab is not Markdown.
7. Confirm existing features still target the source editor via
  `_editor_widgets_by_path`.

### Phase 4: Commands, Menus, and Shortcuts

1. Add command IDs for Markdown preview actions.
2. Add menu entries under `View` or `Edit`, grouped as Markdown actions.
3. Add `Ctrl+Shift+V` for toggle preview.
4. Add `Ctrl+K, V` for split preview if it does not conflict.
5. Add tab context-menu entries:
  - `Open Markdown Preview`;
  - `Open Markdown Split View`;
  - `Show Markdown Source`.
6. Add command status updates so unavailable actions are disabled instead of
  failing silently.

### Phase 5: Styling and Theme

1. Add preview toolbar/browser object names.
2. Add stylesheet rules based on `ShellThemeTokens`.
3. Ensure code blocks, inline code, block quotes, headings, tables, and links are
  readable in light and dark mode.
4. Re-apply theme to open Markdown panes when the theme changes.
5. Keep colors semantic; avoid one-theme hardcoded values except white text on
  accent buttons where already established.

### Phase 6: Local Links and Resource Loading

1. Resolve relative links against the Markdown file's parent directory.
2. Route local file links through the editor open flow.
3. For anchor links within the same document, scroll the preview when feasible.
4. For external links, use an explicit policy:
  - either open via `QDesktopServices` with normal system handling;
  - or show a confirmation/tooltip if product wants stricter offline behavior.
5. Add guardrails around missing images and broken local links so failures are
  visible but not disruptive.

### Phase 7: Scroll Sync

1. Start with preview updates only; do not block MVP on perfect scroll sync.
2. Add source-to-preview approximate sync using cursor block ratio or heading
  positions.
3. Add preview-to-source sync only if local anchor/click mapping is stable.
4. Add a user setting for sync scroll after the interaction is proven useful.

### Phase 8: Performance Guardrails

1. Debounce render updates.
2. Skip live preview for very large Markdown files above a threshold, or require
  manual refresh.
3. Surface a friendly message when preview is paused for file size.
4. Reuse the existing highlighting thresholds as guidance:
  - reduced behavior near large text thresholds;
  - no expensive full-document work on every keystroke.
5. Log render timing at debug/telemetry level if performance issues appear.

### Phase 9: Tests and Acceptance

Write tests only where they protect real behavior:

1. Unit tests for Markdown path detection and mode state transitions.
2. Unit tests for local link resolution.
3. A Qt smoke test that creates `MarkdownEditorPane`, switches modes, and ensures
  the source editor remains accessible.
4. Integration test for opening a Markdown file and preserving save/dirty state
  through the source editor.
5. Manual acceptance additions:
  - open `README.md`;
  - switch `Markdown` / `Preview` / `Split`;
  - edit source and see preview update;
  - switch light/dark themes;
  - click a local `.md` link;
  - open a large Markdown document and verify the UI remains responsive.

### Phase 10: Documentation

1. Update `docs/ACCEPTANCE_TESTS.md`.
2. Update the user manual chapter for editing/navigation.
3. Add shortcut references to the shortcuts chapter.
4. Mention Markdown preview limitations clearly:
  - no script execution;
  - no Mermaid/math in MVP;
  - rendering may not exactly match GitHub.

## Risks and Mitigations

### Qt Markdown Runtime Mismatch

Risk: The development runtime supports `setMarkdown()` but ChoreBoy production
does not.

Mitigation: complete Phase 0 before implementation cutover. If unsupported,
choose a pure-Python parser path before wiring UI.

### Widget Ownership Leaks

Risk: Markdown tabs use a composite widget while existing cleanup releases only
the source editor.

Mitigation: make the composite pane own its child widgets and add an explicit
tab-content release path in the tab factory or shell controller.

### Preview Rendering Freezes

Risk: large docs cause re-render jank.

Mitigation: debounce, size thresholds, manual refresh mode, and telemetry.

### Theme Regressions

Risk: preview HTML is readable in one theme but poor in another.

Mitigation: derive colors from `ShellThemeTokens` and manually validate both
light and dark modes.

### Security Drift

Risk: future richer rendering accidentally permits script execution or remote
content assumptions.

Mitigation: make the initial policy explicit: no JavaScript, no command
execution, no remote dependency. Treat richer features as separate decisions.

## Final Decision

Build a native, Qt-backed Markdown preview integrated into the existing tab
system. Keep the source editor as the canonical buffer, add a per-Markdown-tab
mode control for `Markdown`, `Preview`, and `Split`, and use the app's theme
tokens for a clean light/dark UI.

This gives users the modern Markdown reading experience they expect while
staying aligned with ChoreBoy Code Studio's strongest architectural rules:
in-process PySide2 UI, filesystem-first behavior, no terminal dependency, no
untrusted execution, small modules, and incremental implementation slices.