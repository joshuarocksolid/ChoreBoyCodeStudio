# Style sheets, colours and the form's look

## Text colour and Background
Select a widget. In Appearance, after Font, the Text colour and Background rows each open a colour picker.

* Text colour writes a `color:` line in the widget's own style sheet. ChoreBoy's theme sets text colours, so a palette colour would not show when the app runs.
* Background sets one palette colour for the widget in every state. Labels, group boxes, frames, check boxes and the form also turn on "fill background", so the colour shows.
* Reset (in the picker, or the arrow beside the row) takes back only what the row wrote.
* If a style sheet already sets that colour for the widget, the row says so and offers "Edit style sheet".

## The style sheet drawer
Appearance > Style sheet > Edit…, the canvas menu's "Edit style sheet…", or Form > Style sheet of the form….

* The drawer sits under the canvas. Type a rule such as `QPushButton#okButton { background: #1A7F37; }`; 300 ms after you stop typing the canvas shows it.
* The status says "Looks right" or names the first problem and its line. Click it to jump there. A sheet Qt can't read leaves the last good one on the canvas.
* A chip beside each rule counts the widgets it styles. "No match" is only a note: the form still saves. While the caret is in a rule, those widgets are outlined on the canvas.
* Insert > Colour…, Picture…, Gradient…, Font… and "Rule for this widget" put text at the caret.
* Esc or Done closes the drawer and keeps the text. One visit is one undo step, "Change style sheet of {name}".
* Problems lists a sheet Qt can't read (FB033) and rules that match nothing (FB034); each has an "Edit style sheet" button.

## The form's look
With the form selected, Accent colour (selections, progress bars and links) and Text size (8 to 24 pt) set the root palette's Highlight and Link roles and the root font. Every widget that doesn't set its own size follows Text size.
