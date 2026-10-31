# Steps

## A step
A step is one thing the event does. Then… lists them in groups: Do this, Fields, Show, Windows, Your code, Flow, and Everything else.

Check all fields stops the event when a field fails. Set a field writes a formula into it. Clear fields blanks them. Move focus to puts the cursor there. Show, hide, enable and disable change that one widget. Show a message and Ask yes or no open a box. Ask stops the event on No. Switch tab or page shows one page. Open another form opens a form from this project's forms folder. Close this form accepts, cancels, or closes. Stop here if… stops the event when its condition is true.

## Only if
Every step can have a condition. Shift+F10 on the step, then Only if…. The row gains a second line, "only if {condition}". The step runs only when that condition is true. A condition Code Studio cannot read skips that step and leaves the rest of the event running. The Problems list names the step.

## When the form opens and closes
Select the form. Events lists "When the form opens" and "Before the form closes" first. The open list runs at the end of setup. The close list can keep the form open: if a step stops, the form stays open. The close row says "(the form stays open if a step stops)".
