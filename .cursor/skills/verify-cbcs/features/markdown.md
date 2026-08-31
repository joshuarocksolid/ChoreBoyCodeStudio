# Markdown

`.md` tabs open in split view (source + preview). The user can switch source-only, preview-only, or split, follow in-app links, and pause live preview on large files.

Owns AT-102, AT-103.

## Sub-features

- `md-open-split` opens a new `.md` tab in Split.
- `md-modes` switches Markdown / Preview / Split from the pane toolbar or **View**.
- `md-preview` renders headings, lists, tables, and code.
- `md-links` open local links in-app.
- `md-large` pauses live preview on large files.

## How to get to it (user POV)

- Open any `.md` file.
- **View → Markdown: Toggle Preview** (Ctrl+Shift+V), **Show Source**, **Show Preview**, **Show Split** (Ctrl+K, V).
- Tab context menu Markdown modes.
- Pane toolbar `#shell.markdownEditorPane.modeButton.*`.

## Driving it with control-cbcs

Preconditions:

- Project contains `README.md` or you created `notes.md` with a heading and a list.
- Doctor passed.

- **Open.** Open the `.md` file from the tree. `#shell.markdownEditorPane` is present. Split is the default for a new tab.
- **Preview visible.** `#shell.markdownPreview.browser` is visible in Split or Preview mode.
- **Source only.** `control-cbcs trigger "$SID" shell.action.view.markdownShowSource`. Preview hides; source stays editable.
- **Preview only.** `control-cbcs trigger "$SID" shell.action.view.markdownShowPreview`. Source hides.
- **Split.** `control-cbcs trigger "$SID" shell.action.view.markdownShowSplit`. Both visible. Shot `markdown-split`.
- **Edit.** Type a new heading in source. Preview updates on `textChanged` (~200 ms), not on Save. Disk matches only after Save.
- **Proof.** Shot of Split with a visible heading in the preview, plus the saved `.md` on disk.

## Gotchas

- Live preview pauses on large files. A Paused status is success, not a blank preview bug.
- **View → Markdown: Toggle Preview** from Split goes to Preview-only and never back to Split. Use **Show Split** to return.
- Local links stay in-app; do not expect a system browser.
- Do not open the same `.md` twice as duplicate tabs — the editor should focus the existing tab.
