"""Alt+B and Ctrl+Shift+E, plus the keys the Events list handles itself."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.inspector import TabId
from app.features.form_builder.qtside.pickers import open_event_picker, set_method_actions

_FORM = ("form_tab",)
_LIST = ("behavior_list",)


def _behavior(surface: Any) -> None:
    surface.workbench.inspector.focus_tab(TabId.BEHAVIOR)


def _selected_name(surface: Any) -> str:
    session = surface.session
    ids = session.selection.state.ids
    document = session.document
    if len(ids) == 1:
        node = document.node(ids[0])
        for field in ("object_name", "name"):
            value = node.field(field)
            if isinstance(value, str) and value:
                return value
    return document.root.object_name


def add_event(surface: Any) -> None:
    """Ctrl+Shift+E and Form > Add event… share this."""
    from app.qt.QtWidgets import QWidget

    inspector = surface.workbench.inspector
    _behavior(surface)
    host = inspector.findChild(QWidget, "formBuilder.events.when")
    if host is None:
        host = inspector.findChild(QWidget, "formBuilder.events.first")
    if host is None:
        host = inspector
    open_event_picker(host, _selected_name(surface), "")


def register(keys: Any) -> None:
    from app.features.form_builder.integration.handlers import service

    set_method_actions(service())
    keys.key("form.action.behavior", "Behavior", "Alt+B", _FORM, run=_behavior)
    keys.key("form.action.addEvent", "Add event\u2026", "Ctrl+Shift+E", _FORM, run=add_event)
    keys.key("form.action.behaviorUp", "Previous event row", "Up", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorDown", "Next event row", "Down", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorEnter", "Open the event or step", "Enter", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorDelete", "Delete the event or step", "Delete", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorMoveUp", "Move the step up", "Alt+Up", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorMoveDown", "Move the step down", "Alt+Down", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorDuplicate", "Duplicate the step", "Ctrl+D", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorToggle", "Turn the step off or on", "Space", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorGoTo", "Go to code", "F12", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorFix", "Run the row's first fix", "Ctrl+.", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorMenu", "Event menu", "Shift+F10", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorMenuKey", "Event menu", "Menu", _LIST, kind="qt", available=True)
    keys.key("form.action.behaviorLeave", "Leave the Events list", "Esc", _LIST, kind="qt", available=True)
