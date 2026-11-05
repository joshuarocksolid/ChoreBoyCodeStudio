# Lines and grids

An invoice header and its lines are one form plus one grid. The grid is a table view fed by a child table.

## To add lines

1. Bind the form to the header table. See [Records](records.md).
2. On the Data pane, click `Add lines…`. The button is there when another table points at this form's table and the form has no lines grid yet.
3. Choose `Lines from` and `Linked by`. Set `Order by` and, if you want a line number, `Number lines in`.
4. Tick the columns. You can set the header, the kind, the default, a lookup, and read-only.
5. Click `Add lines`.

Code Studio inserts a table view plus `Add line` and `Delete line`. The Data pane then shows `Lines from …` and an `Edit…` button in place of `Add lines…`.

A table view's own Data tab also has `Add lines…`. That button stays available on a second table view. This version of the form stores one lines grid. A second `cbcsRows` value is an error in the Problems panel. The title says a form has one lines grid in this version, and to use a method for more. See FB320 in [Form problems](diagnostics.md).

## To total the lines

The lines sheet shows a hint that starts with `To total the lines, give Total the Value`. Copy that `sum(...)` formula onto the total field's `Value` row on the Behavior tab.

`sum` adds one column of the grid and skips blanks.

## What the file stores

The grid widget stores `cbcsRows`. The object names the child table, the link column, the key, the order, the position column, and the columns to show.

[Form builder manual](index.md)
