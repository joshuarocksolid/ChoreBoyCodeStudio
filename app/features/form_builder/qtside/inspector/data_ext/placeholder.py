"""The only inspector Data sections M8.0s ships (UX-BIND-001)."""

from __future__ import annotations

from app.qt.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.features.form_builder.qtside.inspector.data_ext import DataSection

_NOT_BINDABLE = "Labels and layouts aren't bound. Select a field."
_NOT_BOUND = "Not bound"


def _sentence(parent: QWidget) -> QWidget:
    body = QWidget(parent)
    body.setObjectName("formBuilder.inspectorData.unbound")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 8, 0, 0)
    label = QLabel(_NOT_BINDABLE, body)
    label.setWordWrap(True)
    label.setObjectName("formBuilder.inspectorData.sentence")
    layout.addWidget(label)
    return body


def _placeholder(parent: QWidget) -> QWidget:
    body = QWidget(parent)
    body.setObjectName("formBuilder.inspectorData.placeholder")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 8, 0, 0)
    label = QLabel(_NOT_BOUND, body)
    label.setObjectName("formBuilder.inspectorData.notBound")
    layout.addWidget(label)
    return body


def _unbound(class_name: str) -> bool:
    return class_name == "QLabel" or class_name.endswith("Layout")


def register(registry: object) -> None:
    add = getattr(registry, "add")
    add(DataSection("not-bindable", 10, _sentence, _unbound))
    add(DataSection("not-bound", 20, _placeholder, lambda class_name: not _unbound(class_name)))
