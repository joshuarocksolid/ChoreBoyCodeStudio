# Logic

The Logic pane on the left lists what the form already does. Press `Alt+L`. It is a list, not the editor. Chips filter `Rules`, `Checks`, `Events`, and `Problems`. The sections are `STATE`, `CHECKS`, `EVENTS`, and `IN YOUR CODE`.

An empty form says `This form has no rules, checks, or events yet. Select a widget and open Behavior to add one.`

`Read as text` and `Form > Read Behavior as Text` print the behavior in sentences. `Copy` and `Print` are on that page. The list says it is read from the window file, that it is best-effort, and that Code Studio does not run the file to build the list.

You edit on the Behavior tab. See [Signals and slots](signals.md) and [The inspector](inspector.md).

The Logic pane groups the work as State, Checks, Events, and In your code. The form file stores that work in four layers. This is the map.

## A widget acts on a widget

The Connections overlay and a plain Events step do this. Examples are `Clear Name` and `Close this form`.

A plain step is a Qt `connection` in the `.ui` file. A step with a condition, or a step that is turned off, is a `cbcsOn…` list with `"do": "slot"`.

## A widget calls your code

`Call save_invoice()` is this layer. The method is written in the window file. `YOUR METHODS` lists those methods.

A plain call is a Qt `connection` whose receiver is the form. A call with a condition is `"do": "call"` and `"method"`.

`F12` opens the method. `Ctrl+Shift+E` adds an event. `Shift+F12` lists uses of the name.

## Rules, checks, and formulas

On `STATE`, set `Kind`, `Enabled when`, `Visible when`, `Read-only when`, `Value`, `Format`, and `Default`. Empty words are `always`, `never`, `typed by the person`, and `as designed`.

Kinds include `Text`, `Whole number`, `Number (places)`, `Money`, `Percent`, `Date`, and `Time`.

On `CHECKS`, add `Required`, `Between`, `Length`, `Email address`, `Phone number`, `US ZIP code`, `Pattern`, `One of`, or `Formula`.

The form file stores formulas as plain text on the widget.

- `cbcsEnabledWhen`
- `cbcsVisibleWhen`
- `cbcsReadOnlyWhen`
- `cbcsValue`
- `cbcsDefault`

Checks are a JSON list on `cbcsValidate`. Each item has `"check"` set to `required`, `range`, `length`, `email`, `phone`, `zip`, `pattern`, `oneOf`, `formula`, or `unique`.

Other steps, such as `Set`, `Show a message`, `Ask`, and `Open form`, live on the event's `cbcsOn…` list. A formula field commits with `Ctrl+Enter`. `Ctrl+Space` completes a name. Esc cancels the edit.

The form root stores `cbcsLogic` as `{"version":1}`. A newer version is shown read-only and kept as it is. The Problems panel says the behavior was saved by a newer version of Code Studio.

## Data

The Data tab and the record steps are the fourth layer. `cbcsData` names the connection and the table. `cbcsBind` names a column. `cbcsLookup` fills a choice list. `cbcsRows` describes the lines grid.

See [Connections](connections.md), [Records](records.md), and [Lines and grids](lines.md).

[Form builder manual](index.md)
