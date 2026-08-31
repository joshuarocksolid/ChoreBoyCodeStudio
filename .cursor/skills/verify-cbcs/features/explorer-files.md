# Explorer and files

The Explorer activity shows the project tree, creates/renames/trashes files, marks source roots, and keeps the tree in sync when the disk changes.

Owns AT-05, AT-27, AT-28, AT-83.

## Sub-features

- `explorer-show` lists project files in `#shell.projectTree`.
- `explorer-new` creates a file or folder from the header or context menu.
- `explorer-rename-trash` renames (F2) and moves to trash (Delete).
- `explorer-source-root` marks/unmarks a directory as a sources root.
- `explorer-import-rewrite` asks before rewriting imports on move/rename.
- `explorer-external` refreshes when files appear on disk.

## How to get to it (user POV)

- Activity bar **Explorer** (`#shell.activityBar.btn.explorer`).
- Header New File / New Folder / Refresh.
- Tree context menu: New, Rename, Move to Trash, Duplicate, Copy Path, Mark as Sources Root, Local History, Run (`.py`).

## Driving it with control-cbcs

Preconditions:

- A project is open (see [project-open-create.md](./project-open-create.md)).
- Doctor passed.
- Explorer page is selected.

- **Show Explorer.** Run `control-cbcs ctl "$SID" click '#shell.activityBar.btn.explorer'`. `#shell.projectTree` is visible.
- **Contents.** Tree lists `main.py` (or the project's entry) and does not list `vendor/` by default.
- **New file.** Header buttons are icon-only `QToolButton`s that share `#shell.explorerAction`. Tooltips are **New File**, **New Folder**, and **Refresh Explorer**. `text:New File` misses. Arm-click the **New File** tooltip (`QTimer.singleShot` then `btn.click`) because `QInputDialog.getText` blocks a direct click. Name it `probe_tree.py`. Tree shows the new name. Guest disk has the file. After create, focus is in the editor. F2/Delete need the tree focused again.
- **Rename.** Select the new file; `control-cbcs ctl "$SID" key F2` (tree focused). Rename to `probe_tree_renamed.py`. Disk matches.
- **Trash.** Select it; `control-cbcs ctl "$SID" key Delete`. File leaves the tree. Trash under disposable HOME contains it.
- **Source root.** On a `src/` directory, context **Mark as Sources Root**. Problems / Run resolve imports from that root (AT-83).
- **Proof.** Shot of the tree after create, plus a guest `ls` of the project dir copied into artifacts.

## Gotchas

- Multiple header buttons use `#shell.explorerAction`. Select by tooltip, not `text:`.
- Delete confirms **Move to Trash**.
- Auto-refresh is ~1s. Wait for the new row; do not assert on a fixed sleep alone — re-read the tree.
- Import rewrite is a policy dialog (Ask / Always / Never). Cancel leaves imports unchanged.
- Multi-select context menus say `Move N Items to Trash`.
