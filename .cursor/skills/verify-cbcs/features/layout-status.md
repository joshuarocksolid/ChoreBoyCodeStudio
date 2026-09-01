# Layout and status

Splitters persist. Reset Layout restores defaults. Zoom changes editor chrome. Status-bar chips report runtime, run, project, indent, diagnostics, and the active run configuration.

Owns AT-25 plus status-bar contracts used by smoke M1/M3/M6.

<!-- dune-owners: platform.shell -->

## Sub-features

- `layout-default` explorer | editor | bottom tabs on first launch (AT-25).
- `layout-persist` splitter sizes survive a relaunch with the same HOME.
- `layout-reset` **View → Reset Layout** restores defaults.
- `zoom` **View → Zoom In / Out / Reset** (Ctrl+=, Ctrl+-, Ctrl+0) changes editor `font_point_size` only, not chrome.
- `status-chips` the named status labels update with project/run/editor state.
- `run-config-chip` `#shell.statusBar.activeRunConfig` opens the config menu.

## How to get to it (user POV)

- Drag splitters; **View → Reset Layout**.
- **View → Zoom In / Out / Reset Zoom**.
- Click status-bar chips (startup → Runtime Center; run-config → menu).

## Driving it with control-cbcs

Preconditions:

- Doctor passed.
- Optional: project open so project/editor chips are populated.

- **Chips after launch.** Read `#shell.startupStatusLabel` (`Startup: Runtime ready (8/8 checks)`), `#shell.runStatusLabel` (`Run: idle`), `#shell.projectStatusLabel` (`Project: none loaded`). Shot `status-launch`.
- **After open + edit.** Project chip shows the name. Editor chip shows `Ln` / `Col` and `modified` after a keystroke.
- **Zoom.** `control-cbcs trigger "$SID" shell.action.view.zoomIn` twice, then `zoomReset`. Editor remains usable; shot `zoom-in` vs `zoom-reset`.
- **Reset layout.** Drag `#shell.topSplitter` if the bridge exposes it; then `control-cbcs trigger "$SID" shell.action.view.resetLayout`. Explorer and bottom tabs return to a usable default. Shot `layout-reset`.
- **Proof.** Before/after shots of zoom or reset, plus the chip reads in artifacts.

## Gotchas

- Outline collapse / sort / follow-cursor also persist — prove with the same HOME or by reading settings before stop.
- Diagnostic chip hides when counts are zero. Absence is not a missing widget.
- Window starts maximized (`showMaximized`). Do not treat a maximized frame as a layout bug.
