# Signals and slots

A signal is something that happens, such as a click. A slot is the work that runs. You wire them on the Connections overlay and on the Behavior tab.

## To connect two widgets

1. Press F4, or choose `Form > Overlays > Connections`.
2. The banner says `Drag from a widget to the widget it should act on. Drop on the form's background to act on the form.`
3. Drag from the sender to the receiver. Enter starts or finishes the link. Home picks the form as the receiver.
4. Pick the event and the step.

Esc before you pick a receiver writes nothing.

`Ctrl+Shift+L` shows every connection. The status line says how many, and the same key hides them again. With the overlay closed, arrows follow the Behavior tab's selection. Tab order and Buddies hide the arrows.

## To add a step on the Behavior tab

1. Select the widget. Press `Alt+B`.
2. Under `EVENTS`, click `+ When…` and choose the event.
3. Click `+ Then…` and choose the step.

Plain steps include `Clear`, `Move focus to`, `Close this form`, `Accept (OK)`, `Cancel`, and `Call` plus a method name.

A step can be `Only if…`, turned off, duplicated, or moved. `Go to code` opens the method. Delete removes the step.

On the form itself, the event headers include `When the form opens` and `Before the form closes (the form stays open if a step stops)`. A form with a table also lists record events, such as `Before saving (a step can stop the save)`.

`YOUR METHODS` names the window file. The line under it says Code Studio adds methods to that file and never changes the rest of it.

## What the file stores

A step that is only a Qt slot or a call to your window, with no condition and not turned off, is stored as a Qt `connection`. Anything else is a `cbcsOn…` property on the sender. The JSON uses `"do": "slot"` or `"do": "call"`. A condition is `"when"`. A step that is off has `"enabled": false`.

If the same event is stored both as a Qt connection and as a Code Studio step list, the row says `This event is stored in two places.` Click `Merge`.

## Connect methods by name

`Form settings`, in the Code group, has `Connect methods by name`. The caption says methods named `on_{widget}_{event}` with `@Slot` run without a step. Qt Designer calls this Connect slots by name.

The box is on unless the form says otherwise. A method that matches shows on the event as `runs by its name`. When the box is off, the Problems panel says that method will not run by itself, and the fix turns the box back on.

[Form builder manual](index.md)
