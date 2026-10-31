"""Formula and step-reference codes (CONTRACTS.md section 17.13).

M7.1a declares every FB1xx code a later lane produces. Producers import this
module and do not declare again. FB106 stays in ``query/name_policy.py``.
FB116 is unused. That case is FB207.
"""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB101", Severity.ERROR, "Unknown name")
declare("FB102", Severity.ERROR, "Type mismatch")
declare("FB103", Severity.ERROR, "Not available in formulas")
declare("FB104", Severity.ERROR, "Circular values")
declare("FB105", Severity.ERROR, "Bad pattern")
declare("FB107", Severity.ERROR, "Excel habit")
declare("FB108", Severity.ERROR, "Syntax error")
declare("FB109", Severity.ERROR, "window.m() is not in the window class")
declare("FB110", Severity.INFO, "A window value has no type")
declare("FB111", Severity.ERROR, "Formula too long or nested too deep")
declare("FB112", Severity.ERROR, "Wrong number of values")
declare("FB113", Severity.ERROR, "A column outside an aggregate")
declare("FB114", Severity.ERROR, "No such value or attribute")
declare("FB115", Severity.ERROR, "Needs a data form")
declare("FB117", Severity.WARNING, "A one-off step changes a property a rule controls")
declare("FB118", Severity.WARNING, "Unknown kind or format")
declare("FB119", Severity.INFO, "A check has no error label")
declare("FB120", Severity.ERROR, "That form isn't in this project's forms folder")
