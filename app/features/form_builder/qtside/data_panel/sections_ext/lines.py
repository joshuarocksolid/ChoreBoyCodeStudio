"""UX-LINES-001. Lines from a child table, or [Add lines…] when one points here."""

from __future__ import annotations

from typing import Any

from app.features.form_builder.engine.commands.base import CommandRejected
from app.features.form_builder.qtside.data_panel.host import narrate, session_of
from app.features.form_builder.qtside.data_panel.lines_sheet import (
    child_tables,
    lines_on,
    open_lines_sheet,
    summary,
    total_hint,
)
from app.features.form_builder.qtside.data_panel.model import record_source
from app.features.form_builder.qtside.data_panel.sections_ext import PanelSection
from app.qt.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


def _create(host: Any) -> QWidget:
    body = QWidget(host)
    body.setObjectName("formBuilder.data.lines")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    row = QHBoxLayout()
    layout.addLayout(row)
    sentence = QLabel(body)
    sentence.setObjectName("formBuilder.data.linesText")
    sentence.setWordWrap(True)
    row.addWidget(sentence, 1)
    edit = QPushButton("Edit…", body)
    edit.setObjectName("formBuilder.data.linesEdit")
    edit.clicked.connect(lambda: _edit(host))
    row.addWidget(edit)
    add = QPushButton("Add lines…", body)
    add.setObjectName("formBuilder.data.linesAdd")
    add.clicked.connect(lambda: _add(host))
    row.addWidget(add)
    hint = QLabel(body)
    hint.setObjectName("formBuilder.data.linesTotal")
    hint.setWordWrap(True)
    layout.addWidget(hint)

    def refresh() -> None:
        session = session_of(host)
        document = session.document if session is not None else None
        found = lines_on(document) if document is not None else ()
        sentence.setText(summary(document) if document is not None else "")
        hint.setText(total_hint(document) if document is not None else "")
        edit.setVisible(bool(found))
        add.setVisible(not found)

    body.refresh = refresh  # type: ignore[attr-defined]
    refresh()
    return body


def _applies(doc: Any) -> bool:
    source = record_source(doc)
    if source is None:
        return False
    if lines_on(doc):
        return True
    return bool(child_tables(doc, source))


def _edit(host: Any) -> None:
    session = session_of(host)
    if session is None:
        return
    found = lines_on(session.document)
    if not found:
        return
    try:
        open_lines_sheet(host, edit_name=found[0][0])
    except CommandRejected as exc:
        narrate(host, str(exc))


def _add(host: Any) -> None:
    try:
        open_lines_sheet(host)
    except CommandRejected as exc:
        narrate(host, str(exc))


def register(registry: Any) -> None:
    registry.add(PanelSection("lines", 60, _create, _applies))
