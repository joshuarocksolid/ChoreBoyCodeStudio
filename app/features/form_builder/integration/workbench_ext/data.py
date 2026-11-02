"""The Data section of the left pane. Ctrl+Shift+D is registered in keys_ext."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QWidget

from app.features.form_builder.integration.workbench_ext import LeftSection
from app.features.form_builder.qtside.data_panel.panel import DataPanel


def _build(workbench: Any) -> DataPanel:
    return DataPanel(workbench)


def _focus(widget: Any) -> None:
    if isinstance(widget, QWidget):
        widget.setFocus()


def register(slots: Any) -> None:
    slots.add_left_section(
        LeftSection("data", "Data", _build, order=27, weight=20, focus=_focus)
    )
