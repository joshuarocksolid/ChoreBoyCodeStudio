"""The Logic section of the left pane. Alt+L focuses its filter."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QWidget

from app.features.form_builder.integration.workbench_ext import LeftSection
from app.features.form_builder.qtside.logic_panel.panel import LogicPanel


def _build(workbench: Any) -> LogicPanel:
    return LogicPanel(workbench)


def _focus(widget: Any) -> None:
    field = widget.findChild(QWidget, "formBuilder.logic.filter") if isinstance(widget, QWidget) else None
    if field is not None:
        field.setFocus()
        select = getattr(field, "selectAll", None)
        if callable(select):
            select()
        return
    if isinstance(widget, QWidget):
        widget.setFocus()


def register(slots: Any) -> None:
    slots.add_left_section(
        LeftSection("logic", "Logic", _build, order=25, weight=20, keys="Alt+L", focus=_focus)
    )
