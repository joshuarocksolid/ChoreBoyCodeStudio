"""Ctrl+Shift+D focuses the Data pane. Alt+D opens the inspector Data tab."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.qtside.inspector import TabId

_FORM = ("form_tab",)


def _data_pane(surface: Any) -> None:
    workbench = surface.workbench
    focus = getattr(workbench, "focus_section", None)
    if callable(focus):
        focus("data")
        return
    from app.qt.QtWidgets import QWidget

    panel = workbench.findChild(QWidget, "formBuilder.dataPanel") if isinstance(workbench, QWidget) else None
    if panel is not None:
        panel.setFocus()


def _data_tab(surface: Any) -> None:
    surface.workbench.inspector.focus_tab(TabId.DATA)


def register(keys: Any) -> None:
    keys.key("form.action.data", "Data", "Ctrl+Shift+D", _FORM, run=_data_pane)
    keys.key("form.action.inspectorData", "Inspector data", "Alt+D", _FORM, run=_data_tab)
