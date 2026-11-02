"""UX-DATA-001, the only left-pane Data section M8.0s ships."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.form_builder.engine.data.source import has_data_source
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection

_SENTENCE = "This form isn't connected to a database."
_LATER = "Arrives with the data lanes"


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.empty")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    sentence = QLabel(_SENTENCE, body)
    sentence.setWordWrap(True)
    sentence.setObjectName("formBuilder.data.sentence")
    layout.addWidget(sentence)
    connect = QPushButton("Connect to a table\u2026", body)
    connect.setObjectName("formBuilder.data.connect")
    connect.setAccessibleName("Connect to a table")
    connect.setEnabled(False)
    connect.setToolTip(_LATER)
    connect.clicked.connect(host.connect_requested.emit)
    layout.addWidget(connect)
    add = QPushButton("Add a connection\u2026", body)
    add.setObjectName("formBuilder.data.addConnection")
    add.setAccessibleName("Add a connection")
    add.setEnabled(False)
    add.setToolTip(_LATER)
    add.clicked.connect(host.add_connection_requested.emit)
    layout.addWidget(add)
    layout.addStretch(1)
    return body


def _applies(doc: Any) -> bool:
    return not has_data_source(doc)


def register(registry: Any) -> None:
    registry.add(PanelSection("empty", 10, _create, _applies))
