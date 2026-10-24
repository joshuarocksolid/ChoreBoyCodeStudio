"""Reader and structural diagnostic codes (CONTRACTS.md section 7.2)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB001", Severity.ERROR, "The form is not valid XML.", blocks_visual_open=True)
declare("FB002", Severity.ERROR, "The form has no root widget.", blocks_visual_open=True)
declare("FB003", Severity.WARNING, "The form version is not 4.x.")
declare("FB004", Severity.ERROR, "The form uses a forbidden XML declaration.", blocks_visual_open=True)
declare("FB005", Severity.INFO, "A value was kept as written.")
declare("FB006", Severity.INFO, "An unknown element was kept as written.")
declare("FB007", Severity.WARNING, "A property was set more than once.")
declare("FB008", Severity.ERROR, "The form is too large or too deeply nested.", blocks_visual_open=True)
declare("FB023", Severity.WARNING, "Two items share a form cell.")
