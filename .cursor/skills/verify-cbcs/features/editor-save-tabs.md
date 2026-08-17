# Editor, save, and tabs

Opening a file puts it in a tab. Edits mark the tab dirty. Save / Save All write disk. Preview tabs stay italic until pinned. Dropping a local file on the main window opens it. External disk changes prompt before overwrite.

Owns AT-06, AT-07, AT-08, AT-09, AT-44, request #43 (drag-drop open).

## Sub-features

- `editor-open` opens a project file in `#shell.editorTabs`.
- `editor-dirty` shows `*` after an edit.
- `editor-save` writes the buffer (Ctrl+S / **File → Save**).
- `editor-save-all` writes every dirty tab.
- `editor-preview` uses italic preview tabs from single-click; double-click or edit pins.
- `editor-drop-open` opens dropped local files (folders ignored).
- `editor-external` prompts when disk is newer than the buffer.

## How to get to it (user POV)

- Double-click a file in the tree, **File → Open File...** (Ctrl+Shift+O), Quick Open (Ctrl+P), or drop a file on the window.
- **File → Save** / **Save As...** / **Save All** / **Auto Save**.
- Tab close, middle-click, Ctrl+W; tab context Close / Local History.

## Driving it with control-cbcs

Preconditions:

- Project open with `main.py`.
- Doctor passed.

- **Open.** Click `#shell.activityBar.btn.explorer`, activate `main.py` in `#shell.projectTree` (double-click). `#shell.editorTabs` current title contains `main.py`.
- **Dirty.** Focus the editor; type a unique comment. Tab title gains `*`. `#shell.editorStatusLabel` contains `modified`.
- **Save.** `control-cbcs trigger "$SID" shell.action.file.save`. `*` clears. Guest file contains the comment. Status contains `saved`.
- **Save All.** Dirty two files; `control-cbcs trigger "$SID" shell.action.file.saveAll`. Both disks match.
- **Preview.** Single-click a second file. Tab title is italic (preview). Open a third via single-click; the previous preview is replaced. Double-click pins.
- **Drop open.** Drop a `.py` from the share onto `#shell.mainWindow` if the bridge can synthesize a drop; otherwise **File → Open File** to the same path. A tab opens. Folders must not open as tabs.
- **External change.** From the Mac/SSH, append to the file on disk while the tab is clean. Wait for the poll. A reload dialog appears. Choose reload; buffer matches disk. Shot `editor-external`.
- **Proof.** Shot of dirty then saved tabs, plus the guest file contents in artifacts.

## Gotchas

- All text editors share `#shell.editorTabs.textEditor`. Do not assume find() returns the visible tab.
- Auto Save can hide dirty. Turn it off (**File → Auto Save** unchecked) when proving `*`.
- Save / Run prompt when the buffer is stale vs disk. Do not treat a silent overwrite as success.
- Drag-drop ignores folders. Dropping `.py` on the **console** executes it (see [repl.md](./repl.md)), which is a different feature.
