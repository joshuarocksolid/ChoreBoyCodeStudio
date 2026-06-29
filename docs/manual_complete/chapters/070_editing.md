# Editing Files

This chapter covers the editor itself: tabs, saving, indentation, comments, zoom, and
the editing helpers built into ChoreBoy Code Studio.

## Tabs and the editor area

Open files appear as tabs across the top of the editor. Each tab shows the file name, a
close button, and a small marker when the file has unsaved changes.

![A Python file open in the editor, with syntax highlighting and the Outline panel populated](../screenshots/070_editor_code.png)

### Preview tabs

To keep your workspace tidy, the editor uses **preview** tabs:

- A **single click** on a file in the Explorer opens it in a preview tab (shown in
  italics). Opening another file in preview replaces it, so casual browsing never piles
  up dozens of tabs.
- A **double click**, or **editing the file**, promotes the preview into a permanent
  tab.

You can turn preview tabs off in **Settings > Editor** (`enable_preview`). When off,
every file opens in a permanent tab.

## Saving your work

| Command | Shortcut | Effect |
| --- | --- | --- |
| Save | `Ctrl+S` | Save the active file. |
| Save All | `Ctrl+Shift+S` | Save every modified file. |

When you save, the modified marker clears and the status bar shows the file as saved.

### Autosave drafts and recovery

ChoreBoy Code Studio continuously protects your unsaved work with **autosave drafts**.
Drafts are written to a recovery store, debounced so they do not churn the disk on every
keystroke. They do **not** overwrite your source file.

- If the application closes unexpectedly, you can recover your unsaved text the next time
  you open the file (see "Local History & recovery").
- You can also enable **File > Auto Save** to save automatically.

> [!IMPORTANT] Saving is always authoritative. **Save** writes the file and records a
> Local History checkpoint; a draft never silently replaces what you explicitly saved.

## Indentation

The editor respects per-project indentation settings (see "Every settings tab & field"):

- **Indent style** — spaces or tabs.
- **Indent size** / **Tab width** — how wide indentation is.
- **Detect indentation from file** — match the existing file's style automatically.

The status bar shows the active indentation, for example `Spaces: 4 (auto)`.

Use these commands while editing:

| Command | Shortcut | Effect |
| --- | --- | --- |
| Indent | `Tab` | Increase indentation of the selected lines. |
| Outdent | `Shift+Tab` | Decrease indentation. |
| Toggle Comment | `Ctrl+/` | Comment or uncomment the selected lines. |

## Undo and redo

| Command | Shortcut |
| --- | --- |
| Undo | `Ctrl+Z` |
| Redo | `Ctrl+Shift+Z` |

## Zooming the editor font

| Command | Shortcut |
| --- | --- |
| Zoom In | `Ctrl+=` |
| Zoom Out | `Ctrl+-` |
| Reset Zoom | `Ctrl+0` |

Zoom changes the editor font size for comfortable reading; it does not change your saved
settings permanently unless you adjust the font size in Settings.

## Pasting flattened Python code

Sometimes code copied from a PDF or web page loses its indentation, leaving everything at
the left margin. ChoreBoy Code Studio can repair this:

- If you paste flattened Python, an inline hint offers **Re-indent**, **Always**, and a
  dismiss button.
- You can also right-click and choose **Paste and Re-indent (Flat Python)**
  (`Ctrl+Alt+V`), or select flattened lines and choose **Re-indent Selection (Flat
  Python)**.
- A single **Undo** reverts the re-indent to the literal paste.

Turn on automatic repair (for high-confidence cases) with **Settings > Editor >
Auto re-indent flat-Python pastes**.

## Syntax highlighting

The editor highlights Python and many other languages (JSON, TOML, INI/desktop, HTML,
CSS, Markdown, YAML, JavaScript, Bash, SQL, XML). Highlighting is role-aware: imports,
parameters, class names, and constructors are coloured distinctly.

- Override the language for a file with **Tools > Set Language Mode...**.
- Return to automatic detection with **Tools > Clear Language Override**.
- Inspect how a token is highlighted with **Tools > Inspect Token Under Cursor**.

> [!NOTE] For very large files, the editor automatically reduces highlighting work to
> keep typing responsive. This is configurable in **Settings > Intelligence**.

## Working with several files at once

- Open as many files as you like; each gets a tab.
- Close a tab with `Ctrl+W` or its close button.
- Use `Ctrl+P` (Quick Open) to jump to a file without hunting in the tree.
- The single preview tab keeps casual browsing from cluttering your tabs — only files you
  edit or double-click become permanent.

## The status bar while editing

While a file is active, the status bar shows, on the right:

- the indentation in use (for example, `Spaces: 4 (auto)`),
- the active file name,
- the cursor's line and column,
- whether the file is **saved** or **modified**.

This is the quickest way to confirm a save succeeded or to read your cursor position when
following a traceback.

## What happens when you save

A save does more than write the file:

1. The buffer is written to disk and the modified marker clears.
2. A **Local History checkpoint** is recorded, so you can compare or restore this version
   later.
3. If you enabled them, **format-on-save** and **organize-imports-on-save** run — but if
   they fail, your text is still written and you get a warning (save reliability wins).

See "Local History & recovery" and "Python formatting & imports".

## If a file changes outside the editor

If a file you have open changes on disk (for example, you edited it elsewhere), Code
Studio detects this and lets you reload it, recording a checkpoint when you do — so you
never silently lose either version.

## Where to go next

- Find and jump around your code in "Navigation & search".
- Get completion, hover, and rename in "Code intelligence".
