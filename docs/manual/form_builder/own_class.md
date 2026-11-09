# Your own class

Use this when a field is a Python widget you wrote, such as a till display. Qt Designer calls the same step Promote.

## To use your class

1. Right-click the widget.
2. Choose `Use my own class…`. The tooltip says `Qt Designer calls this Promote to.`
3. Type the class name, such as `TillDisplay`.
4. Type the module, such as `widgets.till_display`.
5. Click `Use`.

`Based on` shows the Qt class of the widget you started from. You do not type it. `Holds other widgets` is there for a container. The note says the class is saved for this project's other forms.

Code Studio reads the module with a parser. It does not import it. The check line says one of these.

- `Found TillDisplay in widgets.till_display.`
- The class is based on a different Qt class, so the form may look different when it runs.
- The module has no class by that name.
- The module is not in the project yet. You can still use the name.
- The form is not in a project, so Preview shows a stand-in.

`Back to …` on the menu returns the widget to the Qt class.

## What the file stores

The widget's class becomes your class name. The form gains a `customwidget` entry. The header is the module path with slashes and a `.h` ending, such as `widgets/till_display.h`, marked as a local header. That header is there so Qt Designer can read the file. Python loads the module.

The same class is remembered in `cbcs/project.json` for the next form. That memory is not undone when you undo the form edit.

If the module is not in the project, the Problems panel says the class comes from a module that is not in this project. See FB035 in [Form problems](diagnostics.md).

[Form builder manual](index.md)
