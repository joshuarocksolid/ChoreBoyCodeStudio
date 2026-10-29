"""Style sheet diagnostic codes (UX-STYLE-005, UX-STYLE-008): FB033, FB034."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB033", Severity.WARNING, "A style sheet can't be read, so Qt ignores all of it.")
declare("FB034", Severity.INFO, "A style rule matches nothing on the form.")
