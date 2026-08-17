# Flat-Python paste

Pasting flattened Python (typical of PDF / email copies) can be re-indented. The user can apply once, always, or dismiss from an overlay, or run the Tools / Edit commands.

Owns AT-EDIT-FLAT-PYTHON-PASTE.

## Sub-features

- `paste-overlay` shows `PasteHintOverlay` after a flat paste.
- `paste-reindent` **Re-indent** repairs the selection.
- `paste-always` remembers the preference in settings.
- `paste-dismiss` leaves the buffer unchanged.
- `paste-command` **Edit → Paste and Re-indent Flat Python** (Ctrl+Alt+V) and **Tools → Re-indent Flat Python Selection**.

## How to get to it (user POV)

- Paste flattened code into a Python editor.
- Overlay buttons: Re-indent / Always / Dismiss (`#PasteHintOverlayReindentButton`, `#PasteHintOverlayAlwaysButton`, `#PasteHintOverlayDismissButton`).
- **Edit → Paste and Re-indent Flat Python**.
- **Tools → Re-indent Flat Python Selection**.

## Driving it with control-cbcs

Preconditions:

- Python tab open; doctor passed.
- Clipboard or `type` a flat snippet such as a `def` followed by an unindented `return` on the next line.

- **Paste flat.** Insert the flat snippet (bridge `type` or paste). Overlay `#PasteHintOverlay` appears. Shot `paste-hint`.
- **Re-indent.** Click `#PasteHintOverlayReindentButton`. The `return` is indented under the `def`. Buffer is dirty.
- **Dismiss path (separate run).** Paste again; click `#PasteHintOverlayDismissButton`. Indent stays flat.
- **Command.** Select flat lines; `control-cbcs trigger "$SID" shell.action.edit.pasteReindentedFlatPython` or `shell.action.tools.reindentFlatPythonSelection`. Same indent repair.
- **Proof.** Shot of the overlay and of the repaired buffer; if you saved, the guest file matches.

## Gotchas

- Overlay names are not `shell.*` prefixed.
- "Always" writes settings in disposable HOME — copy `settings.json` if you need to prove persistence.
- A normal well-indented paste must not show the overlay.
