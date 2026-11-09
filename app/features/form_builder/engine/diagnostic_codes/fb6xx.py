"""Preview and Try-mode diagnostic codes (CONTRACTS.md section 7.2)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB601", Severity.ERROR, "The preview process stopped unexpectedly.")
declare("FB602", Severity.WARNING, "A custom widget could not load in the preview.")
declare("FB603", Severity.ERROR, "The preview protocol version does not match.")
declare("FB604", Severity.ERROR, "Try mode hit an exception.")
declare("FB605", Severity.WARNING, "Preview is off after repeated crashes.")
