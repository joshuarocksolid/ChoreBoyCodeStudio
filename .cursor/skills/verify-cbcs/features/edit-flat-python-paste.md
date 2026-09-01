# Flat-Python paste

Pasting flattened Python (typical of PDF / email copies) can be re-indented. The user can apply once, always, or dismiss from an overlay, or run the Tools / Edit commands.

Owns AT-EDIT-FLAT-PYTHON-PASTE.

<!-- dune-owners: platform.editors -->

## Sub-features

- `paste-overlay` shows `#PasteHintOverlay` after a real Qt paste of flat Python (`insertFromMimeData`). Typed keys do not show it.
- `paste-reindent` **Re-indent** repairs the just-pasted range.
- `paste-always` repairs that range and persists `editor.auto_reindent_flat_python_paste`.
- `paste-dismiss` **×** leaves the buffer unchanged and hides later hints for the session. A 5 s auto-hide does the same.
- `paste-command` **Edit → Paste and Re-indent Flat Python** (`Ctrl+Alt+V`) pastes the clipboard already repaired and never shows the overlay. **Tools → Re-indent Flat Python Selection** repairs the current selection, or the last paste range if nothing is selected.

## How to get to it (user POV)

- Paste flattened code into an editor. Auto-repair is off by default.
- Overlay copy is **Looks like flat Python.** Buttons are **Re-indent**, **Always**, and **×** (`#PasteHintOverlayReindentButton`, `#PasteHintOverlayAlwaysButton`, `#PasteHintOverlayDismissButton`).
- **Edit → Paste and Re-indent Flat Python**.
- **Tools → Re-indent Flat Python Selection**.
- Settings → General checkbox **Automatically repair flat Python indentation on paste (experimental)**.
- Right-click adds **Paste and Re-indent (Flat Python)** / **Re-indent Selection (Flat Python)** only when the clipboard or selection looks flat.

## Driving it with control-cbcs

Preconditions:

- Editor tab focused. Doctor passed.
- Auto-reindent stays off on a disposable HOME.
- The overlay auto-hides at 5 s. Click immediately.

- **Paste flat.** Click `#shell.editorTabs.textEditor`. Exec a real Qt paste. Bridge `type` / `keyPressEvent` never enters `insertFromMimeData`, so `#PasteHintOverlay` will not appear.

```bash
$CONTROL ctl "$SID" exec -- "from PySide2.QtCore import QMimeData
w=find('#shell.editorTabs.textEditor'); md=QMimeData(); md.setText('def first():\\nreturn 1\\n'); w.insertFromMimeData(md)"
```

- **Overlay.** `#PasteHintOverlay` is visible. Shot `paste-hint`.
- **Re-indent.** Click `#PasteHintOverlayReindentButton`. The buffer becomes `def first():\n    return 1\n`. Overlay is gone. `#shell.editorStatusLabel` contains `modified`. Status text is **Re-indented flat Python paste.**
- **Dismiss path (separate run).** Paste again. Click `#PasteHintOverlayDismissButton` (**×**). Indent stays flat.
- **Commands.** `shell.action.edit.pasteReindentedFlatPython` reads the clipboard and inserts repaired text. It does not re-indent the current selection. `shell.action.tools.reindentFlatPythonSelection` repairs the selection or the last paste range.
- **Proof.** Shot of the overlay and of the repaired buffer.

## Gotchas

- Overlay names are not `shell.*` prefixed.
- Well-indented or non-Python pastes do not hint. Low-confidence repairs do not hint either.
- There is no language gate on the editor.
- "Always" writes settings in disposable HOME. Copy `settings.json` if you need to prove persistence.
