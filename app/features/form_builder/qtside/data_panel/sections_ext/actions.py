"""Bind fields by name, and the record toolbar (UX-DATA-003, UX-DATA-005)."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.edits import insert_record_toolbar
from app.features.form_builder.qtside.data_panel.model import record_source
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection
from app.qt.QtWidgets import QHBoxLayout, QPushButton, QWidget


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.actions")
    layout = QHBoxLayout(body)
    layout.setContentsMargins(0, 8, 0, 0)
    bind = QPushButton("Bind fields by name", body)
    bind.setObjectName("formBuilder.data.bindByName")
    bind.clicked.connect(lambda: _bind(host))
    layout.addWidget(bind)
    toolbar = QPushButton("Add record toolbar", body)
    toolbar.setObjectName("formBuilder.data.addToolbar")
    toolbar.clicked.connect(lambda: _toolbar(host))
    layout.addWidget(toolbar)
    layout.addStretch(1)
    return body


def _bind(host: Any) -> None:
    from app.features.form_builder.qtside.data_panel.sheets import open_bind_sheet

    open_bind_sheet(host)


def _toolbar(host: Any) -> None:
    session = session_of(host)
    if session is None:
        return
    try:
        insert_record_toolbar(session)
    except CommandRejected as exc:
        narrate(host, str(exc))


def _applies(doc: Any) -> bool:
    return record_source(doc) is not None


def register(registry: Any) -> None:
    registry.add(PanelSection("actions", 80, _create, _applies))
