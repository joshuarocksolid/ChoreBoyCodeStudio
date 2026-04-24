# 5) Editing and Navigation

This chapter helps you move faster inside code and text files.

## Find and replace in current file

Use:

- `Ctrl+F` to find
- `Ctrl+H` to replace

Use this for focused edits in one file.

## Find in files (project-wide)

Use `Ctrl+Shift+F`.

This opens the project-wide search panel and scans files for your text.
Click a result to preview, and double-click to open permanently.

![Figure 9 — Find in Files search panel](../screenshots/manual_09_find_in_files.png)

## Quick Open

Use `Ctrl+P`.

Type part of a filename and choose from matches.
This is usually faster than browsing deep folders.

## Go to line

Use `Ctrl+G`, type line number, press Enter.

Helpful for traceback navigation and code review.

## Go to definition and outline

Useful commands:

- `F12` -> Go to Definition
- The **Outline** panel below the project tree in the Explorer sidebar shows a
  live, hierarchical view of classes, functions, methods, properties, and
  constants in the active Python file. Click a symbol to jump to it. The panel
  follows your cursor by highlighting the innermost containing symbol. The
  outline survives mid-edit syntax errors thanks to tree-sitter's incremental
  parser.
- `Ctrl+R` -> **Go to Symbol in File** opens a quick-pick listing every symbol
  in the current Python file. Type to filter by name or qualified name; the
  editor scrolls live as you move through matches. Press `Enter` to commit, or
  `Esc` to cancel and return to your original cursor.

Use these when moving between related functions/classes.

## Preview tabs (important behavior)

Code Studio supports preview tabs:

- single-click file -> preview tab (reused by next single-click),
- double-click file -> permanent tab,
- editing a preview tab promotes it to permanent.

This keeps tab clutter low while browsing.

## Edit reliability tips

1. Save often (`Ctrl+S`).
2. Use Save All before major runs.
3. Keep tabs organized: close files you are done with.
4. Use Quick Open for fast file switching.

