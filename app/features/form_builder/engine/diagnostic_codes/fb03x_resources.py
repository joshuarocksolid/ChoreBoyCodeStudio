"""Picture and resource-file diagnostic codes (UX_SPEC 13.2.10, M5.2)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB031", Severity.WARNING, "A picture is loaded from a file path.")
declare("FB032", Severity.WARNING, "A pictures file lists a file that is missing.")
