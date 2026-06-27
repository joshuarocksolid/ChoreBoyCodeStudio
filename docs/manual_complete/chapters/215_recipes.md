# Common Task Recipes

This chapter is a quick-reference of short, practical recipes for everyday tasks. Each
recipe is two or three steps and links to the chapter with full detail.

## Projects & files

**Create a new project**
File > New Project from Template... → pick a template → name + location. (See "Projects".)

**Open an existing project**
File > Open Project... (`Ctrl+O`) → choose the folder.

**Open a recent project**
File > Open Recent → pick it; or use the welcome screen's recent list.

**Open a folder that wasn't made here**
File > Open Project... → select it; `cbcs/project.json` is created automatically.

**Rename a file**
Right-click it in the Explorer → Rename... (`F2`).

**Delete a file safely**
Right-click → Move to Trash (`Del`). It is recoverable.

**Move a file into a folder**
Drag it onto the folder, or Cut (`Ctrl+X`) and Paste (`Ctrl+V`).

**Set which file runs as the project**
Right-click the file → Set as Entry Point.

**Make `src/` imports resolve**
Right-click the `src` folder → mark it as a Sources Root.

## Editing

**Open a file fast**
`Ctrl+P`, type part of the name, Enter.

**Find text in this file**
`Ctrl+F`. Toggle case (**Aa**), whole word (**W**), or regex (**.\***).

**Replace text in this file**
`Ctrl+H`. Undo with `Ctrl+Z` if needed.

**Search the whole project**
`Ctrl+Shift+F`, type the query, click a result to jump.

**Jump to a line**
`Ctrl+G`, type the number.

**Comment/uncomment lines**
Select them, `Ctrl+/`.

**Fix code pasted from a PDF (lost indentation)**
Right-click → Paste and Re-indent (Flat Python) (`Ctrl+Alt+V`).

**Format the file**
Tools > Format Current File (Black).

**Sort imports**
Tools > Organize Imports.

## Running & debugging

**Run the file I'm editing**
`F5`.

**Run the project**
`Shift+F5`.

**Run with custom arguments**
Run > Run With Arguments... (`Ctrl+Shift+A`).

**Stop a run**
`Shift+F2`, or close the program's window.

**Pause at a line and inspect**
Click the gutter to set a breakpoint (`F9`), then Debug (`Ctrl+F5`).

**Try a quick expression**
Use the Python Console tab; type at the `>>>` prompt.

## Code intelligence

**Go to a definition**
Cursor on the symbol, `F12`.

**Find all uses**
Cursor on the symbol, `Shift+F12`.

**Rename across the project**
Cursor on the symbol, `F2`, review the preview, apply.

**See documentation**
Cursor on the symbol, `Ctrl+Shift+I`.

## Tests

**Discover tests**
View > Show Test Explorer (`Ctrl+Shift+X`).

**Run all tests**
`Ctrl+Shift+T`, or the Test Explorer's Run All.

**Run the test at the cursor**
Run > Run Test at Cursor.

**Re-run only failures**
Test Explorer's Rerun Failed.

## Appearance & settings

**Switch theme**
View > Theme → pick a mode.

**Change a keyboard shortcut**
File > Settings... > Keybindings.

**Make a setting apply to one project only**
File > Settings... → set scope to Project → change → Save.

**Change indentation**
File > Settings... > Editor > Indent style / Indent size.

## Dependencies, plugins, packaging

**Add a Python package from a file**
Tools > Add Dependency... → choose a `.whl`, `.zip`, or folder.

**Manage plugins**
Tools > Plugin Manager...

**Disable a plugin for one project**
Plugin Manager → select it → Disable In Project.

**Package for another machine**
Package Project (toolbar) → choose an output folder outside the project.

## Recovery & support

**Recover unsaved work after a crash**
File > Open Recovery Center...

**Restore an earlier saved version**
Right-click the file → Local History...

**Recover a deleted file**
File > Open Global History...

**See what's wrong with the runtime/project**
Tools > Runtime Center, then Tools > Project Health Check.

**Get help**
Tools > Generate Support Bundle, then share the archive.

## Where to go next

- Full detail for any recipe is in its feature chapter (linked throughout).
- A printable one-pager is in Appendix A, "Quick-reference cheat sheet".
