# Your own widget classes

You can use a widget class that you wrote in your project in place of a stock Qt widget, such as a `TillDisplay` label that shows a running total. Qt Designer calls this Promote to.

## Use my own class
Select a widget, then right-click it (or press Shift+F10) and choose "Use my own class…". Several widgets of the same class change together.

* **Class** is the name of your class, such as `TillDisplay`. **From Python module** is where it lives, such as `widgets.till_display`, which is the file `widgets/till_display.py` in your project (or `widgets/till_display/__init__.py`).
* The line under the fields checks the module without running it. It reads the file as text, so a mistake in your code can't hurt the editor. It says whether the file and the class were found, and warns when your class is based on a different Qt class than the widget.
* [Use TillDisplay] changes the widget to your class in one undo step, "Use class TillDisplay for okLabel". The class is also saved in `cbcs/project.json` for the project's other forms; Undo does not take it out of that list.
* The list "Classes in this project" at the top fills the fields for a class you used before. Each row's ⋯ menu has "Edit…" (description and size on the canvas) and "Remove from this list" (forms that use the class keep it).

The right-click menu of a widget that uses your class also has "Back to label" (its stock class). That is one undo step, and the class is taken out of the form when nothing else uses it.

## What you see
* A widget based on a label, a button or another widget that draws something looks like that widget on the canvas. A corner tag and an outline show on it when it is selected or hovered, and the inspector header says "TillDisplay · your class, based on Label".
* A class based on a plain Widget or Frame has no look the editor can borrow, so the canvas draws a labelled box, "Card · from widgets.card", at the size set in "Edit…" (or 120 × 40). It can be picked even when it is small.
* Insert lists the project's classes under "Your widgets". Inserting one is one undo step, "Insert TillDisplay".
* Problems warns when a class comes from a module that isn't in the project (FB035), with a "Use my own class…" button.

## Preview
Preview is the only place your code runs, and only in the preview window, never in the editor. The first time you preview a form in a session, an info bar names the classes it will run. Before the form is built, each class is created once on a hidden window; if that fails or takes too long, Preview uses a plain widget of the base class for it and says so ("Preview used a plain label for Broken."). Problems has the reason and the file and line (FB602). Edit the file and preview again to try it again.

A form that is not in a project never runs your classes: Preview shows plain widgets instead.

## In the file
The form stores a Qt Designer `customwidget` whose header is the module as a path (`widgets/till_display.h`); Designer opens it, and the generated `ui_*.py` imports the class from your module, as Qt's own tool does.
