"""Lines of a record. M8.3b fills this section. It stays hidden until a lines source exists."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QVBoxLayout, QWidget

from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.lines")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    return body


def _applies(doc: Any) -> bool:
    # M8.3b fills the line editor. A lines source is the only thing that shows it.
    del doc
    return False


def register(registry: Any) -> None:
    registry.add(PanelSection("lines", 60, _create, _applies))
