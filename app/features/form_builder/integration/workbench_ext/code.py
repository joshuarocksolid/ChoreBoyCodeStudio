"""Arm the window-file checks when a form workbench opens."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.handler_checks_bridge import arm


def _surface_of(workbench: Any) -> Any:
    widget = workbench.parentWidget()
    while widget is not None:
        if hasattr(widget, "code_bridge") and hasattr(widget, "session"):
            return widget
        widget = widget.parentWidget()
    return None


def _attach(workbench: Any) -> None:
    surface = _surface_of(workbench)
    if surface is not None:
        arm(surface)


def register(slots: Any) -> None:
    slots.on_workbench(_attach, module=__name__)
