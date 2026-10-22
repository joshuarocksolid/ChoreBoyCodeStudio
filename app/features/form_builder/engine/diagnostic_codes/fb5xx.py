"""Codegen diagnostic codes (CONTRACTS.md section 7.2, FB501-FB507)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB501", Severity.WARNING, "A generated file was edited by hand.")
declare("FB502", Severity.ERROR, "A name on the form can't be generated.")
declare("FB503", Severity.ERROR, "A resource file is missing.")
declare("FB504", Severity.WARNING, "A promoted class header is not a Python module.")
declare("FB505", Severity.WARNING, "A generated file is out of date.")
declare("FB506", Severity.INFO, "This form is outside the project.")
declare("FB507", Severity.ERROR, "The form file name can't be a Python module.")
