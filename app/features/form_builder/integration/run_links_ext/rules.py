"""Run-console links from a check, a touch, or a recheck back to the field."""

from __future__ import annotations

import re
from typing import Optional

_FRAME = re.compile(
    r'File "([^"]+)", line \d+, in _cbcs_(?:recheck|touch|check)_([A-Za-z_][A-Za-z0-9_]*)'
)
_COMMENT = re.compile(r"#\s*([A-Za-z_][A-Za-z0-9_]*)\s*:")


def match(line: str) -> Optional[str]:
    """``widget:{name}`` for a check frame in ``ui_*.py`` or a ``# {widget}:`` comment."""
    frame = _FRAME.search(line or "")
    if frame is not None:
        filename = frame.group(1).replace("\\", "/").rsplit("/", 1)[-1]
        if filename.startswith("ui_") and filename.endswith(".py"):
            return "widget:%s" % frame.group(2)
    comment = _COMMENT.search(line or "")
    if comment is not None:
        return "widget:%s" % comment.group(1)
    return None


def open_checks(surface: object, widget_name: str) -> None:
    """Select ``widget_name`` and focus the first Checks row."""
    select = getattr(surface, "select_object", None)
    if not callable(select) or not select(widget_name):
        return
    workbench = getattr(surface, "workbench", None)
    inspector = getattr(workbench, "inspector", None)
    if inspector is None:
        return
    from app.features.form_builder.qtside.inspector import TabId

    focus = getattr(inspector, "focus_tab", None)
    if callable(focus):
        focus(TabId.BEHAVIOR)
    behavior = getattr(inspector, "behavior", None)
    section = None
    if behavior is not None and hasattr(behavior, "section_widget"):
        section = behavior.section_widget("checks")
    if section is None:
        from app.qt.QtWidgets import QWidget

        section = inspector.findChild(QWidget, "formBuilder.checks")
    opener = getattr(section, "focus_first", None)
    if callable(opener):
        opener()


def activate(target: str) -> None:
    if not isinstance(target, str) or not target.startswith("widget:"):
        return
    name = target.split(":", 1)[1]
    if not name:
        return
    surface = _surface()
    if surface is None:
        return
    open_checks(surface, name)


def _surface() -> object:
    from app.qt.QtWidgets import QApplication, QWidget

    from app.features.form_builder.integration.surface import FormSurface

    app = QApplication.instance()
    if app is None:
        return None
    for widget in app.topLevelWidgets():
        surface = getattr(widget, "_form_undo_surface", None)
        if isinstance(surface, FormSurface) and surface.isVisible():
            return surface
    for widget in app.allWidgets():
        if isinstance(widget, FormSurface) and widget.isVisible():
            return widget
        if isinstance(widget, QWidget):
            surface = getattr(widget, "_form_undo_surface", None)
            if isinstance(surface, FormSurface) and surface.isVisible():
                return surface
    return None


def register(registry: object) -> None:
    from app.features.form_builder.integration.run_links_ext import RunLink

    add = getattr(registry, "add", None)
    if not callable(add):
        return
    add(RunLink(match, activate))
