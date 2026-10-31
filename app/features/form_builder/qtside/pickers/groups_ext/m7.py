"""M7 step-picker groups (UX-STEP-001). Discovered beside ``m6.py``."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.pickers.flow import Item
from app.features.form_builder.qtside.pickers.groups_ext import PickerGroup


def _fields(_ctx: object) -> list:
    return [
        Item("header", "", "FIELDS", header=True),
        Item("verb", "validate", "Check all fields"),
        Item("verb", "set", "Set a field"),
        Item("verb", "clear", "Clear fields"),
        Item("verb", "focus", "Move focus to"),
    ]


def _show(_ctx: object) -> list:
    return [
        Item("header", "", "SHOW", header=True),
        Item("verb", "show-hide", "Show or hide"),
        Item("verb", "enable-disable", "Enable or disable"),
        Item("verb", "message", "Show a message"),
        Item("verb", "ask", "Ask yes or no"),
        Item("verb", "page", "Switch tab or page"),
    ]


def _windows(_ctx: object) -> list:
    return [
        Item("header", "", "WINDOWS", header=True),
        Item("verb", "openForm", "Open another form"),
        Item("verb", "close", "Close this form"),
    ]


def _flow(_ctx: object) -> list:
    return [
        Item("header", "", "FLOW", header=True),
        Item("verb", "stop", "Stop here if\u2026"),
    ]


def register(registry: Any) -> None:
    add = getattr(registry, "add")
    add(PickerGroup("fields", 12, "FIELDS", _fields))
    add(PickerGroup("show", 14, "SHOW", _show))
    add(PickerGroup("windows", 16, "WINDOWS", _windows))
    add(PickerGroup("flow", 22, "FLOW", _flow))
