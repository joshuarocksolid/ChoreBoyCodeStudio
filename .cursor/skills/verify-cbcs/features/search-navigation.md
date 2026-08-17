# Search and navigation

Find and replace in the current file, search the project, jump to a file or symbol, and follow definitions / references / rename.

## Sub-features

- `find-in-file` opens `#shell.findBar` (Ctrl+F) and highlights matches.
- `replace-in-file` replaces one or all (Ctrl+H).
- `find-in-files` uses the Search activity (`#shell.searchSidebar`).
- `quick-open` fuzzy-opens a file (Ctrl+P), optional `:line`.
- `outline-symbol` lists symbols under Explorer and via **Tools → Go to Symbol in File** (Ctrl+R).
- `goto-def-ref-rename` uses F12, Shift+F12, F2.

## How to get to it (user POV)

- **Edit → Find / Replace / Go To Line / Find in Files / Find References / Rename Symbol / Go To Definition**.
- Activity bar **Search**.
- **File → Quick Open...**.
- Outline panel under the tree; **Tools → Go to Symbol in File**.

## Driving it with control-cbcs

Preconditions:

- Project open; `main.py` (or similar) contains a unique identifier you will search.
- Doctor passed.

- **Find.** `control-cbcs trigger "$SID" shell.action.edit.find`. `#shell.findBar.findInput` is focused. Type the unique token. `#shell.findBar.matchCount` is non-zero. Shot `find-match`.
- **Replace.** `control-cbcs trigger "$SID" shell.action.edit.replace`. Fill `#shell.findBar.replaceInput`; click `#shell.findBar.replaceBtn`. Buffer is dirty; the token changed.
- **Find in Files.** `control-cbcs ctl "$SID" click '#shell.activityBar.btn.search'`. Type the token in `#shell.searchSidebar.searchInput`. `#shell.searchSidebar.results` lists hits. Activate a row; an editor tab opens at that line.
- **Quick Open.** `control-cbcs trigger "$SID" shell.action.file.quickOpen`. Type `main.py`. Confirm. Tab opens.
- **Go to Symbol.** `control-cbcs trigger "$SID" shell.action.tools.gotoSymbolInFile`. `#shell.quickSymbolDialog.input` accepts a name; choosing a row moves the cursor.
- **Definition.** Place the cursor on a known function; `control-cbcs trigger "$SID" shell.action.edit.goToDefinition`. Cursor / tab moves to the definition.
- **Proof.** Shot of find-in-files results plus the opened tab line, or the find bar match count and highlighted editor.

## Gotchas

- Find-in-files results debounce. Wait for `#shell.searchSidebar.summary` or `#shell.searchSidebar.noResults`, not a fixed sleep.
- F2 in the **tree** is rename-file, not rename-symbol. Focus the editor first.
- Quick Open preview vs permanent follows the preview-tabs setting.
