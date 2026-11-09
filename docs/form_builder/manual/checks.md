# Checks

A check is a rule for one field. The form runs it when the person leaves the field. If the field fails, the message shows under the field, or as a tooltip when there is no label there.

Select the field and open Behavior. Checks lists the rules in the order they run. Required is first. Alt+Up and Alt+Down move the others.

## The nine kinds

- Required. The field cannot be left blank.
- Between. A smallest value, a largest value, or both. A side can be a number or a formula.
- Length. The shortest and longest text, in characters.
- Email address.
- Phone number.
- US ZIP code.
- Pattern. The text has to match a pattern.
- One of. The value has to be one of the values you list.
- Formula. A formula that has to be true, and the message to show when it is not.

"+ Add check" lists only the kinds that fit the field. A spin box, a date, a slider, and a dial are never blank, so Required is not in their list.

The message starts as the sentence the form would write. Leave it to keep that sentence. Change it to use your own. Formula has no sentence until you write one.

## The error label

The first check asks "Show messages under the field?" Add label puts a label under the field and saves the check in the same step. Not now saves the check without the label. The messages then show only as a tooltip, and Checks offers the label again.

"Add the red outline style" draws a red border on a field that failed. It is added once, on the form.

## Keys

Enter or Down on "+ Add check" opens the list. Enter chooses a kind. Ctrl+Enter saves the check. Esc closes the page and does not change the form.

On a check: Enter edits it, Delete removes it, Alt+Up and Alt+Down move it.

## When it runs

Checks run when the person leaves the field. A field that was never edited stays quiet, even if it is blank.
