"""Steps other widgets aim at the selection (UX-BEH-015). Hidden when there are none."""

from __future__ import annotations

from typing import Optional

from app.qt.QtCore import Qt
from app.qt.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.features.form_builder.engine.query.selection import SelectionSource
from app.features.form_builder.engine.ui4.defaults import QtClassTable
from app.features.form_builder.qtside.inspector.behavior_ext import BehaviorSection, SectionHost, SectionInputs
from app.features.form_builder.qtside.inspector.behavior_ext._rows import IncomingRow, project_incoming
from app.features.form_builder.qtside.inspector.model import OneBehavior


class IncomingBody(QWidget):
    def __init__(self, host: SectionHost) -> None:
        super().__init__(host.parent)
        self.setObjectName("formBuilder.events.incoming")
        self._services = host.services
        self._rows = QVBoxLayout(self)
        self._rows.setContentsMargins(0, 4, 0, 4)
        title = QLabel("FROM OTHER WIDGETS", self)
        self._rows.addWidget(title)
        self._list = QVBoxLayout()
        self._rows.addLayout(self._list)

    def paint(self, inputs: SectionInputs) -> None:
        while self._list.count():
            item = self._list.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        view = inputs.view
        if not isinstance(view, OneBehavior) or not view.sender_name:
            return
        doc = inputs.session.document
        for row in project_incoming(doc, QtClassTable.shared(), view.sender_name):
            button = _Jump(row, self)
            self._list.addWidget(button)

    def go(self, row: IncomingRow) -> None:
        _select_and_focus(self, row.sender, row.signal, row.index)


class _Jump(QLabel):
    def __init__(self, row: IncomingRow, body: IncomingBody) -> None:
        super().__init__(row.words, body)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._row = row
        self._body = body
        self.setAccessibleName(row.words)

    def mousePressEvent(self, event: object) -> None:  # noqa: N802
        self._body.go(self._row)

    def keyPressEvent(self, event: object) -> None:  # noqa: N802
        from app.qt.qt_compat import enum_value

        key = enum_value(event.key())  # type: ignore[attr-defined]
        if key in (enum_value(Qt.Key.Key_Return), enum_value(Qt.Key.Key_Enter)):
            self._body.go(self._row)
            return
        super().keyPressEvent(event)  # type: ignore[arg-type]


def _applies(inputs: SectionInputs) -> bool:
    view = inputs.view
    if not isinstance(view, OneBehavior) or not view.sender_name:
        return False
    return bool(project_incoming(inputs.session.document, QtClassTable.shared(), view.sender_name))


def _create(host: SectionHost) -> QWidget:
    return IncomingBody(host)


def register(registry: object) -> None:
    registry.add(BehaviorSection("incoming", 35, _create, _applies))  # type: ignore[attr-defined]


def _select_and_focus(widget: QWidget, sender: str, signal: str, index: int) -> None:
    services = widget.parent()
    session = getattr(getattr(services, "_services", None), "session", None)
    if session is None:
        session = _session_of(widget)
    if session is None:
        return
    events = getattr(widget.parent(), "section_widget", None)
    body = events("events") if callable(events) else None
    note = getattr(body, "note_added", None)
    if callable(note):
        note(signal, index)
    found = session.document.by_name(sender)
    if not found:
        return
    session.selection.set((found[0],), source=SelectionSource.PROGRAM)


def _session_of(widget: QWidget) -> object:
    current: Optional[QWidget] = widget
    while current is not None:
        services = getattr(current, "_services", None)
        session = getattr(services, "session", None)
        if session is not None:
            return session
        current = current.parentWidget()
    return None
