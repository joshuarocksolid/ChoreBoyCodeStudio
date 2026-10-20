# Form builder spike

A PySide6 form builder prototype for ChoreBoy Code Studio: the editing feel, the `.ui` round trip, generated `ui_<name>.py`, and the speed of a few hundred widgets. It does not change the rest of CBCS. The design is in [DESIGN.md](DESIGN.md).

## Run

From the repository root:

```sh
spikes/form_builder/run.sh            # start screen
spikes/form_builder/run.sh some.ui    # open a form directly
```

The script uses FreeCAD 1.1.3 at `/Applications/FreeCAD.app` and its Python 3.11 with PySide6 6.8. The chrome follows the system light or dark setting (View > Appearance overrides it). The form on the canvas always draws with the runtime look (Fusion, standard light palette), whatever the chrome theme.

Regenerate the sample database and the 302-widget form with:

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/python spikes/form_builder/samples/make_samples.py
```

## Tests, budgets, screenshots

```sh
QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python -m pytest spikes/form_builder/tests -q -p no:cacheprovider
QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python spikes/form_builder/screenshots_capture.py [name ...]
```

- `tests/test_commands.py`, `tests/test_oracle.py`: the command log, the writer, uic and QUiLoader oracles, the 67-file Designer corpus round trip.
- `tests/test_ui_logic.py`: sizing words, paste into a layout, tab-order splicing, next free cell, buddies, layout morphing, Type here menus, generated Python for FreeCAD widgets, and the realizer reusing live widgets on wrap, unwrap, and first layout.
- `tests/test_interaction.py`: gestures driven through real mouse and key events (drag to reorder, Alt-drag copy, gap drag, resize handles, tab-order clicks, buddy drag, Type here, in-place text, outline rename keeping focus, quick insert, wrap and unwrap, page edge).
- `tests/test_perf.py` rewrites `perf_report.txt` and appends to `perf.log`.

Screenshots are written to `screenshots/`: start (light and dark), from-table, workbench light and dark, window-selected (margins and anchors), drag-box, drag-grid, drag-form, layout-selected (gaps), empty-form, empty-group, wrap-menu, quick-insert, inspector-size, inspector-behavior, inspector-data, tab-order, buddy, main-window-menu, two-widths.

## What works

**Start screen.** Templates with painted wireframes (data entry, list and detail, table with search, dialog), blank widget, main window and dialog (each already laid out), Build a form from a table, Open a .ui file, recent files, and a short key list.

**Build from a table.** Pick a SQLite table, choose per column whether to include it, what it shows as, and its label; a live preview renders the result. The form comes out as a form layout with buddies, tab order, and OK / Cancel.

**Workbench.**
- Outline: glyph, name and a muted class and text hint per row; layouts in violet, spacers in pink. Drag rows to reorder or reparent (on a row = into it, between rows = beside it).
- Insert palette: icon tiles by category. Drag a tile to the canvas, or double-click it to insert after the selection.
- Canvas: real widgets on a page card with the window title, a dot-grid backdrop, zoom (Ctrl+wheel, top bar). Layout frames are faint everywhere and explicit (chip, margins, gaps) around what you are looking at. Spacers draw as springs. Empty layouts stay big enough to drop into and say so.
- Selection: name chip, a plain-words size badge (`Fill × Hug · 565 × 26`), and right, bottom and corner handles that write a Fixed size; double-click a handle to go back to Hug.
- Drops: an insertion line in boxes, a target cell in grids (only the dragged item changes cell), label/field halves and new rows in forms, panes in splitters, and "makes a vertical layout" for a bare container. Alt-drag copies.
- Gaps: pink bars between neighbours, draggable (4 px steps, Alt 1 px, Shift 8 px). A selected container shows its margins; the window's root layout also shows its anchors to the four edges.
- The page's right and bottom edges resize the window (root geometry, one undo step) so you can watch the layout follow.
- Text-size preview (S / M / L) and a two-widths view (420 and 760 px side by side).
- Tab order overlay: numbered badges and a flow line; click fields in order, Shift-click to start from one, Esc to leave. New inputs join a saved order where they sit.
- Buddies overlay: links from labels to fields; drag from a label to a field. "Pair labels with their fields" does the form rows in one step.
- Main windows: click a menu title to open it on the canvas, Type here to add menus and actions (`-` adds a separator).
- Inspector: header with an inline name field and breadcrumb; tabs Properties, Behavior, Data. Properties has Content (curated per class, enums as words), Size (Hug / Fill / Fixed per axis, Share, minimum and maximum with blank meaning "not set", a "why is it this size?" sentence), Layout (kind, gaps, margins, grid column and row sizes as numbers, Remove layout behind a confirm), and a searchable All properties list. Every Reset deletes the line. With nothing selected it shows the window: title, size, tab order list, problems, and files. Behavior lists and adds signal → slot connections; Data shows what the logic phase will add.
- Wrap (Ctrl+G) is a popover of six tiles; unwrap (Ctrl+Shift+G) puts children back. Paste and duplicate go into the layout after the selection and select the result. Toasts offer Undo after deletes and wraps.
- Save writes the `.ui` and `ui_<name>.py`; Create window class writes `<name>_window.py` once; Preview runs the generated module.

**Plumbing changed for the UI.** The realizer reconciles by moving existing widgets (wrap, unwrap, nest, and first layout no longer rebuild a subtree). New commands: layout attributes, item cells, body parts for menus, tab splicing, buddy pairing, layout morphing, remove layout. The generator now imports FreeCAD `Gui::` widgets through `FreeCADGui.UiLoader` (Qt base class as fallback), imports promoted Python classes from their header path, writes margins with `setContentsMargins`, emits layout stretch attributes, and no longer crashes on main windows: 61 of the 67 FreeCAD corpus forms run their generated `setupUi` (15 before).

## Keyboard

| Key | Action |
| --- | --- |
| Up / Down | Move in the outline; on the canvas, walk siblings |
| Enter / Esc | Into the first child / up to the parent (Esc also leaves Tab order and Buddies) |
| Tab / Shift+Tab | Nest into the previous container / un-nest (outline) |
| Alt+Up / Alt+Down | Move within the layout (rows swap in forms and grids) |
| F2 | Rename in the outline; edit the visible text on the canvas |
| Shift+F2 | Rename from anywhere (inspector name field) |
| / | Quick insert after the selection |
| Delete / Backspace | Delete (toast offers Undo) |
| Cmd+X / C / V / D | Cut / copy / paste into the layout / duplicate |
| Ctrl+G / Ctrl+Shift+G | Wrap / unwrap (physical Control on macOS) |
| Cmd+Z / Cmd+Shift+Z | Undo / redo |
| Cmd+S / Cmd+R | Save .ui and ui_<name>.py / preview |
| Cmd+1 / 2 / 3 | Design / Tab order / Buddies |
| Cmd+= / Cmd+- / Cmd+0 | Zoom in / out / 100% |
| Up / Down in number fields | Step by 1, Shift by 10; drag a field's label sideways to scrub |

## User pains (docs/form_builder/research/P_user_pain_points.md)

Solved in the spike: 1 layout on drop, 2 size words with Reset deleting the line, 3 paste into a layout, 4 rows you can hit and tree reparenting, 5 no break-layout step (Remove layout asks first), 12 text-size preview with no pixel geometry, 13 overlays instead of sticky modes and connections in the inspector, 14 gaps as numbers and drag handles with visible springs, 18 enum editors that commit, 20 tab order that follows the picture and leaves with Esc, 21 grid drops that move only the dragged item, 25 rename keeps the keyboard. Delighters: Hug / Fill / Fixed, selectable gaps, anchors drawn on the window, tree reparenting, column sizes as numbers, modifier-key nudges, next drop fills the next cell, Reset deletes the line, live canvas on the same file.

Partly: 16 connections are a normal list (no signature check before save yet), 17 Type here works on menus (actions do not drag onto toolbars yet), 19 splitters take drops and Share, but the canvas does not drag splitter handles.

Not in this spike: 6–11, 15, 22–24 (logic-file stubs, promotion dialog, style sheet matches, resources, packaging, out-of-process preview, completion stubs, slot-name checks).

## Known gaps

- Out-of-process preview: Preview still runs in the editor's process.
- Splitter handles cannot be dragged on the canvas, and tab pages cannot be reordered from the outline.
- Actions cannot be dragged onto toolbars; the toolbar has no Type here.
- Structural edits to a main window's menu bar or toolbar rebuild the whole canvas (small forms only).
- The "content size" command from pain 14 and a style sheet editor are not built.
- Six FreeCAD corpus forms still fail to run their generated Python (custom-widget properties set on a fallback base class, a `QTableWidget` item list).
- Two-widths shrinks the wide view to fit; there is no shared selection chrome between the two views.
- Screenshots are offscreen grabs with the overlays and popups composited on top; native window chrome and the macOS menu bar are not in them.
