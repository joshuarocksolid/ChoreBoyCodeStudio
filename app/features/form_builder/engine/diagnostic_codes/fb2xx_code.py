"""Handler diagnostic codes FB201–FB213 (UX-CODE-011, M6.2a).

FB207 is declared here so the range has one owner. Nothing in M6 emits it.
Rules emit it in M7.
"""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB201", Severity.ERROR, "A method the form calls is not in the window class.")
declare("FB202", Severity.ERROR, "A method needs more values than the event sends.")
declare("FB203", Severity.INFO, "A method the form calls is still empty.")
declare("FB204", Severity.ERROR, "A method name would replace a method of the window's Qt class.")
declare("FB205", Severity.WARNING, "A method would run twice.")
declare("FB206", Severity.WARNING, "A method named for an event has no matching @Slot.")
declare("FB207", Severity.WARNING, "Your code sets a property a rule also controls.")
declare("FB208", Severity.WARNING, "A method name looks like an event name that does not match.")
declare("FB209", Severity.INFO, "The window file could not be checked.")
declare("FB210", Severity.WARNING, "The window file has no window class.")
declare("FB211", Severity.INFO, "Connect methods by name is off.")
declare("FB212", Severity.INFO, "A base class of the window could not be read.")
declare("FB213", Severity.ERROR, "A method the form calls cannot be called by Qt.")
