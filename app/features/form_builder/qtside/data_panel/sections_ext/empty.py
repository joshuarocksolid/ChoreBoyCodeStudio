"""UX-DATA-001. Connect opens the sheet. Add a connection stays for an empty project."""

from __future__ import annotations

from typing import Any

from app.qt.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from app.features.form_builder.engine.data.source import has_data_source
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection
from app.features.form_builder.qtside.data_panel.host import session_of
from app.features.form_builder.qtside.data_panel.model import connections_of

_SENTENCE = "This form isn't connected to a database."


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
    connect.setEnabled(True)
    connect.setToolTip("")
    connect.clicked.connect(lambda: _connect(host))
    layout.addWidget(connect)
    add = QPushButton("Add a connection\u2026", body)
    add.setObjectName("formBuilder.data.addConnection")
    add.setAccessibleName("Add a connection")
    add.setEnabled(True)
    add.setToolTip("")
    add.clicked.connect(host.add_connection_requested.emit)
    layout.addWidget(add)
    layout.addStretch(1)

    def refresh() -> None:
        session = session_of(host)
        has_connection = bool(connections_of(session, host)) if session is not None else False
        add.setVisible(not has_connection)

    body.refresh = refresh  # type: ignore[attr-defined]
    refresh()
    return body


def _connect(host: Any) -> None:
    from app.features.form_builder.qtside.data_panel.sheets import open_connect_sheet

    open_connect_sheet(host)
    emit = getattr(host, "connect_requested", None)
    if emit is not None:
        emit.emit()


def _applies(doc: Any) -> bool:
    return not has_data_source(doc)


def register(registry: Any) -> None:
    registry.add(PanelSection("empty", 10, _create, _applies))
