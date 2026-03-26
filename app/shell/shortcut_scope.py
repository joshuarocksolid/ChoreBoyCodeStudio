"""Helpers for focus-scoped shortcut arbitration in shell."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.designer.editor_surface import DesignerEditorSurface


def should_route_designer_mode_shortcut(*, main_window: Any) -> bool:
    """Return True when designer mode shortcuts should win over Run shortcuts."""
    tabs = getattr(main_window, "_editor_tabs_widget", None)
    if tabs is None:
        return False
    current_widget = tabs.currentWidget()
    if current_widget is None:
        return False
    if not _is_designer_surface_instance(current_widget):
        return False
    focus_widget = _focus_widget()
    if focus_widget is None:
        return False
    return _is_widget_within_container(focus_widget, current_widget)


def _is_designer_surface_instance(widget: object) -> bool:
    """Return True when *widget* is a DesignerEditorSurface instance."""
    try:
        from app.designer.editor_surface import DesignerEditorSurface
    except Exception:
        return False
    return isinstance(widget, DesignerEditorSurface)


def _focus_widget() -> object | None:
    """Return currently focused widget, if any."""
    try:
        from PySide2.QtWidgets import QApplication
    except Exception:
        return None
    return QApplication.focusWidget()


def _is_widget_within_container(widget: object, container: object) -> bool:
    """Return True when *widget* is *container* or its descendant."""
    current = widget
    while current is not None:
        if current is container:
            return True
        parent = getattr(current, "parentWidget", None)
        if callable(parent):
            current = parent()
            continue
        parent = getattr(current, "parent", None)
        if callable(parent):
            current = parent()
            continue
        break
    return False
