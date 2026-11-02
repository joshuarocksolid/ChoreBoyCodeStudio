"""The Data section of the left pane. Ctrl+Shift+D is registered in keys_ext."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QWidget

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
    if isinstance(widget, QWidget):
        widget.setFocus()


def register(slots: Any) -> None:
    slots.add_left_section(
        LeftSection("data", "Data", _build, order=27, weight=20, focus=_focus)
    )
