# Try

## Preview runs the form
Ctrl+Shift+R opens Preview. When the form has rules, checks, or steps, Preview runs them. Run behavior, in the Preview toolbar, is on. Turn it off to see the layout only.

Your window file is not imported. Each method the form names is a stand-in. A step that calls one logs "Would call {method}()". A formula that calls window.m() reads the Window values strip under the form.

## What ran
The pane on the right is titled What ran. Each line has a time, a sentence, and the source. Clear and Copy sit above the list.

A rule refresh is one line, "Rules ran (N)". A failing check is "Check {name}: {message}". A step that stops the list is "{Name} is clicked: stopped at step 1 (Check all fields)". Click a line to select that widget and open Behavior.

## Window values
The strip lists each window.m() a formula calls. A method marked bool is a box with a blank line, Yes, and No. Anything else is a text box. A blank box counts as blank, and the log says "{method}() needs a window value" once for that method. Changing a box runs the rules again.

## Editing while Preview is open
Edit a rule or a step and Preview reloads. Values stay where the object name is still there.
