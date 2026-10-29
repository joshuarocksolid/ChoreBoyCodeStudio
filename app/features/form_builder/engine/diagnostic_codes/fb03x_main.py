"""Main-window diagnostic codes (UX_SPEC 13.2.10, FB036 and FB037)."""

from __future__ import annotations

from app.features.form_builder.engine.diagnostics import Severity, declare

declare("FB036", Severity.INFO, "An action is not on any menu, toolbar or widget.")
declare("FB037", Severity.WARNING, "A widget sits inside a toolbar or status bar.")
