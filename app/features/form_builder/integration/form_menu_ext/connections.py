"""Form > Overlays > Connections and Show all connections (UX-ARR-005, UX-ARR-006)."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.integration.form_menu_ext import FormMenuItem
from app.features.form_builder.integration.workbench_ext.connections import links_for
from app.qt.QtGui import QAction

_TITLE = "Overlays"


def _visual(surface: Any) -> bool:
    return surface is not None and surface.can_use_overlays()


def _show_all_offered(surface: Any) -> bool:
    if not _visual(surface):
        return False
    host = links_for(surface)
    if host is None or surface is None:
        return True
    window = surface.window()
    action = window.findChild(QAction, "form.action.showAllConnections") if window is not None else None
    if action is not None:
        action.setCheckable(True)
        action.setChecked(host.show_all)
    return True


def register(registry: Any) -> None:
    registry.add(
        FormMenuItem(
            "form.action.connections",
            (_TITLE, "Connections"),
            lambda surface: surface.toggle_overlay("connections"),
            rank=2,
            enabled=_visual,
        )
    )
    registry.add(
        FormMenuItem(
            "form.action.showAllConnections",
            (_TITLE, "Show all connections"),
            lambda surface: _toggle(surface),
            rank=3,
            offered=_show_all_offered,
            enabled=_visual,
        )
    )


def _toggle(surface: Any) -> None:
    host = links_for(surface)
    if host is not None:
        host.toggle_show_all()
