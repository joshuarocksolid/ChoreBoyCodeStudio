"""The Data section of the left pane. Ctrl+Shift+D is registered in keys_ext."""

from __future__ import annotations

from typing import Any

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QWidget

from app.features.form_builder.integration.data_checks_bridge import arm
from app.features.form_builder.integration.workbench_ext import LeftSection
from app.features.form_builder.qtside.data_panel.panel import DataPanel


def open_connections_settings(workbench: object) -> None:
    """Open Settings on the Connections page. The signal stays connected even when no window is up."""

    window = workbench.window() if isinstance(workbench, QWidget) else None
    workflow = getattr(window, "_file_project_commands_workflow", None)
    opener = getattr(workflow, "_open_settings_dialog", None)
    if callable(opener):
        opener(page_key="connections")


def _build(workbench: Any) -> DataPanel:
    panel = DataPanel(workbench)
    panel.add_connection_requested.connect(lambda: open_connections_settings(workbench))
    return panel


def _focus(widget: Any) -> None:
    if not isinstance(widget, QWidget):
        return
    connect = widget.findChild(QWidget, "formBuilder.data.connect")
    if connect is not None and connect.isVisible() and connect.isEnabled():
        connect.setFocus()
        return
    no_focus = getattr(getattr(Qt, "FocusPolicy", Qt), "NoFocus")
    for child in widget.findChildren(QWidget):
        if child.isVisible() and child.isEnabled() and child.focusPolicy() != no_focus:
            child.setFocus()
            return
    widget.setFocusPolicy(getattr(getattr(Qt, "FocusPolicy", Qt), "StrongFocus"))
    widget.setFocus()


def _arm(workbench: Any) -> None:
    session = getattr(workbench, "session", None)
    if session is not None:
        arm(session)


def register(slots: Any) -> None:
    slots.add_left_section(
        LeftSection("data", "Data", _build, order=27, weight=20, focus=_focus)
    )
    slots.on_workbench(_arm, module=__name__)
