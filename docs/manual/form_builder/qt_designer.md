# What is different from Qt Designer

The `.ui` file is a normal Qt form. A person who knows Qt Designer can keep the same layouts, properties, buddies, tab order, and resources. A few keys and a few words moved, because Code Studio already uses those keys.

## Keys

| In Qt Designer | In Code Studio |
| --- | --- |
| Ctrl+N for a new form | `File > New Form…`. Ctrl+N starts a new project. |
| Ctrl+O to open a form | Ctrl+P Quick Open, or the project tree. |
| Ctrl+S and Ctrl+Shift+S | The same. |
| Ctrl+W, and quit | The same. Ctrl+W closes the tab or the Preview. Ctrl+Q quits. |
| Undo, redo, clipboard, Delete | The same. |
| Ctrl+R to preview | Ctrl+Shift+R. Ctrl+R is Go to widget. |
| Ctrl+P to print | `Form > Print…`. Ctrl+P is Quick Open. |
| F1 help for the widget | F1 opens the help card. |
| Designer help | `Help > Form designer keys`. The same list is the [keyboard reference](keyboard.md). |
| F3 or Esc for widget mode | F3 or Esc leaves an overlay. |
| F4 for signals and slots | F4 opens the Connections overlay. You edit the steps on the Behavior tab. |
| F2 to edit text | Enter edits text. F2 renames. |
| Ctrl+F in the object inspector | Ctrl+F. Where it searches depends on focus. See [Find](find.md). |
| Ctrl+1 through Ctrl+6 for layouts | The same. |
| Ctrl+0 to break a layout | `Form > Layout > Remove layout…`, or Ctrl+Shift+B to unwrap. Ctrl+0 is 100% zoom. |
| Ctrl+J to adjust size | The same. |
| Ctrl-drag to clone | The same. A drag that starts with Ctrl held copies the widgets. |
| Arrow keys snap, Ctrl+arrows move 1 px | Alt+arrow moves by the grid step. Alt+Shift+arrow moves 1 px. The arrow keys select. |
| Shift-click selects the parent layout | Esc selects the parent. |
| Shift+Ctrl-drag moves inside a layout | A plain drag moves inside a layout. |

## Words

`Use my own class…` is what Qt Designer calls Promote. The tooltip on that row says so.

`Connect methods by name` is what Qt Designer calls Connect slots by name. The caption on Form settings says so.

Some lines in the `.ui` file are kept for Qt Designer and for C++ code. Python ignores them. The form settings captions say which ones.

## Help inside the designer

Select a widget and press F1. The card names the widget, the Qt class, and a few properties you can set. `All form designer keys` opens the key list.

[Form builder manual](index.md)
