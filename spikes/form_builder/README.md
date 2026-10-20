# Form builder spike

A throwaway PySide6 form builder for trying the editing feel, the `.ui` round trip, and the speed of a few hundred widgets. It does not change the rest of ChoreBoy Code Studio.

## Run

From the repository root:

```sh
spikes/form_builder/run.sh
```

That script uses FreeCAD 1.1.3 at `/Applications/FreeCAD.app` and its Python 3.11 with PySide6. The window opens on the start screen.

Regenerate the sample database and the large form with:

```sh
/Applications/FreeCAD.app/Contents/Resources/bin/python spikes/form_builder/samples/make_samples.py
```

## Tests

```sh
QT_QPA_PLATFORM=offscreen /Applications/FreeCAD.app/Contents/Resources/bin/python -m pytest spikes/form_builder/tests -q
```

The performance numbers are rewritten to `spikes/form_builder/perf_report.txt` and appended to `spikes/form_builder/perf.log`. The Designer corpus report is `spikes/form_builder/corpus_report.txt`.

## What works

The source of truth is a Qt 6 `.ui` file. Opening one builds an in-memory document with no Qt types. Every edit goes through the undo log. Save writes the `.ui` file and `ui_<name>.py` next to it. Preview opens a real window from that generated module. Create window class writes `<name>_window.py` once and leaves an existing file alone.

The start screen offers four templates, a blank widget, a blank main window, Open, and Build layout from a table. The table flow reads `samples/shop.sqlite` (customers and invoices) or another SQLite file, shows the column mapping, and builds a form layout with buddies, tab order, and a button box.

The workbench has an outline, a filterable widget box, a live canvas, and an inspector. Dropping a widget shows an insertion line. Dropping into a container that has no layout creates a vertical layout. Layouts are framed and labeled. Zoom runs from 50% to 200%. Two widths shows the form at 420 and 760. The inspector edits common properties, a plain-language size policy, and the long tail from the widget's meta object. Signals mode lists connections and can add or remove a simple one.

## Keyboard

| Key | Action |
| --- | --- |
| Arrows | Move the outline selection |
| Tab | Nest into the previous sibling container |
| Shift+Tab | Un-nest |
| Alt+Up or Alt+Down | Reorder in the outline |
| F2 | Rename in the outline |
| / | Quick insert |
| Delete | Delete the selection |
| Escape | Select the parent |
| Command+Z, Command+Shift+Z | Undo, redo |
| Command+C, Command+V | Copy, paste into the selected layout |
| Command+D | Duplicate |
| Command+S | Save `.ui` and `ui_<name>.py` |
| Command+R | Preview |
| Control+G | Wrap in a layout or container |
| Control+Shift+G | Unwrap |

On macOS, Command is the usual shortcut modifier. Wrap stays on the physical Control key.

## Known gaps

- A structural edit that adds or removes a layout still rebuilds that widget's subtree. Insert, delete, and reorder of a widget inside an existing layout are patched.
- The geometry index used for hit testing refreshes on the next pointer event, not during the edit itself.
- Tab order can be reset, and clicking a widget in tab mode moves it to the end of the order. It is not Designer's full restart-from-here editor.
- Buddy mode accepts a drag from a label to a field, and the inspector can set the buddy by name.
- The menu on a main window is an action list, not Designer's inline "Type here" editor.
- Custom FreeCAD widgets such as `Gui::InputField` are preserved in the file and fall back to their base class when Qt builds the preview. The generator emits the short class name, so those files are not imported as Python.
- Screenshots are offscreen grabs. The insertion line is composited from the overlay because a graphics-view grab can miss a translucent child until it is repainted on its own.

## Samples

`samples/shop.sqlite` has customers and invoices. `samples/big_form.ui` is the 302-widget form used for the budgets.
