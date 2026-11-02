"""FB301–FB321 (CONTRACTS.md section 19.8).

M8.0s declares them. The lane that produces a code imports it from here and
does not declare it again.
"""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB301", Severity.ERROR, "This form uses the connection {name}, which this project doesn't have.")
declare("FB302", Severity.ERROR, "The connections file can't be read.")
declare("FB303", Severity.WARNING, "{table} has no column named {column}.")
declare("FB304", Severity.WARNING, "A {type words} column can't be shown in a {class words}.")
declare("FB305", Severity.WARNING, "Generated from a different connections file. It will be regenerated on the next save.")
declare("FB306", Severity.ERROR, "{table} has no single key column. Record forms need one.")
declare("FB307", Severity.ERROR, "{name} can't be used: names with spaces or symbols aren't supported.")
declare("FB308", Severity.WARNING, "{column} is bound to both {a} and {b}.")
declare("FB309", Severity.INFO, "Columns haven't been read yet. [Read now]")
declare("FB310", Severity.INFO, "Columns read {date} (may be out of date)")
declare("FB311", Severity.ERROR, "{name} is missing.")
declare(
    "FB312",
    Severity.INFO,
    "{table} has {n} rows. A search screen opens faster than a long list. [Use a search screen instead]",
)
declare("FB313", Severity.ERROR, "{link} in {table} doesn't point to {source table}.")
declare("FB314", Severity.ERROR, "Only a single SELECT can be a list's source.")
declare("FB315", Severity.WARNING, "{widget} can't be used here.")
declare("FB316", Severity.WARNING, "{file} has no {method}, so this form's data hook isn't checked.")
declare("FB317", Severity.WARNING, "The setup function isn't in connection_setup.py.")
declare("FB318", Severity.ERROR, "Records steps need this form connected to a table.")
declare("FB319", Severity.WARNING, "Saving a new {record} will fail: {column} is required and no field is bound to it.")
declare("FB320", Severity.ERROR, "A form has one lines grid in this version. Use a method for more.")
declare("FB321", Severity.WARNING, "This password file can be read by other users of this computer. [Fix]")
