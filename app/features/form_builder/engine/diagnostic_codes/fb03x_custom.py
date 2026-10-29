"""Your-own-class diagnostic code (UX_SPEC 13.2.10, M5.4)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB035", Severity.WARNING, "A class of your own comes from a module that is not in this project.")
