"""Form > Add event… uses the same command as Ctrl+Shift+E."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.integration.keys_ext.behavior import add_event


def register(registry: Any) -> None:
    registry.add(FormMenuItem("form.action.addEvent", ("Add event\u2026",), add_event, hint="Ctrl+Shift+E"))
